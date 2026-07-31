from fastapi import APIRouter, Query
from app.services.warehouse_sync_service import WarehouseSyncService

router = APIRouter()
service = WarehouseSyncService()


@router.post("/sync/warehouse")
def sync_warehouse(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
):
    """
    Trigger manual sync Warehouse: Odoo (stock.warehouse) -> eSuite.
    Butuh Branch sudah ke-push duluan (POST /sync/branch) -- Warehouse
    mereferensi ID Branch yang di-generate eSuite.
    """
    return service.sync(event=event)
