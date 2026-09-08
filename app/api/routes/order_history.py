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
            "OPSIONAL -- berapa banyak order TERBARU per customer yang di-scan. "
            "SEMUA order di dalam window ini yang invoice_status masuk daftar "
            "eligible (\"to invoice\" atau \"invoiced\", lihat "
            "ELIGIBLE_INVOICE_STATUSES di service) ikut DIKIRIM (bukan cuma 1, "
            "direvisi 7 September 2026 -- 1 outlet lama bisa hasilkan banyak "
            "order sekaligus). Default 50. Perbesar kalau butuh histori lebih "
            "jauh ke belakang per outlet."
        ),
    ),
    salesman_external_code: str | None = Query(
        default=None,
        description=(
            "OPSIONAL -- override external_code Salesman utk SEMUA order di "
            "panggilan ini (default: constant SALESMAN_EXTERNAL_CODE di service, "
            "\"SALES-DUMMY-DEV\"). PENTING (7 September 2026): ini WAJIB "
            "external_code ASLI akun Salesman di eSuite, BUKAN employee_id "
            "(\"2026000xx\") -- 2 field terpisah, kirim employee_id di sini "
            "SELALU \"not resolved\" walau akunnya valid/aktif."
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
    batch_size: int | None = Query(
        default=None,
        ge=1,
        le=100,
        description=(
            "OPSIONAL -- berapa order per-call ke eSuite (batas HARD eSuite: "
            "100/request, dev jawaban #7). Default 100. Perkecil (mis. 20) "
            "buat rollout bertahap/sample dulu sebelum full batch. Endpoint "
            "ini OTOMATIS chunk & push berkali-kali kalau order yang cocok "
            "lebih banyak dari batch_size -- caller TIDAK PERLU manual bagi "
            "customer_ids sendiri. Ada jeda antar batch (lihat "
            "BATCH_DELAY_SECONDS di service) -- response `batch_count` bisa "
            "dicek dulu lewat dry_run=true sebelum push beneran."
        ),
    ),
):
    """
    v1 (28 Agustus 2026) -- push riwayat order ke webhook eDot BARU
    `POST /v1/webhook/orders/import` (endpoint TERPISAH dari `/sales-order`
    yang sudah ada di Postman collection, lihat project memory
    order_history_import.md utk detail lengkap perbedaan & histori keputusan).

    Scope (DIREVISI 7 September 2026, sesuai kebutuhan tim sales -- lihat
    project memory order_history_import.md): per outlet/customer, SEMUA order
    yang `invoice_status` masuk `ELIGIBLE_INVOICE_STATUSES`
    (`["to invoice", "invoiced"]` per 28 Agustus 2026, lihat service utk daftar
    terkini) DALAM WINDOW `lookback_limit` dikirim -- BUKAN cuma 1 order
    terakhir seperti versi awal. Tujuannya sales bisa lihat riwayat order
    outlet lewat filter-by-outlet di app mobile eDot. Kalau 1 customer tidak
    punya SATU PUN order dengan status yang cocok dalam `lookback_limit` order
    terbarunya, customer itu di-skip LOKAL (tidak dikirim ke eSuite sama
    sekali, muncul di `local_skipped` pada response) -- beda dari skip yang
    dilaporkan eSuite sendiri (`esuite_response.data.results[]`, mis. karena
    product/salesman belum ke-resolve).

    Salesman: SEMUA order pakai 1 external_code TETAP (lihat konstanta
    `SALESMAN_EXTERNAL_CODE` di service) -- TIDAK di-mapping presisi ke
    salesperson asli Odoo (dikonfirmasi user, karena visibility order terakhir
    outlet di app eWork tidak digating per-salesperson). Bisa di-override
    per-call lewat query param `salesman_external_code` -- WAJIB external_code
    ASLI akun (bukan employee_id, lihat project memory order_history_import.md
    section 7 September 2026 utk root cause lengkap).

    Response HTTP 200 dari endpoint ini TIDAK BERARTI semua order sukses
    ke-import ke eSuite -- WAJIB baca `esuite_response.data.results[]` per
    order (`imported`/`skipped`+`reason`).

    Batching (7 September 2026, BARU): kalau jumlah order yang cocok lebih
    banyak dari `batch_size` (default/max 100, batas eSuite), endpoint ini
    OTOMATIS chunk & push berkali-kali (dgn jeda antar batch) -- caller
    TIDAK PERLU bagi `customer_ids` manual. `esuite_response.data.summary`/
    `.results[]` tetap 1 shape gabungan dari SEMUA batch (kompatibel dgn
    consumer lama); detail per-batch (termasuk batch yang gagal di level
    call, bukan skip eSuite) ada di field baru `batches[]`.

    Set `dry_run=true` buat lihat/ambil payload TANPA push ke eSuite -- field
    `payload` di response berisi body persis yang AKAN dikirim, siap
    di-copy-paste ke Postman/tool lain buat testing manual. Field `batch_count`
    ikut muncul di dry_run supaya bisa cek dulu berapa batch yang akan
    dipakai sebelum push beneran.
    """
    parsed_ids = _parse_customer_ids(customer_ids)
    return service.sync(
        customer_ids=parsed_ids,
        lookback_limit=lookback_limit,
        salesman_external_code=salesman_external_code,
        dry_run=dry_run,
        batch_size=batch_size,
    )
