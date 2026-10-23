import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import AppError, ValidationError
from app.core.sync_logger import log_sync_result

# company_external_id -- id perusahaan Cahaya Boga Utama di eSuite. Dev eDot
# konfirmasi LANGSUNG (28 Agustus 2026) ini sudah "disesuaikan dev dengan data
# Cahaya Boga" -- bukan dummy ilustratif seperti "ODOO-CUST-42"/"ODOO-EMP-7"
# di contoh payload yang sama (lihat order_history_import.md, klarifikasi
# poin 4). Fixed value sama utk semua order, pola sama dengan CURRENCY di
# customer_sync_service.py (konstanta wajib, bukan hasil resolve dari Odoo).
# REVISI 7 September 2026 -- dev eDot konfirmasi LANGSUNG id ini berubah dari
# "9001065" ke "5120317" (root cause belum dijelaskan dev, kemungkinan sama
# dgn kasus currency/uom-level: id master data eSuite ternyata bisa berubah
# per environment/waktu -- lihat esuite_prod_cutover.md). Constant ini BELUM
# ter-cover endpoint GET /api/debug/verify-reference-constants (lihat
# debug.py) -- kalau eSuite ada entity_path utk company/organization,
# pertimbangkan ditambahkan ke situ juga supaya perubahan berikutnya ketahuan
# otomatis, bukan nunggu laporan manual dev lagi.
COMPANY_EXTERNAL_ID = "5120317"

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

# Salesman -- v1 pakai 1 kode TETAP utk SEMUA order (user konfirmasi 28
# Agustus 2026: TIDAK PERLU mapping presisi ke sale.order.user_id/salesperson
# asli Odoo -- "siapapun sales yang visit outlet akan dapat order terakhir
# yang sama"). sync()/_to_order_payload() terima salesman_external_code sbg
# parameter OPSIONAL (override per-call, 29 Agustus 2026); constant ini cuma
# DEFAULT kalau parameter itu tidak diisi.
#
# 7 September 2026 -- ROOT CAUSE "salesman not resolved" DITEMUKAN & FIXED:
# field ini WAJIB diisi `external_code` ASLI akun Salesman di eSuite, BUKAN
# `employee_id` ("Org employee id", field TERPISAH di skema POST /salesman).
# Kode "2026000xx" yang dev kasih 28 Agustus itu employee_id, BUKAN
# external_code -- makanya SELALU "not resolved" walau akunnya valid/aktif/
# sudah di-mapping ke customer (dibuktikan lewat customer-sales mapping &
# stock yang jalan normal pakai employee_id yang sama). Dev CONFIRM langsung
# 7 September: external_code asli utk employee_id "202600003" ("Sales
# Testing", branch Sunshine Food and Co) = "SALES-DUMMY-DEV" -- TERBUKTI
# LIVE 3/3 order imported (2 test terpisah: lewat endpoint kita & langsung
# Postman ke eSuite, hasil identik -- konfirmasi bug BUKAN di kode/payload
# kita). Value lama "202600002" DIGANTI ke value yang benar ini.
#
# ⚠️ BELUM diverifikasi utk branch CBU/SAP (baru ditest utk branch Sunshine
# Food) -- cek dulu sebelum full rollout lintas branch, lihat
# order_history_import.md section 7 September.
#
# 🔧 10 September 2026 (malam) -- DIGANTI ke "SALES-TESTING-001", value LAMA
# "SALES-DUMMY-DEV" SUDAH BASI (tidak valid lagi di sisi eSuite/eDot -- info
# user langsung, bukan hasil investigasi kode). Konteks: dev CONFIRM menu
# "Order Tracking" eDot difilter per-salesman yang SEDANG LOGIN (lihat
# order_history_import.md, section paling atas) -- fitur custom utk lepas
# dari batasan ini perlu BIAYA TAMBAHAN, jadi utk sekarang TETAP pakai 1 kode
# tetap apa adanya (keputusan lama TIDAK berubah). Tujuan value baru ini
# MURNI supaya salah satu dari 4 akun sales test bisa login & benar-benar
# melihat order-order ini di Order Tracking-nya, buat bahan DEMO ke
# management -- kalau management memang perlu fitur custom (lihat ide
# "salesman asli per outlet" yang sengaja BELUM dikerjakan di section atas
# file order_history_import.md), demo ini jadi acuan arahnya lebih jelas.
# BUKAN keputusan arsitektur baru -- cuma ganti VALUE dummy, mekanisme "1
# kode tetap utk semua order" TIDAK berubah.
SALESMAN_EXTERNAL_CODE = "SALES-TESTING-001"

# Filter scope (28 Agustus 2026, field Odoo sale.order.invoice_status --
# selection standar: upselling/invoiced/to invoice/no): per outlet, kirim
# SEMUA order dengan invoice_status TERMASUK di list ini (dalam window
# lookback_limit, lihat DEFAULT_LOOKBACK_LIMIT di bawah). Awalnya cuma
# "to invoice" -- DIREVISI 28 Agustus 2026 jadi list, krn "to invoice" adalah
# status TRANSIT (barang terkirim, invoice belum dibuat) yang cepat berubah
# jadi "invoiced" begitu tagihan selesai dibuat. List ini SENGAJA dibuat
# extensible -- tambah status baru di sini kalau user minta lagi nanti.
#
# REVISI SCOPE 7 September 2026 (dikonfirmasi eksplisit user via
# AskUserQuestion, MENGGANTI decision lama "1 order terakhir/outlet"):
# team sales butuh LEBIH DARI 1 order historis per outlet -- goal-nya sales
# bisa lihat apa saja yang pernah diorder outlet itu lewat filter-by-outlet
# di app mobile eDot (SUDAH confirmed jalan di sandbox). Scope BARU: SEMUA
# order eligible dalam lookback_limit dikirim, BUKAN cuma yang terakhir.
# Lihat order_history_import.md utk kronologi keputusan lama vs baru.
ELIGIBLE_INVOICE_STATUSES = ["to invoice", "invoiced"]

# Berapa banyak order TERBARU per customer yang DI-SCAN dari Odoo (dari
# get_order_history_by_customer(), sudah date_order desc, jadi ini window
# "N order paling baru" yang DICARI) -- MURNI search window, BUKAN jumlah
# yang dikirim (lihat DEFAULT_MAX_ORDERS_PER_CUSTOMER di bawah utk itu).
# Perbesar param ini di endpoint kalau outlet tertentu perlu dicari lebih
# jauh ke belakang utk nemuin order eligible (mis. outlet jarang order).
DEFAULT_LOOKBACK_LIMIT = 50

# 🔧 10 September 2026 -- REVISI keputusan scope 7 September ("SEMUA order
# eligible dalam lookback_limit dikirim"). Diskusi ulang dgn user: app
# eDot/Salesforce fokusnya "quick look" (kapan terakhir outlet order --
# eSuite sendiri cuma nampilin "last order X days ago", bukan daftar
# histori), BUKAN arsip lengkap -- histori lengkap tetap sumbernya Odoo,
# bridge ini TIDAK sedang "memindahkan Odoo ke eSuite". Jadi dipisah jadi
# 2 dial independen: lookback_limit (search window, di atas, TIDAK
# berubah) vs param BARU max_orders_per_customer (dari `matches` yang
# eligible, SLICE ke N TERATAS -- matches sudah date_order desc, jadi N
# teratas = N TERBARU) -- INI yang menentukan jumlah TERKIRIM.
#
# Default = 1 (utk mode mass "semua customer" -- keputusan eksplisit user:
# "untuk mass upsert aku rasa 1 cukup"). TETAP bisa di-override MANUAL per
# panggilan (`customer_ids` diisi spesifik + `max_orders_per_customer`
# lebih besar, mis. 5/10) utk kasus tertentu yang butuh histori lebih
# dalam -- keputusan ADA DI HUMAN yang manggil, BUKAN hardcode berbeda
# per mode (parameter SAMA dipakai kedua mode, cuma defaultnya yang aman).
#
# ⚠️ Filter ELIGIBLE_INVOICE_STATUSES (di atas) SENGAJA TIDAK disentuh di
# revisi ini (user: "kondisi hanya complete order pun aku rasa masih akan
# jadi pembahasan nantinya... tapi untuk fase 1 cukup, jangan overengineering
# dulu") -- kemungkinan didiskusikan ulang di fase berikutnya, BUKAN scope
# perubahan ini.
DEFAULT_MAX_ORDERS_PER_CUSTOMER = 1

CURRENCY = "IDR"  # string literal, BUKAN object -- beda dari field currency di endpoint /sales-order lama

# Batching (7 September 2026, BARU) -- dev eDot konfirmasi (jawaban #7)
# batas eSuite 100 order/request. Sebelumnya endpoint ini kirim SEMUA order
# dalam 1 push_raw() call. PENTING sejak revisi scope 7 September (lihat
# komentar ELIGIBLE_INVOICE_STATUSES): 1 customer_id sekarang BISA
# menghasilkan LEBIH dari 1 order, jadi jumlah order != jumlah customer_id
# -- caller TIDAK BOLEH asumsikan "<=100 customer_id aman", karena outlet
# dengan banyak histori bisa sendirian menghasilkan puluhan order. Chunking
# di bawah beroperasi di level ORDER (bukan customer_id) justru karena ini.
# Behavior exact eSuite kalau limit 100/request dilanggar belum diverifikasi
# (reject semua? truncate diam-diam?), jadi jangan coba-coba pas-pasan.
MAX_ORDERS_PER_REQUEST = 100
DEFAULT_BATCH_SIZE = MAX_ORDERS_PER_REQUEST

# Jeda antar batch (detik) -- BUKAN utk rate limit BRIDGE KITA SENDIRI
# (limiter di core/limiter.py cuma berlaku ke request MASUK dari client ke
# bridge, TIDAK berlaku ke panggilan KELUAR bridge->eSuite di loop batch
# ini, lihat security_audit.md). Ini murni jaga-jaga skala besar ke eSuite
# -- belum ada dokumentasi resmi rate limit eSuite utk endpoint ini. Angka
# konservatif, sesuaikan kalau ternyata kelamaan/masih kena limit di sisi
# eSuite.
BATCH_DELAY_SECONDS = 1.0

# Prefix external_code Branch -- SAMA PERSIS dgn branch_sync_service.py
# ("ODOO-COMPANY-{res.company id}", Branch eSuite = res.company Odoo).
# Didefinisikan ULANG di sini (bukan cross-import), konsisten convention
# project "tiap service independen". Field "branch" di payload orders/import
# BARU diminta dev eDot 29 Agustus 2026 (sebelumnya tidak ada di skema).
BRANCH_EXTERNAL_CODE_PREFIX = "ODOO-COMPANY-"

# 29 Agustus 2026: dev eDot minta order_date format RFC3339 dgn offset
# eksplisit (mis. "2026-08-13T08:58:37+07:00"), BUKAN string mentah Odoo yg
# sebelumnya di-passthrough apa adanya ("2026-08-13 08:58:37" -- tanpa "T",
# tanpa offset). Odoo defaultnya SIMPAN datetime dalam UTC naive (konvensi
# standar Odoo, company_id/user tidak mengubah cara PENYIMPANAN, cuma
# TAMPILAN di UI) -- ASUMSI ini BELUM eksplisit dikonfirmasi user/dicek ke
# instance Odoo CBU, tapi ini default Odoo yg berlaku hampir selalu kecuali
# di-override eksplisit. Kalau ternyata instance ini beda, cuma perlu ganti
# SOURCE_TIMEZONE di bawah (bukan ubah logic konversi).
SOURCE_TIMEZONE = timezone.utc
TARGET_TIMEZONE = ZoneInfo("Asia/Jakarta")  # WIB, fixed +07:00, tidak ada DST


class OrderHistorySyncService:
    """
    v1 (28 Agustus 2026) -- push riwayat order ke webhook eDot
    POST /v1/webhook/orders/import (endpoint TERPISAH dari POST /sales-order
    yang sudah ada di Postman collection -- lihat order_history_import.md
    utk detail perbedaannya).

    Scope 🔧 DIREVISI 10 September 2026 (menggantikan keputusan 7 September
    "SEMUA order eligible dalam lookback_limit dikirim"): per outlet/
    customer, kirim `max_orders_per_customer` order TERBARU (default 1)
    yang invoice_status masuk ELIGIBLE_INVOICE_STATUSES -- BUKAN lagi
    "semua yang eligible". Alasan: app eDot/Salesforce fokusnya "quick
    look" (kapan terakhir outlet order), bukan arsip lengkap -- histori
    lengkap tetap dilihat dari Odoo langsung. `max_orders_per_customer`
    tetap bisa di-override manual per panggilan (mis. sync 1 customer
    spesifik dgn N lebih besar) -- lihat komentar DEFAULT_MAX_ORDERS_PER_
    CUSTOMER di atas file ini utk detail lengkap.

    Terima 1 ATAU BANYAK customer_id sekaligus (kirim 1 -> cuma 1 yang
    diproses) -- desain diminta user 28 Agustus 2026 supaya endpoint yang
    sama bisa dipakai baik utk 1 outlet spesifik maupun bulk beberapa
    outlet, tanpa 2 endpoint terpisah.
    """

    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(
        self,
        customer_ids: list[int],
        lookback_limit: int | None = None,
        max_orders_per_customer: int | None = None,
        salesman_external_code: str | None = None,
        dry_run: bool = False,
        batch_size: int | None = None,
        include_payload: bool = False,
    ) -> dict:
        if not customer_ids:
            raise ValidationError("customer_ids tidak boleh kosong")

        lookback_limit = lookback_limit or DEFAULT_LOOKBACK_LIMIT
        # 🔧 10 September 2026 -- lihat komentar DEFAULT_MAX_ORDERS_PER_CUSTOMER
        # di atas file ini. Dial TERPISAH dari lookback_limit (search window).
        resolved_max_orders = max_orders_per_customer or DEFAULT_MAX_ORDERS_PER_CUSTOMER
        # Override manual per-call (mis. buat testing kode salesman lain) --
        # default tetap SALESMAN_EXTERNAL_CODE kalau tidak diisi caller.
        resolved_salesman_code = salesman_external_code or SALESMAN_EXTERNAL_CODE
        # Batas atas HARD dari eSuite (100/request) -- caller boleh minta
        # lebih kecil (mis. batch_size=20 buat sample bertahap), TIDAK
        # PERNAH lebih besar dari MAX_ORDERS_PER_REQUEST walau diminta.
        resolved_batch_size = min(batch_size or DEFAULT_BATCH_SIZE, MAX_ORDERS_PER_REQUEST)

        orders_payload = []
        local_skipped = []  # customer yang TIDAK ketemu order "to invoice" -- tidak sempat dikirim ke eSuite sama sekali

        for customer_id in customer_ids:
            orders = self.odoo.get_order_history_by_customer(customer_id, limit=lookback_limit)
            # 🔧 10 September 2026 -- REVISI 7 September ("SEMUA order match
            # ikut dikirim") DIGANTI lagi: SLICE ke `resolved_max_orders`
            # TERATAS (orders sudah date_order desc dari Odoo, jadi N
            # teratas = N TERBARU) -- lihat komentar DEFAULT_MAX_ORDERS_PER_
            # CUSTOMER di atas file ini utk alasan lengkap.
            matches = [o for o in orders if o.get("invoice_status") in ELIGIBLE_INVOICE_STATUSES][:resolved_max_orders]
            if not matches:
                eligible_str = "/".join(ELIGIBLE_INVOICE_STATUSES)
                # customer_name (🆕 10 September 2026, permintaan user) --
                # ambil dari order APA SAJA milik customer ini kalau ada
                # (field partner_id sudah ikut ditarik get_order_history_by_
                # customer(), TANPA call tambahan) -- kalau customer ini
                # benar-benar 0 order sama sekali, tetap None (tidak ada
                # sumber nama dari Odoo di titik ini).
                customer_name = None
                if orders:
                    partner_field = orders[0].get("partner_id")
                    if partner_field:
                        customer_name = partner_field[1]
                local_skipped.append({
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                    "reason": (
                        f"tidak ada order dengan invoice_status in [{eligible_str}] "
                        f"dalam {lookback_limit} order terbaru customer ini"
                    ),
                })
                continue

            for match in matches:
                # 🆕 10 September 2026 -- SEBELUMNYA: 1 order gagal validasi (mis.
                # quantity pecahan produk kg, UOM tidak dikenal, dll di
                # _to_order_payload()) bikin ValidationError PROPAGATE keluar
                # loop ini, meng-crash SELURUH sync() call -- customer LAIN yang
                # belum sempat diproses ikut gagal total. Makin berisiko sejak
                # mode "semua customer" ada (POST /sync/order-history tanpa
                # customer_ids) krn makin banyak customer = makin besar peluang
                # 1 order kena kasus ini. Keputusan user 10 September 2026: skip
                # order yang gagal SAJA (dicatat di local_skipped utk diaudit),
                # customer & order lain TETAP lanjut diproses & terkirim normal.
                try:
                    orders_payload.append(self._to_order_payload(match, customer_id, resolved_salesman_code))
                except ValidationError as e:
                    # customer_name/order_name (🆕 10 September 2026,
                    # permintaan user -- log yang gagal WAJIB sertakan nomor
                    # SO + nama customer + id customer, biar gampang
                    # ditindaklanjuti manual) -- keduanya sudah ada di
                    # `match` (dari get_order_history_by_customer()), TANPA
                    # perlu call tambahan ke Odoo.
                    partner_field = match.get("partner_id") or [None, None]
                    local_skipped.append({
                        "customer_id": customer_id,
                        "customer_name": partner_field[1],
                        "order_id": match.get("id"),
                        "order_name": match.get("name"),
                        "reason": e.message,
                        "error": e.to_dict()["error"],
                    })

        # Payload PREVIEW (dry_run) -- SEMUA order jadi 1 payload utuh, TIDAK
        # di-chunk (dry_run cuma menampilkan, tidak pernah push), jadi caller
        # bisa lihat keseluruhan sekaligus. Push beneran di bawah TETAP
        # di-chunk per resolved_batch_size, terpisah dari preview ini.
        preview_payload = {"company_external_id": COMPANY_EXTERNAL_ID, "orders": orders_payload}

        result = {
            "company_external_id": COMPANY_EXTERNAL_ID,
            "requested_count": len(customer_ids),
            "sent_count": len(orders_payload),
            "local_skipped": local_skipped,
            "dry_run": dry_run,
            # Batch info -- SELALU diisi (dry_run maupun tidak) supaya
            # caller bisa cek dulu berapa batch yang akan kepakai SEBELUM
            # push beneran (7 September 2026, BARU).
            "batch_size": resolved_batch_size,
            "batch_count": (
                (len(orders_payload) + resolved_batch_size - 1) // resolved_batch_size
                if orders_payload else 0
            ),
            # Cuma diisi kalau dry_run=True ATAU caller EKSPLISIT minta lewat
            # include_payload=True (🆕 10 September 2026 -- kebutuhan verifikasi
            # payload ASLI yang terkirim di push BENERAN, mis. cek
            # salesman/branch/customer external_code apa yang sebenarnya
            # dikirim, tanpa perlu ulang panggil dry_run terpisah). Default
            # False -- behavior lama (payload null di luar dry_run) TIDAK
            # berubah kalau param ini tidak diisi. Lihat order_history_import.md.
            "payload": preview_payload if (dry_run or include_payload) else None,
            "esuite_response": None,
        }

        if dry_run:
            # Caller cuma minta preview payload, SENGAJA tidak push ke eSuite.
            return result

        if not orders_payload:
            # Tidak ada 1 pun customer yang match filter -- tidak perlu
            # panggil eSuite sama sekali (hindari push {"orders": []} kosong).
            return result

        # Chunk orders_payload jadi beberapa batch, push 1 batch/call (7
        # September 2026, BARU -- lihat komentar MAX_ORDERS_PER_REQUEST di
        # atas). Tiap batch di-try/except TERPISAH (pola SAMA PERSIS
        # mass_customer_sales_mapping_service.py::map_all_to_one_salesman())
        # -- 1 batch gagal (mis. network error) TIDAK menghentikan batch
        # lain. Hasil per-order (data.summary/data.results[]) DIGABUNG jadi
        # 1 shape yang SAMA seperti response lama (single-call) supaya
        # konsumen existing (dev instruksi: WAJIB parse data.results[] per
        # order) TIDAK perlu berubah -- info batch tambahan taruh di field
        # BARU (batches[]), bukan gantikan struktur lama.
        batches = [
            orders_payload[i : i + resolved_batch_size]
            for i in range(0, len(orders_payload), resolved_batch_size)
        ]

        combined_results = []
        combined_summary = {"received": 0, "imported": 0, "skipped": 0, "errored": 0}
        batch_reports = []
        any_batch_failed = False

        for idx, batch in enumerate(batches, start=1):
            batch_payload = {"company_external_id": COMPANY_EXTERNAL_ID, "orders": batch}
            try:
                response = self.esuite.push_raw("orders/import", batch_payload)
                batch_summary = ((response or {}).get("data") or {}).get("summary") or {}
                batch_results = ((response or {}).get("data") or {}).get("results") or []
                combined_results.extend(batch_results)
                for key in combined_summary:
                    combined_summary[key] += batch_summary.get(key) or 0
                batch_reports.append({
                    "batch": idx,
                    "size": len(batch),
                    "status": "success",
                    "external_ids": [o["external_id"] for o in batch],
                })
            except AppError as e:
                # Sengaja di-catch PER BATCH (bukan biar propagate) -- batch
                # lain tetap lanjut. Order di batch ini TIDAK masuk
                # combined_results (beda dari "skipped" yang eSuite laporkan
                # -- ini kegagalan CALL-nya sendiri, mis. network/5xx), jadi
                # combined_summary["errored"] dihitung manual dari size batch
                # ini supaya total tetap masuk akal.
                any_batch_failed = True
                combined_summary["errored"] += len(batch)
                batch_reports.append({
                    "batch": idx,
                    "size": len(batch),
                    "status": "failed",
                    "external_ids": [o["external_id"] for o in batch],
                    "error": e.to_dict()["error"],
                })

            # Jeda antar batch (BUKAN setelah batch TERAKHIR) -- lihat
            # komentar BATCH_DELAY_SECONDS di atas.
            if idx < len(batches):
                time.sleep(BATCH_DELAY_SECONDS)

        result["esuite_response"] = {
            "status": 200 if not any_batch_failed else 207,  # 207-style: sebagian batch gagal di level CALL (bukan status eSuite asli, cuma penanda lokal)
            "message": "Success" if not any_batch_failed else "Sebagian batch gagal -- cek field batches[]",
            "data": {"summary": combined_summary, "results": combined_results},
        }
        result["batches"] = batch_reports

        # data.summary/data.results[] -- WAJIB dibaca per-order, HTTP 200
        # dari endpoint ini TIDAK BERARTI semua order ke-import (dev eDot,
        # jawaban pertanyaan #1, lihat order_history_import.md).
        log_sync_result(
            "order_history",
            "import",
            {
                "total_matched_in_odoo": len(customer_ids),
                "synced_count": combined_summary.get("imported"),
                "failed_count": (combined_summary.get("skipped") or 0) + (combined_summary.get("errored") or 0),
            },
            note=(
                f"orders/import -- max {resolved_max_orders} order terbaru/outlet "
                f"(revisi scope 10 Sep 2026), invoice_status in {ELIGIBLE_INVOICE_STATUSES}, "
                f"lookback {lookback_limit}, "
                f"{len(local_skipped)} customer di-skip lokal (tidak ada order match), "
                f"{len(batches)} batch @ max {resolved_batch_size} order/batch"
            ),
        )

        return result

    def _format_order_date_rfc3339(self, date_order_raw: str, order_id) -> str:
        """
        Convert string date_order MENTAH dari Odoo ("YYYY-MM-DD HH:MM:SS",
        naive, ASUMSI UTC -- lihat komentar SOURCE_TIMEZONE di atas) jadi
        RFC3339 dgn offset eksplisit WIB (mis. "2026-08-13T15:58:37+07:00").
        Diminta dev eDot 29 Agustus 2026 -- sebelumnya field ini di-passthrough
        mentah apa adanya (lihat order_history_import.md Test live #3, format
        lama TIDAK bikin error parsing tapi belum pasti benar secara semantik).
        """
        if not date_order_raw:
            raise ValidationError(
                f"order_date kosong dari Odoo -- order id {order_id}",
                details={"order_id": order_id},
            )
        try:
            naive = datetime.strptime(date_order_raw, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise ValidationError(
                f"order_date '{date_order_raw}' bukan format 'YYYY-MM-DD HH:MM:SS' yang diharapkan dari Odoo -- order id {order_id}",
                details={"date_order_raw": date_order_raw, "order_id": order_id},
            ) from exc

        as_source_tz = naive.replace(tzinfo=SOURCE_TIMEZONE)
        as_target_tz = as_source_tz.astimezone(TARGET_TIMEZONE)
        return as_target_tz.isoformat(timespec="seconds")

    def _resolve_branch_external_code(self, order: dict, customer_id: int) -> str:
        """
        Field "branch" -- BARU diminta dev eDot 29 Agustus 2026 (sebelumnya
        tidak ada di skema payload orders/import yang sudah di-cross-check).
        Sumbernya sale.order.company_id (Many2one res.company, format
        [id, display_name]) -- SAMA persis dgn entity Branch eSuite yang
        sudah dipush lewat branch_sync_service.py (Branch = res.company).
        """
        company_field = order.get("company_id")
        if not company_field:
            raise ValidationError(
                f"sale.order.company_id kosong -- tidak bisa bentuk field 'branch', "
                f"order id {order.get('id')}, customer {customer_id}",
                details={"order_id": order.get("id"), "customer_id": customer_id},
            )
        return f"{BRANCH_EXTERNAL_CODE_PREFIX}{company_field[0]}"

    def _to_order_payload(self, order: dict, customer_id: int, salesman_external_code: str) -> dict:
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

            # eSuite orders/import (Go backend) WAJIB quantity = integer
            # (struct field int64) -- ditemukan live 28 Agustus 2026: Odoo
            # product_uom_qty selalu Python float (mis. 2.0), json.dumps()
            # menulis "2.0", eSuite REJECT dgn error "cannot unmarshal number
            # 2.0 into ... type int64". Fix: cast ke int eksplisit -- TAPI
            # kalau qty punya pecahan beneran (mis. 2.5 kg), jangan diam-diam
            # dibulatkan/dipotong (bisa keliru datanya) -- raise error jelas
            # supaya ketahuan, bukan silently truncate.
            qty_raw = line.get("product_uom_qty")
            qty_int = int(qty_raw) if qty_raw is not None else None
            if qty_int is None or float(qty_raw) != qty_int:
                raise ValidationError(
                    f"quantity order line '{qty_raw}' bukan bilangan bulat -- "
                    f"eSuite orders/import cuma terima quantity integer (Go int64), "
                    f"order id {order.get('id')}, customer {customer_id}",
                    details={"quantity_raw": qty_raw, "order_id": order.get("id")},
                )

            items.append({
                "product_external_code": f"{PRODUCT_EXTERNAL_CODE_PREFIX}{product[0]}",
                "name": line.get("name"),
                "quantity": qty_int,
                "uom": uom_value,
                "unit_price": line.get("price_unit"),
                "discount": 0,  # non-priority v1, instruksi user 28 Agustus 2026
                "tax": line.get("price_tax"),
                "subtotal": line.get("price_subtotal"),
            })

        return {
            "external_id": f"{ORDER_EXTERNAL_ID_PREFIX}{order.get('id')}",
            "order_number": order.get("name"),
            "order_date": self._format_order_date_rfc3339(order.get("date_order"), order.get("id")),
            "status": "completed",  # hardcode, dikonfirmasi dev (jawaban #2)
            "customer": {"external_code": f"{CUSTOMER_EXTERNAL_CODE_PREFIX}{customer_id}"},
            "branch": {"external_code": self._resolve_branch_external_code(order, customer_id)},
            "salesman": {"external_code": salesman_external_code},
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
