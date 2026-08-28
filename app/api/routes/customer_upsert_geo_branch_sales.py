from fastapi import APIRouter, Query

from app.services.customer_upsert_geo_branch_sales_service import (
    CustomerUpsertGeoBranchSalesService,
)

router = APIRouter()
service = CustomerUpsertGeoBranchSalesService()


@router.post("/mapping/customer-upsert-geo-branch-sales")
def upsert_customer_geo_branch_sales(
    customer_id: int = Query(
        ...,
        description=(
            "WAJIB -- id Odoo res.partner (bukan external_code), mis. 39353. "
            "Customer harus customer_rank > 0 dan active = True di Odoo."
        ),
    ),
    coordinates: str = Query(
        ...,
        description=(
            "WAJIB -- 1 field 'latitude, longitude' hasil copas LANGSUNG dari "
            "Google Maps (klik-kanan titik lokasi -> klik koordinat paling "
            "atas -> paste apa adanya). Contoh: "
            "-8.800799056816937, 115.18475651821433. Dipakai menggantikan "
            "partner_latitude/partner_longitude Odoo yang belum ada datanya."
        ),
    ),
    branch_external_codes: str | None = Query(
        None,
        description=(
            "OPSIONAL -- external_code Branch (format 'ODOO-COMPANY-{id}', "
            "sama dengan /sync/branch), comma-separated kalau >1. Kalau "
            "diisi, salesman_ids WAJIB ikut diisi juga (eSuite mewajibkan "
            "branchs & salesmans di-set bersamaan)."
        ),
    ),
    salesman_ids: str | None = Query(
        None,
        description=(
            "OPSIONAL -- employee_id Salesman di eSuite (dipakai query param "
            "lookup GET /employee?employee_id=...), comma-separated kalau >1. "
            "id+nama yang dikirim ke payload di-resolve OTOMATIS dari hasil "
            "lookup (id INTERNAL eSuite, BUKAN employee_id ini langsung). "
            "Kalau diisi, branch_external_codes WAJIB ikut diisi juga."
        ),
    ),
    salesman_names: str | None = Query(
        None,
        description=(
            "OPSIONAL -- override manual NAMA Salesman saja, comma-separated, "
            "urutan berpasangan 1-1 dengan salesman_ids. id tetap selalu "
            "hasil resolve GET /employee. Kalau kosong, nama juga di-resolve "
            "otomatis."
        ),
    ),
):
    """
    Upsert MANUAL 1 customer by id Odoo dalam SATU call ke eSuite --
    gabungan dari 3 hal: (1) data utama customer ditarik dari Odoo (sama
    logic dengan POST /sync/customers), (2) latitude/longitude MANUAL INPUT
    (menggantikan data Odoo yang belum ada), (3) branch+salesman OPSIONAL
    (sama logic dengan POST /mapping/customer-sales).

    Endpoint BARU, TIDAK mengubah /sync/customers, /update/customer-geolocation,
    atau /mapping/customer-sales yang sudah ada -- 3 endpoint itu tetap
    berjalan seperti biasa dan independen dari endpoint ini.

    ⚠️ addresses[] selalu dikirim dengan "id": "" (address BARU tiap upsert,
    pola sama endpoint geo existing) -- didesain untuk customer yang BELUM
    punya address/geo data di eSuite. Kalau customer ini sudah pernah
    di-upsert sebelumnya (via /sync/customers atau endpoint ini), panggilan
    ulang berpotensi menambah address baru, bukan update yang lama (risiko
    belum diverifikasi vendor, sama seperti endpoint geo existing).
    """
    return service.upsert(
        customer_id=customer_id,
        coordinates=coordinates,
        branch_external_codes=branch_external_codes,
        salesman_ids=salesman_ids,
        salesman_names=salesman_names,
    )
