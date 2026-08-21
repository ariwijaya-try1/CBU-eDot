from fastapi import APIRouter, Query
from app.services.salesman_division_sync_service import SalesmanDivisionSyncService

router = APIRouter()
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
