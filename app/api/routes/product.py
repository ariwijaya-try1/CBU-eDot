from fastapi import APIRouter, Query
from app.services.product_sync_service import ProductSyncService

router = APIRouter()
service = ProductSyncService()


@router.post("/sync/product")
def sync_product(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
):
    """
    Trigger manual sync Product: Odoo (product.product, Saleable & free_qty>0) -> eSuite.
    Butuh Product Category sudah ke-push duluan (POST /sync/product-category).
    """
    return service.sync(event=event)
