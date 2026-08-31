from fastapi import APIRouter, Query
from app.core.exceptions import ValidationError
from app.services.product_sync_service import ProductSyncService


def _parse_product_ids(product_id: str) -> list[str]:
    """
    Terima id Odoo product.product MENTAH, comma-separated kalau >1 (mis.
    "9173,9603,9055") -- shortcut biar tidak perlu ketik prefix
    "ODOO-PROD-" manual tiap id. Balikin list external_code siap gabung
    ke `external_codes`. Pola validasi sama dgn `_parse_customer_ids()` di
    order_history.py (29 Agustus 2026, dibangun buat kebutuhan sama: test
    sync produk spesifik dari hasil order history, tanpa mass-upsert semua
    produk -- lihat order_history_import.md).
    """
    raw_parts = [p.strip() for p in product_id.split(",") if p.strip()]
    if not raw_parts:
        raise ValidationError("product_id tidak boleh kosong")

    codes = []
    for part in raw_parts:
        if not part.isdigit():
            raise ValidationError(
                f"product_id harus angka (id Odoo product.product), comma-separated kalau >1 -- '{part}' bukan angka valid",
                details={"invalid_value": part},
            )
        codes.append(f"ODOO-PROD-{part}")
    return codes

router = APIRouter()
service = ProductSyncService()


@router.post("/sync/product")
def sync_product(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
    limit: int | None = Query(
        default=None,
        description=(
            "TEMPORARY, buat diagnostik push full batch (7 Agustus 2026, pola "
            "sama dengan /sync/customers) -- kirim cuma N produk pertama, "
            "bukan semua. Kosongkan (default) untuk behavior normal (semua produk)."
        ),
    ),
    batch_size: int | None = Query(
        default=None,
        ge=1,
        description=(
            "OPSIONAL (12 Agustus 2026) -- pecah push jadi beberapa batch, "
            "pola sama dengan /sync/customers. Kosongkan untuk behavior lama "
            "(semua produk dalam 1 request, sudah tervalidasi ke 1247 produk)."
        ),
    ),
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL (12 Agustus 2026) -- upsert produk TERTENTU saja, "
            "comma-separated, format 'ODOO-PROD-{id}' (mis. "
            "ODOO-PROD-18374,ODOO-PROD-8857). Kosongkan untuk semua produk."
        ),
    ),
    product_id: str | None = Query(
        default=None,
        description=(
            "OPSIONAL (17 Agustus 2026, DIPERLUAS 29 Agustus 2026) -- "
            "shortcut upsert 1 ATAU BANYAK produk pakai Odoo product id "
            "langsung, comma-separated kalau >1 (mis. product_id=9173,9603), "
            "tanpa perlu tau format external_code. Efeknya sama persis "
            "dengan external_codes=ODOO-PROD-9173,ODOO-PROD-9603. Kalau "
            "external_codes JUGA diisi, external_codes yang dipakai dan "
            "product_id diabaikan."
        ),
    ),
    with_variant: bool = Query(
        default=True,
        description=(
            "Kalau True (default, sejak 14 Agustus 2026), tiap produk ikut "
            "sertakan 1 variant (1:1) LANGSUNG di payload /product "
            "(embedded, sesuai fix resmi vendor 13 Agustus 2026 -- bukan "
            "push /product-variant terpisah lagi seperti versi lama). "
            "Bridge otomatis resolve id variant existing dulu (by "
            "external_code) sebelum push, supaya tidak bikin variant "
            "duplikat kalau produk ini sudah pernah punya variant. "
            "Default True karena setiap produk WAJIB punya variant (kalau "
            "tidak, produk tidak tampil di dashboard sales eSuite) -- set "
            "False cuma untuk keperluan diagnostik/debug."
        ),
    ),
    include_payload: bool = Query(
        default=False,
        description=(
            "OPSIONAL (13 Agustus 2026) -- kalau True, response sertakan "
            "payload_sent penuh (data lengkap yang dikirim ke eSuite) per "
            "batch. Default False supaya Swagger tetap responsif untuk "
            "batch besar -- external_codes tetap selalu tampil. Nyalakan "
            "cuma pas perlu verifikasi payload detail (mis. debug 1-2 produk)."
        ),
    ),
):
    """
    Trigger manual sync Product: Odoo (product.product, category Saleable & list_price>0) -> eSuite.
    Produk dengan free_qty=0 tetap disync (revisi 5 Agustus 2026 -- tidak lagi jadi syarat exclude).
    Butuh Product Category sudah ke-push duluan (POST /sync/product-category).

    Upsert 1 ATAU BEBERAPA produk spesifik: pakai product_id=<id> atau
    product_id=<id1>,<id2>,... (shortcut, comma-separated) ATAU
    external_codes=ODOO-PROD-<id>,ODOO-PROD-<id2>,... -- keduanya sama,
    cuma produk-produk itu yang diupsert (bukan semua produk). Berguna
    buat sync produk SPESIFIK dari hasil order history dulu (lihat
    order_history_import.md) tanpa mass-upsert semua produk.
    """
    resolved_external_codes = external_codes or (
        ",".join(_parse_product_ids(product_id)) if product_id else None
    )
    return service.sync(
        event=event,
        limit=limit,
        batch_size=batch_size,
        external_codes=resolved_external_codes,
        with_variant=with_variant,
        include_payload=include_payload,
    )
