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

**Belum dilakukan (next step, lihat poin 12):** re-run `/sync/product` ke sandbox untuk lihat jumlah produk baru yang ikut kekirim (kemungkinan lebih dari 731), dan pastikan tidak ada error baru dari produk-produk stok 0 yang sebelumnya belum pernah lewat proses mapping/push (mis. UOM asing yang belum ada di `UOM_MAPPING`, atau category yang belum ke-resolve).

## 8. Bug yang Sudah Diperbaiki Sesi-Sesi Lalu

**`product.category` di Odoo 19 tidak punya field `active`** -- domain filter `active=True` sudah dihapus dari `get_product_categories()`. Lihat `CONFIG_NOTES.md` bagian "Field Odoo yang Ternyata Beda dari Asumsi Umum".

## 9. Entity Product -- Status Saat Ini

**Kode sudah lengkap & tervalidasi end-to-end**, TODO currency/product-type/UOM dari v6 semua sudah kelar (lihat `CONFIG_NOTES.md`). Satu-satunya perubahan tersisa adalah revisi filter `free_qty` di poin 7 di atas -- perlu re-test, bukan berarti mundur ke status "belum dites".

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
│   └── product_sync_service.py          # ✅✅ tervalidasi, REVISI filter free_qty (5 Agustus 2026)
└── api/routes/
    ├── branch.py, warehouse.py, product_category.py       # tervalidasi
    └── product.py                       # docstring diupdate

CONFIG_NOTES.md                          # sejajar app/, bukan di dalamnya -- diupdate sesi ini
```

Semua lolos `python3 -m py_compile`.

## 12. TODO Berikutnya (urutan langsung lanjut)

1. **Re-run `POST /api/sync/product?event=upsert`** ke sandbox, catat jumlah produk baru (bandingkan vs 731 sebelumnya) dan cek `payload_sent` untuk produk-produk yang sebelumnya ke-exclude karena stok 0 -- pastikan tidak ada error mapping baru (UOM asing / category belum ke-resolve).
2. Kalau lancar, lanjut ke **Product Brand** & **UOM Level** kalau memang masih dibutuhkan (belum jelas apakah masih perlu -- perlu dicek apakah eSuite butuh `uom_levels` array/hierarki atau `base_uom` doang cukup).
3. Baru lanjut ke **Customer**.
4. Update `CONFIG_NOTES.md` tiap ada aturan bisnis baru -- terpisah dari update session transfer note.

## 13. Daftar Pertanyaan Sync dengan Tim IT eSuite

(Belum berubah dari v6 -- lihat isi lengkap di v6 kalau perlu.) Field opsional Branch, cara efisien dapetin kode wilayah administratif, beda `base_price`/`store_price` di Pricelist, NOO flow wajib/opsional, roadmap webhook vs polling, rate limit, retry safety, migrasi sandbox->production, field `parent` di Product Category/Brand.

## 14. Referensi Dokumen & Kode Eksternal

- Postman collection + environment DEV: prioritas utama.
- PDF eSuite Synchronization v2.0.0: prioritas kedua.
- Excel Master Data Go Live: referensi field saja.
- Kode `searchProduct`/`product_services.py` dari project bridge Odoo↔Cekat AI milik user -- sebelumnya jadi referensi filter Saleable+free_qty. **Catatan:** bagian filter `free_qty` dari referensi itu TIDAK lagi diikuti di bridge eSuite ini sejak revisi 5 Agustus 2026 (poin 7) -- dua project ini sekarang beda aturan bisnis di titik ini, jangan disamakan lagi kalau nanti balik lihat kode referensi itu.

---

**Cara pakai:** upload file ini + `CONFIG_NOTES.md` (atau cukup `bridge_app_v10.zip` yang sudah membundle keduanya) di chat baru, lanjut dari poin 12.
