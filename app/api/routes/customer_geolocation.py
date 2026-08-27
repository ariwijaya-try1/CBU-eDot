from fastapi import APIRouter, Query

from app.services.customer_geolocation_service import CustomerGeolocationService

router = APIRouter()
service = CustomerGeolocationService()


@router.post("/update/customer-geolocation")
def update_customer_geolocation(
    external_code: str = Query(
        ...,
        description=(
            "WAJIB -- external_code Customer di eSuite (mis. ODOO-PARTNER-24458 "
            "hasil sync kita, ATAU external_code data pre-existing/legacy eSuite "
            "seperti CBU-0001). Diterima APA ADANYA, TIDAK divalidasi format."
        ),
    ),
    coordinates: str = Query(
        ...,
        description=(
            "WAJIB -- 1 field 'latitude, longitude' hasil copas LANGSUNG dari "
            "Google Maps (klik-kanan titik lokasi di peta -> klik koordinat "
            "paling atas -> paste di sini apa adanya). Contoh: "
            "-8.800799056816937, 115.18475651821433"
        ),
    ),
):
    """
    Update longitude/latitude 1 Customer di eSuite by external_code -- TERPISAH
    dari upsert Customer penuh (POST /sync/customers). Dibuat khusus untuk isi
    lat-long customer eSuite yang belum ada datanya, karena edit manual lewat
    UI eSuite mewajibkan banyak field lain yang tidak relevan.

    Payload ke eSuite sengaja MINIMAL -- cuma external_code + addresses[]
    berisi longitude/latitude (upsert eSuite partial-merge, field lain TIDAK
    ikut ter-reset). Pola sama dengan POST /deactivate/customer.
    """
    return service.update(external_code=external_code, coordinates=coordinates)
