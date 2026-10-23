from fastapi import APIRouter, Query
from app.services.stock_sync_service import StockSyncService

router = APIRouter()
service = StockSyncService()


@router.post("/sync/stock-matrix")
def sync_stock_matrix(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL -- sync stok produk TERTENTU saja, comma-separated, "
            "format 'ODOO-PROD-{id}' (mis. ODOO-PROD-18374,ODOO-PROD-8857). "
            "Kalau diisi: cek eSuite CUMA utk id ini (cepat, targeted). Kalau "
            "dikosongkan: service tarik SEMUA halaman GET /product eSuite "
            "dulu buat nemuin produk mana yang punya variant valid (bisa "
            "makan waktu lebih lama tergantung jumlah produk di eSuite), "
            "baru query stok Odoo utk yang ketemu -- guard-nya SELALU jalan "
            "baik parameter ini diisi maupun tidak."
        ),
    ),
    product_id: int | None = Query(
        default=None,
        description=(
            "OPSIONAL -- shortcut sync 1 produk aja pakai Odoo product id "
            "langsung (mis. product_id=9169), tanpa perlu tau format "
            "external_code. Efeknya sama persis dengan "
            "external_codes=ODOO-PROD-9169 (targeted, lewat guard eSuite "
            "juga). Kalau external_codes JUGA diisi, external_codes yang "
            "dipakai dan product_id diabaikan."
        ),
    ),
    limit: int | None = Query(
        default=None,
        description=(
            "OPSIONAL -- diagnostik, kirim cuma N produk pertama PER WAREHOUSE "
            "(bukan limit gabungan). Kosongkan untuk behavior normal (semua produk)."
        ),
    ),
    batch_size: int | None = Query(
        default=None,
        ge=1,
        description=(
            "OPSIONAL -- pecah push jadi beberapa batch, pola sama dengan "
            "/sync/product & /sync/customers. Kosongkan untuk 1 batch semua baris sekaligus."
        ),
    ),
    include_payload: bool = Query(
        default=False,
        description="OPSIONAL -- kalau True, response sertakan payload_sent penuh per batch. Default False.",
    ),
):
    """
    Trigger manual sync Stock Matrix: Odoo (stock.quant, dihitung per
    warehouse in-scope) -> eSuite (/stock-matrix).

    Identifier pakai product_variant.code ("ODOO-PROD-{id}") & warehouse.code
    ("ODOO-WH-{id}") -- BUKAN id eSuite, TIDAK ADA external_code khusus
    entity ini. "on_hand"/"quantity" diisi FREE TO USE quantity (on-hand
    dikurangi reserved_quantity dan dikurangi stok dari lot yang sudah
    expired/dijadwalkan destroy -- KEPUTUSAN 17 Agustus 2026, lihat Decision
    Log & docstring OdooClient.get_stock_by_warehouse(), interim sampai ada
    keputusan lanjutan soal forecasted stock). Nilai bersifat absolute
    (set-to-target) & idempotent -- kirim ulang nilai sama tidak mengubah
    apa-apa.

    Sync 1 produk spesifik: pakai product_id=<id> (shortcut) ATAU
    external_codes=ODOO-PROD-<id> -- keduanya beneran targeted ke produk
    itu saja (bukan "kirim semua lalu filter"): guard eSuite cuma cek id
    ini, dan query stok Odoo juga cuma utk id ini.

    GUARD (eSuite-first): service ini cek eSuite DULU (GET /product, cari
    produk yang punya product-variant valid ter-embed) sebelum nyentuh Odoo
    sama sekali -- baru query stok Odoo SPESIFIK ke produk yang ketemu.
    Response include "verified_in_esuite" (jumlah produk yang lolos guard)
    & "skipped_not_found_in_odoo" (produk yang verified di eSuite tapi
    ternyata gak ketemu di query stok Odoo, mis. sudah di-archive). Butuh
    Product & Product Variant sudah ke-push duluan (POST /sync/product
    dengan with_variant=True) untuk produk yang mau di-sync stoknya.
    """
    resolved_external_codes = external_codes or (
        f"ODOO-PROD-{product_id}" if product_id is not None else None
    )
    return service.sync(
        event=event,
        external_codes=resolved_external_codes,
        limit=limit,
        batch_size=batch_size,
        include_payload=include_payload,
    )
