from fastapi import APIRouter, Query
from app.services.customer_sync_service import CustomerSyncService

router = APIRouter()
service = CustomerSyncService()


@router.post("/sync/customers")
def sync_customers(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
):
    """
    Trigger manual sync Customer: Odoo (res.partner, customer_rank > 0) -> eSuite.
    Field `type` di payload eSuite dipetakan dari `company_type` Odoo
    ("company" -> "company", "person" -> "individual") -- BUKAN dari
    `res.partner.type` (itu jenis alamat, bukan tipe customer).
    """
    return service.sync(event=event)
