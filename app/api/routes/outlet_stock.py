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
            "false untuk push beneran. ⚠️ Push menulis stok 0; isian "
            "sales yang ikut jadi 0 langsung dikembalikan -- baca "
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
            "OPSIONAL -- kalau True, response sertakan `payload` (body "
            "langkah 1) dan, saat push, response mentah eSuite + body "
            "langkah 2 per batch. Default False karena mode semua customer "
            "bisa puluhan ribu baris."
        ),
    ),
):
    """
    ## ⚠️ PERHATIAN -- MENULIS KE STOK OUTLET

    Hasil akhirnya: **produk yang belum ada di toko ditambahkan dengan stok
    0; produk yang sudah ada tidak berubah.**

    Endpoint eSuite `store-stock` selalu menimpa, dan bridge tidak bisa
    melihat stok toko sebelum mengirim. Karena itu tiap batch:

    1. dikirim `on_hand: 0` untuk tiap produk -- eSuite membuat baris yang
       belum ada dan melaporkan nilai semula (`on_hand_before`);
    2. **hanya** untuk produk yang nilai semulanya > 0 (stok tanpa tanggal
       kedaluwarsa yang sudah diisi sales), langsung dikirim lagi **nilai
       semula** itu.

    Stok **dengan tanggal kedaluwarsa** tidak tersentuh sama sekali (baris
    terpisah di eSuite). Akibatnya produk yang sudah diisi expired tampil
    sebagai 1 baris stok 0 tanpa expired + baris per tanggal expired.

    Yang perlu disadari sebelum `dry_run=false`:

    - isian sales tanpa expired sempat tampil **0** selama beberapa detik
      (di antara langkah 1 dan 2);
    - kalau langkah 2 gagal (sudah dicoba ulang 3x), proses **berhenti** dan
      isian itu **tertinggal di 0** -- lihat `restore_failed_items` (isinya
      nilai yang seharusnya dikembalikan) dan `abort_reason`;
    - kalau proses berhenti di tengah, sisanya ada di
      `unprocessed_item_count` -- lanjutkan dengan `limit` + `offset`.

    **Jalankan `dry_run=true` dulu**, cek `customer_count` / `item_count` /
    `batch_count`, baru `dry_run=false`. Aman dijalankan ulang.

    ---

    Siapkan LIST produk di stok toko/outlet eSuite (eWork: Outlet Detail ->
    Product Stock) lewat webhook `POST /v1/webhook/store-stock`.

    - **Sumber list produk:** produk yang pernah dibeli outlet -- riwayat
      `sale.order` Odoo dgn `invoice_status` "to invoice"/"invoiced".
    - **Yang dikirim:** `uom_level_code: ""` (satuan dasar), tanpa
      `expired_date`. Odoo tidak tahu stok fisik di outlet.
    - **Guard customer:** harus sudah ada di eSuite DAN punya sales branch
      (syarat endpoint). Yang tidak lolos masuk `skipped_customers`.
    - **Guard produk:** harus sudah ada di eSuite dgn variant valid. Yang
      tidak lolos masuk `skipped_products`, dgn `reason` spesifik dari
      Odoo (archived / bukan Saleable / list_price 0 = wajar, abaikan).
      Cuma yang `action_needed: true` yang perlu `POST /sync/product`.
    - **Batching:** maks 50 item per request, dikirim berurutan dgn jeda.
      Warehouse outlet dibuat otomatis oleh eSuite.

    Cara baca hasil push:

    - `pushed_count` -- item yang selesai;
    - `existing_stock_count` -- item yang ternyata sudah berisi stok (nilainya
      dikembalikan di langkah 2);
    - `esuite_summary.seed` -- ringkasan eSuite langkah 1 (`upserted` =
      baris baru dibuat / isian sales ikut jadi 0, `unchanged` = sudah ada
      dgn stok 0); `.restore` -- ringkasan langkah 2;
    - `failed_items` -- item yang ditolak eSuite di langkah 1.

    Mode semua customer bisa makan waktu lama (1-2 request + 1 detik jeda
    per 50 item) -- jalankan bertahap pakai `limit` + `offset`.
    """
    return service.sync(
        external_codes=external_codes,
        limit=limit,
        offset=offset,
        dry_run=dry_run,
        batch_size=batch_size,
        include_payload=include_payload,
    )
