# Business Rules & Configuration Notes — Odoo → eSuite Bridge

> File ini beda fungsi dari Session Transfer Note. Transfer note isinya riwayat
> keputusan per sesi ngobrol (berubah tiap kali ada progress). File ini isinya
> **aturan bisnis & konfigurasi tetap** yang berlaku terus, apapun sesinya —
> update file ini setiap kali ada aturan bisnis baru yang dikonfirmasi, terlepas
> dari sedang ngerjain entity apa.

---

## Filter Data

### Produk yang boleh disync ke eSuite
**Aturan:** hanya produk dengan category **"Saleable"** DAN **`free_qty > 0`** yang boleh dikirim ke eSuite.

- **Product Category** (`get_product_categories()` di `odoo_client.py`): difilter `complete_name ilike "saleable"` — jadi cuma kategori di bawah pohon "Saleable" yang disync. **Terkonfirmasi** format asli di Odoo: `"ALL / SALEABLE / SAP / OLIVIVERO / IQF"` (contoh) — `categ_id` adalah many2one, muncul sebagai `[id, complete_name]` di query Odoo (gotcha m2o yang sudah diketahui).
- **Product** (entity belum dikerjakan): begitu masuk ke `get_products()`, filter ganda perlu diterapkan:
  1. `categ_id` masuk ke cabang Saleable (domain `("categ_id.complete_name", "ilike", "saleable")` atau setara).
  2. `free_qty > 0` — produk dengan stok kosong **tidak** disync (baik saat pertama kali push maupun saat update).
- Field yang relevan dari sample response nyata: `id`, `name`, `free_qty`, `categ_id` (`[id, display_name]`).

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

**Currency:** cuma **IDR**. Sales cuma ke customer/calon customer (transaksi ke vendor pakai USD, tapi itu di luar scope bridge ini — bridge cuma untuk data yang dipakai sales, bukan pembelian). Diisi di `CURRENCY` constant di `product_sync_service.py`, TODO isi `id` dari `GET /currency`.

**Product Type:** cuma **"Goods"** — semua produk barang fisik, tidak ada services. Diisi di `PRODUCT_TYPE` constant, TODO isi `id` dari `GET /product-type`.

**UOM (`base_uom`):** diambil dari field asli Odoo `uom_id` (BUKAN di-parsing dari teks nama produk seperti `"1x32x25g"` — itu rawan salah baca kalau format nama bervariasi). Sejauh ini teridentifikasi 2 kemungkinan nilai: **pcs** dan **pack**. Mapping ada di `UOM_MAPPING` constant (key = nama `uom_id` Odoo, lowercase). TODO: jalankan `/sync/product` sekali, lihat `payload_sent`/log buat tau nama persis `uom_id` yang keluar dari Odoo (bisa jadi bukan persis "pcs"/"pack", tergantung konfigurasi Odoo), sesuaikan key di `UOM_MAPPING`, lalu isi `id` eSuite dari `GET /uom`.

**`cost`** (harga beli) diambil dari `standard_price` Odoo. **`base_price`** (harga jual) dari `list_price`.

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

## Struktur Response GET (Pull) eSuite — Posisi Field Bisa Beda per Entity

- **Branch**: `external_code` posisinya nested di `basic_info.external_code`.
- **Warehouse**: `external_code` posisinya **top-level**.
- **Kesimpulan:** jangan asumsikan struktur konsisten antar entity — selalu cek response pull nyata dulu sebelum nulis logic matching/resolve ID untuk entity baru.

---

## Auth & Kredensial (Sandbox DEV)

```
ESUITE_BASE_URL=https://openapi-esuite.edot-dev.com/v1/webhook
ESUITE_CLIENT_ID=6a6973780f67da70ae33824a
ESUITE_CLIENT_SECRET=Password123!
```
Sumber: Postman collection + environment DEV (prioritas di atas PDF dokumentasi — PDF sempat kasih base URL yang usang/salah).

Semua Branch (termasuk bawaan sistem eSuite) berada di 1 tenant yang sama (`basic_info.parent.name`: "Cahaya Dev") — konfirmasi 1 kredensial cukup untuk semua badan usaha in-scope, tidak perlu kredensial terpisah per badan usaha.
