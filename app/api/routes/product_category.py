from fastapi import APIRouter, Query
from app.services.product_category_sync_service import ProductCategorySyncService

router = APIRouter()
service = ProductCategorySyncService()


@router.post("/sync/product-category")
def sync_product_category(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL (21 Agustus 2026) -- upsert kategori TERTENTU saja, "
            "comma-separated, format 'ODOO-CAT-{id}' (mis. "
            "ODOO-CAT-1,ODOO-CAT-2). Kosongkan untuk semua kategori Saleable."
        ),
    ),
    limit: int | None = Query(
        default=None,
        description="OPSIONAL -- diagnostik, kirim cuma N kategori pertama. Kosongkan untuk semua.",
    ),
):
    """
    Trigger manual sync Product Category: Odoo (product.category) -> eSuite.
    Catatan: hierarki (parent) sengaja belum dikirim, lihat komentar di service.
    """
    return service.sync(event=event, external_codes=external_codes, limit=limit)
