from fastapi import APIRouter, Query

from app.core.exceptions import ValidationError
from app.core.sync_logger import read_latest_customer_upsert_csv
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
    customer_ids: str | None = Query(
        default=None,
        description=(
            "id Odoo res.partner (Customer/Outlet), comma-separated kalau "
            "mau bulk (mis. 39353,1655,20481). Kirim 1 id -> cuma 1 outlet "
            "diproses. Sama seperti GET /odoo/order-history-by-customer, ini "
            "id Odoo MENTAH, BUKAN external_code. ð 10 September 2026 -- "
            "KOSONGKAN param ini utk proses SEMUA customer sekaligus "
            "(customer_rank > 0, active=True, filter SAMA dgn /sync/customers "
            "tanpa external_codes/names) -- TIDAK perlu lagi comma-separated "
            "manual semua id kalau maksudnya memang \"semua\". Disarankan "
            "coba dry_run=true dulu sebelum push beneran krn scope-nya besar."
        ),
    ),
    lookback_limit: int | None = Query(
        default=None,
        ge=1,
        le=500,
        description=(
            "OPSIONAL -- berapa banyak order TERBARU per customer yang "
            "DI-SCAN (search window mencari yang eligible, invoice_status "
            "\"to invoice\"/\"invoiced\" -- lihat ELIGIBLE_INVOICE_STATUSES "
            "di service). 🔧 10 September 2026: param ini TIDAK LAGI "
            "menentukan berapa yang DIKIRIM (lihat max_orders_per_customer "
            "di bawah utk itu) -- murni seberapa jauh ke belakang dicari. "
            "Default 50. Perbesar kalau outlet tertentu jarang order jadi "
            "susah nemu yang eligible dalam window default."
        ),
    ),
    max_orders_per_customer: int | None = Query(
        default=None,
        ge=1,
        description=(
            "🆕 10 September 2026 -- berapa order TERBARU per customer yang "
            "BENERAN DIKIRIM (dari hasil eligible di dalam lookback_limit, "
            "sudah diurutkan date_order desc -- jadi N teratas = N TERBARU). "
            "Default 1 (keputusan user: mode mass \"semua customer\" cukup "
            "1 order/outlet -- app eDot/Salesforce fokus \"quick look\" "
            "kapan terakhir order, BUKAN arsip lengkap, histori penuh tetap "
            "dilihat dari Odoo). Naikkan MANUAL (mis. 5, 10) kalau memang "
            "perlu histori lebih dalam utk customer_ids tertentu yang "
            "disebut eksplisit -- keputusan ada di pemanggil, bukan hardcode "
            "beda per mode."
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
    use_upsert_csv: bool = Query(
        default=False,
        description=(
            "🆕 10 September 2026 -- HANYA berlaku kalau `customer_ids` "
            "DIKOSONGKAN (mode mass). Kalau True, customer yang diproses "
            "BUKAN semua customer Odoo, tapi HANYA customer_id yang "
            "berstatus 'success' di file upsert_customer_*.csv TERBARU "
            "(hasil POST /sync/customers) -- jalankan /sync/customers dulu "
            "(full, tanpa limit kecil) supaya file-nya ada. Tujuan: hindari "
            "kirim order utk customer yang belum sukses di-upsert ke eSuite "
            "(mayoritas skip eSuite selama ini = 'customer ... not "
            "resolved'). ⚠️ Granularity file ini BATCH-LEVEL, bukan "
            "per-customer confirmed dari eSuite -- lihat "
            "customer_sync_progress.md."
        ),
    ),
    upsert_csv_file: str | None = Query(
        default=None,
        description=(
            "OPSIONAL, dipakai bareng use_upsert_csv=true -- file "
            "upsert_customer_*.csv SPESIFIK yang mau dipakai (mis. mau ulang "
            "test dari snapshot lama), BUKAN otomatis yang terbaru. Boleh "
            "kirim NAMA FILE saja (mis. \"upsert_customer_10-09-2026_"
            "03-51-34.csv\") -- otomatis dicari di folder logs/ yang sama "
            "dengan file itu ditulis, TIDAK perlu path lengkap. Path lengkap "
            "(absolute) juga tetap didukung. Diabaikan kalau "
            "use_upsert_csv=false."
        ),
    ),
    include_payload: bool = Query(
        default=False,
        description=(
            "🆕 10 September 2026 -- kalau True, field `payload` di response "
            "TETAP diisi walau dry_run=False (push beneran) -- berisi body "
            "PERSIS yang dikirim ke eSuite (customer/branch/salesman "
            "external_code, items, dst). Default False (behavior lama: "
            "`payload` null kalau bukan dry_run, supaya response tidak "
            "membesar tanpa perlu). Berguna buat verifikasi manual (mis. cek "
            "salesman_external_code mana yang benar-benar terkirim) TANPA "
            "harus panggil ulang pakai dry_run=true terpisah."
        ),
    ),
):
    """
    ⚠️ STATUS 24 September 2026 -- TIDAK DIPAKAI (dipertahankan, belum dihapus).
    Tujuan awal: import order history PRE-EXISTING (di luar eDot) dengan 1
    salesman hardcode SALESMAN_EXTERNAL_CODE="SALES-TESTING-001". Ternyata
    kebutuhan sales sebenarnya = history order PER OUTLET, sedangkan eDot
    baru menyediakan history PER SALES -- jadi hasil import ini tidak
    menjawab kebutuhan. JANGAN dipakai untuk rollout (termasuk Jakarta/SBU)
    sebelum ada keputusan baru.

    v1 (28 Agustus 2026) -- push riwayat order ke webhook eDot BARU
    `POST /v1/webhook/orders/import` (endpoint TERPISAH dari `/sales-order`
    yang sudah ada di Postman collection, lihat project memory
    order_history_import.md utk detail lengkap perbedaan & histori keputusan).

    Scope 🔧 DIREVISI 10 September 2026 (menggantikan keputusan 7 September
    "SEMUA order eligible dalam lookback_limit dikirim" -- lihat project
    memory order_history_import.md utk kronologi lengkap kedua keputusan):
    per outlet/customer, kirim `max_orders_per_customer` order TERBARU
    (default 1) yang `invoice_status` masuk `ELIGIBLE_INVOICE_STATUSES`
    (`["to invoice", "invoiced"]`, lihat service utk daftar terkini) di
    dalam window `lookback_limit`. Alasan revisi: app eDot/Salesforce
    fokusnya "quick look" (kapan terakhir outlet order -- eSuite sendiri
    cuma nampilin "last order X days ago"), BUKAN arsip lengkap -- histori
    lengkap tetap dilihat dari Odoo langsung, bridge ini bukan alat
    "memindahkan Odoo ke eSuite". `max_orders_per_customer` bisa
    di-override manual per panggilan (mis. customer_ids spesifik + N lebih
    besar) kalau memang perlu histori lebih dalam. Kalau 1 customer tidak
    punya SATU PUN order dengan status yang cocok dalam `lookback_limit` order
    terbarunya, customer itu di-skip LOKAL (tidak dikirim ke eSuite sama
    sekali, muncul di `local_skipped` pada response, sudah menyertakan
    `customer_name`/`order_name` sejak 10 September 2026 buat gampang cek
    manual lewat GET /odoo/sales-order) -- beda dari skip yang dilaporkan
    eSuite sendiri (`esuite_response.data.results[]`, mis. karena
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

    🆕 10 September 2026 -- `use_upsert_csv=true` (hanya berlaku kalau
    `customer_ids` dikosongkan): filter mode mass supaya HANYA customer_id
    yang sukses di file `upsert_customer_*.csv` TERBARU (hasil
    POST /sync/customers) yang diproses -- bukan semua customer Odoo.
    Ditambahkan menyusul temuan log 10 September: mayoritas skip eSuite
    ternyata `"customer ... not resolved"` (customer belum sukses
    di-upsert), jadi filter ini menghindari kirim order utk customer yang
    memang belum bisa di-resolve eSuite. Response ikut membawa field baru
    `upsert_csv_source` (path file yang dipakai) kalau opsi ini aktif.

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

    ð 10 September 2026 -- `customer_ids` SEKARANG OPSIONAL: kosongkan
    param ini utk proses SEMUA customer sekaligus (filter customer_rank > 0
    & active=True, via `OdooClient.get_customer_ids()`), TANPA perlu susun
    comma-separated semua id secara manual. Behavior LAMA (isi 1/banyak id
    manual) TIDAK berubah. â ï¸ Scope "semua customer" bisa lumayan besar
    (1 Odoo call per customer_id, sama seperti mode manual -- lihat
    `sync()` di service) -- disarankan `dry_run=true` dulu buat cek
    `batch_count`/`local_skipped` sebelum push beneran.
    """
    # ð 10 September 2026 -- customer_ids sekarang OPSIONAL: kosongkan
    # utk proses SEMUA customer (customer_rank > 0, active=True) via
    # OdooClient.get_customer_ids() (versi ringan get_customers(), cuma
    # narik id -- lihat docstring method itu). Kalau diisi, behavior LAMA
    # (parse comma-separated) TIDAK berubah sama sekali.
    #
    # 🆕 10 September 2026 -- use_upsert_csv HANYA dicek kalau customer_ids
    # kosong (mode mass). Kalau customer_ids diisi manual, itu instruksi
    # EKSPLISIT caller -- use_upsert_csv diabaikan, tidak menimpa pilihan
    # manual. csv_source cuma keisi kalau jalur ini yang dipakai, supaya
    # response bisa kasih tau snapshot file mana yang jadi filter.
    csv_source: str | None = None
    if customer_ids:
        parsed_ids = _parse_customer_ids(customer_ids)
    elif use_upsert_csv:
        parsed_ids, csv_source = read_latest_customer_upsert_csv(upsert_csv_file)
    else:
        parsed_ids = service.odoo.get_customer_ids()

    result = service.sync(
        customer_ids=parsed_ids,
        lookback_limit=lookback_limit,
        max_orders_per_customer=max_orders_per_customer,
        salesman_external_code=salesman_external_code,
        dry_run=dry_run,
        batch_size=batch_size,
        include_payload=include_payload,
    )
    if csv_source:
        result["upsert_csv_source"] = csv_source
    return result
