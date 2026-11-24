"""
Hapus baris Product Stock outlet utk produk DISCONTINUE (archived di Odoo)
-- 17 November 2026.

Dipakai POST /api/deactivate/outlet-stock-discontinue (grup Swagger
"Deactivate" -- keputusan user: baris tidak benar-benar terhapus permanen,
muncul lagi kalau produk dikirim/diinput ulang).

Keputusan user 13 Nov 2026 (Decision Log outlet_stock v22): SEMUA baris
produk archived di Product Stock outlet dihapus, TERMASUK isian sales
(qty / expired).

Fakta dev eDot 17 Nov 2026 (v26): POST /v1/webhook/store-stock
"event": "delete"; item TANPA expired_date (dan uom_level_code) = hapus
semua baris produk itu di outlet, termasuk baris ber-expired isian sales.
Customer & product_variant boleh id eSuite atau external_code.

Alur:
1. customer eSuite by external_code ODOO-PARTNER-{id}
2. warehouse outlet customer (warehouse.address.id = id customer eSuite,
   fakta 7 Okt 2026)
3. baris stok per warehouse: GET stock-matrix?warehouse_id= (satu-satunya
   jalur yang lolos batas 4 MB eSuite, 12 Nov 2026)
4. variant eSuite -> ODOO-PROD-{id} lewat GET /product (variants[]), status
   Odoo via get_products_sync_status() (active_test False). Archived ATAU
   terhapus dari Odoo = discontinue (sama dgn export input-progress).
5. 1 item delete per (customer, produk) tanpa expired_date, chunk <= 50,
   dikirim berurutan.
Variant tanpa external_code ODOO-PROD-* (bukan dari Odoo) tidak disentuh.

19 November 2026 (keputusan user, Decision Log outlet_stock v29) -- param
opsional include_not_purchased: ikut hapus SEMUA baris produk AKTIF yang
pernah dibeli outlet tsb TAPI tidak dibeli lagi sejak PURCHASE_DATE_FROM
(sisa pre-fill sebelum filter tanggal di POST /sync/outlet-stock).
Produk yang TIDAK PERNAH dibeli outlet (mis. ditambah manual sales) tidak
disentuh.
Aman dijalankan ulang: produk yang sudah terhapus tidak muncul lagi di
GET stock-matrix -> tidak dikirim lagi.
"""
import time

from app.clients.esuite_client import EsuiteClient
from app.clients.odoo_client import OdooClient
from app.core.exceptions import AppError, ValidationError
from app.core.sync_logger import log_sync_result

# Didefinisikan ULANG di sini (convention project: tiap service independen).
CUSTOMER_EXTERNAL_CODE_PREFIX = "ODOO-PARTNER-"
PRODUCT_EXTERNAL_CODE_PREFIX = "ODOO-PROD-"
INTERNAL_WAREHOUSE_PREFIX = "ODOO-WH-"
STOCK_MATRIX_WAREHOUSE_PARAM = "warehouse_id"
MAX_ITEMS_PER_REQUEST = 50  # batas store-stock (dev eDot 5 Okt 2026)
BATCH_DELAY_SECONDS = 1.0
PULL_PAGE_SIZE = 200
MAX_PAGES = 500  # pengaman loop paging
# HARUS SAMA dgn outlet_stock_sync_service.py (sumber list stok outlet).
# 20 Nov 2026: hanya "invoiced" ("to invoice" belum final).
ELIGIBLE_INVOICE_STATUSES = ["invoiced"]
PURCHASE_DATE_FROM = "2026-01-01"
ODOO_CUSTOMER_CHUNK_SIZE = 200


class OutletStockDiscontinueService:
    def __init__(self):
        self.esuite = EsuiteClient()
        self.odoo = OdooClient()

    def run(
        self,
        external_codes: str,
        dry_run: bool = True,
        batch_size: int | None = None,
        include_payload: bool = False,
        include_not_purchased: bool = False,
    ) -> dict:
        codes = self._parse_external_codes(external_codes)
        size = min(batch_size or MAX_ITEMS_PER_REQUEST, MAX_ITEMS_PER_REQUEST)

        # 1. customer eSuite
        customers = self.esuite.find_by_external_codes("customers", set(codes))
        skipped_customers = [
            {"external_code": c, "reason": "customer tidak ada di eSuite"}
            for c in codes if c not in customers
        ]
        code_by_customer_id = {rec["id"]: code for code, rec in customers.items() if rec.get("id")}

        # 2. warehouse outlet milik customer tsb (1 customer bisa >1 warehouse)
        wh_customer: dict[str, str] = {}
        for wh in self._pull_all("warehouse"):
            if str(wh.get("external_code") or "").startswith(INTERNAL_WAREHOUSE_PREFIX):
                continue
            code = code_by_customer_id.get((wh.get("address") or {}).get("id"))
            if wh.get("id") and code:
                wh_customer[wh["id"]] = code
        with_warehouse = set(wh_customer.values())
        skipped_customers += [
            {"external_code": c, "reason": "belum punya warehouse outlet (belum ada Product Stock)"}
            for c in codes if c in customers and c not in with_warehouse
        ]

        # 3. baris stok per warehouse -> {(customer_code, variant_id): [baris]}
        rows_by_key: dict[tuple[str, str], list[dict]] = {}
        variant_info: dict[str, dict] = {}
        for wh_id, customer_code in wh_customer.items():
            result = self.esuite.pull_with_params("stock-matrix", {STOCK_MATRIX_WAREHOUSE_PARAM: wh_id})
            for row in result.get("data") or []:
                if (row.get("warehouse") or {}).get("id") != wh_id:
                    continue  # jaga-jaga kalau filter diabaikan eSuite
                pv = row.get("product_variant") or {}
                if not pv.get("id"):
                    continue
                variant_info.setdefault(pv["id"], {"code": pv.get("code") or "", "name": pv.get("name") or ""})
                rows_by_key.setdefault((customer_code, pv["id"]), []).append(row)

        # 4. variant discontinue (+ opsional: tidak dibeli lagi sejak PURCHASE_DATE_FROM)
        pid_by_variant = self._map_variants_to_pid(set(variant_info))
        discontinued = self._discontinued_variants(pid_by_variant)
        from_odoo_count = len(pid_by_variant)
        stale_keys: set[tuple[str, str]] = set()
        if include_not_purchased:
            stale_keys = self._not_purchased_keys(
                rows_by_key, pid_by_variant, set(discontinued), sorted(with_warehouse)
            )

        # 5. item delete (tanpa expired_date = semua baris produk di outlet)
        items, details = [], []
        for (customer_code, vid), rows in sorted(rows_by_key.items()):
            if vid in discontinued:
                product_code, reason = discontinued[vid]
            elif (customer_code, vid) in stale_keys:
                product_code = f"{PRODUCT_EXTERNAL_CODE_PREFIX}{pid_by_variant[vid]}"
                reason = f"tidak dibeli lagi sejak {PURCHASE_DATE_FROM}"
            else:
                continue
            items.append({
                "customer": {"external_code": customer_code},
                "product_variant": {"external_code": product_code},
            })
            details.append({
                "customer_external_code": customer_code,
                "product_external_code": product_code,
                "variant_code": variant_info[vid]["code"],
                "variant_name": variant_info[vid]["name"],
                "reason": reason,
                "rows": [
                    {"batch": (r.get("batch") or {}).get("code") or "", "on_hand": r.get("on_hand")}
                    for r in rows
                ],
            })

        batches = [items[i:i + size] for i in range(0, len(items), size)]
        result = {
            "dry_run": dry_run,
            "warning": (
                "Delete menghapus SEMUA baris produk di outlet (termasuk qty/expired isian sales). "
                "Baris muncul lagi kalau produk dikirim/diinput ulang."
            ),
            "customer_count": len(codes),
            "warehouse_count": len(wh_customer),
            "item_count": len(items),
            "row_count": sum(len(d["rows"]) for d in details),
            "batch_count": len(batches),
            # diagnostik: 0 item krn memang tidak ada produk archived, atau krn variant tidak terpetakan
            "scan": {
                "stock_row_count": sum(len(v) for v in rows_by_key.values()),
                "variant_count": len(variant_info),
                "variant_from_odoo_count": from_odoo_count,
                "variant_discontinued_count": len(discontinued),
                "include_not_purchased": include_not_purchased,
                "not_purchased_item_count": len(stale_keys),
            },
            "skipped_customers": skipped_customers,
            "items": details,
            "payload": {"event": "delete", "data": items} if include_payload and dry_run else None,
        }
        if dry_run or not items:
            return result

        # 6. push berurutan; call gagal = berhenti (aman dijalankan ulang)
        pushed, summary_total, batch_results = 0, {}, []
        aborted, error = False, None
        for idx, batch in enumerate(batches, start=1):
            try:
                response = self.esuite.push("store-stock", "delete", batch)
            except AppError as exc:
                aborted, error = True, {"batch": idx, **exc.to_dict()["error"]}
                break
            pushed += len(batch)
            data = (response or {}).get("data") or {}
            for key, value in (data.get("summary") or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    summary_total[key] = summary_total.get(key, 0) + value
            batch_results.append({
                "batch": idx,
                "item_count": len(batch),
                "esuite_response": response,
                "payload_sent": {"event": "delete", "data": batch} if include_payload else None,
            })
            if idx < len(batches):
                time.sleep(BATCH_DELAY_SECONDS)

        result.update({
            "pushed_count": pushed,
            "unprocessed_item_count": len(items) - pushed,
            "esuite_summary": summary_total,
            "aborted": aborted,
            "error": error,
            "batches": batch_results,
        })
        log_sync_result(
            "outlet_stock_discontinue",
            "delete",
            {
                "total_matched_in_odoo": len(items),
                "synced_count": pushed,
                "failed_count": len(items) - pushed,
                "batch_count": len(batch_results),
            },
            note=(
                f"{len(codes)} customer, {result['row_count']} baris"
                + (f", termasuk {len(stale_keys)} item tidak dibeli sejak {PURCHASE_DATE_FROM}"
                   if include_not_purchased else "")
            ),
        )
        return result

    def _map_variants_to_pid(self, variant_ids: set[str]) -> dict[str, int]:
        """{variant_id eSuite: product.product id Odoo} lewat GET /product (variants[] ODOO-PROD-*)."""
        pid_by_variant: dict[str, int] = {}
        if not variant_ids:
            return pid_by_variant
        for record in self._pull_all("product"):
            for v in record.get("variants") or []:
                code = str(v.get("external_code") or "")
                raw = code[len(PRODUCT_EXTERNAL_CODE_PREFIX):]
                if v.get("id") in variant_ids and code.startswith(PRODUCT_EXTERNAL_CODE_PREFIX) and raw.isdigit():
                    pid_by_variant[v["id"]] = int(raw)
        return pid_by_variant

    def _discontinued_variants(self, pid_by_variant: dict[str, int]) -> dict[str, tuple[str, str]]:
        """{variant_id eSuite: (ODOO-PROD-{id}, alasan)} utk produk archived / terhapus di Odoo."""
        if not pid_by_variant:
            return {}
        status = self.odoo.get_products_sync_status(sorted(set(pid_by_variant.values())))
        result = {}
        for vid, pid in pid_by_variant.items():
            info = status.get(pid)
            if info is None:
                result[vid] = (f"{PRODUCT_EXTERNAL_CODE_PREFIX}{pid}", "terhapus dari Odoo")
            elif not info.get("active"):
                result[vid] = (f"{PRODUCT_EXTERNAL_CODE_PREFIX}{pid}", "archived di Odoo")
        return result

    def _not_purchased_keys(
        self,
        rows_by_key: dict[tuple[str, str], list[dict]],
        pid_by_variant: dict[str, int],
        discontinued_vids: set[str],
        customer_codes: list[str],
    ) -> set[tuple[str, str]]:
        """
        (customer_code, variant_id) utk produk aktif yang PERNAH dibeli outlet
        tapi TIDAK dibeli lagi sejak PURCHASE_DATE_FROM. Produk yang tidak pernah
        dibeli sama sekali tidak ikut. Lookup Odoo gagal -> AppError diteruskan
        (tidak ada delete berdasarkan data setengah).
        """
        customer_ids = [int(c[len(CUSTOMER_EXTERNAL_CODE_PREFIX):]) for c in customer_codes]
        ever: dict[int, dict] = {}
        recent: dict[int, dict] = {}
        for i in range(0, len(customer_ids), ODOO_CUSTOMER_CHUNK_SIZE):
            chunk = customer_ids[i:i + ODOO_CUSTOMER_CHUNK_SIZE]
            ever.update(self.odoo.get_purchased_product_ids_by_customer(chunk, ELIGIBLE_INVOICE_STATUSES))
            recent.update(self.odoo.get_purchased_product_ids_by_customer(
                chunk, ELIGIBLE_INVOICE_STATUSES, date_from=PURCHASE_DATE_FROM
            ))
        keys = set()
        for customer_code, vid in rows_by_key:
            if vid in discontinued_vids or vid not in pid_by_variant:
                continue
            cid = int(customer_code[len(CUSTOMER_EXTERNAL_CODE_PREFIX):])
            pid = pid_by_variant[vid]
            bought_ever = pid in set((ever.get(cid) or {}).get("product_ids") or [])
            bought_recent = pid in set((recent.get(cid) or {}).get("product_ids") or [])
            if bought_ever and not bought_recent:
                keys.add((customer_code, vid))
        return keys

    def _pull_all(self, entity: str) -> list[dict]:
        rows, page = [], 1
        while True:
            result = self.esuite.pull(entity, page=page, limit=PULL_PAGE_SIZE)
            batch = result.get("data") or []
            rows.extend(batch)
            total_page = (result.get("meta") or {}).get("total_page") or 0
            if not batch or page >= total_page:
                return rows
            page += 1
            if page > MAX_PAGES:
                raise AppError(
                    code="ESUITE_PAGING_LIMIT",
                    message=f"GET /{entity} melebihi {MAX_PAGES} halaman -- dihentikan",
                    status_code=502,
                )

    @staticmethod
    def _parse_external_codes(external_codes: str) -> list[str]:
        """Wajib diisi -- sengaja tidak ada mode 'semua outlet' (1 GET stock-matrix per warehouse)."""
        codes = list(dict.fromkeys(c.strip() for c in (external_codes or "").split(",") if c.strip()))
        if not codes:
            raise ValidationError("external_codes tidak boleh kosong")
        bad = [c for c in codes if not (c.startswith(CUSTOMER_EXTERNAL_CODE_PREFIX)
                                         and c[len(CUSTOMER_EXTERNAL_CODE_PREFIX):].isdigit())]
        if bad:
            raise ValidationError(
                f"external_codes harus format '{CUSTOMER_EXTERNAL_CODE_PREFIX}{{id_odoo}}'",
                details={"invalid": bad},
            )
        return codes
