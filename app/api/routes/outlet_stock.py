from fastapi import APIRouter, Query
from app.services.outlet_stock_sync_service import OutletStockSyncService

router = APIRouter()
service = OutletStockSyncService()


@router.post("/sync/outlet-stock")
def sync_outlet_stock(
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL -- outlet/customer TERTENTU saja, comma-separated, "
            "format 'ODOO-PARTNER-{id}' (mis. ODOO-PARTNER-1655,ODOO-PARTNER-39353). "
            "Kosongkan = SEMUA customer Odoo (customer_rank > 0, active)."
        ),
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        description=(
            "OPSIONAL -- proses cuma N customer (setelah offset, urut id Odoo). "
            "Pakai bareng offset utk jalan bertahap, mis. limit=100&offset=0, "
            "lalu offset=100, dst."
        ),
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="OPSIONAL -- lewati N customer pertama (urut id Odoo). Default 0.",
    ),
    dry_run: bool = Query(
        default=True,
        description=(
            "DEFAULT TRUE (beda dari endpoint sync lain) -- cuma hitung & "
            "tampilkan apa yang AKAN dikirim, TIDAK push ke eSuite. Isi "
            "false untuk push beneran. ⚠️ Push MENIMPA stok outlet tanpa "
            "tanggal kedaluwarsa yang sudah diisi sales menjadi 0 -- baca "
            "peringatan di deskripsi endpoint."
        ),
    ),
    batch_size: int | None = Query(
        default=None,
        ge=1,
        le=50,
        description="OPSIONAL -- item per request ke eSuite. Default & maksimal 50 (batas eSuite).",
    ),
    include_payload: bool = Query(
        default=False,
        description=(
            "OPSIONAL -- kalau True, response sertakan field `payload` (body "
            "persis yang dikirim/akan dikirim). Default False karena mode "
            "semua customer bisa puluhan ribu baris."
        ),
    ),
):
    """
    ## ⚠️ PERINGATAN -- MENIMPA STOK OUTLET

    Endpoint eSuite `store-stock` **menimpa** stok (bukan menambah). Semua
    baris dikirim `on_hand: 0` tanpa `expired_date`, sehingga:

    - stok outlet **tanpa tanggal kedaluwarsa** yang sudah diisi sales untuk
      produk yang sama **di-reset ke 0**;
    - stok yang diisi sales **dengan tanggal kedaluwarsa** tidak tersentuh
      (dicatat eSuite sebagai baris terpisah);
    - produk yang tidak dikirim tidak berubah.

    Bridge belum bisa mengecek stok outlet yang sudah ada, jadi tidak ada
    baris yang dilewati otomatis. **Jalankan `dry_run=true` dulu**, cek
    `customer_count` / `item_count` / `batch_count`, baru `dry_run=false`.

    ---

    Siapkan LIST produk di stok toko/outlet eSuite (eWork: Outlet Detail ->
    Product Stock) lewat webhook `POST /v1/webhook/store-stock`.

    - **Sumber list produk:** produk yang pernah dibeli outlet -- riwayat
      `sale.order` Odoo dgn `invoice_status` "to invoice"/"invoiced".
    - **Nilai yang dikirim:** `on_hand: 0`, `uom_level_code: ""` (satuan
      dasar), tanpa `expired_date`. Odoo tidak tahu stok fisik di outlet.
    - **Guard customer:** harus sudah ada di eSuite DAN punya sales branch
      (syarat endpoint). Yang tidak lolos masuk `skipped_customers`.
    - **Guard produk:** harus sudah ada di eSuite dgn variant valid. Yang
      tidak lolos masuk `skipped_products`.
    - **Batching:** maks 50 item per request, dikirim berurutan dgn jeda.
      Warehouse outlet dibuat otomatis oleh eSuite.

    `pushed_count` = jumlah item di batch yang call-nya sukses (HTTP 2xx).
    Itu BELUM tentu semua item tersimpan -- cek `batches[].esuite_response`
    dan verifikasi di eWork.

    Mode semua customer bisa makan waktu lama (1 detik jeda per 50 item) --
    jalankan bertahap pakai `limit` + `offset`.
    """
    return service.sync(
        external_codes=external_codes,
        limit=limit,
        offset=offset,
        dry_run=dry_run,
        batch_size=batch_size,
        include_payload=include_payload,
    )
