from fastapi import APIRouter, Query
from app.services.pricelist_sync_service import PricelistSyncService

router = APIRouter()
service = PricelistSyncService()


@router.post("/sync/pricelist")
def sync_pricelist(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
    ids: str | None = Query(
        default=None,
        description=(
            "OPSIONAL -- sync pricelist TERTENTU saja, comma-separated, id Odoo "
            "product.pricelist MENTAH (mis. 3,5,12 -- BUKAN format ODOO-PRICELIST-xxx, "
            "pakai id yang sama dari GET /odoo/pricelist). SANGAT DISARANKAN diisi "
            "dulu (1-2 pricelist) untuk test sebelum full push -- ini data HARGA, "
            "sebagian field payload (product[].id top-level, branch[].id) belum "
            "pernah divalidasi live ke eSuite. Kosongkan untuk semua pricelist."
        ),
    ),
    limit: int | None = Query(
        default=None,
        description="OPSIONAL -- diagnostik, proses cuma N pricelist pertama. Kosongkan untuk semua.",
    ),
    batch_size: int | None = Query(
        default=None,
        ge=1,
        description="OPSIONAL -- pecah push jadi beberapa batch, pola sama /sync/product & /sync/customers.",
    ),
    include_payload: bool = Query(
        default=False,
        description="OPSIONAL -- kalau True, response sertakan payload_sent penuh per batch. Default False.",
    ),
):
    """
    Trigger manual sync Pricelist: Odoo (product.pricelist + product.pricelist.item)
    -> eSuite (/pricelists). SEMUA pricelist & SEMUA company ikut (termasuk
    "Sunshine Agri Pratama" & pricelist tanpa company) -- keputusan scope
    dikonfirmasi user 18 Agustus 2026, lihat PricelistSyncService docstring
    untuk detail lengkap desain & asumsi yang masih perlu diverifikasi live.

    GUARD: produk yang belum punya product-variant valid di eSuite (lihat
    POST /sync/product with_variant=True) otomatis di-skip dari product[]
    pricelist manapun -- pricelist yang jadi 0 produk valid ikut di-skip
    (lihat skipped_pricelist_no_valid_product di response), TIDAK
    menggagalkan pricelist lain.

    Hanya baris harga dengan compute_price="fixed" yang didukung (match
    contoh nyata tab "Prices" Odoo) -- baris percentage/formula di-skip &
    dihitung di response (skipped_item_unsupported_compute_price).
    """
    return service.sync(
        event=event,
        ids=ids,
        limit=limit,
        batch_size=batch_size,
        include_payload=include_payload,
    )
