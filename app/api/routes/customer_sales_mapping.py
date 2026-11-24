from enum import Enum

from fastapi import APIRouter, Query
from app.services.customer_sales_mapping_service import CustomerSalesMappingService


class MappingMode(str, Enum):
    """UPDATE 14 September 2026 -- Enum (bukan str+pattern) supaya Swagger
    render param `mode` sebagai select box, bukan input text bebas."""

    reset = "reset"
    add = "add"


# 24 Nov 2026 (permintaan user): pilihan branch di Swagger (multi-select) = kode + nama.
# Id res.company terkonfirmasi live GET /odoo/branch 24 Sep 2026 (company_scope).
# Value = "<kode> | <nama>" supaya nama tampil di select box; yang dikirim ke service hanya kodenya.
BRANCH_CHOICES = {
    "ODOO-COMPANY-1": "Cahaya Boga Utama, CV",
    "ODOO-COMPANY-2": "Sunshine Food and Co, CV",
    "ODOO-COMPANY-3": "Sunshine Agri Pratama, CV",
    "ODOO-COMPANY-4": "Sunshine Boga Utama, PT",
}
BranchChoice = Enum("BranchChoice", {code: f"{code} | {name}" for code, name in BRANCH_CHOICES.items()}, type=str)

router = APIRouter()
# 20 Nov 2026: endpoint POST /unmap/customer-sales (unmap_router) DIHAPUS --
# vendor konfirmasi (25 Agu) clear branchs/salesmans tidak bisa lewat API.
# Unmap salesman tertentu: POST /mapping/mass-customer-sales mode=remove.
service = CustomerSalesMappingService()


@router.post("/mapping/customer-sales")
def map_customer_sales(
    external_codes: str = Query(
        ...,
        description=(
            "WAJIB -- external_code Customer di eSuite yang mau di-mapping, "
            "comma-separated (mis. ODOO-PARTNER-39353,ODOO-PARTNER-1655). "
            "Diterima APA ADANYA (TIDAK divalidasi format)."
        ),
    ),
    branch_external_codes: list[BranchChoice] = Query(
        ...,
        description=(
            "WAJIB -- pilih 1-4 branch (multi-select, Ctrl/Cmd+klik utk >1). "
            "Format 'ODOO-COMPANY-{id}' (SAMA dgn /sync/branch); id+name eSuite "
            "di-RESOLVE OTOMATIS lewat pull GET /branches."
        ),
    ),
    salesman_ids: str = Query(
        ...,
        description=(
            "WAJIB -- employee_id Salesman di eSuite (dipakai sebagai query "
            "param lookup GET /employee?employee_id=...), comma-separated "
            "kalau >1 salesman. id+nama YANG DIKIRIM KE PAYLOAD selalu "
            "di-RESOLVE OTOMATIS dari hasil lookup itu (BUKAN employee_id "
            "ini langsung -- eSuite butuh id INTERNAL, beda dari employee_id)."
        ),
    ),
    salesman_names: str | None = Query(
        None,
        description=(
            "OPSIONAL -- override manual NAMA Salesman saja (mis. nama di "
            "eSuite mau dikoreksi paksa), comma-separated, urutan HARUS "
            "berpasangan 1-1 dengan salesman_ids. `id` TETAP selalu hasil "
            "resolve GET /employee (tidak bisa di-override/dilewati -- id "
            "internal eSuite tidak ada sumber lain). Kalau dikosongkan "
            "(default), nama JUGA di-resolve otomatis."
        ),
    ),
    mode: MappingMode = Query(
        MappingMode.reset,
        description=(
            "OPSIONAL, default 'reset' (PERILAKU LAMA, tidak breaking) -- "
            "'reset': salesmans customer DITIMPA total, HANYA berisi hasil "
            "resolve salesman_ids di request ini. 'add': salesman EXISTING "
            "di eSuite (per customer, hasil GET /customers) DIPERTAHANKAN + "
            "salesman baru dari salesman_ids ditambahkan (dedupe by id, "
            "tidak dobel kalau salesman sama sudah ada). Pakai 'add' kalau "
            "mau customer punya LEBIH DARI 1 salesman tanpa perlu tau/isi "
            "ulang id salesman lama secara manual."
        ),
    ),
):
    """
    Mass mapping Customer -> Branch + Salesman di eSuite SEKALIGUS (field
    `sales.branchs[]` + `sales.salesmans[]`).

    WAJIB isi branch DAN salesman di setiap panggilan -- info dev eSuite (22
    Agustus 2026): branchs & salesmans di dalam object `sales` HARUS di-set
    BERSAMAAN, kalau cuma isi salah satu, yang lain JADI BLANK di eSuite
    (BEDA dari partial-merge field top-level lain seperti name/status).

    GANTI endpoint lama /mapping/customer-salesman (yang cuma kirim
    salesmans, BERBAHAYA -- bisa nge-blank-in branch existing tanpa
    peringatan). Endpoint lama itu SUDAH TIDAK didaftarkan di main.py.

    UPDATE 24 Agustus 2026: nama Salesman di-auto-resolve dari eSuite (GET
    /employee?employee_id=...) kalau salesman_names tidak diisi.

    RALAT 24 Agustus 2026 (dikoreksi user): `id` yang dikirim ke
    sales.salesmans[] BUKAN employee_id (salesman_ids) -- WAJIB id INTERNAL
    eSuite, di-resolve otomatis dari GET /employee. GET /employee jadi WAJIB
    dipanggil di setiap request (termasuk saat salesman_names diisi manual).

    UPDATE 14 September 2026 -- param `mode` ("reset"/"add") untuk multi
    salesman per customer. Default "reset" (perilaku lama, tidak breaking).
    "add" mempertahankan salesman existing + menambahkan salesman baru
    (lihat CustomerSalesMappingService.map_to_sales() untuk detail).

    UPDATE 14 September 2026 (2) -- `mode` sekarang Enum (`MappingMode`),
    tampil sebagai select box "reset"/"add" di Swagger, bukan text input
    bebas. Nilai yang dikirim ke service tetap str polos (mode.value).
    """
    return service.map_to_sales(
        external_codes=external_codes,
        branch_external_codes=",".join(b.value.split(" | ")[0] for b in branch_external_codes),
        salesman_ids=salesman_ids,
        salesman_names=salesman_names,
        mode=mode.value,  # Enum -> str polos, service tetap terima str seperti semula
    )
