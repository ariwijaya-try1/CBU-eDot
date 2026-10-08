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
# produknya (baris stok 0, tanpa expired_date).
#
# 7 Oktober 2026 -- test live + jawaban dev eDot: di eSuite, produk yang
# belum punya baris stok dianggap stok awal 0, jadi kirim on_hand 0 dibalas
# "unchanged" dan produknya tidak disiapkan. Keputusan user: workaround 2
# LANGKAH per batch (lihat sync()):
#   1. kirim SEED_ON_HAND (1) -> eSuite membuat baris + melaporkan
#      on_hand_before (nilai semula) per item;
#   2. langsung kirim on_hand_before itu lagi -> produk baru jadi 0, stok
#      yang sudah diisi sales kembali ke nilai semula.
SEED_ON_HAND = 1

# Status item dari eSuite (data.results[].status) yang berarti item itu
# TIDAK diproses -- tidak ikut langkah 2.
FAILED_ITEM_STATUSES = {"failed", "not_processed"}

# Langkah 2 (mengembalikan nilai) dicoba ulang kalau call-nya gagal, supaya
# stok tidak tertinggal di angka SEED_ON_HAND. Aman diulang: nilainya
# set-to-target, bukan penambahan.
RESTORE_MAX_ATTEMPTS = 3
RESTORE_RETRY_DELAY_SECONDS = 3.0

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
    "PERHATIAN -- endpoint ini menulis ke stok outlet eSuite dalam 2 langkah "
    "per batch: (1) kirim on_hand 1 untuk tiap produk, (2) langsung kirim "
    "nilai semula yang dilaporkan eSuite (0 untuk produk yang belum punya "
    "stok). Hasil akhir: produk yang belum ada muncul dengan stok 0; stok "
    "TANPA tanggal kedaluwarsa yang sudah diisi sales kembali ke nilai "
    "semula; stok DENGAN tanggal kedaluwarsa tidak tersentuh. Selama "
    "beberapa detik di antara 2 langkah, stok tampil 1. Kalau langkah 2 "
    "gagal, proses BERHENTI dan item itu tertinggal di angka 1 -- lihat "
    "restore_failed_items."
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
      5. Push per 50 item, BERURUTAN, 2 langkah per batch (kirim 1 lalu
         kembalikan ke nilai semula -- lihat komentar SEED_ON_HAND).

    Guard dipasang supaya item yang pasti ditolak eSuite tidak ikut dikirim.

    Aman dijalankan ulang: hasil akhir tiap baris = nilai sebelum dijalankan
    (produk baru = 0), jadi isian sales tidak hilang. Proses BERHENTI di
    batch pertama yang call-nya gagal -- sisanya dilaporkan sebagai
    unprocessed_item_count, lanjutkan dengan limit/offset.
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
                    # Nilai langkah 1. Langkah 2 mengganti on_hand dgn nilai
                    # semula dari jawaban eSuite.
                    "on_hand": SEED_ON_HAND,
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
            # Body LANGKAH 1 (on_hand 1) -- cuma diisi kalau diminta (mode
            # semua customer bisa puluhan ribu baris). Body langkah 2 baru
            # diketahui saat jalan (nilainya dari jawaban eSuite).
            "payload": {"event": "upsert", "data": items} if include_payload else None,
            # pushed_count = item yang selesai 2 langkah (baris ada, nilai
            # sudah dikembalikan). failed_count = item yang ditolak eSuite /
            # call-nya gagal.
            "pushed_count": 0,
            "failed_count": 0,
            # Item yang sebelum dijalankan SUDAH berisi stok (> 0) -- nilainya
            # dikembalikan di langkah 2.
            "existing_stock_count": 0,
            # Item yang nilai semulanya tidak dilaporkan eSuite -> dikembalikan
            # ke 0. Seharusnya selalu 0; kalau tidak, format response berubah.
            "unknown_before_count": 0,
            # Gabungan data.summary eSuite dari semua batch, per langkah.
            "esuite_summary": {"seed": {}, "restore": {}},
            "failed_items": [],
            # KRITIS kalau tidak kosong: item ini tertinggal di on_hand 1.
            # Isinya sudah berbentuk payload -- "on_hand" = nilai yang
            # seharusnya dikembalikan.
            "restore_failed_items": [],
            "aborted": False,
            "abort_reason": None,
            "unprocessed_item_count": 0,
            "batches": [],
        }

        if dry_run or not items:
            return result

        # 5. Push BERURUTAN. Tiap batch 2 langkah (lihat komentar
        # SEED_ON_HAND). BERHENTI di call pertama yang gagal -- beda dari
        # sync lain yang lanjut ke batch berikutnya, karena di sini call
        # yang gagal bisa meninggalkan stok di angka 1.
        batches = [
            items[i : i + resolved_batch_size]
            for i in range(0, len(items), resolved_batch_size)
        ]
        processed_items = 0

        for idx, batch in enumerate(batches, start=1):
            report = {"batch": idx, "size": len(batch)}
            result["batches"].append(report)
            processed_items += len(batch)

            # Langkah 1 -- kirim SEED_ON_HAND
            try:
                seed_response = self.esuite.push("store-stock", "upsert", batch)
            except AppError as e:
                # Kalau penyebabnya timeout, eSuite BISA saja sudah memproses
                # batch ini (stok jadi 1) tanpa kita tahu nilai semulanya.
                report.update(status="seed_failed", error=e.to_dict()["error"])
                result["failed_count"] += len(batch)
                result["aborted"] = True
                result["abort_reason"] = (
                    f"langkah 1 batch {idx} gagal di level call -- cek stok "
                    "customer di batch ini (bisa tertinggal di angka 1 kalau "
                    "penyebabnya timeout)"
                )
                report["customer_external_codes"] = sorted(
                    {it["customer"]["external_code"] for it in batch}
                )
                break

            seed_summary, seed_results = self._parse_response(seed_response)
            self._add_summary(result["esuite_summary"]["seed"], seed_summary)

            restore_items = []
            for item in batch:
                item_result = seed_results.get(self._item_key(item))
                if item_result is not None and item_result.get("status") in FAILED_ITEM_STATUSES:
                    # Ditolak eSuite -> tidak ada yang tertulis, tidak perlu langkah 2.
                    result["failed_items"].append({
                        "customer_external_code": item["customer"]["external_code"],
                        "product_external_code": item["product_variant"]["external_code"],
                        "esuite_result": item_result,
                    })
                    result["failed_count"] += 1
                    continue

                before = (item_result or {}).get("on_hand_before")
                # bool ikut dikecualikan krn di Python bool adalah turunan int.
                if not isinstance(before, (int, float)) or isinstance(before, bool):
                    before = 0
                    result["unknown_before_count"] += 1
                if before > 0:
                    result["existing_stock_count"] += 1

                if before == SEED_ON_HAND:
                    # Nilai semula memang 1 -> sudah benar, tidak perlu langkah 2.
                    result["pushed_count"] += 1
                    continue
                # {**item, ...} = salin dict item lalu timpa key on_hand.
                restore_items.append({**item, "on_hand": before})

            # Langkah 2 -- kembalikan ke nilai semula
            restore_summary = {}
            if restore_items:
                restore_response, restore_error = self._push_restore(restore_items)
                if restore_error:
                    report.update(status="restore_failed", seed_summary=seed_summary, error=restore_error)
                    result["restore_failed_items"].extend(restore_items)
                    result["failed_count"] += len(restore_items)
                    result["aborted"] = True
                    result["abort_reason"] = (
                        f"langkah 2 batch {idx} gagal setelah {RESTORE_MAX_ATTEMPTS}x coba -- "
                        "item di restore_failed_items tertinggal di on_hand 1"
                    )
                    break

                restore_summary, restore_results = self._parse_response(restore_response)
                self._add_summary(result["esuite_summary"]["restore"], restore_summary)
                for item in restore_items:
                    item_result = restore_results.get(self._item_key(item))
                    if item_result is not None and item_result.get("status") in FAILED_ITEM_STATUSES:
                        result["restore_failed_items"].append(item)
                        result["failed_count"] += 1
                    else:
                        result["pushed_count"] += 1

            report.update(status="success", seed_summary=seed_summary, restore_summary=restore_summary)
            if include_payload:
                report["seed_response"] = seed_response
                report["restore_payload"] = restore_items
                report["restore_response"] = restore_response if restore_items else None

            if result["restore_failed_items"]:
                report["status"] = "restore_failed"
                result["aborted"] = True
                result["abort_reason"] = (
                    f"eSuite menolak sebagian item di langkah 2 batch {idx} -- "
                    "item di restore_failed_items tertinggal di on_hand 1"
                )
                break

            if idx < len(batches):
                time.sleep(BATCH_DELAY_SECONDS)

        result["unprocessed_item_count"] = len(items) - processed_items

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
                f"store-stock 2 langkah (kirim {SEED_ON_HAND} lalu nilai semula) -- "
                f"{len(customers_report)} customer, {len(items)} item, "
                f"{result['existing_stock_count']} sudah berisi stok, "
                f"{len(result['restore_failed_items'])} gagal dikembalikan, "
                f"{len(skipped_customers)} customer di-skip, "
                f"{len(unverified_products)} produk di-skip, "
                f"{len(batches)} batch @ max {resolved_batch_size} item"
                + (" -- BERHENTI DI TENGAH" if result["aborted"] else "")
            ),
        )

        return result

    def _push_restore(self, restore_items: list) -> tuple[dict | None, dict | None]:
        """
        Langkah 2, dgn retry. Return (response, None) kalau sukses, atau
        (None, error_dict) kalau semua percobaan gagal.
        """
        last_error = None
        for attempt in range(1, RESTORE_MAX_ATTEMPTS + 1):
            try:
                return self.esuite.push("store-stock", "upsert", restore_items), None
            except AppError as e:
                last_error = e.to_dict()["error"]
                if attempt < RESTORE_MAX_ATTEMPTS:
                    time.sleep(RESTORE_RETRY_DELAY_SECONDS)
        return None, last_error

    @staticmethod
    def _item_key(item: dict) -> str:
        return f'{item["customer"]["external_code"]}|{item["product_variant"]["external_code"]}'

    @staticmethod
    def _parse_response(response: dict | None) -> tuple[dict, dict]:
        """
        Pecah response store-stock (format terlihat live 7 Oktober 2026):
        data.summary {received, upserted, unchanged, failed, not_processed}
        + data.results[] per item. Return (summary, {key_item: result}).
        Key = customer + produk -- cukup, karena bridge tidak pernah kirim
        expired_date (1 customer x 1 produk = 1 baris).
        """
        data = (response or {}).get("data") or {}
        results = {
            f'{r.get("customer_external_code")}|{r.get("product_variant_external_code")}': r
            for r in (data.get("results") or [])
        }
        return data.get("summary") or {}, results

    @staticmethod
    def _add_summary(total: dict, summary: dict) -> None:
        for key, value in summary.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total[key] = total.get(key, 0) + value

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
