from fastapi import APIRouter, Query
from app.services.stock_sync_service import StockSyncService

router = APIRouter()
service = StockSyncService()


@router.post("/sync/stock-matrix")
def sync_stock_matrix(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL -- sync stok produk TERTENTU saja, comma-separated, "
            "format 'ODOO-PROD-{id}' (mis. ODOO-PROD-18374,ODOO-PROD-8857). "
            "SANGAT DISARANKAN dipakai dulu (scoped) sebelum full sync -- "
            "baru ~30 dari 1241 produk yang confirmed punya product-variant "
            "ke-push ke eSuite; sync stok produk yang variant-nya belum ada "
            "kemungkinan besar gagal match. Kosongkan untuk semua produk Saleable."
        ),
    ),
    limit: int | None = Query(
        default=None,
        description=(
            "OPSIONAL -- diagnostik, kirim cuma N produk pertama PER WAREHOUSE "
            "(bukan limit gabungan). Kosongkan untuk behavior normal (semua produk)."
        ),
    ),
    batch_size: int | None = Query(
        default=None,
        ge=1,
        description=(
            "OPSIONAL -- pecah push jadi beberapa batch, pola sama dengan "
            "/sync/product & /sync/customers. Kosongkan untuk 1 batch semua baris sekaligus."
        ),
    ),
    include_payload: bool = Query(
        default=False,
        description="OPSIONAL -- kalau True, response sertakan payload_sent penuh per batch. Default False.",
    ),
):
    """
    Trigger manual sync Stock Matrix: Odoo (product.product, qty_available
    per warehouse in-scope) -> eSuite (/stock-matrix).

    Identifier pakai product_variant.code ("ODOO-PROD-{id}") & warehouse.code
    ("ODOO-WH-{id}") -- BUKAN id eSuite, TIDAK ADA external_code khusus
    entity ini. "on_hand"/"quantity" diisi qty_available Odoo (stok fisik
    asli, bukan free_qty). Nilai bersifat absolute (set-to-target) &
    idempotent -- kirim ulang nilai sama tidak mengubah apa-apa.

    Butuh Product & Product Variant sudah ke-push duluan (POST /sync/product
    dengan with_variant=True) untuk produk yang mau di-sync stoknya.
    """
    return service.sync(
        event=event,
        external_codes=external_codes,
        limit=limit,
        batch_size=batch_size,
        include_payload=include_payload,
    )
