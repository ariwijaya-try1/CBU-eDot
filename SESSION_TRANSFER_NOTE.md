# Session Transfer Note v7 — Odoo → eSuite Bridge

> Dibuat 5 Agustus 2026. **Menggantikan v6.** Update: revisi aturan filter Product -- `free_qty > 0` DIHAPUS sebagai syarat exclude (produk stok 0 tetap disync). Tempel file ini di awal chat baru, bareng `CONFIG_NOTES.md`.
>
> **PENTING:** ada file kedua yang WAJIB dibaca bareng ini: **`CONFIG_NOTES.md`** (dibundle jadi 1 di dalam zip kode terbaru). File itu isinya aturan bisnis & konfigurasi PERMANEN (filter Saleable, currency, UOM, dll) yang beda fungsi dari catatan sesi ini — jangan diskip.

---

## 1. Scope App (FIXED)

Bridge murni: **Odoo 19 (SSOT) → eSuite/eDOT**, satu arah (push-only), tanpa pengecualian. Auth: API key statis. Tidak pakai JWT, slowapi, CORS.

## 2. Trigger Sync (FIXED)

Manual, 1 endpoint per entity. Response tiap endpoint selalu include `payload_sent` (data lengkap yang dikirim ke eSuite).

## 3. NOO Flow — Tidak di-handle fase awal.

## 4. Reference Cache / ID Mapping

Push eSuite tidak balikin ID -- reconcile via pull + cocokkan `external_code`. Posisi field `external_code` di response GET **beda-beda per entity** (lihat `CONFIG_NOTES.md`). Kode matching selalu dibuat defensif.

## 5. Prioritas Dokumen — FIXED

Postman collection + environment DEV > PDF.

## 6. Mapping Entity -- Status Semua yang Sudah Dikerjakan

| Entity eSuite | Sumber Odoo | Status |
|---|---|---|
| Branch (`/branches`) | `res.company`, filter `IN_SCOPE_COMPANY_NAMES` | ✅✅ Tervalidasi end-to-end |
| Warehouse (`/warehouse`) | `stock.warehouse`, filter company in-scope | ✅✅ Tervalidasi end-to-end |
| Product Category (`/product-category`) | `product.category`, filter `complete_name ilike "saleable"` | ✅✅ Tervalidasi |
| Product (`/product`) | `product.product` | ✅✅ Tervalidasi end-to-end (731 produk, 30/31 Juli) — **tapi filter berubah 5 Agustus, lihat poin 7. Perlu re-run untuk hitung ulang jumlah produk yang sekarang ikut kekirim.** |
| Customer | `res.partner`? (belum ditentukan) | Belum dikerjakan |
| Pricelist | — | Belum, blocker RPC Odoo masih ada |
| Customer Group / Salesman | — | Belum |

`external_code` convention lengkap ada di `CONFIG_NOTES.md`.

## 7. Revisi Sesi Ini (5 Agustus 2026): Filter `free_qty` Dihapus dari Product Sync

**Keputusan bisnis baru:** produk dengan `free_qty = 0` **tetap disync & tetap tampil** di katalog eSuite. Sebelumnya (v6 dan sebelumnya) produk stok 0 di-exclude total dari `/sync/product`.

**Alasan:** `free_qty = 0` diasumsikan bisa berarti stok belum sempat diupdate di Odoo, atau produk masih proses produksi/replenishment -- bukan berarti produk tidak boleh ditawarkan. Sales tetap perlu bisa menawarkan produk itu ke customer (mis. untuk pre-order), jadi produk tidak boleh hilang dari katalog eSuite hanya gara-gara angka stok sesaat kosong.

**Yang berubah di kode (`product_sync_service.py`):**
- Baris filter `products = [p for p in products if (p.get("free_qty") or 0) > 0]` **dihapus**.
- Pesan error saat list produk kosong disesuaikan (tidak lagi menyebut `free_qty > 0`).
- Docstring di `odoo_client.py::get_products()` dan `api/routes/product.py` diupdate biar tidak menyesatkan (masih menyebut `free_qty>0` di versi lama).

**Yang TIDAK berubah:**
- Filter category Saleable tetap.
- Filter `list_price > 0` (domain Odoo) tetap -- produk tanpa harga jual set masih di-exclude, itu beda topik dari stok.
- Field `free_qty` tetap diambil dari Odoo query (masih relevan untuk entity **Stock Matrix** yang belum dikerjakan -- field `free_to_use` di sana tetap harus diisi dari `free_qty` Odoo apa adanya, termasuk kalau nilainya 0). Cuma tidak lagi dipakai sebagai syarat include/exclude di sync `/product`.
- `CONFIG_NOTES.md` sudah diupdate sesi ini untuk mencerminkan aturan baru (bagian "Filter Data" & "Referensi eSuite untuk Entity Product").

**✅ Sudah di-re-run ke sandbox (5 Agustus 2026):** `synced_count: 1247` (naik dari 731), `esuite_response: status 200 "success"`, tidak ada error mapping category/UOM. Revisi filter dinyatakan **tervalidasi**.

**Temuan baru dari hasil re-run (bukan bug kode, catatan kualitas data):** cukup banyak produk di batch 1247 ini punya `base_price: 1` dan/atau `cost: 0` -- terlihat lebih menonjol sekarang karena produk `free_qty=0` yang baru ikut tersync sering juga belum sempat di-set harganya di Odoo. Sudah dicatat di `CONFIG_NOTES.md` bagian "Referensi eSuite untuk Entity Product". **Perlu ditindaklanjuti ke tim data produk sebelum go-live** -- di luar scope perbaikan kode, murni isu data source Odoo.

## 7b. Product Brand & UOM Level -- Dicek via Postman Collection (5 Agustus 2026)

User upload Postman collection + environment DEV eSuite. Hasil cek (search string di seluruh file JSON, bukan cuma baca 1-2 request):

- **`/product-brand`**: field `product_brand` **0 kemunculan** di manapun -- tidak direferensikan dari payload `/product` atau entity lain manapun. **Di-skip**, tidak perlu dibikin sync service.
- **`/uom-level`** (entity standalone, beda dari field `uom_levels`): juga tidak direferensikan oleh ID dari payload manapun. **Di-skip** juga.
- **TAPI ketemu 2 field yang seharusnya ada di payload `/product` tapi belum kita kirim:** `purchase_uom` (object `{id}`) dan `uom_levels` (array `{uom, qty, convertion}`). Sudah **ditambahkan** ke `product_sync_service.py::_to_esuite_payload()` -- diisi dari `base_uom` yang sama (qty=1, convertion=1), karena Odoo kami tidak punya konsep purchase UOM terpisah atau packaging multi-level. **Belum di-re-test ke sandbox** -- ini next TODO.
- **Temuan bonus, di luar scope tapi penting:** payload `/stock-matrix` referensi `product_variant.id`, BUKAN `product.id`. Berpotensi bentrok dengan keputusan "tidak pakai /product-variant sama sekali". Dicatat di `CONFIG_NOTES.md`, belum ditindaklanjuti -- baru relevan pas mulai kerjain Stock Matrix.

**File Postman collection & environment sudah tersimpan** di `/home/claude/bridge/eSuite-Webhook_postman_collection.json` (working dir sesi ini) -- kalau chat baru, minta user upload ulang kalau perlu cross-check field lain.

## 7c. Keputusan Bisnis Baru (6 Agustus 2026): No-Variant Dikonfirmasi + `cost` Dihapus dari Payload

**1. Stock Matrix / `product_variant` blocker (dari poin 7b) -- dikonfirmasi user, bukan ditemukan pertama kali:**
Tidak ada variant beneran secara praktek di operasional PT -- contoh: *Soft Dried Mango 500gr* vs *Soft Dried Mango 1x10x25gr (1 pack isi 10 pcs @ 25gr)* itu 2 produk terpisah, bukan 1 produk 2 varian. Keputusan lama (skip `/product-variant`) **dipertahankan secara eksplisit** -- kode variant **tidak akan dibuat**. Konsekuensi: blocker Stock Matrix (butuh `product_variant.id`) masih terbuka, perlu diselesaikan pakai cara lain nanti (cek ke IT eSuite / cek response `GET /product-variant` setelah produk di-push, siapa tau eSuite auto-generate 1 variant per product).

**2. `cost` DIHAPUS dari payload Product (instruksi boss):**
Data cost/harga beli **tidak boleh dikirim** ke eSuite -- cuma `base_price` (harga jual) yang boleh. **Ini konflik dengan keputusan sebelumnya** (cost dari `standard_price` sudah ada di kode & sempat tervalidasi di batch 1247 produk), tapi diterapkan langsung karena datang sebagai instruksi eksplisit, bukan ambigu.

**Yang berubah di kode (`product_sync_service.py`):**
- Key `"cost": product.get("standard_price") or 0` **dihapus** dari `_to_esuite_payload()`.
- `standard_price` TETAP diambil dari query Odoo (`odoo_client.py::get_products()`, field list tidak diubah) -- cuma tidak lagi dipetakan ke payload eSuite. Kalau nanti dibutuhkan lagi, datanya sudah ada tanpa perlu ubah query.
- `base_price` (dari `list_price`) sekarang **satu-satunya** field harga yang dikirim.

**Status test:** payload sekarang sudah berubah 2x sejak validasi 1247 produk (tambah `purchase_uom`/`uom_levels`, lalu hapus `cost`) -- **belum ada re-test end-to-end** untuk bentuk payload final ini. Next TODO.

## 8. Bug yang Sudah Diperbaiki Sesi-Sesi Lalu

**`product.category` di Odoo 19 tidak punya field `active`** -- domain filter `active=True` sudah dihapus dari `get_product_categories()`. Lihat `CONFIG_NOTES.md` bagian "Field Odoo yang Ternyata Beda dari Asumsi Umum".

## 9. Entity Product -- Status Saat Ini

**Kode lengkap, filter free_qty tervalidasi (1247 produk).** Tapi payload sudah 2x berubah setelah validasi itu (poin 7c) -- **belum end-to-end tested** untuk bentuk payload sekarang (`purchase_uom`+`uom_levels` ada, `cost` sudah tidak ada). Perlu re-run sebelum dianggap final/siap go-live.

## 10. File Konfigurasi: `CONFIG_NOTES.md`

Tetap dipertahankan terpisah dari session transfer note (aturan bisnis TETAP vs riwayat sesi). Diupdate sesi ini untuk bagian filter Product. Dibundle 1 zip sejajar `app/`.

## 11. Progress Kode Saat Ini (`bridge_app_v10.zip` -- berisi `app/` + `CONFIG_NOTES.md` sejajar)

```
app/
├── main.py                              # router branch+warehouse+product_category+product
├── core/
│   ├── config.py, exceptions.py, scope.py, security.py    # tidak berubah
├── clients/
│   ├── odoo_client.py                   # get_products() -- docstring diupdate (free_qty tidak lagi filter)
│   └── esuite_client.py                 # tidak berubah
├── services/
│   ├── branch_sync_service.py           # ✅✅ tervalidasi
│   ├── warehouse_sync_service.py        # ✅✅ tervalidasi
│   ├── product_category_sync_service.py # ✅✅ tervalidasi
│   └── product_sync_service.py          # ✅✅ tervalidasi (filter), 🟡 payload berubah 2x (purchase_uom/uom_levels ditambah, cost dihapus) -- BELUM di-re-test
└── api/routes/
    ├── branch.py, warehouse.py, product_category.py       # tervalidasi
    └── product.py                       # docstring diupdate

CONFIG_NOTES.md                          # sejajar app/, bukan di dalamnya -- diupdate sesi ini
```

Semua lolos `python3 -m py_compile`.

## 12. TODO Berikutnya (urutan langsung lanjut)

1. ~~Re-run `/sync/product`, validasi filter `free_qty`~~ ✅ selesai (1247 produk, sukses -- tapi payload sudah berubah lagi setelahnya, lihat poin 3).
2. ~~Cek Product Brand & UOM Level~~ ✅ selesai -- keduanya di-skip (tidak dipakai eSuite).
3. **Re-run `POST /api/sync/product?event=upsert` sekali lagi** ke sandbox -- ini yang PALING PRIORITAS sekarang, karena payload sudah berubah 2x sejak test 1247 produk terakhir (tambah `purchase_uom`/`uom_levels`, hapus `cost`). Cek `payload_sent` di response buat mastiin: (a) `uom_levels` diterima eSuite tanpa error, (b) `base_price` tetap kekirim benar tanpa `cost`.
4. Flag ke tim data produk soal `base_price: 1` sebelum go-live (non-coding, lihat CONFIG_NOTES -- `cost: 0` sudah tidak relevan lagi karena `cost` tidak dikirim).
5. Lanjut ke **Customer** -- masih perlu ditentukan dulu sumber model Odoo-nya (`res.partner`? ada opsi lain?).
6. **Blocker Stock Matrix vs `/product-variant`** (lihat CONFIG_NOTES) -- keputusan no-variant sudah dikonfirmasi final, tapi cara teknis nyambungin Stock Matrix masih belum jelas. Perlu diselesaikan sebelum mulai entity Stock Matrix (bukan sekarang).
7. Update `CONFIG_NOTES.md` tiap ada aturan bisnis baru -- terpisah dari update session transfer note.

## 13. Daftar Pertanyaan Sync dengan Tim IT eSuite

(Belum berubah dari v6 -- lihat isi lengkap di v6 kalau perlu.) Field opsional Branch, cara efisien dapetin kode wilayah administratif, beda `base_price`/`store_price` di Pricelist, NOO flow wajib/opsional, roadmap webhook vs polling, rate limit, retry safety, migrasi sandbox->production, field `parent` di Product Category/Brand.

## 14. Referensi Dokumen & Kode Eksternal

- Postman collection + environment DEV: prioritas utama.
- PDF eSuite Synchronization v2.0.0: prioritas kedua.
- Excel Master Data Go Live: referensi field saja.
- Kode `searchProduct`/`product_services.py` dari project bridge Odoo↔Cekat AI milik user -- sebelumnya jadi referensi filter Saleable+free_qty. **Catatan:** bagian filter `free_qty` dari referensi itu TIDAK lagi diikuti di bridge eSuite ini sejak revisi 5 Agustus 2026 (poin 7) -- dua project ini sekarang beda aturan bisnis di titik ini, jangan disamakan lagi kalau nanti balik lihat kode referensi itu.

---

**Cara pakai:** upload file ini + `CONFIG_NOTES.md` (atau cukup `bridge_app_v10.zip` yang sudah membundle keduanya) di chat baru, lanjut dari poin 12.
