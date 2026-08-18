from fastapi import APIRouter, Query
from app.services.salesman_division_sync_service import SalesmanDivisionSyncService

router = APIRouter()
service = SalesmanDivisionSyncService()


@router.post("/sync/salesman-division")
def sync_salesman_division(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
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
    return service.sync(event=event)
