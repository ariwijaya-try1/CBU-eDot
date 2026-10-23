# Session Transfer Note v8 — Odoo → eSuite Bridge

> Dibuat 6 Agustus 2026. **Menggantikan v7.** Update sesi ini: (1) fix docstring salah di `branch.py` (nyebut `stock.warehouse`, seharusnya `res.company`), (2) `cost` di payload direvisi jadi eksplisit `0` -- **UI eSuite tetap tidak 0**. Postman collection dicek: `cost` field VALID & terdokumentasi resmi (bukan computed). Dugaan sekarang: kemungkinan bug backend eSuite yang treat `0` sebagai falsy (skip update). **Perlu 1 test manual dari user (kirim `cost: 1` langsung via Swagger) sebelum lanjut ubah kode** -- lihat poin 7c. (3) Info baru dari vendor (belum divalidasi): produk tidak bisa hard-delete, cuma inactive; `uom_levels` di payload `/product` butuh field `id` tambahan yang belum kita kirim -- kemungkinan terkait pola "upsert sukses tapi ada anomali data" yang juga kelihatan di kasus `cost`. Lihat poin 7d. Mulai sesi ini, **file ini + Postman collection dibundle di dalam zip kode**, sejajar `app/` dan `CONFIG_NOTES.md`.
>
> **PENTING:** ada file kedua yang WAJIB dibaca bareng ini: **`CONFIG_NOTES.md`**. File itu isinya aturan bisnis & konfigurasi PERMANEN (filter Saleable, currency, UOM, dll) yang beda fungsi dari catatan sesi ini -- jangan diskip.

---

## 🆕 ADDENDUM 21 Oktober 2026 (lanjutan 3) -- Call plan `test_mode`: akun Salesman_12 otomatis (Decision Log visit cycle, section 21 Okt mode tes)

- `POST /api/sync/call-plan` param baru `test_mode=true` -> kirim ke Salesman_12 (`202600012`, konstanta `TEST_EMPLOYEE_ID` di `app/core/salesman_slots.py`). `test_employee_id` tetap ada sbg override (biasanya dikosongkan). Default tetap push normal.
- File: `app/core/salesman_slots.py`, `app/api/routes/call_plan.py`, `CONFIG_NOTES.md` (checklist akun). Restart bridge. Belum dites live: cek `dry_run=true` + `test_mode=true` -> `slots[0].esuite_username` = `Salesman_12`.

## 🆕 ADDENDUM 21 Oktober 2026 (lanjutan 2) -- Cycle `M2` tanpa C (Decision Log visit cycle, section 21 Okt `M2`)

- Konfirmasi user: `M2` polos tidak ada di definisi; `CYCLE_RULES` bridge sudah benar, TIDAK diubah. Bridge tetap skip + lapor di `invalid_rows`.
- Perbaikan data di Odoo: customer dengan `M2` polos diubah ke `M1` (+`F4`). Contoh: `ODOO-PARTNER-24522` (MT02). Bagian dari tahap 1 perbaikan data visit Odoo sebelum push MT.
- **Status (user, 21 Okt): 15 baris `M2` sudah diubah ke `M1` di Odoo.** Next: jalankan ulang dry run call plan / `GET /api/odoo/visit-schedule` -> pastikan tidak ada lagi reason "kode cycle 'M2'" di `invalid_rows`.
- ✅ **Live 21 Okt:** call plan tes BINTANG SUPERMARKET HAYAM WURUK (slot MT02, `M1` Rabu) muncul di eSuite Call Plan List utk Sales Cahaya 12, 21/10/2026, Type "Non - Call Plan". Next: cek tampil di app HP akun Salesman_12; sisa outlet eks-`M2` cek via dry run.

## 🆕 ADDENDUM 21 Oktober 2026 (lanjutan) -- Mapping akun MT02 <-> MT04 ditukar (Decision Log visit cycle, section 21 Okt)

- Konfirmasi user (data Nesa, sales manager): Winaya tetap pakai akun **Salesman_3** (`202600009`) agar data input lamanya tetap ada, kini pegang slot **`[SALES] BAL MT02`**; Fani pakai **Salesman_5** (`202600020`), pegang slot **`[SALES] BAL MT04`**.
- ~~14 Okt: "hanya label person ditukar, slot & akun tetap"~~ -> DIGANTI: akun ikut orang.
- File: `app/core/salesman_slots.py` (2 baris + docstring). Tanpa perubahan DB/env/Docker/dependency. Restart bridge.
- Belum ada push call plan MT asli -> tidak ada data salah alamat. TERBUKA: (1) customer MT02/MT04 yang sudah ter-mapping (customer-sales) ke akun lama perlu dipindah? (2) `202600020` belum diverifikasi ulang masih Salesman_5 -- bridge akan warning kalau username beda. (3) Baris "Salesman_7 / MT02 (miror testing)" di tabel Nesa = akun tes Salesman_12 (`202600012`), TIDAK masuk tabel slot (pakai `test_employee_id`).
- Push MT tetap DITAHAN sampai tahap 1 (perbaikan data visit Odoo).

## 🆕 ADDENDUM 21 Oktober 2026 -- Deskripsi Swagger `test_employee_id` diperjelas

- `app/api/routes/call_plan.py`: hanya teks `description` param `test_employee_id` (tanpa perubahan logic). Isi = field `employee_id` eSuite (angka, mis. `202600016`), BUKAN username/`id` internal/id Odoo; cari via `GET /api/debug/pull/employee`. `employee_id` Salesman_12 masih BELUM tercatat di project.
- Restart bridge agar Swagger memuat teks baru.
- **TES LIVE 21 Okt (mode tes):** `employee_id` Salesman_12 = `202600012` (TERVERIFIKASI UI eSuite, field "Employee ID"; kode `EMP-00010` di bawah nama BUKAN employee_id) (esuite id `6ab28274dbb8a7b1086967e0`, nama "Sales Cahaya 12", branch CBU `...500`). Push slot `[SALES] BAL MT02` (bukan GT01) tgl 21 Okt: 1 jadwal terkirim (TIARA GATSU, `ODOO-CP-TEST-202600012-25227-20261021`), eSuite 200 "success". 20 baris invalid MT02 (M2 di luar daftar; M2C13+F4; M1+F1). NEXT: cek Call Plan List eSuite + app eWork Salesman_12.
- **TERBUKA 21 Okt -- usulan tukar slot MT (tabel dari Nesa, BELUM dikonfirmasi final):** MT02 -> Salesman_3 (`202600009`, Winaya) & MT04 -> Salesman_5 (Fani). KONFLIK dgn mapping 7 Okt / `salesman_slots.py` (MT04 -> Salesman_3, MT02 -> Salesman_5). `salesman_slots.py` BELUM diubah. Perlu: konfirmasi final, cek mapping customer-sales MT di eSuite, `employee_id` Salesman_5 (kode: `202600020`). Baris "Salesman_7 / MT02 miror testing" = akun Salesman_12 `202600012` (tidak masuk tabel slot).

## 🆕 ADDENDUM 16 Oktober 2026 -- Call plan: mode tes ke akun testing (Salesman_12), Decision Log: `DECISION_LOG_visit_cycle_call_plan.md` v22

- Tujuan (user): uji apakah jadwal dari visit cycle Odoo memunculkan visit list di app eWork, pakai akun testing `Salesman_12` + data visit slot `[SALES] BAL GT01`.
- `POST /api/sync/call-plan` dapat 3 param opsional: `test_employee_id` (akun eSuite pengganti, wajib 1 slot), `external_codes` (customer tertentu, `ODOO-PARTNER-{id}`), `limit` (maks N jadwal). Mode tes pakai kode `ODOO-CP-TEST-{employee_id}-{id partner}-{YYYYMMDD}` -> tidak menimpa call plan asli Angga. Tanpa param baru = behavior lama.
- File: `app/services/call_plan_sync_service.py`, `app/api/routes/call_plan.py`. Tanpa perubahan DB/env/Docker/dependency. Restart bridge.
- Status: py_compile + tes mock OK; BELUM dites live. Butuh `employee_id` Salesman_12 (belum tercatat). Langkah tes & pertanyaan terbuka di Decision Log v20 section 16 Oktober.
- Swagger call plan: select box `periode` (`hari_ini` default / `besok` / `minggu_ini` / `minggu_depan`, WITA); `date_from`/`date_to` jadi opsional (diisi = override `periode`). File: `app/api/routes/call_plan.py`.
- Endpoint BARU `GET /api/odoo/visit-schedule?external_codes=ODOO-PARTNER-..` (read-only): jadwal kunjungan outlet N minggu ke depan + sales (slot Odoo & akun eDot). Hitungan dari visit cycle Odoo, bukan data call plan eSuite. File: `visit_schedule_service.py`, `odoo_client.py` (param `partner_ids`), `odoo_get.py`.
- Cek `documents/Jadwal MT.xlsx` vs Odoo -> `documents/cek_jadwal_MT_vs_visit_cycle_2026-10-16.xlsx`: MT02 7/20 sesuai, MT03 1/31 sesuai -> data visit MT di Odoo perlu dikoreksi dulu (tahap 1) sebelum push call plan MT. Asumsi blok I = minggu 1&3, II = minggu 2&4 belum dikonfirmasi.

---

## 🆕 ADDENDUM 14 Oktober 2026 -- Perubahan orang di slot sales MT04 & MT02 + jawaban gap call plan, Decision Log: `DECISION_LOG_visit_cycle_call_plan.md` v18

- Salesman_3 (`[SALES] BAL MT04`) sekarang **Fani**; Salesman_5 (`[SALES] BAL MT02`) sekarang **Winaya** (ditukar). Lainnya tetap: Salesman_1 GT02 Ali, Salesman_2 GT01 Angga, Salesman_4 MT03 Anda, Salesman_6 MT01 Yona.
- Slot Odoo, username eDot & `employee_id` TIDAK berubah -> hanya label `person` di `app/core/salesman_slots.py`. Tanpa perubahan DB/env/Docker/dependency/API. Restart bridge.
- **Kondisi call plan (14 Okt sore):** kode sudah live (`POST /api/sync/call-plan`, `GET /api/odoo/visit-today`); push baru sample GT01 19 Okt (7 jadwal, kirim ulang = update). Push meluas MENUNGGU "tahap 1" user = perbaikan data visit di Odoo (kasus Jimbaran/GT01, beban harian GT, 63 baris di `visit_cycle_perlu_dicek_2026-10-12.xlsx`, Other/Delivery, customer beda branch).
- **Masih terbuka:** (1) 2 agen tambahan -- detail slot/akun belum ada; (2) SMD sementara 2 (SMD1 & SMD2), menunggu konfirmasi Dian -> MT01/MT02 tetap HOLD; (3) nilai `type` jadwal rutin belum diketahui; (4) hapus call plan via UI juga gagal ("hanya stock jadi 0") -> dry run dulu sebelum push; (5) mapping customer -> salesman dari `user_id` Odoo belum ada endpoint (usulan Claude belum diputuskan).
- Catatan lama "Belum ada kode baru" (addendum 12 Okt siang) & "Status: belum ada kode" di Decision Log TIDAK BERLAKU lagi.

---

## 🆕 ADDENDUM 10 Oktober 2026 -- Default `branch_external_codes` DIKOSONGKAN, Decision Log: `documents/decision-log/DECISION_LOG_customer_address_administrative_area.md` (v10) + project memory `customer_upsert_geo_branch_sales_endpoint`

- **Keputusan user:** default `branch_external_codes` di `POST /api/mapping/customer-upsert-geo-branch-sales` diubah dari `"ODOO-COMPANY-2"` (SFC, keputusan 28 Agustus) menjadi `""` (kosong). Kosong = key `branchs` tidak dikirim, branch existing (hasil `/sync/customers` dari company Odoo) tidak berubah. Alasan: customer kini di 3 branch (CBU/SFC/SBU); default SFC terbukti memindahkan ODOO-PARTNER-39353 ke branch salah saat tes 7 Oktober.
- **File:** `app/api/routes/customer_upsert_geo_branch_sales.py` (default + description + docstring). Service TIDAK diubah (logika "kosong = tidak dikirim" sudah ada sejak 7 September). Tidak ada perubahan DB/env/dependency/Docker. py_compile OK. **Perlu deploy.**
- **Status mapping wilayah:** rollout selesai 9 Oktober (lihat addendum 5 Oktober + test plan). Sisa: verifikasi acak GET, register customer Jakarta baru ke sales, isi Desa 904 customer di Odoo.

---

## 🆕 ADDENDUM 12 Oktober 2026 (siang) -- Visit cycle: mapping 6 slot sales FINAL + cek data import visit 10 Oktober, Decision Log: `DECISION_LOG_visit_cycle_call_plan.md` v12 (terbaru v16, 13 Okt)

- **Mapping FINAL (user):** Salesman_1 = BAL GT02 (Ali), Salesman_2 = BAL GT01 (Angga), Salesman_3 = BAL MT04 (Fani, per 14 Okt; sebelumnya Winaya), Salesman_4 = BAL MT03 (Anda), Salesman_5 = BAL MT02 (Winaya, per 14 Okt; sebelumnya Fani), Salesman_6 = BAL MT01 (Yona). Username eDot & slot Odoo tetap; orang boleh berganti -> kunci = slot `res.users` <-> akun eDot, nama hanya keterangan. Menggantikan "mapping sementara" 7 Oktober.
- **Salesman di customer = `res.partner.user_id`** (dikonfirmasi user 12 Oktober) -- menutup pertanyaan terbuka 10 Oktober.
- **Contact tipe Other/Delivery** ikut dibuatkan call plan (sementara; dievaluasi saat penyesuaian dgn visit plan existing sales).
- **Data import 10 Oktober:** 918 contact ber-visit, 875 valid, 855 di 6 slot final; 63 baris bermasalah (kombinasi salah 28, `M2` tanpa C 15, FS ber-visit 4, slot tanpa akun eDot 20) -> `documents/visit_cycle_perlu_dicek_2026-10-12.xlsx`, diperbaiki di Odoo.
- ~~**Belum ada kode baru.** Masih terbuka: id `res.users` & id salesman eSuite per slot, webhook `POST /call-plan` belum terbukti masuk, cek branch customer.~~ (SELESAI 12 Okt -- lihat addendum 14 Oktober.)

## 🆕 ADDENDUM 12 Oktober 2026 -- Stok Outlet: rollout semua outlet DIGANTI isi per hari dari visit cycle; endpoint baru `GET /api/odoo/visit-today`

- Keputusan user: rollout semua outlet (10 Oktober) dibatalkan -- lambat & sulit dites; outlet Jakarta ikut muncul di eDot; prioritas Bali. Script `scripts/rollout_outlet_stock.py` tidak dipakai.
- Alur baru tiap pagi: `GET /api/odoo/visit-today` -> copy `external_codes_csv` -> `POST /api/sync/outlet-stock?external_codes=...` (dry run dulu) -> jalan ulang customer di `failed_items`.
- Kode baru (BELUM dites live): `app/services/visit_schedule_service.py` (baru), `app/clients/odoo_client.py` (+`get_customers_with_visit_schedule()`), `app/api/routes/odoo_get.py` (+route `/odoo/visit-today`). Tidak ada perubahan DB/env/Docker/dependency; restart bridge supaya route baru aktif.
- Next: tes hari ini (Senin 12 Okt = minggu ke-3 Oktober) -> cek `outlet_count`, `per_salesperson`, `company`, `invalid_rows`; tentukan perlu `company_id` atau tidak; lalu push stok outlet utk daftar itu.
- **Hasil live 12 Oktober:** visit-today 110 outlet -> push 80 customer / 1.730 item, 1 gagal Good Stock (`ODOO-PARTNER-25207`, perlu jalan ulang), tidak ada isian sales tersentuh, tidak aborted. Response `visit-today` sendiri (company / invalid_rows) belum dikirim ke Claude -> keputusan perlu `company_id` atau tidak masih terbuka.
- Decision Log: `DECISION_LOG_outlet_stock.md` section 12 Oktober; `DECISION_LOG_visit_cycle_call_plan.md` v11 section 12 Oktober.

## 🆕 ADDENDUM 9 Oktober 2026 -- Stok Outlet: alasan `skipped_products` diperjelas + `action_needed`, Decision Log: `documents/decision-log/DECISION_LOG_outlet_stock.md` (section 9 Oktober, v12)

- **Kasus:** dry run `POST /api/sync/outlet-stock` utk `ODOO-PARTNER-24393` (BAGUS SUPERMARKET SASIH) -> 6 produk skip padahal sync produk sudah jalan. Root cause: produk di-ARCHIVE di Odoo (list outlet diambil dari riwayat order tanpa filter; sync produk hanya kirim aktif + Saleable + harga > 0). Kasus serupa: JSF Saus Gochujang (ADJJSF1057) archived -> `POST /sync/product` balas "Tidak ada produk Saleable".
- **Keputusan user (opsi 3):** produk tetap dilaporkan, `reason` spesifik (archived / bukan Saleable / list_price 0 / terhapus) + field baru `action_needed`. Hanya `action_needed: true` yang perlu `POST /sync/product`.
- **Status:** kode DIUBAH 9 Oktober (mock PASS, BELUM live). File: `app/clients/odoo_client.py` (+`get_products_sync_status()`, context `active_test: False`), `app/services/outlet_stock_sync_service.py` (+`_build_skipped_products()`), `app/api/routes/outlet_stock.py` (docstring). Tanpa perubahan DB/env/dependency/Docker.
- **LIVE LULUS 9 Oktober:** dry run 31 customer (multi `external_codes`) -> 624 item / 13 batch, `skipped_customers` kosong; 66 produk skip = 65 archived + 1 kategori `ALL` & list_price 0 (`ODOO-PROD-18625`), SEMUA `action_needed: false`.
- **PUSH LIVE LULUS 9 Oktober:** 32 customer (31 + COCO MART CEMAGI `ODOO-PARTNER-44196`), 648 item / 13 batch -> `esuite_summary.seed` received 648 / upserted 648 / failed 0, `restore` kosong, `existing_stock_count` 0, `aborted` false, `restore_failed_items` kosong. Rollout outlet stok batch pertama SELESAI.
- **Next:** (1) cek di eWork 1-2 outlet (mis. PANDE PUTRI BATUR SARI) tampil list produk stok 0; (2) langkah "kembalikan" **TERBUKTI LIVE 10 Oktober** (outlet 24226, `ODOO-PROD-9054` isian 5 tanpa expired: 5 -> 0 -> 5, `existing_stock_count` 1, restore upserted 1; tinggal konfirmasi tampilan eWork); (3) **KEPUTUSAN USER 10 Oktober: alur aman, lanjut ROLLOUT SEMUA outlet** -- dry run semua (limit/offset kalau timeout) -> push per `limit=100` + `offset` -> cek `aborted`/`restore_failed_items`/`failed_items` tiap potongan -> spot-check eWork. Jalankan di luar jam kunjungan sales. Temuan "CHOCO MUCHO 3x" = 3 varian rasa, bukan duplikat. Outlet yang di-skip krn belum punya sales branch / belum ter-register ke salesman: keputusan user DIBERESKAN di pekerjaan mapping visit cycle (bukan di endpoint stok outlet); setelah itu push stok outlet diulang utk outlet tsb. **Dry run SEMUA outlet 10 Oktober:** 3.581 customer in scope -> 2.132 customer / 32.942 item / 659 batch akan dikirim; `existing_stock_count` 0 (dry run). 1.449 customer di-skip: 1.237 tanpa riwayat order invoiced, 168 semua produknya archived/di luar Saleable, 42 belum punya sales branch (20 di antaranya akun internal/khusus: company sendiri, SAMPLE, SPONSORSHIP, EVENT, dll -- dugaan dari nama), 2 belum ada di eSuite. 434 produk skip, semua `action_needed: false`. Daftar lengkap: `documents/outlet_stock_skipped_customers_2026-10-10.csv` (kolom prioritas & tindakan). Push semua BELUM. **Rollout potongan 1 (offset=0) SELESAI 10 Oktober:** 20 customer / 445 item, pushed 444, 1 isian sales dikembalikan, tidak aborted; 1 item gagal "failed to resolve the Good Stock location" (`ODOO-PARTNER-24224` / `ODOO-PROD-8856`, warehouse baru dibuat di batch yang sama) -> jalankan ulang customer itu, lapor dev kalau tetap gagal. Jalan ulang 24224: LULUS (failed 0). **Potongan 2 (offset=100) SELESAI:** 83 customer / 1.912 item, pushed 1.909, 3 gagal Good Stock location (24343, 24355, 24460) -> antrian jalan ulang di akhir. **Next: offset=200, 300, ... s/d 3500**, kumpulkan customer `failed_items`, lalu jalan ulang sekaligus via `external_codes`. **UPDATE siang 10 Oktober: user sudah push SEMUA outlet** (ringkasan akhir belum dikirim). Gap tersisa: jalan ulang `failed_items`, outlet tanpa branch/salesman (-> mapping visit cycle), BELUM ada update rutin utk pembelian/customer baru (perlu keputusan: manual berkala / scheduled job / trigger order), produk yang di-archive belakangan tidak dihapus dari stok outlet, cek acak eWork. Detail: Decision Log section "Rollout SEMUA outlet dijalankan user + gap tersisa". **Push semua outlet lambat** (siang 10 Oktober, user tunggu maks 60 menit lagi). Cadangan: `scripts/rollout_outlet_stock.py --push` (loop limit/offset otomatis, berhenti kalau aborted/restore_failed, jalan ulang failed_items di akhir). JANGAN jalankan bersamaan dengan push yang masih berjalan di server.
- **Tips:** `GET /odoo/product` tidak menampilkan produk archived; hasil `[]` = archived/terhapus. ID di URL form Products Odoo = product.template (bukan product.product yang dipakai `ODOO-PROD-{id}`).

## 🆕 ADDENDUM 8 Oktober 2026 -- FAKTA: customer baru wajib di-register ke sales supaya muncul di app eWork, Decision Log: `documents/decision-log/DECISION_LOG_visit_cycle_call_plan.md` (section 8 Oktober)

- **Kasus:** outlet baru ULU MART PECATU (push dari Odoo, belum punya sales).
- **Fakta (dikonfirmasi user):** setelah customer di-add ke eDot, HARUS di-register ke sales (manual UI eSuite ATAU `POST /api/mapping/customer-sales` di Swagger, `mode=add`, branchs + salesmans bersamaan) -- baru muncul di list outlet app salesman yang bersangkutan. Random Visit bukan jalan pintas.
- **Alur outlet baru:** `POST /sync/customers` -> register ke sales (UI / mapping) -> (opsional) geolocation + pricelist mapping -> baru bisa dikunjungi.
- **(TERJAWAB 10 Oktober)** ~~KONFLIK TERBUKA: asumsi 17 September "fase 1 semua sales lihat semua customer selama branch sama; mapping per sales = fase 2" tidak sesuai perilaku app.~~ User 10 Oktober: **mapping customer -> salesman di-fix dari Odoo (salesman id)**, dikerjakan bersama mapping visit cycle; bergantung tabel slot salesman Odoo -> akun eDot di bridge (baru Ali terverifikasi per 7 Oktober); field Odoo "salesman id" di customer belum ditentukan. Lihat `DECISION_LOG_visit_cycle_call_plan.md` section 10 Oktober.
- Tidak ada perubahan kode / API / DB / env.

---

## 🆕 ADDENDUM 5 Oktober 2026 (c) -- Riset mapping Visit Cycle Odoo -> Call Plan eSuite (definisi kode Odoo DIKONFIRMASI user; jalur eSuite BELUM diputuskan; belum ada kode), Decision Log: `documents/decision-log/DECISION_LOG_visit_cycle_call_plan.md`, detail gitbook: `documents/ESUITE_GITBOOK_NOTES.md` section 8

- **Requirement (user, 5 Oktober):** mapping "visit cycle" di Odoo ke versi eDot-nya. Masih tahap diskusi.
- **Sumber Odoo (dari export Excel, BUKAN live; tipe field belum dicek):** 3 field Studio di Contact -- `x_studio_visit_frequency` (F1/F2/F4), `x_studio_visit_cycle` (M1, M2C13, M2C24, M4C2, M4C3, + "M2" tanpa C), `x_studio_visit_day` (Senin-Jumat, 1 hari per customer, huruf besar/kecil campur). Terkait: `user_id` (Salesperson, slot `[SALES] BAL GT01` dst), `x_studio_sales_team`, `x_studio_delivery_route`.
- **Definisi kode (DIKONFIRMASI user 5 Oktober, user menyebutnya "asumsi saya" -- belum dicek ke tim sales/admin Odoo):** Frequency = jumlah kunjungan per bulan (F1 = 1x, F2 = 2x / dua minggu sekali, F4 = 4x / tiap minggu). Cycle = pola minggu dalam 1 bulan (4 minggu): M = interval minggu, C = minggu ke berapa. M1 = tiap minggu, tanpa C (F4); M2C13 = minggu ke-1 & ke-3 / ganjil (F2); M2C24 = minggu ke-2 & ke-4 / genap (F2); M4C2 = sebulan sekali di minggu ke-2 (F1); M4C3 = sebulan sekali di minggu ke-3 (F1). Visit day = hari kunjungan, Senin-Jumat. Contoh: M2C13 + F2 + Selasa = Selasa di minggu ke-1 dan ke-3 setiap bulan. Pola per BULAN -> cocok dgn Call Plan Pattern `week_type` Monthly.
- **KEPUTUSAN USER 5 Oktober -- tim FS TIDAK masuk visit cycle:** field visit FS kosong karena memang tidak dipakai (bukan belum diisi); FS sementara pakai random visit (sales buat visit manual di eDot) sampai ada perubahan. Bridge: tidak ada call plan utk FS; field visit kosong = dilewati (bukan error); lingkup = customer yang field visit-nya terisi (sekarang GT/MT).
- **KEPUTUSAN USER 5 Oktober -- baris yang melanggar definisi diperbaiki di Odoo** (project Odoo 19), bukan dikoreksi bridge. Bridge tidak menebak nilai visit; DIKONFIRMASI user: baris yang masih tidak valid dilewati + dilaporkan di response.
- **INFO SALES 5 Oktober -- cara hitung minggu:** M2C13 + Senin di Oktober 2026 -> Senin 28 September = minggu ke-1 Oktober. Jadi minggu = minggu kalender Senin-Minggu yang boleh melewati batas bulan (BUKAN "Senin pertama bulan itu"); hasil: 28 Sep & 12 Okt. M1 = tiap minggu kalender. Lewat `POST /call-plan` aturan ini pasti bisa (bridge hitung tanggal); lewat Pattern tergantung definisi minggu eDot.
- **Mapping salesman (USULAN 5 Oktober, belum dikonfirmasi):** fakta user: eDot punya 12 slot sales, 6 terpakai, semua non-FS. Usulan: tabel kecil `res.users` id Odoo -> `employee_id` eSuite (kunci ID, bukan nama -- nama slot pernah berubah "GT 1" -> "[SALES] BAL GT01"). Slot Odoo ber-visit: BAL GT01/GT02/MT01-MT04 (dugaan = 6 slot eDot terpakai). FS, slot eDot kosong, slot umum (GT ALL/MT ALL/Office/NKA/ASM-BM) tidak dipetakan. Butuh: hasil `GET /api/debug/pull/employee` + `GET /api/odoo/salesperson`.
- **UPDATE 6 Oktober -- akun eDot & pola slot:** user kirim hasil GET employee (18 akun). 12 akun slot `Salesman_1`..`12`, semua branch Cahaya Boga Utama; 4 bernama: `Salesman_1` Ali-GT `202600016`, `Salesman_2` Angga-GT `202600019`, `Salesman_3` Winaya-MT `202600009`, `Salesman_4` Anda-MT `202600014`. Ada akun test ganda utk 4 orang yang sama (`cahayatesting1`-`4`, `202600005`-`008`) -- JANGAN dipakai. Temuan dari Sheet2 file 19 Agustus: slot Odoo vs orang TIDAK 1:1 (GT 1 = Winaya + Abi per wilayah; MT 4 = Abi + Winaya + Ali; hanya GT 2 = Ali yang bersih), dan susunan orang sudah berubah (Agustus: Abi/Fani/Yona; eDot sekarang: Angga/Anda) -> data Agustus tidak bisa dipakai utk mapping. BELUM ada: pasangan orang <-> slot Odoo saat ini (user masih cari pola), id slot Odoo, konfirmasi 1 slot = 1 orang. Catatan teknis: shell di laptop gagal start 6 Oktober, file diedit lewat stage/commit.
- **MAPPING SEMENTARA 7 Oktober (user):** BAL GT02 = Ali (`Salesman_1`, `202600016`, satu-satunya yang TERVERIFIKASI Odoo + eDot); BAL GT01 = Angga (`Salesman_2`, `202600019`); BAL MT04 = Winaya (`Salesman_3`, `202600009`); BAL MT03 = Anda (`Salesman_4`, `202600014`); BAL MT02 = Fani (`Salesman_5`, `202600020`); BAL MT01 = Yona (`Salesman_6`, `202600017`). KEPUTUSAN 7 Oktober: tabel mapping disimpan DI BRIDGE; minggu ke-5 utk M2/M4 sementara dilewati (M1 tetap tiap minggu). TERBUKA: jalur ke eSuite (rekomendasi Claude `POST /call-plan`, uji coba dari Ali / GT02), id `res.users` tiap slot, cek branch customer, konfirmasi sales.
- **KEPUTUSAN 7 Oktober (sore):** lanjut jalur `POST /call-plan`. Kirim ulang `external_code` sama = DIUJI langsung; hapus / batal = manual via UI eDot; cek hasil = via UI; zona waktu `plan_date` = asumsi user WITA (catatan Claude: format vendor `T17:00:00.000Z` hari sebelumnya aman di WIB & WITA, 00:00 WITA berisiko mundur 1 hari -- diuji). NEXT: tes manual lewat Postman vendor (PROD): 1 baris customer BAL GT02 -> cek UI -> kirim ulang kode sama tanggal beda -> hapus manual. Bridge belum punya endpoint call plan (belum ada kode).
- **Tes call plan langkah 1 SELESAI (10 Oktober):** customer `ODOO-PARTNER-39092` (4W MINI MARKET SINDU) di eSuite: id `6a9a82df0e20e15d6b0eb0fa`, branch Cahaya Boga Utama (`...500`) OK, `sales.salesmans[]` berisi 9 akun (termasuk `cahayatesting1` & `Salesman_1`). Kirim 1 (10 Oktober): respons 200 success TAPI tidak muncul di UI Call Plan List (20-31 Okt) -> dugaan silent fail; Kirim 2 ditunda; Kirim Angga (`Salesman_2`) juga 200 tapi tidak muncul -> bukan masalah akun test. Info user: antrian delay atau tidak terkirim, di-fix Senin 12 Oktober. Cek Senin 12 Oktober: tetap kosong di Call Plan List (20-31 Okt, SINDU) -> kiriman Sabtu tidak masuk. NEXT: konfirmasi fix ke dev -> kirim ulang payload Angga sekali -> cek 10-15 menit. Cadangan: Upload Bulk Call Plan List (Excel bertanggal dari bridge), template belum dilihat.
- **12 Oktober 10:44 -- DEV eDot: payload `/call-plan` yang benar** (contoh Postman lama SALAH): `employee.id` (bukan `salesman`), `date_plan: {"date": <unix epoch detik>}` (bukan `plan_date` ISO), `type: "non_generated"`. Contoh dev (`CBU-CP-DEVTEST-20261012-02`, Angga, SINDU, epoch 1791849600 = 13 Okt 00:00 UTC) TERSIMPAN di DB PROD. TERVERIFIKASI UI 12 Okt 11:05: baris muncul, tanggal 13/10/2026 benar, Type "Non - Call Plan". NEXT: tanya dev nilai `type` utk "Call Plan" (jadwal rutin); tes kirim ulang `external_code` sama (14 Okt) update vs dobel; hapus baris tes.
- **12 Oktober -- `POST /api/sync/call-plan` DIBANGUN:** pilihan user = endpoint bridge. Param `slots` (multi-select), `date_from`/`date_to` (maks 31 hari), `dry_run` default TRUE. File baru `app/core/salesman_slots.py` (mapping 6 slot), `app/services/call_plan_sync_service.py`, `app/api/routes/call_plan.py`; `app/main.py` +1 router. Live pertama 13:08 gagal (slot tidak ketemu di res.users) -> FIX: id slot dari `user_id` customer. Dry run live 13:22 OK: 129 jadwal Angga 19-23 Okt (semua M2C24), 1 skip (MIL'S KITCHEN BALI beda branch), 2 invalid (M2C24+F4). NEXT: push 19 Okt saja (7) -> cek UI -> push ulang -> cek tidak dobel -> push 19-23 Okt. Detail: Decision Log v14.
- **CATATAN LAPANGAN 12 Oktober (user):** 1 user/slot Odoo dipakai beberapa orang sales (mis. `[SALES] BAL MT04` sampai 4 orang); masih dikomunikasikan ke lapangan; asumsi user: visit cycle akan disesuaikan ke pembagian yang benar. Dampak: jadwal slot bersama bisa jatuh ke 1 akun yang salah sampai dirapikan; slot teraman utk uji = GT02 (Ali). Data dilewati dry run GT01: MIL'S KITCHEN BALI (beda branch), 2 invalid (M2C24+F4), beban harian tidak rata. Detail: Decision Log section 📌 12 Oktober.
- **12 Oktober 15:02 -- TERBUKTI:** kirim ulang `external_code` sama ke `/call-plan` = UPDATE (19 Okt tetap 7 baris). Temuan lapangan: Angga bilang 13 Okt ke Jimbaran -> belum dibandingkan. Response call-plan sekarang punya `delivery_route` + `per_date_route` (perlu restart bridge). NEXT: dry_run GT01 12-23 Okt, bandingkan rute Selasa 13 vs 20 dgn jadwal Angga; jangan push 19-23 Okt dulu.
- **13 Oktober -- INFO MEETING (user):** MT1 & MT2 masing-masing membawahi 3 sales merchandiser (SMD1-3); MT3, MT4, GT1, GT2 selalu fix schedule. Dampak (usulan, belum diputuskan): slot fix schedule cocok utk call plan; push MT01/MT02 ditahan sampai jelas SMD perlu akun eDot sendiri & jadwal Odoo per SMD atau per MT. GT01 19-23 Okt tetap HOLD (menunggu: RUTE berapa = Jimbaran, TABANAN area Angga?). Detail: Decision Log v16 section 📌 13 Oktober.
- **Aturan delivery (user, 12 Oktober):** update langsung ke folder `C:\Users\HP\Claude\edot`; zip HANYA kalau diminta.
- **Target eSuite (2 lapis, lihat gitbook notes section 8):** (1) **Call Plan Pattern** = pola berulang per Salesman + Customer + Branch: `year`, `week_type` (1 bulanan / 2 tahunan), `month`, `week` (1-5 atau 1-53, multi), `visit_day` (1 = Senin ... 7, multi) -- dibuat lewat UI / bulk upload Excel, webhook-nya BELUM diketahui ada. (2) **Call Plan List** = kunjungan bertanggal; ini yang cocok dgn webhook `POST /call-plan` (`external_code`, `salesman.id`, `customer.id`, `branch.id`, `plan_date`).
- **Usulan mapping (BELUM disetujui):** `visit_day` Senin..Jumat -> 1..5; `visit_cycle` -> `week` (M1 -> 1,2,3,4[,5]; M2C13 -> 1,3; M2C24 -> 2,4; M4C2 -> 2; M4C3 -> 3); `visit_frequency` tidak dikirim (tidak ada field tujuan), dipakai sbg validasi silang saja; `user_id` -> salesman; company customer -> branch.
- **Temuan data (export 19 Agustus, 2.935 contact):** terisi 269 (~9%), semuanya tim GT/MT (+ sedikit OFFICE/NKA); tim FS (1.472 contact) 0 terisi. Dari 265 yang lengkap: 252 konsisten, 13 tidak (M2C24+F4, M1+F1, M1+F2, "M2" tanpa C); 4 terisi sebagian. File user 5 Oktober (190 baris, hasil to import geolocation): 48 terisi, 5 tidak konsisten (M1+F1 x3, M1+F2 x2).
- **Keputusan TERBUKA (perlu user):** (a) arti kode SUDAH dijawab (lihat bullet definisi); SISA: (a1) SUDAH diputuskan user 5 Oktober: minggu kalender yang memuat tanggal 1 = minggu ke-1 bulan itu (Senin 26 Oktober 2026 = minggu ke-1 November; M2C13 Senin = 28 Sep, 12 Okt, 26 Okt, 9 Nov, 30 Nov); (a2) M2/M4 melewatkan minggu ke-5 (jeda 3 minggu) diterima atau tidak -- usulan Claude: diterima; (b) jalur: Pattern (paling mirip Odoo; kalau tanpa webhook = bridge generate file template bulk upload, admin upload) vs List via `POST /call-plan` (otomatis penuh, tapi bridge harus generate tanggal + butuh jadwal rutin); (c) join key Salesperson Odoo <-> employee eSuite -- blocker lama (27 & 31 Agustus, opsi field Studio di `res.users` atau tabel mapping di bridge) AKTIF LAGI karena call plan wajib per salesman; (d) apakah ini memajukan "mapping customer per sales = fase 2" (17 September); (e) SUDAH diputuskan: diperbaiki di Odoo (lihat bullet keputusan).
- **Pertanyaan ke dev eDot:** lihat daftar di gitbook notes section 8 (webhook pattern, tipe baris hasil webhook, hapus/ganti, zona waktu `plan_date`, definisi week, `salesman.id`, syarat mapping customer-salesman).
- **Next:** user jawab keputusan terbuka -> kirim pertanyaan ke dev -> cek tipe 3 field Odoo live (pola `fields_get` yang sudah ada di `GET /api/odoo/delivery-route`) -> baru desain endpoint. Decision Log dibuat 5 Oktober (v1, baru berisi definisi kode + daftar keputusan terbuka).

---

## 🆕 ADDENDUM 5 Oktober 2026 (b) -- Stok Outlet: endpoint eSuite BARU `POST /v1/webhook/store-stock` (info dev) + endpoint bridge `POST /api/sync/outlet-stock` SUDAH DIBANGUN, Decision Log: project memory `outlet_stock_requirement` + `documents/decision-log/DECISION_LOG_outlet_stock.md`

- **Info dev eDot (5 Oktober, lengkap di `documents/catatan dari wa dev.txt`):** endpoint khusus stok toko, auth sama dgn webhook lain. Payload per item: `customer.external_code` (wajib), `product_variant.external_code` (wajib), `uom_level_code` (kosongkan = satuan dasar), `on_hand` (wajib, >= 0, nilai AKHIR bukan selisih), `expired_date` (opsional `YYYY-MM-DD`; tanggal beda = baris stok terpisah).
- **Aturan endpoint:** maks 50 item/request, request dikirim BERURUTAN; nilai MENIMPA stok sebelumnya (idempotent); produk yang tidak dikirim tidak berubah; kombinasi customer+produk+satuan+expired tidak boleh dobel dalam 1 request; customer WAJIB punya sales branch; warehouse outlet dibuat otomatis oleh eSuite.
- **Dampak ke catatan 29 September:** 3 BLOCKER (target `warehouse.id`, cara buat/link warehouse outlet, POST /warehouse `ODOO-OUTLET-{id}`) GUGUR. Asumsi "endpoint sama dgn `/stock-matrix`" TIDAK BERLAKU -> pakai `/store-stock`. Sumber list produk tetap = produk yang pernah dibeli outlet (sale.order per customer).
- **(BAGIAN "KEPUTUSAN USER" DI BULLET INI TIDAK BERLAKU -- diluruskan 7 Oktober, lihat bullet Baseline/Tahap 2 di bawah)** **Risiko timpa TERKONFIRMASI dev + KEPUTUSAN USER 5 Oktober:** kirim ulang `on_hand: 0` tanpa `expired_date` mereset baris stok tanpa-expired isian sales (baris ber-expired tidak tersentuh, key beda). User: sales sebenarnya TIDAK perlu isi manual (fitur input ada di FE eDot, tidak bisa kita ubah; kita cuma bisa pre-input data) -> TIDAK pakai guard skip; cukup PESAN PERINGATAN di Swagger supaya aware sebelum upsert. Menggantikan "coba jalan dulu" (29 September).
- **SUDAH DIBANGUN 5 Oktober (belum live test):** `POST /api/sync/outlet-stock` (tag Sync). Param: `external_codes` (`ODOO-PARTNER-{id}`, kosong = semua customer), `limit` + `offset` (jalan bertahap, urut id Odoo), `dry_run` (**default TRUE** -- beda dari endpoint sync lain, sengaja supaya Execute default tidak menimpa apa pun), `batch_size` (maks 50), `include_payload`. Alur: customer Odoo -> guard customer eSuite (ada + punya `sales.branchs`) -> produk dari `sale.order` `invoice_status` to invoice/invoiced (sama dgn order history) -> guard produk eSuite (variant valid) -> item `on_hand: 0`, `uom_level_code: ""`, TANPA key `expired_date` -> chunk 50 -> `EsuiteClient.push("store-stock", "upsert", batch)` berurutan, jeda 1 detik, try/except per batch -> `logs/sync_log.csv` (entity `outlet_stock`). Peringatan timpa: docstring route (Swagger), deskripsi `dry_run`, field `warning` di response.
- **File:** BARU `app/services/outlet_stock_sync_service.py`, `app/api/routes/outlet_stock.py`; DIUBAH `app/clients/odoo_client.py` (method baru `get_purchased_product_ids_by_customer()`, additif, sebelum `get_sales_orders`), `app/main.py` (+1 import, +1 `include_router`). Tidak ada perubahan DB/env/dependency/Docker. Test: py_compile + TestClient (Odoo & eSuite di-mock) PASS.
- **Asumsi (belum dikonfirmasi user):** `dry_run` default true; filter "pernah dibeli" = `invoice_status` to invoice/invoiced; key `expired_date` tidak dikirim (bukan `""`).
- **Belum dijawab dev / belum dites:** (1) format response kalau sebagian item gagal (pola lama "200 tapi silent fail"); (2) ada GET stok toko per customer? (utk guard & verifikasi); (3) saat sales isi expired di baris placeholder: update baris atau bikin baris baru (placeholder 0 tertinggal)?; (4) baris `on_hand: 0` tampil di list Product Stock eWork?; (5) rate limit; (6) nasib 15 warehouse outlet lama buatan app (ada duplikat).
- **Folder `app/`:** SUDAH dikembalikan user 5 Oktober (dari repo lokal). Dicek: file terbaru 2 Oktober (`odoo_get.py`, `odoo_client.py`), semua perubahan s.d. addendum 2 Oktober ada, compile bersih. Cuma `app/` (tanpa Dockerfile/requirements/.env).
- **Test plan (7 Oktober):** `documents/TEST_PLAN_outlet_stock.md` -- 8 tahap (baseline -> dry run 1 outlet -> push 1 outlet -> idempotent -> perilaku isian sales & timpa -> guard -> >50 item -> hitung skala -> rollout `limit`+`offset`). BELUM dijalankan.
- **Live test DIMULAI 7 Oktober (baseline saja, belum ada push):** outlet uji `ODOO-PARTNER-39353` "07 AM BAKERS CLUB" (id customer eSuite `6a9a25225d9e829bbdf16d9a`). TEMUAN: `warehouse.address.id` = id CUSTOMER (bukan id alamat) -> warehouse outlet-nya `6aa25653123bf4e148ccdb69`; warehouse kedua bernama sama milik customer lain. 21 warehouse (4 internal + 17 outlet, termasuk "E2E STORE STOCK TEST" buatan dev 5 Oktober). Outlet ini sudah punya stok manual TAKARA Beras 5kg, exp 10/09/2026, 10 Units. Dampak ke addendum wilayah: kekhawatiran address `id: ""` memutus link warehouse outlet kemungkinan tidak berlaku. Detail: `documents/TEST_PLAN_outlet_stock.md` (Catatan hasil) + Decision Log v3.
- **Baseline stock-matrix 7 Oktober:** baris store-stock (test dev di warehouse E2E) memakai skema batch sama dgn app (`EWORK{YYYYMMDD}` / `EWORK` tanpa expired, `created_by` kosong) -> placeholder bridge = `EWORK`, `on_hand` 0. Baris isian sales tanpa expired yang berisiko ter-reset saat rollout: 15 baris `on_hand` > 0 di AREA JAYA (9), LIKA MARGA UD (4), MADE MART (2). Outlet uji 39353: 1 baris TAKARA `EWORK20260910` di warehouse `6aa25653...`, branch terisi. `GET /stock-matrix` mengabaikan `limit` (1090 baris sekaligus). Tahap 0 SELESAI. **Tahap 1 (dry run 39353) LULUS 7 Oktober:** 1 customer, 1 item (`ODOO-PROD-9787`), tanpa skip -- query Odoo baru & kedua guard terbukti jalan live. **Tahap 2 (push 39353) 7 Oktober: call sukses TAPI eSuite balas `summary` upserted 0 / unchanged 1, item `status: "unchanged"`, `on_hand_before` 0 -> `on_hand_after` 0, `store_warehouse_created: false`.** Format response store-stock kini diketahui (`data.summary` + `data.results[]` per item). ⚠️ DUGAAN: `on_hand: 0` utk kombinasi yang belum punya baris TIDAK membuat baris -> list tidak muncul di eWork (tujuan pre-load gagal). MENUNGGU verifikasi user (dump stock-matrix + screenshot eWork). Kalau benar: tanya dev eDot / workaround kirim 1 lalu 0 (belum diputuskan). Kode perlu baca `data.summary` (belum dikerjakan). **Jawaban dev eDot 7 Oktober (dicatat di `documents/catatan dari wa dev.txt`):** "unchanged" karena `on_hand: 0` dan stok awal juga 0; dev minta `on_hand` diisi. KONFLIK dgn desain placeholder 0 (Odoo tidak tahu stok outlet) -> MENUNGGU keputusan user: (A) minta dev supaya 0 tetap membuat baris, (B) workaround kirim 1 lalu 0, (C) kirim angka bukan 0 (tidak disarankan). **KEPUTUSAN USER 7 Oktober: opsi B** (workaround; maksud user: cukup pertama kali, selanjutnya sales update dari UI). **SUDAH DIIMPLEMENTASI 7 Oktober (mock PASS, BELUM live test):** per batch 2 langkah -- kirim `on_hand: 1`, lalu kirim `on_hand_before` dari jawaban eSuite (produk baru jadi 0, isian sales tanpa expired KEMBALI ke nilai semula) -> aman dijalankan ulang, keputusan lama "isian sales boleh tertimpa" tidak berlaku lagi. Langkah 2 retry 3x; call gagal = proses BERHENTI (`aborted`, `restore_failed_items`, `unprocessed_item_count`). Bridge kini baca `data.summary` (`esuite_summary.seed/.restore`). File: `app/services/outlet_stock_sync_service.py`, `app/api/routes/outlet_stock.py` (tidak ada perubahan DB/env/dependency/Docker). **Next:** restart bridge -> ulangi push outlet 39353 (`dry_run=false&include_payload=true`) -> harapan `seed` upserted 1 (0->1), `restore` upserted 1 (1->0) -> cek Garam 25kg tampil stok 0 di eWork. Tahap 3 dst menunggu hasil itu. **SKENARIO DILURUSKAN USER 7 Oktober (acuan):** bridge upsert MENAMBAHKAN item dgn stok 0; sales isi qty & expired MANUAL -> isian sales TIDAK BOLEH ditimpa. Catatan lama "tanpa guard / isian sales boleh tertimpa, cukup peringatan" (5 Oktober) = salah baca, TIDAK BERLAKU. Kode 2 langkah sudah sesuai skenario ini. **LIVE TEST kode 2 langkah 7 Oktober sore (outlet 39353, Garam `ODOO-PROD-9787`): sisi API LULUS** -- `seed` upserted (0 -> 1), `restore` upserted (1 -> 0), `pushed_count` 1, tanpa abort. BELUM dicek: baris tampil stok 0 di eWork (penentu workaround berguna/tidak) + baris di stock-matrix. Catatan proses: penulisan pertama file service ke folder `edot` sempat gagal diam-diam (isi lama) -- setelah menulis file, verifikasi ukuran/checksum di sisi device. **UPDATE DEV eDot 7 Oktober malam (dicatat di `documents/catatan dari wa dev.txt`):** eSuite kini bisa menyimpan `on_hand: 0` utk produk yang belum ada di tabel stok, kontrak API tetap. BELUM dites. KONFLIK dgn keputusan opsi B (kirim 1 lalu kembalikan) -> MENUNGGU konfirmasi user atas usulan pengganti: kirim 0 dulu, lalu kembalikan nilai semula HANYA utk item yang `on_hand_before` > 0. Kode belum diubah. Utk menguji perubahan dev perlu outlet/produk yang belum punya baris (39353 + Garam sudah punya). **KEPUTUSAN USER 7 Oktober malam (2 konfirmasi) + SUDAH DIIMPLEMENTASI (mock PASS, belum live):** (1) kirim `on_hand: 0`, kembalikan nilai semula HANYA utk item `on_hand_before` > 0 -- menggantikan "kirim 1 lalu kembalikan"; (2) baris stok 0 tanpa expired boleh tampil di samping baris ber-expired. Perilaku UI menurut user: ubah stok saja = baris ter-update; ubah/tambah expired = baris baru. Konstanta `PLACEHOLDER_ON_HAND = 0`; field response tidak berubah. **KONDISI TERKINI & NEXT:** restart bridge -> cari outlet tanpa stok lewat dry run `?limit=20` -> dry run + push 1 outlet itu (harapan `esuite_summary.seed.upserted` = jumlah item, `restore` kosong) -> cek tampil stok 0 di eWork -> uji "kembalikan": isi 1 produk dgn stok tanpa expired di eWork, push ulang, stok harus tetap -> baru lanjut Tahap 6-8 test plan. **8 Oktober: push outlet `ODOO-PARTNER-24226` (2B'S MART) LULUS sisi API** -- 6 item `on_hand: 0` semua `upserted` (0 -> 0) dlm 1 request, warehouse outlet dibuat otomatis; capability baru dev terbukti. 9 produk lain outlet ini di luar kategori Saleable -> dilewati (wajar). **eWork DIKONFIRMASI user: item tampil dgn qty 0 -> alur "tambah produk stok 0" terbukti ujung-ke-ujung.** Next: uji "kembalikan" (isi 1 produk stok 5 tanpa expired, push ulang, harus tetap 5) + uji expired (Tahap 2b D & E), lalu beberapa outlet (Tahap 6) dan rollout bertahap.
- **Next:** (a) `dry_run` 1 outlet: `POST /api/sync/outlet-stock?external_codes=ODOO-PARTNER-{id}&include_payload=true`; (b) push 1 outlet (`dry_run=false`), catat `batches[].esuite_response` (format hasil per item belum diketahui), cek di eWork: baris `on_hand 0` tampil? sales isi expired = update baris atau baris baru?; (c) kirim pertanyaan sisa ke dev; (d) rollout bertahap `limit`+`offset`; (e) tambah item Postman.

---

## 🆕 ADDENDUM 5 Oktober 2026 -- Gap analysis mapping wilayah Customer (Odoo regional -> eSuite `administrative_level[]`), detail: project memory `customer_address_administrative_area`

- **(SUDAH TIDAK BERLAKU -- `app/` dikembalikan user 5 Oktober siang, lihat addendum (b))** ~~Folder `app/` TIDAK ADA lagi di `C:\Users\HP\Claude\edot`~~ (hilang setelah 2 Oktober ~06:36; tidak ketemu di folder `Claude` lain). Kode bridge tidak bisa dicek/diubah dari sesi ini sampai lokasi barunya diketahui. PERLU konfirmasi user (dipindah ke mana / terhapus?).
- **Status fitur:** kode ditulis 29 September, lolos unit test mock, BELUM pernah live test/deploy (tidak ada bukti run; `logs/sync_log.csv` terakhir 7 September).
- **Belum terverifikasi live:** (1) akun API Odoo bisa baca `res.village`/`res.subdistrict`/`res.city`; (2) `keyword` eSuite harus huruf besar/persis?; (3) eSuite menerima & menyimpan `administrative_level` di upsert Customer.
- **✅ HASIL LIVE 7 Oktober (siang):** B2 LULUS (limit 50: 13/13 desa ketemu, 35 dari 50 customer belum punya Desa di Odoo; total customer aktif 3.455). Upsert sungguhan ODOO-PARTNER-39353 & 1655 sudah dijalankan user (13:06) -> **eSuite MENYIMPAN `administrative_level`** (GET-verified; `postal_code` level 3 tidak tampil di GET). **Risiko alamat ganda DITUTUP:** upsert MENGGANTI address (tetap 1 per customer, `addresses[].id` di GET selalu ""), dan `warehouse.address.id` = `id` CUSTOMER eSuite (bukan id address) -> link warehouse outlet aman. 2 warehouse "07 AM BAKERS CLUB" = 2 customer berbeda (39353 branch CBU, 1655 branch SFC). Field lain (group, branch, salesmans) utuh. **B3 LULUS:** dry run semua 3.455 customer -> 1.311 ter-resolve, 2.143 belum punya Desa di Odoo, 124 dari 125 desa ketemu (semua Bali cocok), 0 lookup_error. 1 tidak ketemu: `JAKARTA|KOTA ADM JAKARTA PUSAT|MENTENG|MENTENG` (partner 47802) -- dugaan beda nama provinsi (Odoo "Jakarta"/"Yogyakarta" vs eSuite "DKI JAKARTA"/"DI YOGYAKARTA"?), ejaan eSuite BELUM terlihat -> PENTING utk rollout Jakarta/SBU. Temuan: `keyword` eSuite = cocok SEBAGIAN (bukan persis). **Kode diubah 7 Oktober (belum deploy):** `_lookup_admin_area()` mengurutkan `esuite_candidates` dari yang paling mirip. **D1 LULUS (13:33):** upsert sungguhan `limit=20` -> 20 sukses, 0 gagal; 6 ter-resolve (5/5 desa), 14 tanpa Desa. **D2 & D3 LULUS (13:37):** GET 40520/40360/40427 -> wilayah benar (CANGGU, DAUH PURI KANGIN, PECATU), 1 address masing-masing; 35520 (tanpa Desa) sukses dgn `administrative_level: []`. **Catatan:** 35520 (0104 HERO GONDANGDIA, branch SBU/Jakarta) = customer BARU dibuat oleh upsert D1 (`CUST-03088`) -> rollout tanpa filter akan MEMBUAT ratusan customer baru (eSuite ~3.088 vs Odoo 3.455). ~~Sisa sebelum E: 3 keputusan~~ **DIPUTUSKAN user 7 Oktober 13:48:** (1) rollout SEMUA customer + minta catatan saat sync Jakarta (param `only_with_village` TIDAK dibuat); (2) 2 endpoint lain DISAMAKAN; (3) ejaan Jakarta di eSuite = `DKI JAKARTA > JAKARTA PUSAT > MENTENG > MENTENG`.
- **KODE 7 Oktober sore (py_compile + test mock PASS, BELUM deploy/live):**
  - BARU `app/core/admin_area.py` -- `AdminAreaResolver` (resolve_map/_lookup), cache, `normalize_area_name`, `to_administrative_level`. Logic wilayah DIPINDAH dari `customer_sync_service.py` ke sini supaya dipakai 3 service (bukan import silang antar service); 1 cache bersama.
  - **Aturan nama longgar** (hanya kalau 4 nama persis tidak ketemu): kecamatan & desa tetap persis; provinsi dibandingkan tanpa kata DKI/DI/DAERAH/ISTIMEWA/KHUSUS/IBUKOTA/PROVINSI; kota tanpa KOTA/KAB/KABUPATEN/ADM/ADMINISTRASI; harus tepat 1 hasil. Yang cocok lewat aturan ini dilaporkan di key baru `administrative_area.matched_by_relaxed_name`. (Yogyakarta/"DI" belum terbukti live.)
  - `customer_sync_service.py`: `_resolve_admin_area_map()` jadi penerus ke resolver; konstanta & method wilayah lama dihapus dari file ini.
  - `customer_upsert_geo_branch_sales_service.py`: address (kalau `coordinates` diisi) sekarang + `administrative_level`; response + `administrative_area`.
  - `customer_geolocation_service.py` + route: untuk `ODOO-PARTNER-{id}` yang ketemu di Odoo address dikirim LENGKAP (street + wilayah dari Odoo, koordinat dari input), response `address_mode: full`; external_code lain = perilaku lama (`coordinates_only`) + `warning`. Service ini sekarang pakai OdooClient.
  - Tidak ada perubahan DB/env/dependency/Docker/route path.
- **HASIL Tahap F (7 Oktober 15:59, kode sudah deploy):** F1 LULUS (47802 ketemu lewat aturan longgar, DKI JAKARTA/JAKARTA PUSAT/MENTENG/MENTENG, V31710601); F2 LULUS (3.457 customer, 1.314 ter-resolve, 125/125 desa, unresolved kosong); F3 belum ada hasil; F4: payload upsert-geo-branch-sales sudah bawa `administrative_level`.
- **⚠️ EFEK SAMPING F4 (perlu dipulihkan):** perintah F4 dari Claude tidak mengosongkan `branch_external_codes` -> default `ODOO-COMPANY-2` terkirim -> branch customer ODOO-PARTNER-39353 dikirim sebagai Sunshine Food and Co (seharusnya Cahaya Boga Utama). Pemulihan: `POST /api/sync/customers?external_codes=ODOO-PARTNER-39353` lalu GET verifikasi (branch CBU, 9 salesman, wilayah ada). Test plan sudah dikoreksi. **Usulan (BELUM diputuskan, konflik dgn keputusan 28 Agustus):** kosongkan default `branch_external_codes` di route `customer_upsert_geo_branch_sales.py` karena customer sekarang tersebar di 3 branch (CBU/SFC/SBU).
- **✅ 39353 PULIH (GET 16:08):** branch kembali Cahaya Boga Utama, 9 salesman utuh, 1 address, wilayah 4 level ada -> F4 LULUS, efek samping selesai.
- **✅ F3 LULUS (9 Oktober 15:39):** endpoint geolocation 39353 -> `address_mode: full`, GET: 1 address, street/koordinat/wilayah utuh, branch CBU & 9 salesman utuh. **Tahap A-D & F test plan SELESAI** -- ketiga endpoint alamat terbukti tidak menghapus wilayah.
- **Dry run semua 9 Oktober 16:36:** 3.571 customer, 2.667 ter-resolve, 902 tanpa Desa di Odoo (turun dari 2.143), 186/187 desa ketemu, 2 desa Jakarta lewat aturan longgar (Kelapa Gading Barat, Menteng). 1 tidak ketemu: `BALI|KAB KLUNGKUNG|KLUNGKUNG|SEMARAPURA KLOD` (customer 39695, 40561), 0 kandidat -- dugaan eSuite "SEMARAPURA KELOD".
- **Kode 9 Oktober (belum deploy, mock PASS):** `app/core/admin_area.py::_lookup()` -- kalau `keyword` tidak menemukan apa pun, cari sekali lagi pakai kata pertama nama desa (`search_name`) KHUSUS utk mengisi `esuite_candidates` (diagnosa, tidak pernah jadi match).
- **Semarapura (9 Oktober 17:09):** kandidat eSuite terlihat (kode diagnosa sudah deploy): SEMARAPURA KELOD. Master Odoo `res.village` Kec. Klungkung TIDAK konsisten ("Semarapura Kelod Kangin" vs "Semarapura Klod ", keduanya tanpa kode pos). **KEPUTUSAN USER:** ejaan benar "Semarapura Kelod", master Odoo salah; perbaikan lewat **alias di bridge**. **Kode (belum deploy, mock PASS):** `VILLAGE_NAME_ALIASES` di `app/core/admin_area.py` (key = jalur Odoo dinormalisasi, value = nama desa eSuite); desa via alias ikut dilaporkan di `matched_by_relaxed_name`. Uji: dry run `external_codes=ODOO-PARTNER-39695,ODOO-PARTNER-40561` -> lalu sync. **✅ LULUS 17:13 (sudah deploy):** 2 customer ter-resolve via alias, unresolved kosong. Semua desa yang dipakai customer sekarang bisa dipetakan. **✅ TAHAP E ROLLOUT SELESAI (9 Oktober 17:15):** `POST /api/sync/customers` -> 3.581 terkirim, 4 batch success, failed 0; wilayah 2.677 customer terisi, 904 tanpa Desa di Odoo, 188/188 desa, unresolved kosong; 4 desa via aturan longgar/alias (Menteng, Ciracas, Kelapa Gading Barat, Semarapura Kelod). 64 pricelist belum ada di eSuite.
- **Next:** (1) verifikasi acak GET (mis. `ODOO-PARTNER-44892,ODOO-PARTNER-24733,ODOO-PARTNER-47264` + 1 customer Jakarta baru) -> cek wilayah & 1 address; (2) register customer Jakarta baru ke sales (`mass-customer-sales`, setelah akun salesman Jakarta ada); (3) customer tanpa Desa (904) -> isi Desa di Odoo (project address_matcher) lalu sync ulang; (4) 64 pricelist -> `/sync/pricelist` bila perlu. ~~Masih menunggu: keputusan default `branch_external_codes`~~ DIPUTUSKAN 10 Oktober (dikosongkan).
- **Next (lama):** Tahap E rollout (`POST /api/sync/customers`) boleh jalan sekarang (2 customer Semarapura masuk tanpa wilayah) -> deploy kode diagnosa -> dry run `external_codes=ODOO-PARTNER-39695` utk lihat ejaan eSuite -> putuskan perbaikan (ubah nama desa di master Odoo vs alias di bridge) -> sync ulang 2 customer itu -> register customer Jakarta baru ke sales. Masih menunggu jawaban user: default `branch_external_codes` dikosongkan atau tidak. **Catatan sync Jakarta** ada di test plan: ~367 customer baru, belum punya salesman, kebanyakan tanpa Desa, 63 pricelist belum ada di eSuite.
- ~~**Risiko address `"id": ""`:**~~ (DITUTUP, lihat hasil 7 Oktober di atas) Catatan lama: tiap upsert kemungkinan bikin address BARU -> duplikat address + memutus link `warehouse.address.id` warehouse outlet (lihat `outlet_stock_requirement`; bukti: 07 AM BAKERS CLUB 2 warehouse, address.id beda). WAJIB dicek (GET customer ODOO-PARTNER-39353) SEBELUM mass upsert ulang customer.
- ~~Belum ada mode dry-run~~ **SELESAI 5 Oktober (sore):** param `dry_run` (default `false`, behavior lama tidak berubah) di `POST /api/sync/customers` -- semua lookup jalan (Odoo + GET eSuite), TANPA push/CSV/sync_log; response: `dry_run`, `total_would_send`, `administrative_area` (+ `unique_villages`/`resolved_villages` baru), `payload_preview` kalau `include_payload=true`. File: `app/services/customer_sync_service.py`, `app/api/routes/customer.py`. py_compile + test mock PASS, belum live. **Next test:** `POST /api/sync/customers?dry_run=true&external_codes=ODOO-PARTNER-39353&include_payload=true`, lalu `dry_run=true` tanpa filter (122 desa unik) utk daftar `unresolved`. **Test plan lengkap (7 Oktober): `documents/TEST_PLAN_customer_regional_mapping.md`** -- 5 tahap (A persiapan/baseline, B dry run, C upsert 1 customer + cek alamat ganda & warehouse outlet, D batch 20, E rollout). **Hasil 7 Oktober: A1, A3, B1 LULUS** (dry run ODOO-PARTNER-39353: 4 level benar, id sama dgn contoh dev -> akses Odoo ke model wilayah & `keyword` eSuite TERBUKTI jalan). A2 (GET customer 39353 & 1655) belum; B2/B3 berikutnya. Temuan: Odoo punya 2 partner "07 AM BAKERS CLUB" (39353 & 1655) -> 2 warehouse outlet itu kemungkinan 2 customer berbeda, bukan duplikat (hipotesis alamat ganda melemah, tetap dicek di C3). Warehouse eSuite sekarang 21 (+SANDI WIJAYA, +E2E STORE STOCK TEST buatan dev).
- **Cakupan data Odoo:** baru batch 1 = 1.420 dari ~2.935 customer yang punya `village_id` (semua Bali, 122 desa unik, 9 kab/kota; 123 di antaranya inactive -> tidak ikut sync). Sisanya (batch 2, Jakarta/SBU) belum diisi -- dikerjakan di project `odoo/address_matcher`.
- **Risiko beda nama:** belum terukur (butuh dry-run). Diketahui: eSuite 78.558 desa vs Odoo 83.761; 34 vs 38 provinsi; nama bertanda baca (mis. "Kaba-kaba") bisa gagal di `keyword` persis -- belum ada fallback `search_name`.
- **Keputusan masih terbuka:** (a) 2 endpoint lain yang kirim `addresses[]` tanpa `administrative_level` (`mapping/customer-upsert-geo-branch-sales`, `update/customer-geolocation`); (b) Branch `ADMINISTRATIVE_AREA` (tanya dev). Postman collection belum ditambah.

---

## 🆕 ADDENDUM 2 Oktober 2026 -- Endpoint baru `GET /api/odoo/delivery-route` (rute Odoo), Decision Log: project memory `odoo_get_endpoints`

- **Requirement (user):** endpoint GET rute; sumber = field Odoo Studio `x_studio_delivery_route`.
- **Yang dibangun:** `GET /api/odoo/delivery-route` (grup Swagger "odoo - Get", diagnostic-only/read-only, bukan bagian sync). Output: metadata field (`field_label`, `field_type`, `relation`, `master_readable`) + `data[]` {`value`, `name`, `customer_count`} + `customers_with_route` / `customers_without_route`. Param opsional `company_id` (0 = customer tanpa company, aturan sama `GET /odoo/customer`). Hitungan customer = customer_rank > 0 & active.
- **Keputusan desain:** tipe field TIDAK di-hardcode -- dibaca dari Odoo lewat `fields_get` (many2one/many2many -> `value` = id rute + rute tanpa customer ikut muncul; selection -> key/label; char -> teks apa adanya). Kalau akun API tidak bisa baca model master rute, nama diambil dari nilai many2one di customer (`master_readable: false`).
- **ASUMSI (belum dikonfirmasi):** field ada di model Contact (`res.partner`), pola sama `x_studio_sales_team`. Kalau ternyata di model lain (mis. `sale.order`), endpoint balas 404 NOT_FOUND -- ubah constant `DELIVERY_ROUTE_MODEL` di `app/api/routes/odoo_get.py` + domain customer di `get_customer_field_values()`.
- **File:** `app/clients/odoo_client.py` (method baru `get_field_info()`, `get_customer_field_values()`, `get_record_names()` -- additif, sebelum `_name_in_domain`), `app/api/routes/odoo_get.py` (constant `DELIVERY_ROUTE_MODEL`/`DELIVERY_ROUTE_FIELD` + endpoint baru sebelum `/odoo/salesperson`, import `OdooRPCError`). `main.py` tidak diubah. Tidak ada perubahan DB/env/dependency/Docker.
- **Status:** py_compile + TestClient (Odoo di-mock, 4 tipe field + 404/401/422) PASS. **BELUM ditest live.** Postman collection belum ditambah item ini.
- **Next:** (1) panggil `GET /api/odoo/delivery-route` di Swagger -> lihat `field_type` & `relation` asli; (2) putuskan pemakaian rute (belum ada keputusan): tampilkan di `GET /odoo/customer`, filter customer per rute, atau sumber `POST /call-plan` eSuite (di Postman vendor baru ada POST, payload butuh salesman.id + customer.id + branch.id + plan_date).

---

## 🚨 ADDENDUM 29 September 2026 (URGENT) -- Requirement baru: stok item di OUTLET, detail: project memory `outlet_stock_requirement`

> **Update 5 Oktober 2026:** bagian BLOCKER & asumsi endpoint `/stock-matrix` di addendum ini SUDAH TIDAK BERLAKU -- digantikan endpoint `POST /v1/webhook/store-stock` (lihat ADDENDUM 5 Oktober 2026 (b) di atas). Requirement, sumber list produk, dan temuan data live tetap berlaku.

- **Kondisi sekarang:** di app eDot, stok item di outlet diinput MANUAL oleh sales (item, stok, expired).
- **Kebutuhan management:** list produk di outlet sudah muncul otomatis; sales tinggal update stok & expired.
- **Tugas bridge:** upsert produk ke "warehouse outlet" eSuite dari data Odoo -- minimal list produk muncul walau stok & expired kosong.
- **Belum diketahui:** (1) sumber list produk per outlet di Odoo (histori order per customer / pricelist customer / semua produk saleable); (2) entity/endpoint eSuite utk "warehouse outlet" (sama dgn `/warehouse`+`/stock-matrix` atau fitur terpisah) -- tanya dev; (3) upsert ulang tidak boleh menimpa stok/expired yang sudah diinput sales.
- **Jawaban user (29 September):** (1) sumber list produk = produk yang PERNAH DIBELI outlet (riwayat sale.order per customer); (2) asumsi endpoint SAMA dgn `/stock-matrix`, bedanya target warehouse per outlet; (3) risiko menimpa isian sales: "coba jalan dulu".
- **Temuan (belum diverifikasi):** row insiden 27 Agustus `warehouse {code: "", name: "NIRMALA KEDONGANAN"}` kemungkinan warehouse OUTLET auto-dibuat eSuite per customer -> `code` kosong, tidak bisa ditarget via `warehouse.code`. stock-matrix set-to-target -> push qty 0 ulang menimpa isian sales (usulan guard: skip produk yang sudah ada row-nya di warehouse outlet).
- **Temuan data live (29 September):** warehouse OUTLET ada di eSuite (15 dari 19 warehouse; 4 sisanya internal ODOO-WH-1/3/5/6), dibuat otomatis saat sales input stok dari app: name = nama customer, `external_code` KOSONG, `customer` kosong, `address.id` terisi, ada duplikat (07 AM BAKERS CLUB x2). Outlet yang belum pernah diinput sales BELUM punya warehouse. Row qty 0 valid. **Expired disimpan di `batch.code` = "EWORK{YYYYMMDD}"** ("EWORK" = tanpa expired) -> anomali "EWORK tanggal maju 1 tahun" (27 Agustus) kemungkinan besar = tanggal expired, bukan bug. Batch = bagian composite key.
- **WA eDot 29 September (14:50-15:00, dicatat di `documents/catatan dari wa dev.txt`):** eDot: product stock = monitoring stok toko, BELUM ada limitasi produk by histori pembelian; sempat salah tangkap (dikira sales tidak input stok). Teknis diteruskan ke Giovankov, belum dijawab. Pre-load list != limitasi (limitasi = fitur app, tidak ada).
- **Status (per 29 September -- BLOCKER di baris ini GUGUR per 5 Oktober, lihat addendum (b)):** belum ada kode. BLOCKER ke dev eSuite: (1) stock-matrix bisa target `warehouse.id`? (2) cara app link/buat warehouse outlet -- kalau bridge buat via POST /warehouse (external_code `ODOO-OUTLET-{partner_id}`), app pakai itu atau bikin baru? (3) placeholder qty 0 batch "EWORK" tampil di app? Verifikasi kita: `warehouse.address.id` vs `addresses[].id` customer eSuite.

---

## 🆕 ADDENDUM 29 September 2026 -- Mapping wilayah administratif Customer (Odoo modul regional -> eSuite `administrative_level[]`), Decision Log: project memory `customer_address_administrative_area` + `documents/decision-log/DECISION_LOG_customer_address_administrative_area.md`

- **Keputusan (dikonfirmasi user):** decision 24 Agustus ("`administrative_level` SENGAJA TIDAK dikirim, Odoo tidak punya 4 level") **DIGANTI** -- Odoo sudah adopsi modul regional `ms_l10n_id_localization` (4 level). `addresses[]` Customer akan diisi `administrative_level[]`.
- **Padanan level:** `res.country.state` -> province (0), `res.city` -> city (1), `res.subdistrict` (Kecamatan) -> district (2), `res.village` (Desa/Kelurahan) -> sub_district (3).
- **Temuan data:** master CSV regional ada di `documents/master data modul regional/` (38 provinsi, 514 kota, 7.277 kecamatan, 83.761 desa); ID Odoo cuma nomor urut modul (bukan kode resmi) -> matching ke eSuite HARUS by nama berjenjang (normalisasi uppercase + buang tanda baca, mis. "Kab. Badung" = "KAB BADUNG"). Kode pos Odoo != eSuite (Kerobokan 80361 vs 80363) -> bukan kunci. Sample `documents/sample import ke odoo/2026_0928 Update Address.xlsx`: 1.420 partner, semua Bali, 4 level terisi. CSV master pakai id tanpa prefix modul -> JANGAN di-import ulang manual (jadi duplikat `__import__.*`).
- **eSuite:** `GET /administrative-areas` tanpa param cuma balikin level 0 (34 provinsi -- Odoo 38, pemekaran Papua belum ada di eSuite). Param query utk ambil level 1-3 BELUM diketahui (screenshot dev belum ada).
- ~~Usulan desain: endpoint build mapping -> file JSON di repo~~ **DITOLAK/diganti** keputusan user di bawah.
- **Keputusan desain (dikonfirmasi user 29 September):** (a) **lookup LIVE + cache** -- saat `/sync/customers`, tiap desa UNIK dicari ke eSuite `GET /administrative-areas?level=3&keyword=<DESA>` (paging limit 100, maks 20 page), dipilih yang `area[]` cocok 4 level dgn Odoo (nama dinormalisasi); hasil MATCH di-cache di memori proses (`_ADMIN_AREA_CACHE`, hilang saat restart), not_found/ambiguous dicoba ulang tiap sync. Tanpa file/tabel baru. (b) **desa tak ketemu/ambigu -> customer TETAP di-upsert tanpa `administrative_level`** + dilaporkan di response `administrative_area.unresolved`.
- **Status kode: SUDAH DIIMPLEMENTASI (29 September), belum deploy/live test.** File: `app/clients/odoo_client.py` (field `village_id` di `get_customers()`, method baru `get_village_hierarchy()`), `app/clients/esuite_client.py` (method baru `pull_with_params()`), `app/services/customer_sync_service.py` (cache + `_resolve_admin_area_map()`, `_lookup_admin_area()`, `_to_administrative_level()`, `_normalize_area_name()`; `_to_esuite_address()` sisip `administrative_level` kalau ke-resolve; response `/sync/customers` tambah key `administrative_area` {resolved_customers, customers_without_village_in_odoo, unresolved[]}). py_compile + unit test mock PASS. Tidak ada perubahan DB/env/dependency/Docker/API route.
- **Test berikutnya:** `/sync/customers?external_codes=ODOO-PARTNER-39353&include_payload=true` (07 AM BAKERS CLUB, Kerobokan) -> cek `administrative_level` di payload & GET eSuite; lalu limit 50 -> cek `administrative_area.unresolved` (beda ejaan Odoo vs eSuite, mis. nama Kota/provinsi DIY/DKI).
- **Issue terbuka:** `customer_upsert_geo_branch_sales_service` & `customer_geolocation_service` kirim `addresses[]` TANPA `administrative_level` -- kalau eSuite replace address, wilayah hasil sync bisa hilang saat endpoint itu dipakai. Belum diubah (minimal change), perlu keputusan.
- **Struktur model regional TERKONFIRMASI (debug tooltip, 29 September):** `res.city` {`name`, `state_id` -> res.country.state}, `res.subdistrict` {`name`, `city_id` -> res.city}, `res.village` {`name`, `subdistrict_id` -> res.subdistrict}.
- **Field res.partner TERKONFIRMASI (dialog Export debug, 29 September):** `state_id` (Provinsi), `city_id` (-> res.city), `subdistrict_id` (-> res.subdistrict), `village_id` (-> res.village). Field char `city` bawaan (mis. "Badung") teks bebas, TIDAK dipakai.
- **Param `GET /administrative-areas` (screenshot dev, 29 September):** `level` 0-3 (default 0), `country` (default ID), `keyword` (nama persis), `search_name` (nama sebagian), `code` (kode persis), `page`/`limit` (default 1/10). Tidak ada filter parent -> cari desa pakai `level=3&keyword=<desa>`, pilih hasil yang `area[]`-nya cocok provinsi/kota/kecamatan Odoo.
- **Blocker/next:** ~~(1) nama field teknis res.partner~~ SELESAI; ~~(2) param query~~ SELESAI; ~~(3) behavior customer tanpa mapping~~ DIPUTUSKAN (kirim + laporkan); (4) `branch_sync_service.ADMINISTRATIVE_AREA` masih format lama deprecated -- sekalian atau terpisah (belum dijawab).

---

## 🆕 ADDENDUM 24 September 2026 -- Scope company 3 -> 4 (Jakarta/SBU), Decision Log: project memory `company_scope`

- **Keputusan (dikonfirmasi user):** `IN_SCOPE_COMPANY_NAMES` jadi 4 company, tambah **Sunshine Boga Utama (SBU, Jakarta)** -- reason: supaya eDot bisa dipakai di Jakarta. Menggantikan keputusan 18 Agustus (3 company).
- **Identitas company:** CBU (Bali, ada sales), SFC (ada sales), SAP = "agro" (branch produksi, TANPA sales, produknya dipasarkan ke Bali & Jakarta), SBU = "branch office luar kota" (Jakarta, customer & sales Jakarta).
- **Business rule:** produk terlihat lintas branch; customer & sales dipisah per branch. Pemisahan mapping sales sudah di-cover filter per-customer `POST /api/mapping/mass-customer-sales` (branch customer == branch salesman), tidak butuh kode baru.
- **Akses Odoo:** akun API sebelumnya cuma lihat 3/4 company; user bilang sekarang sudah bisa akses SBU (belum diverifikasi via data).
- **Status kode (UPDATE 24 September, lanjutan):** `app/core/scope.py` SUDAH diubah -- "Sunshine Boga Utama" ditambah (4 nama), belum deploy. Hasil live GET /api/odoo/branch: 5 company -- id1 CBU (1219 cust), id2 SFC (1777), id3 SAP (0 cust), id4 SBU "Sunshine Boga Utama, PT" (496 cust, 1 WH, 76 pricelist), id5 "Sunshine Group Indonesia, PT" (kosong, out of scope); tanpa company: 49 customer & 23 pricelist (OPEN, belum diputuskan). Next: `/sync/branch?external_codes=ODOO-COMPANY-4`. ~~BELUM diubah (user minta catat dulu)~~ -- Tidak ada endpoint GET company/branch Odoo di bridge -- semua baca res.company lewat filter scope, jadi SBU tidak kelihatan dari bridge sebelum scope.py diubah.
- **Next:** (1) cek nama persis res.company SBU (JSON-RPC), (2) ubah scope.py, (3) `/sync/branch` & `/sync/warehouse` pakai `external_codes` SBU, (4) produk -> pricelist -> customer 1-10, (5) dev buat salesman Jakarta di branch SBU operasional, (6) mass-customer-sales dry_run -> limit -> full, (7) stock-matrix.
- **Gap terbuka:** lihat project memory `company_scope` (stock lintas branch, pricelist per company, customer ber-company SAP, SALESMAN_EXTERNAL_CODE order-history).
- **Update (24 September, lanjutan):** endpoint BARU `GET /api/odoo/branch` (res.company tanpa filter scope + `in_scope` + jumlah customer/warehouse/pricelist per company + `without_company`) & param `company_id` di `GET /api/odoo/customer` (0 = tanpa company). File: `app/clients/odoo_client.py` (method `get_all_companies()`, `count_records()`, param `company_id` di `get_contacts()`), `app/api/routes/odoo_get.py`. py_compile + TestClient mock PASS, belum live. Pricelist PER COMPANY dikonfirmasi user. Aturan stok (sementara, menunggu konfirmasi): stok = stok fisik WH branch sales; produk tanpa stok di WH Jakarta tampil 0 di sales Jakarta.
- **Order history import (24 September): TIDAK DIPAKAI.** Tujuan awal import order pre-existing (hardcode `SALESMAN_EXTERNAL_CODE="SALES-TESTING-001"`) basi -- kebutuhan sales = history per outlet, eDot cuma sediakan per sales. Endpoint `POST /api/sync/order-history` dipertahankan, docstring route (`app/api/routes/order_history.py`) diberi blok info status. Bukan bagian onboarding Jakarta.

---

## ⚠️ ADDENDUM 18 Agustus 2026 -- file ini (v8) BERHENTI di-update per-sesi sejak 14 Agustus. Progress lanjutan ada di Cowork project memory, BUKAN di sini.

Sejak sesi 14 Agustus (poin 26, baris terakhir file ini), kerja lanjutan dipindah ke sesi Cowork (Claude, cloud) yang punya sistem project-memory sendiri (topic file per area + `MEMORY.md` index) -- bukan lagi 1 file besar seperti ini. File ini (dan `CONFIG_NOTES.md`) TETAP disimpan sebagai arsip riwayat 5-14 Agustus (masih valid utk histori Product/Customer/Variant), TAPI **untuk status TERKINI, jangan percaya tabel/klaim di bawah ini mentah-mentah** -- banyak yang sudah obsolete. Ringkasan progress 14-18 Agustus yang PERLU diketahui sebelum lanjut kerja (detail lengkap ada di project memory Cowork, bukan diulang penuh di sini):

- **Customer Group (`/customergroup`):** SUDAH DIBANGUN & di-push (14 Agustus, BUKAN "Belum" seperti tabel poin 6 di bawah) -- 4 grup hardcoded (FS/MT/GT/HORECA), CONFIRMED jalan. TAPI status **PAUSED**: ditemukan record duplikat lama ("Modern Trade (MT)"/"General Trade (GT)", tanpa external_code) di eSuite sebelum push kita, dan ada potensi konflik konsep "Customer Group" (affiliasi customer, mis. "Pepito+cabang") vs "Customer Category" (FS/MT/GT/HORECA) -- BELUM final, nunggu keputusan user.
- **Pricelist (`/pricelists`):** tabel poin 6 di bawah bilang "Belum, blocker RPC Odoo masih ada" -- **INI SUDAH OBSOLETE, TIDAK BENAR LAGI.** GET-inspeksi (`get_pricelists()`, `get_pricelist_items()`) sudah dibangun & LIVE-VALIDATED 17 Agustus (tidak ada blocker RPC). Business model dikonfirmasi user via screenshot Odoo (1 produk bisa punya harga BEDA di 100+ pricelist granular per-toko/customer, base_price BUKAN harga jual final). Push service (`PricelistSyncService`) MASIH BELUM dibangun -- 2 pertanyaan scope masih terbuka (semua ~100+ pricelist vs subset; company "Sunshine Agri Pratama" & tanpa company ikut atau skip).
- **Stock Matrix (`/stock-matrix`):** tabel poin 6 di bawah SAMA SEKALI TIDAK PUNYA baris untuk entity ini. Sudah dibangun penuh sejak 15-18 Agustus: `stock_sync_service.py` + `POST /sync/stock-matrix`, dengan beberapa bug fix penting (double-count lintas company, eSuite butuh int64 jadi quantity di-floor, filter location diperbaiki dari cuma `usage="internal"` jadi tambah `complete_name ilike "/Stock/"` karena warehouse ternyata punya location staging Output/Pre-Production/Post-Production yang ikut kehitung). **Temuan PALING PENTING 18 Agustus:** push ke `/stock-matrix` API sudah BENAR & GET-verified, tapi field `stock`/`stocks` di `product-variant` (yang kemungkinan dibaca UI eSuite) TETAP 0/kosong -- diduga gap recompute di sisi eSuite, SUDAH ditanyakan ke vendor, jawaban masih ditunggu. Ini BLOCKER UTAMA supaya stok kelihatan di dashboard sales.
- **Security audit (16 Agustus):** full review injection/DoS/auth atas semua endpoint dilakukan -- 2 bug kecil di endpoint diagnostic baru sudah difix, 7 temuan lain (paling penting: rate limiting `slowapi` sudah disetup tapi TIDAK PERNAH diaktifkan di `main.py`; `GET /debug/pull/{entity_path}` proxy tanpa whitelist) masih PENDING keputusan user.
- **Endpoint diagnostic baru (16-18 Agustus):** grup Swagger "odoo - Get" ditambahkan (`/odoo/product`, `/odoo/pricelist`, `/odoo/stock-quant-raw`, `/odoo/stock-location`, dll) -- baca data Odoo mentah tanpa lewat proses sync, buat investigasi cepat.

**Kalau lanjut kerja dari sini:** cek dulu ke Cowork/project memory (topic file `stock_sync_progress`, `pricelist_progress`, `sales_entities_gap`, `security_audit`) untuk kondisi PALING BARU sebelum ambil keputusan berdasarkan isi v8 di bawah ini.

---

## 1. Scope App (FIXED)

Bridge murni: **Odoo 19 (SSOT) → eSuite/eDOT**, satu arah (push-only), tanpa pengecualian. Auth: API key statis. Tidak pakai JWT, slowapi, CORS.

## 2. Trigger Sync (FIXED, direvisi 13 Agustus 2026)

Manual, 1 endpoint per entity. `payload_sent` di response sekarang **opt-in** lewat param `include_payload` (default `False`) di `/sync/product` dan `/sync/customers` -- **BUKAN lagi "selalu include" seperti keputusan awal**. Alasan revisi: Swagger jadi lambat waktu payload penuh selalu ikut di-render untuk batch besar. `external_codes` tetap SELALU tampil di tiap batch/variant_sync result (cukup buat tracking sukses/gagal tanpa payload penuh) -- cuma payload lengkapnya yang jadi opsional. Lihat poin 20 untuk detail implementasi.

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
| Product (`/product`) | `product.product` | ✅✅ Filter tervalidasi (1247 produk, 5 Agustus). `cost` sekarang `0` fixed (final, 13 Agustus) -- root cause "cost nyangkut" ternyata `uom_levels.id` salah + delay async queue, BUKAN bug eSuite. `uom_levels.id` sudah fix (12 Agustus, Level "Low"). Next: re-push massal buat konsistenkan produk lama, lihat poin 12.2/21. |
| Customer | `res.partner`, filter `customer_rank > 0` + `active=True` | 🟡 `entity_type` fix + batching (default 1000/batch) sudah diterapkan (11 Agustus 2026). Full push 3038 record sukses (delay awal cuma soal async processing eSuite, sudah beres). Payload MASIH MINIM -- field `price_list.id`/`sales.branchs[]`/`sales.salesmans[]` belum pernah dikirim (gap, lihat ADDENDUM 18 Agustus di atas & Cowork project memory `sales_entities_gap`). |
| Stock Matrix (`/stock-matrix`) | `stock.quant` per warehouse (BUKAN `product.product.free_qty`) | 🟡 DIBANGUN 15-18 Agustus (di Cowork, TIDAK ada di v8 ini). Push jalan & GET-verified, tapi eSuite `product-variant.stock` tidak ikut ter-update (blocker utama, PENDING vendor). Detail: Cowork project memory `stock_sync_progress`. |
| Pricelist (`/pricelists`) | `product.pricelist` / `product.pricelist.item` | 🟡 **OBSOLETE per 17 Agustus** ("blocker RPC" sudah tidak benar). GET-inspeksi LIVE-VALIDATED, business model dikonfirmasi user, push service belum dibangun. Detail: Cowork project memory `pricelist_progress`. |
| Customer Group (`/customergroup`) | HARDCODED (FS/MT/GT/HORECA, bukan dari Odoo) | 🟡 **DIBANGUN & di-push 14 Agustus** (BUKAN "Belum"). PAUSED -- duplikat record lama + konflik konsep Group vs Category, nunggu keputusan user. Detail: Cowork project memory `sales_entities_gap`. |
| Salesman / Salesman Division | `res.users` (asumsi, belum confirmed) | GET-inspeksi read-only sudah ada (17 Agustus), push belum dibangun. |

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
- **✅ Tahap 5 -- falsy-skip TERKONFIRMASI.** User test manual: `POST /product` langsung dengan `"cost": 1` -> UI eSuite berubah jadi `Rp 1`. Terbukti backend eSuite treat value `0` sebagai falsy/"tidak ada value" (skip update), bug di sisi eSuite bukan bridge kita.
- **✅ Tahap 6 (DITERAPKAN ke kode sesi ini) -- keputusan: `cost` dikirim sebagai `1` (Rp 1) fixed.** Sambil nunggu jawaban resmi IT eSuite, user putuskan pakai `1` sebagai sentinel value (bukan cost asli, tetap sesuai instruksi boss) supaya bukan falsy dan benar-benar ke-apply -- daripada nominal cost asli lama yang nyangkut. **Trade-off disadari:** UI nampilin "Rp 1", bukan "Rp 0". **Kalau IT eSuite kasih cara resmi clear ke 0 beneran nanti, ganti `1` -> cara yang benar & re-push ulang semua produk.**
- `standard_price` tetap diambil dari query Odoo (`odoo_client.py::get_products()`), cuma tidak pernah dipetakan ke payload.

## 7d. Info Tambahan dari Vendor (6 Agustus 2026, KEDUANYA BELUM DIVALIDASI/DIKONFIRMASI)

**1. Hard delete tidak didukung, cuma "inactive":** vendor bilang data produk tidak bisa di-hard-delete, cuma bisa di-nonaktifkan (kemungkinan lewat field `status` yang sudah ada di payload). **User masih memvalidasi** -- belum ada keputusan atau perubahan kode. Relevan nanti kalau mulai handle produk yang di-Odoo di-archive/nonaktifkan (belum ada logic ini sekarang, scope masih push-only tanpa NOO flow). Detail di `CONFIG_NOTES.md`.

**2. `uom_levels` butuh field `id` tambahan:** vendor kasih contoh payload terbaru, tiap item `uom_levels` sekarang punya `"id": "01KZ5895R0T1JTR4QTVFGE3GHF"` (format mirip ULID) -- kode kita sekarang cuma kirim `{uom, qty, convertion}` tanpa `id`. Belum jelas asal `id` ini (generated eSuite? wajib atau optional?) dan efeknya kalau tidak kita kirim (reject, atau `status 200 success` tapi ada anomali data diam-diam -- dugaan user, belum terbukti). **Pola ini mirip dengan kasus `cost`** (upsert "sukses" tapi ternyata ada yang tidak ter-apply dengan benar) -- jadi worth dicurigai serius, bukan diabaikan. **JANGAN ubah kode sebelum dikonfirmasi** cara dapetin `id` yang benar (cek `GET /product` buat produk yang sudah di-push, atau tanya vendor langsung). Detail di `CONFIG_NOTES.md`.

## 8. Bug yang Sudah Diperbaiki

- `product.category` di Odoo 19 tidak punya field `active` -- domain filter dihapus dari `get_product_categories()`.
- Docstring `branch.py` salah nyebut sumber Branch (`stock.warehouse`) -- **difix sesi ini**, tidak ada perubahan behavior, murni teks.

Detail field-level ada di `CONFIG_NOTES.md` bagian "Field Odoo yang Ternyata Beda dari Asumsi Umum".

## 9. Entity Product -- Status Saat Ini

**Filter free_qty tervalidasi (1247 produk).** Payload sudah berubah 4x sejak validasi itu: (1) tambah `purchase_uom`+`uom_levels`, (2) hapus `cost`, (3) `cost` sempat 0 fixed (ternyata di-skip eSuite, gagal), (4) `cost` sekarang **`1` fixed** (workaround, sudah diterapkan ke kode). **Belum ada end-to-end test lewat bridge untuk bentuk payload final ini** -- yang sudah dites cuma manual via Swagger (bukan lewat bridge). Prioritas TODO #1. Juga belum ada re-push massal ke produk-produk yang cost-nya masih nyangkut dari payload versi lama.

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

0. **[✅ SELESAI & DITUTUP 13 Agustus 2026 -- root cause BUKAN bug eSuite]** Dugaan lama di baris ini ("falsy-skip bug di endpoint eSuite") **DITARIK**. Root cause sebenarnya: (a) `uom_levels.id` sempat salah (id UOM master, bukan id Product UOM Level) -- field ini MANDATORY, kalau salah SELURUH record gagal diproses dengan benar termasuk field lain di record yang sama (termasuk `cost`), dan (b) delay yang kelihatan seperti "cost tidak berubah" sebagian karena antrian job async eSuite numpuk pas bulk insert (lihat poin 0b, pola serupa juga kejadian di Customer). Setelah `uom_levels.id` difix (12 Agustus), `cost` sekarang dikirim eksplisit `0` (bukan sentinel `1` lagi) -- lihat `product_sync_service.py::_to_esuite_payload()`. **Tidak perlu lapor ke vendor lagi soal ini** (poin 1/1b di bawah closed, dibiarkan sebagai riwayat).
0e. **[BARU, BELUM DILAPORKAN]** Produk BARU (`ODOO-PROD-18374-test`) gagal tersimpan TOTAL (tidak ada di `GET /product` sama sekali, walau response 200) -- bug terpisah dari poin 0, belum ada dugaan penyebab.
0f. **[🚨 PRIORITAS BISNIS, BUKAN CUMA TEKNIS]** 1138/1250 produk (91%) di eSuite masih tampilkan `cost` asli (belum ke-mask) -- kontradiksi instruksi awal "cost tidak boleh disclose". Perlu di-flag ke tim/atasan soal timeline go-live, independen dari kapan bug teknis `cost` API selesai.
0b. **[✅ SELESAI 11 Agustus 2026]** Bulk upsert Customer (3038 record, batch_size=500) -- UI dashboard sempat cuma nunjukin 2002 pas awal dicek. **Dikonfirmasi vendor: eSuite proses upsert secara asynchronous** (response 200 = diterima ke antrian, bukan langsung tersimpan; worker proses belakangan). Bukan bug -- cuma delay pemrosesan. Semua 3038 sudah masuk sekarang. **Insight buat ke depan:** response 200 dari eSuite endpoint manapun tidak bisa langsung dianggap final buat volume besar -- kasih jeda / retry pull kalau perlu verifikasi cepat.
0c. **[✅ FIX DITERAPKAN 11 Agustus 2026]** Root cause gagal upsert Customer (beda dari 0b -- ini soal payload, bukan volume): field `entity_type: "customer"` wajib, sebelumnya tidak dikirim. Dikonfirmasi resmi lewat revisi payload vendor. Sudah ditambahkan ke `customer_sync_service.py`.
0d. **[✅ DITERAPKAN 11 Agustus 2026]** Push Customer sekarang selalu per-batch (default 1000/batch, bisa di-override lewat query param `batch_size`) -- root cause 502 di atas ~2000 record dalam 1 request dikonfirmasi user. Gagal di 1 batch tidak menggagalkan batch lain.
1. **[✅ CLOSED 13 Agustus 2026, lihat poin 0]** ~~Lapor ke vendor soal `cost` API~~ -- tidak jadi perlu, root cause sudah ketemu sendiri (bukan bug eSuite).
1b. **[✅ CLOSED]** ~~Tanya IT eSuite cara clear ke 0~~ -- tidak relevan lagi, `cost: 0` sekarang terbukti aman dikirim setelah `uom_levels` benar.
2. **[NEXT STEP AKTIF]** Re-push semua produk yang sempat ke-upsert dengan payload lama (`cost: 1` sentinel / `uom_levels` salah) supaya konsisten dengan `cost: 0` final. Kebetulan pas dengan rencana vendor kosongkan sandbox (lihat poin 21) -- begitu sandbox bersih, push ulang full batch jadi 1 langkah sekalian testing bersih + reconcile cost.
2c. **[MENUNGGU USER]** Tunggu hasil validasi user soal "produk tidak bisa hard-delete, cuma inactive" -- belum ada aksi kode sampai dikonfirmasi. Lihat poin 7d.
3. Flag ke tim data produk soal `base_price: 1` sebelum go-live (non-coding, lihat `CONFIG_NOTES.md`).
4. **Customer** -- source model (`res.partner`), `entity_type` fix, & batching sudah selesai (lihat 0b/0c/0d). Belum ada full end-to-end reconciliation test (pull balik semua & diff external_code) -- opsional, cuma kalau ada indikasi masalah lagi.
5. **Blocker Stock Matrix vs `/product-variant`** -- no-variant sudah final, cara teknis nyambungin Stock Matrix masih belum jelas. Belum sekarang.
6. Update `CONFIG_NOTES.md` tiap ada aturan bisnis baru -- terpisah dari session transfer note.

## 13. Daftar Pertanyaan Sync dengan Tim IT eSuite

(Belum berubah -- lihat isi lengkap di v6/v7 kalau perlu.) Field opsional Branch, cara efisien dapetin kode wilayah administratif, beda `base_price`/`store_price` di Pricelist, NOO flow wajib/opsional, roadmap webhook vs polling, rate limit, retry safety, migrasi sandbox->production, field `parent` di Product Category/Brand.
~~**Falsy-skip bug `cost`**~~ -- **[✅ SUDAH TIDAK RELEVAN, 13 Agustus 2026]** dugaan bug ini ditarik, root cause asli `uom_levels.id` salah + delay async queue (lihat poin 12.0). Tidak perlu ditanyakan ke vendor.

**Baru juga (terkait poin 2b di TODO):** apakah `uom_levels[].id` wajib dikirim di `POST /product` (termasuk `event=init` pertama kali)? Kalau kita tidak kirim, apakah eSuite reject, auto-generate, atau bikin duplikat entry tiap upsert ulang?

## 14. Referensi Dokumen & Kode Eksternal

- Postman collection + environment DEV: prioritas utama.
- PDF eSuite Synchronization v2.0.0: prioritas kedua.
- Excel Master Data Go Live: referensi field saja.
- Kode `searchProduct`/`product_services.py` dari project bridge Odoo↔Cekat AI milik user -- filter `free_qty` dari referensi itu **tidak lagi diikuti** di bridge eSuite ini sejak 5 Agustus 2026.
- **BARU (12 Agustus 2026):** `https://edot.gitbook.io/knowledge-base-edot` -- Knowledge Base eDOT resmi (dashboard/UI level, bahasa Indonesia). **Bisa diakses langsung oleh AI** (support markdown per-halaman lewat suffix `.md`, dan endpoint tanya-jawab `?ask=<pertanyaan>` di halaman manapun). **Beda scope dari PDF Sync Document**: gitbook ini dokumentasi UI/dashboard eSuite (definisi tabel, cara pakai fitur), PDF Sync Document tetap acuan utama untuk struktur payload webhook API. Dipakai sesi ini buat riset relasi antar entitas (lihat poin 15).

## 15. Housekeeping & Riset Paralel (12 Agustus 2026, sesi akun Pro kantor -- migrasi dari akun free pribadi)

- **File duplikat dihapus:** `eSuite-Webhook.postman_collection.json` (titik) dihapus -- identik byte-for-byte (`diff` = 0 baris beda) dengan `eSuite-Webhook_postman_collection.json` (underscore) yang tetap dipertahankan karena itu yang direferensikan di `CONFIG_NOTES.md`.
- **Nama project (sementara):** user menamai app bridge ini **`eDot_cbu_fastapi`** (CBU = Cahaya Boga Utama, nama kantor). Belum ada perubahan kode/folder/docker terkait penamaan ini -- baru penamaan referensi.
- **Riset paralel (BUKAN blocking terhadap TODO utama):** sambil menunggu jawaban vendor soal bug `cost` (lihat poin 12), user mempelajari relasi data eSuite secara umum (Product ↔ UOM ↔ UOM Level ↔ Category ↔ Brand ↔ Group ↔ Variant ↔ Warehouse ↔ Location ↔ Stock Matrix) lewat gitbook KB. Hasil riset dituangkan ke file baru **`edot_dashboard_entity_relations.mmd`** (mermaid ERD, sejajar `edot_entities_erd.mmd` yang sudah ada -- dua file ini beda scope, lihat catatan di dalam file masing-masing).
- **Temuan baru dari gitbook (belum ada di CONFIG_NOTES sebelumnya):** Product Group berelasi M:N ke Product (manual assign, field "Associated Product"); Product Brand punya hierarchy sendiri (Parent) tapi **tidak direferensikan dari payload Product** (konsisten dengan temuan lama 5 Agustus); UoM Category mengelompokkan UoM dengan field Ratio untuk konversi. Detail lengkap di `edot_dashboard_entity_relations.mmd` dan `CONFIG_NOTES.md` bagian baru.
- **Belum dikonfirmasi dari dokumentasi manapun:** FK eksplisit antara Location dan Warehouse (dugaan: Location = storage bin di dalam Warehouse), dan field `location` di payload `/stock-matrix` (masih dugaan dari contoh Postman).

## 16. Fix `uom_levels[].id` DITERAPKAN + Riset `product-variant` (12 Agustus 2026, lanjutan)

- **✅ Kode `product_sync_service.py` DIUBAH:** `uom_levels[].id` sekarang pakai constant `PRODUCT_UOM_LEVEL["id"]` (Level "Low", `01KZ5895R0T1JTR4QTVFGE3GHF`) untuk semua produk, bukan lagi `base_uom["id"]`. **Keputusan dikonfirmasi user:** reuse "Low" sementara karena CBU cuma pakai 2 UOM fisik (units & kg), tidak ada kebutuhan tier packaging asli. Lolos `python3 -m py_compile`. **BELUM di-re-test end-to-end lewat bridge** -- ini PRIORITAS TODO berikutnya (di atas poin 12 lama), lihat poin 17.
- **Verifikasi data mendukung fix ini:** analisis `sample/hasil get product 10000.txt` (1250 record nyata) menunjukkan 1245/1250 produk `uom_levels`-nya kosong dengan kode lama -- bukti kuat bug lama nyata di skala penuh, bukan cuma di 1 test case.
- **`cost` makin terisolasi sebagai bug spesifik field ini** (cross-check `base_price` yang terbukti diterapkan bervariasi & benar untuk mayoritas produk) -- **status tetap MENUNGGU JAWABAN VENDOR**, tidak ada perubahan kode terkait `cost` sesi ini.
- **Riset `product-variant` / blocker Stock Matrix (BELUM diimplementasi):** payload `POST /product-variant` di Postman collection butuh `product: {id}` (referensi ke Product eSuite yang sudah ada) -- kemungkinan besar butuh push manual per produk (1:1), bukan auto-generate. Detail & alur teknis di `CONFIG_NOTES.md`. **Next step sebelum bikin service baru: test manual 1x lewat Postman dulu**, belum boleh dianggap benar sebelum divalidasi.

## 17. TODO Berikutnya (urutan diperbarui, gantikan urutan lama di poin 12)

1. **[✅ SELESAI & TERVERIFIKASI 12 Agustus 2026]** Fix `uom_levels[].id` (Level "Low") dites lewat bridge asli (`POST /sync/product?limit=5`, 5 produk: `ODOO-PROD-18374/8857/8856/8858/8855`), lalu diverifikasi lewat `GET /api/debug/pull/product?external_codes=...` (endpoint debug baru, lihat poin 18). **4/5 produk terkonfirmasi `uom_levels` terisi Level "Low"** dengan benar -- bukan test manual lagi, ini push asli lewat bridge. Produk ke-5 (`18374`) belum ke-cross-check ulang (kena isu query param di Swagger, bukan indikasi gagal). **Fix dianggap valid & siap buat batch lebih besar.**
2. Tetap tunggu jawaban vendor soal `cost` (lihat poin 13, pertanyaan sudah dikirim) -- independen dari poin 1, tidak saling blocking. `cost` di 4 produk yang barusan dites masih `1` (sentinel, sesuai kode saat ini) -- belum ada perubahan status.
3. **[BELUM]** Test manual `POST /product-variant` 1x lewat Postman (product yang sudah ada di eSuite) -- validasi hipotesis alur di poin 16/`CONFIG_NOTES.md` sebelum bikin `product_variant_sync_service.py`.
4. **[NEXT]** Re-push bertahap sisa produk yang masih pakai payload lama (`uom_levels` kosong) -- ikuti pola diagnostik `limit` yang sudah ada (mis. 100 dulu, verifikasi, baru full ~1240). Belum dilakukan.
5. Sisanya sama seperti poin 12 lama (poin 2c, 3, 4, 5, 6) -- belum berubah.

## 18a. 🚨 TEMUAN KRITIS -- Upsert Bridge Kemungkinan Menghapus `product-variant` (12 Agustus 2026)

**Info dari vendor:** dashboard sales eSuite menampilkan data **Product Variant**, BUKAN data Product langsung. Karena CBU tidak punya konsep variant asli (tiap ukuran/kemasan = `product.product` Odoo terpisah), vendor sarankan **Product : Product Variant = 1:1** -- konfirmasi resmi, sejalan dengan temuan payload `POST /product-variant` sebelumnya (lihat `CONFIG_NOTES.md`).

**Masalah yang ditemukan & DIKONFIRMASI ULANG (12 Agustus 2026):** `ODOO-PROD-8855` (baru di-upsert sesi ini) tidak tampil variant di UI. **Tapi D'LANIER (belum pernah disentuh bridge sesi ini) JUGA tidak ada variant.** Ini menyingkirkan dugaan awal ("upsert bridge menghapus variant") -- kalau produk yang tidak disentuh pun kosong, upsert bukan penyebabnya.

**Kesimpulan revisi:** kemungkinan besar ini BUKAN regresi, tapi **gap yang sudah ada sejak awal** -- bridge memang belum pernah push ke `/product-variant` sama sekali (konsisten dengan keputusan lama 6 Agustus: "kode untuk entity `/product-variant` tidak akan dibuat", diambil sebelum tahu bahwa variant dipakai buat tampilan dashboard sales). Field `variants[]` yang kelihatan terisi di beberapa produk pada `GET /product` kemungkinan cuma data internal/computed eSuite yang tidak nyambung ke tampilan dashboard sales -- bukan bukti variant "asli" pernah ada lalu terhapus. Ini juga menjelaskan kenapa vendor baru kasih saran 1:1 sekarang.

**✅ STATUS: TIDAK PERLU tahan re-push massal karena alasan "upsert menghapus variant"** (dugaan itu sudah gugur) -- tapi re-push massal `uom_levels`/`cost` tetap TIDAK akan menyelesaikan masalah dashboard sales kosong ini, karena akar masalahnya beda (soal variant belum dibuat, bukan soal payload product). **Prioritas baru: bangun `product_variant_sync_service.py` dulu** sebelum lanjut ke re-push massal manapun -- variant yang hilang lebih fatal buat bisnis (produk tidak tampil sama sekali di sales) dibanding `cost` yang cuma salah tampil angka.

**Next step:**
1. **[PRIORITAS BARU]** Desain & bangun `product_variant_sync_service.py` -- push 1 `product-variant` per `product` (1:1), dijalankan setelah `/sync/product` (butuh `product.id` eSuite, yang berarti perlu `GET /product` dulu buat resolve id per `external_code`, sama pola seperti `_resolve_category_ids()` di `product_sync_service.py`). **Perlu keputusan `external_code` convention buat variant** sebelum kode ditulis -- lihat pertanyaan ke user.
2. Cek juga langsung `GET /product-variant` (bukan cuma field nested `variants[]` di `GET /product`) buat 1 produk -- pastikan apakah collection variant beneran kosong total, atau ada tapi tidak nyambung ke dashboard.

## 19. Fitur Baru: Batch, Upsert by external_code, Push Variant, Logging (12 Agustus 2026)

**Dead code dihapus:** `app/services/product_service.py` dan `app/services/customer_service.py` (versi lama/tidak lengkap, tidak pernah di-import di manapun -- sudah dicek grep sebelum dihapus).

**`POST /sync/product` sekarang punya 3 param baru (semua opsional, default = behavior lama tidak berubah):**
- `batch_size` -- pecah push jadi beberapa batch, pola sama dengan `/sync/customers`. Default `None` = 1 batch semua produk (behavior lama).
- `external_codes` -- upsert produk tertentu saja (comma-separated `ODOO-PROD-{id}`), parse balik ke id Odoo lewat `ProductSyncService._parse_external_codes()`.
- `with_variant` -- **default `False` (opt-in)**, kalau `True` tiap produk yang berhasil di-push otomatis push 1 `product-variant` (1:1). Lihat poin 18a soal alasan bisnisnya (vendor: dashboard sales nampilin data Variant, bukan Product).

**`POST /sync/customers` dapat param baru:** `external_codes` (comma-separated `ODOO-PARTNER-{id}`), pola sama dengan Product.

**Push variant (`ProductSyncService._sync_variants_for_batch()`):** alurnya push product → resolve id eSuite via `EsuiteClient.find_by_external_codes()` (method baru, dipakai bareng oleh `debug.py` juga -- logic paging dipusatkan di 1 tempat) → push ke `/product-variant` referensi `product.id` yang di-resolve. `external_code` variant = SAMA PERSIS dengan produk induk (bukan prefix baru), berdasarkan data nyata yang sudah diobservasi. **Best-effort:** produk yang id-nya belum ke-resolve (eSuite masih proses async) di-skip & dilaporkan di `variant_sync[].skipped`, TIDAK bikin batch product gagal. **BELUM divalidasi end-to-end skala besar** -- baru desain & lolos compile, next step test manual `limit` kecil dulu.

**Logging baru:** `app/core/sync_logger.py::log_sync_result()` -- catat 1 baris CSV (`logs/sync_log.csv`, sejajar `app/`) tiap kali `product`/`customer` sync selesai (timestamp, entity, event, total_matched, synced/failed count, batch_count, status). Kolom `actor` disiapkan tapi kosong -- belum ada diferensiasi user di auth (API key statis), lihat `CONFIG_NOTES.md`. Best-effort/silent-fail -- kegagalan tulis log tidak menggagalkan sync utama. **PENTING (operasional, bukan kode):** `logs/` folder ini di dalam container -- kalau mau persisten antar restart/rebuild Docker, perlu tambah volume mount manual di `docker-compose.yml` (belum dicek/ditambahkan, di luar akses saya).

**File yang berubah sesi ini:** `app/services/product_sync_service.py`, `app/services/customer_sync_service.py`, `app/clients/esuite_client.py`, `app/clients/odoo_client.py`, `app/api/routes/product.py`, `app/api/routes/customer.py`, `app/api/routes/debug.py` (disederhanakan, pakai method baru), `app/core/sync_logger.py` (baru). Semua lolos `python3 -m py_compile`.

## 18. Endpoint Debug Baru: Filter `external_codes` (12 Agustus 2026)

`GET /api/debug/pull/{entity_path}` (`app/api/routes/debug.py`) sekarang terima query param opsional `external_codes` (comma-separated). Kalau diisi, endpoint paging INTERNAL sendiri (200/halaman ke eSuite) dan berhenti begitu semua code ketemu -- `page`/`limit` di request diabaikan. Dibuat supaya bisa cari produk tertentu dari Swagger langsung tanpa jq/terminal/tarik semua data sekaligus (sebelumnya `limit` besar bikin Swagger lambat/hang karena response bisa ~9MB). Response sekarang juga include `meta.found`/`meta.not_found` -- langsung kelihatan kalau ada code yang tidak ketemu.

## 20. Regresi `payload_sent` Sempat Hilang -- Sudah Diperbaiki (13 Agustus 2026)

**Apa yang terjadi:** waktu batching ditambahkan ke `product_sync_service.py` (poin 19), field `payload_sent` di tiap `batch_results[]` ketinggalan -- melanggar aturan FIXED poin 2 ("Response tiap endpoint selalu include `payload_sent`"). Root cause: batching di `product_sync_service.py` dicontoh dari pola `customer_sync_service.py` yang sudah lebih dulu ada (dibuat 11 Agustus), dan pola itu sendiri ternyata SUDAH tidak punya `payload_sent` sejak awal -- jadi bukan cuma product yang kena, customer juga sudah lama begini tanpa disadari. User yang menyadari & menegur setelah lihat hasil test upsert 100 produk.

**Fix:** `payload_sent: batch` ditambahkan ke `batch_results[]` di KEDUA file, di kedua case (success & failed/`except AppError`):
- `app/services/product_sync_service.py`
- `app/services/customer_sync_service.py`

Sudah lolos `python3 -m py_compile` untuk keduanya. Behavior lain tidak berubah (minimal invasive fix, cuma nambah 1 key per dict).

**Lanjutan (13 Agustus 2026, sama hari, ditemukan pas user test `with_variant=true` pertama kali):** `variant_sync[]` (hasil `_sync_variants_for_batch()`) TERNYATA juga belum punya `payload_sent` sejak awal dibuat -- luput dari fix di atas karena letaknya di method terpisah, bukan di `batch_results[]` utama. Sudah ditambahkan `payload_sent: variant_payload` di KEDUA case (success & failed) method `_sync_variants_for_batch()` di `product_sync_service.py`. Lolos compile. Sekarang SEMUA response sync (`product` batch, `customer` batch, `variant_sync`) sudah konsisten include `payload_sent`.

**REVISI LANJUTAN, sama hari (13 Agustus 2026) -- `payload_sent` diubah dari "selalu include" jadi opt-in:** setelah fix di atas, user notice Swagger jadi lambat (payload penuh tiap produk/customer ikut di-render browser untuk batch besar). User pilih opsi "1 param show/hide payload" (bukan bikin endpoint duplikat) -- ini mengganti keputusan FIXED poin 2 lama, sudah dikonfirmasi user & poin 2 di atas sudah diupdate.

**Implementasi:** param baru `include_payload: bool = False` (default **hide**) ditambahkan ke:
- `POST /sync/product` (route `product.py` + `ProductSyncService.sync()`)
- `POST /sync/customers` (route `customer.py` + `CustomerSyncService.sync()`)

Kalau `include_payload=False` (default), key `payload_sent` TIDAK muncul sama sekali di `batch_results[]` maupun `variant_sync[]` (bukan `null`, key-nya dihilangkan). Kalau `True`, behavior sama seperti sebelum revisi ini (payload penuh muncul). `external_codes` tidak terpengaruh, tetap selalu tampil. Berlaku juga untuk `_sync_variants_for_batch()` (flag diteruskan dari `sync()`). Semua file lolos `python3 -m py_compile`: `app/services/product_sync_service.py`, `app/services/customer_sync_service.py`, `app/api/routes/product.py`, `app/api/routes/customer.py`.

**TODO belum dikerjakan:** update `postman/bridge_collection.json` supaya request Sync Product & Sync Customer punya param `include_payload` juga (pola sama seperti `batch_size`/`external_codes` yang sudah ada, disabled by default).

## 21. Menunggu Vendor: Sandbox Table Customer/Product/Variant Dikosongkan (13 Agustus 2026)

User sudah request ke vendor hari ini (13 Agustus 2026) untuk **kosongkan tabel sandbox** `customer`, `product`, dan `product-variant` di eSuite -- tujuannya supaya testing berikutnya lebih bersih (tidak ketumpuk data lama dari test-test sebelumnya di sesi ini, termasuk data testing awal dari developer vendor).

**Dampak buat next step:** setelah dikosongkan, `total_matched_in_odoo` tetap sama (data Odoo tidak berubah), tapi hasil `GET /api/debug/pull/...` seharusnya kosong sampai bridge push ulang. Kalau nanti pull ternyata masih ada data lama, kemungkinan vendor belum selesai proses request, bukan bug bridge. Belum ada info kapan vendor akan selesaikan -- status: **menunggu vendor**, tidak ada aksi kode diperlukan sekarang.

**Pelajaran buat ke depan:** kalau nyontoh pola dari file lain, cross-check dulu ke aturan FIXED di file ini -- jangan asumsi pola existing sudah pasti benar/lengkap.

## 22. Verifikasi `with_variant=true`: Relasi 1:1 BENAR, tapi Price Variant Belum Dikirim (13 Agustus 2026)

User test `with_variant=true` untuk 10 produk & pull data mentah `GET /product-variant` + `GET /product`, hasilnya menjawab 2 pertanyaan lama sekaligus:

**✅ Relasi Product ↔ Product Variant SUDAH BENAR (1:1, FK kepasang).** Cross-check manual: `variants[]` di `GET /product` untuk `ODOO-PROD-9035` berisi 1 variant (`id: 6a7d359c1a6a0f06f95ee16b`), dan `GET /product-variant` record itu `product.id`-nya `6a7d359c1a6a0f06f95ee16a` -- cocok persis dengan id produk itu sendiri. Konsisten di semua 10 produk yang dicek. **Menutup poin 18a next-step #2** ("cek langsung GET /product-variant") -- tidak ada bug FK, kemungkinan yang sempat kelihatan "variant tidak muncul" sebelumnya cuma delay antrian async (pola sama seperti kasus lain di sesi ini).

**🐛 BUG DITEMUKAN & DIFIX: variant tidak punya harga sendiri.** `GET /product-variant` nunjukin semua variant `base_price: 0`, `cost: 0`, `store_price: 0`, dan field `is_price_set: false` -- eSuite sendiri tahu harga variant ini belum pernah di-set (bukan sengaja di-nolkan). Root cause: payload `_sync_variants_for_batch()` cuma kirim `product`, `external_code`, `name`, `status`, `product_type`, `product_category`, `base_uom`, `currency` -- tidak pernah kirim `base_price`/`cost` sama sekali (ngikutin contoh payload vendor yang juga tidak mencantumkan field itu). **Dampak bisnis serius:** karena dashboard sales eSuite nampilin data Variant (bukan Product, poin 18a), ini berarti SEMUA harga di dashboard sales berpotensi tampil Rp 0.

**Fix diterapkan:** `product_sync_service.py::_sync_variants_for_batch()` sekarang ikut kirim `"cost": item["cost"]` (selalu `0`, konsisten kebijakan cost) dan `"base_price": item["base_price"]` (mirror dari produk induk) di payload variant. Lolos `python3 -m py_compile`.

**🟡 Re-test dilakukan (13 Agustus 2026), payload TERKONFIRMASI terkirim benar, tapi BELUM di-pull ulang buat verifikasi tersimpan.** User re-push `ODOO-PROD-9035` pakai `with_variant=true&include_payload=true` -- `variant_sync[0].payload_sent[0]` sekarang benar-benar berisi `"cost": 0, "base_price": 57670` (fix sudah aktif & terkirim, `esuite_response: status 200`). **NEXT STEP (belum dilakukan):** `GET /api/debug/pull/product-variant?external_codes=ODOO-PROD-9035` buat pastikan eSuite BENERAN nyimpen `base_price: 57670` & `is_price_set: true` -- jangan anggap selesai cuma dari `status 200`, sudah berkali-kali kejadian di sesi ini "200 sukses" ternyata tidak ke-apply (lihat riwayat `cost`/`uom_levels`). Kalau pull konfirmasi benar, baru boleh ditutup & lanjut re-push massal.

## 23. Tab "Attribute & Variant" di Detail Produk Tidak Nampilin Variant -- ⚠️ SUPERSEDED, lihat poin 25 (13 Agustus 2026)

User cek langsung UI eSuite: tab **"Attribute & Variant"** di halaman Detail Produk (nested, per-produk) TIDAK menampilkan variant yang di-push bridge (placeholder "Input Data Attribute To Add Variant") -- walau data API (`GET /product-variant`, `variants[]`) sudah benar. **TAPI dikonfirmasi user: variant tetap muncul dengan benar di halaman/dashboard "Varian Produk" yang standalone** (list terpisah, bukan tab nested) -- jadi link Product↔Variant TETAP valid secara fungsional, cuma 1 tab UI spesifik itu yang tidak menampilkannya (kemungkinan tab itu khusus utk workflow attribute-based variant generation manual, beda dari variant yang dibuat via API).

**Keputusan waktu itu: SKIP, tidak prioritas.** User sudah tanya ke vendor soal ini.

**❌ KEPUTUSAN "SKIP" DI ATAS DIBATALKAN -- vendor balas dengan root cause & fix resmi (13 Agustus 2026, sama hari).** Ternyata BUKAN cuma gap 1 tab UI kosmetik seperti dugaan -- ini bug arsitektur nyata di pendekatan `with_variant=true` kita. Lihat poin 25 untuk detail lengkap & rencana perbaikan.

## 24. Rencana Kerja: Stock Sync Odoo -> eSuite (13 Agustus 2026, BELUM DIEKSEKUSI)

Riset dilakukan (PDF `eSuite Synchronization Document v2.0.0`, Postman
collection vendor, gitbook) -- hasil lengkap ada di `ESUITE_GITBOOK_NOTES.md`
bagian 5. Ringkasan rencana (urutan, belum mulai coding):

1. **Verifikasi paling kritis dulu, sebelum desain apapun:** test manual 1x
   `POST /stock-matrix` lewat Postman/Swagger buat 1 produk, cek apakah
   field `quantity` itu **delta (nambah dari stok existing)** atau
   **absolute (replace value)** -- dokumentasi vendor bilang "Change applied
   by the adjustment" yang mengarah ke delta, tapi belum dibuktikan. Ini
   MENENTUKAN arsitektur sync: kalau delta, bridge harus hitung SELISIH
   quantity Odoo vs terakhir sync (butuh state/cache), bukan kirim angka
   Odoo apa adanya tiap kali.
2. **Test kedua:** push `stock-matrix` cuma pakai `warehouse.id` (skip
   `location` sepenuhnya) -- cek apakah diterima & muncul benar di UI/GET.
   Kalau ya, TIDAK PERLU bangun entity `/location` baru (lebih simpel).
   Kalau tidak, baru perlu riset lanjut skema `Location Type` (belum ada
   endpoint pull resmi untuk itu, kemungkinan perlu tanya vendor).
3. **Field mapping dari Odoo (butuh field baru di `get_products()`):**
   - `free_to_use` <- `free_qty` (SUDAH di-fetch dari Odoo, belum pernah
     dipakai/dikirim ke mana pun -- cuma nempel di query, comment lama di
     `odoo_client.py` yang bilang "tetap dikirim lewat field stok terkait"
     itu ASPIRASIONAL, belum benar-benar diimplementasi).
   - `on_hand` <- kemungkinan `qty_available` (BELUM di-fetch, perlu
     ditambah ke field list `get_products()`).
   - `quantity` <- tergantung hasil poin 1 (kalau absolute, kemungkinan
     sama dengan `on_hand`; kalau delta, perlu logic hitung selisih).
4. **Dependency yang sudah siap:** Warehouse (sudah di-push & tervalidasi),
   Product Variant (`with_variant=true`, sudah confirmed FK benar & harga
   sudah fix -- lihat poin 22), UOM (`UOM_MAPPING` existing sudah bisa
   dipakai lagi, field `uom` di stock-matrix persis sama skemanya).
5. **Keputusan yang perlu dikonfirmasi user sebelum coding:**
   - `external_code` convention buat record stock-matrix (per
     product-variant per warehouse? gabungan keduanya jadi 1 string unik?).
   - Endpoint baru `/sync/stock` terpisah (pola sama seperti Product/Customer,
     1 endpoint per entity sesuai FIXED poin 2), trigger manual dulu (bukan
     scheduled) konsisten sama arsitektur sekarang.
   - Frekuensi/cadence sync stok -- stok berubah lebih sering dari data
     produk, tapi trigger tetap manual dulu sesuai FIXED poin 2 (belum ada
     scheduling/automation, itu di luar scope app ini untuk saat ini).
6. **Struktur kode (ikuti pola existing, minimal invasive):**
   `stock_sync_service.py` baru (mirip `product_sync_service.py`) -- resolve
   `product_variant.id` via `find_by_external_codes` (method yang sudah ada
   di `esuite_client.py`, reuse), push batch ke `/stock-matrix`, opsional
   `batch_size`/`external_codes`/`include_payload` (pola yang sudah
   established di Product & Customer), logging via `log_sync_result()`
   existing.

**Next action:** eksekusi poin 1 & 2 (test manual via Swagger/Postman)
sebelum lanjut coding apapun -- keduanya cuma butuh 1-2 request manual,
tapi hasilnya menentukan arsitektur. Jangan mulai coding sebelum ini beres
(konsisten sama aturan project: verifikasi dari data, bukan asumsi).

**⚠️ Update (sama hari, setelah vendor balas soal poin 23): rencana ini kemungkinan perlu direvisi urutannya.** Karena `stock-matrix` butuh `product_variant.id` yang valid & konsisten, dan variant sync kita sekarang harus dirombak dulu (poin 25) sebelum id-nya bisa dianggap stabil -- kemungkinan poin 25 (rombak variant) harus selesai DULU sebelum lanjut stock sync, supaya tidak push stock ke variant id yang nanti berubah/jadi orphan.

## 25. Vendor Balas Root Cause: `variants[]` HARUS Embed di `/product`, BUKAN Push `/product-variant` Terpisah (13 Agustus 2026)

**Konteks:** balasan resmi dari vendor soal poin 23 (variant tidak muncul di tab Detail Produk). Root cause & fix lengkap sudah dicatat di `CONFIG_NOTES.md` (bagian Product Variant, cari "ROOT CAUSE RESMI DARI VENDOR"). Ringkasan di sini fokus ke DAMPAK KE KODE.

**Root cause:** tab "Attribute & Variant" baca dari `product.variants[]` yang EMBEDDED di dalam dokumen `/product` -- bukan dari collection `/product-variant` berdiri sendiri. Flow kita (`with_variant=true` -> `_sync_variants_for_batch()` -> push `/product-variant` terpisah) cuma bikin record "mandiri" yang tidak pernah ter-link ke `product.variants[]`. **Vendor eksplisit: hentikan push `/product-variant` terpisah untuk tujuan ini.**

**Perubahan arsitektur yang dibutuhkan (BELUM diimplementasi, cuma rencana):**
1. `_to_esuite_payload()` di `product_sync_service.py` perlu embed key `"variants": [...]` LANGSUNG di payload `/product` (bukan payload terpisah lagi).
2. **Wajib resolve `variants[].id` yang KONSISTEN sebelum tiap push** -- matching update di sisi eSuite pakai `id`, BUKAN `external_code`. Kalau `id` kosong tiap kali, eSuite bikin variant baru tiap sync (duplikat menumpuk). Jadi sebelum build payload, bridge harus:
   - Resolve existing variant id via `GET /product-variant` filter `external_codes` (reuse `EsuiteClient.find_by_external_codes()`, method udah ada, pola sama kayak resolve category id).
   - Kalau ketemu -> isi `variants[0].id` dengan id itu (kasus update / produk yang variantnya sudah pernah dibuat, termasuk 10 produk yang sempat ditest `with_variant=true` sesi ini).
   - Kalau tidak ketemu -> `variants[0].id` dikosongkan (kasus produk benar-benar baru, eSuite auto-generate & isi `product.variants[]` otomatis).
3. **Hapus/deprecate flow lama:** `with_variant` flag & `_sync_variants_for_batch()` (method push ke `/product-variant` terpisah) sudah tidak relevan buat tujuan tampil di UI produk -- kemungkinan diganti total sama logic embed di atas, bukan cuma dipatch. Perlu diputuskan: `variants[]` jadi SELALU di-embed (default, tidak opt-in lagi) karena keputusan 1:1 sudah final, atau tetap ada flag `with_variant`.
4. **Field payload variant BEDA dari skema lama:** `id`, `name`, `external_code`, `attributes: []`, `sku`, `barcode`, `cost`, `extra_price`, `status` -- **TIDAK ADA `base_price`** di level variant (beda dari fix `payload_sent`/`base_price` yang baru saja diterapkan poin 22, yang itu based on skema `/product-variant` standalone lama). Field `extra_price` (baru, belum pernah dipakai) kemungkinan markup di atas `base_price` produk induk -- BELUM dikonfirmasi eksplisit, perlu ditest setelah implementasi.
5. **10 produk yang sudah kadung dites `with_variant=true` sesi ini** (`ODOO-PROD-9035`, `9034`, `9033`, `9032`, `9031`, `8855`, `8856`, `8857`, `8858`, `18374`) -- variant mereka SUDAH ada di collection `/product-variant` sebagai record "orphan" (tidak ter-link). Re-push dengan pendekatan baru (poin 2 di atas) akan resolve id yang sudah ada itu dan LINK-kan (bukan duplikat) -- konsisten dengan cara vendor fix `ODOO-PROD-9035` manual sebagai contoh.

**✅ DIIMPLEMENTASI 13 Agustus 2026 (user konfirmasi "lanjut").** Keputusan poin 3: `with_variant` TETAP flag opt-in (default `False`) -- minimal invasive, tidak ubah behavior default caller yang cuma mau push Product tanpa variant. Perubahan kode:

- **`app/services/product_sync_service.py`:**
  - `_sync_variants_for_batch()` (push `/product-variant` terpisah) **DIHAPUS TOTAL**.
  - Method baru `_resolve_existing_variant_ids(codes_wanted)` -- resolve id variant existing via `GET /product-variant` (reuse `EsuiteClient.find_by_external_codes()`), dipanggil SEKALI di `sync()` sebelum build payload (bukan per-batch lagi).
  - `_to_esuite_payload()` sekarang terima param `with_variant`, `existing_variant_ids` -- kalau `with_variant=True`, embed key `"variants": [{"id": existing_id_or_kosong, "name", "external_code", "attributes": [], "sku": "", "barcode": "", "cost": 0, "extra_price": 0, "status": "active"}]` LANGSUNG di payload `/product` (skema PERSIS contoh vendor, TIDAK ada `base_price` di level variant).
  - `result["variant_sync"]` (list per-batch) diganti `result["variant_summary"]` (`{total, linked_to_existing_variant, new_variant}`) -- tidak ada lagi push terpisah yang perlu dilaporkan per-batch.
  - `payload_sent` (kalau `include_payload=true`) otomatis include `variants[]` juga sekarang, karena sudah jadi bagian dari payload `/product` itu sendiri -- tidak perlu key terpisah.
- **`app/api/routes/product.py`:** deskripsi param `with_variant` diupdate, signature tidak berubah (tetap `bool`, default `False`).

Lolos `python3 -m py_compile` (`product_sync_service.py` + `product.py`).

**BELUM ditest end-to-end.** Next step (WAJIB sebelum re-push massal):
1. Push 1 produk yang SUDAH pernah di-test `with_variant=true` sebelumnya (mis. `ODOO-PROD-9034`, yang variant lamanya masih orphan) pakai `event=upsert&with_variant=true&include_payload=true` -- cek `variant_summary.linked_to_existing_variant` harus `1`, dan `payload_sent[0].variants[0].id` harus KETEMU (bukan kosong) -- itu bukti resolve-id jalan benar.
2. Cek langsung di UI eSuite (tab "Attribute & Variant" halaman Detail Produk) -- variant harus muncul, TIDAK ada duplikat di halaman "List All Variant".
3. Push 1 produk yang BELUM PERNAH ditest variant sama sekali (produk baru) -- cek `variant_summary.new_variant` = `1`, `payload_sent[0].variants[0].id` harus KOSONG (`""`) di request, lalu `GET /product-variant` abis push buat lihat id yang di-generate eSuite.
4. Field `extra_price`/`base_price` di level variant -- belum dikonfirmasi vendor apakah variant otomatis inherit `base_price` produk induk. Setelah test #1/#3, cek `GET /product-variant` produk itu: apakah `base_price`/`is_price_set` sudah benar (mirip `base_price` produk induknya) walau kita tidak kirim `base_price` di level variant. Kalau ternyata TIDAK inherit (variant tetap `base_price: 0`), perlu tanya balik ke vendor -- field itu tidak ada di skema resmi mereka jadi tidak bisa kita tambahkan sembarangan.

**9 produk lain yang masih orphan dari test lama** (`ODOO-PROD-9035` sudah difix manual vendor sebagai contoh, TIDAK perlu di-re-push lagi kecuali mau konsisten prosesnya): `9034`, `9033`, `9032`, `9031`, `8855`, `8856`, `8857`, `8858`, `18374` -- re-push pakai `with_variant=true` setelah verifikasi di atas beres.

**⚠️ Update 14 Agustus 2026: test #1 di checklist atas dijalankan, HASILNYA GAGAL (`linked_to_existing_variant: 0` untuk `ODOO-PROD-9034`) -- root cause BARU ditemukan, bukan cuma soal sandbox belum bersih. Lihat poin 26 untuk detail lengkap & fix kedua yang sudah diterapkan.**

## 26. Fix Kedua: `_resolve_existing_variant_ids()` Salah Query Endpoint -- Root Cause Duplikat Variant yang Masih Muncul (14 Agustus 2026)

**Konteks:** setelah implementasi poin 25 ("lanjut"), user test ulang di `ODOO-PROD-9034` (produk yang sebelumnya sudah py orphan variant dari era push terpisah) pakai `with_variant=true`. Hasilnya `variant_summary.linked_to_existing_variant: 0` -- SEHARUSNYA `1` kalau resolve jalan benar. User pull `GET /product-variant` manual, ketemu bukti: `ODOO-PROD-9034` sekarang punya **2 variant** di `variants[]` embedded-nya (`MPV-09839` sisa lama dengan `external_code` KOSONG, dan `MPV-09889` baru dengan `external_code` benar) -- persis pola duplikat yang harusnya sudah dicegah fix poin 25.

**Investigasi lanjutan (test fresh di `ODOO-PROD-8857`, produk yang SEHARUSNYA sudah pernah linked dari test lama):** hasilnya SAMA -- `linked_to_existing_variant: 0`, dan `GET /product` untuk produk itu menunjukkan variant BARU (`MPV-09895`, `external_code: ODOO-PROD-8857`) ditambahkan DI SAMPING variant lama (`MPV-09830`, `external_code` kosong) -- bukan meng-update yang lama. Duplikat baru terbentuk lagi walau kode sudah pakai flow embed poin 25.

**Root cause sebenarnya (dikonfirmasi dari data mentah `GET /product-variant`, 13 record ditarik user):** SEMUA 13 record di collection standalone `/product-variant` punya field `"id": ""` (kosong total) -- termasuk record yang `external_code`-nya SUDAH cocok persis dengan yang dicari. Ini BUKAN soal data kotor/sandbox belum bersih, tapi **keterbatasan struktural endpoint `GET /product-variant`: field `id` di listing itu memang tidak pernah terisi.** `_resolve_existing_variant_ids()` (poin 25) query ke endpoint ini, lalu filter `if record.get("id")` -- karena `id` SELALU kosong, filter itu SELALU membuang hasil match, resolve SELALU dianggap "belum ada", dan `_to_esuite_payload()` SELALU mengosongkan `variants[0].id` -> eSuite SELALU generate variant baru -> duplikat terus menumpuk, bahkan untuk produk yang sebenarnya sudah linked benar.

**Fix diterapkan (`product_sync_service.py::_resolve_existing_variant_ids()`):** sumber resolve dipindah dari `GET /product-variant` (collection standalone/legacy, field `id` tidak reliable) ke **`GET /product`** (baca `variants[]` yang ter-embed di dalam dokumen produk itu sendiri -- field `id` di sana TERBUKTI valid, lihat data `ODOO-PROD-9035`/`9033` dkk yang variant-nya sudah correctly-linked). Logic baru: `find_by_external_codes("product", codes_wanted)` (reuse method yang sama, cuma ganti `entity_path`), lalu untuk tiap produk yang ketemu, cari elemen `variants[]` yang `external_code`-nya cocok PERSIS dan `id`-nya tidak kosong -- itu yang dipakai untuk update. Lolos `python3 -m py_compile`.

**Cakupan kerusakan existing (dari data yang sudah ditarik user, 14 Agustus 2026) -- cuma 2 dari 11 produk yang benar-benar kena duplikat:**
- `ODOO-PROD-8857` (WESTGOLD Salted 1x40x250g): 2 variant embedded (`MPV-09830` orphan `external_code` kosong, `MPV-09895` benar).
- `ODOO-PROD-9034` (ACETAIA Aceto Balsamico): 2 variant embedded (`MPV-09839` orphan `external_code` kosong, `MPV-09889` benar).
- 9 produk/test lain yang dicek (`9035`, `9033`, `9032`, `9031`, `8855`, `8856`, `8858`, `18374`, + 1 produk test baru `WH-VARTEST-...`) -- masing-masing cuma 1 variant, `external_code` sudah benar, TIDAK ada duplikat.

**PENTING -- fix ini MENCEGAH duplikat BARU, TIDAK membersihkan yang sudah ada.** 2 variant orphan (`MPV-09830`, `MPV-09839`) di atas masih nyangkut di `variants[]` masing-masing produk. Push ulang (bahkan dengan fix ini) TIDAK akan menghapusnya -- berdasarkan pola yang teramati (push dengan `id` kosong sebelumnya MENAMBAH entry baru ke array, bukan REPLACE array), kemungkinan besar API `/product` upsert bersifat APPEND untuk `variants[]`, bukan full-replace. Tidak ada endpoint delete terdokumentasi untuk menghapus 1 entry dari `variants[]`. **Opsi pembersihan (belum dieksekusi, perlu keputusan user):** (a) hapus manual lewat UI eSuite per-produk (cuma 2 produk, kecil), atau (b) minta vendor hapus entry orphan itu langsung di database sandbox.

**Next step (belum dilakukan):**
1. Re-test `ODOO-PROD-9034` dan `ODOO-PROD-8857` pakai `with_variant=true&include_payload=true` -- sekarang HARUS `linked_to_existing_variant: 1` (resolve nemu `MPV-09889`/`MPV-09895` yang `external_code`-nya sudah benar), dan payload yang dikirim harus isi `variants[0].id` = id variant yang benar itu (bukan kosong) -- pastikan TIDAK nambah variant ke-3.
2. Verifikasi 9 produk lain (yang sudah correctly-linked, tidak ada duplikat) tetap aman di-re-push berkali-kali dengan fix ini -- `linked_to_existing_variant` harus konsisten `1` tiap kali, tidak nambah variant baru.
3. Putuskan cara bersihkan 2 variant orphan yang sudah kadung ada (`ODOO-PROD-8857`, `ODOO-PROD-9034`) -- manual UI atau minta vendor.
4. Setelah bersih & fix tervalidasi, baru lanjut ke stock sync (poin 24) -- `product_variant.id` yang dipakai sebagai referensi di `/stock-matrix` sekarang sumbernya jelas: `GET /product` `variants[].id`, bukan `GET /product-variant`.

**✅ STATUS 14 Agustus 2026: modul Product (termasuk variant embed + fix resolve) dianggap SELESAI untuk sesi ini** -- ditutup sampai ada temuan issue baru (bukan berarti 100% zero-defect, cuma tidak ada lagi masalah terbuka yang diketahui). Keputusan user: pembersihan data sandbox (termasuk 2 variant orphan di atas) akan diminta ke vendor **secara berkala**, bukan cuma sekali sekarang -- **terutama WAJIB sebelum UAT** supaya UAT mulai dari clean state. Ini keputusan project-level, dicatat di sini supaya sesi berikutnya tahu ada kebutuhan rutin ini (belum ada jadwal pasti, trigger manual/on-demand tiap mau testing bersih).

**Lanjut sesi baru:** user akan pindah ke chat baru dan lanjut dari file ini (`SESSION_TRANSFER_NOTE.md`) + `CONFIG_NOTES.md` -- tidak perlu re-explain dari awal, langsung baca kedua file ini dulu sebagai context sebelum lanjut kerja.

---

**Cara pakai:** upload `bridge_app_vXX.zip` (sudah membundle `app/` + `CONFIG_NOTES.md` + `SESSION_TRANSFER_NOTE.md`) di chat baru, lanjut dari poin 17.
