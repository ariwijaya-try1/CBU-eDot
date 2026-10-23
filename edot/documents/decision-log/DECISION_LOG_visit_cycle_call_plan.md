# DECISION LOG -- Visit Cycle Odoo -> Call Plan eSuite

> **Version: v22** -- diupdate 16 Oktober 2026 (mode tes call plan Salesman_12 + `periode` Swagger + GET /odoo/visit-schedule + cek Jadwal MT vs Odoo) (v1 dibuat 5 Oktober 2026)
> Setiap keputusan baru di topik ini: file ini di-update (bukan dibuat baru)
> dan nomor versi dinaikkan. Riset gitbook: `documents/ESUITE_GITBOOK_NOTES.md`
> section 8. Kondisi terakhir: `SESSION_TRANSFER_NOTE.md` addendum 16 Oktober 2026.
> Ringkasan gap terbaru: section "📌 14 Oktober 2026 (sore)" di akhir file.

---

## ✅ 5 Oktober 2026 -- DEFINISI KODE visit di Odoo (dari user)

**Status:** dikonfirmasi user sebagai dasar mapping. User menyebutnya "asumsi
saya" -- belum dicek ke tim sales / admin Odoo yang membuat kodenya. Data
mendukung: di export 19 Agustus, 252 dari 265 baris yang terisi lengkap
konsisten dengan definisi ini.

**Sumber:** 3 field Odoo Studio di Contact (`res.partner`).

- `x_studio_visit_frequency` = jumlah kunjungan per bulan.
  - F1 = 1x sebulan.
  - F2 = 2x sebulan (dua minggu sekali).
  - F4 = 4x sebulan (setiap minggu).
- `x_studio_visit_cycle` = pola minggu kunjungan dalam 1 bulan (4 minggu).
  M = interval dalam minggu, C = minggu ke berapa kunjungan dilakukan.
  - M1 = setiap minggu, tidak perlu C. Pasangannya F4.
  - M2C13 = tiap 2 minggu, di minggu ke-1 dan ke-3 (minggu ganjil). Pasangannya F2.
  - M2C24 = tiap 2 minggu, di minggu ke-2 dan ke-4 (minggu genap). Pasangannya F2.
  - M4C2 = sebulan sekali, di minggu ke-2. Pasangannya F1.
  - M4C3 = sebulan sekali, di minggu ke-3. Pasangannya F1.
- `x_studio_visit_day` = hari kunjungan, Senin sampai Jumat.
- Contoh: M2C13 + F2 + Selasa = dikunjungi hari Selasa di minggu ke-1 dan
  ke-3 setiap bulan.

**Konsekuensi:**
- Pola berlaku per BULAN -> padanan eSuite = Call Plan Pattern dengan
  `week_type` Monthly (`week` 1-5, `visit_day` 1 = Senin ... 7 = Minggu).
- Frequency bisa diturunkan dari cycle; eSuite tidak punya field frequency.
- Baris yang melanggar pasangan di atas (mis. M1 + F1, M1 + F2, M2C24 + F4)
  dan kode di luar daftar ("M2" tanpa C) = data tidak konsisten.

## ✅ 5 Oktober 2026 -- KEPUTUSAN USER: tim FS TIDAK masuk visit cycle

- Field visit customer tim FS kosong total karena memang FS tidak masuk visit
  cycle -- bukan data yang belum diisi.
- FS sementara pakai random visit: sales langsung buat visit manual di eDot.
- Berlaku sampai ada perubahan selanjutnya.

**Konsekuensi untuk bridge:**
- Tidak ada call plan yang dibuat / dikirim untuk customer FS.
- Field visit kosong = customer tidak ikut call plan (dilewati, bukan error).
- Lingkup call plan saat ini = customer yang field visit-nya terisi (di data
  sekarang: tim GT / MT).

## ✅ 5 Oktober 2026 -- KEPUTUSAN USER: baris yang melanggar definisi diperbaiki di Odoo

- Baris visit yang melanggar definisi kode (mis. M1 + F1, M1 + F2,
  M2C24 + F4, "M2" tanpa C, terisi sebagian) akan DIPERBAIKI DI ODOO
  (project Odoo 19), bukan dikoreksi oleh bridge.
- User menegaskan ulang: tim FS memang tidak pakai jadwal kunjungan.

**Konsekuensi untuk bridge:**
- Bridge TIDAK menebak / mengoreksi otomatis nilai visit (Odoo = sumber data).
- DIKONFIRMASI user 5 Oktober: baris yang masih tidak valid DILEWATI +
  DILAPORKAN di response (tidak ada call plan salah yang terkirim).

## ✅ 5 Oktober 2026 -- INFO SALES (via user): cara menghitung "minggu ke-N"

- Kasus dari sales: M2C13 + Senin di Oktober 2026 -> Senin 28 September
  dihitung MINGGU KE-1 OKTOBER.
- Artinya: minggu = minggu kalender utuh Senin-Minggu, dan boleh melewati
  batas bulan (tanggal di akhir bulan sebelumnya bisa masuk minggu ke-1).
  BUKAN "Senin pertama di bulan itu" (kalau begitu hasilnya 5 & 19 Oktober).
- Hasil kasus itu: kunjungan 28 September dan 12 Oktober.
- M1 jadi sederhana: setiap minggu kalender, tanpa soal minggu ke-5.

**Konsekuensi untuk bridge:**
- Tanggal kunjungan harus dihitung dengan aturan sales ini. Lewat
  `POST /call-plan` (bertanggal) aturan apa pun bisa dipenuhi karena bridge
  yang menghitung tanggal. Lewat Call Plan Pattern (month + week) hasilnya
  tergantung cara eDot menghitung minggu -- belum diketahui (tanya dev).

## ✅ 5 Oktober 2026 -- KEPUTUSAN USER: aturan minggu di batas bulan

- User: pakai logika yang SAMA dengan kasus sales (Senin 28 September =
  minggu ke-1 Oktober).
- Aturan: minggu kalender (Senin-Minggu) yang memuat TANGGAL 1 = minggu ke-1
  bulan itu. Minggu berikutnya = minggu ke-2, dst.
- Jadi Senin 26 Oktober 2026 (minggunya memuat 1 November) = minggu ke-1
  NOVEMBER, bukan minggu ke-5 Oktober.
- Contoh M2C13 + Senin: 28 Sep, 12 Okt, 26 Okt, 9 Nov, 30 Nov, 14 Des, 28 Des.
- Catatan: kasus 26 Oktober ini diputuskan user dengan menerapkan logika
  sales, belum ditanyakan langsung ke sales.

## 6 Oktober 2026 -- FAKTA: akun sales di eDot (hasil GET employee dari user, 18 akun)

- 12 akun slot `Salesman_1` .. `Salesman_12`, semuanya di branch
  "Cahaya Boga Utama, CV" (id `6a990e0a0edb65b57e137500`).
- 4 slot sudah bernama orang (cocok dgn info user):
  - `Salesman_1` = "Sales 1 (Ali-GT)" = employee_id `202600016`
  - `Salesman_2` = "Sales 2 (Angga-GT)" = employee_id `202600019`
  - `Salesman_3` = "Sales 3 (Winaya-MT)" = employee_id `202600009`
  - `Salesman_4` = "Sales 4 (Anda-MT)" = employee_id `202600014`
- `Salesman_5` .. `Salesman_12` masih bernama "Sales Cahaya N" (belum dipakai
  orang). User sebelumnya menyebut 6 slot terpakai -- di data baru 4 bernama.
- AKUN GANDA: 4 orang yang sama punya akun test lama (`cahayatesting1`-`4`,
  employee_id `202600005`-`202600008`, external_code `SALES-TESTING-00x`).
  Mapping harus ke akun `Salesman_N`, bukan akun test.
- employee_id TIDAK urut dgn nomor slot -> harus didaftar satu per satu.
- Akun lain: "Sales Testing" (`202600003`, branch Sunshine Food),
  "cahaya-boga-test" (`202600001`, branch HO).
- Company ID eDot (dari user): 5120317.

## 6 Oktober 2026 -- TEMUAN: slot Odoo vs orang TIDAK 1:1 (data Agustus)

Sumber: `documents/old/20260819_Update Contact(1).xlsx`, "Sheet2" (daftar
tim sales: outlet + nama sales, 635 baris) dicocokkan by nama outlet ke
Salesperson Odoo, hanya customer yang punya data visit.

- GT 2 (sekarang `[SALES] BAL GT02`) -> ALI (79 outlet). Bersih.
- GT 1 (sekarang `[SALES] BAL GT01`) -> WINAYA (55) + ABI (37): 2 orang di
  1 slot, terbagi per wilayah (Abi: Jimbaran / Uluwatu; Winaya: Tabanan /
  Canggu / Seminyak).
- MT 4 (sekarang `BAL MT04`) -> ABI (15) + WINAYA (14) + ALI (8): 3 orang.
- MT 2 & MT 3 -> FANI. MT 1 -> YONA.
- Nama di Sheet2: Abi, Ali, Winaya, Fani, Yona, Anda. TIDAK ADA Angga.
  Nama di eDot sekarang: Ali, Angga, Winaya, Anda. Jadi susunan orang sudah
  berubah sejak Agustus -- data ini TIDAK bisa dipakai utk mapping sekarang.
- Yang konsisten di dua sumber: Ali <-> BAL GT02.
- Rename slot Odoo terbukti (by id contact): "GT 1" -> "[SALES] BAL GT01",
  "GT 2" -> "BAL GT02", "MT 2/3/4" -> "BAL MT02/03/04".

**Implikasi desain:** tabel "slot Odoo -> employee_id" hanya benar kalau
1 slot Odoo = 1 orang. Kalau 1 slot masih dipegang beberapa orang, call
plan akan jatuh ke orang yang salah. Perlu dipastikan ke tim sales.

## ✅ 7 Oktober 2026 -- MAPPING SEMENTARA slot Odoo -> orang (dari user)

Status: SEMENTARA (kata user). Menurut user, yang benar-benar sesuai di
Odoo dan eDot baru ALI.

- `[SALES] BAL GT02` -> Ali (GT)    -> eDot `Salesman_1`, employee_id `202600016`  [TERVERIFIKASI]
- `[SALES] BAL GT01` -> Angga (GT)  -> eDot `Salesman_2`, employee_id `202600019`  [sementara]
- `[SALES] BAL MT04` -> Winaya (MT) -> eDot `Salesman_3`, employee_id `202600009`  [sementara]
- `[SALES] BAL MT03` -> Anda (MT)   -> eDot `Salesman_4`, employee_id `202600014`  [sementara]
- `[SALES] BAL MT02` -> Fani (MT)   -> eDot `Salesman_5`, employee_id `202600020`  [sementara, slot dari user 7 Oktober]
- `[SALES] BAL MT01` -> Yona (MT)   -> eDot `Salesman_6`, employee_id `202600017`  [sementara, slot dari user 7 Oktober]

Kolom eDot diisi Claude dari daftar akun 6 Oktober (nama orang yang sama);
pasangan slot -> orang dari user.

**Catatan:**
- Fani = `Salesman_5`, Yona = `Salesman_6` (user, 7 Oktober). Di eDot nama
  akunnya masih "Sales Cahaya 5" / "Sales Cahaya 6" (belum diganti nama orang).
- Mapping ini menggantikan gambaran Agustus (GT 1 = Winaya + Abi, dst).
- Usulan Claude (belum diputuskan): uji coba call plan mulai dari Ali /
  BAL GT02 saja, slot lain menyusul setelah dikonfirmasi.

## ✅ 7 Oktober 2026 -- KEPUTUSAN USER: tempat mapping & minggu ke-5

- Tabel mapping slot Odoo -> akun eDot disimpan DI BRIDGE (bukan field Odoo).
- Minggu ke-5 untuk M2 / M4: SEMENTARA ikut usulan Claude -- dilewati, jeda
  3 minggu diterima. M1 tetap tiap minggu (termasuk minggu ke-5).

## ✅ 7 Oktober 2026 (sore) -- KEPUTUSAN USER: lanjut jalur `POST /call-plan`, 4 hal dijawab sendiri (tanpa menunggu dev)

- Kirim ulang `external_code` yang sama (update atau baris baru?): DIUJI
  langsung, tidak ditanyakan ke dev.
- Batalkan / hapus call plan: sementara MANUAL lewat UI eDot (dugaan user:
  webhook hapus belum disediakan).
- Zona waktu `plan_date`: asumsi user = WITA.
- Cek call plan yang sudah masuk: lewat UI eDot (dugaan user: tidak ada GET).

**Catatan Claude soal `plan_date` (belum dikonfirmasi user, diuji di tes):**
contoh vendor `...T17:00:00.000Z` = 00:00 WIB = 01:00 WITA -> tanggalnya
benar di KEDUA zona. Kalau dikirim 00:00 WITA (`...T16:00:00.000Z`) dan eDot
membacanya dalam WIB, tanggal mundur 1 hari. Usulan: pakai format vendor
(17:00Z hari sebelumnya).

**Rencana tes (lewat Postman vendor, environment PROD, tanpa kode baru):**
1. Kirim 1 baris (1 customer BAL GT02, tanggal jadwal asli), cek di UI:
   muncul? tanggal benar? tipe barisnya apa?
2. Kirim ulang `external_code` sama dgn tanggal beda, cek: 1 baris atau 2.
3. Hapus baris tes manual di UI.
- Bridge belum punya endpoint call plan; `call-plan` belum masuk whitelist
  `GET /api/debug/pull`. Id customer eSuite diambil lewat
  `GET /api/debug/pull/customers?external_codes=ODOO-PARTNER-{id}`.
- Usulan Claude: tes pakai akun test lama (`cahayatesting1`, `202600005`)
  supaya jadwal sales asli tidak tersentuh -- menunggu pilihan user.

## ✅ 8 Oktober 2026 -- FAKTA (dikonfirmasi user): customer baru WAJIB di-register ke sales supaya muncul di app

Kasus: outlet baru ULU MART PECATU, di-push dari Odoo ke eDot, belum punya sales.

- Setelah customer di-add ke eDot, customer itu HARUS di-register ke sales
  dulu, baru muncul di list outlet app eWork salesman yang bersangkutan.
- Cara register (dua-duanya sah): (a) manual via UI eSuite, atau
  (b) bridge `POST /api/mapping/customer-sales` (Swagger, tag Mapping) --
  pakai `mode=add` supaya salesman lain tidak tertimpa; `branchs` +
  `salesmans` wajib dikirim bersamaan (Decision 22 Agustus).
- Implikasi: `POST /sync/customers` saja TIDAK cukup untuk outlet baru --
  langkah mapping ke sales adalah langkah wajib setelahnya. Random Visit
  di eWork tidak bisa dipakai sebagai jalan pintas untuk customer yang
  belum di-register.
- Implikasi call plan: customer yang dikirim lewat `POST /call-plan` juga
  sebaiknya sudah ter-mapping ke salesman yang sama (dugaan, diuji saat
  tes call plan).
- ⚠ Bertentangan dengan asumsi 17 September ("fase 1 semua sales bisa
  lihat semua customer selama branch sama") -- lihat catatan di section
  bawah. Perubahan keputusan MENUNGGU konfirmasi user.

## Keputusan yang masih berlaku dari topik lain (terkait)

- Odoo = sumber data, eDot hanya menerima (arsitektur push satu arah).
- 31 Agustus 2026: join key Salesperson Odoo <-> employee eSuite TIDAK
  dibangun UNTUK order history import; statusnya "pending sampai ada
  kebutuhan lain". Call plan = kebutuhan lain itu (bukan pembatalan keputusan).
- 17 September 2026: fase 1 semua sales bisa lihat semua customer selama
  branch sama; mapping customer per sales = fase 2.
  ⚠ 8 Oktober 2026: TIDAK SESUAI perilaku app -- customer baru baru muncul
  di app sales setelah di-register ke sales (lihat section 8 Oktober).
  Apakah "mapping customer per sales" dimajukan jadi fase 1 = menunggu user.

## BELUM diputuskan (menunggu user) -- status per 14 Oktober 2026

1. ~~Hasil tes `POST /call-plan`~~ **SEBAGIAN BESAR SELESAI (12 Okt):** format
   payload dari dev (`employee`, `date_plan.date` epoch 00:00 UTC), upsert by
   `external_code` (kirim ulang = update), `employee.id` = id internal
   GET /employee. **SISA:** nilai `type` utk jadwal rutin ("Call Plan" vs
   "Non - Call Plan") -- belum tahu (user 14 Okt).
2. ~~Id `res.users` tiap slot Odoo~~ **SELESAI 12 Okt:** id slot diambil dari
   `user_id` customer ber-visit (GT01 = user id 63, terbukti live).
3. ~~Cek branch customer vs akun sales~~ **SUDAH di kode (12 Okt):** guard di
   `POST /api/sync/call-plan` -> beda branch = `skipped` + dilaporkan.
   Kasusnya (MIL'S KITCHEN BALI, HOME DELICATESSEN) diselesaikan di tahap 1
   (lihat section 14 Oktober sore).
4. ~~Konfirmasi tim sales atas mapping sementara (selain Ali).~~ **SELESAI 12 Oktober: mapping 6 slot FINAL** (lihat section 12 Oktober siang).

## ✅ 12 Oktober 2026 -- FAKTA DEV: format payload `/call-plan` yang benar

Contoh Postman vendor lama SALAH (makanya 200 tapi tidak tersimpan). Dev
eDot mengirim payload yang sudah ia coba & TERSIMPAN di DB PROD Cahaya Boga:

```json
{"event":"upsert","data":[{
  "external_code":"CBU-CP-DEVTEST-20261012-02",
  "type":"non_generated",
  "employee":{"id":"6ab2827c285335e17e540f6b"},
  "customer":{"id":"6a9a82df0e20e15d6b0eb0fa"},
  "branch":{"id":"6a990e0a0edb65b57e137500"},
  "date_plan":{"date":1791849600}
}]}
```

- `salesman` -> `employee` (id akun dari GET /employee, terkonfirmasi).
- `plan_date` (string ISO) -> `date_plan: {"date": <unix epoch, detik>}`.
- Field baru `type: "non_generated"` (arti & nilai lain belum dijelaskan).
- Epoch contoh dev 1791849600 = 13 Oktober 2026 00:00 UTC (07:00 WIB /
  08:00 WITA) -> usulan Claude: epoch = tanggal kunjungan jam 00:00 UTC
  (tanggalnya sama di semua zona). Catatan zona waktu `plan_date`
  (7 Oktober) TIDAK BERLAKU lagi.
- Postman collection vendor (`postman/eSuite-Webhook.postman_collection.json`,
  item `call-plan`) masih berisi contoh lama -- JANGAN dipakai.
- Sumber: `documents/catatan dari wa dev.txt` [12 Oktober 2026, 10:44].
- 12 Oktober 11:05 -- TERVERIFIKASI di UI Call Plan List: baris dev muncul --
  Sales 2 (Angga-GT), 4W MINI MARKET SINDU (CUST-00006), Cahaya Boga Utama,
  Call Plan Date 13/10/2026 (epoch 00:00 UTC -> tanggal benar), Visit
  Sequence "-", Type **"Non - Call Plan"**, Status Not Visited, Active True.
- TERBUKA: `type: "non_generated"` tampil sebagai "Non - Call Plan". Jadwal
  rutin dari visit cycle idealnya tipe "Call Plan" -- tanya dev: nilai `type`
  apa utk itu (mis. "generated"?) & dampaknya ke laporan / tampilan eWork.
  Tes kirim ulang `external_code` sama (epoch 1791936000 = 14 Okt) belum.

## ✅ 12 Oktober 2026 -- KEPUTUSAN USER: sample call plan lewat endpoint bridge

- User memilih endpoint bridge (bukan payload manual Postman) utk sample
  call plan Angga (slot `[SALES] BAL GT01`).
- DIBANGUN: `POST /api/sync/call-plan` (tag Sync).
  - Param: `slots` (multi-select dari tabel mapping), `date_from`, `date_to`
    (maks 31 hari), `dry_run` (DEFAULT TRUE), `batch_size` (default 50,
    maks 100), `include_payload`.
  - Alur: customer ber-visit Odoo -> id Salesperson diambil dari `user_id`
    customer (nama slot PERSIS) -> akun eSuite (GET /employee by
    employee_id -> id internal & branch) -> tanggal (aturan
    `visit_schedule_service.py`) -> guard customer eSuite (harus ada + branch
    sama) -> push per batch, jeda 1 detik, batch gagal tidak menghentikan
    batch lain.
  - Payload: `external_code` `ODOO-CP-{id partner}-{YYYYMMDD}`, `type`
    `non_generated`, `employee.id`, `customer.id`, `branch.id`,
    `date_plan.date` = epoch 00:00 UTC.
  - Dilewati + dilaporkan: `invalid_rows`, `skipped` (customer tidak ada di
    eSuite / beda branch). Info saja: `customer_not_mapped_to_salesman_count`
    (customer belum ter-mapping ke salesman di eSuite, tetap dikirim).
- Tabel mapping slot: `app/core/salesman_slots.py` (6 slot final; kunci
  Odoo = nama slot; kunci eSuite = employee_id).
- File: BARU `app/core/salesman_slots.py`, `app/services/call_plan_sync_service.py`,
  `app/api/routes/call_plan.py`; DIUBAH `app/main.py` (+1 import, +1 include_router).
  Tidak ada perubahan DB / env / dependency / Docker.
- FIX 12 Oktober 13:08: live pertama gagal "Slot Odoo '[SALES] BAL GT01'
  ditemukan 0 res.users" -- cari `res.users` by nama (filter share=False,
  hanya user aktif, tergantung akses akun API) tidak menemukan user slot.
  Diganti: id slot diambil dari `user_id` customer ber-visit (data yang
  memang dibaca bridge). Kalau nama tidak ketemu, error menampilkan daftar
  `salespersons_with_visit_data`.
- Test: py_compile + tes mock OK (aturan minggu, epoch, skip, invalid,
  dry_run, batch gagal, validasi rentang, Swagger multi-select, 422).
- Next: dry_run GT01 19-23 Oktober -> tes kirim ulang kode sama (update vs
  dobel) -> push sample -> cek Call Plan List & app Angga.
- 12 Oktober 13:22 -- DRY RUN LIVE OK (setelah fix): slot `[SALES] BAL GT01`
  (Odoo user id 63) -> Sales 2 (Angga-GT) `6ab2827c285335e17e540f6b`, branch
  `...500`. 295 customer ber-visit, 293 valid. 19-23 Okt (minggu ke-4
  Oktober) = 129 jadwal, semua M2C24 (Sen 7, Sel 36, Rab 42, Kam 16, Jum 28),
  semua customer sudah ter-mapping ke Angga di eSuite, 3 batch.
  - 1 dilewati: MIL'S KITCHEN BALI (`ODOO-PARTNER-24866`) -- branch eSuite
    Sunshine Food (`...502`) beda dgn branch Angga.
  - 2 tidak valid (M2C24 + F4): BUKIT ARTA PANGAN CV, KARUNIA SEJAHTERA ->
    diperbaiki di Odoo.
  - Usulan Claude: tes kirim ulang dulu dgn rentang 1 hari (19 Okt, 7
    jadwal): push -> cek UI 7 baris -> push ulang -> cek tetap 7 (bukan 14).
- 12 Oktober 13:32 -- PUSH PERTAMA lewat bridge: GT01, 19 Okt, dry_run=false
  -> 7 jadwal, 1 batch, eSuite 200 "success", failed 0. Kode:
  ODOO-CP-40360/24240/24379/24665/25402/25485/25487-20261019. Menunggu cek UI
  (harus 7 baris), lalu push ulang identik (harus tetap 7).
- 12 Oktober 14:35 -- TERVERIFIKASI UI: 7 baris 19/10/2026 Sales 2
  (Angga-GT) sesuai 7 customer, branch Cahaya Boga Utama, Type "Non - Call
  Plan", Not Visited, Active True (+1 baris tes dev 13/10 SINDU masih ada).
  Belum jelas apakah screenshot ini sesudah push ulang -- ditanyakan ke user.
- 12 Oktober 14:36 -- user: hasil 8 baris (7 + SINDU). DIBACA Claude sbg:
  sesudah push ulang tetap 7 -> kirim ulang `external_code` sama TIDAK
  menggandakan (perlu konfirmasi user).
- 12 Oktober 14:36 -- TEMUAN LAPANGAN: user cross-check ke Angga -> jadwal
  Angga BESOK (Selasa 13 Okt, minggu ke-3 Oktober) ke JIMBARAN. Belum dicek
  apakah jadwal hitungan bridge utk 13 Okt sama. Kemungkinan: (a) slot GT01
  dipakai >1 orang (data Agustus: Abi = Jimbaran/Uluwatu, Winaya = Tabanan/
  Canggu/Seminyak) -> lihat catatan masalah lapangan; (b) data visit Odoo
  tidak sesuai jadwal nyata; (c) beda cara hitung minggu.
- Kode: response `POST /api/sync/call-plan` ditambah `delivery_route` per
  jadwal + `per_date_route` (ringkasan tanggal -> rute) dari
  `x_studio_delivery_route` -- info saja, gagal baca tidak menggagalkan sync.
  File: `app/services/call_plan_sync_service.py`.
- Next: dry_run GT01 12-23 Okt -> bandingkan `per_date_route` Selasa 13 vs
  Selasa 20 dgn jadwal nyata Angga.

## ✅ 12 Oktober 2026 15:02 -- TERBUKTI: kirim ulang `external_code` sama = UPDATE, bukan dobel

- Push ulang identik (GT01, 19 Okt, 7 jadwal, respons 200) -> Call Plan List
  19/10/2026 tetap 7 baris (filter 19-19 Okt, Sales 2 Angga-GT).
- Artinya: `/call-plan` upsert by `external_code`. Endpoint bridge aman
  dijalankan ulang utk rentang yang sama; perubahan jadwal di Odoo cukup
  dikirim ulang (baris yang tanggalnya HILANG dari Odoo tidak terhapus
  otomatis -- tetap hapus manual via UI, keputusan 7 Oktober).
- Menutup pertanyaan terbuka "kirim ulang update atau baris baru" (7 Okt).
- Catatan: respons ini belum berisi `delivery_route` -> bridge belum
  di-restart setelah update kode route.
- 12 Oktober 15:28 -- DRY RUN GT01 12-23 Okt (dgn rute): 265 jadwal
  (minggu ke-3 = M2C13 136, minggu ke-4 = M2C24 129), 2 skip beda branch
  (HOME DELICATESSEN 15 Okt, MIL'S KITCHEN BALI 20 Okt), 2 invalid.
  - Rute di Odoo bernama "RUTE 9".."RUTE 18" + TABANAN / DENPASAR /
    KLUNGKUNG -- TIDAK ada rute bernama Jimbaran.
  - Selasa 13 Okt (besok): RUTE 16 22, RUTE 11 9, RUTE 9 4, TABANAN 2,
    DENPASAR 1, RUTE 12 1. Selasa 20 Okt: RUTE 12 19, RUTE 15 8, RUTE 14 3,
    RUTE 13 3, RUTE 11 2, TABANAN 1.
  - TABANAN banyak di GT01 (Rab 21 Okt 38, Jum 16 Okt 22) -- di data Agustus
    Tabanan wilayah Winaya (slot GT 1 bersama Abi) -> indikasi slot bersama.
  - Belum bisa disimpulkan: perlu tahu RUTE berapa = Jimbaran (tanya user /
    sales).

## Progres tes `POST /call-plan`

- 10 Oktober, langkah 1 OK: customer `ODOO-PARTNER-39092` -> eSuite id
  `6a9a82df0e20e15d6b0eb0fa`, branch Cahaya Boga Utama, sudah ter-mapping ke
  9 akun sales (termasuk `cahayatesting1` dan `Salesman_1`).
- 10 Oktober, Kirim 1 (Postman PROD, `external_code` `ODOO-CP-TEST-39092`,
  salesman `cahayatesting1` id `6a9e2896d955b7b97a88a46e`, customer
  `6a9a82df0e20e15d6b0eb0fa`, branch `...500`, `plan_date`
  `2026-10-21T17:00:00.000Z`): respons `200 {"data":"success"}`, TAPI di UI
  Call Plan List rentang 20-31 Oktober 2026: "No results found". Pola
  "200 tapi tidak tersimpan" (atau diproses async / ke tempat lain).
  Kirim 2 DITUNDA. Next: lebarkan rentang tanggal; kalau tetap kosong ->
  tanya dev eDot (skema `/call-plan` di PDF hanya "per ework contract",
  contoh Postman bisa jadi tidak lengkap).
- 10 Oktober, Kirim Angga (`external_code` `ODOO-CP-TEST-39092-ANGGA`,
  salesman `Salesman_2` id `6ab2827c285335e17e540f6b`, sisanya sama):
  respons 200, di UI (20-31 Oktober, filter Sales 2) juga "No results found".
  Jadi bukan masalah akun test.
- Info dari user (10 Oktober): penyebabnya antara antrian terlalu banyak
  (update delay) atau memang tidak terkirim; akan di-fix Senin 12 Oktober.
- Saran Claude: Senin cek UI dulu SEBELUM kirim ulang -- kalau antrian
  akhirnya diproses, kirim ulang bisa membuat baris ganda. Kirim 2 (tes
  update `external_code` sama) tetap ditunda sampai baris pertama terbukti
  masuk.
- 12 Oktober (Senin, 08:45): Call Plan List (`/ework/call-plan/list`),
  rentang 20-31 Oktober, cari "SINDU" -> tetap "No results found". Dua
  kiriman Sabtu TIDAK masuk (bukan sekadar antrian sampai Senin pagi).
  Next: konfirmasi ke dev apakah fix sudah naik -> kalau sudah, kirim ulang
  payload Angga SEKALI, cek 10-15 menit kemudian.
- Cadangan kalau webhook tetap gagal (usulan Claude, belum diputuskan):
  Call Plan List punya tombol "Upload Bulk" -> bridge bisa menghasilkan file
  Excel bertanggal (tanggal tetap dihitung bridge dgn aturan minggu sales),
  admin upload manual. Template-nya belum dilihat.
- 12 Oktober: payload khusus investigasi dev dibuat -- `external_code`
  `CBU-CP-DEVTEST-20261012-01`, salesman Angga `6ab2827c285335e17e540f6b`,
  customer `6a9a82df0e20e15d6b0eb0fa`, branch `...500`, `plan_date`
  `2026-10-12T17:00:00.000Z` (13 Oktober). Dikirim ke dev bersama
  X-Request-ID & X-Timestamp dari Postman Console.

## 📌 12 Oktober 2026 -- CATATAN MASALAH LAPANGAN & DATA YANG DILEWATI (catatan, BUKAN keputusan)

**Masalah lapangan (dari user):**
- Pada kenyataannya tim sales memakai 1 user (slot) Odoo untuk BEBERAPA
  orang sales. Contoh: `[SALES] BAL MT04` bisa dipegang sampai 4 orang.
- Konsisten dgn analisa Claude 6 Oktober (data Agustus, Sheet2
  `20260819_Update Contact(1).xlsx`): GT02 = Ali (bersih); GT01 = Winaya 55 +
  Abi 37; MT04 = Abi 15 + Winaya 14 + Ali 8; MT02 = Fani 20; MT03 = Fani 10
  (+ beberapa lain); MT01 = Yona 1.
- Status: masih akan dikomunikasikan ke lapangan.
- Asumsi user: dampaknya akan ada penyesuaian visit cycle mengikuti
  pembagian (slot / orang) yang benar.
- Dampak ke bridge (catatan Claude): mapping 1 slot = 1 akun eDot
  (keputusan 12 Oktober) mengirim SEMUA jadwal slot ke 1 akun. Utk slot yang
  dipakai beberapa orang, sebagian jadwal bisa jatuh ke orang yang salah
  sampai pembagian di Odoo dirapikan. Slot paling aman utk uji: GT02 (Ali).
  Tidak ada perubahan kode / mapping dari catatan ini.

**Data yang dilewati / ditemukan di dry run GT01 (Angga) 19-23 Okt:**
- MIL'S KITCHEN BALI (`ODOO-PARTNER-24866`): dilewati -- di eSuite branch
  Sunshine Food (`...502`), Angga di branch Cahaya Boga Utama (`...500`).
  Perlu cek company / slot customer ini di Odoo.
- BUKIT ARTA PANGAN CV & KARUNIA SEJAHTERA: tidak valid (M2C24 + F4, harus
  F2) -> perbaiki di Odoo.
- Beban per hari tidak rata: Senin 7, Selasa 36, Rabu 42, Kamis 16, Jumat 28
  -- perlu dikonfirmasi ke sales (kemungkinan terkait slot dipakai banyak
  orang).

## 📌 13 Oktober 2026 -- INFO MEETING: struktur tim sales (catatan fakta, BUKAN keputusan)

**Dari user (hasil meeting):**
- Sales MT1 dan MT2 masing-masing membawahi 3 sales merchandiser (SMD1, SMD2,
  SMD3).
- Sales MT3, MT4, GT1, GT2 selalu FIX SCHEDULE.

**Dampak ke call plan (analisa Claude, belum diputuskan):**
- Slot fix schedule (`GT01`, `GT02`, `MT03`, `MT04`) = cocok dgn pendekatan
  call plan bertanggal dari visit cycle Odoo.
- `MT01` / `MT02`: kunjungan kemungkinan dijalankan SMD, sedangkan mapping
  saat ini mengirim semua jadwal ke 1 akun (Yona / Fani). Usulan: TAHAN push
  call plan MT01 & MT02 sampai jelas (a) SMD perlu akun eDot sendiri atau
  tidak, (b) jadwal di Odoo dicatat per SMD atau per MT.
- Belum menjawab kasus Angga (GT01) 13 Okt "ke Jimbaran" -- masih perlu tahu
  RUTE berapa = Jimbaran & apakah TABANAN area Angga. Push GT01 19-23 Okt
  tetap HOLD.
- Tidak ada perubahan kode / mapping dari catatan ini.

## Belum dijawab dev eDot

Daftar lengkap di `documents/ESUITE_GITBOOK_NOTES.md` section 8 (webhook
pattern, tipe baris hasil `POST /call-plan`, cara hapus/ganti, zona waktu
`plan_date`, definisi week + minggu ke-5, `salesman.id`, syarat mapping
customer-salesman).

## Status (per 14 Oktober 2026)

~~Tahap diskusi. Belum ada kode~~ (TIDAK BERLAKU sejak 12 Oktober).
- Kode jalan live: `GET /api/odoo/visit-today`, `POST /api/sync/call-plan`
  (dry run default), tabel `app/core/salesman_slots.py` (6 slot).
- Push live baru 1 sample: GT01 (Angga) 19 Okt, 7 jadwal (terverifikasi UI,
  kirim ulang = update). Push lebih luas MENUNGGU tahap 1 (perbaikan data
  Odoo, lihat section 14 Oktober sore).
- Tidak ada perubahan database / env / Docker / dependency di topik ini.

---

## 10 Oktober 2026 -- Titipan dari topik Stok Outlet (keputusan user)

- Endpoint `POST /api/sync/outlet-stock` melewati outlet yang belum punya sales branch di eSuite (`skipped_customers`), dan outlet yang belum ter-register ke salesman tidak tampil di app sales (fakta 8 Oktober).
- Keputusan user: perbaikan mapping outlet -> sales branch + salesman utk outlet-outlet ini DIKERJAKAN DI SINI (mapping visit cycle), bukan di endpoint stok outlet.
- Setelah mapping visit cycle dijalankan utk outlet tsb: jalankan ulang `POST /api/sync/outlet-stock` (aman diulang; isian sales tidak tertimpa). Detail: `DECISION_LOG_outlet_stock.md` section 10 Oktober.

## 10 Oktober 2026 -- KEPUTUSAN USER: mapping customer -> salesman diambil dari Odoo (salesman id)

- Pernyataan user: "mapping customer juga akan di fix dari odoo (salesman id)".
- Artinya (pembacaan Claude, terbuka utk dikoreksi): pasangan customer -> salesman di eSuite (`sales.salesmans[]`) diturunkan dari salesman yang tercatat di customer Odoo, bukan diisi manual lewat UI / `POST /api/mapping/customer-sales` dgn `salesman_ids` ketikan.
- Menjawab KONFLIK TERBUKA 8 Oktober (asumsi 17 September "fase 1 semua sales lihat semua customer selama branch sama; mapping per sales = fase 2"): mapping per sales jadi bagian pekerjaan sekarang, sumbernya Odoo.
- Ketergantungan: tabel mapping slot salesman Odoo -> akun eDot di bridge (keputusan 7 Oktober; per 7 Oktober baru Ali yang terverifikasi sesuai di Odoo & eDot). Field Odoo yang dipakai sbg "salesman id" di customer BELUM ditentukan. **(TERJAWAB 12 Oktober: `res.partner.user_id` / Salesperson -- lihat section 12 Oktober siang.)**
- Juga menutup kebutuhan outlet stok yang di-skip / tidak tampil di app krn belum punya branch / salesman (titipan 10 Oktober di atas).

## 12 Oktober 2026 -- KODE PERTAMA: hitung jadwal kunjungan (read-only) utk stok outlet

- Dibangun `app/services/visit_schedule_service.py` + `GET /api/odoo/visit-today` (tag "odoo - Get"). Dipakai topik Stok Outlet (keputusan user 12 Oktober, lihat `DECISION_LOG_outlet_stock.md`), logic disiapkan utk dipakai ulang call plan.
- Menerapkan aturan yang sudah diputuskan: minggu kalender Senin-Minggu, minggu yang memuat tgl 1 = minggu ke-1; M1 tiap minggu (termasuk ke-5), M2C13 = 1 & 3, M2C24 = 2 & 4, M4C2 = 2, M4C3 = 3; pasangan F wajib (M1-F4, M2-F2, M4-F1); baris tidak valid dilewati + dilaporkan (`invalid_rows`).
- Detail teknis: nilai field dibaca lewat `fields_get` (selection key -> label), dinormalisasi huruf besar (data Odoo campur "Senin"/"SENIN"); "hari ini" = WITA (UTC+8, offset tetap); hari Sabtu/Minggu = tidak valid (definisi Senin-Jumat).
- Uji mock: 28 Sep = minggu 1 Okt, 12 Okt = minggu 3, 26 Okt = minggu 1 Nov, 30 Nov = minggu 1 Des, 28 Des = minggu 1 Jan 2027 -- cocok dgn contoh M2C13 + Senin di section 5 Oktober.
- Filter: `salesperson_ids` = `res.partner.user_id` (dikonfirmasi user 12 Oktober), `company_id` = `res.partner.company_id`.
- Belum menulis apa pun ke eSuite (bukan call plan).

## ✅ 12 Oktober 2026 (siang) -- KEPUTUSAN USER: mapping slot Odoo -> akun eDot FINAL + data import visit 10 Oktober

**Mapping FINAL (berlaku sampai ada perubahan selanjutnya):**

- `Salesman_1` = `[SALES] BAL GT02` = Ali (GT)
- `Salesman_2` = `[SALES] BAL GT01` = Angga (GT)
- `Salesman_3` = `[SALES] BAL MT04` = ~~Winaya~~ -> Fani (MT) (per 14 Oktober)
- `Salesman_4` = `[SALES] BAL MT03` = Anda (MT)
- `Salesman_5` = `[SALES] BAL MT02` = ~~Fani~~ -> Winaya (MT) (per 14 Oktober)
- `Salesman_6` = `[SALES] BAL MT01` = Yona (MT)

**Aturan (user):** username eDot TETAP dan mapping ke slot Odoo TETAP; orang di
balik slot boleh berganti (resign, izin, dst). Jadi kunci mapping di bridge =
slot Odoo (`res.users`) <-> akun eDot (username / id salesman); nama orang
hanya keterangan, bukan kunci. Menggantikan status "mapping sementara" 7 Oktober.

**Field salesman di customer:** `res.partner.user_id` (Salesperson) --
dikonfirmasi user 12 Oktober (lihat section 12 Oktober kode pertama & 
`DECISION_LOG_outlet_stock.md`). Menjawab pertanyaan terbuka 10 Oktober.

**Contact tipe `Other` / `Delivery` (alamat anak):** KEPUTUSAN USER -- sementara
TETAP dibuatkan call plan seperti `Contact` biasa. Kalau ternyata tidak perlu,
akan kelihatan saat penyesuaian call plan dengan visit plan existing sales.

**Data import ke Odoo 10 Oktober** (file user `sudah_di_import_10-10-2026.xlsx`,
2.574 contact Bali; kolom `user_id`, `x_studio_sales_team`, 3 field visit, lat-long):

- 918 contact punya visit; tipe: 310 Contact, 582 Other, 26 Delivery.
- 875 baris valid (pasangan cycle-frequency sesuai definisi, non-FS); 855 di
  antaranya dipegang 6 slot final: GT02 386, GT01 267, MT03 76, MT01 65,
  MT04 55, MT02 45 (hitungan semua baris visit per slot).
- Semua contact ber-visit sudah punya lat-long.
- 63 baris bermasalah -> daftar: `documents/visit_cycle_perlu_dicek_2026-10-12.xlsx`
  (diperbaiki di Odoo sesuai keputusan 5 Oktober; bridge melewati + melaporkan):
  - 28 kombinasi cycle+frequency salah (M1+F1 9 & M2C13+F4 9 di MT02, M1+F2 3, M2C24+F4 6, M2+F2 1);
  - 15 cycle `M2` tanpa C;
  - 4 customer FS punya visit (FS05 x3, FS08 x1) -- bertentangan dgn keputusan FS tanpa visit;
  - 20 baris di slot tanpa akun eDot (GT05-09, GT11, MT05, MT08, NKA, Office) -> dilewati + dilaporkan.
- Hari campur huruf besar/kecil (`Senin`/`SENIN`) -- sudah ditangani normalisasi
  di `visit_schedule_service.py` (bukan koreksi definisi).

## ✅ 14 Oktober 2026 -- PERUBAHAN DATA SALES (dari user): orang di MT04 & MT02 ditukar

- `Salesman_1` = `[SALES] BAL GT02` = Ali (tetap)
- `Salesman_2` = `[SALES] BAL GT01` = Angga (tetap)
- `Salesman_3` = `[SALES] BAL MT04` = **Fani** (sebelumnya Winaya)
- `Salesman_4` = `[SALES] BAL MT03` = Anda (tetap)
- `Salesman_5` = `[SALES] BAL MT02` = **Winaya** (sebelumnya Fani)
- `Salesman_6` = `[SALES] BAL MT01` = Yona (tetap)

Sesuai aturan 12 Oktober (slot Odoo & username eDot tetap, orang boleh berganti):
kunci mapping TIDAK berubah, `employee_id` tidak berubah. Yang diubah hanya label
`person` di `app/core/salesman_slots.py` (dipakai cuma utk echo di response
call plan). Tidak ada perubahan DB/env/Docker/dependency/API. Restart bridge
supaya label baru muncul di response. Nama tampilan akun di UI eDot
(Sales Cahaya 3 / 5) -- kalau perlu diganti, dilakukan manual di eDot.

## 📌 14 Oktober 2026 (sore) -- JAWABAN USER atas daftar gap (pengganti daftar terbuka sebelumnya)

"Tahap/step 1" = istilah user; dibaca sbg tahap perbaikan & penataan data
visit di Odoo sebelum push call plan meluas.

1. **Kasus Angga (GT01) 13 Okt "ke Jimbaran":** diselesaikan dgn pengecekan
   data di Odoo. Dari sisi bridge: pastikan data jadwal memang murni dari
   Odoo (field visit contact + `res.partner.user_id`; rute dari
   `x_studio_delivery_route`, info saja). Bridge tidak mengoreksi apa pun --
   sudah sesuai keputusan 5 Oktober.
2. **1 slot Odoo dipakai beberapa orang:** akan di-setup di Odoo sesuai
   mapping terakhir (14 Okt): Salesman_1 GT02 Ali, Salesman_2 GT01 Angga,
   Salesman_3 MT04 Fani, Salesman_4 MT03 Anda, Salesman_5 MT02 Winaya,
   Salesman_6 MT01 Yona. **Ditambah 2 agen lagi** -- detail (slot Odoo, akun
   eDot, orang) BELUM diberikan; tabel `salesman_slots.py` belum diubah.
3. **MT01 & MT02 (SMD):** setup sementara ada 2 SMD (SMD1 & SMD2), masih
   perlu konfirmasi Dian. Push MT01/MT02 tetap ditahan sampai jelas.
4. **Beban harian GT tidak rata:** diselesaikan di tahap 1.
5. **Nilai `type` utk jadwal rutin:** belum diketahui.
6. **Hapus call plan:** masih manual via UI, dan delete via UI pun masih
   gagal (kata user: "hanya stock jadi 0"). Belum ada jalan hapus yang
   berhasil -> hindari push jadwal yang belum pasti (pakai dry run dulu).
7. **63 baris bermasalah** (`visit_cycle_perlu_dicek_2026-10-12.xlsx`):
   diselesaikan di tahap 1.
8. **Customer beda branch (MIL'S KITCHEN BALI, HOME DELICATESSEN):** dijelaskan
   ke user 14 Okt -- branch eSuite customer = company Odoo customer (lewat
   `/sync/customers`), akun Angga di branch CBU. Penyelesaian = koreksi data
   Odoo (company ATAU salesperson) -- menunggu pengecekan user.
9. **Mapping customer -> salesman di eSuite dari `user_id` Odoo:** dijelaskan
   ke user 14 Okt; belum ada endpoint otomatis. Usulan Claude (BELUM
   diputuskan): endpoint mapping dari Odoo, mode `add` default, hanya
   customer ber-visit di slot final, beda branch = skip + lapor.
10. **Contact Other/Delivery:** ditinjau di tahap 1.

Tidak ada perubahan kode / DB / env / Docker / dependency dari section ini.

## ✅ 16 Oktober 2026 -- MODE TES call plan ke akun testing (`Salesman_12`)

**Permintaan user:** data testing visit cycle utk `Salesman_12` (akun testing)
pakai data visit `[SALES] BAL GT01`, utk menguji apakah jadwal dari visit
cycle memunculkan visit list di app eWork.

**Dibangun (minimal invasive, behavior lama tidak berubah tanpa param baru):**
`POST /api/sync/call-plan` + 3 param opsional:
- `test_employee_id` -- `employee_id` akun eSuite pengganti. Data visit tetap
  dari slot Odoo terpilih (WAJIB 1 slot), `employee.id` & branch diambil dari
  akun ini. `slots[].warnings` menandai "MODE TES", `test_mode: true`.
- `external_codes` -- customer tertentu saja (`ODOO-PARTNER-{id}`, comma-separated).
- `limit` -- maks N jadwal yang dikirim (tes kecil, krn call plan belum bisa dihapus).

**Alasan kode tes beda:** `/call-plan` upsert by `external_code` (terbukti
12 Oktober). Kalau tes pakai `ODOO-CP-{partner}-{tgl}`, push asli GT01 nanti
akan MENIMPA baris tes (pindah ke Angga) atau sebaliknya. Mode tes pakai
`ODOO-CP-TEST-{employee_id}-{partner}-{YYYYMMDD}` -> terpisah dari jadwal asli.
Tabel `salesman_slots.py` TIDAK diubah (Salesman_12 bukan slot final).

**File:** `app/services/call_plan_sync_service.py`, `app/api/routes/call_plan.py`.
Tanpa perubahan DB / env / Docker / dependency. Restart bridge.
Test: py_compile + tes mock OK (kode tes, limit, filter customer, tolak >1 slot).

**Langkah tes (usulan Claude):**
1. `employee_id` Salesman_12 -- BELUM tercatat di project (data 6 Oktober
   hanya mencatat Salesman_1-4). Ambil dari UI eSuite / GET /employee.
2. Dry run: slot GT01, `date_from`=`date_to`=hari ini, `test_employee_id`,
   `limit` kecil (mis. 3), `include_payload=true`. Cek `slots[0].esuite_username`
   = Salesman_12 & branch = CBU (`...500`).
3. Customer di eSuite perlu ter-mapping ke Salesman_12 supaya muncul di list
   outlet app (fakta 8 Oktober) -- `POST /api/mapping/customer-sales` mode
   `add` utk customer tsb. Usulan: biarkan 1 customer TIDAK di-mapping utk
   menjawab apakah call plan butuh mapping (lihat `salesman_mapped_on_customer`).
4. Push `dry_run=false` -> cek Call Plan List (filter Salesman_12) -> login app
   eWork Salesman_12 -> cek visit list hari itu.

**Yang dijawab tes ini (terbuka):** (a) apakah baris `type: non_generated`
("Non - Call Plan") tampil di visit list app; (b) apakah customer wajib
ter-mapping ke salesman agar call plan tampil. Catatan: baris tes tidak bisa
dihapus (UI delete gagal, 14 Okt) -> tetap nyangkut di akun testing.

## ✅ 16 Oktober 2026 (lanjutan) -- Swagger call plan: pilihan `periode` (tanpa ketik tanggal)

- Permintaan user: `date_from` di Swagger bisa dipilih, tidak diketik.
- Swagger UI tidak punya date picker utk query param -> dibuat select box
  `periode`: `hari_ini` (default), `besok`, `minggu_ini`, `minggu_depan`
  (minggu = Senin-Minggu). Dihitung saat request dlm WITA (bukan saat start
  server, jadi tidak basi).
- `date_from` / `date_to` jadi OPSIONAL: kalau `date_from` diisi, `periode`
  diabaikan; `date_to` kosong = sama dgn `date_from`. Rentang maks 31 hari tetap.
- ⚠ Perubahan perilaku: sebelumnya `date_from`/`date_to` WAJIB; sekarang
  kosong = hari ini. `dry_run` tetap default TRUE.
- File: `app/api/routes/call_plan.py` saja (service tidak berubah). Tanpa
  perubahan DB / env / Docker / dependency. Restart bridge.
- Test: py_compile + TestClient OK (default hari ini, minggu_depan 19-25 Okt,
  date_from override, periode tidak valid = 422, Swagger render enum).

## ✅ 16 Oktober 2026 (lanjutan 2) -- `GET /api/odoo/visit-schedule`: cek jadwal kunjungan per outlet

- Permintaan user: kirim external code outlet -> tampil jadwal kunjungan + sales-nya.
- Endpoint BARU (tag "odoo - Get", read-only): `GET /api/odoo/visit-schedule`
  - `external_codes` WAJIB (`ODOO-PARTNER-{id}`, pisah koma, maks 50);
    `date_from` opsional (kosong = hari ini WITA); `weeks` 1-12 (default 4).
  - Per outlet: Salesperson Odoo (`user_id`), `esuite_username` +
    `sales_person_name` dari `salesman_slots.py` (null = slot belum di-mapping),
    cycle/day/frequency, `next_visit`, `visit_dates[]` (tanggal, hari, minggu ke-N bulan).
  - Data visit tidak valid -> `valid: false` + `reason` (aturan sama visit-today).
  - Outlet tanpa data visit / bukan customer aktif -> `not_found`.
- Sumber = HITUNGAN dari visit cycle Odoo (aturan minggu 5 & 7 Oktober),
  BUKAN call plan yang tersimpan di eSuite (eSuite belum punya GET call plan).
- File: BARU method `VisitScheduleService.get_outlet_schedule()`
  (`app/services/visit_schedule_service.py`, + import `SLOTS_BY_NAME`);
  `app/clients/odoo_client.py` -- `get_customers_with_visit_schedule()` +
  param opsional `partner_ids` (pemanggil lama tidak berubah);
  `app/api/routes/odoo_get.py` -- route baru. Tanpa perubahan DB / env /
  Docker / dependency. Restart bridge.
- Test mock OK: M2C13 Senin dari 16 Okt -> 26 Okt (minggu ke-1 Nov) & 9 Nov
  (cocok aturan 5 Okt), pasangan salah -> invalid, id tanpa visit -> not_found,
  format salah -> 422.

## 📌 16 Oktober 2026 -- CEK `documents/Jadwal MT.xlsx` (jadwal nyata MT dari user) vs visit cycle Odoo (catatan, BUKAN keputusan)

- Laporan: `documents/cek_jadwal_MT_vs_visit_cycle_2026-10-16.xlsx`.
- Sumber Odoo: `Claude/odoo/Claude outputs/sudah di import semua kolom 16-10-2026.xlsx`
  (export 08-10 + import sesudahnya; bukan live).
- Asumsi baca jadwal (belum dikonfirmasi user): blok I = minggu 1 & 3, blok II =
  minggu 2 & 4; outlet di I dan II hari sama = mingguan (M1 F4).
- Blok A (Bintang/Frestive/Grand Lucky/Pande Putri, slot Odoo MT02): jadwal
  MINGGUAN; 7 dari 20 outlet sesuai. Beda utama: Frestive x5 (Odoo M2C13 JUMAT
  F4 vs jadwal Senin/Selasa tiap minggu), Bintang Ubud & Hayam Wuruk cycle `M2`
  (tanpa C), Bintang Seminyak hari, Grand Lucky Udayana/Sanur F1 (harus F4),
  Karmaphala M2C13, Freshindo Tunjung Sari hari, MU GUNG HWA di Odoo slot MT04.
- Blok B (Coco/7 Hungry/Papaya/Uncle Jo/Circle K, slot Odoo MT03): jadwal 2
  MINGGUAN; hanya 1 dari 31 outlet sesuai (COCO SUPERMARKET SANUR). Banyak yang di
  Odoo M1 F4 padahal jadwal 2 mingguan; hari banyak beda. 7 Hungry: 4 outlet di
  jadwal vs 1 contact di Odoo. MM DC NYANGNYANG tidak ditemukan.
- 98 outlet MT02/MT03 ber-visit di Odoo tidak ada di Jadwal MT (jadwal kemungkinan
  parsial). TRIANDA (C30) di luar blok -> tidak dicek.
- Kesimpulan: data visit MT di Odoo BELUM mencerminkan jadwal nyata -> push call
  plan MT03 juga sebaiknya DITAHAN sampai Odoo dikoreksi (masuk "tahap 1" user).
  Tidak ada perubahan kode.

## ✅ 21 Oktober 2026 -- Swagger `test_employee_id`: deskripsi diperjelas

- Nilai yang diisi = field `employee_id` akun eSuite (angka NIK eSuite, contoh
  `202600016` = Salesman_1), sama dgn kolom `esuite_employee_id` di
  `app/core/salesman_slots.py` & lookup `GET /employee?employee_id=`.
  BUKAN username, BUKAN `id` internal eSuite, BUKAN id user Odoo.
- Cara cari: `GET /api/debug/pull/employee` -> baris username `Salesman_12`.
- Hanya teks description di `app/api/routes/call_plan.py`; logic tidak berubah.
- Fakta live 21 Okt: `employee_id` Salesman_12 = `202600012` (terverifikasi UI
  eSuite field "Employee ID"; `EMP-00010` di header profil BUKAN yang diisi)
  (esuite id `6ab28274dbb8a7b1086967e0`, branch CBU `...500`). Push tes pertama
  pakai slot MT02 -> 1 jadwal (TIARA GATSU 21 Okt) terkirim, eSuite 200.

## ✅ 21 Oktober 2026 -- Mapping akun MT02 <-> MT04 ditukar (MENGGANTI keputusan 14 Okt)

- Sumber: data Nesa (sales manager), DIKONFIRMASI user.
- Keputusan lama 14 Okt ("hanya label `person` ditukar, slot & akun tetap")
  TIDAK berlaku lagi utk MT02/MT04. Alasan: Winaya harus tetap pakai akun
  Salesman_3 agar data input lamanya di eSuite tetap ada.
- Mapping baru di `app/core/salesman_slots.py`:
  - `[SALES] BAL MT02` -> Salesman_3 (`202600009`), Winaya (MT)
  - `[SALES] BAL MT04` -> Salesman_5 (`202600020`), Fani (MT)
- Slot lain tidak berubah: GT02 Salesman_1 Ali, GT01 Salesman_2 Angga,
  MT03 Salesman_4 Anda, MT01 Salesman_6 Yona.
- Akun tes Salesman_12 (`202600012`, "miror testing" MT02 di tabel Nesa)
  TETAP di luar tabel slot -> pakai `test_employee_id`.
- Dampak: belum ada push call plan MT asli -> tidak ada data salah alamat.
  Mapping customer->salesman di eSuite utk outlet MT02/MT04 (kalau sudah
  pernah dibuat ke akun lama) perlu dipindah -- belum dicek.
- Standing rule (user, 21 Okt): setiap perubahan konfigurasi user/akun sales
  -> Claude wajib mengingatkan update `salesman_slots.py` + restart bridge.
  Checklist permanen ditaruh di `CONFIG_NOTES.md`.

## ✅ 21 Oktober 2026 -- `M2` tanpa C = TIDAK VALID; perbaikan data di Odoo -> `M1`

- Konfirmasi user: kode cycle `M2` tanpa C tidak ada dalam definisi (semua M2
  wajib punya C: `M2C13` / `M2C24`). Daftar `CYCLE_RULES` di
  `app/services/visit_schedule_service.py` (M1, M2C13, M2C24, M4C2, M4C3)
  SUDAH BENAR -- tidak diubah.
- Bridge tetap menolak `M2` polos (dilewati + dilaporkan di `invalid_rows`),
  sesuai keputusan 5 Okt (data diperbaiki di Odoo, bukan ditebak bridge).
- Aturan perbaikan data (user): customer Odoo yang tercatat `M2` polos diubah
  ke **`M1`** di Odoo (pasangan `F4`). Contoh kasus: `ODOO-PARTNER-24522`
  BINTANG SUPERMARKET HAYAM WURUK, slot `[SALES] BAL MT02`, `M2` + RABU + F4.
- Catatan teknis: `_invalid_reason()` hanya melaporkan alasan PERTAMA; setelah
  cycle diperbaiki, cek pasangan frequency bisa memunculkan alasan baru.
- Status 21 Okt (user): **15 baris `M2` di Odoo SUDAH diubah ke `M1`.** Belum
  diverifikasi ulang lewat dry run bridge (`invalid_rows` harus tanpa `M2`).
- ✅ Bukti live 21 Okt (screenshot UI eSuite Call Plan List): BINTANG SUPERMARKET
  HAYAM WURUK (CUST-00931) muncul utk Sales Cahaya 12, tgl 21/10/2026 (Rabu),
  branch CBU BRCH-00002, Type "Non - Call Plan", Not Visited -> data `M1` hasil
  perbaikan Odoo terbaca bridge & mode tes Salesman_12 jalan.
- Tanpa perubahan kode/DB/env/Docker/dependency.

## ✅ 21 Oktober 2026 -- Mode tes call plan: akun testing Salesman_12 terisi otomatis

- Keputusan user: test employee SELALU ke Salesman_12 -> employee_id dibuat
  pre-input, tidak perlu diketik lagi.
- Implementasi:
  - `app/core/salesman_slots.py`: konstanta `TEST_EMPLOYEE_ID = "202600012"`,
    `TEST_USERNAME = "Salesman_12"` (di luar `SALESMAN_SLOTS`, bukan slot Odoo).
  - `POST /api/sync/call-plan`: param baru `test_mode` (bool, default false).
    true -> kirim ke `TEST_EMPLOYEE_ID`. `test_employee_id` DIPERTAHANKAN sbg
    override (diisi = mengalahkan default). Aturan mode tes lain tetap (1 slot,
    kode `ODOO-CP-TEST-...`).
- Alasan tidak mengisi default `test_employee_id` = 202600012 langsung: push
  normal jadi harus mengosongkan field tiap kali, dan push multi-slot akan
  error -> default tetap mode normal (false), mode tes cukup 1 centang.
- Tanpa perubahan DB/env/Docker/dependency. Restart bridge.

