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
        "ODOO-COMPANY-2",
        description=(
            "OPSIONAL -- external_code Branch (format 'ODOO-COMPANY-{id}', "
            "sama dengan /sync/branch), comma-separated kalau >1. DEFAULT "
            "'ODOO-COMPANY-2' (branch yang dipakai hampir semua backfill "
            "customer saat ini, instruksi user 28 Agustus 2026) -- ganti "
            "manual kalau customer ini butuh branch lain. Kosongkan (string "
            "kosong) kalau memang tidak mau kirim sales sama sekali. Kalau "
            "diisi, salesman_ids WAJIB ikut diisi juga (eSuite mewajibkan "
            "branchs & salesmans di-set bersamaan)."
        ),
    ),
    salesman_ids: str | None = Query(
        "202600002,202600003,202600004",
        description=(
            "OPSIONAL -- employee_id Salesman di eSuite (dipakai query param "
            "lookup GET /employee?employee_id=...), comma-separated kalau >1. "
            "DEFAULT 3 kode real yang dipakai hampir semua customer saat ini "
            "('202600002,202600003,202600004', instruksi user 28 Agustus "
            "2026) -- ganti manual kalau customer ini butuh salesman "
            "berbeda. Kosongkan (string kosong) kalau memang tidak mau "
            "kirim sales sama sekali. id+nama yang dikirim ke payload "
            "di-resolve OTOMATIS dari hasil lookup (id INTERNAL eSuite, "
            "BUKAN employee_id ini langsung). Kalau diisi, "
            "branch_external_codes WAJIB ikut diisi juga."
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
    belum diverifikasi vendor, sama seperti endpoint geo existing). Hipotesis
    user (28 Agustus 2026, BELUM dikonfirmasi): "id": "" mungkin diabaikan
    eSuite (pola sama dengan sales.branchs/salesmans "[]" yang terbukti
    diabaikan di /unmap/customer-sales) -- kalau benar, risiko numpuk ini
    tidak terjadi, tapi belum ada test live yang membuktikan/membantah.

    branch_external_codes & salesman_ids sudah ada DEFAULT (branch
    "ODOO-COMPANY-2" + 3 salesman tetap yang dipakai hampir semua customer
    saat ini) supaya tidak perlu diisi manual tiap panggilan -- tetap bisa
    dioverride atau dikosongkan kalau customer tertentu butuh beda.
    """
    return service.upsert(
        customer_id=customer_id,
        coordinates=coordinates,
        branch_external_codes=branch_external_codes,
        salesman_ids=salesman_ids,
        salesman_names=salesman_names,
    )
