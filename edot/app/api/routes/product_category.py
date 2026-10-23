from fastapi import APIRouter, Query
from app.services.product_category_sync_service import ProductCategorySyncService

router = APIRouter()
service = ProductCategorySyncService()


@router.post("/sync/product-category")
def sync_product_category(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL (21 Agustus 2026) -- upsert kategori TERTENTU saja, "
            "comma-separated, format 'ODOO-CAT-{id}' (mis. "
            "ODOO-CAT-1,ODOO-CAT-2). Kosongkan untuk semua kategori Saleable."
        ),
    ),
    limit: int | None = Query(
        default=None,
        description="OPSIONAL -- diagnostik, kirim cuma N kategori pertama. Kosongkan untuk semua.",
    ),
    with_parent: bool = Query(
        default=False,
        description=(
            "OPSIONAL (BARU 27 Agustus 2026, default False) -- kalau True, "
            "sekalian kirim field 'parent' (hierarki, mis. GROCERIES nested "
            "di bawah SALEABLE/OTHER) ke eSuite, bukan cuma nama kategori "
            "flat. Default OFF supaya behavior existing (dipakai automation "
            "lain) tidak berubah -- lihat komentar lengkap di service. "
            "Disarankan test dulu ke subset kecil pakai bareng "
            "'external_codes' sebelum jalanin ke semua kategori."
        ),
    ),
):
    """
    Trigger manual sync Product Category: Odoo (product.category) -> eSuite.

    Default (with_parent=False): kirim nama kategori LEAF saja, flat --
    behavior ASLI, tidak berubah.

    with_parent=True: tambahan fase ke-2 -- resolve & kirim field 'parent'
    (dikonfirmasi ada di skema resmi PDF section 9.2) supaya hierarki Odoo
    ('ALL / SALEABLE / OTHER / GROCERIES') ikut kebawa ke eSuite, bukan cuma
    nama leaf-nya. Lihat ProductCategorySyncService.sync() untuk detail
    lengkap (kenapa 2 fase, & catatan soal rollback).
    """
    return service.sync(
        event=event,
        external_codes=external_codes,
        limit=limit,
        with_parent=with_parent,
    )
