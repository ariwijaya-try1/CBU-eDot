from fastapi import APIRouter, Query

from app.core.exceptions import ValidationError
from app.services.order_history_sync_service import OrderHistorySyncService

router = APIRouter()
service = OrderHistorySyncService()


def _parse_customer_ids(customer_ids: str) -> list[int]:
    """
    Terima RAW id Odoo (res.partner), comma-separated kalau >1 -- pola SAMA
    dengan identifier customer_id di GET /odoo/order-history-by-customer
    (odoo_get.py), BUKAN external_code (endpoint ini kirim 1 order/outlet
    langsung ke eSuite, tidak perlu resolve external_code -> id Odoo).
    """
    raw_parts = [p.strip() for p in customer_ids.split(",") if p.strip()]
    if not raw_parts:
        raise ValidationError("customer_ids tidak boleh kosong")

    parsed = []
    for part in raw_parts:
        if not part.isdigit():
            raise ValidationError(
                f"customer_ids harus angka (id Odoo res.partner) -- '{part}' bukan angka valid",
                details={"invalid_value": part},
            )
        parsed.append(int(part))
    return parsed


@router.post("/sync/order-history")
def sync_order_history(
    customer_ids: str = Query(
        ...,
        description=(
            "WAJIB -- id Odoo res.partner (Customer/Outlet), comma-separated "
            "kalau mau bulk (mis. 39353,1655,20481). Kirim 1 id -> cuma 1 "
            "outlet diproses. Sama seperti GET /odoo/order-history-by-customer, "
            "ini id Odoo MENTAH, BUKAN external_code."
        ),
    ),
    lookback_limit: int | None = Query(
        default=None,
        ge=1,
        le=500,
        description=(
            "OPSIONAL -- berapa banyak order TERBARU per customer yang di-scan "
            "buat cari 1 yang invoice_status masuk daftar eligible (\"to invoice\" "
            "atau \"invoiced\", lihat ELIGIBLE_INVOICE_STATUSES di service). "
            "Default 50. Perbesar kalau outlet tertentu tidak ketemu order yang "
            "cocok dalam 50 order terbarunya."
        ),
    ),
    salesman_external_code: str | None = Query(
        default=None,
        description=(
            "OPSIONAL -- override external_code Salesman utk SEMUA order di "
            "panggilan ini (default: constant SALESMAN_EXTERNAL_CODE di service, "
            "\"202600002\"). Berguna buat testing kode salesman lain (mis. "
            "\"SALES-DUMMY-DEV\", \"202600003\", \"202600004\") tanpa ubah kode."
        ),
    ),
    dry_run: bool = Query(
        default=False,
        description=(
            "OPSIONAL -- kalau True, endpoint TIDAK push apa pun ke eSuite. "
            "Cuma balikin payload yang AKAN dikirim (field `payload` di "
            "response) supaya bisa di-copy manual buat ditest lewat Postman "
            "atau tool lain. `esuite_response` selalu null saat dry_run=True."
        ),
    ),
):
    """
    v1 (28 Agustus 2026) -- push riwayat order ke webhook eDot BARU
    `POST /v1/webhook/orders/import` (endpoint TERPISAH dari `/sales-order`
    yang sudah ada di Postman collection, lihat project memory
    order_history_import.md utk detail lengkap perbedaan & histori keputusan).

    Scope v1 (PROVISIONAL, bisa di-expand nanti): per outlet/customer,
    HANYA 1 order TERAKHIR yang `invoice_status` masuk `ELIGIBLE_INVOICE_STATUSES`
    (`["to invoice", "invoiced"]` per 28 Agustus 2026, lihat service utk daftar
    terkini) yang dikirim -- BUKAN full history. Kalau 1 customer tidak punya
    order dengan status yang cocok dalam `lookback_limit` order terbarunya,
    customer itu di-skip LOKAL (tidak dikirim ke eSuite sama sekali, muncul di
    `local_skipped` pada response) -- beda dari skip yang dilaporkan eSuite
    sendiri (`esuite_response.data.results[]`, mis. karena product/salesman
    belum ke-resolve).

    Salesman: SEMUA order pakai 1 external_code TETAP (lihat konstanta
    `SALESMAN_EXTERNAL_CODE` di service) -- TIDAK di-mapping presisi ke
    salesperson asli Odoo (dikonfirmasi user, cukup salah satu dari 3 akun
    test real yang dikasih dev, karena visibility order terakhir outlet di
    app eWork tidak digating per-salesperson). Bisa di-override per-call lewat
    query param `salesman_external_code` (mis. buat coba kode lain kalau
    default-nya "not resolved" di eSuite, lihat project memory
    order_history_import.md Test live #3).

    Response HTTP 200 dari endpoint ini TIDAK BERARTI semua order sukses
    ke-import ke eSuite -- WAJIB baca `esuite_response.data.results[]` per
    order (`imported`/`skipped`+`reason`).

    Set `dry_run=true` buat lihat/ambil payload TANPA push ke eSuite -- field
    `payload` di response berisi body persis yang AKAN dikirim, siap
    di-copy-paste ke Postman/tool lain buat testing manual.
    """
    parsed_ids = _parse_customer_ids(customer_ids)
    return service.sync(
        customer_ids=parsed_ids,
        lookback_limit=lookback_limit,
        salesman_external_code=salesman_external_code,
        dry_run=dry_run,
    )
