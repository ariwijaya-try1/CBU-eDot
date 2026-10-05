import time

from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import AppError, ValidationError
from app.core.sync_logger import log_sync_result

# Prefix external_code -- didefinisikan ULANG di sini (bukan cross-import),
# konsisten convention project "tiap service independen".
CUSTOMER_EXTERNAL_CODE_PREFIX = "ODOO-PARTNER-"
PRODUCT_EXTERNAL_CODE_PREFIX = "ODOO-PROD-"

# "Pernah dibeli" = order yang barangnya sudah terkirim. Daftar status SAMA
# dgn ELIGIBLE_INVOICE_STATUSES di order_history_sync_service.py (draft /
# quotation / cancel tidak ikut).
ELIGIBLE_INVOICE_STATUSES = ["to invoice", "invoiced"]

# Odoo TIDAK tahu stok fisik di outlet -- bridge cuma menyiapkan LIST
# produknya. Tiap baris dikirim on_hand 0, tanpa expired_date.
PLACEHOLDER_ON_HAND = 0

# Dev eDot 5 Oktober 2026: kosongkan = satuan dasar produk (semua produk
# Cahaya cuma punya 1 satuan).
UOM_LEVEL_CODE = ""

# Batas HARD eSuite: maks 50 item per request, request dikirim BERURUTAN.
MAX_ITEMS_PER_REQUEST = 50

# Jeda antar request ke eSuite (detik) -- belum ada info resmi rate limit
# endpoint ini, angka konservatif (sama dgn order_history_sync_service.py).
BATCH_DELAY_SECONDS = 1.0

# Berapa customer per 1 putaran query Odoo (2 RPC per putaran).
ODOO_CUSTOMER_CHUNK_SIZE = 50

# Ditampilkan di Swagger (docstring route) DAN di field "warning" response.
OVERWRITE_WARNING = (
    "PERINGATAN -- endpoint eSuite store-stock MENIMPA stok (bukan menambah). "
    "Semua baris dikirim on_hand 0 tanpa expired_date, jadi stok outlet TANPA "
    "tanggal kedaluwarsa yang sudah diisi sales untuk produk yang sama akan "
    "di-reset ke 0. Stok yang diisi sales DENGAN tanggal kedaluwarsa tidak "
    "tersentuh (dicatat sebagai baris terpisah). Bridge belum bisa mengecek "
    "stok outlet yang sudah ada, jadi tidak ada baris yang dilewati otomatis."
)


class OutletStockSyncService:
    """
    Stok Outlet (5 Oktober 2026) -- siapkan LIST produk di stok toko/outlet
    eSuite (eWork: Outlet Detail -> Product Stock) dari data Odoo, lewat
    webhook POST /store-stock.

    Alur:
      1. Customer Odoo (semua, atau external_codes tertentu).
      2. GUARD customer -- cek eSuite: customer harus sudah ada DAN punya
         sales branch (syarat endpoint store-stock dari dev eDot).
      3. Odoo -- produk yang pernah dibeli tiap customer (riwayat sale.order).
      4. GUARD produk -- cek eSuite: produk harus sudah ada dgn variant valid
         (pola sama stock_sync_service.py).
      5. Push per 50 item, BERURUTAN.

    Guard dipasang karena perilaku store-stock kalau 1 item tidak dikenal
    BELUM diketahui (1 request ditolak semua / per item / diam-diam dilewati).
    """

    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(
        self,
        external_codes: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        dry_run: bool = True,
        batch_size: int | None = None,
        include_payload: bool = False,
    ) -> dict:
        # Caller boleh minta batch lebih kecil, TIDAK PERNAH lebih besar
        # dari batas eSuite.
        resolved_batch_size = min(batch_size or MAX_ITEMS_PER_REQUEST, MAX_ITEMS_PER_REQUEST)

        # 1. Customer Odoo -- diurutkan id supaya offset/limit stabil antar
        # panggilan (dipakai utk jalan bertahap).
        if external_codes:
            customer_ids = self._parse_external_codes(external_codes)
        else:
            customer_ids = self.odoo.get_customer_ids()
        customer_ids = sorted(set(customer_ids))
        total_in_scope = len(customer_ids)

        customer_ids = customer_ids[offset:]
        if limit:
            customer_ids = customer_ids[:limit]

        skipped_customers = []

        # 2. GUARD customer
        esuite_customers = self._find_esuite_customers(customer_ids)
        eligible_ids = []
        for customer_id in customer_ids:
            code = f"{CUSTOMER_EXTERNAL_CODE_PREFIX}{customer_id}"
            record = esuite_customers.get(code)
            if record is None:
                skipped_customers.append({
                    "customer_external_code": code,
                    "customer_name": None,
                    "reason": "customer belum ada di eSuite -- jalankan POST /sync/customers dulu",
                })
                continue
            if not ((record.get("sales") or {}).get("branchs") or []):
                skipped_customers.append({
                    "customer_external_code": code,
                    "customer_name": record.get("name"),
                    "reason": "customer belum punya sales branch di eSuite (syarat store-stock)",
                })
                continue
            eligible_ids.append(customer_id)

        # 3. Odoo -- produk yang pernah dibeli, per chunk customer
        purchased: dict[int, dict] = {}
        for i in range(0, len(eligible_ids), ODOO_CUSTOMER_CHUNK_SIZE):
            chunk = eligible_ids[i : i + ODOO_CUSTOMER_CHUNK_SIZE]
            purchased.update(
                self.odoo.get_purchased_product_ids_by_customer(chunk, ELIGIBLE_INVOICE_STATUSES)
            )

        # 4. GUARD produk
        wanted_product_codes = {
            f"{PRODUCT_EXTERNAL_CODE_PREFIX}{pid}"
            for entry in purchased.values()
            for pid in entry["product_ids"]
        }
        verified_product_codes = self._find_verified_product_codes(wanted_product_codes)

        # Item payload. Tidak mungkin dobel: 1 customer x 1 produk = 1 baris
        # (product_ids per customer sudah unik dari Odoo).
        items = []
        customers_report = []
        unverified_products: dict[str, int] = {}  # code -> jumlah customer yang kena
        eligible_statuses = "/".join(ELIGIBLE_INVOICE_STATUSES)

        for customer_id in eligible_ids:
            code = f"{CUSTOMER_EXTERNAL_CODE_PREFIX}{customer_id}"
            name = (esuite_customers.get(code) or {}).get("name")
            entry = purchased.get(customer_id)
            if not entry:
                skipped_customers.append({
                    "customer_external_code": code,
                    "customer_name": name,
                    "reason": f"tidak ada riwayat order (invoice_status {eligible_statuses}) di Odoo",
                })
                continue

            product_count = 0
            for product_id in entry["product_ids"]:
                product_code = f"{PRODUCT_EXTERNAL_CODE_PREFIX}{product_id}"
                if product_code not in verified_product_codes:
                    unverified_products[product_code] = unverified_products.get(product_code, 0) + 1
                    continue
                items.append({
                    "customer": {"external_code": code},
                    "product_variant": {"external_code": product_code},
                    "uom_level_code": UOM_LEVEL_CODE,
                    "on_hand": PLACEHOLDER_ON_HAND,
                    # expired_date SENGAJA tidak dikirim (opsional, dev: kosongkan
                    # kalau tidak ada tanggal kedaluwarsa).
                })
                product_count += 1

            if not product_count:
                skipped_customers.append({
                    "customer_external_code": code,
                    "customer_name": name,
                    "reason": "semua produk yang pernah dibeli belum ada di eSuite",
                })
                continue
            customers_report.append({
                "customer_external_code": code,
                "customer_name": name,
                "product_count": product_count,
            })

        result = {
            "warning": OVERWRITE_WARNING,
            "dry_run": dry_run,
            "total_customers_in_scope": total_in_scope,
            "processed_customer_count": len(customer_ids),
            "customer_count": len(customers_report),
            "item_count": len(items),
            "batch_size": resolved_batch_size,
            "batch_count": (len(items) + resolved_batch_size - 1) // resolved_batch_size,
            "customers": customers_report,
            "skipped_customers": skipped_customers,
            "skipped_products": [
                {
                    "product_external_code": product_code,
                    "customer_count": count,
                    "reason": "produk/variant belum ada di eSuite -- jalankan POST /sync/product dulu",
                }
                for product_code, count in sorted(unverified_products.items())
            ],
            # Body persis yang dikirim -- cuma diisi kalau diminta (mode semua
            # customer bisa puluhan ribu baris).
            "payload": {"event": "upsert", "data": items} if include_payload else None,
            "pushed_count": 0,
            "failed_count": 0,
            "batches": [],
        }

        if dry_run or not items:
            return result

        # 5. Push BERURUTAN, 1 batch per call. Tiap batch di-try/except
        # terpisah (pola order_history_sync_service.py) -- 1 batch gagal
        # tidak menghentikan batch lain.
        batches = [
            items[i : i + resolved_batch_size]
            for i in range(0, len(items), resolved_batch_size)
        ]
        for idx, batch in enumerate(batches, start=1):
            try:
                response = self.esuite.push("store-stock", "upsert", batch)
                result["pushed_count"] += len(batch)
                # Response eSuite disimpan APA ADANYA -- format hasil per item
                # endpoint ini belum diketahui, HTTP 200 belum tentu semua
                # item tersimpan.
                result["batches"].append({
                    "batch": idx,
                    "size": len(batch),
                    "status": "success",
                    "esuite_response": response,
                })
            except AppError as e:
                result["failed_count"] += len(batch)
                result["batches"].append({
                    "batch": idx,
                    "size": len(batch),
                    "status": "failed",
                    "customer_external_codes": sorted({it["customer"]["external_code"] for it in batch}),
                    "error": e.to_dict()["error"],
                })

            if idx < len(batches):
                time.sleep(BATCH_DELAY_SECONDS)

        log_sync_result(
            "outlet_stock",
            "upsert",
            {
                "total_matched_in_odoo": len(customer_ids),
                "synced_count": result["pushed_count"],
                "failed_count": result["failed_count"],
                "batch_count": len(batches),
            },
            note=(
                f"store-stock -- {len(customers_report)} customer, {len(items)} item "
                f"(on_hand {PLACEHOLDER_ON_HAND}), {len(skipped_customers)} customer di-skip, "
                f"{len(unverified_products)} produk di-skip, "
                f"{len(batches)} batch @ max {resolved_batch_size} item"
            ),
        )

        return result

    def _find_esuite_customers(self, customer_ids: list[int]) -> dict[str, dict]:
        """
        GUARD customer -- {external_code: record GET /customers}.
        find_by_external_codes() berhenti begitu semua code ketemu (hemat
        kalau cuma beberapa customer); kalau ada yang tidak ketemu, semua
        halaman ke-scan (sama dgn full pull).
        """
        if not customer_ids:
            return {}
        codes = {f"{CUSTOMER_EXTERNAL_CODE_PREFIX}{cid}" for cid in customer_ids}
        return self.esuite.find_by_external_codes("customers", codes)

    def _find_verified_product_codes(self, wanted_codes: set[str]) -> set[str]:
        """
        GUARD produk -- external_code produk yang ADA di eSuite dan punya
        variant valid ter-embed (variants[].external_code sama + id terisi).
        Aturan SAMA dgn stock_sync_service.py::_extract_verified_ids(),
        didefinisikan ulang di sini (tiap service independen).
        """
        if not wanted_codes:
            return set()
        records = self.esuite.find_by_external_codes("product", wanted_codes)
        return {
            code
            for code, record in records.items()
            if any(
                v.get("external_code") == code and v.get("id")
                for v in (record.get("variants") or [])
            )
        }

    def _parse_external_codes(self, external_codes: str) -> list[int]:
        """Parse "ODOO-PARTNER-1655,ODOO-PARTNER-39353" -> [1655, 39353]."""
        ids = []
        for raw in external_codes.split(","):
            code = raw.strip()
            if not code:
                continue
            if not code.startswith(CUSTOMER_EXTERNAL_CODE_PREFIX):
                raise ValidationError(
                    f"external_code '{code}' tidak sesuai format '{CUSTOMER_EXTERNAL_CODE_PREFIX}{{id_odoo}}'",
                    details={"expected_prefix": CUSTOMER_EXTERNAL_CODE_PREFIX},
                )
            id_part = code[len(CUSTOMER_EXTERNAL_CODE_PREFIX):]
            if not id_part.isdigit():
                raise ValidationError(
                    f"external_code '{code}' -- bagian id bukan angka valid",
                    details={"external_code": code},
                )
            ids.append(int(id_part))
        if not ids:
            raise ValidationError("external_codes tidak boleh kosong")
        return ids
