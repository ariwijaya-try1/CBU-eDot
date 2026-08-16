from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import AppError, ValidationError
from app.core.sync_logger import log_sync_result
from app.core.scope import IN_SCOPE_COMPANY_NAMES

# Prefix external_code Product -- HARUS sama persis dengan
# product_sync_service.py::EXTERNAL_CODE_PREFIX ("ODOO-PROD-{id}"), karena
# stock-matrix identify product lewat "product_variant.code" = external_code
# variant, dan external_code variant SAMA PERSIS dengan external_code produk
# induknya (lihat product_sync_service.py). Didefinisikan ulang di sini
# (bukan import silang antar service) konsisten dengan pola tiap sync
# service independen yang sudah dipakai di project ini.
PRODUCT_EXTERNAL_CODE_PREFIX = "ODOO-PROD-"

# Prefix external_code Warehouse -- HARUS sama persis dengan
# warehouse_sync_service.py ("ODOO-WH-{id}").
WAREHOUSE_EXTERNAL_CODE_PREFIX = "ODOO-WH-"

# uom_level_code -- opsional menurut vendor (15 Agustus 2026), dikosongkan
# selalu untuk sekarang. Beda dari Product UOM Level (entity terpisah,
# dipakai di /product) -- field ini spesifik punya /stock-matrix, belum ada
# kebutuhan isi spesifik.
DEFAULT_UOM_LEVEL_CODE = ""

# Default batch_size KALAU batch_size tidak diisi -- None (1 batch = semua
# baris sekaligus), pola sama dengan product_sync_service.py. Diisi kalau
# nanti volume gede & perlu dipecah.
DEFAULT_BATCH_SIZE = None


class StockSyncService:
    """
    Sync Stock Matrix: Odoo (product.product, qty_available per warehouse)
    -> eSuite (/stock-matrix). Dibuat 15/16 Agustus 2026 setelah skema resmi
    & seluruh keputusan pending dikonfirmasi vendor + user -- lihat
    stock_sync_progress.md untuk riwayat lengkap Test 1/2 & 2 konflik yang
    sudah di-resolve.

    Keputusan final yang dipakai di service ini:
    - Identifier pakai "product_variant.code" (= external_code produk,
      "ODOO-PROD-{id}") & "warehouse.code" (= external_code warehouse,
      "ODOO-WH-{id}") -- BUKAN id eSuite. TIDAK ADA field external_code
      khusus stock-matrix (1 baris diidentifikasi otomatis oleh eSuite lewat
      composite key: company + product_variant + uom + warehouse + location
      + batch).
    - "on_hand" & "quantity" (nilai sama) diisi dari qty_available Odoo
      (stok fisik/on-hand asli) -- BUKAN free_qty. Keputusan bisnis baru,
      dikonfirmasi user 15 Agustus 2026 (sumber: tim inventory/Komang),
      membatalkan keputusan lama "kirim free-to-use saja".
    - TIDAK kirim uom.id / free_to_use / location -- bukan field input yang
      valid (vendor konfirmasi 15 Agustus 2026); free_to_use & location
      muncul otomatis di GET (computed/auto-derived dari warehouse).
    - Nilai bersifat absolute/set-to-target (bukan delta) & idempotent --
      dikonfirmasi resmi vendor, tidak perlu logic delta di sisi bridge.

    PENTING -- GUARD, eSuite-FIRST (16 Agustus 2026, revisi ke-2). Baru ~30
    dari 1241 produk yang confirmed punya product-variant ke-push ke eSuite
    (embed 1:1). Supaya stok yang di-push TIDAK PERNAH nyasar ke produk yang
    variant-nya belum ada, sync() ini SELALU cek eSuite DULU (bukan cek
    belakangan) buat nentuin id produk mana yang aman -- baru query stok
    Odoo SPESIFIK ke id-id itu:

      1. eSuite (GET /product) -> kumpulin id produk yang punya
         product-variant valid ter-embed ("variants[].id" terisi, pola
         identik product_sync_service.py::_resolve_existing_variant_ids()).
      2. Odoo (get_stock_by_warehouse) -> query stok HANYA utk id-id hasil
         langkah 1 (product_ids terarah, bukan tarik semua lalu buang).
      3. Push ke /stock-matrix.

    REVISI dari versi pertama (yang query Odoo dulu baru cek eSuite):
    urutan lama BOROS karena himpunan yang dicek ke eSuite jadi besar
    (~1241 code, padahal cuma ~30 yang bakal ketemu) -- find_by_external_codes()
    scan hampir semua halaman /product buat cari yang gak akan pernah ketemu.
    Cek eSuite dulu (himpunan kecil, murah) baru Odoo (query terarah) jauh
    lebih hemat, apalagi makin lama katalog Odoo (1241+) makin jauh lebih
    besar daripada yang sudah confirmed di eSuite.

    Parameter "external_codes" (kalau diisi) mempersempit LANGKAH 1 juga --
    pakai find_by_external_codes() yang early-exit (bukan full pull semua
    halaman), lebih hemat lagi kalau memang cuma mau cek beberapa produk.
    """

    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(
        self,
        event: str = "upsert",
        external_codes: str | None = None,
        limit: int | None = None,
        batch_size: int | None = None,
        include_payload: bool = False,
    ):
        warehouses = self._get_in_scope_warehouses()

        # LANGKAH 1 (eSuite-FIRST, lihat docstring kelas) -- tentuin dulu id
        # produk Odoo mana yang AMAN (product-variant-nya udah confirmed ada
        # di eSuite), SEBELUM nyentuh Odoo sama sekali buat query stok.
        if external_codes:
            wanted_ids = self._parse_external_codes(external_codes)
            verified_ids = self._resolve_verified_variant_ids(wanted_ids)
        else:
            verified_ids = self._pull_all_verified_variant_ids()

        if not verified_ids:
            raise ValidationError(
                "Tidak ada produk dengan product-variant valid di eSuite (cek external_codes kalau "
                "diisi, atau push Product dulu lewat POST /sync/product dengan with_variant=True)"
            )

        # LANGKAH 2 -- query stok Odoo SPESIFIK ke id yang sudah confirmed di
        # langkah 1 (bukan tarik semua produk Saleable lalu buang yang gak
        # kepake). 1 pemanggilan get_stock_by_warehouse() per warehouse
        # (context Odoo cuma bisa di-scope ke 1 warehouse per call).
        rows_by_warehouse = {}
        total_matched = 0
        for wh in warehouses:
            stock_rows = self.odoo.get_stock_by_warehouse(wh["id"], product_ids=verified_ids)
            total_matched += len(stock_rows)
            # limit -- diagnostic aid (pola sama dengan product/customer sync),
            # diterapkan PER WAREHOUSE supaya tetap ada baris buat tiap
            # warehouse walau limit kecil (bukan limit gabungan semua warehouse).
            if limit is not None:
                stock_rows = stock_rows[:limit]
            rows_by_warehouse[wh["id"]] = stock_rows

        if total_matched == 0:
            raise ValidationError(
                "Produk sudah confirmed punya product-variant di eSuite, tapi tidak ketemu datanya "
                "di Odoo (category Saleable / mungkin sudah di-archive) -- cek lagi id-nya"
            )

        # skipped_not_found_in_odoo -- id yang confirmed ADA di eSuite (langkah 1)
        # tapi TERNYATA tidak ketemu di query stok Odoo langkah 2 (misal produk
        # sudah di-archive/keluar domain Saleable di Odoo setelah variant-nya
        # sempat di-push). Kasus jarang, tapi dicatat buat visibility -- bukan error.
        found_ids = {row["id"] for wh in warehouses for row in rows_by_warehouse[wh["id"]]}
        skipped_not_found_in_odoo = sorted(
            f"{PRODUCT_EXTERNAL_CODE_PREFIX}{pid}" for pid in set(verified_ids) - found_ids
        )

        payload = [
            self._to_esuite_payload(row, wh)
            for wh in warehouses
            for row in rows_by_warehouse[wh["id"]]
        ]

        # Batching -- pola sama dengan product_sync_service.py: opsional,
        # default None -> 1 batch semua baris sekaligus.
        # Payload di sini secara teori tetap bisa kosong (mis. semua produk
        # verified ternyata kena "limit" jadi 0 per warehouse) -- guard ini
        # cegah "batch_size or len(payload)" jadi 0 & bikin range() step=0 error.
        size = batch_size or len(payload)
        batches = [payload[i : i + size] for i in range(0, len(payload), size)] if payload else []

        batch_results = []
        synced_count = 0
        failed_count = 0

        for idx, batch in enumerate(batches, start=1):
            keys = [self._row_key(item) for item in batch]
            try:
                esuite_result = self.esuite.push("stock-matrix", event=event, data=batch)
                batch_entry = {
                    "batch": idx,
                    "size": len(batch),
                    "status": "success",
                    "keys": keys,
                    "esuite_response": esuite_result,
                }
                if include_payload:
                    batch_entry["payload_sent"] = batch
                batch_results.append(batch_entry)
                synced_count += len(batch)
            except AppError as e:
                # Pola sama dengan product/customer sync -- di-catch per
                # batch, batch lain tetap lanjut. Belum ditest apakah eSuite
                # gagal-per-item (skip item yang product_variant-nya nggak
                # ketemu) atau gagal-1-batch-semua -- kalau ternyata
                # gagal-semua gara-gara 1 item, kecilin batch_size /
                # scoped pakai external_codes dulu (lihat docstring kelas).
                batch_entry = {
                    "batch": idx,
                    "size": len(batch),
                    "status": "failed",
                    "keys": keys,
                    "error": e.to_dict()["error"],
                }
                if include_payload:
                    batch_entry["payload_sent"] = batch
                batch_results.append(batch_entry)
                failed_count += len(batch)

        result = {
            "verified_in_esuite": len(verified_ids),
            "total_matched_in_odoo": total_matched,
            "total_sent": len(payload),
            "skipped_not_found_in_odoo": skipped_not_found_in_odoo,
            "batch_size": size,
            "batch_count": len(batches),
            "synced_count": synced_count,
            "failed_count": failed_count,
            "batches": batch_results,
        }

        note = (
            f"{len(skipped_not_found_in_odoo)} produk verified di eSuite tapi tidak ketemu di Odoo"
            if skipped_not_found_in_odoo
            else ""
        )
        log_sync_result("stock-matrix", event, result, note=note)
        return result

    def _get_in_scope_warehouses(self) -> list:
        """
        Warehouse in-scope, pola sama dengan warehouse_sync_service.py --
        DIPUSATKAN dari Odoo (bukan hardcode 2 external_code) supaya kalau
        nanti ada warehouse baru dalam scope, service ini otomatis ikut,
        tidak perlu ubah kode.
        """
        companies = self.odoo.get_companies(IN_SCOPE_COMPANY_NAMES)
        if not companies:
            raise ValidationError(
                "Tidak ada res.company yang cocok dengan IN_SCOPE_COMPANY_NAMES",
                details={"expected_names": IN_SCOPE_COMPANY_NAMES},
            )

        company_ids = [c["id"] for c in companies]
        warehouses = self.odoo.get_warehouses(company_ids)
        if not warehouses:
            raise ValidationError("Tidak ada stock.warehouse aktif untuk badan usaha in-scope")

        return warehouses

    def _resolve_verified_variant_ids(self, wanted_ids: list[int]) -> list[int]:
        """
        GUARD, versi TARGETED -- dipakai kalau `external_codes` diisi user.
        Cek eSuite CUMA utk id yang diminta lewat `find_by_external_codes()`
        (early-exit begitu semua code ketemu) -- lebih hemat daripada full
        pull kalau himpunan yang mau dicek memang sudah spesifik/kecil.
        """
        if not wanted_ids:
            return []
        codes_wanted = {f"{PRODUCT_EXTERNAL_CODE_PREFIX}{pid}" for pid in wanted_ids}
        resolved = self.esuite.find_by_external_codes("product", codes_wanted)
        return self._extract_verified_ids(resolved.values())

    def _pull_all_verified_variant_ids(self) -> list[int]:
        """
        GUARD, versi FULL PULL -- dipakai kalau `external_codes` TIDAK
        diisi (mau cek SEMUA produk yang ada di eSuite). Loop SEMUA halaman
        GET /product, pola sama dengan warehouse_sync_service.py::
        _resolve_branch_ids() / product_sync_service.py::_resolve_category_ids()
        -- BUKAN pakai find_by_external_codes() (itu buat himpunan code yang
        SUDAH diketahui/spesifik, bukan buat "temukan semua yang ada").
        """
        records = []
        page = 1
        limit = 200

        while True:
            pulled = self.esuite.pull("product", page=page, limit=limit)
            records.extend(pulled.get("data") or [])

            meta = pulled.get("meta") or {}
            total_page = meta.get("total_page", 1)
            if page >= total_page:
                break
            page += 1

        return self._extract_verified_ids(records)

    def _extract_verified_ids(self, product_records) -> list[int]:
        """
        GUARD -- inti logic-nya, dipakai KEDUA versi di atas. Dari sekumpulan
        record /product (baik hasil find_by_external_codes().values() maupun
        full pull), ekstrak id Odoo produk yang punya product-variant VALID
        ter-embed (external_code cocok convention "ODOO-PROD-{id}" DAN
        "variants[].id" terisi) -- pola & alasan IDENTIK dengan
        product_sync_service.py::_resolve_existing_variant_ids() (baca
        komentar di sana untuk detail lengkap kenapa harus baca
        "variants[].id" dari GET /product, BUKAN dari GET /product-variant
        yang collection standalone-nya selalu balikin id kosong).
        Didefinisikan ulang di sini (bukan import silang antar service),
        konsisten dengan pola tiap sync service independen di project ini.

        Return: list id Odoo produk yang AMAN dikirim stoknya. Produk yang
        tidak masuk return berarti: belum pernah di-push ke /product sama
        sekali, ATAU sudah di-push tapi variant-nya belum ke-embed dengan
        benar -- dua-duanya SAMA-SAMA di-skip dari stock-matrix (bukan tugas
        service ini membedakan/memperbaiki, cukup jangan kirim).
        """
        ids = []
        for record in product_records:
            code = record.get("external_code")
            if not code or not code.startswith(PRODUCT_EXTERNAL_CODE_PREFIX):
                continue
            id_part = code[len(PRODUCT_EXTERNAL_CODE_PREFIX):]
            if not id_part.isdigit():
                continue
            has_valid_variant = any(
                v.get("external_code") == code and v.get("id")
                for v in (record.get("variants") or [])
            )
            if has_valid_variant:
                ids.append(int(id_part))
        return ids

    def _parse_external_codes(self, external_codes: str) -> list[int]:
        """
        Parse "ODOO-PROD-123,ODOO-PROD-456" -> [123, 456] -- dipakai buat
        scoped sync (lihat docstring kelas soal kenapa ini penting: baru
        ~30 produk yang confirmed punya product-variant di eSuite). Pola
        & format SAMA PERSIS dengan product_sync_service.py::_parse_external_codes().
        """
        ids = []
        for raw in external_codes.split(","):
            code = raw.strip()
            if not code:
                continue
            if not code.startswith(PRODUCT_EXTERNAL_CODE_PREFIX):
                raise ValidationError(
                    f"external_code '{code}' tidak sesuai format '{PRODUCT_EXTERNAL_CODE_PREFIX}{{id_odoo}}'",
                    details={"expected_prefix": PRODUCT_EXTERNAL_CODE_PREFIX},
                )
            id_part = code[len(PRODUCT_EXTERNAL_CODE_PREFIX):]
            if not id_part.isdigit():
                raise ValidationError(
                    f"external_code '{code}' -- bagian id bukan angka valid",
                    details={"external_code": code},
                )
            ids.append(int(id_part))
        return ids

    def _to_esuite_payload(self, stock_row: dict, warehouse: dict) -> dict:
        # qty_available = stok fisik/on-hand asli (KEPUTUSAN 15 Agustus 2026,
        # lihat docstring kelas -- BUKAN free_qty). Dikirim apa adanya
        # (termasuk 0 atau negatif kalau ada kasus oversold/backorder) --
        # tidak di-floor/dibulatkan, minimal invasive sampai ada bukti nyata
        # perlu penanganan khusus.
        qty = stock_row["qty_available"]

        return {
            "product_variant": {
                "code": f"{PRODUCT_EXTERNAL_CODE_PREFIX}{stock_row['id']}"
            },
            "warehouse": {
                "code": f"{WAREHOUSE_EXTERNAL_CODE_PREFIX}{warehouse['id']}"
            },
            "uom_level_code": DEFAULT_UOM_LEVEL_CODE,
            "quantity": qty,
            "on_hand": qty,
        }

    @staticmethod
    def _row_key(item: dict) -> str:
        """Label ringkas 1 baris payload buat tracing sukses/gagal per batch (pengganti external_codes -- entity ini tidak punya field itu)."""
        return f"{item['product_variant']['code']}@{item['warehouse']['code']}"
