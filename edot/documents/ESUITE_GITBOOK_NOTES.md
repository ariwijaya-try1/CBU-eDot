# Ringkasan Riset Gitbook eSuite (Knowledge Base eDOT)

> File ini adalah kompilasi temuan dari gitbook resmi eSuite
> (https://edot.gitbook.io/knowledge-base-edot) supaya tidak perlu fetch ulang
> tiap sesi. **Update file ini (bukan re-create) tiap ada riset gitbook baru.**
> Index lengkap semua halaman ada di https://edot.gitbook.io/knowledge-base-edot/llms.txt
> (tiap halaman gitbook juga bisa dibaca sebagai markdown dengan nambahin
> `.md` di akhir URL-nya).

Dibuat: 13 Agustus 2026, sebagai respons riset relasi **Product ↔ Product
Variant ↔ Attribute**.

---

## 1. Produk (Products)

**Source:** https://edot.gitbook.io/knowledge-base-edot/esuite/interactive-blocks/produk-products/produk-products.md

Definisi kolom tabel Produk di UI eSuite:
- **Product ID** -- ID produk yang tercatat pada sistem.
- **Product Name** -- Nama produk.
- **Cost** -- Harga modal dari produk.
- **Base Price** -- Harga dasar untuk menjual produk.
- **Product Category** -- Kategori produk (All, Expenses, Salesable).
- **Actions** -- Lihat/ubah detail produk.

Halaman ini cuma index singkat -- detail langkah-langkah ada di file
attachment terpisah (`/files/RwvaYt7EqLX08wSZnucR`) yang **tidak bisa
di-fetch sebagai teks** (gambar/PDF, bukan halaman markdown).

## 2. Varian Produk (Product Variant)

**Source:** https://edot.gitbook.io/knowledge-base-edot/esuite/interactive-blocks/produk-products/varian-produk-product-variant.md

Definisi kolom tabel Varian Produk di UI eSuite:
- **Product ID** -- ID varian produk yang tercatat pada sistem.
- **Product Name** -- Nama varian produk.
- **Attribute** -- Attribute dari varian produk.
- **Price** -- Harga dari varian produk.
- **Product Category** -- Kategori varian produk.
- **Actions** -- Lihat/ubah detail varian produk.

**Penting:** `Attribute` dan `Price` adalah kolom RESMI di tabel Product
Variant menurut dokumentasi ini -- bukan cuma field internal API yang kita
tebak. Detail langkah-langkah ada di file attachment terpisah
(`/files/cxTgWkvIG8uv58Lj6lhu`), juga **tidak bisa di-fetch sebagai teks**.

**Keterbatasan dokumentasi:** gitbook TIDAK punya halaman berdiri sendiri
khusus "Attribute" (sudah dicek index lengkap `llms.txt`, tidak ada entry
"Atribut"/"Attribute" sebagai menu terpisah) -- attribute cuma disebut
sebagai salah satu kolom di tabel Product Variant di atas. Jadi skema/aturan
detail field `attribute` (format value, wajib/opsional, gimana cara set via
API) **tidak terdokumentasi di gitbook** -- kesimpulan di bagian 3 di bawah
murni dari observasi empiris kita sendiri, bukan dari dokumentasi resmi.

## 3. Temuan Empiris (BUKAN dari gitbook, dari testing kita sendiri, 13 Agustus 2026)

**Konteks:** user coba nambahkan "Attribute" di UI produk `KATSUOBUSHI 500g`
(`MPD-01268`) -- isi attribute dengan referensi ke Product Variant
`MPV-09829` (`id: 6a7d359b1a6a0f06f95ee159`), qty `1`. Setelah itu, variant
`MPV-09829` baru muncul sebagai "varian dari" produk `MPD-01268` di UI.

**Cross-check ke data API (`GET /product` & `GET /product-variant`,
external_codes `ODOO-PROD-18374` dkk, ditarik user sesi ini):**
- Field `product.variants[]` di response `GET /product` **SUDAH terisi
  benar** untuk SEMUA 10 produk yang dicek (termasuk yang TIDAK pernah
  disentuh manual lewat UI attribute) -- `variants[].id` cocok persis
  dengan `product-variant.id`, dan `product-variant.product.id` cocok
  balik ke `product.id`-nya. FK 2 arah ini terbukti benar HANYA dari push
  `POST /product-variant` (payload kita, field `"product": {"id": ...}"`),
  TANPA pernah set `attribute` apapun lewat API.
- Field `product.attributes[]` (top-level, terpisah dari `variants[]`) di
  semua 10 produk itu **kosong (`[]`)** -- termasuk `KATSUOBUSHI 500g`
  (padahal user manual nambahin attribute lewat UI buat produk ini).

**✅ UPDATE 13 Agustus 2026 -- pull ulang setelah user nambah attribute manual, kesimpulan berubah arah.**
Pull kedua (`GET /product` untuk 10 produk yang sama) nunjukin:
- `KATSUOBUSHI 500g` sekarang `attributes[]` KEISI 1 item:
  ```json
  {"id": "01KZWK4Q8TVS5V1DSXE07JGHX6", "name": "MPV-09829", "values": ["1"], "pos": {"card_color": ""}}
  ```
  (`name` = kode variant `MPV-09829`, `values` = qty yang user isi `["1"]`) -- pola EAV generik
  (id + name + values bebas), BUKAN skema "link ke variant" yang terstruktur/typed.
- 9 produk lain TETAP `attributes: []` (tidak disentuh).
- **PALING PENTING: `variants[]` KATSUOBUSHI PERSIS SAMA di kedua pull** (`id:
  6a7d359b1a6a0f06f95ee159`, `code: MPV-09829`, semua field identik) --
  attribute yang ditambahkan TIDAK mengubah `variants[]` sama sekali.

**Kesimpulan final: `attributes[]` dan `variants[]` adalah 2 hal yang TIDAK
berkaitan.** Relasi Product↔Product Variant (`variants[]`) sudah benar SEJAK
SEBELUM attribute ditambahkan -- murni dari FK `product: {id}` yang bridge
kirim di `POST /product-variant`, terbukti tidak berubah oleh aksi attribute
apapun. Dugaan paling masuk akal: pengamatan user ("variant baru muncul
setelah tambah attribute") adalah **UI cache/refresh, bukan sebab-akibat**
-- halaman detail produk itu kemungkinan belum di-reload sejak bridge push
sebelumnya, dan aksi edit-attribute (yang trigger save+reload) yang membuat
data lama (variant yang sudah lama terpasang) baru "kelihatan".

**Rekomendasi: TIDAK PERLU ubah payload bridge untuk kirim `attributes[]`.**
Field ini kemungkinan cuma custom attribute bebas (spec/spesifikasi produk),
tidak ada urusan dengan relasi Product-Variant yang dibutuhkan dashboard sales.

**Verifikasi tambahan yang disarankan (opsional, buat mastiin 100%):** buka
detail salah satu dari 9 produk yang belum pernah disentuh attribute-nya
(mis. `ACETAIA Pure Glaze 1x12x250mL` / `MPD-01277`) langsung di UI eSuite --
cek apakah variant-nya (`MPV-09838`) sudah muncul TANPA perlu tambah
attribute. Kalau muncul, teori "UI cache" di atas terkonfirmasi 100% dan
kasus ini bisa ditutup total.

## 4. Referensi Lain yang Relevan (belum digali detail)

Dari index `llms.txt`, halaman-halaman lain di modul Produk (Inventory) yang
mungkin relevan buat riset relasi entity lanjutan, belum dibaca detail:
- Kategori Produk (Product Category): https://edot.gitbook.io/knowledge-base-edot/esuite/interactive-blocks/produk-products/kategori-produk-product-category.md
- Brand Produk (Product Brand): https://edot.gitbook.io/knowledge-base-edot/esuite/interactive-blocks/produk-products/brand-produk-product-brand.md
- Grup Produk (Product Group): https://edot.gitbook.io/knowledge-base-edot/esuite/interactive-blocks/produk-products/grup-produk-product-group.md
- Manajemen Stok (Management Stock): https://edot.gitbook.io/knowledge-base-edot/esuite/interactive-blocks/manajemen-stok-management-stock.md
- Konfigurasi > Satuan (UoM): https://edot.gitbook.io/knowledge-base-edot/esuite/interactive-blocks/konfigurasi-configuration/satuan-unit-of-measurement.md
- Konfigurasi > Kategori Satuan (UoM Category): https://edot.gitbook.io/knowledge-base-edot/esuite/interactive-blocks/konfigurasi-configuration/kategori-satuan-uom-category.md

**Catatan umum soal gitbook ini:** isinya dominan panduan UI end-user
(langkah klik-klik), BUKAN dokumentasi skema data/API teknis -- detail
teknis (field wajib, tipe data, aturan validasi) hampir selalu ada di file
attachment (gambar/PDF) yang tidak bisa di-fetch sebagai teks. Untuk
kebutuhan integrasi API, `eSuite_Synchronization_Document_v2.0.0.pdf` dan
Postman collection vendor tetap sumber utama (lihat `CONFIG_NOTES.md`) --
gitbook ini pelengkap buat konteks bisnis/UI saja.

## 5. Stock Sync -- Riset Skema (13 Agustus 2026)

**Source utama:** `documents/eSuite Synchronization Document v2.0.0.pdf`
section 9.11 (Warehouse), 9.12 (Location), 9.16 (Stock Adjustment /
`/stock-matrix`), 9.17 (Goods Receipt), 9.18 (Deliveries). Section 8 (Entity
index) & 10 (Pull entities) juga dicek untuk daftar lengkap endpoint.

**Skema resmi `POST /stock-matrix` (section 9.16):**
```json
{
  "external_code": "123",
  "product_variant": {"id": "..."},
  "uom": {"id": "664219e2236dfcd5a4000001"},
  "location": {"id": "670350aa07a76756a9abec59"},
  "free_to_use": 100, "on_hand": 100, "quantity": 100,
  "batch": {"code": "Batch1", "expiry_date": "30/09/2024"}
}
```
Field wajib: `product_variant`, `uom`, `warehouse` **ATAU** `location`
(ditandai `Yes*` di dokumentasi -- salah satu cukup), `free_to_use`,
`on_hand`, `quantity`. Contoh JSON di dokumentasi cuma pakai key `location`,
tidak pernah pakai `warehouse` -- belum ketahuan apakah `warehouse` benar2
valid dipakai langsung sebagai pengganti `location` (perlu test).

**⚠️ TEMUAN PALING PENTING, BELUM DIVERIFIKASI:** field `quantity`
didefinisikan di tabel dokumentasi sebagai **"Change applied by the
adjustment"** -- bahasanya mengindikasikan endpoint ini **DELTA-based**
(nambah/kurang dari stok yang sudah ada), BUKAN "set nilai absolut". Kalau
benar delta-based, push berulang dengan angka yang sama (mis. push
`quantity: 100` tiap hari) akan terus menambah stok, bukan menjaga tetap
100 -- desain sync HARUS beda total (kirim SELISIH dari terakhir kali sync,
bukan angka absolut dari Odoo). **WAJIB ditest dengan 1 produk sebelum
desain final** -- lihat rencana kerja di `SESSION_TRANSFER_NOTE.md`.

**`Location` (section 9.12):** field wajib cuma `external_code`, `name`.
Contoh payload: `{"name": "Location", "parent": {"id": ""}, "type": {"id":
"663a02088e35cb03f2e03736"}, "salesman": {"id": ""}}`. `type` merujuk ke
semacam master "Location Type" -- **tidak ada endpoint pull terdokumentasi**
buat ambil daftar Location Type yang valid (beda dari UOM Level yang ada
`GET /uom-level`). Dari gitbook (`Lokasi (Location)`, UI page): waktu bikin
lokasi baru, user pilih "Category Storage" dan **"untuk sekarang cuma ada
storage"** -- kemungkinan cuma ada 1 pilihan type/category saat ini, tapi
id-nya harus dicari lewat cara lain (kemungkinan trial only lewat UI/tanya
vendor, karena tidak ada GET pull resminya).

**Warehouse vs Location -- STATUS: MASIH AMBIGU, jangan diasumsikan.** Dari
skema API murni, `stock-matrix` cuma butuh SALAH SATU (`warehouse` atau
`location`). Tapi dari gitbook (`Stok (Stocks)`, tabel kolom UI), Warehouse
DAN Location ditampilkan sebagai 2 kolom terpisah ("Warehouse -> Lokasi
penempatan stok", "Location -> Jenis lokasi penempatan stok") -- mengesankan
keduanya biasanya diisi bareng dalam praktik nyata, bukan pilih salah satu.
**Perlu test empiris:** push `stock-matrix` cuma pakai `warehouse.id` (skip
`location` sepenuhnya, reuse Warehouse yang sudah kita push & valid) -- kalau
diterima & `GET /stock-matrix` balikin data lengkap dengan Warehouse
kelihatan di UI, kita bisa skip bikin entity Location sama sekali (lebih
simpel, minim entity baru). Kalau ditolak/data ganjil, baru bangun Location.

**Entity terkait lain yang baru ketemu (belum diriset detail, dicatat buat referensi):**
- `Goods Receipt` (`/goods-receipt`) & `Deliveries` (`/deliveries`) --
  mekanisme stock movement berbasis DOKUMEN (`schedule_date`,
  `receive_from`/`delivery_to`, list `product_variants[]` dengan `demand` +
  `uom` + `batch`), BEDA dari `/stock-matrix` yang lebih ke snapshot/adjustment
  langsung. Kemungkinan ini alur yang lebih "benar" secara bisnis (tiap
  penerimaan/pengiriman barang = 1 dokumen), tapi jauh lebih kompleks
  (butuh partner "receive_from"/"delivery_to", scheduling, dll) -- di luar
  scope awal, dicatat sebagai opsi masa depan kalau `/stock-matrix` polos
  tidak cukup.
- `Product Attribute` (`GET /products/attribute`, section 10 Pull entities)
  -- TERNYATA ada endpoint pull resmi untuk "Attribute" sebagai master data
  (bukan cuma field bebas di Product). Belum digali -- relevan buat riset
  Attribute di bagian 3 di atas kalau nanti perlu lanjut (saat ini sudah
  di-skip per keputusan user, lihat SESSION_TRANSFER_NOTE poin 23).

## 6. Sales / Salesman -- Struktur Menu Gitbook (21 Agustus 2026)

**Konteks:** cek gitbook cari "dimana manage data sales", relevan buat blocker
Salesman individual di `sales_entities_gap.md` (project memory Cowork).

**Struktur menu "Aktifitas Salesman" (index):**
https://edot.gitbook.io/knowledge-base-edot/esuite/markdown/aktifitas-salesman.md
-- 5 submenu: Target & Achievement, Kehadiran (Attendance), Live Tracking,
**Divisi Salesman (Salesman Division)**, Kunjungan Salesman (Salesman Visit).
Ini semua halaman AKTIVITAS (operational), BUKAN halaman "manage master data
salesman individual" berdiri sendiri.

**Divisi Salesman (Salesman Division), UI table columns:**
https://edot.gitbook.io/knowledge-base-edot/esuite/markdown/aktifitas-salesman/divisi-salesman-salesman-division.md
Division Code, Salesman Division Name, **Salesman** (daftar nama salesman
anggota divisi), Product Group, Status, Action ("Lihat Detail"). Konsisten
dengan yang sudah kita bangun (`salesman_division_sync_service.py`).

**✅ KETEMU -- cara bikin akun Salesman individual (BUKAN via API `/salesman`,
tapi via User Group di UI eSuite):**
https://edot.gitbook.io/knowledge-base-edot/esuite/akun/cara-menambahkan-akun-salesman-ework-di-esuite.md
Lokasi: menu **Company User -> User Group management**. Field yang WAJIB diisi
menurut gitbook: **name, username, email, phone, password, employee ID,
branch** -- lalu assign akun tsb ke user group **"ework salesman"**.

**⚠️ TEMUAN PENTING -- mismatch dengan skema `POST /salesman` di PDF (section
9.9/9.10) yang sudah dicatat di `sales_entities_gap.md`:** gitbook (cara bikin
akun via UI) SAMA SEKALI tidak sebut field `title`, `department`,
`job_position` -- padahal field itu ditandai **wajib (Yes)** di skema
`POST /salesman` PDF. Ada 2 kemungkinan: (a) UI account-creation ("ework
salesman" user group) itu proses BEDA dari entity `/salesman` (mis. cuma
bikin login app, master data salesman lengkap diisi terpisah lewat halaman
lain yang belum ketemu), atau (b) field title/department/job_position di
API punya default/optional value tersembunyi walau ditandai "Yes" di PDF.
**Belum terjawab -- perlu tanya vendor atau trial langsung di UI eSuite buat
mastiin.** Tidak mengubah status blocker (`sales_entities_gap.md` tetap
DITUNDA), tapi field yang WAJIB diisi manual (name/username/email/phone/
password/employee ID/branch) ini konsisten dengan bukti sebelumnya bahwa
akun salesperson Odoo CBU = slot/rute, bukan identitas personal tetap --
employee ID di sini kemungkinan juga cuma kode slot, bukan employee ID HR
sungguhan.

**Belum ditemukan di gitbook:** halaman "Sales Order" / "Order Management"
belum digali detail (index nemu `sales-order.md` dan
`managemen-pemesanan-order-managemen.md` di bawah
`esuite/images-and-media/managemen-pemesanan-order-managemen/`) -- relevan
kalau nanti perlu riset entity transaksi (bukan master data), belum prioritas
sesi ini.

## 7. "Force Check-In" (di luar radius toko) -- Riset Gitbook (17 September 2026), RESOLVED

**Konteks:** user tanya istilah "force checkin" -- muncul di app eWork sebagai
tombol/link biru **"Force Check-In"** di dialog "You Are Outside the Radius"
saat salesman coba check-in tapi GPS-nya di luar radius toko (screenshot user,
dialog "Check-In Confirmation" -> alert merah "You Are Outside Store Radius" ->
popup "You Are Outside the Radius" dengan link "Force Check-In" + tombol
"Back").

**Hasil cek index `llms.txt` & fetch langsung ke halaman markdown terkait --
istilah "force checkin"/"force check-in"/"paksa checkin" TIDAK muncul secara
literal di teks gitbook manapun**, sudah dicek di semua halaman berikut (fetch
`.md`, bukan cuma index):
- `ework/attendance-kehadiran/absen-hadir.md` (Absen Hadir)
- `ework/attendance-kehadiran/list-kehadiran.md` (List Kehadiran)
- `ework/store-visit-kunjungan-toko/kunjungan-toko.md` (Kunjungan Toko)
- `ework/store-visit-kunjungan-toko/menambahkan-kunjungan-acak.md` (Kunjungan Acak)
- `esuite/markdown/aktifitas-salesman/kunjungan-salesman-salesman-visit.md`
- `esuite/markdown/geofencing/membuat-konfigurasi-geofencing-baru.md`
- `esuite/markdown/geofencing/mengelola-aturan-geofencing.md`
- `esuite/markdown/geofencing/export-data-kunjungan-gagal-karena-aturan-geofencing.md`

Fitur "Force Check-In" itu NYATA (dikonfirmasi screenshot user langsung dari
app eWork), tapi cuma ada sebagai **UI copy di dalam screenshot/gambar**
halaman gitbook (pola yang sama seperti attachment gambar/PDF di bagian 1 & 2
di atas -- tidak ke-extract sebagai teks markdown), BUKAN sesuatu yang
dijelaskan tertulis di badan teks manapun. Halaman gitbook paling relevan
secara tekstual: `membuat-konfigurasi-geofencing-baru.md`, field **"Tindakan
untuk Upaya Check-in di Luar Radius"** dengan 3 opsi: **"Izinkan Kunjungan"**
/ "Blokir kunjungan hanya pada jam operasional" / "Blokir Kunjungan Selama Jam
Operasional dan Setelah Jam Operasional".

**✅ RESOLVED 17 September 2026 -- dikonfirmasi app representative eDot (via
user):** tombol "Force Check-In" **SEHARUSNYA** cuma muncul kalau setup
geofencing toko itu **NON-AKTIF** (konsisten dgn opsi "Izinkan Kunjungan" di
atas). Kasus yang ditemukan user: geofencing toko itu **AKTIF**, tapi tombol
tetap muncul -- **dikonfirmasi GLITCH dari sisi eDot, SUDAH DIJADWALKAN
di-takeout** (bukan API flag/behavior baru yang perlu diakomodasi bridge
kita). Detail percakapan lengkap di `documents/catatan dari wa dev.txt`
(device, section [17 September 2026]).

**Relevansi ke project bridge (Odoo<->eSuite) ini:** info-only, TIDAK ADA
tindak lanjut kode -- bridge fokus ke master data (Product/Customer/Salesman/
Pricelist/Stock), bukan data operasional harian seperti visit/attendance/
geofencing. Topik ini CLOSED kecuali muncul requirement baru.

## 8. Call Plan (Rencana Kunjungan) -- Riset Gitbook (5 Oktober 2026)

**Konteks:** user minta mapping "visit cycle" Odoo (field Studio di Contact:
`x_studio_visit_cycle`, `x_studio_visit_day`, `x_studio_visit_frequency`) ke
versi eDot-nya. Section ini murni hasil riset -- BELUM ada keputusan & belum
ada kode. Status diskusi ada di `SESSION_TRANSFER_NOTE.md` addendum 5 Oktober
2026 (c).

**Halaman yang dibaca (fetch `.md`, isi di bawah = ringkasan hasil fetch,
BELUM dicek langsung ke UI eSuite):**
- https://edot.gitbook.io/knowledge-base-edot/esuite/markdown/call-plan.md
  (index: 2 submenu -- Call Plan Pattern & Call Plan List)
- https://edot.gitbook.io/knowledge-base-edot/esuite/markdown/call-plan/call-plan-pattern.md
- https://edot.gitbook.io/knowledge-base-edot/esuite/markdown/call-plan/call-plan-pattern/cara-mengisi-template-call-plan-pattern.md
- https://edot.gitbook.io/knowledge-base-edot/esuite/markdown/call-plan/call-plan-pattern/ganti-rencana-kunjungan-salesman.md
- https://edot.gitbook.io/knowledge-base-edot/esuite/markdown/call-plan/call-plan-list.md
- https://edot.gitbook.io/knowledge-base-edot/esuite/markdown/call-plan/call-plan-list-1.md
- https://edot.gitbook.io/knowledge-base-edot/esuite/markdown/call-plan/call-plan-list-1/bulk-upload-call-plan-list.md
- https://edot.gitbook.io/knowledge-base-edot/ework/store-visit-kunjungan-toko/kunjungan-toko.md

Belum dibaca: `esuite/markdown/aktifitas-salesman/rencana-kunjungan.md` dan
`.../rencana-kunjungan/melihat-ringkasan-harian-salesman-daily-overview.md`.

**Call Plan Pattern = POLA BERULANG (padanan paling dekat visit cycle Odoo).**
Rencana kunjungan per pasangan Salesman + Customer. Dibuat manual di UI eSuite
atau Bulk Upload template Excel.
- Field form manual: Salesman (Branch terisi otomatis dari salesman), Customer,
  Year, Visit Week Type ("Monthly" / "Yearly"), Visit Month (1-12, hanya utk
  Monthly), Visit Week (Monthly: 1-5, Yearly: 1-53, bisa pilih banyak), Visit
  Day (1 = Senin ... 7 = Minggu, bisa pilih banyak), toggle "Delete Existing
  Call Plan".
- Kolom template bulk upload: `employee_number` ATAU `employee_external_code`
  (salah satu wajib), `customer_number` ATAU `customer_external_code`,
  `branch_number` ATAU `branch_external_code`, `visit_day` (wajib, mis.
  "1,5"), `week` (wajib, mis. "1,3,5"), `week_type` (wajib, 1 = bulan, 2 =
  tahun), `month` (wajib, mis. "4"), `year` (wajib, mis. "2024").
- Validasi: Customer dan Salesman harus berasal dari branch yang sama;
  kombinasi Customer-Salesman-Branch yang tidak valid ditolak.
- **Implikasi:** tipe Monthly terikat ke 1 bulan + 1 tahun tertentu (list
  view punya kolom "Month & Year") -- jadi BUKAN pola abadi; pola bulanan
  perlu dibuat per bulan (atau pakai tipe Yearly dgn daftar minggu 1-53).
  TIDAK ADA field "frequency" -- frekuensi tersirat dari jumlah minggu x hari.

**Call Plan List = KUNJUNGAN BERTANGGAL (hasil pattern + tambahan).** Kolom:
Salesman, Customer, Branch, Call Plan Date, Visit Sequence (urutan kunjungan
dalam 1 hari), Type, Status (Visited / Not Visited), Active, Customer Status.
- Type: "Call Plan Visit" (terjadwal dari rencana), "Non Call Plan Visit"
  (outlet terdaftar tapi tidak dijadwalkan di tanggal itu), "Random Visit"
  (outlet di luar rencana / dibuat sales dari eWork).
- Bisa ditambah manual (Salesman, Customer, Branch, Date, Visit Sequence) atau
  bulk upload (kode salesman, kode outlet, visit sequence, tanggal -- nama
  kolom persisnya tidak ditulis di gitbook).
- Gitbook TIDAK menjelaskan kapan/bagaimana pattern di-generate jadi list.

**Ganti rencana kunjungan salesman (import ulang pattern):** centang "Hapus
Rencana Kunjungan yang Belum Dikunjungi" + isi "Start Deletion From". Yang
dihapus: call plan status Belum Dikunjungi, milik salesman yang ada di file
import, mulai tanggal itu ke depan. Yang TIDAK dihapus: status Visited,
tanggal sebelum start, salesman yang tidak ada di file. Tidak bisa di-undo,
tidak bisa pilih tanggal lampau.

**Di app eWork:** sales memilih toko "dari call plan, non call plan, atau
random" untuk dikunjungi. Cara daftar harian disusun tidak dijelaskan teks.

**Webhook yang tersedia (BUKAN dari gitbook):** PDF `eSuite Synchronization
Document v2.0.0` section 9.26 cuma bilang "Call Plan -- /call-plan, POST only,
owned by ework, schema per ework contract" (tanpa tabel field; `/call-plan`
TIDAK masuk daftar endpoint yang bisa di-GET). Sample Postman vendor:
`{"event":"upsert","data":[{"external_code","salesman":{"id"},"customer":{"id"},
"branch":{"id"},"plan_date":"2026-07-27T17:00:00.000Z"}]}` -- bentuknya 1
baris per TANGGAL (= Call Plan List), bukan pattern, dan tanpa visit sequence.
`plan_date` sample = 28 Juli 00:00 WIB ditulis dalam UTC.

**Belum diketahui (perlu tanya dev eDot):** (1) ada webhook utk Call Plan
PATTERN atau cuma UI/bulk upload? (2) baris yang masuk lewat `POST /call-plan`
bertipe "Call Plan Visit" atau "Non Call Plan Visit"? (3) cara hapus/ganti
call plan lewat webhook (event delete? key = external_code?); (4) zona waktu
`plan_date` utk branch Bali (WITA) & Jakarta (WIB); (5) definisi "week 1" dalam
bulan + perlakuan minggu ke-5; (6) `salesman.id` = id dari `GET /employee`?;
(7) wajibkah customer sudah ter-mapping ke salesman itu (`sales.salesmans[]`)
selain branch sama?

**Relevansi ke project bridge:** catatan penutup section 7 ("bridge fokus ke
master data, bukan data operasional seperti visit") perlu dibaca ulang --
call plan sekarang jadi requirement yang sedang didiskusikan.
