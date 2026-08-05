# Business Rules & Configuration Notes — Odoo → eSuite Bridge

> File ini beda fungsi dari Session Transfer Note. Transfer note isinya riwayat
> keputusan per sesi ngobrol (berubah tiap kali ada progress). File ini isinya
> **aturan bisnis & konfigurasi tetap** yang berlaku terus, apapun sesinya —
> update file ini setiap kali ada aturan bisnis baru yang dikonfirmasi, terlepas
> dari sedang ngerjain entity apa.

---

## Filter Data

### Produk yang boleh disync ke eSuite
**Aturan (REVISI 5 Agustus 2026):** produk dengan category **"Saleable"** DAN **`list_price > 0`** disync ke eSuite. **`free_qty` TIDAK LAGI jadi syarat exclude** — produk dengan `free_qty = 0` tetap disync & tetap tampil di katalog eSuite.

- **Alasan bisnis revisi:** `free_qty = 0` bisa berarti stok belum sempat diupdate di Odoo, atau produk sedang proses produksi/replenishment — bukan berarti produk itu tidak boleh ditawarkan. Sales tetap boleh menawarkan produk tsb ke customer (mis. untuk pre-order/indent), jadi produk tidak boleh hilang dari katalog eSuite hanya karena stok sesaat kosong.
- **Product Category** (`get_product_categories()` di `odoo_client.py`): difilter `complete_name ilike "saleable"` — jadi cuma kategori di bawah pohon "Saleable" yang disync. **Terkonfirmasi** format asli di Odoo: `"ALL / SALEABLE / SAP / OLIVIVERO / IQF"` (contoh) — `categ_id` adalah many2one, muncul sebagai `[id, complete_name]` di query Odoo (gotcha m2o yang sudah diketahui).
- **Product** (`get_products()` di `odoo_client.py` + `product_sync_service.py`): filter yang berlaku sekarang cuma:
  1. `categ_id` masuk ke cabang Saleable (domain `("categ_id.complete_name", "ilike", "saleable")` atau setara).
  2. `list_price > 0` (domain Odoo).
  - ~~`free_qty > 0`~~ — **dihapus**, sudah tidak dipakai sebagai filter exclude sejak 5 Agustus 2026.
- Field yang relevan dari sample response nyata: `id`, `name`, `free_qty`, `categ_id` (`[id, display_name]`). `free_qty` tetap diambil dari Odoo (masih dipakai untuk entity Stock Matrix di bawah), cuma tidak lagi dipakai untuk exclude produk dari sync `/product`.

### Stok yang direfleksikan ke eSuite
**Aturan:** kuantitas stok yang dikirim ke eSuite itu **"Free to Use"**, bukan on-hand/total stock.

- Field Odoo: **`free_qty`** (ada di `stock.quant` / computed di level `product.product`).
- Berlaku untuk entity **Stock Matrix** (`/stock-matrix`, belum dikerjakan) — field `free_to_use` di payload eSuite harus diisi dari `free_qty` Odoo, bukan dari `qty_available` (on-hand) atau `virtual_available` (forecasted).

## Struktur Produk & Variant

**Terkonfirmasi dari data nyata: tidak ada konsep variant di Odoo kami.** Tiap ukuran/kemasan produk yang berbeda = `product.product` record TERPISAH dengan `id` sendiri-sendiri, bukan 1 produk dengan attribute/variant. Contoh:
- `OLIVIVERO Freeze Dried Mango 100g` (id 19157) — dijual per **pcs** (1 unit = 100g)
- `OLIVIVERO Freeze Dried Mango 1x32x25g` (id 18952) — dijual per **pack** (1 pack isi 32 pcs @ 25g)

Dua-duanya produk "sama" secara nama dasar, tapi punya `id` Odoo masing-masing.

**Konsekuensi buat entity Product di eSuite:** cukup pakai endpoint `/product` biasa untuk semua, **TIDAK perlu** entity `/product-variant`. Ini lebih simpel dari rencana awal.

**Catatan hati-hati:** pola kemasan (`1x32x25g`, `1x10x1kg`, dst) itu keliatan encoded di **nama produk** (teks), bukan di field terstruktur. Kalau nanti butuh angka konversi UOM (`uom_levels.qty`/`convertion` di payload eSuite) dari sini, JANGAN parsing dari teks nama produk (fragile, gampang salah baca format) — cek dulu apakah Odoo punya field terstruktur buat ini (misal `product.packaging`, atau UOM per produk yang udah didefinisikan), baru pakai teks nama sebagai fallback terakhir kalau memang nggak ada.

## Endpoint Referensi yang Sudah Ada (Bridge Odoo ↔ Cekat AI)

Ada API terpisah (bukan bagian dari project bridge eSuite ini) yang sudah dibuat user sebagai jembatan Odoo ↔ Cekat AI, punya endpoint `searchProduct` yang query `product.product` dengan filter Saleable + `free_qty > 0`, return `{id, name, free_qty, categ_id}`.

**Penting:** bridge eSuite ini TIDAK butuh fitur "search by keyword" — sales search produk dilakukan di dashboard eSuite, terhadap data yang sudah dipopulate ke sana, bukan live query ke Odoo. Yang dibutuhkan dari endpoint `searchProduct` di atas cuma bagian **domain filter Odoo-nya** (Saleable + free_qty > 0) untuk dipakai ulang di `get_products()` versi "ambil semua" (tanpa parameter keyword) — pola yang sama seperti `get_companies()`/`get_warehouses()`/`get_product_categories()` yang sudah ada.

Didefinisikan di `core/scope.py` → `IN_SCOPE_COMPANY_NAMES`:
- **Cahaya Boga Utama, CV**
- **Sunshine Food and Co, CV**

2 badan usaha lain (agro & branch office luar kota) di luar scope, tidak disync.

---

## Referensi eSuite untuk Entity Product

**Currency:** cuma **IDR**. Sales cuma ke customer/calon customer (transaksi ke vendor pakai USD, tapi itu di luar scope bridge ini — bridge cuma untuk data yang dipakai sales, bukan pembelian). **Sudah diisi:** `id: "6a695cc1917e8fc836359505"`.

**Product Type:** cuma **"Goods"** — semua produk barang fisik, tidak ada services. **Catatan:** eSuite tidak punya opsi literal "Goods", pilihannya: Fixed Asset, Competitor, Consumable, Service, Service and Consumable, Storable Product. **Dipilih "Storable Product"** (`id: "664191ad236dfcd5a4000001"`, code `PD-003`) karena produk kami punya stok yang ditrack (`free_qty`) — sesuai konsep "storable" di Odoo sendiri (beda dari "Consumable" yang artinya stok tidak ditrack). Kalau ternyata salah pilih, gampang diganti, cuma ubah 1 constant.

**UOM (`base_uom`):** diambil dari field asli Odoo `uom_id` (BUKAN di-parsing dari teks nama produk seperti `"1x32x25g"` — itu rawan salah baca kalau format nama bervariasi). **Terkonfirmasi & SELESAI** — cuma 2 UOM yang dipakai di seluruh 731 produk Saleable: `units` dan `kg`. Dugaan awal "pcs"/"pack" (istilah bisnis di awal diskusi) ternyata TIDAK dipakai literal sebagai `uom_id` di Odoo. Mapping final di `UOM_MAPPING`:
```python
UOM_MAPPING = {
    "units": {"id": "664219e2236dfcd5a400001a"},  # UM-0001
    "kg": {"id": "664219e2236dfcd5a4000015"},      # UM-0006 Kilogram
}
```

**`purchase_uom` & `uom_levels` (REVISI 5 Agustus 2026, dicek langsung dari Postman collection eSuite):** dua field ini ADA di skema resmi `POST /product` (contoh payload di collection), tapi sebelumnya belum dikirim di payload kita — push tetap sukses (jadi optional secara teknis), tapi ditambahkan sekarang biar payload lengkap/aman untuk kebutuhan konversi unit ke depan (mis. Sales Order line qty).
- `purchase_uom`: diisi sama dengan `base_uom` — Odoo kami tidak punya konsep purchase UOM terpisah dari sales/base UOM.
- `uom_levels`: array 1 level, `{uom: base_uom, qty: 1, convertion: 1}` — karena tidak ada packaging multi-level di data kami (tiap ukuran/kemasan = `product.product` id sendiri-sendiri, bukan 1 produk dengan beberapa level konversi; lihat bagian "Struktur Produk & Variant").

**`cost`** (harga beli) diambil dari `standard_price` Odoo. **`base_price`** (harga jual) dari `list_price`.

**⚠️ Catatan kualitas data (bukan bug kode):** ditemukan beberapa produk dengan `base_price: 1` atau `cost: 0` di hasil push nyata — kemungkinan `list_price`/`standard_price` belum di-set benar di Odoo untuk produk-produk itu. Perlu dicek ke tim yang pegang data produk sebelum go-live, supaya harga di dashboard sales tidak salah tampil.

**STATUS ENTITY PRODUCT: ✅ SELESAI, TERVALIDASI END-TO-END.** Riwayat angka: 731 produk (30/31 Juli 2026, sebelum revisi filter `free_qty`) → **1247 produk** (5 Agustus 2026, setelah revisi — produk `free_qty=0` sekarang ikut tersync). Push ke sandbox `esuite_response: status 200 "success"`, tidak ada error mapping category/UOM untuk 1247 produk tsb. **Payload `purchase_uom`/`uom_levels` ditambahkan setelah validasi ini — belum di-re-test ke sandbox**, lihat TODO di session transfer note.

**⚠️ Update catatan kualitas data (5 Agustus 2026):** setelah revisi filter, jumlah produk dengan `base_price: 1` dan/atau `cost: 0` di hasil push nyata jadi lebih banyak kelihatan (contoh: beberapa varian OLIVIVERO Freeze Dried, KANEKA Filling tertentu, KIMBO Bites Sosis Ayam, VIGO Sosis Ayam 20 Pcs, JAVA BITE Dried Mango Tropical Paradise, SUN FOOD Black Salt, ELATE Basmati Rice 25kg, SUNBAY Sterilised Milk & Krimer Kental Manis, DIM SUM Mini Veg Risoles, VOYA Syrup Palm Sugar, NOEL Tapas De Espana, dll). Dugaan: produk stok 0 sering juga belum sempat di-set harganya di Odoo — dua masalah data yang berkorelasi. **Perlu dicek ke tim data produk sebelum go-live** supaya harga `Rp 1` tidak salah tampil ke sales/customer di dashboard eSuite.

---

## Product Brand & UOM Level — DICEK, TIDAK DIPERLUKAN untuk Product (5 Agustus 2026)

Dicek langsung dari Postman collection eSuite (search string di seluruh file JSON):
- **`product_brand`**: **0 kemunculan** di manapun di collection — field ini TIDAK direferensikan dari payload `POST /product` (atau entity lain manapun yang sudah dicek). Entity `/product-brand` (`GET`/`POST`) memang ada sebagai master data standalone (`external_code`, `name`, `status`), tapi tidak ada link dari Product ke Brand di skema yang kelihatan.
- **`uom-level` (entity standalone, `POST /uom-level` dengan `external_code`/`name`/`description`/`status`)**: TIDAK direferensikan oleh ID dari payload Product manapun. Ini beda dari field `uom_levels` (huruf kecil, plural, array) yang ADA di dalam payload `/product` — dua hal yang namanya mirip tapi TIDAK berhubungan. `uom_levels` di payload Product isinya array `{uom, qty, convertion}` langsung, bukan referensi ke entity `/uom-level`.

**Kesimpulan:** dua-duanya (`/product-brand` dan `/uom-level`) **di-skip dulu**, tidak perlu dibikin sync service-nya sekarang — tidak ada dependency dari entity Product. Kalau nanti ternyata dashboard eSuite butuh brand utk filter/grouping (bukan cuma soal push berhasil), baru direvisit — tapi dari sisi API contract, tidak wajib.

---

## ⚠️ Temuan Penting: Stock Matrix Butuh `product_variant`, Bukan `product` (5 Agustus 2026)

Dicek dari contoh payload `POST /stock-matrix` di Postman collection:
```json
{
  "external_code": "PM-stk",
  "product_variant": {"id": "..."},
  "uom": {"id": "..."},
  "location": {"id": "..."},
  "free_to_use": 10,
  "on_hand": 10,
  "quantity": 10
}
```
Field-nya `product_variant`, **BUKAN** `product`. Ini berpotensi bentrok dengan keputusan yang sudah diambil di bagian "Struktur Produk & Variant" (tidak pakai `/product-variant` sama sekali, cukup `/product`). Kalau Stock Matrix di eSuite memang HARUS nempel ke `product_variant` (bukan `product`), berarti nanti pas ngerjain entity Stock Matrix, kita mungkin tetap perlu push `/product-variant` (mungkin 1:1 dengan tiap `/product`, sekadar biar ada ID buat direferensikan Stock Matrix) — meskipun secara bisnis tidak ada konsep "variant" beneran di data kami.

**Belum ditindaklanjuti** — di luar scope Product/Brand/UOM Level, dicatat sebagai blocker/pertanyaan buat pas mulai kerjain Stock Matrix nanti. Kemungkinan juga perlu ditanyakan ke tim IT eSuite.

---

## External Code Convention

Pola: `ODOO-{SINGKATAN-ENTITY}-{id_odoo}`

| Entity eSuite | Sumber Odoo | Convention |
|---|---|---|
| Branch | `res.company` | `ODOO-COMPANY-{id}` |
| Warehouse | `stock.warehouse` | `ODOO-WH-{id}` |
| Product Category | `product.category` | `ODOO-CAT-{id}` |
| Product | `product.product` | `ODOO-PROD-{id}` |

*(Ditambah baris baru tiap ada entity baru yang selesai dikerjakan.)*

---

## Field Odoo yang Ternyata Beda dari Asumsi Umum

Catatan teknis biar nggak keulang salah asumsi:

- **`product.category` tidak punya field `active`** — beda dari `stock.warehouse`/`res.company` yang punya. Jangan pakai filter `active=True` untuk model ini.

---

## Struktur Response GET (Pull) eSuite — Posisi/Keberadaan Field Bisa Beda per Entity

- **Branch**: `external_code` posisinya nested di `basic_info.external_code`.
- **Warehouse**: `external_code` posisinya **top-level**.
- **Product Category**: `external_code` **TIDAK ADA SAMA SEKALI** di response GET (dicek langsung dari data nyata) — beda dari Branch/Warehouse yang cuma beda posisi, ini beneran nggak ada. Struktur record-nya juga beda: info kategori asli nested di dalam key `product_category` (bukan di top-level record), dan top-level `id` record itu BUKAN id kategori (kemungkinan itu id relasi/mapping company-category). Konsekuensi: matching untuk entity ini terpaksa pakai `product_category.name`, bukan `external_code` seperti pola lain. Ada risiko tabrakan kalau ada 2 kategori dengan nama leaf sama persis.
- **Kesimpulan (diperkuat):** jangan asumsikan struktur konsisten antar entity, bahkan jangan asumsikan field yang sama pasti ADA. Selalu cek response pull nyata dulu sebelum nulis logic matching untuk entity baru.

---

## Auth & Kredensial (Sandbox DEV)

```
ESUITE_BASE_URL=https://openapi-esuite.edot-dev.com/v1/webhook
ESUITE_CLIENT_ID=6a6973780f67da70ae33824a
ESUITE_CLIENT_SECRET=Password123!
```
Sumber: Postman collection + environment DEV (prioritas di atas PDF dokumentasi — PDF sempat kasih base URL yang usang/salah).

Semua Branch (termasuk bawaan sistem eSuite) berada di 1 tenant yang sama (`basic_info.parent.name`: "Cahaya Dev") — konfirmasi 1 kredensial cukup untuk semua badan usaha in-scope, tidak perlu kredensial terpisah per badan usaha.
