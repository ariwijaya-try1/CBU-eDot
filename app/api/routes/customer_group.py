from fastapi import APIRouter, Query
from app.services.customer_group_sync_service import CustomerGroupSyncService

router = APIRouter()
service = CustomerGroupSyncService()


@router.post("/sync/customer-group")
def sync_customer_group(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
):
    """
    Trigger manual sync Customer Group: hardcoded list (FS/MT/GT/HORECA) -> eSuite.
    BUKAN dari Odoo -- lihat komentar CUSTOMER_GROUPS di service untuk alasan
    & catatan soal external_code (ASUMSI penamaan, belum dikonfirmasi user).
    event=init  : dipakai sekali di awal (seed pertama kali).
    event=upsert: dipakai untuk sync berikutnya (default).
    """
    return service.sync(event=event)
