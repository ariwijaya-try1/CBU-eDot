from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import AppError, ValidationError
from app.core.sync_logger import log_sync_result

# Currency -- sama persis dengan CURRENCY di service lain (IDR, satu-satunya
# currency di seluruh bisnis). Didefinisikan ulang di sini (bukan import
# silang antar service), konsisten dengan pola tiap sync service independen
# di project ini.
CURRENCY = {"id": "6a695cc1917e8fc836359505"}  # IDR, dari GET /currency

# Prefix external_code Pricelist -- BARU (18 Agustus 2026), belum pernah
# dipakai entity apapun sebelumnya. Sumber = product.pricelist.id Odoo.
EXTERNAL_CODE_PREFIX = "ODOO-PRICELIST-"

# Prefix external_code Product -- HARUS sama persis dengan
# product_sync_service.py::EXTERNAL_CODE_PREFIX ("ODOO-PROD-{id}").
PRODUCT_EXTERNAL_CODE_PREFIX = "ODOO-PROD-"

# Prefix external_code Branch (res.company) -- HARUS sama persis dengan
# branch_sync_service.py ("ODOO-COMPANY-{id}").
COMPANY_EXTERNAL_CODE_PREFIX = "ODOO-COMPANY-"

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

    KEPUTUSAN DESAIN (lihat pricelist_progress.md utk analisa lengkap):
    - `customer_group[]` SENGAJA TIDAK dikirim di v1 ini. Kesimpulan riset
      17 Agustus: assignment harga per-toko yang SEBENARNYA jalan lewat
      field `price_list.id` di entity Customer (pekerjaan terpisah, belum
      dibangun -- lihat sales_entities_gap.md), BUKAN lewat customer_group[]
      yang sifatnya grouping generik. Kalau nanti user tetap mau kirim
      customer_group[] sebagai fallback broad scope, tinggal tambah field
      ini (additive) -- external_code yang sudah ada:
      CBU-CUSTGROUP-FS/MT/GT/HORECA (lihat customer_group_sync_service.py).
    - `product[].key` (ULID di contoh PDF) SENGAJA DIKOSONGKAN/tidak dikirim
      -- tidak ada di daftar "Required fields" resmi (cuma external_code &
      name yang wajib), dan tidak ada sumber data Odoo yang jelas untuk ini.
    - `effective_date` SENGAJA TIDAK dikirim -- tiap item punya date_start/
      date_end sendiri-sendiri (bukan 1 range per pricelist), jadi tidak ada
      1 angka header yang akurat mewakili semua item. Field ini juga tidak
      ada di "Required fields" resmi.
    - Hanya item dengan `compute_price="fixed"` yang didukung (lihat
      _compute_item_price()) -- match 100% dengan contoh nyata user
      (screenshot tab "Prices", semua baris "Fixed Price"). Item lain
      (percentage/formula) di-skip & dihitung di response, TIDAK menggagalkan
      pricelist lain.
    - `base_price` di tiap variant SENGAJA dikirim 0 (konsisten dgn PDF
      contoh & instruksi lama soal cost/harga beli tidak boleh dikirim) --
      `store_price` yang berisi harga jual sebenarnya (dari fixed_price).
      BELUM dikonfirmasi vendor apakah base_price=0 ini benar secara
      tampilan UI eSuite -- test dengan 1-2 pricelist dulu (param `ids`)
      sebelum full push, sama seperti precedent Stock Matrix/Customer Group.

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
        limit: int | None = None,
        batch_size: int | None = None,
        include_payload: bool = False,
    ):
        odoo_ids = self._parse_ids(ids) if ids else None
        pricelists = self.odoo.get_pricelists(ids=odoo_ids)

        if not pricelists:
            raise ValidationError(
                "Tidak ada product.pricelist ditemukan di Odoo (cek juga parameter 'ids' kalau diisi)"
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

        items_by_pricelist, skipped_no_product, skipped_unsupported_compute = (
            self._group_items(items)
        )

        # Resolve id eSuite produk -- 1x FULL PULL GET /product (pola sama
        # stock_sync_service.py::_pull_all_verified_variant_ids(), lihat
        # alasan lengkap di _pull_esuite_product_map()).
        needed_product_ids = {
            row["product_id"] for rows in items_by_pricelist.values() for row in rows
        }
        esuite_products = self._pull_esuite_product_map(needed_product_ids)

        # Resolve id eSuite branch per company -- himpunan KECIL (cuma
        # sejumlah company unik yang muncul di pricelist terpilih), pakai
        # find_by_external_codes() early-exit (pola sama branch/customer).
        company_ids = {pl["company_id"][0] for pl in pricelists if pl.get("company_id")}
        esuite_branches = self._resolve_branches(company_ids)

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
                store_price = row["price"]
                product_entries.append(
                    {
                        "id": resolved["product_id"],
                        "variant": [
                            {
                                "id": resolved["variant_id"],
                                "base_price": 0,
                                "store_price": store_price,
                            }
                        ],
                        "min_base_price": 0,
                        "max_base_price": 0,
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
                esuite_branch_id = esuite_branches.get(company_code)
                if esuite_branch_id:
                    branch_entries = [{"id": esuite_branch_id}]
                else:
                    branch_unresolved.append(f"{EXTERNAL_CODE_PREFIX}{pl['id']}")

            payload.append(self._to_esuite_payload(pl, product_entries, branch_entries))

        if not payload:
            raise ValidationError(
                "Tidak ada pricelist dengan produk yang sudah punya product-variant valid di eSuite -- "
                "push Product dulu (POST /sync/product dengan with_variant=True), atau sync stock-matrix "
                "supaya lebih banyak produk ter-verifikasi",
                details={
                    "total_pricelist_diproses": len(pricelists),
                    "skipped_pricelist_no_valid_product_count": len(skipped_pricelist_no_valid_product),
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
            "skipped_item_no_product_id": skipped_no_product,
            "skipped_item_unsupported_compute_price": skipped_unsupported_compute,
            "branch_unresolved": branch_unresolved,
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
        yang punya product_id (applied_on = produk spesifik -- konsisten
        dengan model bisnis terkonfirmasi "harga per produk per toko", lihat
        docstring kelas) DAN compute_price="fixed" (lihat _compute_item_price()).

        Return: (items_by_pricelist, skipped_no_product, skipped_unsupported_compute)
        - items_by_pricelist: {pricelist_id: [{"product_id": int, "price": float}, ...]}
        - skipped_no_product: jumlah baris di-skip krn tidak ada product_id
          (applied_on kategori/semua produk -- di luar scope v1 ini)
        - skipped_unsupported_compute: jumlah baris di-skip krn compute_price
          bukan "fixed" (percentage/formula, belum didukung)
        """
        items_by_pricelist: dict = {}
        skipped_no_product = 0
        skipped_unsupported_compute = 0

        for item in items:
            pl_ref = item.get("pricelist_id")
            product_ref = item.get("product_id")
            if not pl_ref or not product_ref:
                skipped_no_product += 1
                continue

            price = self._compute_item_price(item)
            if price is None:
                skipped_unsupported_compute += 1
                continue

            items_by_pricelist.setdefault(pl_ref[0], []).append(
                {"product_id": product_ref[0], "price": price}
            )

        return items_by_pricelist, skipped_no_product, skipped_unsupported_compute

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
                        result[odoo_id] = {
                            "product_id": record["id"],
                            "variant_id": variant["id"],
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
        sejumlah company unik yang muncul di pricelist terpilih, biasanya
        <=3), pakai find_by_external_codes() early-exit (BEDA dari resolve
        produk di atas yang sengaja full-pull -- di sini himpunannya memang
        kecil & besar kemungkinan ketemu semua, jadi early-exit worth it).

        CATATAN: sama seperti produk, field "id" top-level dokumen /branches
        BELUM PERNAH dipakai/divalidasi di kode manapun sebelumnya (Branch
        selama ini cuma di-push, tidak pernah di-resolve balik oleh service
        lain). Kalau company (mis. "Sunshine Agri Pratama") tidak ketemu di
        eSuite sama sekali (belum pernah dipush krn di luar
        IN_SCOPE_COMPANY_NAMES, lihat docstring kelas), code-nya otomatis
        tidak ada di dict hasil -- caller (sync()) treat sebagai
        branch_unresolved, BUKAN error fatal.

        Return: {external_code: esuite_branch_id}
        """
        if not company_ids:
            return {}
        codes = {f"{COMPANY_EXTERNAL_CODE_PREFIX}{cid}" for cid in company_ids}
        resolved = self.esuite.find_by_external_codes("branches", codes)
        return {code: record["id"] for code, record in resolved.items() if record.get("id")}

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
    def _to_esuite_payload(pricelist: dict, product_entries: list, branch_entries: list) -> dict:
        return {
            "external_code": f"{EXTERNAL_CODE_PREFIX}{pricelist['id']}",
            "name": pricelist["name"],
            "status": "active" if pricelist.get("active", True) else "inactive",
            "currency": CURRENCY,
            "product": product_entries,
            "branch": branch_entries,
            # customer_group -- SENGAJA tidak dikirim, lihat docstring kelas.
        }
