from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError
from app.core.sync_logger import log_sync_result

# company_external_id -- id perusahaan Cahaya Boga Utama di eSuite. Dev eDot
# konfirmasi LANGSUNG (28 Agustus 2026) ini sudah "disesuaikan dev dengan data
# Cahaya Boga" -- bukan dummy ilustratif seperti "ODOO-CUST-42"/"ODOO-EMP-7"
# di contoh payload yang sama (lihat order_history_import.md, klarifikasi
# poin 4). Fixed value sama utk semua order, pola sama dengan CURRENCY di
# customer_sync_service.py (konstanta wajib, bukan hasil resolve dari Odoo).
COMPANY_EXTERNAL_ID = "9001065"

# Prefix external_code -- didefinisikan ULANG di sini (bukan cross-import
# dari customer_sync_service.py/product_sync_service.py), konsisten dengan
# convention project ini "tiap service independen" (lihat komentar sama di
# customer_upsert_geo_branch_sales_service.py).
CUSTOMER_EXTERNAL_CODE_PREFIX = "ODOO-PARTNER-"
PRODUCT_EXTERNAL_CODE_PREFIX = "ODOO-PROD-"
ORDER_EXTERNAL_ID_PREFIX = "ODOO-SO-"  # dikonfirmasi user 28 Agustus 2026 (AskUserQuestion)

# UOM Odoo -> STRING nama persis eSuite (BEDA bentuk dari UOM_MAPPING di
# product_sync_service.py yang berupa {"id": ...} -- field "uom" di payload
# orders/import ini STRING NAMA langsung, bukan object). VERIFIED LIVE 28
# Agustus 2026 via GET /debug/pull/uom: UM-0001 name="Units", UM-0006
# name="Kilogram" -- cocok 100% dgn dugaan awal. UOM bisnis CBU cuma pakai
# 2 ini (dikonfirmasi user, mostly "Units").
UOM_NAME_MAPPING = {
    "units": "Units",
    "kg": "Kilogram",
}

# Salesman -- HANYA 4 external_code test tersedia dari dev eDot selama masa
# development (akun tambahan kena charge, jadi cuma dikasih 4). User
# konfirmasi 28 Agustus 2026: TIDAK PERLU mapping presisi ke
# sale.order.user_id (salesperson asli Odoo) -- "siapapun sales yang visit
# outlet akan dapat order terakhir yang sama". v1: 1 kode TETAP dipakai utk
# SEMUA order, dipilih dari 3 kode REAL (punya akses mobile app eWork) --
# BUKAN "202600001" (dummy, tidak ada akses mobile, order dgn kode ini tidak
# akan bisa diverifikasi lewat app). Ganti constant ini kalau mau kode lain
# (202600003/202600004) -- user konfirmasi pilihan di antara 3 kode real
# tidak berpengaruh ke hasil yang muncul di app.
SALESMAN_EXTERNAL_CODE = "202600002"

# Filter scope v1 (28 Agustus 2026, PROVISIONAL -- user: "untuk sekarang buat
# 1 last order, nanti aku minta feedback actual dari sales"): per outlet,
# ambil 1 order TERAKHIR dengan invoice_status ini saja (bukan full history).
# Field Odoo sale.order.invoice_status (selection standar: upselling/invoiced/
# to invoice/no) -- "to invoice" = user: "sudah dikirim dan/atau sedang dalam
# pencairan finance". BUKAN state="sale"+locked=true (itu cuma nunjukin
# invoice_status="invoiced", beda kriteria).
ELIGIBLE_INVOICE_STATUS = "to invoice"

# Berapa banyak order TERBARU per customer yang di-scan (dari
# get_order_history_by_customer(), sudah date_order desc) buat cari yang
# invoice_status cocok. Bukan angka final/dikonfirmasi user -- default aman
# supaya tidak narik seluruh histori tiap customer (bisa ratusan order utk
# customer lama), tapi cukup besar buat kemungkinan besar nemu order
# "to invoice" kalau ada. Kalau ternyata sering tidak ketemu dalam N ini,
# perbesar param lookback_limit di endpoint (bukan ubah constant ini).
DEFAULT_LOOKBACK_LIMIT = 50

CURRENCY = "IDR"  # string literal, BUKAN object -- beda dari field currency di endpoint /sales-order lama


class OrderHistorySyncService:
    """
    v1 (28 Agustus 2026) -- push riwayat order ke webhook eDot
    POST /v1/webhook/orders/import (endpoint TERPISAH dari POST /sales-order
    yang sudah ada di Postman collection -- lihat order_history_import.md
    utk detail perbedaannya). Scope v1: per outlet/customer, cuma 1 order
    TERAKHIR yang invoice_status="to invoice" (PROVISIONAL, bisa di-expand
    ke full-history nanti kalau user minta pasca feedback tim sales).

    Terima 1 ATAU BANYAK customer_id sekaligus (kirim 1 -> cuma 1 yang
    diproses) -- desain diminta user 28 Agustus 2026 supaya endpoint yang
    sama bisa dipakai baik utk 1 outlet spesifik maupun bulk beberapa
    outlet, tanpa 2 endpoint terpisah.
    """

    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(self, customer_ids: list[int], lookback_limit: int | None = None) -> dict:
        if not customer_ids:
            raise ValidationError("customer_ids tidak boleh kosong")

        lookback_limit = lookback_limit or DEFAULT_LOOKBACK_LIMIT

        orders_payload = []
        local_skipped = []  # customer yang TIDAK ketemu order "to invoice" -- tidak sempat dikirim ke eSuite sama sekali

        for customer_id in customer_ids:
            orders = self.odoo.get_order_history_by_customer(customer_id, limit=lookback_limit)
            match = next(
                (o for o in orders if o.get("invoice_status") == ELIGIBLE_INVOICE_STATUS),
                None,
            )
            if not match:
                local_skipped.append({
                    "customer_id": customer_id,
                    "reason": (
                        f"tidak ada order dengan invoice_status='{ELIGIBLE_INVOICE_STATUS}' "
                        f"dalam {lookback_limit} order terbaru customer ini"
                    ),
                })
                continue

            orders_payload.append(self._to_order_payload(match, customer_id))

        result = {
            "company_external_id": COMPANY_EXTERNAL_ID,
            "requested_count": len(customer_ids),
            "sent_count": len(orders_payload),
            "local_skipped": local_skipped,
            "esuite_response": None,
        }

        if not orders_payload:
            # Tidak ada 1 pun customer yang match filter -- tidak perlu
            # panggil eSuite sama sekali (hindari push {"orders": []} kosong).
            return result

        response = self.esuite.push_raw(
            "orders/import",
            {"company_external_id": COMPANY_EXTERNAL_ID, "orders": orders_payload},
        )
        result["esuite_response"] = response

        # data.summary/data.results[] -- WAJIB dibaca per-order, HTTP 200
        # dari endpoint ini TIDAK BERARTI semua order ke-import (dev eDot,
        # jawaban pertanyaan #1, lihat order_history_import.md).
        summary = ((response or {}).get("data") or {}).get("summary") or {}
        log_sync_result(
            "order_history",
            "import",
            {
                "total_matched_in_odoo": len(customer_ids),
                "synced_count": summary.get("imported"),
                "failed_count": (summary.get("skipped") or 0) + (summary.get("errored") or 0),
            },
            note=(
                f"orders/import v1 -- 1 order terakhir/outlet, "
                f"invoice_status='{ELIGIBLE_INVOICE_STATUS}', "
                f"{len(local_skipped)} customer di-skip lokal (tidak ada order match)"
            ),
        )

        return result

    def _to_order_payload(self, order: dict, customer_id: int) -> dict:
        items = []
        for line in order.get("lines", []):
            # Skip baris section/note Odoo (display_type line_section/line_note)
            # -- baris ini TIDAK punya product_id (selalu False), bukan item
            # produk beneran. get_order_history_by_customer() tidak filter ini
            # di query, jadi difilter di sini.
            product = line.get("product_id")
            if not product:
                continue

            uom_field = line.get("product_uom_id") or [None, ""]
            uom_name_odoo = (uom_field[1] or "").strip()
            uom_key = uom_name_odoo.lower()
            uom_value = UOM_NAME_MAPPING.get(uom_key)
            if not uom_value:
                raise ValidationError(
                    f"UOM Odoo '{uom_name_odoo}' belum ada di UOM_NAME_MAPPING "
                    f"(order id {order.get('id')}, customer {customer_id})",
                    details={"odoo_uom_name": uom_name_odoo, "known_mappings": list(UOM_NAME_MAPPING.keys())},
                )

            items.append({
                "product_external_code": f"{PRODUCT_EXTERNAL_CODE_PREFIX}{product[0]}",
                "name": line.get("name"),
                "quantity": line.get("product_uom_qty"),
                "uom": uom_value,
                "unit_price": line.get("price_unit"),
                "discount": 0,  # non-priority v1, instruksi user 28 Agustus 2026
                "tax": line.get("price_tax"),
                "subtotal": line.get("price_subtotal"),
            })

        return {
            "external_id": f"{ORDER_EXTERNAL_ID_PREFIX}{order.get('id')}",
            "order_number": order.get("name"),
            "order_date": order.get("date_order"),
            "status": "completed",  # hardcode, dikonfirmasi dev (jawaban #2)
            "customer": {"external_code": f"{CUSTOMER_EXTERNAL_CODE_PREFIX}{customer_id}"},
            "salesman": {"external_code": SALESMAN_EXTERNAL_CODE},
            "currency": CURRENCY,
            "items": items,
            "amount": {
                "subtotal": order.get("amount_untaxed"),
                "discount": 0,  # non-priority v1
                "tax": order.get("amount_tax"),
                "delivery_fee": 0,  # hardcode, dikonfirmasi dev (jawaban #5)
                "grand_total": order.get("amount_total"),
            },
        }
