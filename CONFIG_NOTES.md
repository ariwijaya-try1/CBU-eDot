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

## 15. Entity Customer (BARU, 7 Agustus 2026)

**Keputusan sumber data (dikonfirmasi user):**
- Model: `res.partner`, domain `customer_rank > 0` + `active = True`.
- Field `type` payload eSuite (`"company"`/`"individual"`) dipetakan dari **`company_type`** Odoo (`"company"`/`"person"`), **BUKAN** dari `res.partner.type` (itu jenis alamat -- invoice/delivery/dll -- bukan tipe customer). Mapping: `company -> company`, `person -> individual`.
- `currency`: IDR fixed (`id: "6a695cc1917e8fc836359505"`), sama seperti Product -- satu-satunya currency yang dipakai bisnis ini.
- `external_code` prefix: `ODOO-PARTNER-{res.partner id}` -- konsisten pola `ODOO-COMPANY-`/`ODOO-PROD-`.
- **Tidak difilter company scope** (`IN_SCOPE_COMPANY_NAMES`) -- mengikuti pola Product (juga tidak difilter company), bukan pola Branch/Warehouse. **Ini asumsi minimal, belum eksplisit dikonfirmasi user** -- kalau ternyata customer perlu dipisah per company/badan usaha, perlu direvisi.
- Skema payload eSuite `/customers` yang tersedia di Postman collection **minim** (cuma `name`, `external_code`, `type`, `status`, `currency` -- tidak ada contoh lengkap kayak Product). Field lain (customer_group, salesman_division, alamat, dll) **belum dipetakan** -- kalau nanti dashboard eSuite butuh itu, perlu revisit skema.

**File:** `app/clients/odoo_client.py::get_customers()` (baru), `app/services/customer_sync_service.py` (baru), `app/api/routes/customer.py` (baru), `app/main.py` (router didaftarkan).

**Status: belum pernah di-push ke sandbox.** Lolos `py_compile` saja. TODO test ada di `SESSION_TRANSFER_NOTE.md` poin 12.

**⚠️ Update 7 Agustus 2026 (setelah dites) -- 502 Bad Gateway saat push full batch.** `POST /api/sync/customers` (semua customer, 1 request) balik **502 Bad Gateway dari Cloudflare** (`edot-dev.com`, upstream `openapi-esuite.edot-dev.com`) -- 2x berturut-turut. **Bukan endpoint mati/salah route** -- dikonfirmasi lewat 2 hal: (1) test dummy 1 customer langsung via Postman ke eSuite (bukan lewat bridge) **sukses** (`status 200 success`); (2) endpoint `/product` (juga push banyak record dalam 1 request, 1247 produk) berhasil sebelumnya. Jadi bukan soal "batch besar pasti gagal" secara umum, kemungkinan spesifik ke jumlah atau isi data Customer. **Root cause belum diketahui -- jangan ditebak lebih jauh tanpa data.**

**Diagnostic aid ditambahkan (BUKAN fitur bisnis permanen):** `CustomerSyncService.sync()` & route `/api/sync/customers` sekarang terima query param `limit` opsional (default `None` = behavior normal, semua customer). Tujuannya buat isolasi bertahap (test `limit=5`, `limit=50`, dst) apakah 502 soal jumlah record (size/timeout) atau soal data spesifik di record tertentu. Response juga sekarang include `total_matched_in_odoo` (total customer yang match domain, terpisah dari `synced_count` yang cuma jumlah yang dikirim kalau `limit` dipakai).

**✅ Update 7 Agustus 2026 -- hasil test bertahap: `limit=5`, `limit=50`, `limit=500` SEMUA SUKSES.** Jadi 502 sebelumnya kemungkinan besar bukan soal jumlah record kecil/menengah -- entah baru muncul di angka yang lebih besar dari 500 (mendekati `total_matched_in_odoo`), atau memang transient (pas 2x kejadian sebelumnya kebetulan). **Belum ketemu titik pastinya** -- next step: coba `limit` yang lebih besar lagi (mis. 800, 1000) atau langsung tanpa `limit` (full) sekali lagi buat lihat apakah masih 502 atau ternyata sudah pulih. Pola diagnostik `limit` yang sama (5/50/500 dst) juga baru ditambahkan ke `/sync/product` (lihat `product_sync_service.py`) kalau nanti perlu debug serupa di sana.

**Setelah root cause ketemu, pertimbangkan apakah `limit` ini dibuang lagi atau dipertahankan sebagai fitur** (mis. buat re-push manual bertahap kalau eSuite ada limit batch resmi).

**Catatan currency:** test dummy user via Postman pakai `currency.id = "696759da076ea746282ae708"` (sama persis kayak contoh mentah vendor di collection) -- **beda** dari `CURRENCY` yang dipakai bridge kita (`"6a695cc1917e8fc836359505"`, sudah dicek dari `GET /currency` buat Product). Punya bridge kemungkinan lebih benar (sudah divalidasi), tapi worth di-double-check kalau nanti push customer sukses -- pastikan `GET /customers` balik currency yang sesuai, bukan kosong/salah.

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

**⚠️ Info tambahan dari vendor eSuite (6 Agustus 2026, BELUM DIVALIDASI):** vendor kasih contoh payload `POST /product` terbaru yang tiap item `uom_levels` punya field **`id`** tambahan (contoh: `"id": "01KZ5895R0T1JTR4QTVFGE3GHF"`, format mirip ULID) — sebelumnya kode kita cuma kirim `{uom, qty, convertion}` tanpa `id`. **Belum jelas:** (a) `id` ini asalnya dari mana — apakah ID yang di-generate eSuite sendiri saat produk pertama kali dibuat (jadi baru ada setelah GET balik, tidak bisa diisi manual di push pertama)? apakah wajib atau optional? (b) kalau wajib dan kita tidak kirim, apakah upsert reject dengan error, atau tetap `status 200 success` tapi ada anomali data diam-diam (dugaan user: **"mungkin upsert berhasil tapi ada anomali parameter"** — belum terbukti, tapi worth dicurigai terutama untuk konteks masalah `cost` yang di atas juga "sukses" tapi ternyata tidak ter-apply sepenuhnya). **JANGAN ubah kode `product_sync_service.py` untuk nambahin field ini sebelum dikonfirmasi** — kalau `id` itu di-generate eSuite dan kita kirim ID sembarangan/kosong, bisa salah mapping. Next step: cek respons `GET /product` untuk produk yang sudah pernah di-push, lihat apakah `uom_levels[].id` muncul di sana (baru tau format ID yang benar), atau tanya vendor langsung apakah field ini wajib di push pertama kali (`event=init`).

**Catatan (6 Agustus 2026): ini kemungkinan besar BUKAN mekanisme yang sama dengan bug falsy-skip `cost`** (lihat "Tahap 5" di atas) -- itu soal *value* `0` di-skip, sedangkan `uom_levels[].id` yang hilang soal *identitas sub-record* (kalau `uom_levels` disimpan sebagai sub-dokumen berelasi di eSuite, tanpa `id` eSuite mungkin nggak tau ini "update yang sudah ada" vs "insert baru"). **Dugaan spesifik yang belum dites:** tanpa `id`, tiap kali produk yang sama di-upsert ulang, `uom_levels` array-nya numpuk/duplikat (bukan ke-update di tempat yang sama). **Cara verifikasi (belum dilakukan):** push 1 produk yang sama 2x lewat bridge (kondisi sekarang, tanpa `id`), lalu `GET /product` produk itu -- cek apakah `uom_levels` masih 1 item atau sudah jadi 2+ item identik. Kalau nambah → konfirmasi dugaan duplikasi, prioritasnya naik (perlu benerin sebelum go-live). Kalau tetap 1 → kemungkinan optional/auto-dedup, aman untuk sementara.

**✅ Update 7 Agustus 2026 -- bukti empiris pertama dari `GET /api/debug/pull/product`, TAPI belum 100% closed.** User pull data nyata (bukan cuma contoh vendor lagi):
- **Semua produk hasil sync lewat bridge** (payload sekarang: `uom_levels` dikirim TANPA `id`) balik dengan **`uom_levels: []` (kosong total)** di GET -- bukan array 1 item seperti yang dikirim, bukan error/reject juga (push tetap `status 200`). Ini pola "sukses tapi diam-diam hilang" yang sama seperti dugaan di paragraf atas, dan cocok sama pola `cost` (partial-merge/silent-drop di sisi eSuite).
- **2 produk test manual** (`PROD-9001065-001` & `PROD-9001065-002`, kemungkinan dites user langsung lewat Swagger dengan `id` diisi manual) balik dengan `uom_levels` **terisi 1 item + `id` ada**.
- **Kesimpulan sementara: `id` di `uom_levels[]` kemungkinan besar WAJIB** -- tanpa itu, eSuite terima requestnya (200 success) tapi diam-diam tidak menyimpan array `uom_levels` sama sekali. Confidence naik dari "dugaan vendor" jadi "terlihat langsung di data production real (1247 produk)".
- **Yang BELUM terjawab (jangan diabaikan sebelum ubah kode):**
  1. **Asal `id` masih belum jelas.** Kedua produk test punya `id` **PERSIS SAMA** (`01KZ5895R0T1JTR4QTVFGE3GHF`) walau produknya beda -- ini justru mengarah ke dugaan `id` itu **bukan di-generate eSuite per produk**, melainkan **nilai yang di-supply client** (mirip pola `external_code`), kemungkinan user cuma copy-paste contoh `id` dari vendor apa adanya waktu test manual, bukan bikin id baru. Kalau benar begitu, artinya bridge kita yang perlu generate `id` sendiri (mis. ULID) per baris `uom_levels`, BUKAN nunggu ID dari eSuite.
  2. **Belum ada test soal duplikasi saat re-upsert** (poin di paragraf atas) -- masih belum dilakukan.
  3. **Belum ada test "asal ada `id`, apapun formatnya, sudah cukup"** -- semua bukti sejauh ini pakai id vendor yang sama persis, belum dicoba id lain/random.
- **✅ Keputusan kode (7 Agustus 2026): DITERAPKAN.** User pilih opsi deterministik. `product_sync_service.py::_generate_uom_level_id()` sekarang generate `id` dari `sha1(f"{external_code}:{uom_id}")[:26].upper()` -- stabil, produk+uom yang sama selalu hasilkan `id` yang sama tiap re-push (bukan random ULID). Pertanyaan yang MASIH terbuka (tidak terjawab oleh keputusan ini, cuma di-mitigasi): apakah format id bebas dan apakah eSuite replace vs append array saat re-upsert.
- **⚠️ Update 7 Agustus 2026 (setelah fix di-deploy & dites) -- hasil PARSIAL, belum tuntas.** Re-push lewat bridge (payload sekarang include `uom_levels[].id`) berhasil update **~110 dari 1247 produk** (`uom_levels` sekarang keisi di GET) -- **sisanya (~1137) belum ikut ter-update**. **Root cause belum diketahui** -- kandidat dugaan (belum diverifikasi satupun): rate limit/timeout partial batch di sisi eSuite, batch besar di-truncate diam-diam, atau karakteristik khusus di 110 produk pertama. **Status: MENUNGGU analisa vendor eSuite** -- user sudah lapor, belum ada jawaban. **JANGAN re-push ulang / ubah kode `product_sync_service.py` dulu** sampai ada info dari vendor.

**`cost` -- REVISI 6 Agustus 2026 (2 tahap).** Keputusan bisnis (instruksi boss): data cost/harga beli asli **tidak boleh dikirim** ke eSuite -- cuma `base_price` (harga jual) yang boleh. Tahap 1: key `cost` dihapus total dari payload. **Tahap 2 (revisi, sesi yang sama):** ternyata eSuite upsert bersifat partial-merge -- produk yang sebelumnya sudah punya `cost` (dari batch 1247, versi lama yang include `cost`) tetap menampilkan nominal lama di UI eSuite meski key `cost` tidak dikirim lagi, karena "tidak dikirim" tidak dianggap "clear ke 0". **Fix tahap 2: `cost` dikirim eksplisit sebagai `0`** (fixed value, bukan dari `standard_price`). `standard_price` tetap diambil dari Odoo di `get_products()` (tidak dihapus dari query, cuma tidak pernah dipetakan ke payload) -- kalau nanti field ini dibutuhkan lagi, datanya sudah tersedia tanpa perlu ubah query.

**⚠️ Tahap 3 (6 Agustus 2026) -- fix tahap 2 tidak menyelesaikan masalah, TAPI dugaan "computed di UI" sudah TERBANTAH.** Postman collection eSuite (`eSuite-Webhook_postman_collection.json`, contoh body `POST /product`) **mengonfirmasi `cost` field valid & terdokumentasi resmi** (contoh: `"cost": 1000, "base_price": 1200`) -- bukan field yang kita karang sendiri, dan tidak ada indikasi field itu computed/read-only di UI. Jadi field-nya memang dipakai eSuite, tapi entah kenapa `cost: 0` yang kita kirim tidak ter-apply.

**✅ Tahap 5 (6 Agustus 2026) -- falsy-skip TERKONFIRMASI lewat test manual user.** User kirim `POST /product` langsung (Swagger, bukan lewat bridge) dengan `"cost": 1` buat produk yang sama -- kolom "Cost" di UI eSuite berubah jadi `Rp 1`. **Terbukti:** field `cost` memang dipakai eSuite, tapi backend eSuite treat value `0` sebagai falsy/"tidak ada value" (skip update), sementara value non-zero ke-apply normal. Bug ini murni di sisi eSuite, bukan bridge kita.

**✅ Tahap 6 (6 Agustus 2026) -- KEPUTUSAN: `cost` dikirim sebagai `1` (Rp 1) fixed, DITERAPKAN ke kode.** Karena `0` di-skip eSuite dan belum ada jawaban resmi dari IT eSuite soal cara clear yang benar, user memutuskan pakai `1` sebagai sentinel value -- bukan cost asli (tetap sesuai instruksi boss: data cost asli tidak dikirim), cuma workaround supaya bukan falsy dan benar-benar ke-apply ke eSuite. **Trade-off yang disadari:** UI eSuite akan nampilin "Rp 1", bukan "Rp 0" -- bukan hasil ideal, tapi jauh lebih baik daripada nominal cost asli yang nyangkut dari sync lama. **Kalau nanti IT eSuite kasih cara resmi buat clear ke 0 beneran, ganti `1` -> `0`/cara yang benar dan re-push ulang semua produk.** `standard_price` tetap diambil dari Odoo di `get_products()`, cuma tidak pernah dipetakan ke payload.

**`base_price`** (harga jual) dari `list_price` Odoo -- **satu-satunya** field harga yang dikirim ke eSuite sekarang.

**⚠️ Catatan kualitas data (bukan bug kode):** ditemukan beberapa produk dengan `base_price: 1` (dan sebelumnya `cost: 0`, tapi `cost` sekarang tidak lagi dikirim -- lihat revisi di atas) di hasil push nyata -- kemungkinan `list_price` belum di-set benar di Odoo untuk produk-produk itu. **Yang masih relevan buat go-live sekarang cuma `base_price: 1`**, karena itu satu-satunya field harga yang sampai ke eSuite. Perlu dicek ke tim yang pegang data produk, supaya harga di dashboard sales tidak salah tampil.

**STATUS ENTITY PRODUCT: ✅ FILTER TERVALIDASI, PAYLOAD BELUM DI-RE-TEST.** Riwayat angka: 731 produk (30/31 Juli 2026, sebelum revisi filter `free_qty`) → **1247 produk** (5 Agustus 2026, setelah revisi -- produk `free_qty=0` sekarang ikut tersync). Push 1247 ini `esuite_response: status 200 "success"`, tidak ada error mapping category/UOM. **Tapi payload sudah berubah 2x sejak validasi 1247 itu** -- (1) tambah `purchase_uom`/`uom_levels`, (2) hapus `cost` -- jadi belum ada test end-to-end untuk bentuk payload yang sekarang. **Perlu re-run `/sync/product` sekali lagi** sebelum dianggap final, lihat TODO di session transfer note.

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

**✅ Keputusan bisnis dikonfirmasi (6 Agustus 2026):** tidak ada variant beneran secara praktek di operasional PT -- semua "varian" (ukuran/kemasan berbeda, mis. *Soft Dried Mango 500gr* vs *Soft Dried Mango 1x10x25gr*) itu **produk terpisah masing-masing**, bukan 1 produk dengan banyak varian. Keputusan lama (skip `/product-variant`, cukup `/product`) **dipertahankan** -- kode untuk entity `/product-variant` **tidak akan dibuat**. Konsekuensinya: blocker Stock Matrix di atas (butuh `product_variant.id`) **masih terbuka** dan harus diselesaikan lewat cara lain saat entity itu dikerjakan (kemungkinan: tanya ke IT eSuite apakah `/stock-matrix` bisa terima `product.id` juga, atau eSuite otomatis generate 1 variant per product saat push `/product` -- perlu dicek response `GET /product-variant` di sandbox setelah produk di-push).

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

## ⚠️ Info Tambahan dari Vendor: Data Produk Tidak Bisa Hard Delete (6 Agustus 2026, BELUM DIVALIDASI)

Vendor eSuite kasih info: data produk **tidak bisa di-hard-delete**, cuma bisa di-**"inactive"-kan** (kemungkinan lewat field `status` yang sudah ada di payload `/product`, jadi bukan endpoint delete terpisah — tapi ini masih dugaan, belum dicek langsung ke API). **User masih memvalidasi info ini** — belum dianggap final/actionable.

Relevansi ke bridge: scope app sekarang push-only tanpa NOO flow (poin 3 di session transfer note) dan belum ada logic untuk produk yang di-nonaktifkan/dihapus di Odoo. Kalau info ini dikonfirmasi, kemungkinan pola yang dipakai nanti: produk yang di-Odoo di-set tidak aktif/di-archive tetap di-push tapi dengan `status: "inactive"` alih-alih dihilangkan dari payload. **Belum ada keputusan atau kode terkait ini — tunggu hasil validasi user dulu.**

---

## Auth & Kredensial (Sandbox DEV)

```
ESUITE_BASE_URL=https://openapi-esuite.edot-dev.com/v1/webhook
ESUITE_CLIENT_ID=6a6973780f67da70ae33824a
ESUITE_CLIENT_SECRET=Password123!
```
Sumber: Postman collection + environment DEV (prioritas di atas PDF dokumentasi — PDF sempat kasih base URL yang usang/salah).

Semua Branch (termasuk bawaan sistem eSuite) berada di 1 tenant yang sama (`basic_info.parent.name`: "Cahaya Dev") — konfirmasi 1 kredensial cukup untuk semua badan usaha in-scope, tidak perlu kredensial terpisah per badan usaha.
