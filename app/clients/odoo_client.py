from datetime import date

import requests
from app.core.config import settings
from app.core.exceptions import OdooConnectionError, OdooRPCError, OdooTimeoutError


class OdooClient:
    def __init__(self):
        self.session = requests.Session()
        self.url = f"{settings.ODOO_BASE_URL}/jsonrpc"

    def _execute(self, model, method, args, kwargs=None):
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    settings.ODOO_DB,
                    settings.ODOO_UID,
                    settings.ODOO_API_KEY,
                    model,
                    method,
                    args,
                    kwargs or {},
                ],
            },
        }

        try:
            res = self.session.post(self.url, json=payload, timeout=settings.REQUEST_TIMEOUT)
            res.raise_for_status()
            data = res.json()

            if "error" in data:
                raise OdooRPCError(message=str(data["error"]))

            return data.get("result", [])

        except requests.Timeout:
            raise OdooTimeoutError()

        except requests.RequestException as e:
            raise OdooConnectionError(details={"raw": str(e)})

    def get_companies(self, names: list, ids: list | None = None):
        """
        Sumber data untuk entity Branch di eSuite.
        Match pakai ilike per nama (bukan exact 'in') supaya nggak gampang
        meleset gara-gara format string (koma, spasi, dst).

        ids (OPSIONAL, 21 Agustus 2026): filter tambahan "id in ids" (res.company
        id) -- dipakai buat upsert Branch tertentu saja lewat external_code,
        pola sama get_customers()/get_products(). Kosongkan untuk behavior
        normal (semua company in-scope).
        """
        conditions = self._name_in_domain(names)
        if ids:
            conditions = conditions + [("id", "in", ids)]
        domain = [conditions]

        return self._execute(
            "res.company",
            "search_read",
            domain,
            {"fields": ["id", "name", "partner_id"]},
        )

    def get_warehouses(self, company_ids: list, ids: list | None = None):
        """
        Sumber data untuk entity Warehouse di eSuite.
        WAJIB difilter company_ids -- tanpa ini kebawa semua warehouse dari
        4 badan usaha, padahal cuma 2 yang in-scope.

        ids (OPSIONAL, 21 Agustus 2026): filter tambahan "id in ids"
        (stock.warehouse id) -- dipakai buat upsert Warehouse tertentu saja
        lewat external_code. Kosongkan untuk behavior normal.
        """
        conditions = [("company_id", "in", company_ids), ("active", "=", True)]
        if ids:
            conditions.append(("id", "in", ids))
        domain = [conditions]

        return self._execute(
            "stock.warehouse",
            "search_read",
            domain,
            {"fields": ["id", "name", "code", "company_id"]},
        )

    def get_product_categories(self, ids: list | None = None):
        """
        Sumber data untuk entity Product Category di eSuite.
        Difilter cuma kategori di bawah "Saleable" -- sesuai aturan bisnis:
        produk yang boleh dijual/disync itu produk dengan category SALEABLE.
        Tidak difilter active -- model ini tidak punya field 'active' di Odoo 19.

        ids (OPSIONAL, 21 Agustus 2026): filter tambahan "id in ids"
        (product.category id) -- dipakai buat upsert kategori tertentu saja
        lewat external_code. Kosongkan untuk behavior normal.

        field "parent_id" (BARU, 27 Agustus 2026): dipakai OPSIONAL oleh
        product_category_sync_service.py utk resolve hierarki "parent" ke
        eSuite (fitur with_parent, default OFF -- lihat komentar di service
        itu). Many2one Odoo standar, balik [id, display_name] atau False
        kalau root (tidak punya parent).
        """
        conditions = [("complete_name", "ilike", "saleable")]
        if ids:
            conditions.append(("id", "in", ids))
        domain = [conditions]

        return self._execute(
            "product.category",
            "search_read",
            domain,
            {"fields": ["id", "name", "complete_name", "parent_id"]},
        )

    def get_products(self, ids: list | None = None):
        """
        Sumber data untuk entity Product di eSuite.
        Model: product.product (BUKAN product.template) -- field 'free_qty'
        (Free to Use) cuma ada di product.product. Konsekuensinya: 1 baris =
        1 ukuran/kemasan (sudah dikonfirmasi tidak ada konsep variant
        terpisah -- tiap ukuran = product.product id sendiri).

        Filter domain Odoo:
        - categ_id.complete_name ilike "ALL / SALEABLE" -- produk yang boleh dijual
        - list_price > 0 -- exclude produk yang harganya belum di-set
        - ids (OPSIONAL, 12 Agustus 2026) -- kalau diisi, tambahan filter
          "id in ids" -- dipakai buat upsert produk tertentu saja lewat
          external_code (lihat product_sync_service.py), bukan cuma semua
          produk sekaligus. Kosongkan (default None) untuk behavior normal.

        REVISI 5 Agustus 2026: filter free_qty > 0 DIHAPUS (baik di domain
        maupun di post-filter Python). Produk dengan free_qty = 0 tetap
        disync -- keputusan bisnis: stok kosong bisa berarti belum diupdate
        atau masih proses produksi, produk tetap boleh ditawarkan sales.
        Field free_qty tetap diambil & dikirim apa adanya (termasuk 0) lewat
        field stok terkait, cuma tidak lagi dipakai sebagai syarat exclude
        dari katalog produk. Lihat CONFIG_NOTES.md untuk detail keputusan ini.
        """
        conditions = [
            ("categ_id.complete_name", "ilike", "ALL / SALEABLE"),
            ("list_price", ">", 0),
        ]
        if ids:
            conditions.append(("id", "in", ids))
        domain = [conditions]

        # "default_code" (2 September 2026, ADDITIF) -- sebelumnya cuma
        # ditarik di get_products_raw() (diagnostic-only, GET /odoo/product)
        # tapi TIDAK PERNAH dipakai proses sync asli -- product_sync_service.py
        # selalu kirim variants[].sku = "" ke eSuite dengan alasan "Odoo tidak
        # punya SKU terpisah". Dev eDot kirim contoh payload /pricelists yang
        # WAJIB isi sku (master SKU produk, tidak boleh kosong utk webhook) --
        # ditambahkan di sini supaya field itu tersedia utk diisi ke sku,
        # lihat product_sync_service.py::_to_esuite_payload() &
        # pricelist_progress.md/product_variant_mirror_clarification.md.
        return self._execute(
            "product.product",
            "search_read",
            domain,
            {
                "fields": [
                    "id", "name", "default_code", "free_qty", "categ_id",
                    "list_price", "standard_price", "uom_id",
                ]
            },
        )

    def get_stock_by_warehouse(self, warehouse_id: int, product_ids: list | None = None):
        """
        Sumber data stok PER WAREHOUSE untuk entity Stock Matrix di eSuite,
        dipakai stock_sync_service.py (lihat stock_sync_progress.md).

        REVISI 17 Agustus 2026 (fix Bug #2, MENGGANTIKAN pendekatan lama) --
        versi SEBELUMNYA pakai computed field 'qty_available' dari
        product.product + context {"warehouse": warehouse_id} (asumsi Odoo
        native compute context cukup, TIDAK perlu baca stock.quant manual).
        TERBUKTI SALAH lewat test end-to-end 17 Agustus: context 'warehouse'
        TIDAK dihormati Odoo 19 instance ini -- hasilnya SELALU gabungan
        SEMUA warehouse (dicek: hasil dengan & tanpa context identik).
        Pembuktian: produk id 9169 balikin qty_available=16.72, padahal
        fisik CBU cuma 9.00 (cocok Odoo UI) + Sunshine Food 7.72 (cocok
        Odoo UI) = 16.72 persis -- CONFIRMED double-count lintas company.
        Ini jugalah risiko ICT (Inter-Company Transfer) yang sudah diflag
        14 Agustus 2026 ("kalau hasil stock-matrix tidak sesuai, ICT
        kandidat pertama buat dicek") -- sekarang terbukti nyata.

        SEKARANG: baca stock.quant MENTAH (bukan computed field), filter
        location_id.warehouse_id = warehouse_id + location_id.usage =
        "internal" (lokasi fisik nyata, exclude lokasi virtual/transit/
        partner) + location_id.complete_name mengandung "/Stock/" (lihat
        REVISI 18 Agustus di bawah -- exclude location staging/proses
        internal seperti Output/Pre-Production/Post-Production yang tetap
        usage="internal" tapi BUKAN zone stok fisik), lalu jumlahkan
        quantity per produk manual di Python. Pola warehouse+usage sudah
        diverifikasi akurat 100% match Odoo UI (lihat stock_sync_progress.md)
        -- filter "/Stock/" ditambahkan belakangan, BELUM diverifikasi ulang
        ke Odoo UI dengan filter baru ini (next step user).

        CATATAN behavior beda dari versi lama (dicatat sebagai referensi,
        BUKAN bug): produk yang TIDAK PERNAH punya baris stock.quant sama
        sekali di warehouse ini (belum pernah ada pergerakan stok) TIDAK
        AKAN MUNCUL di hasil (versi lama tetap muncul dengan qty_available:
        0). Efeknya di stock_sync_service.py: produk begitu masuk ke
        skipped_not_found_in_odoo, bukan dipush dengan quantity 0. Kalau
        nanti ada laporan "produk X nggak pernah ke-sync stoknya", ini
        kandidat pertama buat dicek (kemungkinan besar genuinely belum
        ada stok, bukan bug -- verifikasi via GET /odoo/stock-quant-raw).

        REVISI 17 Agustus 2026 (KEPUTUSAN BISNIS BARU, INTERIM -- lihat
        stock_sync_progress.md utk alasan lengkap & histori): field yang
        disync SEKARANG adalah FREE TO USE quantity, BUKAN raw on-hand.

        Alasan: user cek Odoo UI (Forecasted Report), "Quantity On Hand"
        mentah (dulu dipakai versi sebelumnya) ternyata masih menghitung
        "Expired Stock" -- stok yang SUDAH lewat tanggal removal & tinggal
        nunggu di-destroy, TIDAK BENERAN BISA DIJUAL. Contoh nyata: produk
        9169 "PAULS Butter", CBU on-hand = 9.00 (0.72 expired + 8.28
        beneran available/"Free Stock" di Odoo UI). Kalau kita push 9.00
        mentah, sales bisa nawarin 0.72 unit yang sebenarnya sudah rusak/
        kadaluarsa -- resiko bisnis nyata.

        Formula "free to use" yang dipakai di sini:
          SUM(quantity) - SUM(reserved_quantity) - SUM(quantity milik lot
          yang removal_date-nya SUDAH LEWAT hari ini, dianggap "Expired
          Stock, to remove now" persis kayak kategori di Odoo UI)

        INI KEPUTUSAN INTERIM, BUKAN final -- SENGAJA TIDAK termasuk stok
        "Forecasted" (dari PO/production yang dijadwalkan datang tapi
        belum fisik ada). Secara bisnis sales idealnya bisa lihat 2 angka
        terpisah (stok yang beneran ada sekarang vs proyeksi ke depan),
        tapi itu perlu keputusan/desain terpisah (mis. field tambahan di
        eSuite) -- BELUM dibahas/diputuskan. Untuk sekarang: minimal sales
        dapat angka yang BENERAN bisa dijual hari ini, bukan angka yang
        ikut ke-inflate stok expired.

        ASUMSI (belum divalidasi 100%): field 'removal_date' di model
        'stock.lot' -- field standar Odoo (product_expiry addon) yang
        drive kategori "to remove now" vs "to remove on <tanggal>" di
        Forecasted Report. Kalau field ini ternyata tidak ada/beda nama
        di instance ini, RPC bakal langsung error jelas (nama field
        salah), gampang disesuaikan.

        Domain Saleable sengaja SAMA dengan get_products() -- cuma produk
        yang disync ke eSuite yang perlu stok-nya disync juga.

        product_ids (OPSIONAL): filter tambahan "product_id in product_ids",
        pola sama dengan get_products() -- kosongkan untuk semua produk
        Saleable.

        REVISI 18 Agustus 2026 (KEPUTUSAN BISNIS BARU, ditemukan via GET
        /odoo/stock-location) -- filter `usage="internal"` SAJA TERNYATA
        TIDAK CUKUP. 1 warehouse Odoo punya BEBERAPA location usage=
        "internal" selain zone stok fisik, misalnya `CBU/Output`,
        `CBU/Pre-Production`, `CBU/Post-Production` -- semua itu location
        staging/proses internal, BUKAN representasi stok yang beneran bisa
        dijual, tapi tetap usage="internal" jadi ikut ke-hitung SEBELUM fix
        ini. Konfirmasi higher-up: location valid = pola
        "<KodeCompany>/Stock/<Zone>" (mis. CBU/Stock/AC, SFC/Stock/Frozen,
        SAP/Stock/Dry -- AC/Chiller/Dry/Frozen = marker zone type/suhu).

        Filter tambahan: `location_id.complete_name ilike "/Stock/"` --
        dipilih SUBSTRING match "/Stock/" (dengan slash di kedua sisi),
        BUKAN daftar hardcode nama zone (AC/Chiller/Dry/Frozen) supaya:
        (1) otomatis meng-exclude location PARENT "<Company>/Stock" itu
        sendiri (tidak ada "/" setelah "Stock" di complete_name-nya, cuma
        cocok kalau ada child location di bawahnya, mis. ".../Stock/AC"),
        (2) tetap ikut kalau suatu saat ada zone type baru selain 4 yang
        sudah ada sekarang (tidak perlu update kode lagi tiap ada zone
        baru). CATATAN: pola ini otomatis IKUT-kan "SAP/Stock/Supply"
        (zone ke-13, bukan cuma 4 zone AC/Chiller/Dry/Frozen yang dikasih
        contoh) dan otomatis EXCLUDE "SUPL/Stock" (warehouse "Supplies",
        company CBU -- tidak punya child zone) -- BELUM eksplisit
        dikonfirmasi user, di-flag terpisah di stock_sync_progress.md.
        """
        conditions = [
            ("location_id.warehouse_id", "=", warehouse_id),
            ("location_id.usage", "=", "internal"),
            ("location_id.complete_name", "ilike", "/Stock/"),
            ("product_id.categ_id.complete_name", "ilike", "ALL / SALEABLE"),
        ]
        if product_ids:
            conditions.append(("product_id", "in", product_ids))
        domain = [conditions]

        quants = self._execute(
            "stock.quant",
            "search_read",
            domain,
            {"fields": ["product_id", "quantity", "reserved_quantity", "lot_id"]},
        )

        # Resolve removal_date per lot -- buat exclude stok yang sudah
        # "Expired Stock, to remove now" dari total free-to-use.
        lot_ids = list({q["lot_id"][0] for q in quants if q.get("lot_id")})
        removal_dates = {}
        if lot_ids:
            lots = self._execute(
                "stock.lot",
                "search_read",
                [[("id", "in", lot_ids)]],
                {"fields": ["id", "removal_date"]},
            )
            removal_dates = {lot["id"]: lot["removal_date"] for lot in lots}

        today_str = date.today().isoformat()

        totals = {}
        for q in quants:
            lot = q.get("lot_id")
            removal_date = removal_dates.get(lot[0]) if lot else None
            if removal_date and removal_date <= today_str:
                continue  # expired, dijadwalkan destroy -- exclude dari free-to-use

            pid = q["product_id"][0]
            free_qty = q["quantity"] - (q.get("reserved_quantity") or 0)
            totals[pid] = totals.get(pid, 0) + free_qty

        return [{"id": pid, "qty_available": qty, "free_qty": qty} for pid, qty in totals.items()]

    def get_stock_quants(self, product_id: int):
        """
        DIAGNOSTIC-ONLY (17 Agustus 2026) -- baca stock.quant MENTAH per
        produk, TERMASUK detail lokasi (complete_name/usage/warehouse_id/
        company_id per baris) -- BUKAN computed qty_available seperti
        get_stock_by_warehouse(). Dibuat buat investigasi dugaan ICT
        (Inter-Company Transfer) bikin context {"warehouse": id} di
        get_stock_by_warehouse() ke-leak lintas company (lihat
        stock_sync_progress.md -- bukti: qty_available warehouse CBU =
        16.72, padahal fisik CBU cuma 9.00 & Sunshine Food Free Stock
        7.72 -- 9.00 + 7.72 = 16.72 persis, indikasi kuat ke-double-count).

        Tidak pakai context apapun (sengaja) -- baca SEMUA baris quant
        produk ini apa adanya, biar kelihatan lokasi mana aja yang
        nyumbang stok & apakah ada lokasi "asing" (company lain / lokasi
        transit ICT) yang mestinya tidak masuk hitungan warehouse CBU.

        REVISI 17 Agustus 2026: field "product_id" ditambah ke fields --
        Odoo search_read otomatis balikin [id, display_name] utk field
        many2one, jadi nama produk ikut tampil di tiap baris (user nggak
        perlu buka Odoo lagi cuma buat tahu "product_id sekian itu produk
        apa"). Tidak perlu RPC call tambahan.
        """
        quants = self._execute(
            "stock.quant",
            "search_read",
            [[("product_id", "=", product_id)]],
            {"fields": ["id", "product_id", "location_id", "company_id", "quantity", "reserved_quantity", "lot_id", "in_date"]},
        )

        location_ids = list({q["location_id"][0] for q in quants if q.get("location_id")})
        locations = {}
        if location_ids:
            loc_records = self._execute(
                "stock.location",
                "search_read",
                [[("id", "in", location_ids)]],
                {"fields": ["id", "complete_name", "usage", "warehouse_id", "company_id"]},
            )
            locations = {loc["id"]: loc for loc in loc_records}

        for q in quants:
            loc_id = q["location_id"][0] if q.get("location_id") else None
            q["location_detail"] = locations.get(loc_id)

        return quants

    def get_stock_locations(self, usage: str | None = "internal"):
        """
        DIAGNOSTIC-ONLY (18 Agustus 2026) -- baca SEMUA stock.location Odoo
        (bukan cuma yang nyangkut ke 1 produk seperti get_stock_quants()).

        Dibuat buat verifikasi konfirmasi bisnis (lihat stock_sync_progress.md):
        apakah location usage="internal" SELALU punya complete_name yang
        mengandung "Stock" -- karena nama location itu human input (bukan
        field terkontrol/enum), berisiko ada pengecualian/typo. Jangan cuma
        asumsi dari beberapa contoh -- endpoint ini biar bisa dicek ke data
        ASLI, semua baris sekaligus.

        Field 'contains_stock' ditambahkan per baris (dihitung di Python,
        BUKAN dari Odoo) -- True kalau substring "stock" ada di
        complete_name (case-insensitive). Biar baris yang FALSE (kandidat
        exception/typo) langsung kelihatan tanpa scan manual satu-satu.

        usage: filter stock.location.usage standar Odoo (internal/supplier/
        customer/inventory/transit/view/production). Default "internal",
        sama dengan yang dipakai get_stock_by_warehouse(). Kosongkan (None)
        untuk lihat SEMUA location apapun usage-nya.
        """
        domain = [[("usage", "=", usage)]] if usage else [[]]
        locations = self._execute(
            "stock.location",
            "search_read",
            domain,
            {"fields": ["id", "complete_name", "usage", "warehouse_id", "company_id", "active"]},
        )
        for loc in locations:
            loc["contains_stock"] = "stock" in (loc.get("complete_name") or "").lower()
        return locations

    def get_categories_by_ids(self, ids: list):
        """
        Ambil name asli (leaf name, bukan complete_name) untuk sekumpulan
        category id -- dipakai product_sync_service buat cocokkan balik ke
        eSuite product-category, KARENA GET /product-category eSuite tidak
        balikin external_code sama sekali (lihat CONFIG_NOTES.md), jadi
        matching terpaksa pakai name.
        """
        if not ids:
            return {}

        domain = [[("id", "in", ids)]]
        records = self._execute(
            "product.category",
            "search_read",
            domain,
            {"fields": ["id", "name"]},
        )
        return {r["id"]: r["name"] for r in records}

    def get_customers(self, ids: list | None = None, names: list | None = None):
        """
        Sumber data untuk entity Customer di eSuite.
        Model: res.partner, difilter customer_rank > 0 (konvensi standar Odoo
        untuk "kontak yang pernah/bisa jadi customer" -- dikonfirmasi user
        7 Agustus 2026) + active = True (exclude kontak yang sudah diarsip,
        konsisten dengan pola get_warehouses()).

        company_type diambil MENTAH dari Odoo ("company"/"person") -- mapping
        ke value eSuite ("company"/"individual") dilakukan di
        customer_sync_service.py, BUKAN di sini, supaya odoo_client tetap
        cuma baca data mentah tanpa logic transformasi bisnis.

        Catatan (dari user): field Odoo yang benar untuk tipe customer itu
        `company_type`, BUKAN `type` -- `res.partner.type` artinya jenis
        alamat (invoice/delivery/dll), bukan tipe entitas customer.

        ids (OPSIONAL, 12 Agustus 2026): filter tambahan "id in ids" --
        dipakai buat upsert customer tertentu saja lewat external_code
        (lihat customer_sync_service.py). Kosongkan untuk behavior normal.

        names (OPSIONAL, 31 Agustus 2026): filter tambahan cari customer BY
        NAMA (bukan id Odoo) -- dipakai fitur "upsert customer by nama"
        (comma-separated di endpoint, bisa banyak nama sekaligus), lihat
        customer_sync_service.py::_match_customers_by_name(). Match EXACT
        case-insensitive per nama (operator Odoo "=ilike", BUKAN ilike
        biasa/substring yang dipakai get_companies()) -- keputusan user:
        exact match supaya tidak salah tangkap record yang mirip, filter
        customer_rank>0/active=True TETAP berlaku sama seperti filter ids.

        phone/email (21 Agustus 2026): ditambahkan setelah live test
        `POST /sync/customers` konfirmasi field ini benar-benar tersimpan &
        tampil di GET eSuite (beda dari currency yang masih pending -- lihat
        CONFIG_NOTES.md). Field standar res.partner, sama nama-nya dengan
        yang sudah dipakai di get_contacts().

        ⚠️ "mobile" SENGAJA TIDAK diikutkan (dihapus lagi 21 Agustus 2026,
        beberapa jam setelah ditambahkan) -- Odoo 19 instance CBU error
        "Invalid field 'mobile'" pas query res.partner. Field ini memang
        sudah dihapus resmi dari Contacts di Odoo 19 (di-merge ke `phone`,
        dikonfirmasi user), BUKAN field standar lagi di versi ini walau
        masih ada di Odoo versi lama/dokumentasi umum. Jangan tambahkan
        balik tanpa cek dulu apakah field ini benar-benar ada di instance
        Odoo yang dipakai.

        street/partner_latitude/partner_longitude (24 Agustus 2026): ditambah
        untuk isi "addresses[]" di payload Customer -- field SAMA yang dipakai
        get_partner_address() (branch_sync_service.py), tapi di sini LANGSUNG
        masuk ke query bulk ini (bukan panggil terpisah per record) karena
        volume Customer bisa ribuan -- N+1 query per customer terlalu mahal,
        beda dari Branch yang cuma ~3 record. Lihat
        customer_sync_service.py::_to_esuite_address().

        property_product_pricelist (26 Agustus 2026, DIAGNOSTIC-ONLY, TIDAK
        dipakai _to_esuite_payload() -- lihat customer_sync_service.py, field
        di sana di-assign eksplisit key-by-key jadi field baru ini otomatis
        AMAN, tidak ikut ke-push kemana-mana sampai memang ditambahkan).
        Field standar Odoo (many2one ke product.pricelist) -- kandidat SSOT
        buat Customer -> Pricelist mapping (Task #4, PDF 9.8) yang lebih
        reliable daripada mapping manual/parsing nama pricelist. Ditambahkan
        supaya bisa dicek dulu lewat GET /odoo/customer apakah field ini
        ke-populate di instance Odoo CBU (mis. utk outlet PEPITO) sebelum
        diputuskan mau dipakai buat automasi mapping atau tidak.
        """
        conditions = [("customer_rank", ">", 0), ("active", "=", True)]
        if ids:
            conditions.append(("id", "in", ids))
        if names:
            conditions = conditions + self._name_in_domain(names, op="=ilike")
        domain = [conditions]

        return self._execute(
            "res.partner",
            "search_read",
            domain,
            {
                "fields": [
                    "id", "name", "company_type", "phone", "email",
                    "street", "partner_latitude", "partner_longitude",
                    "property_product_pricelist",
                ]
            },
        )

    # ------------------------------------------------------------------
    # GET / inspeksi mentah (16 Agustus 2026) -- dipakai
    # app/api/routes/odoo_get.py (grup Swagger "odoo - Get"), TUJUANNYA
    # cuma buat cek data Odoo 19 lewat Swagger/Postman. BEDA dari
    # method-method di atas (get_products/get_customers/dst) yang punya
    # domain filter khusus proses sync -- method di bawah ini SENGAJA
    # tanpa filter Saleable/list_price/dst supaya bisa lihat data apa
    # adanya. TIDAK dipakai proses sync manapun (product_sync_service.py
    # dkk tetap pakai method lama, tidak disentuh).
    # ------------------------------------------------------------------

    def get_products_raw(self, limit: int | None = None, ids: list | None = None, name: str | None = None):
        """GET mentah product.product -- tanpa filter Saleable/list_price."""
        conditions = []
        if ids:
            conditions.append(("id", "in", ids))
        if name:
            conditions.append(("name", "ilike", name))
        domain = [conditions] if conditions else [[]]

        kwargs = {
            "fields": [
                "id", "name", "default_code", "categ_id", "list_price",
                # "product_tmpl_id" -- DITAMBAHKAN 25 Agustus 2026, additif
                # (field baru di response, tidak ubah field lain). Dibutuhkan
                # supaya bisa cari pricelist yang memuat 1 produk tertentu:
                # product.pricelist.item Odoo CBU SELALU pakai product_tmpl_id
                # (bukan product_id, lihat FIX 18 Agustus di
                # get_product_ids_by_template_ids()) -- jadi GET /odoo/product
                # perlu ikut tampilkan id template-nya, dipakai sebagai filter
                # GET /odoo/pricelist-item?product_tmpl_id=... (lihat method
                # get_pricelist_items() di bawah).
                "standard_price", "qty_available", "free_qty", "uom_id", "active",
                "product_tmpl_id",
            ],
        }
        if limit:
            kwargs["limit"] = limit

        return self._execute("product.product", "search_read", domain, kwargs)

    def get_uoms(self, limit: int | None = None, name: str | None = None):
        """GET mentah uom.uom (Unit of Measure)."""
        conditions = [("name", "ilike", name)] if name else []
        domain = [conditions] if conditions else [[]]

        kwargs = {"fields": ["id", "name", "category_id", "uom_type", "factor", "active"]}
        if limit:
            kwargs["limit"] = limit

        return self._execute("uom.uom", "search_read", domain, kwargs)

    def get_contacts(
        self,
        limit: int | None = None,
        name: str | None = None,
        customer_only: bool = False,
        supplier_only: bool = False,
        active_only: bool = True,
    ):
        """
        GET mentah res.partner -- dipakai GET /odoo/contact & GET /odoo/customer.
        BEDA dari get_customers() (dipakai proses sync /sync/customers):
        method ini buat inspeksi manual/fleksibel, bukan proses sync.

        Konvensi Odoo standar (dikonfirmasi user 16 Agustus 2026):
        - customer_rank > 0 -> kontak dianggap pernah/bisa jadi Customer
        - customer_rank = 0 -> belum pernah jadi customer
        - supplier_rank > 0 -> kontak pernah/merupakan Vendor
        customer_only=True -> filter customer_rank > 0 (dipakai GET /odoo/customer).
        supplier_only=True -> filter supplier_rank > 0.
        Default (keduanya False) -> semua kontak apa adanya (GET /odoo/contact).
        """
        conditions = []
        if customer_only:
            conditions.append(("customer_rank", ">", 0))
        if supplier_only:
            conditions.append(("supplier_rank", ">", 0))
        if active_only:
            conditions.append(("active", "=", True))
        if name:
            conditions.append(("name", "ilike", name))
        domain = [conditions] if conditions else [[]]

        kwargs = {
            "fields": [
                "id", "name", "company_type", "customer_rank",
                "supplier_rank", "active", "email", "phone",
                # user_id -- field "Salesperson" (18 Agustus 2026, lihat
                # get_salespersons()/get_customers_by_salesperson() di bawah).
                # Ikut ditampilkan di sini juga (additif, tidak ubah signature)
                # supaya GET /odoo/customer & /odoo/contact langsung kelihatan
                # salesperson-nya tanpa perlu panggil endpoint terpisah.
                "user_id",
                # street/partner_latitude/partner_longitude -- disamakan
                # (24 Agustus 2026) dengan get_customers() yang sekarang
                # sudah tarik field ini juga (dipakai isi "addresses[]" di
                # payload upsert Customer, lihat customer_sync_service.py::
                # _to_esuite_address()). Ditambahkan di sini juga (diagnostic-
                # only, additif) supaya GET /odoo/customer & /odoo/contact
                # kelihatan data alamat yang SAMA PERSIS dengan yang bakal
                # dikirim ke eSuite -- bisa dicek dulu lewat Swagger sebelum
                # sync, tanpa perlu panggil endpoint terpisah.
                "street", "partner_latitude", "partner_longitude",
                # property_product_pricelist -- SAMA dengan get_customers()
                # (26 Agustus 2026, diagnostic-only, lihat docstring di sana
                # untuk alasan lengkap). Diikutkan di sini juga supaya
                # GET /odoo/customer & /odoo/contact langsung kelihatan
                # pricelist assignment Odoo tanpa panggil endpoint lain.
                "property_product_pricelist",
                # category_id (4 September 2026, DIAGNOSTIC-ONLY, TIDAK
                # dipakai get_customers()/_to_esuite_payload() manapun).
                # 🆕 STATUS DIREVISI (4 September, sesi sama): SEBELUMNYA
                # kandidat SSOT Customer Group -- SEKARANG diturunkan jadi
                # "Customer Label" (istilah user, res.partner.category /
                # Contact Tags) -- sepertinya cuma tag bebas admin Odoo,
                # BUKAN representasi Customer Group yang sebenarnya. TETAP
                # diikutkan di sini (harmless, referensi), tapi field
                # `industry_id` di bawah yang jadi kandidat utama sekarang.
                # Datang sbg list of [id, display_name] tuple (many2many
                # Odoo standar) -- match ke GET /odoo/customer-label.
                "category_id",
                # industry_id (4 September 2026, DIAGNOSTIC-ONLY, TIDAK
                # dipakai get_customers()/_to_esuite_payload() manapun).
                # Field STANDAR Odoo "Industry" (many2one ke
                # res.partner.industry) -- kandidat SSOT BARU utk Customer
                # Group eSuite (belum 100% dikonfirmasi user, lihat
                # sales_entities_gap.md). Ditambahkan supaya user bisa cek
                # LANGSUNG lewat Swagger isi per customer sebelum diputuskan
                # mapping/logic sync-nya (pola diagnostic-dulu yang sama).
                # Datang sbg [id, display_name] tuple (many2one Odoo
                # standar) atau `false` kalau kosong -- match ke GET
                # /odoo/industry.
                "industry_id",
            ],
        }
        if limit:
            kwargs["limit"] = limit

        return self._execute("res.partner", "search_read", domain, kwargs)

    def get_salespersons(self, limit: int | None = None, name: str | None = None):
        """
        GET debug -- res.users, dipakai GET /odoo/salesperson (18 Agustus 2026).

        ASUMSI, BELUM DIKONFIRMASI USER (lihat sales_entities_gap.md poin
        "apakah CBU pakai hr.employee untuk data Salesman"): "Salesperson"
        di sini diartikan sebagai konvensi standar Odoo Sales App --
        res.users yang di-assign lewat field res.partner.user_id (label UI
        "Salesperson"). Filter share=False buat exclude portal/user eksternal
        (cuma internal user yang biasanya jadi salesperson). Kalau ternyata
        CBU nyimpen data salesperson terpisah di hr.employee, endpoint ini
        perlu disesuaikan -- kabari kalau hasilnya kelihatan gak sesuai
        (mis. yang keluar cuma akun admin/teknis, bukan tim sales beneran).
        """
        conditions = [("share", "=", False)]
        if name:
            conditions.append(("name", "ilike", name))
        domain = [conditions]

        kwargs = {"fields": ["id", "name", "login", "email", "active"]}
        if limit:
            kwargs["limit"] = limit

        return self._execute("res.users", "search_read", domain, kwargs)

    def get_customers_by_salesperson(self, salesperson_id: int, limit: int | None = None):
        """
        GET debug -- res.partner yang field Salesperson (user_id) = salesperson_id
        tertentu, dipakai GET /odoo/customer-by-salesperson (18 Agustus 2026).
        """
        domain = [[("user_id", "=", salesperson_id)]]
        kwargs = {
            "fields": ["id", "name", "company_type", "customer_rank", "supplier_rank", "user_id"],
        }
        if limit:
            kwargs["limit"] = limit

        return self._execute("res.partner", "search_read", domain, kwargs)

    def get_salesperson_by_customer(self, customer_id: int):
        """
        GET debug -- balikan Salesperson (res.users, dari field user_id) yang
        di-assign ke 1 customer tertentu, dipakai GET /odoo/salesperson-by-customer
        (18 Agustus 2026). Return None kalau customer_id tidak ditemukan.
        """
        records = self._execute(
            "res.partner",
            "read",
            [[customer_id]],
            {"fields": ["id", "name", "user_id"]},
        )
        return records[0] if records else None

    def get_order_history_by_customer(self, customer_id: int, limit: int | None = None):
        """
        GET mentah riwayat Sales Order (sale.order + sale.order.line) milik
        1 Customer tertentu -- diagnostic-only (28 Agustus 2026), dipakai
        GET /odoo/order-history-by-customer. TUJUAN: riset/lihat bentuk data
        asli sale.order Odoo 19 CBU dulu SEBELUM dipetakan ke payload webhook
        eDot POST /v1/webhook/orders/import (lihat order_history_import.md
        di project memory utk detail endpoint eDot & pertanyaan terbuka ke
        dev) -- endpoint ini TIDAK push apapun ke eSuite, murni GET.

        Domain filter: partner_id = customer_id LANGSUNG (bukan
        commercial_partner_id) -- konsisten dengan konvensi project ini,
        "Outlet" = 1 res.partner tunggal (customer_rank > 0), bukan struktur
        parent/child company (lihat sales_entities_gap.md, "Outlet
        dikonfirmasi = Customer, bukan entity baru"). Kalau ternyata di data
        live CBU order-nya nempel ke child contact/alamat pengiriman
        terpisah (bukan partner utama), field ini perlu direvisi -- baru
        kelihatan setelah dicoba live.

        order: date_order DESC -- order terbaru duluan, lebih berguna buat
        inspeksi manual daripada urutan id.

        Order header fields dipilih dari model standar Odoo Sales
        (`sale.order`) -- BELUM DIVALIDASI ke instance Odoo CBU (pola sama
        seperti get_pricelists()/get_pricelist_items(), assistant tidak
        punya akses network langsung ke Odoo dari sandbox cloud). Kalau
        muncul error RPC (field/model tidak ada/tidak accessible dari API
        key ini), kabari pesan errornya biar disesuaikan.

        ⚠️ "state" Odoo 19: kemungkinan cuma ada draft/sent/sale/cancel
        (value "done" yang lama sudah digantikan field terpisah `locked` di
        versi Odoo yang lebih baru -- BELUM dikonfirmasi persis di versi 19
        CBU). Field `locked` ikut diambil sebagai jaga-jaga. JANGAN
        petakan ke field `status` payload webhook eDot dulu sebelum dicek
        nilai aslinya dari hasil live endpoint ini.

        FIX LIVE (28 Agustus 2026): field UOM di sale.order.line BUKAN
        `product_uom` (error RPC "Invalid field 'product_uom' on
        'sale.order.line'" dari live test user) -- di Odoo 19 CBU sudah
        `product_uom_id` (konsisten dengan konvensi Many2one modern Odoo,
        field lama `product_uom` di versi Odoo sebelumnya di-rename).
        Sudah diperbaiki di query field list di bawah, BELUM di-retest live
        pasca fix ini.
        """
        domain = [[("partner_id", "=", customer_id)]]
        kwargs = {
            "fields": [
                "id", "name", "date_order", "state", "locked",
                "invoice_status", "partner_id", "user_id", "currency_id",
                "amount_untaxed", "amount_tax", "amount_total",
                # company_id -- BARU 29 Agustus 2026, dipakai
                # order_history_sync_service.py buat field "branch" di
                # payload orders/import (dev eDot minta ditambahkan). Many2one
                # standar, balik sbg [id, display_name].
                "company_id",
            ],
            "order": "date_order desc",
        }
        if limit:
            kwargs["limit"] = limit

        orders = self._execute("sale.order", "search_read", domain, kwargs)
        if not orders:
            return []

        order_ids = [o["id"] for o in orders]
        lines = self._execute(
            "sale.order.line",
            "search_read",
            [[("order_id", "in", order_ids)]],
            {
                "fields": [
                    "id", "order_id", "product_id", "name",
                    "product_uom_qty", "product_uom_id", "price_unit",
                    "discount", "price_subtotal", "price_tax", "price_total",
                ],
            },
        )

        lines_by_order = {}
        for line in lines:
            # order_id datang sbg [id, display_name] (many2one Odoo standar)
            order_id = line["order_id"][0] if line["order_id"] else None
            lines_by_order.setdefault(order_id, []).append(line)

        for order in orders:
            order["lines"] = lines_by_order.get(order["id"], [])

        return orders

    def get_customer_labels(self, limit: int | None = None):
        """
        GET mentah res.partner.category (Contact Tags) -- RENAMED dari
        get_customer_categories() (4 September 2026). SEBELUMNYA dianggap
        kandidat SSOT Customer Group -- SEKARANG diturunkan statusnya jadi
        "Customer Label" murni (istilah user): tag bebas yang ditambahkan
        admin Odoo, TAPI sepertinya TIDAK dipakai/tidak representasikan
        Customer Group beneran (lihat sales_entities_gap.md). Kandidat SSOT
        yang lebih kuat sekarang field `industry_id` (res.partner.industry),
        lihat get_industries() di bawah. Method ini TETAP DIPERTAHANKAN
        (bukan dihapus) sbg referensi/diagnostic, cuma penamaan & statusnya
        yang berubah.
        """
        kwargs = {"fields": ["id", "name", "parent_id", "color"]}
        if limit:
            kwargs["limit"] = limit

        return self._execute("res.partner.category", "search_read", [[]], kwargs)

    def get_industries(self, limit: int | None = None):
        """
        GET mentah res.partner.industry (field standar Odoo "Industry",
        di-assign via res.partner.industry_id) -- ditambahkan 4 September
        2026 sbg kandidat SSOT BARU utk Customer Group eSuite, menggantikan
        hipotesis res.partner.category/"Customer Label" di atas (belum 100%
        dikonfirmasi user, lihat sales_entities_gap.md). Dibikin biar bisa
        dicek LANGSUNG lewat Swagger apakah data industry di Odoo CBU
        granularitasnya sama/lebih detail dari 4 grup CBU (FS/MT/GT/HORECA)
        -- kalau lebih detail (mis. "Restaurant", "Retail"), perlu mapping
        parent/child manual ke 4 grup itu.
        """
        kwargs = {"fields": ["id", "name"]}
        if limit:
            kwargs["limit"] = limit

        return self._execute("res.partner.industry", "search_read", [[]], kwargs)

    def get_pricelists(self, limit: int | None = None, ids: list | None = None, name: str | None = None):
        """
        GET mentah product.pricelist (header Pricelist) dari Odoo 19 -- dipakai
        GET /odoo/pricelist (17 Agustus 2026), LANGKAH AWAL riset entity
        Pricelist eSuite (POST /pricelists, belum pernah di-push -- lihat
        sales_entities_gap.md & business_flow_brainstorm.md: "Pricelist harus
        di-push karena nempel ke customer").

        BELUM DIVALIDASI ke instance Odoo CBU (assistant tidak punya akses
        network langsung ke Odoo dari sandbox ini) -- field dipilih dari model
        standar Odoo Sales (`product.pricelist`), BUKAN hasil cek live.
        SESSION_TRANSFER_NOTE.md (sesi lampau) sempat catat "Pricelist --
        blocker RPC Odoo masih ada" tanpa detail lebih lanjut -- kalau field di
        bawah bikin error RPC (field tidak ada / model tidak accessible dari
        API key ini), kabari pesan errornya biar disesuaikan.

        Sengaja TIDAK expand item_ids di sini (cuma list id) -- detail baris
        harga per pricelist diambil terpisah lewat get_pricelist_items().
        """
        conditions = []
        if ids:
            conditions.append(("id", "in", ids))
        if name:
            conditions.append(("name", "ilike", name))
        domain = [conditions] if conditions else [[]]

        kwargs = {
            "fields": ["id", "name", "currency_id", "company_id", "active", "item_ids"],
        }
        if limit:
            kwargs["limit"] = limit

        return self._execute("product.pricelist", "search_read", domain, kwargs)

    def get_pricelist_items(
        self,
        pricelist_id: int | None = None,
        pricelist_ids: list[int] | None = None,
        product_id: int | None = None,
        product_tmpl_id: int | None = None,
        limit: int | None = None,
    ):
        """
        GET mentah product.pricelist.item (baris aturan harga per produk/
        kategori dalam 1 Pricelist) -- dipakai GET /odoo/pricelist-item.
        Pelengkap get_pricelists(): header dulu (nama pricelist), baru
        drill-down ke item lewat pricelist_id (dari field item_ids di
        get_pricelists()) ATAU lewat product_id/product_tmpl_id (17-25
        Agustus 2026, lihat REVISI di bawah -- 1 produk bisa muncul di BANYAK
        pricelist sekaligus dengan fixed_price beda-beda per toko/customer/
        channel, jadi query per-produk juga relevan, bukan cuma per-pricelist).

        BELUM DIVALIDASI SEPENUHNYA -- field dipilih dari model standar Odoo
        (`product.pricelist.item`): applied_on menentukan scope baris (produk
        spesifik/varian/kategori/semua produk), compute_price menentukan cara
        hitung harga (fixed/percentage/formula), fixed_price dipakai kalau
        compute_price="fixed". Sama seperti get_pricelists(), kabari kalau
        ada error RPC field-not-found -- field yang salah tinggal diganti
        di sini.

        REVISI 18 Agustus 2026 -- parameter `pricelist_ids` (list, JAMAK)
        DITAMBAHKAN, dipakai pricelist_sync_service.py buat ambil SEMUA item
        lintas BANYAK pricelist sekaligus (1 RPC call, domain "pricelist_id
        in [...]") -- bukan 1 RPC call terpisah per pricelist (~100+
        pricelist = ~100+ round-trip kalau dipanggil satu-satu, mahal).
        `pricelist_id` (tunggal, existing, dipakai GET /odoo/pricelist-item
        drill-down 1 pricelist) TETAP DIPERTAHANKAN APA ADANYA -- tidak ada
        breaking change ke behavior lama. Kalau KEDUANYA diisi, `pricelist_ids`
        yang menang (lebih spesifik/bulk).

        REVISI 25 Agustus 2026 -- parameter `product_tmpl_id` DITAMBAHKAN.
        `product_id` (filter ke field `product_id` product.pricelist.item)
        yang lama TERBUKTI hampir selalu KOSONG hasilnya untuk data CBU --
        root cause SUDAH DIKONFIRMASI 18 Agustus (lihat FIX #1 di
        pricelist_sync_service.py & get_product_ids_by_template_ids()): SEMUA
        item Odoo CBU pakai applied_on="1_product", yaitu field
        `product_tmpl_id` yang TERISI, `product_id` KOSONG/false. Jadi filter
        `product_id` lama HAMPIR TIDAK PERNAH match apa pun di data nyata --
        `product_tmpl_id` inilah yang seharusnya dipakai buat cari "pricelist
        mana saja yang memuat produk X" (dipakai user buat push manual
        pricelist utk 1 produk tertentu, lihat GET /odoo/product yang sekarang
        ikut tampilkan `product_tmpl_id`, [[pricelist_progress]]). `product_id`
        TIDAK dihapus (masih diterima apa adanya, cuma jarang berguna sendiri)
        -- kalau keduanya diisi, dikombinasikan AND (jarang perlu keduanya).
        """
        conditions = []
        if pricelist_ids:
            conditions.append(("pricelist_id", "in", pricelist_ids))
        elif pricelist_id:
            conditions.append(("pricelist_id", "=", pricelist_id))
        if product_id:
            conditions.append(("product_id", "=", product_id))
        if product_tmpl_id:
            conditions.append(("product_tmpl_id", "=", product_tmpl_id))
        domain = [conditions] if conditions else [[]]

        kwargs = {
            "fields": [
                "id", "pricelist_id", "applied_on", "product_tmpl_id", "product_id",
                "categ_id", "compute_price", "fixed_price", "percent_price",
                "price_discount", "price_surcharge", "min_quantity",
                "date_start", "date_end",
            ],
        }
        if limit:
            kwargs["limit"] = limit

        return self._execute("product.pricelist.item", "search_read", domain, kwargs)

    def get_product_ids_by_template_ids(self, template_ids: list[int]):
        """
        Resolve product.template id -> product.product id(s) -- dipakai
        pricelist_sync_service.py (FIX 18 Agustus 2026, live test end-to-end
        pertama: SEMUA product.pricelist.item Odoo CBU ternyata pakai
        applied_on="1_product" -- product_tmpl_id TERISI, product_id KOSONG/
        false. Bukti live: GET /odoo/pricelist-item?pricelist_id=2293 ->
        {"product_id": false, "product_tmpl_id": [17854, "..."], ...}.
        Asumsi awal (filter cuma ke product_id) SALAH -- itu penyebab
        POST /sync/pricelist balikin 0 hasil di 316/316 pricelist (semua
        item ke-skip di tahap grouping, sebelum sempat cek eSuite).

        Karena bisnis CBU dikonfirmasi 1 template = 1 product.product (tidak
        ada variant fisik terpisah -- tiap ukuran/kemasan = product.product
        id sendiri, lihat get_products() & CONFIG_NOTES.md), SEHARUSNYA 1
        template cuma balik 1 product.product id -- tapi method ini TETAP
        mengembalikan LIST (bukan single id) supaya caller bisa deteksi
        anomali (template dengan >1 product.product, atau 0 kalau produknya
        sudah di luar domain/di-archive) tanpa exception tersembunyi.

        TIDAK difilter Saleable/list_price di sini (beda dari get_products())
        -- pricelist bisa saja punya rule utk produk yang sudah tidak
        Saleable, caller (pricelist_sync_service.py) yang putuskan treat-nya.

        Return: {template_id: [product_product_id, ...]}
        """
        if not template_ids:
            return {}

        records = self._execute(
            "product.product",
            "search_read",
            [[("product_tmpl_id", "in", template_ids)]],
            {"fields": ["id", "product_tmpl_id"]},
        )

        result = {}
        for r in records:
            tmpl_id = r["product_tmpl_id"][0]
            result.setdefault(tmpl_id, []).append(r["id"])
        return result

    @staticmethod
    def _name_in_domain(names: list, op: str = "ilike"):
        """
        Bangun domain OR: name <op> names[0] OR name <op> names[1] OR ...
        op default "ilike" (substring, case-insensitive -- dipakai
        get_companies(), behavior TIDAK BERUBAH). op="=ilike" (exact,
        case-insensitive) ditambahkan 31 Agustus 2026 untuk get_customers()
        fitur cari-by-nama -- lihat customer_sync_service.py.
        """
        if len(names) == 1:
            return [("name", op, names[0])]
        # Odoo domain OR pakai prefix '|' sebanyak (n-1) sebelum daftar kondisinya
        return ["|"] * (len(names) - 1) + [("name", op, n) for n in names]

    def get_partner_address(self, partner_id: int):
        """Detail alamat pemilik warehouse (res.partner), dipakai untuk isi field address Branch."""
        records = self._execute(
            "res.partner",
            "read",
            [[partner_id]],
            {
                "fields": [
                    "street",
                    "zip",
                    "partner_latitude",
                    "partner_longitude",
                ]
            },
        )
        return records[0] if records else None

    def get_sales_teams(self, ids: list | None = None):
        """
        Sumber data untuk entity Salesman Division di eSuite.
        Model: crm.team (Sales Team) -- DIKONFIRMASI 18 Agustus 2026 lewat
        cek langsung UI Odoo: representasi WILAYAH/TERRITORY (mis. "BALI FS
        AREA 1", "JKT MT"), BUKAN representasi 1 karyawan (anggota tiap
        team cuma kode slot/rute, lihat sales_entities_gap.md). Ambil SEMUA
        team active=True apa adanya, termasuk yang non-territory
        ("Sales"/"OFFICE"/"ONLINE") -- tidak ada exclude, dikonfirmasi user.
        TIDAK difilter company_id -- Sales Team Odoo CBU kelihatan
        "Visible to all" (tidak selalu terikat 1 company tertentu), beda
        dari Branch/Warehouse yang memang representasi company itu sendiri.

        ids (OPSIONAL, 21 Agustus 2026): filter tambahan "id in ids"
        (crm.team id) -- dipakai buat upsert division tertentu saja lewat
        external_code. Kosongkan untuk behavior normal.
        """
        conditions = [("active", "=", True)]
        if ids:
            conditions.append(("id", "in", ids))
        domain = [conditions]

        return self._execute(
            "crm.team",
            "search_read",
            domain,
            {"fields": ["id", "name"]},
        )
