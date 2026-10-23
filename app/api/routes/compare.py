from fastapi import APIRouter, Query
from app.services.pricelist_compare_service import PricelistCompareService

router = APIRouter()
service = PricelistCompareService()


@router.get("/compare/pricelist")
def compare_pricelist(
    product_name: str = Query(
        ..., min_length=3,
        description="WAJIB -- nama produk Odoo (ilike, mis. 'ACROYALI Canned'). Kode internal (default_code) tidak dicari.",
    ),
    customer: str | None = Query(
        default=None,
        description=(
            "OPSIONAL -- ODOO-PARTNER-<id> atau id angka (mis. ODOO-PARTNER-24522). "
            "Diisi -> hanya bandingkan pricelist customer itu. Kosong -> semua pricelist yg memuat produk."
        ),
    ),
    product_limit: int = Query(default=5, ge=1, le=20, description="Maks produk Odoo yang cocok dgn nama."),
):
    """
    READ-ONLY. Bandingkan harga produk di pricelist Odoo vs pricelist eSuite.
    Output per produk: nama pricelist Odoo + harga Odoo, nama pricelist eSuite + harga eSuite,
    status (sama / beda / produk_tidak_ada_di_pricelist_esuite / pricelist_tidak_ada_di_esuite /
    dobel_di_esuite / odoo_bukan_fixed / tidak_ada_di_pricelist_odoo), plus esuite_only
    (pricelist eSuite lain yang memuat produk ini).
    Catatan: scan SEMUA pricelist eSuite per panggilan -> bisa beberapa detik.
    """
    return service.compare(product_name=product_name, customer=customer, product_limit=product_limit)
