# Test Plan -- Mapping Wilayah Customer (Odoo regional -> eSuite administrative_level)

> Dibuat 7 Oktober 2026. Fitur: `POST /api/sync/customers` mengisi `addresses[].administrative_level`
> dari `res.partner.village_id` (lookup eSuite + cache), plus param `dry_run`.
> Customer uji: `ODOO-PARTNER-39353` (07 AM BAKERS CLUB -- Bali / Kab. Badung / Kuta Utara / Kerobokan).
> Aturan: jalankan berurutan. Tahap A-B tidak mengubah data eSuite. Tahap C ke atas MENULIS ke eSuite.

## Tahap A -- Persiapan (tidak mengubah data)

### A1. Deploy & cek versi
- Deploy `app/` terbaru, buka Swagger.
- Lulus kalau: `POST /api/sync/customers` punya parameter `dry_run`.
- Catat: environment eSuite yang dipakai bridge (dev atau production).

### A2. Simpan kondisi awal customer uji
- `GET /api/debug/pull/customers?external_codes=ODOO-PARTNER-39353`
- Simpan response ke `sample/` (mis. `baseline_customer_39353.txt`).
- Catat: jumlah `addresses[]`, `id` tiap address, ada/tidaknya `administrative_level`.

### A3. Simpan kondisi awal warehouse outlet
- `GET /api/debug/pull/warehouse?limit=200`
- Catat `address.id` dua warehouse "07 AM BAKERS CLUB" dan bandingkan dengan `addresses[].id` dari A2.
- Tujuan: tahu apakah warehouse outlet terhubung ke customer lewat id address.

## Tahap B -- Dry run (tidak mengubah data)

### B1. Dry run 1 customer
- `POST /api/sync/customers?dry_run=true&external_codes=ODOO-PARTNER-39353&include_payload=true`
- Lulus kalau:
  - `dry_run: true`, `synced_count: 0`, `total_would_send: 1`
  - `administrative_area`: `resolved_customers: 1`, `unique_villages: 1`, `resolved_villages: 1`, `unresolved: []`
  - `payload_preview[0].addresses[0].administrative_level` berisi 4 item urut level 0 -> 3:
    BALI (province), KAB BADUNG (city), KUTA UTARA (district), KEROBOKAN (sub_district, ada `postal_code`)
- Kalau gagal:
  - Error Odoo menyebut `res.village` / `res.subdistrict` / `res.city` / field `village_id` -> akun API belum punya akses baca model wilayah; minta admin Odoo.
  - `customers_without_village_in_odoo: 1` -> field Desa customer ini kosong di Odoo.
  - `reason: not_found_in_esuite` -> lihat `esuite_candidates`, kirim ke Claude (beda ejaan / keyword).
  - `reason: lookup_error` -> kirim isi `error`.

### B2. Dry run 50 customer
- `POST /api/sync/customers?dry_run=true&limit=50`
- Catat: lama proses, `unique_villages`, `resolved_villages`, isi `unresolved`.
- Lulus kalau: selesai tanpa timeout dan tidak ada `lookup_error`.

### B3. Dry run semua customer
- `POST /api/sync/customers?dry_run=true`
- Simpan bagian `administrative_area` ke `sample/dryrun_admin_area_all.txt`.
- Catat: `total_would_send`, `resolved_customers`, `customers_without_village_in_odoo`, `unique_villages`, `resolved_villages`, lama proses.
- Perkiraan: sekitar 122 desa unik (batch 1 Bali), 1-2 menit.
- Kalau timeout: jalankan bertahap pakai `limit` (200, 500, dst) -- hasil yang sudah ketemu tersimpan di cache.

### B4. Dry run semua, diulang
- Jalankan lagi panggilan B3.
- Lulus kalau: angka sama dengan B3 dan jauh lebih cepat (cache bekerja).

### B5. Tindak lanjut daftar `unresolved`
- Kirim hasil B3 ke Claude. Tiap baris dikelompokkan:
  - beda ejaan Odoo vs eSuite -> perbaiki aturan pencocokan atau data Odoo
  - desa tidak ada di eSuite -> laporkan ke dev eSuite
  - `ambiguous` -> cek kandidat
- Syarat lanjut ke Tahap C: tidak ada `lookup_error`, dan `unresolved` sudah dipahami penyebabnya (boleh masih ada isinya).

## Tahap C -- Upsert 1 customer (MENULIS ke eSuite)

### C1. Upsert customer uji
- `POST /api/sync/customers?external_codes=ODOO-PARTNER-39353&include_payload=true`
- Lulus kalau: `synced_count: 1`, `failed_count: 0`, `batches[0].status: success`.
- Simpan response.

### C2. Verifikasi tersimpan di eSuite
- `GET /api/debug/pull/customers?external_codes=ODOO-PARTNER-39353`, bandingkan dengan A2.
- Lulus kalau: address punya `administrative_level` 4 level yang sama dengan payload.
- Cek juga tampilan di dashboard eSuite / eWork: provinsi, kota, kecamatan, kelurahan terisi.

### C3. Cek alamat ganda (PENTING)
- Bandingkan jumlah `addresses[]` dan `id`-nya dengan A2.
- Lulus kalau: jumlah address TIDAK bertambah.
- Kalau bertambah / id berubah: **BERHENTI, jangan lanjut Tahap D.** Artinya tiap upsert membuat address baru; kirim hasil A2 dan C2 ke Claude untuk diperbaiki dulu (kirim id address yang sudah ada).

### C4. Upsert ulang customer yang sama
- Ulangi C1, lalu GET lagi.
- Lulus kalau: jumlah address tetap, `administrative_level` tetap benar.

### C5. Cek warehouse outlet
- `GET /api/debug/pull/warehouse?limit=200`
- Lulus kalau: warehouse "07 AM BAKERS CLUB" tidak bertambah dan `address.id`-nya masih cocok dengan address customer.

### C6. Regresi field lain
- Di hasil GET C2: `customer_groups`, `sales.branchs`, `customer_price_list`, phone/mobile, koordinat masih sama seperti A2.

## Tahap D -- Batch kecil (MENULIS ke eSuite)

### D1. Upsert 20 customer
- `POST /api/sync/customers?limit=20`
- Lulus kalau: `failed_count: 0`; `administrative_area.resolved_customers` sesuai hasil dry run.

### D2. Verifikasi acak
- Ambil 3 `external_codes` dari response D1, GET satu-satu.
- Pilih kalau bisa: 1 dari Kab. Badung, 1 dari Kota Denpasar, 1 dari kabupaten lain.
- Lulus kalau: wilayah benar dan jumlah address tidak dobel.

### D3. Customer tanpa desa
- Cari 1 customer yang field Desa-nya kosong di Odoo, upsert pakai `external_codes`.
- Lulus kalau: tetap `success`, address terkirim tanpa `administrative_level`, `customers_without_village_in_odoo: 1`.

## Tahap E -- Rollout penuh (MENULIS ke eSuite)

- Syarat: C2, C3, C4, C5, D1, D2 semua lulus.
- `POST /api/sync/customers` (tanpa filter).
- Catat: `total_sent`, `synced_count`, `failed_count`, `administrative_area`, nama file `upsert_csv_file`.
- Verifikasi acak 5 customer via GET + cek di eWork.
- Catat hasil ke SESSION_TRANSFER_NOTE (lewat Claude).

## Kapan harus berhenti
- Error akses model wilayah di Odoo (B1).
- `lookup_error` berulang atau timeout terus (B2/B3).
- Jumlah address bertambah setelah upsert (C3/C4).
- Warehouse outlet bertambah / link address putus (C5).
- Field lain berubah atau hilang (C6).

## Yang dikirim ke Claude
- Response B1 (lengkap), bagian `administrative_area` dari B3, hasil GET A2 dan C2.

## Hasil pengujian

### 7 Oktober 2026
- **A1 LULUS** -- param `dry_run` sudah ada (dry run bisa dijalankan).
- **A2 BELUM** -- hasil `GET /api/debug/pull/customers?external_codes=ODOO-PARTNER-39353,ODOO-PARTNER-1655` belum dikirim.
- **A3 SELESAI** -- 21 warehouse (4 internal + 17 outlet). "07 AM BAKERS CLUB" tetap 2 warehouse: address.id `6a9a25225d9e829bbdf16d9a` dan `6a9a79bac02cd2f9be807c89`. Baru sejak 29 September: "SANDI WIJAYA" (buatan sales) dan "E2E STORE STOCK TEST (JANGAN DIPAKAI)" (test dev eSuite).
- **B1 LULUS** -- `resolved_villages: 1`, `unresolved: []`; `administrative_level` 4 level urut 0->3 (BALI V51 / KAB BADUNG V5103 / KUTA UTARA V510306 / KEROBOKAN V51030602, postal_code 80363), id sama persis dengan contoh dev eSuite. Terbukti: akun API Odoo bisa baca model wilayah; `keyword` huruf besar cocok di eSuite.
- Catatan: di Odoo ada 2 partner bernama "07 AM BAKERS CLUB" (id 39353 dan 1655) -> 2 warehouse outlet itu kemungkinan milik 2 customer berbeda, bukan duplikat. Dipastikan lewat A2.
- Berikutnya: A2 (dua customer), B2, B3.

### 7 Oktober 2026 (siang, lanjutan)
- **B2 LULUS** -- `limit=50`: 13 desa unik, 13 ketemu, `unresolved: []`; 15 customer ter-resolve, 35 belum punya Desa di Odoo. `total_matched_in_odoo: 3455`. (`customer_price_list_unresolved` 3 pricelist = hal terpisah, bukan soal wilayah.)
- **GET customer 39353 & 1655 (diambil SETELAH upsert, `updated_at` 7 Oktober 13:06 WITA)** -- jadi ini bukti C2, bukan baseline A2:
  - **C2 LULUS** -- eSuite MENYIMPAN `administrative_level` 4 level utk kedua customer. Catatan: `postal_code` level 3 tidak ikut tampil di GET.
  - **C3 LULUS** -- tiap customer tetap 1 address (upsert MENGGANTI address, tidak menambah). `addresses[].id` di GET selalu "" (address tidak punya id sendiri).
  - **C5 LULUS** -- `warehouse.address.id` ternyata = `id` CUSTOMER (39353 -> `6a9a25225d9e829bbdf16d9a`, 1655 -> `6a9a79bac02cd2f9be807c89`), bukan id address. Link warehouse outlet tidak terpengaruh upsert. Dua warehouse "07 AM BAKERS CLUB" = dua customer berbeda (CBU & SFC), bukan duplikat.
  - **C6 LULUS** -- customer group, branch, dan daftar salesman tetap ada setelah upsert.
- Risiko "alamat ganda / link warehouse putus" DITUTUP.
- **B3 LULUS (dengan 1 catatan)** -- dry run semua: 3.455 customer; 1.311 ter-resolve; 2.143 belum punya Desa di Odoo; 125 desa unik, **124 ketemu**; 0 `lookup_error`. Semua desa Bali cocok.
  - 1 tidak ketemu: `JAKARTA|KOTA ADM JAKARTA PUSAT|MENTENG|MENTENG` (customer Odoo id 47802). Dugaan: beda nama provinsi (Odoo "Jakarta" vs eSuite kemungkinan "DKI JAKARTA"); ejaan eSuite belum terlihat karena 5 kandidat yang tampil bukan yang relevan.
  - Temuan: `keyword` eSuite cocok SEBAGIAN, bukan persis ("MENTENG" ikut mengembalikan "MENTENG KARYA", "BOJONG MENTENG"). Tidak mengganggu -- pencocokan tetap pakai 4 nama persis.
  - Perbaikan kode (7 Oktober): `esuite_candidates` sekarang diurutkan dari yang paling mirip (desa -> kecamatan -> kota sama). Perlu deploy ulang.
- (`customer_price_list_unresolved` 63 pricelist = topik terpisah, bukan soal wilayah.)
- Berikutnya: (1) deploy, jalankan `POST /api/sync/customers?dry_run=true&external_codes=ODOO-PARTNER-47802` -> kirim `esuite_candidates`; (2) D1 batch 20; (3) E rollout setelah keputusan 2 endpoint lain.

### 7 Oktober 2026 (13:33)
- **D1 LULUS** -- `POST /api/sync/customers?limit=20`: `synced_count: 20`, `failed_count: 0`, batch `success`. Wilayah: 6 customer ter-resolve (5 desa, semua ketemu), 14 belum punya Desa di Odoo. CSV: `logs/upsert_customer_07-10-2026_05-33-33.csv`.
- Catatan: `"data": "success"` dari eSuite = tanda terima per batch, bukan bukti tiap customer tersimpan -> D2 tetap perlu.
- Berikutnya: D2 = `GET /api/debug/pull/customers?external_codes=ODOO-PARTNER-40520,ODOO-PARTNER-40360,ODOO-PARTNER-40427,ODOO-PARTNER-35520` (3 customer ber-desa + 1 tanpa desa, sekaligus D3).

### 7 Oktober 2026 (13:37)
- **D2 LULUS** -- GET 3 customer, wilayah sesuai harapan, masing-masing tetap 1 address:
  - 40520 (12 KITCHEN & WINE): BALI / KAB BADUNG / KUTA UTARA / CANGGU (V51030605)
  - 40360 (163 MART): BALI / KOTA DENPASAR / DENPASAR BARAT / DAUH PURI KANGIN (V51710308)
  - 40427 (2 ROOTS): BALI / KAB BADUNG / KUTA SELATAN / PECATU (V51030504)
- **D3 LULUS** -- 35520 (0104 HERO GONDANGDIA, tanpa Desa di Odoo): ter-upsert sukses, address ada, `administrative_level: []`.
- Field lain utuh (customer group, branch, salesman).
- **Catatan penting:** 35520 adalah customer BARU di eSuite (`created_at` = waktu upsert D1, kode `CUST-03088`, branch Sunshine Boga Utama/Jakarta, belum ada salesman). Artinya upsert tanpa filter juga MEMBUAT customer yang belum ada di eSuite -- eSuite ~3.088 customer vs Odoo 3.455 aktif, jadi rollout penuh (Tahap E) akan menambah ratusan customer baru (sebagian besar Jakarta/SBU).
- Sisa sebelum Tahap E: (1) ejaan Jakarta di eSuite (dry run 47802 setelah deploy), (2) keputusan 2 endpoint lain, (3) keputusan cakupan rollout (semua customer vs hanya yang sudah punya Desa).

### 7 Oktober 2026 (13:48) -- keputusan user + perubahan kode
- Dry run 47802 (setelah deploy urutan kandidat): ejaan eSuite = `DKI JAKARTA > JAKARTA PUSAT > MENTENG > MENTENG` (Odoo: `Jakarta > Kota Adm. Jakarta Pusat > Menteng > Menteng`). Provinsi DAN kota beda penulisan.
- Keputusan user: (1) rollout SEMUA customer, dengan catatan khusus saat sync Jakarta; (2) dua endpoint lain DISAMAKAN.
- Kode (belum deploy): aturan nama longgar utk provinsi/kota, resolver dipindah ke `app/core/admin_area.py`, 2 endpoint lain ikut kirim wilayah.

## Tahap F -- Uji perubahan 7 Oktober (jalankan SETELAH deploy, SEBELUM Tahap E)

### F1. Jakarta ketemu lewat aturan nama longgar (tidak mengubah data)
- `POST /api/sync/customers?dry_run=true&external_codes=ODOO-PARTNER-47802&include_payload=true`
- Lulus kalau: `unresolved: []`, `resolved_villages: 1`, dan `matched_by_relaxed_name` berisi
  `esuite_path: "DKI JAKARTA > JAKARTA PUSAT > MENTENG > MENTENG"`.

### F2. Dry run semua, ulang (tidak mengubah data)
- `POST /api/sync/customers?dry_run=true`
- Lulus kalau: `resolved_villages` = `unique_villages` (125/125), `unresolved: []`, Bali tidak berubah (1.311 -> 1.312 customer ter-resolve).
- Periksa isi `matched_by_relaxed_name`: semua pasangan Odoo vs eSuite harus memang wilayah yang sama.

### F3. Endpoint geolocation tidak menghapus wilayah (MENULIS ke eSuite, 1 customer)
- `POST /api/update/customer-geolocation?external_code=ODOO-PARTNER-39353&coordinates=-8.6560885, 115.1529303`
- Lulus kalau: `address_mode: "full"`, payload berisi street + `administrative_level`.
- GET customer 39353: wilayah, street, tipe alamat masih ada; tetap 1 address.

### F4. Endpoint upsert-geo-branch-sales tidak menghapus wilayah (MENULIS ke eSuite, 1 customer)
- `POST /api/mapping/customer-upsert-geo-branch-sales?customer_id=39353&coordinates=-8.6560885, 115.1529303&branch_external_codes=` -- **`branch_external_codes` WAJIB dikosongkan** (default endpoint = `ODOO-COMPANY-2`/SFC, akan mengganti branch customer).
- Lulus kalau: response punya `administrative_area.resolved_customers: 1`; GET customer: wilayah masih ada, branch & salesman utuh.

## Catatan sebelum sync Jakarta (dibaca sebelum Tahap E)
- Rollout tanpa filter OTOMATIS ikut Jakarta (branch Sunshine Boga Utama) -- `/sync/customers` tidak punya filter per company.
- Sekitar 367 customer BARU akan dibuat di eSuite (Odoo 3.455 aktif vs eSuite ~3.088), sebagian besar Jakarta.
- Customer baru itu BELUM punya salesman -> belum muncul di app sales sampai di-mapping (`POST /api/mapping/mass-customer-sales`, setelah akun salesman Jakarta ada di eSuite).
- Wilayah: kebanyakan customer Jakarta belum punya Desa di Odoo -> masuk tanpa wilayah. Setelah Desa diisi di Odoo (project address_matcher), jalankan sync lagi; cek `matched_by_relaxed_name` dan `unresolved`.
- Pricelist: 63 pricelist belum ada di eSuite (`customer_price_list_unresolved`) -> customer terkait masuk TANPA pricelist. Kalau mau lengkap, jalankan `/sync/pricelist` dulu.
- Urutan aman: dry run semua -> cek angka -> baru `POST /api/sync/customers`.

### 7 Oktober 2026 (15:59) -- hasil Tahap F
- **F1 LULUS** -- 47802 (CULINARY JOURNEY INDONESIA PT): `unresolved: []`; `matched_by_relaxed_name` = `DKI JAKARTA > JAKARTA PUSAT > MENTENG > MENTENG`; payload berisi 4 level (V31 / V3173 / V317106 / V31710601, postal_code 10310).
- **F2 LULUS** -- dry run semua: 3.457 customer, 1.314 ter-resolve, 2.143 tanpa Desa, **125/125 desa ketemu**, `unresolved: []`; hanya 1 desa lewat aturan longgar (Menteng).
- **F3 BELUM** -- hasil endpoint geolocation belum dikirim.
- **F4 SEBAGIAN + EFEK SAMPING** -- payload endpoint upsert-geo-branch-sales sudah berisi `administrative_level` (tujuan F4 tercapai di sisi payload; belum GET-verified). TAPI perintah F4 di test plan tidak mengosongkan `branch_external_codes`, jadi default `ODOO-COMPANY-2` ikut terkirim -> `sales.branchs` customer 39353 dikirim sebagai **Sunshine Food and Co, CV**, padahal customer ini milik **Cahaya Boga Utama, CV**. Kesalahan ada di perintah test plan (sudah dikoreksi di atas).
  - Pemulihan: `POST /api/sync/customers?external_codes=ODOO-PARTNER-39353` (branch mengikuti company di Odoo), lalu `GET /api/debug/pull/customers?external_codes=ODOO-PARTNER-39353` -> pastikan branch = Cahaya Boga Utama, salesman masih 9, wilayah ada.
- Tahap E ditahan sampai pemulihan 39353 terverifikasi.

### 7 Oktober 2026 (16:08) -- pemulihan 39353 terverifikasi
- GET customer 39353 (`updated_at` 16:07): branch = **Cahaya Boga Utama, CV** (sudah kembali benar), 9 salesman utuh, 1 address, wilayah 4 level ada (BALI / KAB BADUNG / KUTA UTARA / KEROBOKAN), koordinat & street utuh.
- **F4 LULUS** (wilayah tetap tersimpan setelah endpoint upsert-geo-branch-sales dipakai) dan efek samping branch SUDAH PULIH.
- Sisa: F3 (endpoint geolocation), keputusan default `branch_external_codes`, lalu Tahap E.

### 9 Oktober 2026 (15:39) -- F3
- **F3 LULUS** -- `POST /api/update/customer-geolocation` (39353): `address_mode: "full"`, payload berisi street + `administrative_level` 4 level, eSuite `success`. GET sesudahnya: 1 address, street & koordinat & wilayah utuh, branch Cahaya Boga Utama, 9 salesman utuh.
- **Tahap A-D dan F SELESAI.** Sisa: Tahap E (rollout semua) + keputusan default `branch_external_codes` (tidak menghalangi E).

### 9 Oktober 2026 (16:36) -- dry run semua sebelum Tahap E
- 3.571 customer aktif (naik dari 3.457); **2.667 ter-resolve**; 902 tanpa Desa di Odoo (turun dari 2.143 -- data Desa di Odoo sudah bertambah); 187 desa unik, **186 ketemu**.
- `matched_by_relaxed_name`: 2 desa Jakarta (KELAPA GADING BARAT, MENTENG) -- benar.
- 1 tidak ketemu: `BALI|KAB KLUNGKUNG|KLUNGKUNG|SEMARAPURA KLOD` (customer 39695, 40561), tanpa kandidat sama sekali (`keyword` tidak menemukan apa pun). Dugaan: eSuite menulis "SEMARAPURA KELOD".
- Kode (belum deploy): kalau nama desa sama sekali tidak ketemu, bridge mencari sekali lagi pakai kata pertama nama desa (`search_name`) HANYA untuk mengisi `esuite_candidates` -- tidak dipakai sebagai match.
- Rollout boleh jalan; 2 customer Semarapura masuk tanpa wilayah dan bisa di-sync ulang setelah ejaannya dibereskan.

### 9 Oktober 2026 (16:47) -- ejaan Semarapura
- Dry run 39695 (kode diagnosa sudah deploy): kandidat eSuite di Kec. Klungkung = SEMARAPURA KELOD, KANGIN, TENGAH, KAUH, KAJA.
- Cek master Odoo (`documents/master data modul regional/res.village.csv`), Kec. Klungkung: Semarapura Kaja, Kauh, Tengah, Kangin, **Semarapura Kelod Kangin** (village_51176), **Semarapura Klod** (village_51177). Keduanya tanpa kode pos.
- Kesimpulan: master Odoo sendiri tidak konsisten ("Kelod Kangin" vs "Klod"). "Semarapura Klod" di Odoo = "SEMARAPURA KELOD" di eSuite (desa yang sama, beda ejaan). "Semarapura Kelod Kangin" adalah desa lain.
- **KEPUTUSAN USER (17:09):** ejaan benar = "Semarapura Kelod" (master Odoo salah); perbaikan lewat ALIAS di bridge.
- Kode (belum deploy): `VILLAGE_NAME_ALIASES` di `app/core/admin_area.py`. Uji setelah deploy: `POST /api/sync/customers?dry_run=true&external_codes=ODOO-PARTNER-39695,ODOO-PARTNER-40561` -> `unresolved: []`, `matched_by_relaxed_name` berisi `SEMARAPURA KELOD`; lalu sync tanpa dry_run.
- **Alias LULUS (17:13, sudah deploy):** dry run 39695 & 40561 -> `resolved_customers: 2`, `unresolved: []`, `matched_by_relaxed_name` = `BALI > KAB KLUNGKUNG > KLUNGKUNG > SEMARAPURA KELOD`. Dengan ini dry run semua seharusnya 187/187 desa. Sisa: Tahap E (rollout semua).

### 9 Oktober 2026 (17:15) -- TAHAP E: ROLLOUT SEMUA
- `POST /api/sync/customers`: **3.581 terkirim, 4 batch semua `success`, `synced_count: 3581`, `failed_count: 0`.** CSV: `logs/upsert_customer_09-10-2026_09-15-32.csv` (di container bridge).
- Wilayah: **2.677 customer terisi**, 904 tanpa Desa di Odoo, **188/188 desa ketemu**, `unresolved: []`.
- Lewat aturan longgar / alias (4 desa): MENTENG (2), CIRACAS (1), KELAPA GADING BARAT (1) -- Jakarta; SEMARAPURA KELOD (2) -- alias.
- `customer_price_list_unresolved`: 64 pricelist (topik terpisah).
- Sisa: verifikasi acak GET (lihat Session Transfer Note), register customer Jakarta baru ke sales.

### 10 Oktober 2026
- Default `branch_external_codes` di endpoint upsert-geo-branch-sales DIKOSONGKAN (keputusan user). Setelah deploy, perintah F4 tidak perlu lagi mengosongkan kolom branch secara manual.
