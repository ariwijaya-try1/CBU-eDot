"""
Endpoint EXPORT (download file) -- 2 November 2026.

Dipisah dari odoo_get.py (permintaan user) supaya muncul di grup Swagger
"Export". Read-only, tidak kirim ke eSuite.

ATURAN (user, 9 November 2026): SEMUA endpoint yang berbentuk export
(download file) ditempatkan di file ini / grup Swagger "Export".
"""
from datetime import date
from enum import Enum
from io import BytesIO

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.salesman_slots import SALESMAN_SLOTS
from app.services.outlet_stock_input_export_service import OutletStockInputExportService
from app.services.visit_schedule_export_service import ExportPeriode, VisitScheduleExportService, resolve_period

router = APIRouter()

# Pilihan slot (select box Swagger) = isi tabel mapping.
# Enum("Nama", {key: value}) = cara bikin Enum dinamis dari data.
ExportSlot = Enum("ExportSlot", {s["odoo_slot"]: s["odoo_slot"] for s in SALESMAN_SLOTS}, type=str)


@router.get("/odoo/visit-schedule/export")
def export_odoo_visit_schedule(
    periode: ExportPeriode = Query(
        default=ExportPeriode.bulan_ini,
        description=(
            "Rentang (WITA), tanpa ketik. Diabaikan kalau date_from diisi. "
            "bulan_ini / bulan_depan = tgl 1 s/d akhir bulan. minggu_* = Senin-Minggu."
        ),
    ),
    slots: list[ExportSlot] | None = Query(
        default=None,
        description="OPSIONAL -- slot sales (boleh banyak). Kosong = SEMUA slot di app/core/salesman_slots.py.",
    ),
    date_from: date | None = Query(default=None, description="OPSIONAL -- tanggal awal manual YYYY-MM-DD (periode diabaikan)."),
    date_to: date | None = Query(default=None, description="OPSIONAL -- tanggal akhir manual (kosong = sama dgn date_from). Maks 62 hari."),
):
    """
    Download Excel call plan HITUNGAN dari visit cycle Odoo utk direview
    sales manager -- 2 November 2026. Read-only (tidak kirim ke eSuite).

    Tanggal dihitung sama persis dgn `POST /sync/call-plan`. Sheet: Ringkasan
    (rekap review otomatis), Beban Harian, 1 sheet per sales (1 baris per
    outlet, kolom per minggu, kolom KUNING: Review OK/Revisi + usulan cycle/
    hari + catatan), Perlu Dicek (visit tidak valid / Salesperson di luar
    tabel slot), Detail Kunjungan (1 baris per kunjungan + kode call plan).

    Di Swagger: Execute -> klik "Download file".
    """
    d_from, d_to = resolve_period(periode, date_from, date_to)
    content, filename = VisitScheduleExportService().build(
        d_from, d_to, [s.value for s in slots] if slots else None
    )
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/outlet-stock/input-progress/export")
def export_outlet_stock_input_progress(
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL -- outlet tertentu, comma-separated, format 'ODOO-PARTNER-{id}' "
            "(mis. ODOO-PARTNER-25066,ODOO-PARTNER-25067). Kosong = SEMUA outlet yang punya Product Stock di eSuite."
        ),
    ),
):
    """
    Download Excel progress input Product Stock outlet (eWork) -- 9 November
    2026. Read-only (tidak menulis ke eSuite / Odoo).

    Utk management: "sales X sudah input 30 dari 70 SKU". Total SKU = list
    Product Stock outlet di app (pre-fill bridge + tambahan sales).
    "Sudah input" = stok >= 1, ada expired, atau baris dibuat user app.
    ⚠️ Isian 0 pada baris pre-fill tanpa expired terhitung BELUM (tidak bisa
    dibedakan).

    Sheet: Per Sales, Per Outlet, Belum Input (SKU yang belum diisi),
    Detail, Catatan.

    Di Swagger: Execute -> klik "Download file". Semua outlet bisa makan
    waktu (tarik seluruh stock-matrix + customer + warehouse eSuite).
    """
    codes = external_codes.split(",") if external_codes else None
    content, filename = OutletStockInputExportService().build(codes)
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
