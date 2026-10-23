from datetime import date, datetime, timedelta
from enum import Enum

from fastapi import APIRouter, Query

from app.core.salesman_slots import SALESMAN_SLOTS, TEST_EMPLOYEE_ID, TEST_USERNAME
from app.services.call_plan_sync_service import MAX_BATCH_SIZE, MAX_RANGE_DAYS, CallPlanSyncService
from app.services.visit_schedule_service import WITA

router = APIRouter()
service = CallPlanSyncService()

# Pilihan slot di Swagger = isi tabel mapping (select box, bisa pilih banyak).
CallPlanSlot = Enum("CallPlanSlot", {s["odoo_slot"]: s["odoo_slot"] for s in SALESMAN_SLOTS}, type=str)


class Periode(str, Enum):
    """16 Oktober 2026 -- pilihan rentang (select box Swagger, tanpa ketik tanggal).
    Dihitung saat request (WITA), bukan saat server start."""
    hari_ini = "hari_ini"
    besok = "besok"
    minggu_ini = "minggu_ini"      # Senin-Minggu minggu berjalan
    minggu_depan = "minggu_depan"  # Senin-Minggu minggu depan


def _periode_range(periode: Periode) -> tuple[date, date]:
    today = datetime.now(WITA).date()
    if periode == Periode.besok:
        return today + timedelta(days=1), today + timedelta(days=1)
    if periode == Periode.minggu_ini:
        monday = today - timedelta(days=today.weekday())
        return monday, monday + timedelta(days=6)
    if periode == Periode.minggu_depan:
        monday = today - timedelta(days=today.weekday()) + timedelta(days=7)
        return monday, monday + timedelta(days=6)
    return today, today


@router.post("/sync/call-plan")
def sync_call_plan(
    slots: list[CallPlanSlot] = Query(
        ...,
        description="WAJIB -- slot Salesperson Odoo (boleh lebih dari 1). Daftar = tabel mapping app/core/salesman_slots.py.",
    ),
    periode: Periode = Query(
        default=Periode.hari_ini,
        description=(
            "Pilihan rentang tanggal (WITA), tanpa ketik. Diabaikan kalau date_from diisi. "
            "minggu_ini / minggu_depan = Senin-Minggu."
        ),
    ),
    date_from: date | None = Query(
        default=None, description="OPSIONAL -- tanggal awal manual, YYYY-MM-DD. Kalau diisi, `periode` diabaikan."
    ),
    date_to: date | None = Query(
        default=None,
        description=f"OPSIONAL -- tanggal akhir manual, YYYY-MM-DD (kosong = sama dgn date_from). Maks {MAX_RANGE_DAYS} hari.",
    ),
    dry_run: bool = Query(
        default=True,
        description="DEFAULT TRUE -- cuma hitung & tampilkan jadwal, TIDAK kirim ke eSuite. Isi false utk kirim.",
    ),
    batch_size: int | None = Query(
        default=None, ge=1, le=MAX_BATCH_SIZE, description=f"OPSIONAL -- baris per request ke eSuite (default 50, maks {MAX_BATCH_SIZE})."
    ),
    include_payload: bool = Query(default=False, description="OPSIONAL -- sertakan body yang dikirim ke eSuite."),
    # 21 Oktober 2026: centang test_mode -> otomatis ke akun testing Salesman_12.
    test_mode: bool = Query(
        default=False,
        description=(
            f"MODE TES -- true = jadwal dikirim ke akun testing `{TEST_USERNAME}` "
            f"(employee_id `{TEST_EMPLOYEE_ID}`, sudah terisi otomatis). "
            "`slots` WAJIB pilih tepat 1 (data visit diambil dari slot itu). "
            "Default false = push normal ke akun asli slot."
        ),
    ),
    test_employee_id: str | None = Query(
        default=None,
        description=(
            f"OPSIONAL, override MODE TES -- biasanya KOSONGKAN (pakai test_mode). Diisi = kirim ke akun lain, "
            f"mengalahkan default `{TEST_EMPLOYEE_ID}`. "
            "Isi = kolom `employee_id` akun eSuite tujuan tes (angka NIK eSuite, mis. `202600016` = Salesman_1). "
            "BUKAN username (`Salesman_12`), BUKAN `id` internal eSuite, BUKAN id user Odoo. "
            "Cara cari: GET /api/debug/pull/employee (limit=200) -> cari baris username `Salesman_12` -> salin field `employee_id`. "
            "Aturan: `slots` WAJIB pilih tepat 1 (data visit diambil dari slot itu), jadwal dikirim ke akun ini; "
            "cek dulu dgn dry_run=true -> `slots[0].esuite_username` harus = akun tes. "
            "Kode jadi `ODOO-CP-TEST-{employee_id}-{id partner}-{YYYYMMDD}` -> tidak menimpa call plan asli."
        ),
    ),
    external_codes: str | None = Query(
        default=None,
        description="OPSIONAL -- customer tertentu saja, comma-separated, format 'ODOO-PARTNER-{id}'.",
    ),
    limit: int | None = Query(
        default=None, ge=1, description="OPSIONAL -- kirim maksimal N jadwal (utk tes kecil; call plan belum bisa dihapus)."
    ),
):
    """
    Kirim jadwal kunjungan sales (call plan) dari visit cycle Odoo ke eSuite
    -- `POST /v1/webhook/call-plan`. **Jalankan `dry_run=true` dulu.**

    - **Sumber:** Contact Odoo ber-visit (`x_studio_visit_cycle` / `_day` /
      `_frequency`) milik slot terpilih (`user_id`).
    - **Tanggal:** dihitung bridge. Minggu kalender Senin-Minggu; minggu yang
      memuat tgl 1 = minggu ke-1. M1 tiap minggu; M2C13 minggu 1 & 3; M2C24
      minggu 2 & 4; M4C2 minggu 2; M4C3 minggu 3.
    - **Dilewati + dilaporkan:** data visit tidak valid (`invalid_rows`),
      customer belum ada di eSuite / beda branch dgn salesman (`skipped`).
    - **Info:** `customer_not_mapped_to_salesman_count` -- customer yang di
      eSuite belum ter-mapping ke salesman itu (tetap dikirim).
    - **Kode per jadwal:** `ODOO-CP-{id partner}-{YYYYMMDD}`.
    - **Belum dipastikan:** kirim ulang kode yang sama = update atau jadwal
      ganda. Tipe yang dikirim `non_generated` tampil "Non - Call Plan".

    Respons 200 belum bukti tersimpan -- cek di eSuite: ework -> Call Plan List.
    """
    if date_from:
        date_to = date_to or date_from
    else:
        date_from, date_to = _periode_range(periode)
    return service.sync(
        slots=[s.value for s in slots],
        date_from=date_from,
        date_to=date_to,
        dry_run=dry_run,
        batch_size=batch_size,
        include_payload=include_payload,
        # Override manual menang; kalau kosong & test_mode -> akun testing default.
        test_employee_id=(test_employee_id or "").strip() or (TEST_EMPLOYEE_ID if test_mode else None),
        external_codes=external_codes,
        limit=limit,
    )
