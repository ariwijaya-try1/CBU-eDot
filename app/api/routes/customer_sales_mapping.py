from fastapi import APIRouter, Query
from app.services.customer_sales_mapping_service import CustomerSalesMappingService

router = APIRouter()
# Router terpisah -- endpoint un-map ke-grup di Swagger tag "Un-Map" sendiri
# (bukan numpuk di "Mapping"), didaftarkan terpisah di main.py. Pola SAMA
# dengan deactivate_router (branch.py/customer.py/salesman_division.py).
unmap_router = APIRouter()
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
    """
    return service.map_to_sales(
        external_codes=external_codes,
        branch_external_codes=branch_external_codes,
        salesman_ids=salesman_ids,
        salesman_names=salesman_names,
    )


@unmap_router.post("/unmap/customer-sales")
def unmap_customer_sales(
    external_codes: str = Query(
        ...,
        description=(
            "WAJIB -- external_code Customer di eSuite yang mau dihapus "
            "mapping branch+salesman-nya, comma-separated. Diterima APA "
            "ADANYA (TIDAK divalidasi format)."
        ),
    ),
    clear_value: str = Query(
        default="null",
        pattern="^(null|empty_array)$",
        description=(
            "DIAGNOSTIK (25 Agustus 2026) -- cara mengosongkan "
            "branchs/salesmans di payload: 'null' (default, best-guess baru "
            "krn array kosong '[]' TERBUKTI diabaikan eSuite -- lihat RALAT "
            "di service) atau 'empty_array' (perilaku lama, buat "
            "dibandingkan). Ganti-ganti nilai ini utk cari tau mana yang "
            "beneran jalan, TANPA perlu ubah kode."
        ),
    ),
):
    """
    Hapus/kosongkan mapping Branch DAN Salesman dari Customer SEKALIGUS --
    kebalikan dari POST /mapping/customer-sales.

    RALAT 25 Agustus 2026 (temuan testing user): kirim array kosong
    (`sales.branchs: []`/`sales.salesmans: []`) TERNYATA diabaikan eSuite
    (diperlakukan sama seperti field tidak dikirim -- mapping lama TETAP
    ada). Default sekarang kirim `null`, BELUM dikonfirmasi vendor pasti
    berhasil -- gunakan `clear_value` utk test cepat lewat Swagger.

    TIDAK ADA opsi unmap branch/salesman secara terpisah -- info dev eSuite
    (22 Agustus 2026): branchs & salesmans di dalam object `sales` saling
    ikut ke-reset kalau salah satu di-set tanpa yang lain, jadi mengosongkan
    salah satu otomatis mengosongkan keduanya. Field Customer lain
    (name/addresses/invoice/dst) TIDAK ikut dikirim/direset.
    """
    return service.unmap_from_sales(external_codes=external_codes, clear_value=clear_value)
