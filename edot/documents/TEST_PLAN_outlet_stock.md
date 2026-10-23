# TEST PLAN -- Stok Outlet (`POST /api/sync/outlet-stock`)

> Dibuat 7 Oktober 2026. Kode: `app/services/outlet_stock_sync_service.py`, `app/api/routes/outlet_stock.py` (5 Oktober 2026).
> Status saat dibuat: lolos test mock, BELUM pernah live test.
> Decision Log: `documents/decision-log/DECISION_LOG_outlet_stock.md`.

## Tujuan

1. Membuktikan endpoint jalan terhadap Odoo & eSuite asli.
2. Menjawab 4 hal yang belum diketahui:
   - format response eSuite `store-stock` (hasil per item ada atau tidak);
   - baris `on_hand 0` tampil atau tidak di eWork (Outlet Detail -> Product Stock);
   - sales mengisi expired di baris placeholder = update baris itu, atau jadi baris baru;
   - push ulang benar-benar mereset isian sales tanpa expired (sesuai peringatan).
3. Menentukan boleh/tidaknya rollout ke semua outlet.

## Perhatian sebelum mulai

- Test ini menulis ke eSuite **PRODUCTION** (`store-stock` baru diumumkan live di production).
- Bridge **tidak punya cara menghapus** baris stok outlet yang sudah terkirim. Karena itu urutannya: 1 outlet dulu, baru beberapa, baru semua.
- `dry_run` default `true`. Push sungguhan hanya terjadi kalau `dry_run=false` diisi eksplisit.
- Berhenti dan jangan lanjut ke tahap berikutnya kalau ada kriteria LULUS yang tidak terpenuhi.

## Persiapan

- [ ] Bridge dijalankan ulang dengan `app/` terbaru; di Swagger (`/docs`) grup **Sync** ada `POST /api/sync/outlet-stock`, dan deskripsinya diawali blok "PERINGATAN -- MENIMPA STOK OUTLET".
- [ ] `.env`: `ESUITE_BASE_URL` mengarah ke production (`https://openapi-esuite.edot.id/v1/webhook`).
- [ ] API key bridge sudah di-Authorize di Swagger.
- [ ] Akun sales TEST bisa login di eWork.
- [ ] Pilih **Outlet A** (outlet uji utama). Syarat:
  - sudah ada di eSuite dan punya sales branch;
  - punya riwayat order invoiced di Odoo;
  - sudah di-mapping ke akun sales test (supaya terlihat di eWork);
  - **belum** punya stok isian sales yang penting (supaya tidak ada data asli yang tertimpa).
- [ ] Catat: Outlet A = `ODOO-PARTNER-______` (nama: ____________).

## Tahap 0 -- Baseline (tanpa perubahan data)

1. `GET /api/debug/pull/warehouse?page=1&limit=50` -> catat jumlah warehouse (terakhir diketahui: 19) dan apakah Outlet A sudah punya warehouse (nama = nama customer).
   - **JANGAN pakai `external_codes` di sini.** Filter itu mencocokkan `external_code` milik WAREHOUSE; warehouse outlet `external_code`-nya kosong, jadi `external_codes=ODOO-PARTNER-{A}` selalu `not_found` (dicoba 7 Oktober, hasil `found: []` -- itu wajar, bukan error).
   - Cara pasti (temuan 7 Oktober): warehouse outlet milik customer = yang `address.id`-nya SAMA dgn `id` customer eSuite (id di URL Detail Customer / field `id` hasil `GET /debug/pull/customers`). Nama saja tidak cukup -- bisa ada customer lain bernama sama.
2. `GET /api/debug/pull/customers?external_codes=ODOO-PARTNER-{A}` -> pastikan `sales.branchs` terisi.
3. `GET /api/odoo/order-history-by-customer?customer_id={A}` -> catat daftar produk yang pernah dibeli (untuk dicocokkan di Tahap 1).
4. Kalau Outlet A sudah punya stok isian: `GET /api/debug/pull/stock-matrix?page=1&limit=200` (catatan 7 Oktober: endpoint ini mengabaikan `limit`, semua baris keluar sekaligus ~1,8 MB -- simpan ke file) -> cari baris dengan `warehouse.name` = nama outlet, catat `warehouse.id`, produk, qty, `batch.code` (expired tersimpan sbg `EWORK{YYYYMMDD}`).

LULUS kalau: customer ketemu di eSuite, `sales.branchs` tidak kosong, ada minimal 1 order `invoice_status` "to invoice"/"invoiced".

## Tahap 1 -- Dry run 1 outlet (tanpa push)

Request:
`POST /api/sync/outlet-stock?external_codes=ODOO-PARTNER-{A}&include_payload=true`

Periksa response:
- [ ] `dry_run: true`, `batches: []`, `pushed_count: 0`.
- [ ] `customer_count: 1`, `item_count` = jumlah produk unik dari Tahap 0 dikurangi yang masuk `skipped_products`.
- [ ] Tiap item di `payload.data` berbentuk: `customer.external_code`, `product_variant.external_code` (`ODOO-PROD-{id}`), `uom_level_code: ""`, `on_hand: 0`, **tanpa** key `expired_date`.
- [ ] Tidak ada pasangan customer+produk yang dobel.
- [ ] `skipped_customers` kosong untuk Outlet A.
- [ ] Field `warning` ada.

Kalau muncul error `ODOO_RPC_ERROR` (mis. field tidak dikenal): berhenti, simpan pesan errornya.

Simpan: response lengkap Tahap 1.

## Tahap 2 -- Push 1 outlet

Request:
`POST /api/sync/outlet-stock?external_codes=ODOO-PARTNER-{A}&include_payload=true&dry_run=false`

Periksa response:
- [ ] `batches[].status` semua `success`, `failed_count: 0`.
- [ ] **Salin utuh `batches[].esuite_response`** -- ini pertama kalinya kita melihat format response `store-stock`. Perhatikan apakah ada ringkasan/hasil per item (pola lama project: HTTP 200 belum tentu tersimpan).
- [ ] `logs/sync_log.csv` bertambah 1 baris `outlet_stock`.

Verifikasi di eSuite:
- [ ] `GET /api/debug/pull/warehouse?page=1&limit=50` -> Outlet A sekarang punya warehouse (dibuat otomatis). Catat `id`, `external_code`, isi `customer`.
- [ ] `GET /api/debug/pull/stock-matrix?page=1&limit=200` (lanjut halaman berikutnya bila perlu) -> ada baris dengan warehouse = Outlet A, jumlah baris = `item_count`, qty 0. Catat isi `batch.code` dan `expired_date`.

Verifikasi di eWork (akun sales test):
- [ ] Outlet A -> Outlet Detail -> Product Stock: list produk muncul, stok 0, tanpa expired.
- [ ] Jumlah produk di list = `item_count`.

LULUS kalau: baris muncul di eSuite DAN di eWork. Kalau response sukses tapi list di eWork kosong -> berhenti, tanya dev eDot (lampirkan request & response).

## Tahap 2 (ulang) -- Push 1 outlet dgn kode 2 langkah (7 Oktober 2026)

Restart bridge dulu (kode berubah). Request sama:
`POST /api/sync/outlet-stock?external_codes=ODOO-PARTNER-{A}&include_payload=true&dry_run=false`

Harapan utk outlet 39353 (1 item, Garam 25kg, belum punya baris):
- [ ] `esuite_summary.seed`: upserted 1 (di `batches[0].seed_response`: `on_hand_before` 0, `on_hand_after` 1).
- [ ] `batches[0].restore_payload[0].on_hand` = 0.
- [ ] `esuite_summary.restore`: upserted 1 (`on_hand_before` 1, `on_hand_after` 0).
- [ ] `pushed_count` 1, `failed_count` 0, `aborted` false, `restore_failed_items` kosong, `existing_stock_count` 0.
- [ ] eWork Product Stock: SUMATRACO Garam 25kg MUNCUL dgn stok 0; TAKARA 10 Units tidak berubah.
- [ ] stock-matrix: ada baris Garam di warehouse `6aa25653123bf4e148ccdb69`, `batch.code` "EWORK", `on_hand` 0.

Kalau Garam TIDAK muncul di eWork walau `restore` upserted: eSuite menghapus/menyembunyikan baris bernilai 0 -> workaround tidak berguna, berhenti & tanya dev.

Kalau `aborted: true` / `restore_failed_items` tidak kosong: item itu tertinggal di stok 1 -- perbaiki manual di eWork (set ke nilai `on_hand` di `restore_failed_items`) atau jalankan ulang setelah penyebabnya beres.

## Tahap 2b -- Kode "kirim 0, kembalikan hanya kalau perlu" (7 Oktober 2026 malam)

Menggantikan cara "kirim 1 lalu kembalikan" (bagian "Tahap 2 (ulang)" di atas tinggal riwayat). Restart bridge dulu.

A. Cari outlet uji BARU yang belum punya stok sama sekali (39353 + Garam sudah punya baris):
`POST /api/sync/outlet-stock?limit=20` (dry run) -> pilih 1 outlet dgn `product_count` kecil, sebut Outlet B.

B. Push Outlet B:
`POST /api/sync/outlet-stock?external_codes=ODOO-PARTNER-{B}&include_payload=true&dry_run=false`
- [ ] `payload.data[].on_hand` semua 0.
- [ ] `esuite_summary.seed.upserted` = `item_count`; `esuite_summary.restore` kosong `{}`.
- [ ] `existing_stock_count` 0, `pushed_count` = `item_count`, `aborted` false.
- [ ] eWork: semua produk muncul dgn stok 0. (Ini bukti capability baru dev.)

**Hasil B (8 Oktober 2026) -- SISI API LULUS:** Outlet B = `ODOO-PARTNER-24226` "2B'S MART". Dry run: 6 item, 9 produk di-skip (belum ada di eSuite; `POST /sync/product` utk ke-9 produk itu balas "Tidak ada produk Saleable" -> di luar kategori Saleable, wajar dilewati). Push: 1 request, `esuite_summary.seed` received 6 / **upserted 6** (tiap item `on_hand_before` 0 -> `on_hand_after` 0), `restore` kosong, `existing_stock_count` 0, `pushed_count` 6, `aborted` false. Item pertama `store_warehouse_created: true` -> warehouse outlet dibuat otomatis oleh eSuite. => **Capability baru dev TERBUKTI di level API** (0 pada pasangan baru = baris dibuat, bukan "unchanged"). **eWork DIKONFIRMASI user 8 Oktober: item tampil di Product Stock outlet dgn qty 0 -> Tahap 2b-B LULUS penuh.**

C. Jalankan ulang request B tanpa mengubah apa pun:
- [ ] `esuite_summary.seed.unchanged` = `item_count`, tidak ada baris baru.

**Hasil jalan ulang Outlet B (10 Oktober 2026):** `esuite_summary.seed` received 6 / upserted 1 / unchanged 5, `restore` kosong, `existing_stock_count` 0, `aborted` false. 5 produk `unchanged` (0 -> 0) = C LULUS (tidak ada baris dobel dari sisi API). Produk `ODOO-PROD-9054` `upserted` dgn `on_hand_before` 0 -> baris tanpa expired utk produk itu TIDAK ADA lagi sebelum run ini, lalu dibuat ulang bridge. Penyebab belum dikonfirmasi user (dugaan: expired diisi di eWork sehingga baris pindah jadi baris ber-expired, atau baris dihapus di eWork). D ("kembalikan") BELUM terbukti: tidak ada item dgn `on_hand_before` > 0.

D. Uji "kembalikan": di eWork isi 1 produk Outlet B dgn stok 5 TANPA expired, lalu jalankan ulang request B:
- [ ] `existing_stock_count` 1; `batches[0].restore_payload` berisi produk itu dgn `on_hand` 5.
- [ ] `esuite_summary.restore.upserted` 1.
- [ ] eWork: stok produk itu TETAP 5.

**Hasil D (10 Oktober 2026) -- "KEMBALIKAN" LULUS di level API:** sebelum run, stok `ODOO-PROD-9054` diisi 5 tanpa expired di eWork (produk yang diisi ternyata 9054, bukan 9055 seperti rencana -- tidak masalah). Langkah 1: 9054 `on_hand_before` 5 -> `on_hand_after` 0 (`upserted`), 5 produk lain `unchanged`. Langkah 2: `restore_payload` = 9054 `on_hand: 5`; `restore_response` 9054 `on_hand_before` 0 -> `on_hand_after` 5 (`upserted`). `existing_stock_count` 1, `esuite_summary.restore` received 1 / upserted 1, `restore_failed_items` kosong, `aborted` false. User 10 Oktober: "sepertinya lulus" (tampilan eWork OK). Temuan "CHOCO MUCHO tampil 3x dgn MPV beda" = 3 varian rasa berbeda (9054/9055/9056), BUKAN duplikat -- dikonfirmasi user.

E. Uji expired: di eWork isi 1 produk lain dgn stok + tanggal kedaluwarsa, lalu jalankan ulang request B:
- [ ] baris ber-expired tidak berubah; baris stok 0 tanpa expired utk produk itu ada (tampil berdampingan -- sudah disetujui user).

## Tahap 3 -- Kirim ulang (idempotent)

Ulangi persis request Tahap 2.

- [ ] Response sukses.
- [ ] Jumlah baris stock-matrix Outlet A **tidak bertambah**.
- [ ] List di eWork tidak dobel.

## Tahap 4 -- Perilaku isian sales & timpa

Pilih 2 produk di Outlet A: **P1** dan **P2**.

4a. Sales mengisi lewat eWork:
- [ ] P1: isi stok 5, **tanpa** tanggal kedaluwarsa.
- [ ] P2: isi stok 7, **dengan** tanggal kedaluwarsa (mis. 31-12-2026).
- [ ] Cek list di eWork dan `GET /api/debug/pull/stock-matrix`: untuk P2, apakah baris placeholder (0, tanpa expired) **berubah** jadi baris ber-expired, atau **tetap ada** di samping baris baru? Catat.
  - Pernyataan user 7 Oktober (belum diuji lewat test ini): hanya stok diubah -> baris ter-update; expired diubah/ditambah -> jadi baris baru. Yang masih perlu dilihat: baris stok 0 tanpa expired tetap tampil atau tidak setelah itu.

4b. Push ulang dari bridge (request Tahap 2), lalu cek lagi:
- [ ] P1 (tanpa expired): menjadi ______ (perkiraan dgn kode 2 langkah: TETAP 5; `existing_stock_count` 1).
- [ ] P2 baris ber-expired: menjadi ______ (perkiraan: tetap 7).
- [ ] P2 baris tanpa expired: ada / tidak ada, nilainya ______.

Hasil tahap ini menentukan:
- apakah teks peringatan di Swagger sudah sesuai kenyataan;
- kalau placeholder 0 tetap tertinggal di samping baris ber-expired (list jadi dobel per produk) -> **jangan rollout dulu**, bahas ulang desain.

## Tahap 5 -- Guard (data yang seharusnya dilewati)

Dry run saja (tanpa `dry_run=false`):

1. Customer yang belum punya sales branch:
   `POST /api/sync/outlet-stock?external_codes=ODOO-PARTNER-{tanpa_branch}`
   - [ ] masuk `skipped_customers`, reason "belum punya sales branch".
2. Customer yang belum ada di eSuite:
   - [ ] masuk `skipped_customers`, reason "belum ada di eSuite".
3. Format salah: `external_codes=ODOO-PROD-1`
   - [ ] HTTP 422 `VALIDATION_ERROR`.

## Tahap 6 -- Beberapa outlet, lebih dari 50 item

1. Dry run: `POST /api/sync/outlet-stock?external_codes=ODOO-PARTNER-{A},ODOO-PARTNER-{B},ODOO-PARTNER-{C}`
   - [ ] `item_count` > 50 dan `batch_count` >= 2 (tambah outlet kalau belum).
2. Push: request yang sama + `&dry_run=false`
   - [ ] semua `batches[].status` = `success`, tiap batch `size` <= 50.
   - [ ] Catat lama eksekusi (untuk estimasi rollout).
   - [ ] Cek acak 1 outlet di eWork.

## Tahap 7 -- Hitung skala (dry run semua customer)

Request: `POST /api/sync/outlet-stock` (semua default, tidak push).

Kalau Swagger timeout, pecah: `?limit=200&offset=0`, `offset=200`, dst.

Catat:
- `total_customers_in_scope` = ______
- `customer_count` = ______
- `item_count` = ______, `batch_count` = ______
- jumlah `skipped_customers` per alasan: belum di eSuite ____ / tanpa sales branch ____ / tanpa riwayat order ____ / semua produk belum di eSuite ____
- jumlah `skipped_products` = ______

Perkiraan lama push = `batch_count` x (1 detik jeda + waktu respon eSuite dari Tahap 6).

Tindak lanjut sebelum rollout:
- customer tanpa sales branch -> mapping dulu (`POST /api/mapping/customer-sales` / mass mapping);
- produk belum di eSuite -> `POST /api/sync/product` dulu.

## Tahap 8 -- Rollout bertahap

Syarat mulai (GO): Tahap 2, 3, 4, 6 lulus; hasil Tahap 4 sudah diputuskan; angka Tahap 7 sudah dilihat.

Jalankan per potongan, urut:
`POST /api/sync/outlet-stock?dry_run=false&limit=100&offset=0`
lalu `offset=100`, `offset=200`, ... sampai `offset` >= `total_customers_in_scope`.

Setelah tiap potongan:
- [ ] `failed_count: 0`.
- [ ] catat `offset`, `customer_count`, `pushed_count`.

BERHENTI kalau: ada batch `failed`, eSuite membalas 429/5xx, atau `esuite_response` berbeda dari yang dilihat di Tahap 2.
Batch yang gagal: jalankan ulang potongan yang sama (aman, kiriman bersifat menimpa/idempotent) -- TAPI ingat kiriman ulang juga mereset isian sales tanpa expired di potongan itu.

Setelah selesai:
- [ ] cek acak 5 outlet di eWork;
- [ ] `logs/sync_log.csv` berisi baris tiap potongan.

## Yang perlu dikirim balik ke sesi Claude

1. Response lengkap Tahap 1 dan Tahap 2 (terutama `batches[].esuite_response`).
2. 1 baris stock-matrix Outlet A hasil Tahap 2 (lihat `batch.code`, `expired_date`, `warehouse`).
3. Hasil pengamatan Tahap 4a dan 4b.
4. Angka Tahap 7.

## Catatan hasil

- Tanggal test: ____________
- Outlet A: ____________
- Tahap 0: LULUS (7 Okt)  Tahap 1: LULUS (7 Okt)  Tahap 2: kode 2 langkah, sisi API LULUS (7 Okt). Tahap 2b-B (kirim 0, outlet 24226): LULUS penuh, API + eWork (8 Okt). Tahap 2b-C (jalan ulang): LULUS (10 Okt). Tahap 2b-D (kembalikan): LULUS (10 Okt). User memutuskan lanjut rollout semua outlet (10 Okt)  Tahap 3: ____  Tahap 4: ____  Tahap 5: ____  Tahap 6: ____  Tahap 7: ____  Tahap 8: ____
- Temuan:
  - 12 Oktober 2026 (alur baru visit-today): 110 outlet dikunjungi -> 80 customer / 1.730 item / pushed 1.729 / unchanged 1.134 / aborted false / 1 gagal Good Stock (ODOO-PARTNER-25207) -> jalan ulang.
  - 10 Oktober 2026 Tahap 8 potongan offset=0: 20 customer / 445 item / pushed 444 / existing 1 dikembalikan / aborted false. 1 item gagal: ODOO-PARTNER-24224 + ODOO-PROD-8856 "failed to resolve the Good Stock location" (warehouse baru dibuat) -> jalankan ulang customer itu. Lanjut offset=100.
  - 10 Oktober 2026 jalan ulang 24224: failed 0 (upserted 1, unchanged 256) -- LULUS.
  - 10 Oktober 2026 potongan offset=100: 83 customer / 1.912 item / pushed 1.909 / aborted false. 3 gagal Good Stock location: 24343, 24355, 24460 -> jalan ulang di akhir. Antrian jalan ulang: ODOO-PARTNER-24343, ODOO-PARTNER-24355, ODOO-PARTNER-24460.
  - 7 Oktober 2026 (baseline, sebelum push apa pun): user memilih `ODOO-PARTNER-39353` sebagai outlet uji. Outlet ini SUDAH punya stok isian manual di eWork: TAKARA Beras Takara 5kg (MPV-04023), Exp Date 10/09/2026, 10 Units. Baris ini ber-expired -> perkiraan TIDAK tersentuh push bridge; kalau produk ini termasuk yang pernah dibeli outlet, setelah push akan terlihat apakah muncul baris kedua (0, tanpa expired) di samping baris ini = jawaban Tahap 4.
  - 7 Oktober 2026, Tahap 0.1 `GET /debug/pull/warehouse` (tanpa external_codes): total **21** warehouse (29 September: 19) = 4 internal (`ODOO-WH-1/3/5/6`) + 17 outlet. Semua warehouse outlet: `external_code` "" dan `customer` {} KOSONG, hanya `address.id` yang terisi.
  - Warehouse baru sejak 29 September: "E2E STORE STOCK TEST (JANGAN DIPAKAI)" id `6ac2f534f5700c0a22c969e3` (dibuat 05 Oct 2026 08:54 WITA, `created_by: 0` = sistem, kemungkinan besar test dev eDot utk store-stock sebelum mengumumkan fitur) dan "SANDI WIJAYA" id `6ac4ae4b0d6e3c8e267e730d` (dibuat 06 Oct 2026 16:16 WITA oleh user app 24702148).
  - Contoh E2E itu menunjukkan warehouse buatan store-stock pun TETAP `external_code` kosong & `customer` kosong -> link ke customer kemungkinan lewat `address.id` (BELUM dikonfirmasi).
  - "07 AM BAKERS CLUB" masih 2 warehouse: (1) id `6aa25653123bf4e148ccdb69`, address `6a9a25225d9e829bbdf16d9a`, `updated_at` 23 Sep 2026 07:49 WITA oleh sistem; (2) id `6a9f805d75419a230ec85d0c`, address `6a9a79bac02cd2f9be807c89`, `updated_at` 10 Sep 2026 11:51 WITA oleh sistem. Yang dipakai store-stock BELUM diketahui -> cocokkan dgn `addresses[].id` hasil GET customers ODOO-PARTNER-39353.
  - 7 Oktober 2026, UI eSuite (Detail Customer): `ODOO-PARTNER-39353` = "07 AM BAKERS CLUB", CUST-00001, **id customer `6a9a25225d9e829bbdf16d9a`** (dari URL). Id ini SAMA PERSIS dgn `address.id` warehouse (1) `6aa25653123bf4e148ccdb69`. Kesimpulan: **`warehouse.address.id` = id CUSTOMER** (bukan id alamat). Warehouse (1) = warehouse outlet customer ini -> perkiraan tujuan push. Warehouse (2) (address `6a9a79bac02cd2f9be807c89`) milik record customer LAIN yang namanya sama -- DIKONFIRMASI user: di Odoo memang ada 2 contact "07 AM BAKERS" (duplikat contact). Belum diketahui stok TAKARA 10 Units diinput di outlet yang mana -> cek `warehouse.id` di stock-matrix.
  - 7 Oktober 2026, Tahap 0.4 `GET /debug/pull/stock-matrix?page=1&limit=200`: mengembalikan SEMUA 1090 baris sekaligus (`limit` diabaikan, `meta.total_page: 0`). Internal 1015 baris (ODOO-WH-1: 446, ODOO-WH-6: 437, ODOO-WH-5: 132), outlet 75 baris (52 milik "E2E STORE STOCK TEST", 23 isian sales).
  - Baris TAKARA Beras 5kg 10 Units ADA di warehouse `6aa25653123bf4e148ccdb69` (= outlet `ODOO-PARTNER-39353`), `batch.code` `EWORK20260910` -> expired 10 September 2026 (format app dd/mm/yyyy), dibuat `cahayatesting3` 10 September. Itu SATU-SATUNYA baris outlet ini. Ber-expired -> perkiraan tidak tersentuh push.
  - Jejak test dev eDot (5 Oktober 08:54 WITA, `created_by` kosong = lewat webhook): 52 baris KATSUOBUSHI 500g di warehouse E2E -- 51 baris dgn expired berbeda (`batch.code` `EWORK2027MMDD`) + 1 baris TANPA expired (`batch.code` `EWORK`, `on_hand` 0). Artinya: (a) baris kiriman store-stock disimpan dgn skema batch yang SAMA dgn isian app; (b) baris placeholder kita akan berbentuk `batch.code` "EWORK", `on_hand` 0, `created_by` kosong; (c) field `expired_date` di GET tetap "" -- expired hanya terbaca dari `batch.code`.
  - Isian sales TANPA expired (`batch.code` "EWORK") yang ADA SEKARANG = yang berisiko ter-reset saat rollout: 19 baris di 3 outlet, 15 di antaranya `on_hand` > 0 -- AREA JAYA 9 baris (Salesman_2, 30 September), LIKA MARGA UD 4 baris, MADE MART 2 baris (Salesman_2, 29 September). Baris ber-expired (07 AM BAKERS CLUB, CITRA MINIMARKET, TOKO KITA GUNTUR, 1 baris LIKA MARGA UD) aman.
  - 7 Oktober 2026, UI eSuite tab Sales customer 39353: Branch "Cahaya Boga Utama, CV" terisi; 9 salesman ter-mapping (termasuk SALES-TESTING-001 s.d. 004) -> syarat sales branch terpenuhi.
  - 7 Oktober 2026, **Tahap 1 (dry run 39353) LULUS**: `customer_count` 1, `item_count` 1, `batch_count` 1, `skipped_customers` & `skipped_products` kosong, `customer_name` "07 AM BAKERS CLUB". Payload: 1 item `ODOO-PROD-9787`, `uom_level_code` "", `on_hand` 0, tanpa `expired_date`. Ini juga bukti live pertama: query Odoo baru (`get_purchased_product_ids_by_customer`) jalan tanpa error RPC, guard customer membaca `sales.branchs` dgn benar, guard produk menemukan variant valid. DICEK 7 Oktober: `ODOO-PROD-9787` = SUMATRACO Garam Sumatraco Sak 25kg (MPV-03872, SKU SLMSUM1011), variant `6a9b8caad3455d1139cb9064` -- BUKAN TAKARA. Baris TAKARA 10 Units = input manual user sendiri utk test UI (bukan produk yang pernah dibeli outlet ini). Perkiraan setelah push: list berisi 2 produk -- TAKARA 10 Units (exp 10/09/2026, tidak berubah) + SUMATRACO Garam 0 tanpa expired (baru). Tahap 4 (isi expired di baris placeholder) dijalankan manual pada baris Garam.
  - 7 Oktober 2026, **Tahap 2 (push 39353, `dry_run=false`) -- CALL SUKSES, HASIL PERLU DIVERIFIKASI**. Response eSuite: `data.summary` = received 1, **upserted 0, unchanged 1**, failed 0, not_processed 0. `data.results[0]`: `status: "unchanged"`, `on_hand_before: 0`, `on_hand_after: 0`, `store_warehouse_created: false`, `expired_date: ""`.
  - Format response store-stock SEKARANG DIKETAHUI: `data.summary` {received, upserted, unchanged, failed, not_processed} + `data.results[]` per item {index, customer_external_code, product_variant_external_code, uom_level_code, expired_date, status, on_hand_before, on_hand_after, store_warehouse_created}.
  - ⚠️ DUGAAN KUAT (belum diverifikasi): kirim `on_hand: 0` utk kombinasi yang BELUM punya baris dianggap "tidak ada perubahan" (0 -> 0) sehingga baris TIDAK dibuat -> list produk tidak muncul di eWork = tujuan pre-load tidak tercapai. Sebelum push, outlet ini tidak punya baris Garam sama sekali. VERIFIKASI: dump stock-matrix (cari SUMATRACO Garam di warehouse `6aa25653123bf4e148ccdb69`) + screenshot Product Stock eWork.
  - `store_warehouse_created: false` = eSuite memakai warehouse yang sudah ada -> cocok dgn temuan `warehouse.address.id` = id customer.
  - 7 Oktober 2026, jawaban dev eDot: "unchanged" karena `on_hand: 0` dan stok awal juga 0; dev minta `on_hand` diisi. Dugaan di atas konsisten dgn jawaban ini. **Tahap 3 dst DITAHAN** sampai ada keputusan (minta dev supaya 0 membuat baris / workaround kirim 1 lalu 0).
  - 7 Oktober 2026, KEPUTUSAN user: workaround B. Kode diubah (2 langkah per batch: kirim 1, lalu kirim `on_hand_before`). **Tahap 2 HARUS DIULANG** dgn kode baru -- lihat "Tahap 2 (ulang)" di bawah. Tahap 4b berubah arti: push ulang seharusnya TIDAK mereset isian sales.
  - 7 Oktober 2026 (sore), catatan proses: penulisan pertama file service versi 2 langkah ke folder `edot` GAGAL diam-diam (isi lama tertulis ulang), sehingga 1x push lagi masih memakai kode lama (0 -> 0, "unchanged", tidak ada perubahan di eSuite). Ditulis ulang & diverifikasi checksum.
  - 7 Oktober 2026, **Tahap 2 (ulang) dgn kode 2 langkah -- SISI API LULUS**: `esuite_summary.seed` upserted 1 (`on_hand_before` 0 -> `on_hand_after` 1), `restore_payload` on_hand 0, `esuite_summary.restore` upserted 1 (1 -> 0); `pushed_count` 1, `failed_count` 0, `existing_stock_count` 0, `unknown_before_count` 0, `aborted` false, `restore_failed_items` kosong, `store_warehouse_created` false. BELUM dicek: Garam 25kg tampil stok 0 di eWork + baris di stock-matrix.
