from fastapi import APIRouter, Query
from app.services.customer_sales_mapping_service import CustomerSalesMappingService

router = APIRouter()
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
    branch_external_codes: str = Query(
        ...,
        description=(
            "WAJIB -- external_code Branch (format 'ODOO-COMPANY-{id}', SAMA "
            "dengan /sync/branch), comma-separated kalau >1 branch. id+name "
            "eSuite di-RESOLVE OTOMATIS lewat pull GET /branches."
        ),
    ),
    salesman_ids: str = Query(
        ...,
        description=(
            "WAJIB -- employee_id Salesman di eSuite, comma-separated kalau "
            ">1 salesman. Nama di-RESOLVE OTOMATIS lewat GET /employee?"
            "employee_id=... (hindari typo) -- tidak perlu isi salesman_names."
        ),
    ),
    salesman_names: str | None = Query(
        None,
        description=(
            "OPSIONAL -- override manual nama Salesman kalau perlu (mis. GET "
            "/employee lagi down), comma-separated, urutan HARUS berpasangan "
            "1-1 dengan salesman_ids. Kalau dikosongkan (default), nama "
            "di-resolve otomatis dari eSuite per salesman_id."
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

    UPDATE 24 Agustus 2026: nama Salesman sekarang di-auto-resolve dari
    eSuite (GET /employee?employee_id=...) kalau salesman_names tidak diisi.
    """
    return service.map_to_sales(
        external_codes=external_codes,
        branch_external_codes=branch_external_codes,
        salesman_ids=salesman_ids,
        salesman_names=salesman_names,
    )
