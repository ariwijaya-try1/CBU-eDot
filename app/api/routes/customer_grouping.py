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
    customer_group_external_codes: str = Query(
        ...,
        description=(
            "WAJIB -- external_code Customer Group (format 'CBU-CUSTGROUP-"
            "{code}', SAMA dengan yang dipakai /sync/customer-group, mis. "
            "CBU-CUSTGROUP-FS), comma-separated kalau mau assign lebih dari 1 "
            "grup sekaligus. id+name eSuite di-RESOLVE OTOMATIS lewat pull "
            "GET /customergroup -- tidak perlu tau ObjectId eSuite. Grup yang "
            "sama di-assign ke SEMUA external_codes yang dikirim (mass mapping)."
        ),
    ),
):
    """
    Mass mapping Customer -> Customer Group di eSuite, supaya tidak perlu
    assign group 1 per 1 lewat UI eSuite. Payload yang dikirim ke eSuite
    MINIMAL -- cuma external_code + customer_groups (id+name, di-resolve
    otomatis), field Customer lain (name/type/phone/dst) TIDAK ikut
    dikirim/direset (upsert eSuite bersifat partial-merge).

    REVISI 22 Agustus 2026: sebelumnya cuma kirim id tanpa name -- terbukti
    dari live data, customer_groups[].name jadi KOSONG di eSuite meski
    mapping "berhasil". Sekarang name di-resolve otomatis dari GET
    /customergroup, caller cukup kasih external_code (bukan ObjectId).
    """
    return service.map_to_group(
        external_codes=external_codes,
        customer_group_external_codes=customer_group_external_codes,
    )
