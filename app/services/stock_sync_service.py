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

    PENTING (belum jadi blocker koding, tapi blocker ROLLOUT penuh): baru
    ~30 dari 1241 produk yang confirmed punya product-variant ke-push ke
    eSuite (embed 1:1). Push stock buat produk yang variant-nya BELUM ada
    di eSuite kemungkinan besar gagal match ("product_variant not found").
    Makanya parameter "external_codes" di bawah PENTING dipakai buat scoped
    test dulu ke produk yang sudah settled, sebelum full rollout menunggu
    mass re-push produk selesai.
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
        product_ids = self._parse_external_codes(external_codes) if external_codes else None

        warehouses = self._get_in_scope_warehouses()

        # Ambil stok per warehouse -- 1 pemanggilan get_stock_by_warehouse()
        # per warehouse (context Odoo cuma bisa di-scope ke 1 warehouse per
        # call, lihat odoo_client.py::get_stock_by_warehouse()).
        rows_by_warehouse = {}
        total_matched = 0
        for wh in warehouses:
            stock_rows = self.odoo.get_stock_by_warehouse(wh["id"], product_ids=product_ids)
            total_matched += len(stock_rows)
            # limit -- diagnostic aid (pola sama dengan product/customer sync),
            # diterapkan PER WAREHOUSE supaya tetap ada baris buat tiap
            # warehouse walau limit kecil (bukan limit gabungan semua warehouse).
            if limit is not None:
                stock_rows = stock_rows[:limit]
            rows_by_warehouse[wh["id"]] = stock_rows

        if total_matched == 0:
            raise ValidationError(
                "Tidak ada stok produk Saleable ditemukan di Odoo untuk warehouse in-scope "
                "(cek juga external_codes kalau diisi)"
            )

        payload = [
            self._to_esuite_payload(row, wh)
            for wh in warehouses
            for row in rows_by_warehouse[wh["id"]]
        ]

        # Batching -- pola sama dengan product_sync_service.py: opsional,
        # default None -> 1 batch semua baris sekaligus.
        size = batch_size or len(payload)
        batches = [payload[i : i + size] for i in range(0, len(payload), size)] or [[]]

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
            "total_matched_in_odoo": total_matched,
            "total_sent": len(payload),
            "batch_size": size,
            "batch_count": len(batches),
            "synced_count": synced_count,
            "failed_count": failed_count,
            "batches": batch_results,
        }

        log_sync_result("stock-matrix", event, result)
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
