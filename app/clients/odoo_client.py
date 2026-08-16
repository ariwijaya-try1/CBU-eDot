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

    def get_companies(self, names: list):
        """
        Sumber data untuk entity Branch di eSuite.
        Match pakai ilike per nama (bukan exact 'in') supaya nggak gampang
        meleset gara-gara format string (koma, spasi, dst).
        """
        domain = [self._name_in_domain(names)]

        return self._execute(
            "res.company",
            "search_read",
            domain,
            {"fields": ["id", "name", "partner_id"]},
        )

    def get_warehouses(self, company_ids: list):
        """
        Sumber data untuk entity Warehouse di eSuite.
        WAJIB difilter company_ids -- tanpa ini kebawa semua warehouse dari
        4 badan usaha, padahal cuma 2 yang in-scope.
        """
        domain = [[("company_id", "in", company_ids), ("active", "=", True)]]

        return self._execute(
            "stock.warehouse",
            "search_read",
            domain,
            {"fields": ["id", "name", "code", "company_id"]},
        )

    def get_product_categories(self):
        """
        Sumber data untuk entity Product Category di eSuite.
        Difilter cuma kategori di bawah "Saleable" -- sesuai aturan bisnis:
        produk yang boleh dijual/disync itu produk dengan category SALEABLE.
        Tidak difilter active -- model ini tidak punya field 'active' di Odoo 19.
        """
        domain = [[("complete_name", "ilike", "saleable")]]

        return self._execute(
            "product.category",
            "search_read",
            domain,
            {"fields": ["id", "name", "complete_name"]},
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

        return self._execute(
            "product.product",
            "search_read",
            domain,
            {"fields": ["id", "name", "free_qty", "categ_id", "list_price", "standard_price", "uom_id"]},
        )

    def get_stock_by_warehouse(self, warehouse_id: int, product_ids: list | None = None):
        """
        Sumber data stok PER WAREHOUSE untuk entity Stock Matrix di eSuite,
        dipakai stock_sync_service.py (lihat stock_sync_progress.md).

        BEDA dari get_products(): field 'qty_available'/'free_qty' di
        product.product itu GLOBAL (semua lokasi digabung) KECUALI dikasih
        context 'warehouse' -- Odoo native support ini lewat compute
        context, jadi TIDAK perlu baca stock.quant manual/group-by sendiri.

        UPDATE 15 Agustus 2026 (skema resmi vendor + keputusan bisnis baru,
        lihat stock_sync_progress.md): field eSuite "on_hand" (dikirim ke
        /stock-matrix -- TIDAK ADA field "free_to_use" sebagai input, itu
        computed otomatis di GET) diisi dari 'qty_available' (stok fisik/
        on-hand asli) -- BUKAN 'free_qty' seperti draft awal. 'free_qty'
        tetap diambil di sini (siapa tahu dibutuhkan lagi nanti), tapi
        TIDAK dipakai stock_sync_service.py.

        Domain Saleable sengaja SAMA dengan get_products() -- cuma produk
        yang disync ke eSuite yang perlu stok-nya disync juga.

        CATATAN/BELUM TUNTAS (14 Agustus 2026, dari info admin inventory):
        Odoo 19 CBU pakai ICT (Inter-Company Transfer) -- stok bisa
        berpindah ANTAR company. Versi pertama ini TETAP pakai warehouse_id
        sebagai kunci utama (bukan company_id), asumsi 1 warehouse = 1
        company pemilik fisik barang saat ini -- BELUM divalidasi penuh
        terhadap skenario ICT (stok transit/in-transit antar company).
        Kalau nanti hasil stock-matrix kelihatan tidak sesuai (stok ICT
        ke-double count atau hilang), ini kandidat pertama buat dicek.
        Keputusan (user, 14 Agustus 2026): jalan per-warehouse dulu sambil
        lihat perkembangan, bukan didesain ulang sekarang tanpa bukti masalah.

        product_ids (OPSIONAL): filter tambahan "id in product_ids", pola
        sama dengan get_products() -- kosongkan untuk semua produk Saleable.
        """
        conditions = [("categ_id.complete_name", "ilike", "ALL / SALEABLE")]
        if product_ids:
            conditions.append(("id", "in", product_ids))
        domain = [conditions]

        return self._execute(
            "product.product",
            "search_read",
            domain,
            {
                "fields": ["id", "qty_available", "free_qty"],
                "context": {"warehouse": warehouse_id},
            },
        )

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

    def get_customers(self, ids: list | None = None):
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
        """
        conditions = [("customer_rank", ">", 0), ("active", "=", True)]
        if ids:
            conditions.append(("id", "in", ids))
        domain = [conditions]

        return self._execute(
            "res.partner",
            "search_read",
            domain,
            {"fields": ["id", "name", "company_type"]},
        )

    @staticmethod
    def _name_in_domain(names: list):
        """Bangun domain OR: name ilike names[0] OR name ilike names[1] OR ..."""
        if len(names) == 1:
            return [("name", "ilike", names[0])]
        # Odoo domain OR pakai prefix '|' sebanyak (n-1) sebelum daftar kondisinya
        return ["|"] * (len(names) - 1) + [("name", "ilike", n) for n in names]

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
