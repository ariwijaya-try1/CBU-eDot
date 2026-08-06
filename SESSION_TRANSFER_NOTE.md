# Session Transfer Note v8 — Odoo → eSuite Bridge

> Dibuat 6 Agustus 2026. **Menggantikan v7.** Update sesi ini: (1) fix docstring salah di `branch.py` (nyebut `stock.warehouse`, seharusnya `res.company`), (2) `cost` di payload direvisi jadi eksplisit `0` -- **UI eSuite tetap tidak 0**. Postman collection dicek: `cost` field VALID & terdokumentasi resmi (bukan computed). Dugaan sekarang: kemungkinan bug backend eSuite yang treat `0` sebagai falsy (skip update). **Perlu 1 test manual dari user (kirim `cost: 1` langsung via Swagger) sebelum lanjut ubah kode** -- lihat poin 7c. Mulai sesi ini, **file ini + Postman collection dibundle di dalam zip kode**, sejajar `app/` dan `CONFIG_NOTES.md`.
>
> **PENTING:** ada file kedua yang WAJIB dibaca bareng ini: **`CONFIG_NOTES.md`**. File itu isinya aturan bisnis & konfigurasi PERMANEN (filter Saleable, currency, UOM, dll) yang beda fungsi dari catatan sesi ini -- jangan diskip.

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
| Branch (`/branches`) | `res.company`, filter `IN_SCOPE_COMPANY_NAMES` | ✅✅ Tervalidasi end-to-end. Docstring di `branch.py` sempat salah nyebut `stock.warehouse` -- **sudah difix sesi ini** (perilaku/kode tidak pernah salah, cuma teks docstring). |
| Warehouse (`/warehouse`) | `stock.warehouse`, filter company in-scope | ✅✅ Tervalidasi end-to-end |
| Product Category (`/product-category`) | `product.category`, filter `complete_name ilike "saleable"` | ✅✅ Tervalidasi |
| Product (`/product`) | `product.product` | ✅✅ Filter tervalidasi (1247 produk, 5 Agustus). 🟡 `cost` dikirim eksplisit 0 tapi **UI eSuite masih nampilin nominal (bukan bug kode kita)** -- dugaan computed di sisi eSuite, belum dikonfirmasi. **Belum bisa dianggap selesai**, lihat poin 7c/9. |
| Customer | `res.partner`? (belum ditentukan) | Belum dikerjakan |
| Pricelist | — | Belum, blocker RPC Odoo masih ada |
| Customer Group / Salesman | — | Belum |

`external_code` convention lengkap ada di `CONFIG_NOTES.md`.

## 7. Filter `free_qty` Dihapus dari Product Sync (5 Agustus 2026)

Produk `free_qty = 0` tetap disync & tampil di katalog eSuite (sebelumnya di-exclude). Sudah tervalidasi ke sandbox (1247 produk, `status 200 success`). Detail lengkap ada di `CONFIG_NOTES.md` bagian "Filter Data".

## 7b. Product Brand & UOM Level -- Dicek via Postman Collection (5 Agustus 2026)

- `/product-brand` & `/uom-level` (standalone): **di-skip**, tidak direferensikan dari payload manapun.
- `purchase_uom` & `uom_levels` ditambahkan ke payload `/product`, diisi dari `base_uom` yang sama (Odoo tidak punya konsep purchase UOM/packaging multi-level terpisah).
- Temuan bonus (belum ditindaklanjuti, baru relevan pas Stock Matrix): payload `/stock-matrix` referensi `product_variant.id`, bukan `product.id` -- berpotensi bentrok dengan keputusan no-variant. Lihat poin 7c dan `CONFIG_NOTES.md`.

## 7c. No-Variant Dikonfirmasi + Revisi `cost` (2 Tahap, 6 Agustus 2026)

**1. Stock Matrix / `product_variant` blocker:** keputusan lama (skip `/product-variant`, no-variant) **dikonfirmasi final** oleh user -- bukan cuma asumsi. Blocker Stock Matrix (butuh `product_variant.id`) masih terbuka, diselesaikan nanti (cek IT eSuite / cek `GET /product-variant` setelah produk di-push).

**2. `cost` -- revisi 2 tahap:**
- **Tahap 1 (awal sesi):** key `cost` dihapus total dari payload (instruksi boss: cost/harga beli tidak boleh dikirim, cuma `base_price` yang boleh).
- **Tahap 2 (ditemukan lewat testing user, akhir sesi):** produk yang re-upsert dengan payload tahap 1 ternyata **masih menampilkan nominal cost lama di UI eSuite**. Root cause: eSuite upsert kemungkinan besar **partial-merge**, bukan full-replace -- key yang tidak dikirim dianggap "tidak diubah", bukan "clear ke 0/null". Produk-produk itu sebelumnya sempat tersync pakai payload versi lama (batch 1247, masih include `cost` dari `standard_price`), jadi value lama itu yang nyangkut di eSuite.
- **Fix tahap 2 (diterapkan sesi ini):** `cost` dikirim eksplisit sebagai **`0` fixed value** (bukan dari `standard_price`).
- **⚠️ Tahap 3 -- fix tahap 2 tidak menyelesaikan masalah.** User re-test: `payload_sent` konfirmasi `"cost": 0` terkirim, tapi kolom "Cost" di UI eSuite tetap nampilin nominal lama (`Rp 44.345,6` buat produk `base_price: 55432`). Sempat diduga computed (rasio 80% ke base_price) -- **dugaan ini gugur** setelah cek Postman collection eSuite: field `cost` **valid & terdokumentasi resmi** di contoh body `POST /product` (`"cost": 1000, "base_price": 1200`), bukan field computed/read-only.
- **⚠️ Tahap 4 (dugaan baru, BELUM DIKONFIRMASI):** kemungkinan bug backend eSuite treat `0` sebagai falsy (pola umum: `if (payload.cost) update` -- gagal buat value `0`, dianggap sama dengan tidak dikirim). **Perlu 1 test manual dari user sebelum lanjut ubah kode**: kirim `POST /product` langsung via Swagger/Postman (bukan lewat bridge) dengan `"cost": 1` buat produk yang sama, cek apakah UI berubah jadi `Rp 1`. Kalau ya -> confirm falsy-skip, next step tanya IT eSuite cara resmi clear ke 0 (bukan masalah kode bridge). Kalau tidak berubah -> balik ke titik nol, perlu digali arah lain. **Masalah ini masih OPEN, jangan ubah kode `product_sync_service.py` lagi sebelum hasil test ini ada.**
- `standard_price` tetap diambil dari query Odoo (`odoo_client.py::get_products()`), cuma tidak pernah dipetakan ke payload.

## 8. Bug yang Sudah Diperbaiki

- `product.category` di Odoo 19 tidak punya field `active` -- domain filter dihapus dari `get_product_categories()`.
- Docstring `branch.py` salah nyebut sumber Branch (`stock.warehouse`) -- **difix sesi ini**, tidak ada perubahan behavior, murni teks.

Detail field-level ada di `CONFIG_NOTES.md` bagian "Field Odoo yang Ternyata Beda dari Asumsi Umum".

## 9. Entity Product -- Status Saat Ini

**Filter free_qty tervalidasi (1247 produk).** Payload sudah berubah 3x sejak validasi itu: (1) tambah `purchase_uom`+`uom_levels`, (2) hapus `cost`, (3) `cost` balik dikirim tapi sebagai `0` fixed. **Belum ada end-to-end test untuk bentuk payload final ini (poin 3).** Prioritas TODO #1.

## 10. File Konfigurasi: `CONFIG_NOTES.md`

Tetap terpisah dari session transfer note (aturan bisnis TETAP vs riwayat sesi). Diupdate sesi ini untuk bagian `cost`.

## 11. Progress Kode Saat Ini

```
app/
├── main.py                              # router branch+warehouse+product_category+product
├── core/
│   ├── config.py, exceptions.py, scope.py, security.py    # tidak berubah
├── clients/
│   ├── odoo_client.py                   # tidak berubah sesi ini
│   └── esuite_client.py                 # tidak berubah
├── services/
│   ├── branch_sync_service.py           # ✅✅ tervalidasi, tidak berubah
│   ├── warehouse_sync_service.py        # ✅✅ tervalidasi
│   ├── product_category_sync_service.py # ✅✅ tervalidasi
│   └── product_sync_service.py          # 🟡 cost sekarang eksplisit 0 (bukan dihapus) -- BELUM di-re-test
└── api/routes/
    ├── branch.py                        # docstring difix (res.company, bukan stock.warehouse)
    ├── warehouse.py, product_category.py, product.py  # tidak berubah sesi ini

CONFIG_NOTES.md                          # sejajar app/ -- diupdate sesi ini (bagian cost)
SESSION_TRANSFER_NOTE.md                 # file ini -- mulai sesi ini ikut dibundle di zip
```

Semua lolos `python3 -m py_compile`.

## 12. TODO Berikutnya (urutan langsung lanjut)

1. **[OPEN, PALING PRIORITAS, butuh aksi USER dulu] Test manual: kirim `POST /product` via Swagger/Postman langsung (bukan lewat bridge) dengan `"cost": 1`** buat produk yang sama, cek apakah UI eSuite berubah jadi `Rp 1`. Postman collection sudah dicek -- `cost` field valid & terdokumentasi resmi, bukan computed, jadi dugaan sekarang bug falsy-skip di backend eSuite (`0` dianggap "tidak dikirim"). **Jangan ubah kode `product_sync_service.py` lagi sebelum hasil test ini ada** -- sudah 2x tebakan meleset.
2. Setelah root cause dikonfirmasi & fix yang benar ketemu: **re-push semua produk yang sempat ke-upsert dengan payload lama** (cost dihapus total / cost 0 yang ternyata belum fix) supaya konsisten.
3. Flag ke tim data produk soal `base_price: 1` sebelum go-live (non-coding, lihat `CONFIG_NOTES.md`).
4. Lanjut ke **Customer** -- masih perlu ditentukan dulu sumber model Odoo-nya (`res.partner`? ada opsi lain?).
5. **Blocker Stock Matrix vs `/product-variant`** -- no-variant sudah final, cara teknis nyambungin Stock Matrix masih belum jelas. Belum sekarang.
6. Update `CONFIG_NOTES.md` tiap ada aturan bisnis baru -- terpisah dari session transfer note.

## 13. Daftar Pertanyaan Sync dengan Tim IT eSuite

(Belum berubah -- lihat isi lengkap di v6/v7 kalau perlu.) Field opsional Branch, cara efisien dapetin kode wilayah administratif, beda `base_price`/`store_price` di Pricelist, NOO flow wajib/opsional, roadmap webhook vs polling, rate limit, retry safety, migrasi sandbox->production, field `parent` di Product Category/Brand.
**Baru (relevan buat poin 1 di TODO, prioritas tinggi -- tunggu hasil test manual user dulu):** kalau test manual `cost: 1` konfirmasi falsy-skip (UI berubah jadi Rp 1), tanyakan ke IT eSuite: apa cara resmi buat clear field `cost` ke 0 lewat API upsert (misal ada konvensi kirim `null`, atau memang backend mereka perlu di-fix di sisi mereka)? Field `cost` sendiri sudah dikonfirmasi valid & terdokumentasi dari Postman collection (`"cost": 1000` di contoh body `POST /product`).

## 14. Referensi Dokumen & Kode Eksternal

- Postman collection + environment DEV: prioritas utama.
- PDF eSuite Synchronization v2.0.0: prioritas kedua.
- Excel Master Data Go Live: referensi field saja.
- Kode `searchProduct`/`product_services.py` dari project bridge Odoo↔Cekat AI milik user -- filter `free_qty` dari referensi itu **tidak lagi diikuti** di bridge eSuite ini sejak 5 Agustus 2026.

---

**Cara pakai:** upload `bridge_app_vXX.zip` (sudah membundle `app/` + `CONFIG_NOTES.md` + `SESSION_TRANSFER_NOTE.md`) di chat baru, lanjut dari poin 12.
