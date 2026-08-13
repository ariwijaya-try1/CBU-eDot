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
    batch_size: int | None = Query(
        default=None,
        ge=1,
        description=(
            "OPSIONAL (12 Agustus 2026) -- pecah push jadi beberapa batch, "
            "pola sama dengan /sync/customers. Kosongkan untuk behavior lama "
            "(semua produk dalam 1 request, sudah tervalidasi ke 1247 produk)."
        ),
    ),
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL (12 Agustus 2026) -- upsert produk TERTENTU saja, "
            "comma-separated, format 'ODOO-PROD-{id}' (mis. "
            "ODOO-PROD-18374,ODOO-PROD-8857). Kosongkan untuk semua produk."
        ),
    ),
    with_variant: bool = Query(
        default=False,
        description=(
            "OPSIONAL (12 Agustus 2026, BARU, belum divalidasi skala besar) -- "
            "kalau True, tiap produk yang berhasil di-push juga otomatis "
            "push 1 product-variant (1:1), sesuai saran vendor (dashboard "
            "sales nampilin data Variant, bukan Product). Default False "
            "(opt-in) sampai fitur ini tervalidasi."
        ),
    ),
    include_payload: bool = Query(
        default=False,
        description=(
            "OPSIONAL (13 Agustus 2026) -- kalau True, response sertakan "
            "payload_sent penuh (data lengkap yang dikirim ke eSuite) per "
            "batch. Default False supaya Swagger tetap responsif untuk "
            "batch besar -- external_codes tetap selalu tampil. Nyalakan "
            "cuma pas perlu verifikasi payload detail (mis. debug 1-2 produk)."
        ),
    ),
):
    """
    Trigger manual sync Product: Odoo (product.product, category Saleable & list_price>0) -> eSuite.
    Produk dengan free_qty=0 tetap disync (revisi 5 Agustus 2026 -- tidak lagi jadi syarat exclude).
    Butuh Product Category sudah ke-push duluan (POST /sync/product-category).
    """
    return service.sync(
        event=event,
        limit=limit,
        batch_size=batch_size,
        external_codes=external_codes,
        with_variant=with_variant,
        include_payload=include_payload,
    )
