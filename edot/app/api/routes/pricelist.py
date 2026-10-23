from fastapi import APIRouter, Query
from app.services.pricelist_sync_service import PricelistSyncService

router = APIRouter()
service = PricelistSyncService()


@router.post("/sync/pricelist")
def sync_pricelist(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
    ids: str | None = Query(
        default=None,
        description=(
            "OPSIONAL -- sync pricelist TERTENTU saja, comma-separated, id Odoo "
            "product.pricelist MENTAH (mis. 3,5,12 -- BUKAN format ODOO-PRICELIST-xxx, "
            "pakai id yang sama dari GET /odoo/pricelist). SANGAT DISARANKAN diisi "
            "dulu (1-2 pricelist) untuk test sebelum full push -- ini data HARGA, "
            "sebagian field payload (product[].id top-level, branch[].id) belum "
            "pernah divalidasi live ke eSuite. Kosongkan untuk semua pricelist."
        ),
    ),
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL (21 Agustus 2026) -- alternatif 'ids' di atas, format "
            "'ODOO-PRICELIST-{id}' (mis. ODOO-PRICELIST-2293), konsisten dengan "
            "entity lain. Kalau 'ids' JUGA diisi, external_codes yang dipakai."
        ),
    ),
    limit: int | None = Query(
        default=None,
        description="OPSIONAL -- diagnostik, proses cuma N pricelist pertama. Kosongkan untuk semua.",
    ),
    batch_size: int | None = Query(
        default=None,
        ge=1,
        description="OPSIONAL -- pecah push jadi beberapa batch, pola sama /sync/product & /sync/customers.",
    ),
    include_payload: bool = Query(
        default=False,
        description="OPSIONAL -- kalau True, response sertakan payload_sent penuh per batch. Default False.",
    ),
    customer_group_external_code: str | None = Query(
        default=None,
        description=(
            "WAJIB diisi KECUALI with_customer_group=False di bawah -- assign "
            "customer_group SPESIFIK ke SEMUA pricelist yang diproses panggilan ini "
            "(mapping MANUAL, 1 nilai per panggilan, pola sama "
            "customer_group_external_codes di /api/mapping/customer-grouping). "
            "Customer Group ini WAJIB sudah dibuat manual di UI eSuite (parent "
            "'Customer Type') dengan external_code ini. 🆕 4 September 2026: "
            "fallback lama ke 'All Customer Group' SUDAH DIHAPUS (id-nya tidak ada "
            "di eSuite PROD, root cause bug 'harga tertimpa' -- lihat "
            "pricelist_progress.md) -- kosongkan param ini TANPA with_customer_group=False "
            "akan GAGAL (ValidationError)."
        ),
    ),
    with_customer_group: bool = Query(
        default=True,
        description=(
            "OPSIONAL (BARU 5 September 2026, DEFAULT True = behavior automation/"
            "panggilan lain TIDAK BERUBAH). Set False utk SKIP customer_group SAMA "
            "SEKALI dari payload (key 'customer_group' tidak dikirim, bukan dikirim "
            "kosong []) -- dipakai utk test isolasi apakah customer_group[] beneran "
            "mandatory di eSuite, atau utk assign Price List LANGSUNG dari UI "
            "Customer eSuite tanpa customer_group Pricelist ini. Kalau False, param "
            "customer_group_external_code di atas DIABAIKAN (tidak wajib diisi)."
        ),
    ),
):
    """
    Trigger manual sync Pricelist: Odoo (product.pricelist + product.pricelist.item)
    -> eSuite (/pricelists). SEMUA pricelist & SEMUA company ikut (termasuk
    "Sunshine Agri Pratama" & pricelist tanpa company) -- keputusan scope
    dikonfirmasi user 18 Agustus 2026, lihat PricelistSyncService docstring
    untuk detail lengkap desain & asumsi yang masih perlu diverifikasi live.

    GUARD: produk yang belum punya product-variant valid di eSuite (lihat
    POST /sync/product with_variant=True) otomatis di-skip dari product[]
    pricelist manapun -- pricelist yang jadi 0 produk valid ikut di-skip
    (lihat skipped_pricelist_no_valid_product di response), TIDAK
    menggagalkan pricelist lain.

    Hanya baris harga dengan compute_price="fixed" yang didukung (match
    contoh nyata tab "Prices" Odoo) -- baris percentage/formula di-skip &
    dihitung di response (skipped_item_unsupported_compute_price).
    """
    return service.sync(
        event=event,
        ids=ids,
        external_codes=external_codes,
        limit=limit,
        batch_size=batch_size,
        include_payload=include_payload,
        customer_group_external_code=customer_group_external_code,
        with_customer_group=with_customer_group,
    )
