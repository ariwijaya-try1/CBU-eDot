from enum import Enum

from fastapi import APIRouter, Query

from app.services.mass_customer_sales_mapping_service import MassCustomerSalesMappingService


class MappingMode(str, Enum):
    """UPDATE 14 September 2026 -- Enum (bukan str+pattern) supaya Swagger
    render param `mode` sebagai select box, bukan input text bebas. SAMA
    pola dengan MappingMode di api/routes/customer_sales_mapping.py."""

    add = "add"
    reset = "reset"


router = APIRouter()
service = MassCustomerSalesMappingService()


@router.post("/mapping/mass-customer-sales")
def mass_map_customers_to_sales(
    salesman_ids: str = Query(
        ...,
        description=(
            "WAJIB -- employee_id Salesman di eSuite (dipakai query param "
            "lookup GET /employee?employee_id=...), comma-separated kalau "
            ">1 salesman. Tiap customer eligible HANYA dapat salesman yang "
            "branch-nya cocok sama branch customer itu (filter PER-CUSTOMER, "
            "aman kalau salesman_ids dicampur beda branch)."
        ),
    ),
    mode: MappingMode = Query(
        MappingMode.add,
        description=(
            "OPSIONAL, default 'add' -- salesman EXISTING di eSuite (per "
            "customer) DIPERTAHANKAN + salesman baru yang match branch "
            "ditambahkan (dedupe by id). 'reset' -- salesmans customer "
            "DITIMPA total, HANYA berisi salesman yang match branch dari "
            "request ini."
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
    di eSuite) ke SALESMAN sekaligus. Dibuat KHUSUS masa PRE-LIVE (utility
    sekali pakai buat percepat setup awal, BUKAN endpoint permanen jangka
    panjang seperti /mapping/customer-sales -- itu tetap dipakai utk mapping
    per-customer/per-batch spesifik setelah go-live).

    Alur:
    1. Resolve tiap salesman_ids -> id internal eSuite + name + branches[]
       (branch tempat salesman itu terdaftar di eSuite).
    2. Pull SEMUA customer dari eSuite (GET /customers, paginated).
    3. Filter LOKAL PER-CUSTOMER (bukan call tambahan per customer): tiap
       customer HANYA dapat subset salesman_ids yang branch-nya BENERAN
       cocok sama branch customer itu (sales.branchs[], yang SUDAH dibawa
       dari /sync/customers company_id auto-resolve ATAU endpoint upsert
       manual sebelumnya). Customer yang branch-nya tidak cocok SATU PUN
       salesman_ids, atau BELUM punya branch sama sekali -- DI-SKIP (dicatat
       di response["skipped"] dengan alasan "branch_mismatch" atau
       "customer_no_branch"), TIDAK menghentikan proses customer lain.
    4. Customer eligible di-push BATCH (partial-merge, payload MINIMAL --
       cuma `external_code` + `sales.salesmans[]`, branch existing customer
       TIDAK disentuh/di-reset sama sekali karena key "branchs" tidak ikut
       dikirim). 1 batch gagal TIDAK menghentikan batch lain (pola sama
       POST /sync/customers).

    🆕 UPDATE 14 September 2026 -- param `mode` ("add" default/"reset") +
    `salesman_id` tunggal jadi `salesman_ids` multi. Root cause: versi lama
    SELALU overwrite total salesmans[] existing (cuma kirim 1 salesman per
    push) -- run kedua dgn salesman lain jadi GANTIKAN, bukan NAMBAH,
    ditemukan user dari kasus nyata mapping bertahap 4 salesman. Lihat
    `MassCustomerSalesMappingService` docstring utk detail desain lengkap
    (opsi filter branch & default mode dikonfirmasi eksplisit oleh user).

    ⚠️ ASUMSI BELUM DIKONFIRMASI VENDOR: field "branches[]" di response GET
    /employee -- diambil dari skema POST /salesman (upsert) yang CONFIRMED
    punya field ini, TAPI belum ada bukti GET /employee mengembalikan field
    yang SAMA PERSIS. Kalau field ini kosong/nama beda di response nyata,
    endpoint GAGAL FAIL-FAST dengan pesan jelas (bukan diam-diam skip semua
    customer) -- cek response error-nya kalau terjadi. ⚠️ JUGA belum
    dikonfirmasi vendor: `sales.salesmans[]` ikut ke-return di GET
    /customers yang dipakai `mode="add"` -- cek response dry_run pertama
    pasca update ini (lihat `_salesmans_of()`).

    ⚠️ BELUM ditest live sama sekali (termasuk update mode/multi-salesman
    ini). WAJIB jalankan dry_run=true dulu (cek salesmen_resolved ke-resolve
    benar + jumlah eligible/skipped masuk akal + payload_preview per
    customer sudah gabung existing+baru dgn benar saat mode=add), baru
    jalankan dengan limit kecil (mis. 5) sebelum full run ke semua customer.

    UPDATE 14 September 2026 (2) -- `mode` sekarang Enum (`MappingMode`),
    tampil sebagai select box "add"/"reset" di Swagger, bukan text input
    bebas. Nilai yang dikirim ke service tetap str polos (mode.value).
    """
    return service.map_all_to_salesmen(
        salesman_ids=salesman_ids,
        mode=mode.value,  # Enum -> str polos, service tetap terima str seperti semula
        limit=limit,
        dry_run=dry_run,
        batch_size=batch_size,
    )
