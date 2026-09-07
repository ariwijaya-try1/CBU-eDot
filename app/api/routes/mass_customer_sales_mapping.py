from fastapi import APIRouter, Query

from app.services.mass_customer_sales_mapping_service import MassCustomerSalesMappingService

router = APIRouter()
service = MassCustomerSalesMappingService()


@router.post("/mapping/mass-customer-sales")
def mass_map_customers_to_sales(
    salesman_id: str = Query(
        ...,
        description=(
            "WAJIB -- employee_id Salesman TUNGGAL di eSuite (dipakai query "
            "param lookup GET /employee?employee_id=...). CUMA 1 kode (bukan "
            "comma-separated) -- endpoint ini khusus map SEMUA customer ke 1 "
            "salesman yang SAMA sekaligus."
        ),
    ),
    limit: int | None = Query(
        None,
        description=(
            "OPSIONAL -- batasi jumlah customer ELIGIBLE (branch match) yang "
            "BENERAN di-push, buat test bertahap (mis. 5 atau 50 dulu) "
            "sebelum full run ke semua customer. Default None = semua "
            "customer eligible di-push sekaligus."
        ),
    ),
    dry_run: bool = Query(
        False,
        description=(
            "OPSIONAL -- True: cuma preview (hitung eligible/skipped + "
            "payload yang AKAN dikirim di response['payload_preview']), "
            "TIDAK ADA push ke eSuite sama sekali. WAJIB dicoba dulu sebelum "
            "full run (endpoint ini belum pernah ditest live). Default "
            "False."
        ),
    ),
    batch_size: int | None = Query(
        None,
        description=(
            "OPSIONAL -- override ukuran batch push (default 1000, sama "
            "pola dengan POST /sync/customers)."
        ),
    ),
):
    """
    🆕 7 September 2026, BARU -- Mass mapping SEMUA customer (yang sudah ada
    di eSuite) ke 1 SALESMAN yang sama sekaligus. Dibuat KHUSUS masa
    PRE-LIVE (utility sekali pakai buat percepat setup awal, BUKAN endpoint
    permanen jangka panjang seperti /mapping/customer-sales -- itu tetap
    dipakai utk mapping per-customer/per-batch spesifik setelah go-live).

    Alur:
    1. Resolve salesman_id -> id internal eSuite + name + branches[]
       (branch tempat salesman ini terdaftar di eSuite).
    2. Pull SEMUA customer dari eSuite (GET /customers, paginated).
    3. Filter LOKAL (bukan call tambahan per customer): customer ELIGIBLE
       kalau ada branch customer (sales.branchs[], yang SUDAH dibawa dari
       /sync/customers company_id auto-resolve ATAU endpoint upsert manual
       sebelumnya) yang SAMA dengan salah satu branch salesman. Customer
       yang branch-nya BEDA, atau BELUM punya branch sama sekali -- DI-SKIP
       (dicatat di response["skipped"] dengan alasan "branch_mismatch" atau
       "customer_no_branch"), TIDAK menghentikan proses customer lain.
    4. Customer eligible di-push BATCH (partial-merge, payload MINIMAL --
       cuma `external_code` + `sales.salesmans[]`, branch existing customer
       TIDAK disentuh/di-reset sama sekali karena key "branchs" tidak ikut
       dikirim). 1 batch gagal TIDAK menghentikan batch lain (pola sama
       POST /sync/customers).

    ⚠️ ASUMSI BELUM DIKONFIRMASI VENDOR: field "branches[]" di response GET
    /employee -- diambil dari skema POST /salesman (upsert) yang CONFIRMED
    punya field ini, TAPI belum ada bukti GET /employee mengembalikan field
    yang SAMA PERSIS. Kalau field ini kosong/nama beda di response nyata,
    endpoint GAGAL FAIL-FAST dengan pesan jelas (bukan diam-diam skip semua
    customer) -- cek response error-nya kalau terjadi.

    ⚠️ BELUM ditest live sama sekali. WAJIB jalankan dry_run=true dulu (cek
    salesman_branch_ids ke-resolve benar + jumlah eligible/skipped masuk
    akal), baru jalankan dengan limit kecil (mis. 5) sebelum full run ke
    semua customer.
    """
    return service.map_all_to_one_salesman(
        salesman_id=salesman_id,
        limit=limit,
        dry_run=dry_run,
        batch_size=batch_size,
    )
