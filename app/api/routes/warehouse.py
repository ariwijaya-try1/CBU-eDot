from fastapi import APIRouter, Query
from app.services.warehouse_sync_service import WarehouseSyncService

router = APIRouter()
service = WarehouseSyncService()


@router.post("/sync/warehouse")
def sync_warehouse(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL (21 Agustus 2026) -- upsert Warehouse TERTENTU saja, "
            "comma-separated, format 'ODOO-WH-{id}' (mis. "
            "ODOO-WH-1,ODOO-WH-2). Kosongkan untuk semua warehouse in-scope."
        ),
    ),
    limit: int | None = Query(
        default=None,
        description="OPSIONAL -- diagnostik, kirim cuma N warehouse pertama. Kosongkan untuk semua.",
    ),
):
    """
    Trigger manual sync Warehouse: Odoo (stock.warehouse) -> eSuite.
    Butuh Branch sudah ke-push duluan (POST /sync/branch) -- Warehouse
    mereferensi ID Branch yang di-generate eSuite.
    """
    return service.sync(event=event, external_codes=external_codes, limit=limit)
