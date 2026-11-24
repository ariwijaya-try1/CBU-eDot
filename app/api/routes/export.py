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
from app.core.exceptions import ValidationError
from app.core.scope import IN_SCOPE_COMPANY_NAMES
from app.services.outlet_stock_input_export_service import OutletStockInputExportService
from app.services.visit_schedule_export_service import ExportPeriode, VisitScheduleExportService, resolve_period

router = APIRouter()

# Pilihan slot (select box Swagger) = isi tabel mapping.
# Enum("Nama", {key: value}) = cara bikin Enum dinamis dari data.
ExportSlot = Enum("ExportSlot", {s["odoo_slot"]: s["odoo_slot"] for s in SALESMAN_SLOTS}, type=str)
# 23 Nov 2026: pilihan company (select box Swagger) = daftar company in-scope.
ExportCompany = Enum("ExportCompany", {n: n for n in IN_SCOPE_COMPANY_NAMES}, type=str)


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
    company: ExportCompany | None = Query(
        default=None,
        description=(
            "OPSIONAL -- hanya outlet milik company Odoo ini (res.partner.company_id). "
            "Kosong = SEMUA company. Bisa digabung dgn external_codes."
        ),
    ),
    salesperson_ids: str | None = Query(
        default=None,
        description=(
            "OPSIONAL -- id res.users (Salesperson Odoo, field user_id di Contact), pisah koma "
            "(mis. 87,92). Lihat GET /odoo/salesperson. Kosong = semua sales. Bisa digabung dgn company."
        ),
    ),
    salesman_employee_ids: str | None = Query(
        default=None,
        description=(
            "OPSIONAL -- employee_id akun eSuite, pisah koma (spasi boleh). Contoh Jakarta: "
            "202600018, 202600010, 202600015, 202600013 | Bali: 202600019, 202600016, 202600017, "
            "202600011, 202600009, 202600014, 202600020. Diterjemahkan ke Salesperson Odoo lewat "
            "app/core/salesman_slots.py (akun mirror ikut slot utamanya). Kosong = semua sales. "
            "Digabung dgn filter lain sebagai AND."
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
    Produk discontinue (di-archive di Odoo) tidak dihitung (13 Nov 2026).

    Sheet: Per Sales, Per Outlet, Belum Input (SKU yang belum diisi),
    Detail, Catatan.

    Di Swagger: Execute -> klik "Download file". Semua outlet bisa makan
    waktu (tarik seluruh stock-matrix + customer + warehouse eSuite).
    """
    codes = external_codes.split(",") if external_codes else None
    user_ids = None
    if salesperson_ids:
        try:
            user_ids = [int(i.strip()) for i in salesperson_ids.split(",") if i.strip()]
        except ValueError:
            raise ValidationError(
                f"Parameter 'salesperson_ids' harus angka semua, pisah koma -- dapat: '{salesperson_ids}'",
                details={"salesperson_ids": salesperson_ids},
            )
    content, filename = OutletStockInputExportService().build(
        codes,
        company.value if company else None,
        user_ids,
        salesman_employee_ids.split(",") if salesman_employee_ids else None,
    )
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
