# DECISION LOG -- Stok Outlet (Outlet Stock / Stok Toko)

> **Version: v12** -- diupdate 9 Oktober 2026
> COPY read-only dari Decision Log utama di memory Claude (Project "eDot",
> file `outlet_stock_requirement`). Setiap keputusan baru di topik
> ini: file ini di-update (bukan dibuat baru) dan nomor versi dinaikkan.

---

## 5 Oktober 2026 -- FAKTA VENDOR: endpoint khusus `POST /v1/webhook/store-stock` (LIVE di PROD)

**Menggantikan:** asumsi 29 September "endpoint sama dgn `/stock-matrix`, target warehouse per outlet" + 3 blocker (target `warehouse.id`, cara buat/link warehouse outlet, POST /warehouse `ODOO-OUTLET-{partner_id}`).

**Kontrak endpoint (dari dev eDot):**
- URL: `POST https://openapi-esuite.edot.id/v1/webhook/store-stock`, auth sama dgn webhook lain (Authorization, X-Signature, X-Timestamp, X-Request-ID; client ID & secret sama).
- Body: `{"event": "upsert", "data": [ ... ]}`.
- `customer.external_code` (wajib) -- `ODOO-PARTNER-{id}`. Warehouse outlet dibuat otomatis kalau belum ada. Customer WAJIB punya sales branch.
- `product_variant.external_code` (wajib) -- `ODOO-PROD-{id}`.
- `uom_level_code` (opsional) -- dikosongkan (semua produk Cahaya 1 satuan).
- `on_hand` (wajib, >= 0) -- nilai AKHIR, bukan selisih. 0 = habis.
- `expired_date` (opsional, `YYYY-MM-DD`) -- tanggal beda = baris stok terpisah.

**Aturan:**
- Maks 50 item per request; lebih dari itu dipecah, dikirim BERURUTAN.
- Nilai yang dikirim MENIMPA stok sebelumnya; kirim ulang data sama aman (idempotent).
- Produk yang tidak dikirim tidak diubah.
- Dalam 1 request, kombinasi customer + produk + satuan + expired tidak boleh dobel.

## Keputusan yang masih berlaku (29 September 2026, user)

- Tujuan: list produk di outlet muncul otomatis; sales tinggal isi stok & expired.
- Sumber list produk per outlet = produk yang PERNAH DIBELI outlet (riwayat `sale.order` per customer).
- Pre-load list TIDAK membatasi sales menambah produk lain (limitasi = fitur app eDot, belum ada).

## ~~5 Oktober 2026 -- KEPUTUSAN USER: tanpa guard, cukup peringatan di Swagger~~ (TIDAK BERLAKU -- diluruskan user 7 Oktober, lihat "SKENARIO YANG DIPERLUKAN" di bawah)

> Catatan 7 Oktober: entri ini adalah PEMBACAAN Claude atas pesan user 5 Oktober, bukan kebutuhan user. Isian sales tidak pernah dimaksudkan utk ditimpa.

**Menggantikan:** "risiko menimpa isian sales: coba jalan dulu" (29 September).

- Sales sebenarnya TIDAK perlu mengisi stok manual. Fitur input itu milik FE eDot (tidak bisa kita ubah); yang bisa kita lakukan hanya pre-input data.
- Kalau kiriman bridge menimpa stok isian sales: TIDAK di-skip, cukup ada PESAN PERINGATAN di Swagger supaya aware sebelum upsert.

## ✅ 5 Oktober 2026 -- Endpoint bridge `POST /api/sync/outlet-stock` DIBANGUN (belum live test)

- Param: `external_codes` (`ODOO-PARTNER-{id}`; kosong = semua customer), `limit` + `offset`, `dry_run`, `batch_size` (maks 50), `include_payload`.
- Alur: customer Odoo -> guard customer eSuite (sudah ada + punya `sales.branchs`) -> produk yang pernah dibeli -> guard produk eSuite (variant valid) -> push per 50 item berurutan (jeda 1 detik, gagal per batch tidak menghentikan batch lain).
- Nilai item: `on_hand: 0`, `uom_level_code: ""`, key `expired_date` tidak dikirim.
- Peringatan timpa tampil di 3 tempat: deskripsi endpoint (Swagger), deskripsi param `dry_run`, field `warning` di response.
- File: `app/services/outlet_stock_sync_service.py` (baru), `app/api/routes/outlet_stock.py` (baru), `app/clients/odoo_client.py` (`get_purchased_product_ids_by_customer()`), `app/main.py` (daftar router).

**Asumsi implementasi (belum dikonfirmasi user):**
- `dry_run` default TRUE (endpoint sync lain default false) -- supaya Execute tanpa ubah param tidak menimpa apa pun.
- "Pernah dibeli" = `sale.order.invoice_status` "to invoice"/"invoiced" (sama dgn order history).
- `pushed_count` = item di batch yang call-nya sukses; BUKAN bukti tersimpan (format hasil per item eSuite belum diketahui).

## 7 Oktober 2026 -- TEMUAN DATA LIVE: `warehouse.address.id` = id CUSTOMER eSuite

- Bukti: customer "07 AM BAKERS CLUB" (`ODOO-PARTNER-39353`, CUST-00001) id eSuite `6a9a25225d9e829bbdf16d9a` (URL Detail Customer) == `address.id` warehouse outlet `6aa25653123bf4e148ccdb69`. Baru 1 titik data, belum dikonfirmasi dev.
- Warehouse outlet (termasuk buatan store-stock, contoh "E2E STORE STOCK TEST" milik dev) tetap `external_code` "" & `customer` {} kosong -> satu-satunya kunci ke customer = `address.id`.
- "Duplikat" 07 AM BAKERS CLUB (catatan 29 September) BUKAN 2 warehouse utk 1 customer: warehouse kedua (`address.id` `6a9a79bac02cd2f9be807c89`) milik record customer lain bernama sama. **DIKONFIRMASI user 7 Oktober:** di Odoo memang ada 2 contact "07 AM BAKERS" (duplikat contact), jadi 2 customer & 2 warehouse outlet di eSuite itu wajar.
- Dampak: (a) stok outlet yang SUDAH ADA bisa dilacak per customer: id customer -> warehouse (`address.id`) -> baris `GET /stock-matrix` (`warehouse.id`). Bisa dipakai utk laporan "baris yang akan tertimpa" di dry run kalau nanti diminta (belum dibangun); (b) kekhawatiran "upsert customer dgn address `id: \"\"` memutus link warehouse outlet" kemungkinan TIDAK berlaku (link pakai id customer, bukan id alamat) -- risiko duplikat alamat tetap perlu dicek terpisah.
- Jumlah warehouse 7 Oktober: 21 (4 internal + 17 outlet).

## 7 Oktober 2026 -- TEMUAN DATA LIVE: bentuk baris store-stock di stock-matrix & daftar baris yang berisiko tertimpa

- Sumber: `GET /stock-matrix` 7 Oktober (1090 baris; endpoint mengabaikan `limit`, `meta.total_page: 0`).
- Test dev eDot 5 Oktober (warehouse "E2E STORE STOCK TEST"): baris kiriman webhook store-stock disimpan dgn skema SAMA dgn isian app -- expired di `batch.code` = `EWORK{YYYYMMDD}`, tanpa expired = `batch.code` "EWORK"; `created_by` kosong; `expired_date` di GET tetap "". Placeholder bridge akan berbentuk `batch.code` "EWORK", `on_hand` 0.
- Konsekuensi: yang ditimpa placeholder = baris `batch.code` "EWORK" utk customer+produk yang sama. Per 7 Oktober ada 19 baris isian sales seperti itu di 3 outlet, 15 dgn `on_hand` > 0: AREA JAYA (9), LIKA MARGA UD (4), MADE MART (2) -- semua diinput Salesman_2 29-30 September. Baris ber-expired tidak tersentuh.
- Outlet uji `ODOO-PARTNER-39353`: hanya 1 baris (TAKARA Beras 5kg, `EWORK20260910`, 10 Units) di warehouse `6aa25653123bf4e148ccdb69`; Branch terisi, 9 salesman ter-mapping.

## 7 Oktober 2026 -- HASIL LIVE: format response store-stock + status "unchanged" utk on_hand 0

- Push pertama (1 outlet `ODOO-PARTNER-39353`, 1 item `ODOO-PROD-9787` SUMATRACO Garam 25kg, `on_hand: 0`): HTTP 200.
- **Format response (fakta):** `data.summary` {received, upserted, unchanged, failed, not_processed}; `data.results[]` per item {index, customer_external_code, product_variant_external_code, uom_level_code, expired_date, status, on_hand_before, on_hand_after, store_warehouse_created}. Pertanyaan "format hasil per item" TERJAWAB: eSuite melaporkan per item.
- **Hasil:** summary upserted 0 / unchanged 1; item `status: "unchanged"`, `on_hand_before: 0`, `on_hand_after: 0`, `store_warehouse_created: false`.
- **⚠️ Risiko desain (MENUNGGU verifikasi stock-matrix + eWork):** `on_hand: 0` utk kombinasi yang belum punya baris kemungkinan TIDAK membuat baris (dianggap 0 -> 0). Kalau benar, placeholder 0 tidak memunculkan list produk di eWork -> tujuan requirement tidak tercapai dgn kontrak endpoint sekarang. Opsi kalau terkonfirmasi: (a) minta dev eDot supaya `on_hand: 0` tetap membuat baris; (b) workaround 2 langkah (kirim 1 lalu 0) -- belum diuji, menggandakan request; (c) kirim nilai bukan 0 -- TIDAK disarankan (stok palsu). BELUM ada keputusan.
- **Tindak lanjut kode (belum dikerjakan):** `pushed_count` bridge hanya menghitung call sukses; perlu membaca `data.summary` (upserted/unchanged/failed/not_processed) & menampilkan item `failed`.

## 7 Oktober 2026 -- FAKTA VENDOR: `on_hand: 0` pada produk tanpa baris stok = "unchanged"

- Dev eDot (WA, 7 Oktober): response "unchanged" karena payload mengirim `on_hand: 0` dan stok awalnya juga 0; dev minta `on_hand` diisi.
- Artinya: di eSuite "belum ada baris" = stok awal 0. Kirim 0 tidak dihitung sebagai perubahan. Dugaan "0 tidak membuat baris" dari hasil push pertama KONSISTEN dgn jawaban ini; tampil/tidaknya di eWork belum dijawab eksplisit.
- **KONFLIK dgn desain 5 Oktober** (placeholder `on_hand: 0`, karena Odoo tidak tahu stok fisik outlet): permintaan dev "isi on_hand" tidak bisa dipenuhi dgn data asli. MENUNGGU keputusan user. Opsi:
  - (A) jelaskan tujuan ke dev & minta `on_hand: 0` tetap membuat baris produk (disarankan);
  - (B) workaround bridge 2 langkah: kirim 1 lalu 0 (belum diuji; 2x request; stok palsu sesaat; perlu dipastikan baris tetap ada setelah jadi 0);
  - (C) kirim angka bukan 0 dan dibiarkan -- tidak disarankan (stok palsu terlihat sales).
- (Status saat ditulis: kode belum diubah. Keputusan menyusul di bawah.)

## ~~7 Oktober 2026 (sore) -- KEPUTUSAN USER: opsi B, workaround 2 langkah (kirim 1 lalu kembalikan)~~ (DIGANTI malam yang sama -- lihat "kirim 0, kembalikan hanya kalau perlu" di bawah)

**Menggantikan:** desain 5 Oktober "tiap baris dikirim `on_hand: 0`" DAN keputusan 5 Oktober "tanpa guard, isian sales boleh tertimpa, cukup peringatan".

- User memilih B dgn syarat maksud: workaround ini utk PERTAMA KALI saja; setelah baris ada, stok & expired di-update sales dari UI eWork.
- **Implementasi (supaya benar-benar "pertama kali saja" walau endpoint dijalankan ulang):** per batch, langkah 1 kirim `on_hand: 1`; eSuite membalas `on_hand_before` per item; langkah 2 langsung kirim `on_hand_before` itu. Hasil akhir: produk baru = baris stok 0; stok tanpa expired yang sudah diisi sales = KEMBALI ke nilai semula; stok ber-expired tidak tersentuh. Nilai semula 1 -> langkah 2 dilewati.
- Efek samping yang diterima: stok tampil 1 selama beberapa detik di antara 2 langkah; jumlah request 2x.
- **Aturan gagal:** langkah 2 dicoba ulang 3x (jeda 3 detik). Kalau tetap gagal, atau call langkah 1 gagal, proses BERHENTI (tidak lanjut ke batch berikutnya -- beda dari sync lain). Item yang tertinggal di angka 1 dilaporkan di `restore_failed_items` lengkap dgn nilai yang harus dikembalikan; sisa item di `unprocessed_item_count`.
- Item yang ditolak eSuite di langkah 1 (`status` failed/not_processed) tidak ikut langkah 2, masuk `failed_items`.
- Bridge sekarang membaca `data.summary` & `data.results[]`: field baru `esuite_summary.seed/.restore`, `existing_stock_count`, `unknown_before_count`, `failed_items`, `restore_failed_items`, `aborted`, `abort_reason`, `unprocessed_item_count`. `pushed_count` = item selesai 2 langkah.
- Peringatan Swagger diganti: bukan lagi "menimpa stok", tapi "menulis 2 langkah, stok sempat 1, bisa tertinggal di 1 kalau langkah 2 gagal".
- File: `app/services/outlet_stock_sync_service.py`, `app/api/routes/outlet_stock.py`. Test mock (fake eSuite berstatus, format response = live 7 Oktober) PASS. **BELUM live test.**
- **Belum terbukti live:** (1) baris TETAP ADA & tampil di eWork setelah 1 -> 0; (2) `on_hand_before` akurat utk baris yang sudah diisi sales.
- Daftar "15 baris isian sales berisiko ter-reset" (temuan di atas) TIDAK lagi berisiko dgn desain ini, selama langkah 2 sukses.

## ✅ 7 Oktober 2026 -- SKENARIO YANG DIPERLUKAN (pernyataan user, acuan utama topik ini)

1. Bridge upsert utk MENAMBAHKAN item ke stok outlet dgn stok 0.
2. Sales mengisi qty dan expired secara MANUAL di eWork.

Konsekuensi:
- Isian sales (qty/expired) TIDAK BOLEH ditimpa bridge -- bukan "boleh tertimpa asal ada peringatan".
- Asal-usul salah catat: endpoint store-stock bersifat menimpa (set-to-target); rancangan awal 5 Oktober mengirim `on_hand: 0` utk semua pasangan customer+produk di SETIAP run, sehingga isian sales tanpa expired ikut jadi 0. Itu efek samping rancangan, bukan kebutuhan.
- Implementasi 2 langkah (kirim 1, lalu kirim `on_hand_before`) SUDAH sesuai skenario ini: item baru = stok 0; item yang sudah diisi sales kembali ke nilainya.
- Masih perlu dibuktikan live: (a) baris tetap tampil setelah 1 -> 0; (b) saat sales mengisi expired di baris stok 0, apakah baris itu berubah jadi baris ber-expired atau tetap ada di sampingnya -- kalau "berubah", run bridge berikutnya akan membuat lagi baris stok 0 tanpa expired utk produk yang sama.

## 7 Oktober 2026 (malam) -- FAKTA VENDOR: eSuite kini menyimpan `on_hand: 0` utk produk yang belum ada di tabel stok

- Dev eDot: capability ditambahkan, API contract tidak berubah, minta dicoba lagi. BELUM dites dari sisi kita.
- Live test kode 2 langkah (sore, sebelum update ini): outlet 39353 / `ODOO-PROD-9787` -- seed upserted (0 -> 1), restore upserted (1 -> 0). Tampil/tidaknya di eWork belum dicek.
- **KONFLIK dgn keputusan sore ini (opsi B, kirim 1 lalu kembalikan):** alasan utamanya ("0 tidak membuat baris") tidak berlaku lagi. MENUNGGU konfirmasi user. Usulan pengganti -- "kirim 0, kembalikan hanya kalau perlu":
  1. kirim `on_hand: 0` (1 request) -> produk baru langsung jadi baris stok 0, selesai;
  2. HANYA utk item yang `on_hand_before` > 0 (stok tanpa expired isian sales yang baru saja ikut jadi 0): kirim lagi nilai semulanya.
  - Tetap memenuhi skenario acuan (item baru = 0; isian sales tidak hilang), tanpa angka 1 palsu, request kedua hanya utk sebagian kecil item, dan kalau langkah 2 gagal yang terdampak cuma item yang memang sudah berisi stok.
- Kode BELUM diubah (masih 2 langkah kirim 1 lalu kembalikan -- tetap benar, hanya lebih boros).

## 7 Oktober 2026 (malam) -- Perilaku UI eWork pada baris stok 0 tanpa expired (pernyataan user)

Untuk item X dgn stok 0 dan expired kosong:
- kalau HANYA stok yang diubah dari UI -> baris itu ter-update dgn stoknya;
- kalau expired diubah/ditambah -> menjadi baris BARU (sejalan dgn catatan dev: tanggal berbeda = stok terpisah).

Akibat utk bridge (analisis, belum diuji live):
- Stok diisi tanpa expired -> di run berikutnya bridge mengirim 0, lalu MENGEMBALIKAN angka itu (kasus "kembalikan").
- Expired diisi -> baris ber-expired tidak tersentuh bridge. Baris stok 0 tanpa expired utk produk itu tetap ada / dibuat lagi di run berikutnya, jadi produk tampil sbg 1 baris stok 0 tanpa expired + baris per tanggal expired. Jumlahnya tidak bertambah terus (paling banyak 1 baris tanpa expired per produk).
- Tidak perlu aturan tambahan di bridge, KECUALI user tidak mau baris stok 0 itu tampil di samping baris ber-expired (kalau begitu bridge harus membaca stok outlet dulu -- belum dibangun).

## ✅ 7 Oktober 2026 (malam) -- KEPUTUSAN USER (2 konfirmasi): kirim 0, kembalikan hanya kalau perlu

**Menggantikan:** opsi B sore ini (kirim 1 lalu kembalikan). Alasan: dev eDot menambah capability `on_hand: 0` membuat baris.

1. **Cara kirim (dikonfirmasi):** tiap batch dikirim `on_hand: 0`; HANYA item yang `on_hand_before` > 0 (stok tanpa expired isian sales) dikirim lagi dgn nilai semulanya. Hasil akhir: yang belum ada ditambah (stok 0), yang sudah ada tidak berubah.
2. **Tampilan (dikonfirmasi):** baris stok 0 tanpa expired BOLEH tetap tampil di samping baris ber-expired utk produk yang sama. Bridge tidak membaca stok outlet dulu / tidak melewati produk yang sudah punya baris ber-expired.

Implementasi (7 Oktober malam, mock PASS, BELUM live test):
- Konstanta `SEED_ON_HAND = 1` diganti `PLACEHOLDER_ON_HAND = 0`; logika langkah 2, retry 3x, berhenti saat call gagal, dan pembacaan `data.summary` TIDAK berubah.
- Kegagalan langkah 2 sekarang berarti isian sales tertinggal di 0 (bukan seluruh batch tertinggal di 1); nilai yang harus dikembalikan tetap di `restore_failed_items`.
- Nama field response tetap (`esuite_summary.seed` = langkah 1, `.restore` = langkah 2).
- File: `app/services/outlet_stock_sync_service.py`, `app/api/routes/outlet_stock.py` (teks Swagger disesuaikan). Tidak ada perubahan DB/env/dependency/Docker.
- (a) capability baru dev TERBUKTI di level API 8 Oktober: outlet `ODOO-PARTNER-24226` (2B'S MART), 6 item `on_hand: 0` -> semua `upserted` (0 -> 0), 1 request, warehouse outlet dibuat otomatis (`store_warehouse_created: true` di item pertama). (b) baris stok 0 TAMPIL di eWork -- dikonfirmasi user 8 Oktober (Product Stock outlet 2B'S MART menampilkan item dgn qty 0). (c) langkah "kembalikan" TERBUKTI di level API 10 Oktober: outlet 24226, produk `ODOO-PROD-9054` diisi 5 tanpa expired di eWork -> langkah 1 5 -> 0, langkah 2 0 -> 5 (`existing_stock_count` 1, `restore` upserted 1, tanpa kegagalan). Jalan ulang tanpa perubahan = 5 produk `unchanged` (tidak ada baris dobel).
- Produk yang pernah dibeli tapi di luar kategori Saleable tidak ada di eSuite -> dilewati (`skipped_products`); konsisten dgn aturan sync produk (hanya Saleable). Contoh 2B'S MART: 9 dari 15 produk.

## ✅ 9 Oktober 2026 -- KEPUTUSAN USER: alasan `skipped_products` diperjelas (opsi 3)

Kasus: dry run BAGUS SUPERMARKET SASIH (`ODOO-PARTNER-24393`) -- 6 produk skip "belum ada di eSuite" padahal sync produk sudah jalan. Penyebab: keenamnya di-ARCHIVE di Odoo (`GET /odoo/product?ids=...` = `[]`). Sumber list outlet (riwayat `sale.order.line`) TIDAK difilter active/Saleable/harga, sedangkan `POST /sync/product` hanya kirim produk aktif + `ALL / SALEABLE` + `list_price > 0`.

Opsi yang ditawarkan: (1) biarkan, (2) filter dari awal, (3) tetap tampilkan dgn alasan spesifik. **User pilih opsi 3.**

Implementasi (mock PASS; **LIVE LULUS 9 Oktober** -- dry run 31 customer: 66 produk skip = 65 archived + 1 kategori `ALL`/harga 0, semua `action_needed: false`):
- `skipped_products[]` tiap item kini punya `reason` spesifik + field BARU `action_needed` (bool, additif):
  - "produk di-archive di Odoo" / "kategori bukan ALL / SALEABLE (...)" / "list_price 0 di Odoo" / "produk tidak ditemukan di Odoo (kemungkinan sudah dihapus)" (bisa digabung `; `) + "-- memang tidak disync ke eSuite, abaikan" -> `action_needed: false`.
  - Lolos semua aturan sync produk tapi tetap tidak ada di eSuite -> alasan lama "belum ada di eSuite -- jalankan POST /sync/product dulu" -> `action_needed: true`.
- Aturan cek = SAMA dgn `odoo_client.get_products()` (`ALL / SALEABLE` ilike, `list_price > 0`, aktif).
- Method baru `odoo_client.get_products_sync_status(ids)` -- `search_read` product.product dgn `context: {"active_test": False}` (tanpa context ini Odoo membuang record archived), chunk 1000, hanya dipanggil utk produk yang di-skip.
- Lookup Odoo gagal -> fallback alasan lama (`action_needed: true`); sync TIDAK ikut gagal (ini cuma laporan).
- Item yang dikirim ke eSuite, guard, dan field response lain TIDAK berubah.
- File: `app/clients/odoo_client.py` (method baru, additif), `app/services/outlet_stock_sync_service.py` (method baru `_build_skipped_products()`), `app/api/routes/outlet_stock.py` (docstring). Tidak ada perubahan DB/env/dependency/Docker. Perlu restart bridge.

Catatan umum: endpoint diagnostik `GET /odoo/product` juga TIDAK menampilkan produk archived (tanpa `active_test=False`) -- hasil `[]` = archived atau terhapus.

## 9 Oktober 2026 -- HASIL LIVE: push batch pertama 32 outlet

- 32 customer (multi `external_codes`), 648 item, 13 request: seed received/upserted 648, failed 0, restore kosong (`existing_stock_count` 0), tidak abort. Endpoint terbukti stabil utk 13 request berurutan.
- Belum terbukti: langkah "kembalikan" (`on_hand_before` > 0) -- tidak ada outlet di batch ini yang sudah diisi sales tanpa expired.

## ✅ 10 Oktober 2026 -- KEPUTUSAN USER: alur dinyatakan aman, lanjut rollout SEMUA outlet

- Dasar: tambah produk stok 0 tampil di eWork (8 Oktober), rollout 32 outlet / 648 item (9 Oktober), "kembalikan" isian sales lulus (10 Oktober, user: "sepertinya lulus"), jalan ulang tidak membuat baris dobel.
- Cara rollout (usulan Claude): dry run semua dulu (pakai `limit`+`offset` kalau timeout), lalu push per potongan `limit=100` + `offset` naik; berhenti kalau `aborted` / `restore_failed_items` / `failed_items` tidak kosong. Disarankan dijalankan di luar jam kunjungan sales (isian sales tanpa expired sempat 0 beberapa detik di antara langkah 1 & 2).
- Outlet yang di-skip krn belum punya sales branch / belum ada di eSuite perlu ditindaklanjuti terpisah (mapping customer-sales / sync customers); outlet juga harus ter-register ke sales supaya tampil di app (fakta 8 Oktober).
- **Keputusan user 10 Oktober:** mapping outlet ke sales branch + salesman utk outlet yang di-skip akan DIBERESKAN di pekerjaan mapping visit cycle (lihat `DECISION_LOG_visit_cycle_call_plan.md`), BUKAN di endpoint stok outlet. Endpoint stok outlet tidak diubah; setelah mapping visit cycle jalan, cukup jalankan push stok outlet lagi utk outlet tsb (aman diulang).
- User 10 Oktober (lanjutan): mapping customer -> salesman juga akan di-fix dari Odoo (salesman id) -- detail di `DECISION_LOG_visit_cycle_call_plan.md`.

## 10 Oktober 2026 -- Hasil dry run SEMUA outlet (fakta)

- 3.581 customer in scope -> 2.132 customer, 32.942 item, 659 batch.
- 1.449 customer di-skip: 1.237 tanpa riwayat order invoiced; 168 semua produknya archived / di luar Saleable; 42 belum punya sales branch (20 akun internal / khusus menurut nama -- company sendiri, SAMPLE*, SPONSORSHIP*, EVENT, ENTERTAIN, EMPLOYEE, GENERAL AFFAIR, UNIDENTIFICATION TRANSACTION, SEWA MOBIL; 22 kemungkinan outlet); 2 belum ada di eSuite (nama kosong).
- 434 produk skip, semua `action_needed: false`.
- Daftar lengkap: `documents/outlet_stock_skipped_customers_2026-10-10.csv`.

## 10 Oktober 2026 -- Rollout potongan 1 (`limit=100&offset=0`) -- hasil live (fakta)

- 100 customer diproses -> 20 customer dikirim, 445 item, 9 batch. `pushed_count` 444, `existing_stock_count` 1 (isian sales dikembalikan, restore upserted 1), `aborted` false, `restore_failed_items` kosong, `unprocessed_item_count` 0.
- seed: received 445 / upserted 431 / unchanged 13 / failed 1.
- 1 item gagal: `ODOO-PARTNER-24224` (PT SENTRAL RETAILINDO DEWATA - DC. 001) / `ODOO-PROD-8856`, reason "failed to resolve the Good Stock location", `store_warehouse_created: true`. Dugaan (belum dikonfirmasi dev): location Good Stock belum siap tepat saat warehouse outlet baru dibuat di batch yang sama. Tindakan: jalankan ulang khusus customer itu (aman diulang); kalau tetap gagal -> lapor dev.
- **Jalan ulang `ODOO-PARTNER-24224` (10 Oktober): LULUS** -- 257 item, upserted 1 (item yang tadi gagal), unchanged 256, failed 0. Dugaan timing (location Good Stock belum siap saat warehouse baru dibuat) makin kuat; jalan ulang per customer = cara perbaikan yang dipakai.
- **Potongan 2 (`offset=100`, 10 Oktober):** 83 customer / 1.912 item / 39 batch, pushed 1.909, upserted 1.836, unchanged 73, `existing_stock_count` 0, aborted false, `restore_failed_items` kosong. 3 item gagal, alasan sama ("failed to resolve the Good Stock location", `store_warehouse_created: true`): `ODOO-PARTNER-24343`/`ODOO-PROD-8941`, `ODOO-PARTNER-24355`/`ODOO-PROD-8856`, `ODOO-PARTNER-24460`/`ODOO-PROD-8856`. Antrian jalan ulang di akhir rollout.
- Alasan skip customer baru terlihat: "semua produk yang pernah dibeli belum ada di eSuite" (produk archived / non-Saleable) -- tidak perlu tindakan.
- Aturan berhenti per potongan diperjelas: `failed_items` berisi item gagal per-item (bukan gagal call) TIDAK menghentikan rollout -- dicatat lalu dijalankan ulang per customer. Yang menghentikan rollout: `aborted: true`, `restore_failed_items` tidak kosong, atau HTTP 429/5xx.

## 10 Oktober 2026 -- Rollout SEMUA outlet dijalankan user + gap tersisa

- User menjalankan push ke semua outlet (10 Oktober, siang). Ringkasan response akhir (`failed_items`, `aborted`, `restore_failed_items`) belum dikirim ke sesi Claude.
- Gap setelah rollout (belum diputuskan kecuali disebut):
  1. Item gagal "Good Stock location" -> jalan ulang customer di `failed_items` via `external_codes` (terbukti berhasil utk 24224).
  2. 42 customer tanpa sales branch + 2 belum ada di eSuite -> diberesken di mapping visit cycle (keputusan user 10 Oktober).
  3. Outlet yang belum ter-register ke salesman tidak tampil di app eWork (fakta 8 Oktober) -> mapping customer->salesman dari Odoo (salesman id), keputusan user 10 Oktober.
  4. BELUM ADA mekanisme update rutin: produk baru yang dibeli outlet / customer yang baru pertama order setelah hari ini TIDAK otomatis masuk. Opsi (perlu keputusan user): jalankan ulang manual berkala, scheduled job (mis. harian malam), atau trigger saat order Odoo dikonfirmasi.
  5. Produk yang nanti di-archive di Odoo tetap ada di stok outlet eSuite (bridge tidak menghapus; belum ada event delete yang dipakai).
  6. Pertanyaan dev masih terbuka: GET stok per customer, rate limit.
  7. Cek acak 5 outlet di eWork (Tahap 8) belum dilaporkan.

## 10 Oktober 2026 -- Rollout otomatis per potongan: script `scripts/rollout_outlet_stock.py` (usulan Claude, menunggu dipakai user)

- Latar: push semua outlet dalam 1 request lama sekali (user beri batas 60 menit lagi, siang 10 Oktober). Kalau tidak selesai -> kirim per potongan, tanpa manual.
- Solusi: script lokal (Python standar, tanpa dependency) yang memanggil endpoint yang SUDAH ADA berulang `limit=100` + `offset` naik. Endpoint & logic bridge TIDAK diubah.
- Perilaku: default dry run (`--push` utk menulis); simpan tiap response ke `logs/outlet_stock_rollout/<timestamp>/offset_XXXXX.json`; berhenti kalau `aborted` / `restore_failed_items` berisi / HTTP gagal (429/5xx diulang 3x jeda 30 detik; timeout TIDAK diulang); kumpulkan customer di `failed_items` lalu jalan ulang sekali di akhir (20 customer per call); `--start-offset` utk melanjutkan.
- ATURAN PENTING: jangan pernah menjalankan 2 push stok outlet bersamaan (mis. script saat request "semua outlet" masih jalan di server). Endpoint `def` biasa -> tetap jalan di server walau Swagger/browser timeout. Kalau dua proses tumpang tindih, proses kedua bisa membaca stok yang sedang di-0-kan proses pertama sebagai `on_hand_before` 0, sehingga isian sales TIDAK dikembalikan.
- Lolos uji mock lokal (3 potongan + jalan ulang 2 customer gagal).

## ✅ 12 Oktober 2026 -- KEPUTUSAN USER: GANTI rollout semua outlet -> isi stok per hari berdasarkan outlet yang dikunjungi sales (visit cycle)

- Decision lama yang DIGANTI: "10 Oktober -- lanjut rollout SEMUA outlet" (per potongan `limit=100` + `offset`, script `scripts/rollout_outlet_stock.py`). Alasan user: lambat dan sulit dites. Script tidak dipakai lagi (file dibiarkan, bisa dihapus nanti).
- Fakta pemicu (user 12 Oktober): outlet Jakarta ikut muncul di eDot; prioritas sekarang outlet Bali.
- Alur baru (manual, tiap pagi sebelum sales berangkat):
  1. `GET /api/odoo/visit-today` (opsional `visit_date`, `salesperson_ids`, `company_id`) -> ambil `external_codes_csv`.
  2. `POST /api/sync/outlet-stock?external_codes=<csv>&dry_run=true` -> cek -> ulang dengan `dry_run=false`.
  3. Customer di `failed_items` (mis. "Good Stock location") -> jalankan ulang via `external_codes`.
- Filter wilayah: user belum cek data visit outlet Jakarta, asumsikan bisa terisi -> pakai `company_id` (customer.company_id) bila perlu; `company` tampil per baris utk verifikasi. Salesperson = `res.partner.user_id` (dikonfirmasi user).
- Endpoint `POST /api/sync/outlet-stock` TIDAK diubah.
- Konsekuensi: outlet tanpa jadwal kunjungan (tim FS, data visit kosong/tidak valid) tidak terisi lewat jalur ini -- tetap bisa manual via `external_codes`.
- Lanjutan yang mungkin (belum diputuskan): gabungkan jadi 1 langkah / jadwal otomatis tiap pagi.
- **Hasil live pertama 12 Oktober (Senin, minggu ke-3 Oktober):** `visit-today` -> 110 outlet; push `external_codes` (dry_run=false): 80 customer / 1.730 item / 35 batch, pushed 1.729, upserted 595, unchanged 1.134 (sudah terisi dari rollout sebelumnya), `existing_stock_count` 0, aborted false, `restore_failed_items` kosong. 1 gagal "Good Stock location": `ODOO-PARTNER-25207` / `ODOO-PROD-9793` (warehouse baru dibuat) -> jalan ulang. 30 customer di-skip (16 tanpa riwayat order, 14 semua produknya belum di eSuite / archived); TIDAK ada yang di-skip karena belum punya sales branch. 166 produk skip, semua `action_needed: false`.
- Kendala saat tes (bukan kode): container bridge gagal resolve `sunshinefood.odoo.com` (DNS Docker) -> beres setelah container dijalankan ulang (`docker compose up -d`). Bridge berjalan dari `D:\laragon\www\eDot_cbu_fastapi` (bukan folder `C:\Users\HP\Claude\edot`).

## Belum dijawab dev / belum dites

1. ~~Format response kalau sebagian item gagal~~ -- TERJAWAB 7 Oktober: ada `summary` + `results[]` per item (bentuk item `failed`/`not_processed` belum pernah terlihat).
2. Ada GET stok toko per customer?
3. Sales isi expired di baris placeholder (0, tanpa expired): update baris itu atau bikin baris baru?
4. Baris `on_hand: 0` tampil di list Product Stock eWork?
5. Rate limit / jeda antar request.
6. 15 warehouse outlet lama buatan app (ada duplikat "07 AM BAKERS CLUB") -- dipakai endpoint ini atau dibuat baru?

## Status

Kode sudah ada di folder `edot/app` (5 Oktober 2026), lolos test mock, BELUM live test. Next: dry_run 1 outlet -> push 1 outlet -> cek eWork -> rollout bertahap.
