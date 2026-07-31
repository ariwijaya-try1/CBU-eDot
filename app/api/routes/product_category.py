from fastapi import APIRouter, Query
from app.services.product_category_sync_service import ProductCategorySyncService

router = APIRouter()
service = ProductCategorySyncService()


@router.post("/sync/product-category")
def sync_product_category(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
):
    """
    Trigger manual sync Product Category: Odoo (product.category) -> eSuite.
    Catatan: hierarki (parent) sengaja belum dikirim, lihat komentar di service.
    """
    return service.sync(event=event)
