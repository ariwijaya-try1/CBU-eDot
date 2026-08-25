from fastapi import APIRouter, Query
from app.services.salesman_division_sync_service import SalesmanDivisionSyncService

router = APIRouter()
# Router terpisah -- endpoint deactivate ke-grup di Swagger tag "Deactivate"
# sendiri (bukan numpuk di "Sync"), didaftarkan terpisah di main.py. Pola
# SAMA dengan branch.py/customer.py (lihat [[branch_deactivate_endpoint]]).
deactivate_router = APIRouter()
service = SalesmanDivisionSyncService()


@router.post("/sync/salesman-division")
def sync_salesman_division(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL (21 Agustus 2026) -- upsert division TERTENTU saja, "
            "comma-separated, format 'ODOO-SALESTEAM-{id}' (mis. "
            "ODOO-SALESTEAM-1,ODOO-SALESTEAM-2). Kosongkan untuk semua division."
        ),
    ),
    limit: int | None = Query(
        default=None,
        description="OPSIONAL -- diagnostik, kirim cuma N division pertama. Kosongkan untuk semua.",
    ),
):
    """
    Trigger manual sync Salesman Division: Odoo (crm.team / Sales Team) -> eSuite.
    Sales Team dipetakan 1:1 jadi Salesman Division (representasi wilayah,
    BUKAN karyawan individual) -- lihat SalesmanDivisionSyncService untuk
    detail keputusan & catatan kenapa `employees` sengaja dikirim kosong.
    Push Salesman individual (per-orang) MASIH TERPISAH & belum dikerjakan.
    event=init  : dipakai sekali di awal (seed pertama kali).
    event=upsert: dipakai untuk sync berikutnya (default).
    """
    return service.sync(event=event, external_codes=external_codes, limit=limit)


@deactivate_router.post("/deactivate/salesman-division")
def deactivate_salesman_division(
    external_codes: str = Query(
        ...,
        description=(
            "WAJIB -- external_code Salesman Division di eSuite yang mau "
            "dinonaktifkan (status -> inactive), comma-separated. Diterima "
            "APA ADANYA (TIDAK divalidasi format 'ODOO-SALESTEAM-{id}') -- "
            "bisa data hasil sync kita maupun data pre-existing/legacy eSuite."
        ),
    ),
):
    """
    Nonaktifkan Salesman Division di eSuite by external_code (status:
    "inactive"). Payload yang dikirim ke eSuite MINIMAL -- cuma status +
    external_code, field lain (name/code/employees/dst) TIDAK ikut
    dikirim/direset (upsert eSuite bersifat partial-merge). Pola sama
    dengan POST /deactivate/branch & POST /deactivate/customer.
    """
    return service.deactivate(external_codes=external_codes)
