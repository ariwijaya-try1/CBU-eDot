from fastapi import APIRouter, Query
from app.services.customer_grouping_service import CustomerGroupingService

router = APIRouter()
service = CustomerGroupingService()


@router.post("/mapping/customer-grouping")
def map_customer_grouping(
    external_codes: str = Query(
        ...,
        description=(
            "WAJIB -- external_code Customer di eSuite yang mau di-mapping ke "
            "grup, comma-separated (mis. ODOO-PARTNER-39353,ODOO-PARTNER-1655). "
            "Diterima APA ADANYA (TIDAK divalidasi format)."
        ),
    ),
    customer_group_ids: str = Query(
        ...,
        description=(
            "WAJIB -- id Customer Group di eSuite (ObjectId, dari "
            "GET /customergroup), comma-separated kalau mau assign lebih dari "
            "1 grup sekaligus (mis. 6a8911e3d5d77369eccac408). Grup yang sama "
            "di-assign ke SEMUA external_codes yang dikirim (mass mapping)."
        ),
    ),
):
    """
    Mass mapping Customer -> Customer Group di eSuite, supaya tidak perlu
    assign group 1 per 1 lewat UI eSuite. Payload yang dikirim ke eSuite
    MINIMAL -- cuma external_code + customer_groups, field Customer lain
    (name/type/phone/dst) TIDAK ikut dikirim/direset (upsert eSuite bersifat
    partial-merge).
    """
    return service.map_to_group(
        external_codes=external_codes, customer_group_ids=customer_group_ids
    )
