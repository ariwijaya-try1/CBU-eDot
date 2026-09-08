from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import AppError, ValidationError
from app.core.sync_logger import log_sync_result

# Currency -- sama persis dengan CURRENCY di service lain (IDR, satu-satunya
# currency di seluruh bisnis). Didefinisikan ulang di sini (bukan import
# silang antar service), konsisten dengan pola tiap sync service independen
# di project ini.
CURRENCY = {"id": "6a97ad0fba3a62f899d29060"}  # IDR PROD -- direvisi 4 September 2026
# (id lama "6a695cc1917e8fc836359505" itu id DEV/sandbox, TERBUKTI SALAH di PROD,
# lihat esuite_prod_cutover.md). BELUM ditest live pasca fix ini.

# Prefix external_code Pricelist -- BARU (18 Agustus 2026), belum pernah
# dipakai entity apapun sebelumnya. Sumber = product.pricelist.id Odoo.
EXTERNAL_CODE_PREFIX = "ODOO-PRICELIST-"

# Prefix external_code Product -- HARUS sama persis dengan
# product_sync_service.py::EXTERNAL_CODE_PREFIX ("ODOO-PROD-{id}").
PRODUCT_EXTERNAL_CODE_PREFIX = "ODOO-PROD-"

# Prefix external_code Branch (res.company) -- HARUS sama persis dengan
# branch_sync_service.py ("ODOO-COMPANY-{id}").
COMPANY_EXTERNAL_CODE_PREFIX = "ODOO-COMPANY-"

# Customer Group "All Customer Group" (external_code "All") -- FIX 26 Agustus
# 2026, lihat docstring kelas. Constant FIXED (pola sama CURRENCY di atas),
# BUKAN di-resolve per pricelist -- Odoo tidak punya sumber data customer
# group per pricelist (assignment harga per-toko yang sebenarnya tetap lewat
# price_list.id di Customer, lihat sales_entities_gap.md), jadi SEMUA
# pricelist kirim grup catch-all yang sama ini (dari sample sukses vendor).
CUSTOMER_GROUP_ALL = {
    "id": "6a890e1ad5d77369eccac407",
    "name": "All Customer Group",
    "external_code": "All",
}

# effective_date -- FIX 26 Agustus 2026, lihat docstring kelas. FIXED
# (start_date/end_date = 0, artinya "tidak ada batas tanggal", sama seperti
# contoh sukses vendor & sama seperti record dibuat manual via UI eSuite
# yang dicek 26 Agustus/pricelist_progress.md) -- item Odoo tetap punya
# date_start/date_end sendiri per baris, field header ini cuma placeholder
# struktur yang WAJIB ADA (bukan berarti ada 1 tanggal berlaku per pricelist).
EFFECTIVE_DATE_DEFAULT = {"timezone": "Asia/Jakarta", "start_date": 0, "end_date": 0}

# sales_channel -- FIX 26 Agustus 2026, DIINSTRUKSIKAN LANGSUNG user (BUKAN
# dari sample dev yang isinya placeholder id/name kosong "" -- itu sengaja
# TIDAK dipakai). id/name ini = channel "esuite" itu sendiri, dari master
# data eSuite (GET /sales-channel, belum ada endpoint diagnostic-nya di
# bridge ini). FIXED constant sama seperti CUSTOMER_GROUP_ALL/CURRENCY --
# Odoo tidak punya sumber data sales_channel per pricelist.
SALES_CHANNEL_DEFAULT = [{"id": "6a695cc1917e8fc836359461", "name": "esuite"}]

# Default batch_size KALAU tidak diisi -- None (1 batch = semua pricelist
# sekaligus), pola sama product_sync_service.py/stock_sync_service.py.
DEFAULT_BATCH_SIZE = None


class PricelistSyncService:
    """
    Sync Pricelist: Odoo (product.pricelist + product.pricelist.item) ->
    eSuite (/pricelists). Dibuat 18 Agustus 2026 setelah scope dikonfirmasi
    user (lihat Cowork project memory pricelist_progress.md untuk riwayat
    lengkap GET-inspeksi & konfirmasi bisnis 17 Agustus):

    - SEMUA pricelist Odoo disync (bukan subset) -- "Semua pricelist"
      dikonfirmasi user 18 Agustus 2026.
    - SEMUA company ikut, TERMASUK "Sunshine Agri Pratama" (di luar
      IN_SCOPE_COMPANY_NAMES) dan pricelist tanpa company (company_id=False)
      -- "Ikut semua, termasuk keduanya" dikonfirmasi user 18 Agustus 2026.
      Makanya service ini SENGAJA TIDAK filter company_id sama sekali (beda
      dari branch/warehouse/stock yang selalu filter IN_SCOPE_COMPANY_NAMES).

    FIX 18 Agustus 2026 (setelah live test pertama balikin 0/316 pricelist):
    item Odoo CBU ternyata SELALU pakai applied_on="1_product" (product_tmpl_id
    terisi, product_id KOSONG/false) -- bukan applied_on="0_product_variant"
    seperti asumsi awal. Sekarang resolve product_tmpl_id -> product.product
    id dulu (lihat _resolve_products() & OdooClient.get_product_ids_by_template_ids())
    sebelum lanjut ke resolve eSuite. Confirmed live: GET /odoo/pricelist-item
    ?pricelist_id=2293 -> {"product_id": false, "product_tmpl_id": [17854, ...],
    "compute_price": "fixed", "fixed_price": 9009}.

    🆕🆕 FIX 26 Agustus 2026 -- root cause dugaan kuat kenapa push via webhook
    sering gagal/tidak kelihatan hasilnya (user report: "sync pricelist often
    failed, webhook eSuite juga failed, cuma UI yang berhasil"). Dev vendor
    kirim 1 sample payload TERKONFIRMASI SUKSES lewat Postman webhook
    (`external_code: "WH-PL-POSTMAN-01"`) -- dibandingkan dgn payload kita,
    ada beberapa perbedaan struktur:
    1. **Key nested produk itu `"products"` (JAMAK), BUKAN `"product"`**
       (tunggal) seperti yang selama ini kita kirim & seperti yang tertulis
       di skema PDF section 9.13 (skema PDF ini SEKARANG terbukti stale/salah,
       konsisten dgn precedent lain di project ini -- lihat
       feedback_source_of_truth_hierarchy.md: live/dev-confirmed sample >
       PDF statis). **Ini KEMUNGKINAN BESAR penyebab utama** kegagalan:
       key yang salah nama kemungkinan diterima eSuite sebagai field asing
       (di-skip diam-diam) -- response tetap HTTP 200 "success" (record
       pricelist-nya sendiri tetap ke-create/update), TAPI products[]-nya
       kosong sama sekali di eSuite -- persis pola "200 OK tapi silent fail"
       yang sudah beberapa kali ditemukan di entity lain project ini.
    2. `products[]`/`variant[]` di sample sukses ikut isi `name`/`sku`/
       `external_code` (level produk) & `name` (level variant) -- SEBELUMNYA
       cuma `id`. `branch[]` ikut isi `name` -- SEBELUMNYA cuma `id`.
    3. `customer_group[]`/`effective_date`/`sales_channel[]` SEBELUMNYA
       sengaja tidak dikirim (lihat versi lama catatan ini di bawah) --
       **DIREVISI 26 Agustus 2026 atas instruksi eksplisit user**: semua
       field yang ada di sample/struktur ini WAJIB dikirim. `customer_group[]`
       & `effective_date` pakai FIXED constant (`CUSTOMER_GROUP_ALL`,
       `EFFECTIVE_DATE_DEFAULT` -- Odoo tidak punya sumber data buat
       differensiasi per pricelist, sama alasan seperti CURRENCY).
       `sales_channel[]` (`SALES_CHANNEL_DEFAULT`) NILAINYA BUKAN dari sample
       dev (yang isinya placeholder `id`/`name` kosong `""`) tapi dari
       instruksi eksplisit user (channel "esuite", id
       `6a695cc1917e8fc836359461`).
    4. **BELUM ditest live** -- perubahan ini urgent (user report kegagalan
       berulang) makanya langsung diterapkan, TAPI wajib divalidasi dgn 1-2
       pricelist dulu (param `ids`) + cek visual UI eSuite, sebelum full push
       ulang ke semua pricelist yang sudah pernah "berhasil" (200) versi lama
       -- kemungkinan perlu re-push ulang supaya products[]-nya benar-benar
       terisi (bukan cuma diam2 diabaikan seperti dugaan di atas).

    🆕 FIX 4 September 2026 -- fallback `CUSTOMER_GROUP_ALL` DIHAPUS, param
    `customer_group_external_code` SEKARANG WAJIB diisi. Endpoint
    `GET /api/debug/verify-reference-constants` (dibangun 4 September,
    lihat esuite_prod_cutover.md) menemukan id `CUSTOMER_GROUP_ALL`
    (`6a890e1ad5d77369eccac407`) TIDAK ADA di tenant PROD -- dikonfirmasi
    ulang via `GET /customergroup` PROD langsung, record "All Customer
    Group"/external_code "All" memang tidak pernah dibuat di PROD (25
    customer group PROD lain semua ada, ini yang tidak). Daripada terus
    fallback ke id yang basi/tidak ada (risiko silent-fail sama seperti
    currency kemarin), keputusan user: WAJIBKAN caller isi
    `customer_group_external_code` eksplisit tiap panggilan -- konsisten
    dgn arah SCOPE PHASE 1 (27 Agustus, customer_group spesifik per
    segmen, bukan grup catch-all generik). Constant `CUSTOMER_GROUP_ALL`
    di atas SENGAJA TIDAK dihapus dari kode (histori/referensi), TAPI
    TIDAK DIPAKAI lagi -- lihat `sync()` di bawah.

    KEPUTUSAN DESAIN LAMA (SEBAGIAN SUDAH DIREVISI, lihat FIX 26 Agustus di
    atas -- riwayat dipertahankan buat konteks, lihat pricelist_progress.md
    utk analisa lengkap):
    - ~~`customer_group[]` SENGAJA TIDAK dikirim di v1 ini~~ -- DIREVISI,
      sekarang SELALU dikirim (`CUSTOMER_GROUP_ALL`, lihat FIX 26 Agustus).
      Kesimpulan riset 17 Agustus (assignment harga per-toko yang SEBENARNYA
      tetap lewat field `price_list.id` di Customer, lihat sales_entities_gap.md)
      TETAP BERLAKU -- customer_group[] di sini cuma grup catch-all generik,
      BUKAN pengganti mapping price_list.id per customer.
    - `product[].key` (ULID di contoh PDF) SENGAJA DIKOSONGKAN/tidak dikirim
      -- tidak ada di daftar "Required fields" resmi (cuma external_code &
      name yang wajib), dan tidak ada sumber data Odoo yang jelas untuk ini.
      Field ini TIDAK muncul di sample sukses dev juga -- konsisten, tetap
      tidak dikirim.
    - ~~`effective_date` SENGAJA TIDAK dikirim~~ -- DIREVISI, sekarang SELALU
      dikirim (`EFFECTIVE_DATE_DEFAULT`, lihat FIX 26 Agustus). Alasan lama
      (tiap item Odoo punya date_start/date_end sendiri, tidak ada 1 range
      akurat per pricelist) TETAP BERLAKU -- makanya value yang dikirim FIXED
      "tidak ada batas tanggal" (start/end = 0), bukan hasil hitung dari item.
    - Hanya item dengan `compute_price="fixed"` yang didukung (lihat
      _compute_item_price()) -- match 100% dengan contoh nyata user
      (screenshot tab "Prices", semua baris "Fixed Price"). Item lain
      (percentage/formula) di-skip & dihitung di response, TIDAK menggagalkan
      pricelist lain.
    - 🆕 2 September 2026 (DIKONFIRMASI USER, merevisi catatan lama di
      bawah): `base_price` tiap variant SEKARANG diisi `list_price` produk
      (hasil reuse field `base_price` yang sudah benar di GET /product
      eSuite, lihat _pull_esuite_product_map()) -- user klarifikasi
      base_price itu HARGA DASAR produk, BUKAN cost/harga beli (yang tetap
      terpisah, tetap hardcode 0 di product_sync_service.py, tidak
      terpengaruh). `store_price` SEMPAT di-hardcode 0 utk FASE 1 (asumsi
      lama: field ini = harga provider ke CBU) -- 🆕 8 September 2026
      DIREVERT: dikonfirmasi user via admin Odoo bahwa `store_price` =
      field `fixed_price` model `product.pricelist.item`, yaitu harga jual
      per customer/pricelist yang SEMULA memang dikirim (sebelum fix 2
      September). Jadi diferensiasi harga per customer/toko SEKARANG
      tersalur lagi ke eSuite via `store_price`/`min_store_price`/
      `max_store_price` = fixed_price item Odoo. Detail lengkap di
      pricelist_progress.md.
      ~~Catatan lama (SEBELUM 2 September, base_price=0 utk semua, PENDING
      konfirmasi vendor) -- SUDAH DIGANTIKAN keputusan di atas.~~

    GUARD (pola sama stock_sync_service.py) -- produk yang belum punya
    product-variant valid ter-embed di eSuite (GET /product, "variants[].id")
    di-skip dari product[] pricelist manapun, TIDAK bikin sync gagal. Baru
    ~30 dari 1241 produk yang confirmed valid saat ditulis (lihat
    stock_sync_service.py) -- WAJAR kalau banyak pricelist awalnya keluar
    dengan product[] kosong/pricelist itu ikut ke-skip (lihat
    skipped_pricelist_no_valid_product di response), ini akan otomatis
    membaik seiring makin banyak produk yang punya variant di-push.

    CATATAN BARU (belum jadi keputusan, PERLU DIBAWA KE USER TERPISAH):
    pricelist dengan company "Sunshine Agri Pratama" TIDAK PUNYA Branch di
    eSuite (branch_sync_service.py cuma push 2 company dari
    IN_SCOPE_COMPANY_NAMES) -- pricelist company ini tetap ikut dipush
    (sesuai keputusan scope), tapi `branch[]`-nya otomatis KOSONG (lihat
    branch_unresolved di response) karena tidak ada Branch eSuite yang bisa
    di-link. Ini BUKAN bug, tapi gap yang perlu keputusan lanjutan: apakah
    Branch untuk company ini perlu dibangun juga, atau pricelist-nya memang
    dimaksudkan "global/tanpa branch tertentu".
    """

    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(
        self,
        event: str = "upsert",
        ids: str | None = None,
        external_codes: str | None = None,
        limit: int | None = None,
        batch_size: int | None = None,
        include_payload: bool = False,
        customer_group_external_code: str | None = None,
        with_customer_group: bool = True,
    ):
        # external_codes (21 Agustus 2026) -- ditambahkan buat konsisten
        # dengan entity lain (format "ODOO-PRICELIST-{id}"), TAPI param `ids`
        # lama TETAP ADA & tetap jadi cara utama (lihat alasan di _parse_ids:
        # dikonfirmasi user supaya bisa langsung pakai id dari GET
        # /odoo/pricelist tanpa format ulang). Kalau keduanya diisi,
        # external_codes yang dipakai (pola sama product_id vs external_codes
        # di /sync/product).
        if external_codes:
            odoo_ids = self._parse_external_codes(external_codes)
        elif ids:
            odoo_ids = self._parse_ids(ids)
        else:
            odoo_ids = None
        pricelists = self.odoo.get_pricelists(ids=odoo_ids)

        if not pricelists:
            raise ValidationError(
                "Tidak ada product.pricelist ditemukan di Odoo (cek juga parameter 'ids'/'external_codes' kalau diisi)"
            )

        total_matched = len(pricelists)

        # limit -- diagnostic aid, pola sama service lain: kirim cuma N
        # pricelist pertama. Default None -> semua pricelist (sesuai
        # keputusan scope "Semua pricelist").
        if limit is not None:
            pricelists = pricelists[:limit]

        # 1 RPC call ambil SEMUA item lintas pricelist yang mau diproses
        # (lihat REVISI 18 Agustus di odoo_client.py::get_pricelist_items()).
        pricelist_ids = [pl["id"] for pl in pricelists]
        items = self.odoo.get_pricelist_items(pricelist_ids=pricelist_ids)

        grouped_raw, skipped_no_product, skipped_unsupported_compute = self._group_items(items)

        # FIX 18 Agustus 2026 (live test pertama: 316/316 pricelist balik 0
        # hasil) -- item Odoo CBU ternyata SELALU pakai applied_on="1_product"
        # (product_tmpl_id terisi, product_id KOSONG/false), BUKAN
        # applied_on="0_product_variant" seperti asumsi awal. Resolve
        # product_tmpl_id -> product.product id DULU (1 RPC bulk call)
        # sebelum lanjut ke resolve eSuite -- lihat
        # OdooClient.get_product_ids_by_template_ids() & _resolve_products().
        items_by_pricelist, skipped_ambiguous_template, skipped_template_no_product = (
            self._resolve_products(grouped_raw)
        )

        # Resolve id eSuite produk -- 1x FULL PULL GET /product (pola sama
        # stock_sync_service.py::_pull_all_verified_variant_ids(), lihat
        # alasan lengkap di _pull_esuite_product_map()).
        needed_product_ids = {
            row["product_id"] for rows in items_by_pricelist.values() for row in rows
        }
        esuite_products = self._pull_esuite_product_map(needed_product_ids)

        # DIAGNOSTIC (18 Agustus 2026, ditambahkan setelah test pricelist_id=2293
        # balik "0 valid product" -- supaya ketahuan LANGSUNG dari response produk
        # mana yang belum punya variant valid di eSuite, tanpa perlu debug manual
        # bolak-balik GET /odoo/product vs GET /product). Sorted supaya output stabil.
        products_not_in_esuite = sorted(
            f"{PRODUCT_EXTERNAL_CODE_PREFIX}{pid}"
            for pid in needed_product_ids - esuite_products.keys()
        )

        # Resolve id eSuite branch per company -- himpunan KECIL (cuma
        # sejumlah company unik yang muncul di pricelist terpilih), pakai
        # find_by_external_codes() early-exit (pola sama branch/customer).
        company_ids = {pl["company_id"][0] for pl in pricelists if pl.get("company_id")}
        esuite_branches = self._resolve_branches(company_ids)

        # customer_group_entries (27 Agustus 2026, Phase 1 -- lihat pricelist_progress.md
        # section "KONFLIK SEBAGIAN DIPUTUSKAN 27 Agustus") -- SEBELUMNYA fixed
        # CUSTOMER_GROUP_ALL utk SEMUA pricelist (26 Agustus), ternyata itu root
        # cause bug "harga tertimpa" (banyak pricelist share customer_group sama
        # -> saling override di app). SEKARANG opsional: kalau
        # customer_group_external_code diisi (mapping MANUAL per panggilan, pola
        # sama customer_grouping_endpoint), resolve id+name via GET /customergroup
        # (customer group itu WAJIB sudah dibuat manual di eSuite UI dgn
        # external_code terisi & parent "Customer Type", lihat dev_wa_notes.md
        # Note #1). 🆕 4 September 2026: fallback CUSTOMER_GROUP_ALL DIHAPUS --
        # id-nya terbukti tidak ada di eSuite PROD (verify-reference-constants +
        # GET /customergroup langsung), jadi param ini SEKARANG WAJIB diisi,
        # lihat esuite_prod_cutover.md untuk detail lengkap.
        # 🆕 5 September 2026 -- with_customer_group=False (OPSIONAL, DEFAULT
        # True = behavior TIDAK BERUBAH utk semua panggilan existing/automation).
        # Alasan: instruksi user, mau test assign Price List LANGSUNG dari UI
        # Customer eSuite (field pilih Price List) tapi terhalang krn upsert
        # pricelist WAJIB bawa customer_group_external_code (4 September). FIX
        # 26 Agustus 2026 sebenarnya menggabung 3 perubahan sekaligus (key
        # "product"->"products" diduga KUAT jadi akar masalah asli -- lihat
        # docstring kelas), customer_group SENDIRI belum pernah diisolasi-test
        # terpisah, jadi belum ada bukti kuat dia beneran mandatory di eSuite.
        # Kalau False: customer_group_external_code DIABAIKAN (tidak
        # divalidasi/tidak wajib), dan key "customer_group" TIDAK dikirim SAMA
        # SEKALI ke payload (bukan dikirim kosong [], lihat _to_esuite_payload()).
        if not with_customer_group:
            customer_group_entries = None
        elif customer_group_external_code:
            found_groups = self.esuite.find_by_external_codes(
                "customergroup", {customer_group_external_code}
            )
            resolved_group = found_groups.get(customer_group_external_code)
            if not resolved_group:
                raise ValidationError(
                    "customer_group_external_code tidak ditemukan di eSuite -- "
                    "pastikan Customer Group ini sudah dibuat manual di UI eSuite "
                    "(parent 'Customer Type') dengan external_code yang sama persis",
                    details={"customer_group_external_code": customer_group_external_code},
                )
            customer_group_entries = [
                {
                    "id": resolved_group.get("id", ""),
                    "name": resolved_group.get("name") or "",
                    "external_code": customer_group_external_code,
                }
            ]
        else:
            # CUSTOMER_GROUP_ALL TIDAK dipakai lagi sbg fallback (4 September
            # 2026) -- id-nya tidak ada di eSuite PROD, lihat komentar di atas
            # & esuite_prod_cutover.md. Error eksplisit di sini supaya gagal
            # CEPAT & JELAS (bukan 200 sukses tapi customer_group-nya diam-diam
            # invalid, pola "silent fail" yang berkali-kali kejadian di project
            # ini).
            raise ValidationError(
                "customer_group_external_code wajib diisi -- fallback default "
                "'All Customer Group' sudah dihapus karena id lama tidak ditemukan "
                "di eSuite (lihat esuite_prod_cutover.md). Buat/pilih Customer Group "
                "spesifik di eSuite UI (parent 'Customer Type') lalu isi param ini "
                "dengan external_code-nya, ATAU set with_customer_group=false (BARU "
                "5 September 2026) utk skip customer_group sama sekali.",
            )

        payload = []
        skipped_pricelist_no_valid_product = []
        branch_unresolved = []

        for pl in pricelists:
            rows = items_by_pricelist.get(pl["id"], [])
            product_entries = []
            for row in rows:
                resolved = esuite_products.get(row["product_id"])
                if not resolved:
                    continue
                # 🆕 8 September 2026 (REVERT, dikonfirmasi user via admin
                # Odoo: store_price = field `fixed_price` model
                # product.pricelist.item) -- fixed_price Odoo DIKIRIM LAGI
                # sbg store_price, menggantikan hardcode 0 (2 September).
                # Lihat pricelist_progress.md utk detail keputusan.
                store_price = row["price"]
                # name/sku/external_code (26 Agustus 2026, FIX; direvisi lagi
                # 2 September 2026) -- lihat docstring kelas bagian "FIX 26
                # Agustus" utk alasan lengkap.
                # "name" (2 September 2026, FIX) -- format DIREVISI jadi
                # "{external_code} - {nama}" (mis. "ODOO-PROD-18374 -
                # KATSUOBUSHI 500g"), sesuai contoh payload dev eDot ("UI
                # format"). SEBELUMNYA cuma nama polos.
                # "sku" (2 September 2026, FIX) -- SEBELUMNYA selalu "" ("Odoo
                # tidak punya SKU terpisah"), TERNYATA salah asumsi & dev eDot
                # WAJIB isi sku produk (master SKU) di payload /pricelists.
                # Sekarang diisi dari sku yang SUDAH di-resolve di
                # _pull_esuite_product_map() (hasil push /sync/product yang
                # sudah pakai default_code Odoo, lihat FIX tanggal sama di
                # product_sync_service.py) -- fallback "" kalau produk itu
                # belum pernah di-re-push pasca fix atau genuinely tidak
                # punya default_code.
                #
                # "base_price"/"store_price" (2 September 2026, FIX,
                # DIKONFIRMASI USER; store_price DIREVERT 8 September 2026):
                # base_price = harga dasar (list_price) produk, reuse dari
                # `resolved["base_price"]` (_pull_esuite_product_map(), hasil
                # /sync/product yang sudah benar). store_price = fixed_price
                # item Odoo (`store_price` lokal di atas) -- dikonfirmasi
                # user via admin: field Odoo `product.pricelist.item.fixed_price`
                # itulah store_price, jadi harga jual per customer/pricelist
                # SUDAH tersalur lewat sini (bukan lagi hardcode 0). Lihat
                # docstring kelas & pricelist_progress.md utk detail lengkap.
                base_price = resolved.get("base_price") or 0
                product_entries.append(
                    {
                        "id": resolved["product_id"],
                        "name": f"{resolved['external_code']} - {resolved['name']}",
                        "sku": resolved.get("sku") or "",
                        "external_code": resolved["external_code"],
                        "variant": [
                            {
                                "id": resolved["variant_id"],
                                "name": resolved["name"],
                                "base_price": base_price,
                                "store_price": store_price,
                            }
                        ],
                        "min_base_price": base_price,
                        "max_base_price": base_price,
                        "min_store_price": store_price,
                        "max_store_price": store_price,
                    }
                )

            if not product_entries:
                skipped_pricelist_no_valid_product.append(f"{EXTERNAL_CODE_PREFIX}{pl['id']}")
                continue

            branch_entries = []
            if pl.get("company_id"):
                company_code = f"{COMPANY_EXTERNAL_CODE_PREFIX}{pl['company_id'][0]}"
                esuite_branch = esuite_branches.get(company_code)
                if esuite_branch:
                    # "name" (26 Agustus 2026, FIX) -- ikut dikirim, bukan
                    # cuma "id" -- lihat docstring kelas.
                    branch_entries = [{"id": esuite_branch["id"], "name": esuite_branch["name"]}]
                else:
                    branch_unresolved.append(f"{EXTERNAL_CODE_PREFIX}{pl['id']}")

            payload.append(self._to_esuite_payload(pl, product_entries, branch_entries, customer_group_entries))

        if not payload:
            raise ValidationError(
                "Tidak ada pricelist dengan produk yang sudah punya product-variant valid di eSuite -- "
                "push Product dulu (POST /sync/product dengan with_variant=True) untuk produk yang "
                "dilist di 'products_not_in_esuite_sample', atau sync stock-matrix supaya lebih banyak "
                "produk ter-verifikasi",
                details={
                    "total_pricelist_diproses": len(pricelists),
                    "skipped_pricelist_no_valid_product_count": len(skipped_pricelist_no_valid_product),
                    "products_needed_count": len(needed_product_ids),
                    "products_not_in_esuite_count": len(products_not_in_esuite),
                    "products_not_in_esuite_sample": products_not_in_esuite[:20],
                },
            )

        # Batching -- pola sama product_sync_service.py/stock_sync_service.py:
        # opsional, default None -> 1 batch semua pricelist sekaligus.
        size = batch_size or len(payload)
        batches = [payload[i : i + size] for i in range(0, len(payload), size)]

        batch_results = []
        synced_count = 0
        failed_count = 0

        for idx, batch in enumerate(batches, start=1):
            try:
                esuite_result = self.esuite.push("pricelists", event=event, data=batch)
                batch_entry = {
                    "batch": idx,
                    "size": len(batch),
                    "status": "success",
                    "external_codes": [item["external_code"] for item in batch],
                    "esuite_response": esuite_result,
                }
                if include_payload:
                    batch_entry["payload_sent"] = batch
                batch_results.append(batch_entry)
                synced_count += len(batch)
            except AppError as e:
                # Pola sama service lain -- di-catch per batch, batch lain tetap lanjut.
                batch_entry = {
                    "batch": idx,
                    "size": len(batch),
                    "status": "failed",
                    "external_codes": [item["external_code"] for item in batch],
                    "error": e.to_dict()["error"],
                }
                if include_payload:
                    batch_entry["payload_sent"] = batch
                batch_results.append(batch_entry)
                failed_count += len(batch)

        result = {
            "total_pricelist_in_odoo": total_matched,
            "total_pricelist_diproses": len(pricelists),
            "total_sent": len(payload),
            "skipped_pricelist_no_valid_product": skipped_pricelist_no_valid_product,
            "skipped_item_no_product_ref": skipped_no_product,
            "skipped_item_unsupported_compute_price": skipped_unsupported_compute,
            "skipped_item_ambiguous_template": skipped_ambiguous_template,
            "skipped_item_template_no_product": skipped_template_no_product,
            "products_not_in_esuite_count": len(products_not_in_esuite),
            "products_not_in_esuite_sample": products_not_in_esuite[:20],
            "branch_unresolved": branch_unresolved,
            "customer_group_used": customer_group_entries,
            "batch_size": size,
            "batch_count": len(batches),
            "synced_count": synced_count,
            "failed_count": failed_count,
            "batches": batch_results,
        }

        note_parts = []
        if skipped_pricelist_no_valid_product:
            note_parts.append(
                f"{len(skipped_pricelist_no_valid_product)} pricelist di-skip (belum ada produk valid di eSuite)"
            )
        if branch_unresolved:
            note_parts.append(f"{len(branch_unresolved)} pricelist push tanpa branch (company belum ada di eSuite)")
        log_sync_result("pricelist", event, result, note="; ".join(note_parts))
        return result

    def _group_items(self, items: list) -> tuple[dict, int, int]:
        """
        Kelompokkan product.pricelist.item per pricelist_id, HANYA baris
        yang punya product_id ATAU product_tmpl_id (applied_on = produk
        spesifik -- konsisten dengan model bisnis terkonfirmasi "harga per
        produk per toko", lihat docstring kelas; kategori/semua produk di
        luar scope v1 ini) DAN compute_price="fixed" (lihat
        _compute_item_price()).

        REVISI 18 Agustus 2026 (FIX bug live: 316/316 pricelist balik 0
        hasil) -- SEBELUMNYA cuma baca `product_id`, TERNYATA item Odoo CBU
        selalu pakai applied_on="1_product" (`product_tmpl_id` terisi,
        `product_id` KOSONG/false, dikonfirmasi live GET /odoo/pricelist-item
        pricelist_id=2293). Sekarang tangkap KEDUANYA -- resolve
        product_tmpl_id -> product.product id dilakukan TERPISAH di
        _resolve_products() (butuh 1 RPC bulk call, tidak dilakukan di sini
        supaya fungsi ini tetap murni baca Odoo, tidak query lagi di tengah loop).

        Return: (grouped_raw, skipped_no_product, skipped_unsupported_compute)
        - grouped_raw: {pricelist_id: [{"product_id": int|None, "product_tmpl_id": int|None, "price": float}, ...]}
          (salah satu dari product_id/product_tmpl_id pasti terisi, tidak
          pernah dua-duanya None -- sudah difilter di bawah)
        - skipped_no_product: jumlah baris di-skip krn tidak ada product_id
          MAUPUN product_tmpl_id (applied_on kategori/semua produk)
        - skipped_unsupported_compute: jumlah baris di-skip krn compute_price
          bukan "fixed" (percentage/formula, belum didukung)
        """
        grouped_raw: dict = {}
        skipped_no_product = 0
        skipped_unsupported_compute = 0

        for item in items:
            pl_ref = item.get("pricelist_id")
            product_ref = item.get("product_id")
            tmpl_ref = item.get("product_tmpl_id")
            if not pl_ref or (not product_ref and not tmpl_ref):
                skipped_no_product += 1
                continue

            price = self._compute_item_price(item)
            if price is None:
                skipped_unsupported_compute += 1
                continue

            grouped_raw.setdefault(pl_ref[0], []).append(
                {
                    "product_id": product_ref[0] if product_ref else None,
                    "product_tmpl_id": tmpl_ref[0] if tmpl_ref else None,
                    "price": price,
                }
            )

        return grouped_raw, skipped_no_product, skipped_unsupported_compute

    def _resolve_products(self, grouped_raw: dict) -> tuple[dict, int, int]:
        """
        Resolve baris yang masih pakai product_tmpl_id (applied_on=
        "1_product") jadi product.product id -- lihat
        OdooClient.get_product_ids_by_template_ids() untuk alasan lengkap.
        Baris yang sudah punya product_id langsung (applied_on=
        "0_product_variant", kalau ada) dilewati apa adanya, tidak perlu resolve.

        1 RPC bulk call TOTAL (bukan per pricelist/per item) -- kumpulin
        SEMUA template_id yang dibutuhkan dulu, baru query sekali.

        Return: (items_by_pricelist, skipped_ambiguous_template, skipped_template_no_product)
        - items_by_pricelist: {pricelist_id: [{"product_id": int, "price": float}, ...]}
          -- SEMUA baris di sini sudah pasti punya product_id valid.
        - skipped_ambiguous_template: baris di-skip krn 1 product_tmpl_id
          ternyata resolve ke LEBIH DARI 1 product.product id (anomali --
          bisnis CBU dikonfirmasi 1 template = 1 product.product, tapi
          dicek eksplisit di sini daripada asumsi buta & salah pilih salah
          satu produk secara diam-diam).
        - skipped_template_no_product: baris di-skip krn product_tmpl_id
          tidak resolve ke product.product manapun (mis. sudah di-archive).
        """
        template_ids_needed = {
            row["product_tmpl_id"]
            for rows in grouped_raw.values()
            for row in rows
            if row["product_tmpl_id"] and not row["product_id"]
        }
        template_map = self.odoo.get_product_ids_by_template_ids(list(template_ids_needed))

        items_by_pricelist: dict = {}
        skipped_ambiguous_template = 0
        skipped_template_no_product = 0

        for pl_id, rows in grouped_raw.items():
            resolved_rows = []
            for row in rows:
                pid = row["product_id"]
                if not pid:
                    candidates = template_map.get(row["product_tmpl_id"], [])
                    if len(candidates) == 1:
                        pid = candidates[0]
                    elif len(candidates) == 0:
                        skipped_template_no_product += 1
                        continue
                    else:
                        skipped_ambiguous_template += 1
                        continue
                resolved_rows.append({"product_id": pid, "price": row["price"]})

            if resolved_rows:
                items_by_pricelist[pl_id] = resolved_rows

        return items_by_pricelist, skipped_ambiguous_template, skipped_template_no_product

    @staticmethod
    def _compute_item_price(item: dict) -> float | None:
        """
        Hitung harga final 1 baris product.pricelist.item. SEKARANG cuma
        dukung compute_price="fixed" -- match 100% dengan contoh nyata user
        (screenshot tab "Prices" Odoo, semua baris "Fixed Price"). Tipe lain
        ("percentage" butuh price_list acuan, "formula" gabungan beberapa
        field) BELUM divalidasi -- return None (di-skip di _group_items,
        DIHITUNG bukan disembunyikan) daripada salah tebak formula & push
        harga yang keliru ke customer beneran (data harga = risiko tinggi).
        """
        if item.get("compute_price") != "fixed":
            return None
        return item.get("fixed_price")

    def _pull_esuite_product_map(self, needed_ids: set) -> dict:
        """
        Full-pull SEMUA halaman GET /product eSuite SEKALI -- pola SAMA
        PERSIS stock_sync_service.py::_pull_all_verified_variant_ids() (baca
        docstring di sana untuk alasan lengkap kenapa full-pull lebih hemat
        daripada find_by_external_codes() per kode kalau himpunan yang
        dicari besar sementara yang confirmed valid di eSuite masih sedikit
        -- early-exit find_by_external_codes() TIDAK PERNAH kena kalau
        banyak kode yang dicari memang belum ada, jadi combine ke situasi
        ini full-scan semua halaman lagipula, mending 1x pull depan lalu
        lookup O(1) di Python).

        CATATAN BARU (18 Agustus 2026): berbeda dari
        _resolve_existing_variant_ids() di product_sync_service.py (yang
        cuma butuh variants[].id), fungsi ini JUGA pakai "id" TOP-LEVEL dari
        dokumen /product (bukan cuma variants[].id) -- field ini BELUM
        PERNAH dipakai/divalidasi di kode manapun sebelumnya (beda dari
        variants[].id yang sudah terbukti reliable, vs id di collection
        /product-variant standalone yang terbukti SELALU kosong). Secara
        desain REST, "id" top-level 1 dokumen HARUSNYA jadi primary key
        dokumen itu sendiri (beda kasus dari bug lama), tapi karena belum
        pernah dicek langsung -- SARAN: test dulu 1 pricelist kecil (param
        `ids=<1 pricelist id>` di POST /sync/pricelist) sebelum full push,
        supaya kalau field ini ternyata juga tidak reliable, dampaknya
        kelihatan di 1 pricelist dulu, bukan semua ~100+ sekaligus.

        Return: {odoo_product_id: {"product_id": <id eSuite>, "variant_id": <id eSuite>}}
        -- cuma produk yang punya external_code cocok format "ODOO-PROD-{id}"
        DAN variant valid ter-embed (variants[].id terisi).
        """
        result: dict = {}
        if not needed_ids:
            return result

        page = 1
        limit = 200
        while True:
            pulled = self.esuite.pull("product", page=page, limit=limit)
            for record in pulled.get("data") or []:
                code = record.get("external_code") or ""
                if not code.startswith(PRODUCT_EXTERNAL_CODE_PREFIX):
                    continue
                id_part = code[len(PRODUCT_EXTERNAL_CODE_PREFIX):]
                if not id_part.isdigit():
                    continue
                odoo_id = int(id_part)
                if odoo_id not in needed_ids or not record.get("id"):
                    continue
                for variant in record.get("variants") or []:
                    if variant.get("external_code") == code and variant.get("id"):
                        # "name"/"external_code" (26 Agustus 2026) -- ikut
                        # disimpan dari record yang SAMA (tidak ada RPC/pull
                        # tambahan) supaya bisa diisi ke product[].name/sku/
                        # external_code di payload -- lihat FIX di sync()
                        # bagian bawah, alasan lengkap di docstring kelas.
                        # "sku" (2 September 2026, FIX) -- ikut disimpan dari
                        # variant eSuite yang SAMA (sku yang SUDAH di-set via
                        # /sync/product, lihat product_sync_service.py fix
                        # tanggal sama) -- dev eDot WAJIB isi sku produk di
                        # payload /pricelists, TIDAK BOLEH "" lagi.
                        result[odoo_id] = {
                            "product_id": record["id"],
                            "variant_id": variant["id"],
                            "name": record.get("name") or "",
                            "external_code": code,
                            "sku": variant.get("sku") or "",
                            # "base_price" (2 September 2026, FIX) -- reuse
                            # field top-level "base_price" dari record eSuite
                            # yang SAMA (sudah diisi list_price Odoo via
                            # /sync/product, lihat product_sync_service.py
                            # baris "base_price": product.get("list_price")
                            # or 0) -- TIDAK ada RPC/pull tambahan, dipakai
                            # isi products[].variant[].base_price di sync().
                            "base_price": record.get("base_price") or 0,
                        }
                        break

            meta = pulled.get("meta") or {}
            total_page = meta.get("total_page", 1)
            if page >= total_page:
                break
            page += 1

        return result

    def _resolve_branches(self, company_ids: set) -> dict:
        """
        Resolve id eSuite Branch per company_id Odoo -- himpunan kecil (cuma
        sejumlah company unik yang muncul di pricelist terpilih, biasanya <=3).

        FIX 18 Agustus 2026 (live test: pricelist company CBU, yang PASTI
        sudah punya Branch di eSuite, tetap selalu masuk branch_unresolved) --
        root cause dikonfirmasi via `GET /debug/pull/branches`: `external_code`
        Branch itu **NESTED** di `basic_info.external_code`, BUKAN top-level
        seperti Product/Customer/Product-Category. `find_by_external_codes()`
        generik (EsuiteClient, dipakai banyak entity lain) cuma cek
        `record.get("external_code")` di level atas -- utk Branch ini SELALU
        None, jadi resolve SELALU gagal walau datanya ada & benar. Ini bukan
        soal company belum ke-push (dugaan awal), murni salah lokasi baca
        field. TIDAK mengubah `find_by_external_codes()` generik-nya (itu
        sudah terbukti benar untuk entity lain yang external_code-nya
        top-level) -- di sini pakai pull loop manual yang baca posisi nested
        Branch secara spesifik.

        Himpunan Branch kecil (7 record total saat dicek live) -- full-pull
        semua halaman aman & simpel, tidak perlu logic early-exit.

        CATATAN: field "id" top-level dokumen /branches SUDAH dikonfirmasi
        reliable (terisi persis, tidak kosong) dari live check di atas.
        "name" (26 Agustus 2026, FIX) -- ikut disimpan dari record yang SAMA
        (top-level "name", sama field yang dikirim branch_sync_service.py
        line ~133) supaya branch[] di payload Pricelist bisa isi "name" juga,
        bukan cuma "id" -- lihat docstring kelas bagian "FIX 26 Agustus".

        Kalau company (mis. "Sunshine Agri Pratama") tidak ketemu di eSuite
        sama sekali (belum pernah dipush krn di luar IN_SCOPE_COMPANY_NAMES,
        lihat docstring kelas), code-nya otomatis tidak ada di dict hasil --
        caller (sync()) treat sebagai branch_unresolved, BUKAN error fatal.

        Return: {external_code: {"id": ..., "name": ...}}
        """
        if not company_ids:
            return {}
        codes_wanted = {f"{COMPANY_EXTERNAL_CODE_PREFIX}{cid}" for cid in company_ids}

        result: dict = {}
        page = 1
        limit = 200
        while True:
            pulled = self.esuite.pull("branches", page=page, limit=limit)
            for record in pulled.get("data") or []:
                code = (record.get("basic_info") or {}).get("external_code")
                if code in codes_wanted and record.get("id") and code not in result:
                    result[code] = {"id": record["id"], "name": record.get("name") or ""}

            meta = pulled.get("meta") or {}
            total_page = meta.get("total_page", 1)
            if page >= total_page or len(result) == len(codes_wanted):
                break
            page += 1

        return result

    @staticmethod
    def _parse_ids(ids: str) -> list:
        """
        Parse "3,5,12" -> [3, 5, 12] -- id Odoo product.pricelist MENTAH
        (bukan format "ODOO-PRICELIST-{id}" seperti _parse_external_codes()
        di service lain), konsisten dengan parameter `ids` yang sudah dipakai
        GET /odoo/pricelist (odoo_get.py) -- supaya user bisa langsung pakai
        id yang sama dari situ tanpa perlu format ulang.
        """
        try:
            return [int(i.strip()) for i in ids.split(",") if i.strip()]
        except ValueError:
            raise ValidationError(
                f"Parameter 'ids' harus angka semua (Odoo product.pricelist id), pisah koma -- dapat: '{ids}'",
                details={"ids": ids},
            )

    @staticmethod
    def _parse_external_codes(external_codes: str) -> list[int]:
        """
        Parse "ODOO-PRICELIST-3,ODOO-PRICELIST-5" -> [3, 5] -- pola sama
        dengan customer_sync_service.py/product_sync_service.py. Ditambahkan
        21 Agustus 2026 supaya konsisten dgn entity lain; param 'ids' lama
        (id Odoo mentah) tetap jadi cara utama, lihat komentar di sync().
        """
        ids = []
        for raw in external_codes.split(","):
            code = raw.strip()
            if not code:
                continue
            if not code.startswith(EXTERNAL_CODE_PREFIX):
                raise ValidationError(
                    f"external_code '{code}' tidak sesuai format '{EXTERNAL_CODE_PREFIX}{{id_odoo}}'",
                    details={"expected_prefix": EXTERNAL_CODE_PREFIX},
                )
            id_part = code[len(EXTERNAL_CODE_PREFIX):]
            if not id_part.isdigit():
                raise ValidationError(
                    f"external_code '{code}' -- bagian id bukan angka valid",
                    details={"external_code": code},
                )
            ids.append(int(id_part))
        return ids

    @staticmethod
    def _to_esuite_payload(
        pricelist: dict, product_entries: list, branch_entries: list, customer_group_entries: list
    ) -> dict:
        # FIX 26 Agustus 2026 -- lihat docstring kelas bagian "FIX 26 Agustus"
        # untuk root cause & alasan lengkap tiap perubahan di bawah:
        # 1. key "product" -> "products" (PALING KRITIS -- root cause dugaan
        #    kuat kenapa sync via webhook sering gagal/silent-empty walau
        #    response 200, sementara create manual via UI selalu berhasil).
        # 2. customer_group[]/effective_date/sales_channel[] SEKARANG ikut
        #    dikirim (SEBELUMNYA sengaja tidak dikirim, keputusan 18 Agustus)
        #    -- DIREVISI atas instruksi eksplisit user 26 Agustus 2026: semua
        #    field ini WAJIB dikirim, konsisten dgn sample sukses dari dev.
        payload = {
            "external_code": f"{EXTERNAL_CODE_PREFIX}{pricelist['id']}",
            "name": pricelist["name"],
            "status": "active" if pricelist.get("active", True) else "inactive",
            "currency": CURRENCY,
            "effective_date": EFFECTIVE_DATE_DEFAULT,
            "branch": branch_entries,
            "sales_channel": SALES_CHANNEL_DEFAULT,
            "products": product_entries,
        }
        # 🆕 5 September 2026 -- customer_group_entries None (with_customer_group=False
        # di sync()) -> key "customer_group" TIDAK ditulis sama sekali ke payload
        # (bukan dikirim kosong []), pola sama "sales" di customer_sync_service.py.
        if customer_group_entries is not None:
            payload["customer_group"] = customer_group_entries
        return payload
