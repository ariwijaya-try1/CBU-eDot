from fastapi import APIRouter, Query
from app.services.product_sync_service import ProductSyncService

router = APIRouter()
service = ProductSyncService()


@router.post("/sync/product")
def sync_product(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
    limit: int | None = Query(
        default=None,
        description=(
            "TEMPORARY, buat diagnostik push full batch (7 Agustus 2026, pola "
            "sama dengan /sync/customers) -- kirim cuma N produk pertama, "
            "bukan semua. Kosongkan (default) untuk behavior normal (semua produk)."
        ),
    ),
):
    """
    Trigger manual sync Product: Odoo (product.product, category Saleable & list_price>0) -> eSuite.
    Produk dengan free_qty=0 tetap disync (revisi 5 Agustus 2026 -- tidak lagi jadi syarat exclude).
    Butuh Product Category sudah ke-push duluan (POST /sync/product-category).
    """
    return service.sync(event=event, limit=limit)
