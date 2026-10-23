from fastapi import APIRouter, Query
from app.services.customer_pricelist_mapping_service import CustomerPricelistMappingService

router = APIRouter()
service = CustomerPricelistMappingService()


@router.post("/mapping/customer-pricelist")
def map_customer_pricelist(
    external_codes: str = Query(
        ...,
        description=(
            "WAJIB -- external_code Customer di eSuite yang mau di-mapping "
            "ke pricelist yang SAMA, comma-separated (mis. "
            "ODOO-PARTNER-39353,ODOO-PARTNER-1655). Diterima APA ADANYA "
            "(TIDAK divalidasi format)."
        ),
    ),
    pricelist_external_code: str = Query(
        ...,
        description=(
            "WAJIB -- external_code Pricelist (format 'ODOO-PRICELIST-{id}', "
            "SAMA dengan /sync/pricelist), TUNGGAL (bukan comma-separated) -- "
            "1 customer cuma bisa punya 1 pricelist aktif dalam satu waktu. "
            "id+name di-RESOLVE OTOMATIS lewat GET /pricelists."
        ),
    ),
):
    """
    Mass mapping Customer -> Pricelist di eSuite (field `price_list.id`,
    PDF section 9.8) -- bagian terakhir Task #4 (lihat sales_entities_gap.md
    project memory), melengkapi `sales.branchs[]`/`sales.salesmans[]` yang
    sudah ada lewat POST /mapping/customer-sales.

    1 panggilan = assign 1 pricelist yang SAMA ke SEMUA customer yang
    disebut di external_codes. Kalau ada customer yang butuh pricelist
    berbeda, panggil endpoint ini lagi terpisah per grup.

    Pricelist WAJIB sudah pernah di-push ke eSuite dulu (POST /sync/pricelist)
    sebelum bisa di-mapping ke sini -- kalau belum ketemu, endpoint ini
    return error, bukan diam-diam gagal.
    """
    return service.map_to_pricelist(
        external_codes=external_codes,
        pricelist_external_code=pricelist_external_code,
    )
