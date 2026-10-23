# Business Rules & Configuration Notes — Odoo → eSuite Bridge

> File ini beda fungsi dari Session Transfer Note. Transfer note isinya riwayat
> keputusan per sesi ngobrol (berubah tiap kali ada progress). File ini isinya
> **aturan bisnis & konfigurasi tetap** yang berlaku terus, apapun sesinya —
> update file ini setiap kali ada aturan bisnis baru yang dikonfirmasi, terlepas
> dari sedang ngerjain entity apa.

---

## ⚠️ ADDENDUM 18 Agustus 2026 -- aturan bisnis baru dari sesi Cowork (14-18 Agustus), belum tercakup di isi file di bawah

Isi asli file ini (5-14 Agustus) TETAP BERLAKU untuk Product/Customer/UOM/Variant kecuali disebutkan lain di sini. Detail lengkap tiap poin ada di Cowork project memory (topic file disebutkan di tiap poin) -- ini cuma ringkasan aturan PERMANEN yang sudah dikonfirmasi final, bukan riwayat penuh.

**Stock Matrix -- KOREKSI bagian "Stok yang direfleksikan ke eSuite" di bawah (baris ~24-28), sudah OBSOLETE:**
- Field yang dikirim SEKARANG bukan `free_qty` Odoo mentah, tapi hasil hitung manual: `free_to_use = SUM(quantity) - SUM(reserved_quantity) - SUM(quantity lot yang removal_date sudah lewat)`, dijumlah dari `stock.quant` MENTAH per warehouse (bukan computed field `product.product`, karena Odoo 19 instance ini terbukti tidak menghormati context `{"warehouse": id}`).
- **Filter location WAJIB (18 Agustus, keputusan higher-up):** cuma quant di location `usage="internal"` DAN `complete_name` mengandung `"/Stock/"` yang dihitung -- location staging (`.../Output`, `.../Pre-Production`, `.../Post-Production`) yang SAMA-SAMA `usage="internal"` TIDAK dihitung. 2 edge case (`SAP/Stock/Supply`, warehouse "Supplies" tanpa child zone) masih PENDING konfirmasi.
- **Pembulatan: `math.floor()` (ke bawah), BUKAN round-nearest** -- keputusan user, alasan: paling aman dari resiko oversell (8.9→8, 8.4→8). eSuite `quantity`/`on_hand` field WAJIB int64, tidak terima desimal sama sekali (walau nilainya kebetulan bulat).
- Payload: `product_variant.code` (= `external_code` Product, konsisten no-variant), `warehouse.code`, `uom_level_code` (boleh kosong), `quantity`, `on_hand` -- TANPA `location`/`uom.id`/`free_to_use` (auto-assign eSuite ke location default "Good Stock" per warehouse). Dikonfirmasi resmi tim dev eSuite via WA 17 Agustus.
- Detail lengkap: Cowork project memory `stock_sync_progress`.

**Customer Group (`/customergroup`) -- BARU, tidak ada di isi asli file ini:**
- 4 grup: Food Service (FS), Modern Trade (MT), General Trade (GT), HORECA -- **HARDCODED di kode, BUKAN dari field Odoo manapun** (Odoo `res.partner` tidak punya tag/grouping ini). `external_code` prefix `CBU-CUSTGROUP-{CODE}`.
- BELUM final: kemungkinan `res.partner.category` (Contact Tags) adalah SSOT asli yang seharusnya dipakai, belum dicek. Juga ada potensi konflik konsep "Group" (affiliasi customer, mis. "Pepito+cabang") vs "Category" (FS/MT/GT/HORECA) yang sedang dibangun ini.
- Detail lengkap: Cowork project memory `sales_entities_gap`.

**Pricelist -- business model CONFIRMED (17 Agustus), push belum dibangun:**
- **`base_price`/`list_price` di Product BUKAN harga jual final ke customer manapun** -- cuma fallback/reference. Harga jual sebenarnya = lookup by (produk, pricelist toko/customer tsb), granular PER TOKO/CUSTOMER (bukan cuma per 4 grup FS/MT/GT/HORECA) -- 1 produk bisa punya 10+ pricelist berbeda dengan Fixed Price beda-beda. Dikonfirmasi user via screenshot Odoo tab "Prices", quote: *"ketika sales akan menawarkan produk a ke toko x maka sales harus melihat harga barang a untuk toko x.. bukan base price atau harga toko y"*.
- Assignment ke customer kemungkinan lewat field `price_list.id` di Customer (belum dibangun, lihat gap Customer payload di bawah).
- Detail lengkap: Cowork project memory `pricelist_progress`.

**Customer payload -- gap yang belum tertutup (lama, masih relevan):**
Field resmi `price_list.id` dan `sales.branchs[]`/`sales.salesmans[]` di skema `/customers` TIDAK PERNAH dikirim sejak awal. Customer yang sudah dipush belum ke-assign ke pricelist/salesman/branch manapun secara eksplisit di eSuite.

**Security (16 Agustus) -- rate limiting `slowapi` sudah di-setup tapi TIDAK PERNAH diaktifkan** di `main.py` (dependency ada, tidak ada `app.state.limiter`/`SlowAPIMiddleware`/`@limiter.limit()` di manapun) -- nol proteksi DoS/brute-force nyata sampai sekarang. `GET /debug/pull/{entity_path}` juga proxy TANPA whitelist ke eSuite. Detail: Cowork project memory `security_audit`.

---

## ⚠️ ADDENDUM 21 Agustus 2026 -- temuan bisnis dari WhatsApp chat vendor eDOT (6-21 Agustus), dibaca ulang & diringkas di sesi Cowork. Ini baru RINGKASAN INFO/MAPPING dari chat, BELUM ada perubahan kode/test terkait poin-poin baru di bawah kecuali disebutkan lain.

**Alur visibilitas Produk untuk Salesman di eWork (mobile) -- CONFIRMED vendor via WA:**
1. Produk baru muncul di katalog/search produk salesman kalau: customer & product sudah termapping, DAN ada stok (`stock-matrix`) di warehouse yang di-assign ke branch tempat salesman itu ditempatkan (menu HR -> Employee di eSuite dashboard, bukan via payload bridge kita).
2. Root cause bug "stock kosong di app mobile" yang ditemukan 18-20 Agustus: salesman belum di-mapping ke branch yang punya warehouse (default jatuh ke branch Headquarter, yang tidak punya stok). Assignment ini manual dari UI, `salesman_division_sync_service.py` kita belum push field branch assignment ini.
3. **Cross-branch visibility BELUM didukung eSuite** (dikonfirmasi vendor 21 Agustus) -- salesman tidak bisa lihat produk/stok dari warehouse di branch lain di luar branch tempatnya sendiri.
4. **Pengecualian transaksional:** saat proses kunjungan toko (visit) langsung di app, sales masih mungkin melihat produk yang tidak lolos aturan stok di atas -- beda dari tampilan katalog master produk (belum ada detail lebih jauh, cek behavior aktualnya kalau relevan).

**Relasi Branch <-> Warehouse (klarifikasi dari chat 6 Agustus, bukan kontradiksi dgn baris "Warehouse -> Branch" di bawah):** 1 warehouse tetap FK ke 1 branch (sudah benar di file ini), TAPI 1 branch bisa dituju oleh BANYAK warehouse. Mapping warehouse->branch dilakukan dari sisi detail Warehouse ("add branch" di UI), tidak ada opsi mapping dari sisi Branch, dan tidak otomatis (warehouse baru harus di-assign manual ke branch).

**Stock Matrix -- formula incoming/outgoing/forecasted (CONFIRMED vendor 18-19 Agustus):**
- `forecasted = on_hand + incoming - outgoing`; `free_to_use = on_hand - outgoing`.
- `free_to_use` berkurang begitu ada sales order (sebelum DO selesai); `on_hand` baru berubah setelah DO/GR benar-benar diproses selesai.
- incoming/outgoing SAAT INI murni dari transaksi di app eWork (GR/DO), payload `/stock-matrix` webhook kita cuma set `on_hand`/`quantity` (jadi incoming=outgoing=0 di sisi kita, forecasted=on_hand=free_to_use selalu). Vendor lagi dicek apakah Odoo bisa push incoming/outgoing sendiri lewat webhook (GR/DO Odoo) -- **belum ada jawaban final per 21 Agustus, jangan asumsikan sudah bisa.**
- `batch_code`: default tertulis "EWORK" kalau lewat webhook tanpa field batch eksplisit; vendor lagi nambahin parameter biar batch_code bisa dikirim custom kalau nanti dibutuhkan (belum ada kepastian dibutuhkan/tidak).

**Bulk operation constraints (klarifikasi tambahan dari chat 11-12 Agustus, general untuk semua entity bukan cuma Customer):** push >~3000 record sekaligus dalam 1 request beresiko 502 (Cloudflare/timeout) -- perlu di-batch (contoh vendor: 7x500 aman utk 3038 customer). Semua endpoint sync bersifat async via queue, response 200 = "diterima", bukan "tersimpan" -- count di UI/GET bisa delay.

**Open/belum terjawab per 21 Agustus:** delete Branch via Postman collection (`BRCH-00009` ditest, hasil/behavior-nya belum sempat dikonfirmasi vendor di chat -- thread berhenti di sini).

**⚠️ Currency Customer -- discrepancy lama (baris ~120 di bawah, dicatat 11 Agustus) kini ACTIONABLE karena user report langsung (21 Agustus): field `currency` di UI Customer eSuite tidak ter-update walau payload sudah pakai `currency.id = "6a695cc1917e8fc836359505"` (IDR, hasil `GET /currency`, SAMA PERSIS dengan yang dipakai & terbukti jalan di entity Product). Jadi hipotesis awal user ("kita tidak pakai id currency dari eDOT") **tidak tepat** -- id yang dipakai memang resmi dari eDOT, bukan buatan sendiri. Test live `?external_codes=ODOO-PARTNER-39353` (21 Agustus): `esuite_response.status: 200 / data: "success"`, tapi belum dikonfirmasi field currency-nya benar-benar tersimpan/tampil di dashboard.
- Kemungkinan root cause (BELUM diverifikasi, jangan diasumsikan benar tanpa test): (a) pola async-queue yang sudah diketahui (poin bulk operation di atas) -- response 200 cuma "diterima", field bisa telat muncul di UI/GET; (b) entity Customer di eSuite mungkin punya currency master BEDA dari currency master Product/global (contoh payload customer dari vendor sendiri, 11 Agustus, pakai id lain: `696759da076ea746282ae708` -- tapi ini dari akun demo/internal vendor sendiri, BELUM tentu applicable ke tenant Cahaya Boga Utama, karena utk Product `6a695cc1917e8fc836359505` sudah terbukti valid & konsisten dipakai sukses); (c) field `currency` mungkin memang tidak ditampilkan di UI detail Customer eSuite (cuma dipakai internal, belum dikonfirmasi vendor apakah field ini punya representasi UI utk Customer).
- **PENDING -- next step verifikasi (belum dieksekusi, butuh akses Postman/dashboard eSuite langsung):** (1) `GET /customers?external_code=ODOO-PARTNER-39353` (atau lewat `GET /api/debug/pull/customers`) -- cek apakah field `currency` benar-benar tersimpan di response, beri jeda beberapa menit dulu (pola async). (2) Kalau tersimpan tapi tetap tidak tampil di UI -- kemungkinan besar poin (c), tanya vendor langsung. (3) Kalau TIDAK tersimpan / kosong -- baru coba test currency id vendor (`696759da076ea746282ae708`) khusus di 1 dummy customer test, bandingkan hasilnya. **Jangan ubah `CURRENCY` constant di `customer_sync_service.py` sebelum salah satu dari 3 langkah ini dikonfirmasi** -- constant ini sudah terbukti valid untuk Product, ubah tanpa bukti beresiko malah merusak yang sudah jalan.

Sumber: chat WhatsApp "eDOT >< Cahaya Boga Utama" (file `chat export/WhatsApp Chat with eDOT  Cahaya Boga Utama.txt` di folder eDOT user), rentang 19 Juni - 21 Agustus 2026.

---

## ⚠️ CHECKLIST: perubahan user/akun sales -> update `app/core/salesman_slots.py` (21 Oktober 2026)

Tabel slot Odoo -> akun eSuite untuk call plan di-HARDCODE di bridge. Setiap kali
ada perubahan user/akun sales (orang ganti akun, akun eSuite baru, slot Odoo
di-rename, sales baru/resign), lakukan:
1. Update baris terkait di `app/core/salesman_slots.py`:
   `odoo_slot` (nama res.users PERSIS di Odoo), `esuite_employee_id` (field
   "Employee ID" di UI eSuite, BUKAN kode `EMP-xxxxx`), `esuite_username`, `person`.
   Akun testing call plan (`TEST_EMPLOYEE_ID` / `TEST_USERNAME`, kini Salesman_12
   `202600012`) ada di file yang sama -- ganti di situ kalau akun testing berubah.
2. Restart bridge (pilihan `slots` di Swagger & mapping baru ikut ter-load).
3. Cek: `POST /api/sync/call-plan` `dry_run=true` per slot yang berubah ->
   `slots[0].esuite_username` sesuai & tidak ada warning username beda.
4. Kalau outlet pindah akun: pindahkan juga mapping customer->salesman di eSuite
   (`/api/mapping/customer-sales` / `mass-customer-sales`).
5. Update Session Transfer Note + Decision Log visit cycle.

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

**✅ Fix root cause gagal upsert customer (11 Agustus 2026, dari revisi payload vendor):** payload `/customers` butuh field **`entity_type: "customer"`** (fixed value, bukan dari Odoo) yang sebelumnya tidak kita kirim -- ini konfirmasi resmi vendor lewat revisi payload mereka, bukan dugaan. Sudah ditambahkan ke `customer_sync_service.py::_to_esuite_payload()`. **Belum di-re-test end-to-end lewat bridge** setelah fix ini -- next step: re-push customer (mulai `limit` kecil) dan verifikasi lewat `GET /api/debug/pull/customers` (atau entity path yang sesuai).

**✅ Field `phone`/`mobile`/`email` ditambahkan (21 Agustus 2026), CONFIRMED via live test.** Skema Postman poin di atas ("minim, cuma name/external_code/type/status/currency") **TERBUKTI cuma contoh bare minimum**, BUKAN daftar lengkap field yang diterima eSuite -- 3 field ini dites manual (`external_code: ODOO-PARTNER-39353`, payload tambah `phone`/`mobile`/`email`) dan CONFIRMED tersimpan + tampil balik persis sesuai kiriman di `GET /customers`. Sudah ditambahkan ke `odoo_client.py::get_customers()` (fields query) & `customer_sync_service.py::_to_esuite_payload()` (Odoo `False` utk char kosong dinormalkan ke `""`, key tetap dikirim). **Prinsip ke depan:** jangan asumsikan field tidak didukung eSuite cuma karena tidak ada di contoh Postman -- field lain yang mungkin relevan (address, customer_groups, dll -- lihat struktur `GET /customers` yang lebih lengkap dari payload POST) berpotensi juga bisa diisi, tapi belum ditest satu-satu.

**⚠️ KOREKSI, beberapa jam kemudian (masih 21 Agustus 2026): `mobile` DIHAPUS LAGI.** Test manual Postman di atas berhasil karena dikirim LANGSUNG ke eSuite (bypass Odoo sama sekali, jadi tidak ketauan field-nya valid atau tidak di sisi Odoo). Begitu bridge beneran jalan (`odoo_client.py::get_customers()` query `res.partner` dgn field `mobile`), Odoo balikin error **`Invalid field 'mobile'`**. Root cause (dikonfirmasi user): **Odoo 19 sudah resmi menghapus field `Mobile` terpisah dari Contacts**, di-merge ke field `Phone` -- jadi `mobile` bukan field standar lagi di instance Odoo 19 ini (beda dari versi Odoo lama/dokumentasi umum yang masih punya field ini). Fix: `mobile` dihapus dari fields query `get_customers()` DAN dari payload `_to_esuite_payload()` -- `phone`/`email` TETAP jalan seperti biasa, tidak ada sumber data Odoo lagi untuk `mobile` jadi tidak dikirim sama sekali (bukan dikirim kosong `""`). **Constraint baru buat entity lain:** kalau nanti ada kebutuhan field lain dari `res.partner` yang juga historically "umum" (mis. field Odoo versi lama), CEK DULU field itu benar-benar ada di instance Odoo 19 CBU (test query kecil / cek error) sebelum diasumsikan otomatis ada.

**⚠️ Currency Customer -- update temuan (21 Agustus 2026), lihat juga bagian ADDENDUM 21 Agustus di atas untuk detail lengkap.** Data baru dari `GET /customers` (external_code sama, satu request test): response GET **tidak punya field top-level `currency` sama sekali** -- yang ada cuma `invoice.currency: {id:"", name:"", symbol:""}` (nested, kosong terus walau `currency.id` sudah dikirim di payload). Field lain yang dikirim (name/phone/mobile/email/type/status) semua balik sinkron persis di GET yang sama request -- jadi BUKAN soal delay/async-queue. Dugaan bergeser: kemungkinan besar field `currency` di payload Customer memang tidak dipetakan/dipersist eSuite ke representasi apa pun yang kelihatan di GET (beda dari Product, di mana currency dipakai langsung utk `base_price`). **Masih PENDING konfirmasi vendor** -- JANGAN hapus field `currency` dari payload dulu (bisa saja tetap required walau tidak nampak efeknya, sama seperti kasus `entity_type` dulu sebelum vendor konfirmasi).

**File:** `app/clients/odoo_client.py::get_customers()` (baru), `app/services/customer_sync_service.py` (baru), `app/api/routes/customer.py` (baru), `app/main.py` (router didaftarkan).

**Status: belum pernah di-push ke sandbox.** Lolos `py_compile` saja. TODO test ada di `SESSION_TRANSFER_NOTE.md` poin 12.

**⚠️ Update 7 Agustus 2026 (setelah dites) -- 502 Bad Gateway saat push full batch.** `POST /api/sync/customers` (semua customer, 1 request) balik **502 Bad Gateway dari Cloudflare** (`edot-dev.com`, upstream `openapi-esuite.edot-dev.com`) -- 2x berturut-turut. **Bukan endpoint mati/salah route** -- dikonfirmasi lewat 2 hal: (1) test dummy 1 customer langsung via Postman ke eSuite (bukan lewat bridge) **sukses** (`status 200 success`); (2) endpoint `/product` (juga push banyak record dalam 1 request, 1247 produk) berhasil sebelumnya. Jadi bukan soal "batch besar pasti gagal" secara umum, kemungkinan spesifik ke jumlah atau isi data Customer. **Root cause belum diketahui -- jangan ditebak lebih jauh tanpa data.**

**Diagnostic aid ditambahkan (BUKAN fitur bisnis permanen):** `CustomerSyncService.sync()` & route `/api/sync/customers` sekarang terima query param `limit` opsional (default `None` = behavior normal, semua customer). Tujuannya buat isolasi bertahap (test `limit=5`, `limit=50`, dst) apakah 502 soal jumlah record (size/timeout) atau soal data spesifik di record tertentu. Response juga sekarang include `total_matched_in_odoo` (total customer yang match domain, terpisah dari `synced_count` yang cuma jumlah yang dikirim kalau `limit` dipakai).

**✅ Update 7 Agustus 2026 -- hasil test bertahap: `limit=5`, `limit=50`, `limit=500` SEMUA SUKSES.** Jadi 502 sebelumnya kemungkinan besar bukan soal jumlah record kecil/menengah -- entah baru muncul di angka yang lebih besar dari 500 (mendekati `total_matched_in_odoo`), atau memang transient (pas 2x kejadian sebelumnya kebetulan). **Belum ketemu titik pastinya** -- next step: coba `limit` yang lebih besar lagi (mis. 800, 1000) atau langsung tanpa `limit` (full) sekali lagi buat lihat apakah masih 502 atau ternyata sudah pulih. Pola diagnostik `limit` yang sama (5/50/500 dst) juga baru ditambahkan ke `/sync/product` (lihat `product_sync_service.py`) kalau nanti perlu debug serupa di sana.

**✅ Update 11 Agustus 2026 -- SELESAI, bukan bug. Root cause: async processing di eSuite.** Vendor konfirmasi: eSuite proses upsert customer secara **asynchronous** (request diterima & di-queue, response `200` = "diterima ke antrian", bukan "sudah tersimpan" -- proses tulis ke DB baru menyusul lewat worker/background job). Selisih 3038 dikirim vs 2002 tampil di UI (saat pertama dicek) adalah **delay pemrosesan**, bukan data hilang. **Sekarang semua 3038 sudah masuk.** Implikasi buat cara kerja kita ke depan: response `200` dari eSuite untuk endpoint manapun **tidak bisa langsung dianggap final** -- kalau perlu verifikasi cepat setelah push volume besar, kasih jeda dulu sebelum cek UI/GET, atau retry pull beberapa kali.

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
- **⚠️ Update 7 Agustus 2026 (setelah fix di-deploy & dites) -- hasil PARSIAL, belum tuntas.** Re-push lewat bridge (payload sekarang include `uom_levels[].id`) berhasil update **~110 dari 1247 produk** (`uom_levels` sekarang keisi di GET) -- **sisanya (~1137) belum ikut ter-update**. **Root cause belum diketahui** -- kandidat dugaan (belum diverifikasi satupun): rate limit/timeout partial batch di sisi eSuite, batch besar di-truncate diam-diam, atau karakteristik khusus di 110 produk pertama. **Status: MENUNGGU analisa vendor eSuite** -- user sudah lapor, belum ada jawaban.
- **❌ Keputusan sha1-generate DIANULIR (11 Agustus 2026).** Vendor eSuite konfirmasi lewat test manual mereka sendiri: `id` hasil generate kita (`3B175ABEB25165E4D806B0DDC3`, contoh) dibaca sistem mereka sebagai **id asing/tidak dikenal** -- kutipan vendor: "id tersebut adalah id nya Odoo nya Cahaya Boga, bukan esuite". Setelah vendor koreksi `uom_levels`, update `cost` yang sama-sama ada di payload itu ikut berhasil. **Kesimpulan penting:** id yang tidak dikenali eSuite kemungkinan bikin **seluruh update produk gagal ter-apply (bukan cuma `uom_levels`)** walau response tetap `status 200` -- ini kemungkinan besar **root cause asli** dari kasus "110/1247 partial" di atas (bukan soal rate-limit/batching seperti dugaan awal).
- **⚠️ Update 11 Agustus 2026 -- fix `uom.id` juga BELUM terbukti benar.** User test manual 1 produk baru (`ODOO-PROD-18374`) via Postman vendor pakai `uom_levels[].id = "01KZ5895R0T1JTR4QTVFGE3GHF"` -- **id ini adalah contoh id dari dokumentasi vendor (poin 7d), BUKAN id yang di-generate/dimiliki produk ini.** Hasil: response `200` tapi UI tidak berubah -- pola gagal-diam-diam yang sama lagi. Ini menyingkirkan 1 kemungkinan (reuse id sembarang/id "yang kelihatan valid" milik record lain tidak jalan), tapi **belum membuktikan** apakah `uom.id` (pendekatan kode kita sekarang) itu benar atau salah -- test ini pakai id yang beda dari `uom.id` produk ini juga. **Pertanyaan sudah dikirim ke vendor** (11 Agustus): dari mana asal `uom_levels[].id` yang valid buat produk BARU -- apakah eSuite generate sendiri (perlu push tanpa `id` dulu lalu `GET` buat ambil id-nya), atau ada aturan generate di sisi client yang belum kita tahu. **STATUS: MENUNGGU JAWABAN VENDOR** -- jangan ubah kode `product_sync_service.py` lagi sampai ada jawaban, supaya tidak nebak-nebak lagi.

- **✅ KOREKSI PENTING 11 Agustus 2026, dari `eSuite_Synchronization_Document_v2.0.0.pdf` (dokumentasi resmi vendor, section 9.4 & section 8/10) -- id `01KZ5895R0T1JTR4QTVFGE3GHF` di atas TERNYATA BUKAN "id contoh dokumentasi", tapi id ASLI & VALID dari record "Low" di `GET /uom-level`.** Kesalahan pemahamanku sebelumnya (baris di atas) sudah diralat. Temuan struktural yang jauh lebih penting: **"Product UOM Level" (`/uom-level`, alias `/product-uom-level`) adalah ENTITY TERPISAH dari UOM master (`/uom`)** -- bukan alias/turunan dari UOM master seperti asumsi kode kita sekarang. Konsepnya semacam "tier kemasan" (contoh dari dokumentasi: Small/Medium/Large; punya user: "Mid"/"Low") -- required field cuma `external_code` + `name`, dan **bisa punya lebih dari 1 UOM per produk** (contoh section 9.6 PDF: 1 produk, 2 entry `uom_levels`, masing-masing `id` Level BEDA dan `uom` fisik BEDA). Vendor: *"UoM level biasanya kita samakan dengan UoM yang bersandingannya atau bisa disesuaikan dengan usecase tim Cahaya... High (karton, palet), Med (bungkus, plastik, lusin), Kecil (pack, sachet, pcs)"* -- ini keputusan pemodelan bisnis, bukan cuma soal id yang benar. **Implikasi konkret: pendekatan kode kita sekarang (`uom_levels[].id = base_uom["id"]`, disamakan dengan UOM master) SALAH KONSEP** menurut dokumentasi resmi -- harusnya merujuk ke record `Product UOM Level` (`GET /uom-level`), bukan `GET /uom`.
- **⚠️ TAPI test lanjutan (11 Agustus 2026, sesudah baca dokumentasi ini) pakai id "Low" yang VALID -- MASIH GAGAL juga (cost tidak berubah).** Jadi walau salah konsep tadi kemungkinan benar, **belum terbukti itu satu-satunya root cause** -- ada faktor lain yang belum ketemu (kandidat dugaan, BELUM diverifikasi: beda behavior create vs update, downstream async yang gagal diam-diam untuk field tertentu, atau field lain yang masih kurang/salah di payload). **Belum ada keputusan final soal Level id mana yang harus dipakai** (reuse "Low"/"Mid" existing, atau bikin Level baru khusus lewat `POST /uom-level` yang representasikan "tier tunggal" karena Odoo tidak punya konsep multi-tier packaging -- lihat poin 7b). **JANGAN ubah kode dulu** -- next step: test dengan `external_code` yang BENAR-BENAR baru (belum pernah di-push, murni create bukan update) + Level id valid, kasih jeda buat proses async, baru simpulkan. Kalau masih gagal juga, itu bukti kuat buat lapor ke vendor.

**Referensi resmi (11 Agustus 2026):** `eSuite_Synchronization_Document_v2.0.0.pdf` sekarang jadi acuan utama buat struktur payload (di atas Postman collection utk hal yang didokumentasikan) -- base URL prod `https://openapi.esuite.edot.id/v1/webhook/`, sandbox `https://openapistg.esuite.edot.id/v1/webhook/`. Auth 4 header (Authorization Basic, X-Signature HMAC-SHA256, X-Timestamp, X-Request-ID) **sudah cocok 100% dengan implementasi `esuite_client.py` kita** -- dicek ulang, tidak ada perubahan diperlukan di situ. Max 5000 record/request (batch kita 500-1000, aman). Dikonfirmasi resmi: *"A successful POST means the payload was accepted... not that the owning service finished persisting it. Downstream processing is asynchronous"* -- berlaku ke SEMUA entity (bukan cuma Customer).

- **✅ HASIL TEST 12 Agustus 2026 -- root cause `cost` TERISOLASI dari `uom_levels`.** User pull `GET /product` full (1250 record) dan bandingkan langsung ke record `ODOO-PROD-18374` yang sudah ditest manual (payload: Level id "Low", `cost: 13344`):
  - `uom_levels` di GET **sekarang menunjukkan Level "Low" yang valid** (`01KZ5895R0T1JTR4QTVFGE3GHF`) -- persis payload test. **`uom_levels` DIANGGAP BERHASIL tersimpan.**
  - `cost` di GET **masih `0`, BUKAN `13344`** yang dikirim. **`cost` TERBUKTI gagal ter-update, terpisah dari isu `uom_levels`.**
  - ⚠️ Anomali belum terjelaskan: `updated_at` record ini masih nunjuk **7 Agustus 2026** (tanggal batch push lama), bukan 12 Agustus (tanggal test manual). Tidak jelas apakah field `updated_at` di eSuite tidak reliable, atau perubahan `uom_levels` itu sebenarnya bukan dari test hari ini. **Perlu ditanyakan ke vendor kalau relevan** -- jangan dijadikan dasar kesimpulan apapun untuk sekarang.
  - **Kesimpulan:** root cause sekarang murni soal `cost`, BUKAN lagi soal `uom_levels[].id`/Level. `uom_levels[].id = Product UOM Level id yang valid` (bukan `uom.id`) kemungkinan besar memang pendekatan yang benar (perlu direvisi ke kode setelah Level id yang tepat buat tiap produk dikonfirmasi -- lihat poin di atas soal keputusan "Low"/"Mid"/bikin Level baru).
  - **✅ DIVERIFIKASI ULANG & DITERAPKAN KE KODE (12 Agustus 2026).** Analisis langsung `sample/hasil get product 10000.txt` (1250 record GET /product nyata, bukan cuma 1 kasus test) MENGKONFIRMASI dampak bug ini di skala penuh: **1245/1250 produk (99.6%) punya `uom_levels` KOSONG** -- semua yang lewat bridge (pakai `uom.id` yang salah), cuma 5 produk test manual (pakai Level id benar) yang berhasil. Cross-check `base_price` pada grup produk dengan `cost` "bocor" (694/1138 nilai unik & wajar) membuktikan mekanisme upsert secara umum JALAN -- bukan seluruh record gagal, `cost` memang bug spesifik field itu sendiri (bukan efek samping `uom_levels`). Kekhawatiran duplikasi `uom_levels` saat re-upsert **terbukti TIDAK terjadi** (0 dari 1250 record punya >1 item) -- bisa dicoret dari daftar risiko.
  - **✅ KEPUTUSAN USER (12 Agustus 2026): reuse Level "Low" (`01KZ5895R0T1JTR4QTVFGE3GHF`) untuk SEMUA produk, sementara.** Alasan: CBU cuma pakai 2 UOM fisik (units & kg), tidak ada kebutuhan tier packaging beneran, jadi 1 Level generic cukup -- tidak perlu bikin Level baru via `POST /uom-level` dulu. **Kode SUDAH diubah** (`product_sync_service.py`, constant `PRODUCT_UOM_LEVEL`) -- `uom_levels[].id` sekarang selalu `PRODUCT_UOM_LEVEL["id"]`, bukan lagi `base_uom["id"]`. **Belum di-re-test end-to-end lewat bridge** (baru lolos `py_compile`) -- next step: re-run `/sync/product` (mulai `limit` kecil), lalu `GET /product` verifikasi `uom_levels` benar-benar terisi "Low" untuk produk yang di-push lewat bridge (bukan cuma test manual lagi).
  - **Produk BARU (`ODOO-PROD-18374-test`, belum pernah ada) -- benar-benar TIDAK TERSIMPAN.** Di-cari di 1250 record hasil `GET /product`, tidak ditemukan sama sekali. Response `200` tapi bukan cuma UI yang belum sinkron -- di level API pun tidak ada. **Ini bug terpisah dari isu cost di atas** (create gagal total, vs update yang partial-gagal-di-1-field) -- belum ada dugaan root cause, belum dilaporkan ke vendor.

- **🚨 TEMUAN BISNIS PENTING (12 Agustus 2026) -- tujuan "cost tidak boleh terlihat di eSuite" BELUM TERCAPAI buat mayoritas produk.** Distribusi `cost` di seluruh 1250 produk yang ada di eSuite sekarang:
  | Kondisi | Jumlah | % |
  |---|---|---|
  | `cost` = nilai asli Odoo (BELUM ke-mask) | **1138** | **91%** |
  | `cost` = `0` (kemungkinan dari test lama) | 111 | 9% |
  | `cost` = `1` (sentinel target kita saat ini) | **1** | <1% |

  **Ini prioritas bisnis yang lebih urgent daripada sekadar "belum sempurna 100%"** -- mayoritas mutlak produk (1138/1250) masih expose cost asli mereka ke eSuite, kontradiksi langsung sama instruksi awal (cost tidak boleh disclose). **Perlu di-flag terpisah ke tim/atasan** soal risiko ini kalau ada rencana go-live dekat -- independen dari kapan root cause teknis `cost` API ketemu.
- **Status re-push massal 1247 produk:** **[UPDATE 13 Agustus 2026]** root cause sudah ketemu & fix sudah diterapkan (lihat Tahap 8 di bawah) -- re-push massal sekarang jadi next step aktif, bukan lagi menunggu. Angka 91% di atas adalah snapshot LAMA (12 Agustus), akan berubah setelah re-push massal dilakukan.

**`cost` -- REVISI 6 Agustus 2026 (2 tahap).** Keputusan bisnis (instruksi boss): data cost/harga beli asli **tidak boleh dikirim** ke eSuite -- cuma `base_price` (harga jual) yang boleh. Tahap 1: key `cost` dihapus total dari payload. **Tahap 2 (revisi, sesi yang sama):** ternyata eSuite upsert bersifat partial-merge -- produk yang sebelumnya sudah punya `cost` (dari batch 1247, versi lama yang include `cost`) tetap menampilkan nominal lama di UI eSuite meski key `cost` tidak dikirim lagi, karena "tidak dikirim" tidak dianggap "clear ke 0". **Fix tahap 2: `cost` dikirim eksplisit sebagai `0`** (fixed value, bukan dari `standard_price`). `standard_price` tetap diambil dari Odoo di `get_products()` (tidak dihapus dari query, cuma tidak pernah dipetakan ke payload) -- kalau nanti field ini dibutuhkan lagi, datanya sudah tersedia tanpa perlu ubah query.

**⚠️ Tahap 3 (6 Agustus 2026) -- fix tahap 2 tidak menyelesaikan masalah, TAPI dugaan "computed di UI" sudah TERBANTAH.** Postman collection eSuite (`eSuite-Webhook_postman_collection.json`, contoh body `POST /product`) **mengonfirmasi `cost` field valid & terdokumentasi resmi** (contoh: `"cost": 1000, "base_price": 1200`) -- bukan field yang kita karang sendiri, dan tidak ada indikasi field itu computed/read-only di UI. Jadi field-nya memang dipakai eSuite, tapi entah kenapa `cost: 0` yang kita kirim tidak ter-apply.

**✅ Tahap 5 (6 Agustus 2026) -- falsy-skip TERKONFIRMASI lewat test manual user.** User kirim `POST /product` langsung (Swagger, bukan lewat bridge) dengan `"cost": 1` buat produk yang sama -- kolom "Cost" di UI eSuite berubah jadi `Rp 1`. **Terbukti:** field `cost` memang dipakai eSuite, tapi backend eSuite treat value `0` sebagai falsy/"tidak ada value" (skip update), sementara value non-zero ke-apply normal. Bug ini murni di sisi eSuite, bukan bridge kita.

**✅ Tahap 6 (6 Agustus 2026) -- KEPUTUSAN: `cost` dikirim sebagai `1` (Rp 1) fixed, DITERAPKAN ke kode.** Karena `0` di-skip eSuite dan belum ada jawaban resmi dari IT eSuite soal cara clear yang benar, user memutuskan pakai `1` sebagai sentinel value -- bukan cost asli (tetap sesuai instruksi boss: data cost asli tidak dikirim), cuma workaround supaya bukan falsy dan benar-benar ke-apply ke eSuite. **Trade-off yang disadari:** UI eSuite akan nampilin "Rp 1", bukan "Rp 0" -- bukan hasil ideal, tapi jauh lebih baik daripada nominal cost asli yang nyangkut dari sync lama. **Kalau nanti IT eSuite kasih cara resmi buat clear ke 0 beneran, ganti `1` -> `0`/cara yang benar dan re-push ulang semua produk.** `standard_price` tetap diambil dari Odoo di `get_products()`, cuma tidak pernah dipetakan ke payload.

**⚠️ Tahap 7 (11 Agustus 2026) -- update cost ke `0` lewat endpoint API masih GAGAL, tapi lewat UI dashboard eSuite BERHASIL.** User coba update manual `cost` ke `0` via UI dashboard eSuite -- berhasil, tersimpan. Tapi lewat endpoint API (Swagger/Postman) masih gagal seperti sebelumnya. **Ini menguatkan bahwa falsy-skip bug ini spesifik di endpoint API eSuite, bukan keterbatasan sistem mereka secara umum** -- artinya secara bisnis `cost: 0` seharusnya valid dan tidak masalah begitu bug endpoint-nya beres. Sudah dilaporkan ke vendor, **user sedang menunggu jawaban** (kemungkinan root cause sama dengan kasus `uom_levels[].id` di atas -- id yang tidak dikenali bikin seluruh update, termasuk `cost`, gagal ter-apply diam-diam). **`cost` di kode TETAP `1` untuk sekarang** -- JANGAN ganti ke `0` sampai laporan endpoint ini dijawab/dikonfirmasi vendor.

**✅ Tahap 8 (13 Agustus 2026) -- RESOLVED, FINAL. Dugaan "falsy-skip bug di endpoint eSuite" (Tahap 5-7 di atas) DITARIK.** Setelah dikaji ulang, root cause `cost` "tidak ter-update" sebenarnya GABUNGAN dua hal, bukan bug field `cost` itu sendiri:
1. `uom_levels.id` sempat salah (id UOM master, bukan id Product UOM Level) -- field ini MANDATORY. Kalau salah, eSuite gagal memproses record dengan benar SECARA KESELURUHAN (bukan cuma `uom_levels` yang kosong) -- field lain di record yang sama, termasuk `cost`, ikut tidak ter-apply walau response tetap `200`.
2. Delay yang kelihatan seperti "cost tidak berubah" sebagian juga karena antrian job async eSuite numpuk pas bulk insert banyak produk sekaligus (silent queue backlog) -- pola sama seperti yang sudah dikonfirmasi terjadi di Customer (poin 0b session note), bukan berarti request di-skip/ditolak.

**Keputusan final: `cost` sekarang dikirim `0` fixed** (bukan lagi sentinel `1`) -- user awalnya mau `null`, tapi eSuite render `null` jadi `0` juga di UI, jadi `0` eksplisit dipakai langsung (hasil sama, kode lebih jelas). **Kode SUDAH diubah** (`product_sync_service.py::_to_esuite_payload()`, sejalan dengan `uom_levels.id` yang sudah difix 12 Agustus ke Level "Low"). **Tidak perlu lapor/tunggu jawaban vendor lagi soal ini** -- pertanyaan yang sempat dikirim (Tahap 7, "cara resmi clear ke 0") sudah tidak relevan.

**Next step aktif:** re-push massal produk yang sempat ke-upsert dengan payload lama (`cost: 1` sentinel + `uom_levels` salah) supaya konsisten -- lihat SESSION_TRANSFER_NOTE.md poin 12.2 & poin 21 (kebetulan bertepatan dengan rencana vendor kosongkan sandbox, jadi bisa sekalian testing bersih).

**🔎 TEMUAN (12 Agustus 2026, sesi lanjutan, KONTEKS HISTORIS -- konsisten dengan kesimpulan Tahap 8 di atas soal delay antrian async) -- indikasi race condition di antrian async eSuite, bukan cuma falsy-skip.** Setelah fix `uom_levels[].id` (Level "Low") diverifikasi jalan lewat bridge (5 produk, lihat `SESSION_TRANSFER_NOTE.md` poin 17-18), 4 dari 5 produk (`ODOO-PROD-8855/8856/8857/8858`) tampil `cost: 1` sesuai yang dikirim bridge. Tapi produk ke-5 (`ODOO-PROD-18374`) tampil **`cost: 13344`** -- BUKAN `1` yang baru dikirim bridge, BUKAN juga `0` yang tercatat sebelumnya. Angka `13344` itu persis payload test manual lama (sebelum sesi ini, lihat "HASIL TEST 12 Agustus 2026" di bawah). `updated_at` produk ini juga ~28 menit lebih baru dari 4 sibling yang di-push dalam batch sama. **Dugaan: job async lama (test manual) baru selesai diproses eSuite SETELAH push bridge baru, sehingga menimpa balik nilai baru.** Kalau benar, ini berarti urutan proses eSuite tidak FIFO/reliable per `external_code` -- job lama bisa "menang" atas job baru tergantung kapan worker mereka sempat memprosesnya, bukan soal `0` di-skip. **Belum dikonfirmasi vendor, baru 1 kasus** -- next step: push ulang `18374` sendirian sekarang, tunggu beberapa menit, cek lagi apakah akhirnya settle ke `1`. Kalau iya, ini cuma stale-queue satu kali; kalau masih balik ke nilai lain, ini pola race condition yang berulang dan perlu dilaporkan terpisah dari falsy-skip.

**⚠️ Update 11 Agustus 2026 -- fix `uom_levels[].id` (= `uom.id`, lihat bagian `uom_levels[].id` di atas) BELUM menyelesaikan masalah cost sepenuhnya.** Update cost via bridge/endpoint masih cuma nyantol ke sekitar **110 produk** (angka yang sama seperti kasus partial `uom_levels` sebelumnya) -- dan **ini BUKAN soal delay/async processing** seperti yang terjadi di kasus batch Customer (sudah ditunggu beberapa hari, tetap 110). Jadi beda kategori masalah dari Customer: kemungkinan besar `uom_levels[].id` yang kita generate (`= uom.id`) **masih belum sesuai format/aturan yang eSuite mau**, bukan soal timing. **Next step (sedang berjalan):** user test manual 1 produk langsung lewat Postman collection vendor sendiri, `uom_levels` disesuaikan persis sama settingan/contoh vendor, buat cek apakah cost bisa ke-update dengan format `uom_levels` yang "benar" menurut mereka. Hasil test ini akan nentukan revisi berikutnya ke `_to_esuite_payload()` di `product_sync_service.py`. **JANGAN ubah kode sebelum hasil test ini ada.**

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

**🔎 TEMUAN BARU (12 Agustus 2026, dari skema payload `POST /product-variant` di Postman collection eSuite, BELUM DITEST):**
```json
{
  "product": {"id": "6a66d702386b1d658ebf302a"},
  "external_code": "PM-pvar",
  "name": "PM PVar",
  "status": "active",
  "product_type": {"id": "..."},
  "product_category": {"id": "..."},
  "base_uom": {"id": "..."},
  "currency": {"id": "..."}
}
```
Payload ini butuh field **`product: {id}`** -- referensi ke Product yang **sudah ada** di eSuite. Ini menjawab (secara struktural, belum divalidasi lewat test) pertanyaan lama di atas: `product-variant` **kemungkinan besar butuh push manual**, bukan auto-generate oleh eSuite saat push `/product`. **Tidak bertentangan dengan keputusan no-variant** (6 Agustus tetap berlaku, tidak ada variant asli secara bisnis) -- opsinya: bridge push **1 `product-variant` per `product`** (1:1, data mirror dari Product yang sama) semata-mata supaya Stock Matrix punya `product_variant.id` untuk direferensikan, bukan karena ada variant beneran.

**Konsekuensi alur teknis (belum diimplementasi):** karena `POST /product` tidak balikin id eSuite (reconcile pakai `external_code`, lihat bagian "Reference Cache" di `SESSION_TRANSFER_NOTE.md`), alurnya jadi: push Product → `GET /product` pull utk dapat id eSuite → push `/product-variant` dgn `product.id` itu → baru bisa isi `/stock-matrix`.

**STATUS: dugaan terstruktur dari skema payload, BELUM divalidasi lewat test manual.** Next step sebelum bikin `product_variant_sync_service.py`: test manual 1x push `/product-variant` lewat Postman utk 1 produk yang sudah ada, cek `GET /product-variant` apakah tersimpan & field apa yang dibalikin (khususnya id-nya, buat dipakai di Stock Matrix).

---

**✅✅ ROOT CAUSE RESMI DARI VENDOR (13 Agustus 2026) -- KOREKSI PENUH pendekatan di atas, `POST /product-variant` terpisah SALAH untuk tujuan tampil di halaman produk.**

Vendor konfirmasi: tab "Attribute & Variant" di halaman Detail Produk baca dari field **`product.variants[]` yang ter-embed di DALAM dokumen `/product` itu sendiri** -- BUKAN dari collection `/product-variant` yang berdiri sendiri. Alur kita sebelumnya (push `/product` tanpa `variants[]`, lalu push `/product-variant` terpisah) cuma bikin record variant "mandiri" (muncul di "List All Variant") tapi TIDAK ter-link ke `product.variants[]` produk induknya -- makanya kosong di halaman produk.

**Skema BARU yang WAJIB dipakai (contoh dari vendor, produk `ODOO-PROD-9035`):**
```json
{
  "event": "upsert",
  "data": [{
    "external_code": "ODOO-PROD-9035",
    "name": "ACETAIA Pure Glaze 1x12x250mL",
    "status": "active",
    "product_type":     { "id": "664191ad236dfcd5a4000001" },
    "product_category": { "id": "01KZ5Q6FNTM3G8G7R3E2P3SHVT" },
    "base_uom":     { "id": "664219e2236dfcd5a400001a" },
    "purchase_uom": { "id": "664219e2236dfcd5a400001a" },
    "uom_levels": [{ "id": "01KZ5895R0T1JTR4QTVFGE3GHF", "uom": { "id": "664219e2236dfcd5a400001a" }, "qty": 1, "convertion": 1 }],
    "cost": 0,
    "base_price": 57670,
    "currency": { "id": "6a695cc1917e8fc836359505" },
    "variants": [
      {
        "id": "6a7d359c1a6a0f06f95ee16b",
        "name": "ACETAIA Pure Glaze 1x12x250mL",
        "external_code": "ODOO-PROD-9035",
        "attributes": [],
        "sku": "",
        "barcode": "",
        "cost": 0,
        "extra_price": 0,
        "status": "active"
      }
    ]
  }]
}
```
**Field variant nested TIDAK punya `base_price` sendiri** (beda dari skema `/product-variant` standalone yang kita pakai sebelumnya) -- cuma `id`, `name`, `external_code`, `attributes`, `sku`, `barcode`, `cost`, `extra_price`, `status`. Dugaan: `base_price` variant kemungkinan inherit dari `base_price` produk induk (di level yang sama dalam 1 payload), dan `extra_price` adalah markup tambahan di atas itu (default `0`) -- BELUM dikonfirmasi eksplisit ke vendor, perlu test setelah implementasi.

**⚠️ ATURAN PALING KRITIS (WAJIB dipatuhi, kalau tidak akan bikin data duplikat):**
1. **Matching saat update variant pakai `id`, BUKAN `external_code`.** Kalau tiap sync cycle kirim `variants[].id` kosong, eSuite akan bikin variant BARU tiap kali (duplikat menumpuk).
2. **Produk BARU** (belum pernah punya variant): `variants[].id` boleh dikosongkan -- eSuite auto-generate id & langsung isi `product.variants[]`. Id itu WAJIB disimpan (di Odoo atau minimal di-resolve ulang tiap sync) buat dipakai di update berikutnya.
3. **Produk yang variantnya SUDAH TERLANJUR dibuat lewat flow lama** (push `/product-variant` terpisah, spt `ODOO-PROD-9035`, `ODOO-PROD-18374`, dan 8 produk lain yang sempat ditest `with_variant=true` sesi ini) -- HARUS kirim ulang produk dengan `variants[].id` diisi id variant yang SUDAH ADA. ~~(ambil dari `GET /product-variant` filter by `external_code`)~~ **[⚠️ KOREKSI 14 Agustus 2026 -- lihat catatan di bawah, sumber ini TERBUKTI TIDAK RELIABLE, ganti `GET /product`.]**
4. **Push `/product-variant` terpisah untuk tujuan tampil di halaman produk HARUS DIHENTIKAN** -- itu penyebab akar masalahnya. Ini artinya fitur `with_variant=true` + `_sync_variants_for_batch()` yang dibuat sesi ini (poin 19 di `SESSION_TRANSFER_NOTE.md`) **PERLU DIROMBAK TOTAL**, bukan cuma di-patch.

**Konfirmasi vendor:** `ODOO-PROD-9035` sudah diperbaiki manual dari sisi mereka sebagai contoh -- variant seharusnya sudah muncul di halaman produknya.

**⚠️ KOREKSI PENTING (14 Agustus 2026) -- poin 3 di atas ("resolve id via `GET /product-variant`") TERBUKTI SALAH SUMBER, bukan cuma teori yang belum tervalidasi.** Implementasi awal (13 Agustus) sudah ikut instruksi poin 3 apa adanya -- query resolve ke `GET /product-variant` filter `external_code`. Test nyata di `ODOO-PROD-9034` & `ODOO-PROD-8857` (14 Agustus) menunjukkan resolve SELALU gagal (`linked_to_existing_variant: 0`) walau variant-nya sudah benar-benar ada & `external_code`-nya cocok -- karena **`GET /product-variant` (collection standalone/legacy) TIDAK PERNAH mengembalikan field `id` (selalu string kosong, dicek 13/13 record)**. Ini bikin variant baru terus dibuat tiap sync meski produk sudah linked, jadi duplikat menumpuk lagi (persis masalah yang harusnya dicegah). **Sumber resolve yang BENAR: `GET /product`, baca `variants[].id` yang ter-embed di dalam dokumen produk itu sendiri** -- field ini TERBUKTI valid (lihat contoh `ODOO-PROD-9035` di skema JSON atas, `variants[0].id: "6a7d359c1a6a0f06f95ee16b"` beneran ada & konsisten). Fix sudah diterapkan di `product_sync_service.py::_resolve_existing_variant_ids()` -- detail lengkap di `SESSION_TRANSFER_NOTE.md` poin 26.

**Duplikat existing yang sudah kadung terbentuk (belum dibersihkan, per 14 Agustus 2026):** `ODOO-PROD-8857` dan `ODOO-PROD-9034` masing-masing punya 2 entry di `variants[]` (1 orphan `external_code` kosong dari era flow lama, 1 benar). Fix di atas cuma cegah duplikat BARU, tidak menghapus yang sudah ada -- perlu dibersihkan manual via UI eSuite atau minta vendor hapus langsung di database sandbox (tidak ada endpoint delete terdokumentasi untuk 1 entry di dalam `variants[]`).

**STATUS: rencana implementasi disusun (13 Agustus 2026), BELUM dieksekusi -- lihat `SESSION_TRANSFER_NOTE.md` poin 25.**

---

## External Code Convention

Pola: `ODOO-{SINGKATAN-ENTITY}-{id_odoo}`

| Entity eSuite | Sumber Odoo | Convention |
|---|---|---|
| Branch | `res.company` | `ODOO-COMPANY-{id}` |
| Warehouse | `stock.warehouse` | `ODOO-WH-{id}` |
| Product Category | `product.category` | `ODOO-CAT-{id}` |
| Product | `product.product` | `ODOO-PROD-{id}` |
| Product Variant (BARU, 12 Agustus 2026) | `product.product` (1:1 dgn Product) | SAMA PERSIS dengan `external_code` Product induk (`ODOO-PROD-{id}`) -- bukan prefix baru, lihat `SESSION_TRANSFER_NOTE.md` poin 19 |
| Customer (BARU, 18 Agustus addendum) | `res.partner` | `ODOO-PARTNER-{id}` |
| Customer Group (BARU, 18 Agustus addendum) | HARDCODED (bukan Odoo) | `CBU-CUSTGROUP-{CODE}` (mis. `CBU-CUSTGROUP-FS`) -- ASUMSI penamaan, belum eksplisit dikonfirmasi user |
| Stock Matrix (BARU, 18 Agustus addendum) | `stock.quant` per warehouse | TIDAK ADA `external_code` sendiri -- composite key eSuite: company + product_variant + uom + warehouse + location + batch. Payload pakai `product_variant.code` (= `ODOO-PROD-{id}`) + `warehouse.code` (= `ODOO-WH-{id}`) |

*(Ditambah baris baru tiap ada entity baru yang selesai dikerjakan.)*

---

## ✅ Semua endpoint `/sync/*` punya `external_codes` + `limit` (21 Agustus 2026)

Sebelumnya cuma Customer/Product/Stock Matrix yang punya fitur "upsert 1/beberapa record tertentu" -- sekarang SEMUA endpoint sync ikut, biar bisa ditest 1 data dulu sebelum full push (konsisten dgn precedent Customer/Product/Stock Matrix, minta user sebelum full push data besar).

- **Branch** (`ODOO-COMPANY-{id}`), **Warehouse** (`ODOO-WH-{id}`), **Product Category** (`ODOO-CAT-{id}`), **Salesman Division** (`ODOO-SALESTEAM-{id}`) -- pola PERSIS sama dengan Customer/Product: `external_codes` (comma-separated) + `limit`, parse ke id Odoo numerik lewat `_parse_external_codes()` per service (constant `EXTERNAL_CODE_PREFIX` masing-masing).
- **Customer Group** -- BEDA: bukan id Odoo (entity ini hardcoded, tidak bersumber dari Odoo, lihat bagian Customer Group di atas). `external_codes` di sini match ke **code** (FS/MT/GT/HORECA), format `CBU-CUSTGROUP-{code}`, filter langsung ke list `CUSTOMER_GROUPS` in-memory (bukan query Odoo).
- **Pricelist** -- SUDAH punya param `ids` (id Odoo `product.pricelist` MENTAH, BUKAN external_code) sejak 18 Agustus, sengaja dipertahankan (alasan: konsisten dgn `GET /odoo/pricelist`, lihat komentar `_parse_ids()`). `external_codes` (`ODOO-PRICELIST-{id}`) ditambahkan sebagai ALTERNATIF, bukan pengganti -- kalau keduanya diisi, `external_codes` yang dipakai.
- **Customer, Product, Stock Matrix** -- SUDAH ADA duluan (11-16 Agustus), tidak berubah.

`odoo_client.py` ikut direvisi: `get_companies()`, `get_warehouses()`, `get_product_categories()`, `get_sales_teams()` sekarang terima parameter `ids` opsional (filter tambahan `"id in ids"` di domain Odoo) -- additive, behavior lama (tanpa `ids`) tidak berubah.

**Belum ditest live** untuk 5 entity yang baru ditambah (Branch/Warehouse/Product Category/Salesman Division/Customer Group) -- baru lolos `py_compile`. Test dulu satu-satu (`limit=1` atau `external_codes=` 1 record) sebelum dianggap beres.

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

## Referensi Relasi Entitas Dashboard eSuite (dari Knowledge Base gitbook, 12 Agustus 2026)

Sumber: `https://edot.gitbook.io/knowledge-base-edot`. Ini dokumentasi level dashboard/UI eSuite (definisi tabel & cara pakai), **beda scope** dari PDF Sync Document (payload webhook API) yang tetap jadi acuan utama untuk kode bridge. Detail lengkap & diagram: `edot_dashboard_entity_relations.mmd` (sejajar `app/`).

Ringkasan relasi yang **baru dikonfirmasi** lewat dokumentasi ini (belum pernah tercatat sebelumnya):

- **Product Category & Product Brand**: sama-sama punya field **Parent** (self-referencing hierarchy). Product Category **link ke Product** (field "Product Category" di tabel Product). Product Brand **TIDAK ada link eksplisit ke Product** di dokumentasi UI maupun payload webhook (konsisten dengan temuan lama 5 Agustus: 0 referensi `product_brand` di payload `POST /product`).
- **Product Group**: relasi **M:N ke Product** lewat field "Associated Product" (assign manual, bisa lebih dari satu produk per grup). Juga punya hierarchy sendiri (Parent).
- **Product Variant**: entity UI terpisah (Product ID, Attribute, Price, Category sendiri) -- **project bridge ini sengaja tidak sync entity ini** (keputusan no-variant, sudah final, lihat bagian "Struktur Produk & Variant" di atas).
- **UoM Category → UoM**: UoM Category cuma "grup" (ID + Name), tiap UoM (Satuan) individual punya field UoM Category, Type, **Ratio**, Precision. Ratio inilah yang menentukan konversi antar UOM dalam 1 category yang sama.
- **Warehouse → Branch**: 1 warehouse selalu merujuk 1 Branch (field "Branch" di tabel Warehouse) -- konsisten dengan asumsi bridge yang sudah ada.
- **Location**: hierarchy sendiri (Parent Location + Location Type + Category Storage). **Belum dikonfirmasi** apakah Location adalah sub-entity dari Warehouse (storage bin) -- tidak ada FK eksplisit disebut di dokumentasi.

**Catatan penting:** dokumentasi gitbook ini tidak menyebutkan entity "Product UOM Level" (`/uom-level`) secara eksplisit sebagai menu terpisah -- entity ini cuma ditemukan lewat PDF Sync Document (section 9.4) dan pengalaman langsung vendor (lihat bagian `uom_levels[].id` di atas). Kemungkinan entity ini baru/khusus API, belum masuk dokumentasi UI umum.

---

## Auth & Kredensial (Sandbox DEV)

```
ESUITE_BASE_URL=https://openapi-esuite.edot-dev.com/v1/webhook
ESUITE_CLIENT_ID=6a6973780f67da70ae33824a
ESUITE_CLIENT_SECRET=Password123!
```
Sumber: Postman collection + environment DEV (prioritas di atas PDF dokumentasi — PDF sempat kasih base URL yang usang/salah).

Semua Branch (termasuk bawaan sistem eSuite) berada di 1 tenant yang sama (`basic_info.parent.name`: "Cahaya Dev") — konfirmasi 1 kredensial cukup untuk semua badan usaha in-scope, tidak perlu kredensial terpisah per badan usaha.
