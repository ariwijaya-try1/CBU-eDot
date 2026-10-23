from fastapi import APIRouter, Query
from app.services.customer_salesman_mapping_service import CustomerSalesmanMappingService

router = APIRouter()
service = CustomerSalesmanMappingService()


@router.post("/mapping/customer-salesman")
def map_customer_salesman(
    external_codes: str = Query(
        ...,
        description=(
            "WAJIB -- external_code Customer di eSuite yang mau di-mapping ke "
            "salesman, comma-separated (mis. ODOO-PARTNER-39353,ODOO-PARTNER-1655). "
            "Diterima APA ADANYA (TIDAK divalidasi format)."
        ),
    ),
    salesman_ids: str = Query(
        ...,
        description=(
            "WAJIB -- employee_id Salesman di eSuite, comma-separated kalau "
            "mau assign lebih dari 1 salesman sekaligus. Salesman yang sama "
            "di-assign ke SEMUA external_codes yang dikirim (mass mapping)."
        ),
    ),
):
    """
    Mass mapping Customer -> Salesman di eSuite, supaya tidak perlu assign
    salesman 1 per 1 lewat UI eSuite. Payload yang dikirim ke eSuite MINIMAL
    -- cuma external_code + sales.salesmans, field Customer lain (name/type/
    customer_groups/dst) TIDAK ikut dikirim/direset (upsert eSuite bersifat
    partial-merge).
    """
    return service.map_to_salesman(
        external_codes=external_codes, salesman_ids=salesman_ids
    )
