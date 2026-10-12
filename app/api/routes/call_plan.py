from datetime import date
from enum import Enum

from fastapi import APIRouter, Query

from app.core.salesman_slots import SALESMAN_SLOTS
from app.services.call_plan_sync_service import MAX_BATCH_SIZE, MAX_RANGE_DAYS, CallPlanSyncService

router = APIRouter()
service = CallPlanSyncService()

# Pilihan slot di Swagger = isi tabel mapping (select box, bisa pilih banyak).
CallPlanSlot = Enum("CallPlanSlot", {s["odoo_slot"]: s["odoo_slot"] for s in SALESMAN_SLOTS}, type=str)


@router.post("/sync/call-plan")
def sync_call_plan(
    slots: list[CallPlanSlot] = Query(
        ...,
        description="WAJIB -- slot Salesperson Odoo (boleh lebih dari 1). Daftar = tabel mapping app/core/salesman_slots.py.",
    ),
    date_from: date = Query(..., description="WAJIB -- tanggal awal jadwal, YYYY-MM-DD."),
    date_to: date = Query(
        ..., description=f"WAJIB -- tanggal akhir jadwal, YYYY-MM-DD. Rentang maksimal {MAX_RANGE_DAYS} hari."
    ),
    dry_run: bool = Query(
        default=True,
        description="DEFAULT TRUE -- cuma hitung & tampilkan jadwal, TIDAK kirim ke eSuite. Isi false utk kirim.",
    ),
    batch_size: int | None = Query(
        default=None, ge=1, le=MAX_BATCH_SIZE, description=f"OPSIONAL -- baris per request ke eSuite (default 50, maks {MAX_BATCH_SIZE})."
    ),
    include_payload: bool = Query(default=False, description="OPSIONAL -- sertakan body yang dikirim ke eSuite."),
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
    return service.sync(
        slots=[s.value for s in slots],
        date_from=date_from,
        date_to=date_to,
        dry_run=dry_run,
        batch_size=batch_size,
        include_payload=include_payload,
    )
