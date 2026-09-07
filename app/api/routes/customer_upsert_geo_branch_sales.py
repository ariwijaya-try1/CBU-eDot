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
    coordinates: str | None = Query(
        None,
        description=(
            "OPSIONAL -- 1 field 'latitude, longitude' hasil copas LANGSUNG dari "
            "Google Maps (klik-kanan titik lokasi -> klik koordinat paling "
            "atas -> paste apa adanya). Contoh: "
            "-8.800799056816937, 115.18475651821433. Dipakai menggantikan "
            "partner_latitude/partner_longitude Odoo yang belum ada datanya. "
            "Kosongkan kalau memang tidak mau update geo/address (mis. mass "
            "update sales-only pre-live, instruksi user 7 September 2026) -- "
            "kalau kosong, key \"addresses\" TIDAK dikirim sama sekali ke "
            "eSuite (partial-merge upsert, geo/address existing di eSuite "
            "TIDAK ikut ter-reset)."
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
            "kosong) kalau memang tidak mau update branch sama sekali -- key "
            "\"branchs\" TIDAK ikut dikirim (partial-merge, branch existing "
            "TIDAK ter-reset), dipakai untuk mass update SALESMAN SAJA masa "
            "pre-live saat branch customer sudah terbawa otomatis dari "
            "/sync/customers (instruksi user 7 September 2026). 🆕 SEKARANG "
            "INDEPENDEN dari salesman_ids (sebelumnya wajib diisi bersamaan). "
            "⚠️ GUARD: kalau dikosongkan & salesman_ids diisi, customer ini "
            "WAJIB SUDAH punya branch di eSuite (dari /sync/customers atau "
            "panggilan endpoint ini sebelumnya) -- kalau belum, request "
            "GAGAL EKSPLISIT (422 ValidationError, bukan diam-diam sukses). "
            "BELUM ditest live, test 1 customer dulu sebelum mass update."
        ),
    ),
    salesman_ids: str | None = Query(
        "202600003",
        description=(
            "OPSIONAL -- employee_id Salesman di eSuite (dipakai query param "
            "lookup GET /employee?employee_id=...), comma-separated kalau >1. "
            "DEFAULT 1 kode ('202600003') -- OVERRIDE SEMENTARA UNTUK MASA "
            "PRE-LIVE (instruksi user 5 September 2026), MENGGANTIKAN default "
            "3 kode ('202600002,202600003,202600004', instruksi user 28 "
            "Agustus 2026) selama pre-live. TODO: kembalikan ke 3 kode "
            "setelah go-live kalau tidak ada instruksi lain. Ganti manual "
            "kalau customer ini butuh salesman berbeda. Kosongkan (string "
            "kosong) kalau memang tidak mau kirim sales sama sekali. id+nama "
            "yang dikirim ke payload di-resolve OTOMATIS dari hasil lookup "
            "(id INTERNAL eSuite, BUKAN employee_id ini langsung). 🆕 "
            "SEKARANG INDEPENDEN dari branch_external_codes (sebelumnya "
            "wajib diisi bersamaan, instruksi user 7 September 2026) -- "
            "kosongkan branch_external_codes kalau mau mass update SALESMAN "
            "SAJA (branch existing tidak ikut ter-reset)."
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
    logic dengan POST /sync/customers), (2) latitude/longitude OPSIONAL
    INPUT (menggantikan data Odoo yang belum ada, kalau diisi), (3)
    branch+salesman OPSIONAL (sama logic dengan POST /mapping/customer-sales).

    coordinates kosong -- key "addresses" TIDAK ikut dikirim ke eSuite sama
    sekali (partial-merge upsert, dipakai untuk mass update sales-only masa
    pre-live, instruksi user 7 September 2026).

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

    🆕 7 September 2026: branch_external_codes & salesman_ids SEKARANG
    INDEPENDEN -- SEBELUMNYA kalau salah satu diisi, yang lain WAJIB ikut
    diisi (aturan eSuite dev 22 Agustus 2026: branchs[]/salesmans[] harus
    di-set bersamaan). Sekarang kalau salah satu dikosongkan, key terkait
    ("branchs" atau "salesmans") TIDAK dikirim sama sekali -- partial-merge
    upsert eSuite tidak akan reset yang sudah ada. Dipakai untuk mass update
    SALESMAN SAJA (kosongkan branch_external_codes) saat branch customer
    sudah otomatis terbawa dari /sync/customers (company_id Odoo, keputusan
    5 September 2026).

    ⚠️ GUARD mass update salesman-only: kalau branch_external_codes dikosongkan
    TAPI salesman_ids diisi, endpoint ini CEK DULU ke eSuite (GET /customers
    by external_code) apakah customer SUDAH punya sales.branchs[] -- kalau
    BELUM, request GAGAL EKSPLISIT dengan 422 ValidationError (bukan diam-diam
    kirim salesmans[] ke customer yang belum py branch, state jadi tidak
    lengkap di eSuite). Error ini jadi log kegagalan per customer_id saat
    dipakai mass update batch (mis. dari n8n) -- customer yang gagal berarti
    belum pernah di-/sync/customers atau belum di-upsert lewat endpoint ini
    dengan branch eksplisit.

    Arah "branchs-saja tanpa salesmans" sudah CONFIRMED LIVE (5 September
    2026) tapi lewat endpoint /sync/customers yang beda; arah "salesmans-saja
    tanpa branchs" di endpoint INI belum pernah dites live -- test 1 customer
    dulu sebelum mass update ke banyak customer.
    """
    return service.upsert(
        customer_id=customer_id,
        coordinates=coordinates,
        branch_external_codes=branch_external_codes,
        salesman_ids=salesman_ids,
        salesman_names=salesman_names,
    )
