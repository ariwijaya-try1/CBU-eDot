# DECISION LOG -- Sales Entities Gap (Salesman / Salesman Division / Customer Group)

> **Version: v1** -- disimpan 17 September 2026
> Ini adalah COPY read-only dari Decision Log utama, yang sumber aslinya (dan
> selalu paling update) ada di memory Claude (Cowork), terikat ke Project
> "eDot" di akun kamu -- BUKAN file yang bisa diedit langsung untuk mengubah
> Decision Log-nya (edit di sini tidak akan sync balik ke memory).
> Kenapa disimpan di sini juga: supaya kamu punya salinan yang bisa dibuka
> langsung dari folder `edot`, tanpa perlu buka chat Claude.
> **Setiap kali ada keputusan baru yang dicatat ke Decision Log ini, file di
> sini akan di-update (bukan dibuat file baru) dan nomor versi di atas
> di-naikkan (v2, v3, dst) supaya kamu tahu urutan revisinya.**

---

## ✅ 17 September 2026 -- KEPUTUSAN USER: 2 pertanyaan bisnis Salesman individual DIJAWAB; arah Customer Group diperjelas

**Q1 (login per-orang vs per-slot) DIJAWAB: per-orang sendiri-sendiri**, kemungkinan besar akun dibuat **manual via UI eSuite** (bukan push otomatis dari bridge). **Keputusan management:** kalau orangnya ganti (turnover), akun TETAP pakai akun orang SEBELUMNYA (tidak dibuatkan akun baru) -- artinya risiko mismatch identitas yang sudah diidentifikasi (nama/title lama nempel ke orang baru) DITERIMA SADAR oleh management, bukan dianggap masalah yang perlu dihindari lewat desain data.

**Q2 (sumber data identitas) DIJAWAB: BELUM ADA di Odoo** -- admin Odoo belum set data karyawan. Data karyawan SAAT INI ada di file Excel yang dibuat tim sales sendiri (user akan taruh di folder device `edot`). **Prasyarat kalau mau bridge push otomatis ke depan:** Excel ini kemungkinan perlu di-import ke Odoo dulu (jadi data karyawan resmi di Odoo), BARU bridge bisa dibangun dari situ -- bukan langsung dari Excel ke eSuite.

**Kesimpulan operasional:** `SalesmanSyncService` individual **TETAP DITUNDA** -- 2 pertanyaan bisnis sudah terjawab, tapi jawabannya justru mengonfirmasi proses akun Salesman kemungkinan besar akan TETAP manual via UI eSuite (bukan use-case yang butuh push otomatis dari bridge), DAN data sumbernya (karyawan) belum ada di Odoo sama sekali. **Next step:** tunggu user taruh file Excel karyawan di folder device; TIDAK ADA rencana kerja proaktif membangun `SalesmanSyncService` sampai (a) data karyawan resmi ada di Odoo, DAN (b) ada kebutuhan konkret untuk push otomatis (bukan cuma manual UI).

**Customer Group -- arah diperjelas (bukan perubahan status, PAUSED tetap berlaku):** user konfirmasi **biarkan saja, dengan sendirinya tidak akan terpakai** -- mapping Customer Group ke eDot (walau sudah di-push/sync) sepertinya belum akan dipakai sampai data sales masuk ke Odoo. Odoo saat ini cuma punya Sales Division (`crm.team`), belum ada sales individual -- jadi ini **PENDING sampai Odoo diselesaikan, BUKAN issue di sisi eDot/bridge**. Data sales SAAT INI cuma ada 6 (slot/akun), rencananya akan dipetakan berdasarkan **Branch** (representasi company Odoo) + tipe Customer Group -- **untuk sekarang (fase 1), semua sales bisa lihat semua customer selama branch-nya sesuai** (cukup); mapping granular customer-per-sales individual kemungkinan lanjut di **fase 2**.

**Order Tracking:** user reconfirm keputusan 10 September (terima apa adanya yang disediakan eDot dulu, custom fix ditunda) -- tidak ada perubahan, lihat catatan project `order_history_import`.

---

- **14 Agustus 2026, dari cross-check `documents/eDOT Template Master Data Go Live - Cahaya Boga Utama.xlsx` (sheet: Basic Information, Branch, User, Customer, Product, Pricelist) + PDF section 8 (Entity index) & 9.9-9.10/9.13:**

- **Entity yang SUDAH dibangun di bridge:** Branch (dari `res.company`), Warehouse, Product Category, Product (+ Variant embed 1:1), Customer (payload MASIH MINIM -- lihat gap di bawah), Customer Group, Stock Matrix, Pricelist, **Salesman Division (BARU 18 Agustus 2026, lihat detail di bawah).**

## 🆕🆕🆕🆕🆕 4 September 2026 (lanjutan lagi) -- Customer Group DIGANTI TOTAL ke data industry Odoo, KODE SUDAH DIBANGUN & py_compile OK, BELUM ditest live

**Keputusan final user:** ganti sepenuhnya sumber data upsert Customer Group dari hardcode (FS/MT/GT/HORECA, 4 grup) ke data DINAMIS `res.partner.industry` Odoo. Proses: ambil semua industry dari Odoo (`OdooClient.get_industries()`), upsert 1:1 jadi Customer Group eSuite -- **BUKAN** mapping/translasi ke 4 grup lama. Tidak ada lagi target "4 grup" buat ditranslasikan, tiap industry Odoo langsung jadi Customer Group sendiri-sendiri di eSuite (pola SAMA PERSIS dengan `SalesmanDivisionSyncService`, crm.team -> Salesman Division 1:1).

**Data real industry Odoo (18 record, dari `GET /odoo/industry` PROD, dishare user 4 September 2026):** Distributor(38), FS-Catering(36), FS-Hotel(34), FS-Industry(37), FS-Restaurant(35), GT-Buah(29), GT-Frozen(28), GT-Retail(32), GT-Specialty Store(39), GT-Supplier(31), LMT-A(25), LMT-B(26), LMT-C(30), LMT-D(27), NKA-A(22), NKA-B(24), NKA-C(23), ONLINE(33). **Catatan:** granularitas & penamaan JAUH beda dari 4 grup hardcode lama (tidak ada "MT" atau "HORECA" polos) -- ini yang mengonfirmasi keputusan 4 September sebelumnya bahwa 4 grup lama cuma ASUMSI sandbox, bukan representasi PROD yang benar.

**Kode SUDAH diubah (4 September 2026), py_compile OK semua 3 file:**
- `app/clients/odoo_client.py::get_industries()` -- tambah param `ids: list | None = None` (filter domain `"id in ids"`, pola sama `get_sales_teams(ids=...)`), dipakai buat upsert industry tertentu saja via `external_codes`. Param `limit` lama TETAP ada (dipakai jg oleh `GET /odoo/industry` diagnostic endpoint).
- `app/services/customer_group_sync_service.py` -- REWRITE total logic, mirror pola `SalesmanDivisionSyncService`:
  - `__init__`: tambah `self.odoo = OdooClient()`.
  - `sync()`: data diambil dari `self.odoo.get_industries(ids=odoo_ids)` (resolve dari `external_codes` kalau diisi), BUKAN lagi iterasi `CUSTOMER_GROUPS` constant. Raise `ValidationError` kalau tidak ada industry ditemukan (pola sama Salesman Division).
  - `EXTERNAL_CODE_PREFIX` diganti dari `"CBU-CUSTGROUP-"` -> **`"ODOO-CONTACT-INDUSTRY-"`** (format dikonfirmasi LANGSUNG oleh user), konsisten pola "ODOO-*" project (id Odoo jadi bagian key upsert, sama ODOO-SALESTEAM-/ODOO-COMPANY-/ODOO-PARTNER-).
  - `_parse_external_codes()`: sekarang parse ke id Odoo numerik (dulu parse ke "code" string FS/MT/GT/HORECA) -- pola sama `SalesmanDivisionSyncService._parse_external_codes()`.
  - `_to_esuite_payload()`: `external_code = f"{EXTERNAL_CODE_PREFIX}{industry['id']}"`, `name = industry['name']`. `basic_transaction.currency` TIDAK berubah (masih `CURRENCY` id PROD yang sudah difix sebelumnya).
  - `CUSTOMER_GROUPS` constant lama (4 grup FS/MT/GT/HORECA) DIPERTAHANKAN di kode (histori/referensi, TIDAK dihapus) TAPI TIDAK DIPAKAI LAGI oleh `sync()`.
- `app/api/routes/customer_group.py` -- docstring & `Query(external_codes=...)` description diupdate ke format & behavior baru.

**4 record lama (external_code prefix `CBU-CUSTGROUP-FS/MT/GT/HORECA`) yang sudah CONFIRMED ada di eSuite sejak 14 Agustus:** TIDAK disentuh/dihapus oleh perubahan ini (external_code beda -> eSuite anggap entity berbeda, upsert-by-external_code) -- jadi **ORPHAN** (tidak ke-update lagi lewat sync ini). User ditanya mau diapain (biarkan vs set inactive lewat 1 sync manual) -- **tidak dijawab eksplisit**, jadi default AMAN yang dipakai: **dibiarkan, TIDAK ada tindakan destruktif/deactivate otomatis dari kode.**

**⚠️ BELUM DIVERIFIKASI -- constraint parent "Customer Type" (dev WA note 26 Agustus):** payload baru ini TIDAK mengirim field `parent` (sama seperti versi lama). Kalau constraint "customer_group[] di Pricelist cuma bisa pilih grup yang parent-nya Customer Type" berlaku juga ke 18 group baru ini, mereka BELUM PASTI otomatis kepilihable di Pricelist tanpa `parent` diisi. **PENDING follow-up terpisah**, TIDAK memblokir push Customer Group itu sendiri.

**BELUM ditest live** -- next step: user panggil `POST /sync/customer-group` (Swagger), cek response eSuite & `GET /customergroup` balik buat verifikasi 18 record beneran tersimpan.

**Belum disentuh (tahap SELANJUTNYA, terpisah dari perubahan ini):** `customer_sync_service.py::_to_esuite_payload()` -- assign `customer_groups[]` ke tiap Customer berdasarkan `industry_id`-nya. Yang baru dibangun ini CUMA push entity Customer Group-nya (18 group), BELUM assign customer ke group manapun. Cardinality question (1 customer bisa >1 industry atau selalu 1?) juga masih belum terjawab.

## 🆕🆕🆕🆕 4 September 2026 (lanjutan) -- User bikin 6 rule baru: SSOT Customer Group direvisi total, hipotesis `industry_id`, rencana auto-mapping Customer->Customer Group

**Konteks:** setelah insiden `CUSTOMER_GROUP_ALL`, user jelaskan asal-usulnya: grup itu **dummy yang dia buat sendiri via UI eSuite**, dipakai sebagai catch-all karena dulu admin Odoo belum kasih mapping customer group yang tepat, jadi SEMUA customer sementara dimasukkan ke situ. Sekarang situasinya berubah -- user susun 6 rule baru:

1. **4 grup hardcode (FS/MT/GT/HORECA) sekarang berstatus ASUMSI, HANYA berlaku sandbox/DEV** -- belum tentu final utk PROD. **🆕 SEKARANG SUDAH RESOLVED sepenuhnya -- hardcode ini sudah TIDAK DIPAKAI LAGI, diganti data industry Odoo.**
2. **Istilah "Customer Category" (res.partner.category / Contact Tags) DIGANTI "Customer Label"** -- alasan user: sepertinya field ini cuma tag bebas yang ditambahkan admin Odoo, TIDAK benar-benar dipakai/representasikan Customer Group. Rename diterapkan konsisten di kode: `OdooClient.get_customer_categories()` -> `get_customer_labels()`, endpoint `GET /odoo/customer-category` -> `GET /odoo/customer-label`. **⚠️ Perubahan path API** -- endpoint lama sudah tidak ada, siapa pun/automation yang masih panggil path lama akan 404.
3. **Hipotesis (SEKARANG DIKONFIRMASI):** Customer Group yang dimaksud eDot memang merujuk ke **field standar Odoo `industry_id`** (model `res.partner`, relasi ke `res.partner.industry`, field UI "Industry") -- BUKAN `res.partner.category` (Contact Tags/"Customer Label" di atas).
4. **Endpoint BARU `GET /odoo/industry`** dibangun -- list mentah `res.partner.industry` (id, name), analog dgn `get_customer_labels()`/`GET /odoo/customer-label` lama.
5. **Mapping (SEKARANG DIIMPLEMENTASI):** Customer Group (eSuite) = Customer Industry (`res.partner.industry_id`), TAPI implementasinya BUKAN "assign existing group ke Customer" seperti rencana awal -- user putuskan pendekatan lebih sederhana: SEMUA industry Odoo langsung jadi Customer Group eSuite sendiri-sendiri (1:1), bukan di-assign ke 4 grup lama.
6. **Mapping internal parent/child -- SUPERSEDED (4 September 2026):** rencana asli (tabel translasi industry Odoo granular -> parent Customer Group umum, format manual `parent[id]`+`child[ids]`, sempat pending nunggu consult dev) **TIDAK JADI DIPAKAI** -- keputusan final: push SEMUA industry 1:1 jadi Customer Group sendiri, tanpa translasi/pengelompokan.

**BELUM DIPUTUSKAN / PENDING (SISA):**
- Cardinality: 1 customer bisa >1 industry atau selalu tepat 1? Menentukan struktur `customer_groups[]` di payload Customer nanti.
- Constraint parent "Customer Type" utk Pricelist -- PENDING follow-up terpisah.
- `customer_sync_service.py::_to_esuite_payload()` -- resolve & kirim `customer_groups[]` otomatis berdasarkan `industry_id` Customer -- **BELUM disentuh sama sekali sampai sekarang**.

## 🆕🆕🆕 4 September 2026 -- Customer Group currency.id: id DEV kepakai di PROD, SUDAH DIFIX

Bagian dari insiden lebih besar cutover eSuite dev->prod. Dev eDot konfirmasi LANGSUNG via WA (4 September) bahwa id currency DEV yang sama (`6a695cc1917e8fc836359505`) masih dipakai di payload Customer Group yang dikirim ke PROD -- SALAH, harusnya id PROD (`6a97ad0fba3a62f899d29060`), sama seperti bug yang lebih dulu ditemukan di payload Product.

**Fix diterapkan:** `customer_group_sync_service.py::CURRENCY` (baris 61) diganti ke id PROD, py_compile OK. Endpoint pre-flight BARU `GET /api/debug/verify-reference-constants` dibangun. **BELUM ditest live.** Status PAUSED soal duplikat record lama (CG-00001/CG-00002) TETAP berlaku terpisah, tidak terkait fix ini.

## 🆕🆕 31 Agustus 2026 -- KEPUTUSAN FINAL: gap join-key TIDAK dikejar dari kebutuhan order-history-import, alasan baru ditemukan

User klarifikasi lebih jauh soal makna field `salesman.external_code`: field itu SEHARUSNYA merepresentasikan **PIC (person in charge) order** -- sales yang ASLI closing order tsb (mapping ke `sale.order.user_id` Odoo) -- BUKAN soal siapa boleh lihat history (visibility sudah terbukti sama utk semua sales yang visit outlet, tidak butuh mapping apa pun).

Ditanya apakah user mau mulai bangun solusi mapping join-key, **user memilih TIDAK -- tetap pakai kode dummy/test tetap**. Alasan eksplisit, 2 lapis:
1. Blocker teknis lama: tim Odoo/CBU belum input data korelasi Odoo-salesperson <-> eSuite-employee_id di mana pun.
2. **Alasan tambahan BARU, PENTING:** SEKALIPUN korelasi itu diinput SEKARANG, **tidak ada histori "siapa sales yang closing order apa" di masa lalu** yang bisa dipakai backfill order-order LAMA. Jadi order-history-import (use-case backfill order lama) TIDAK AKAN PERNAH bisa dapat PIC akurat, walau join-key dibangun kapan pun.

**Konsekuensi:** gap join-key (blocker `SalesmanSyncService` individual & proposal auto-sync Customer->Salesperson) **TETAP TIDAK RESOLVED**, PENDING keputusan user kalau/ketika kebutuhan itu muncul.

## 🆕 28 Agustus 2026 -- Klarifikasi: 4 kode test salesman (order history import) BUKAN solusi untuk gap di bawah

Dev eDot kasih 4 `employee_id` test (`202600001` dummy/no-mobile-access, `202600002`/`3`/`4` real agent dgn akses mobile eWork) khusus buat masa development/testing app mereka. User konfirmasi order backfill TIDAK PERLU presisi map ke `sale.order.user_id` (Odoo salesperson asli) -- cukup 1 kode tetap dari salah satu 3 kode real, karena "siapapun sales yang visit outlet akan dapat order terakhir yang sama". **Ini SAMA SEKALI TIDAK menyelesaikan gap Odoo-salesperson<->eSuite-employee_id di bawah.**

## 🆕 27 Agustus 2026 -- `x_studio_sales_team` dicek, auto-sync Customer->Salesperson diinvestigasi, TERNYATA masih blocked oleh gap yang sama

User share screenshot Odoo Studio field editor + Contact form (Sales & Purchase tab), minta cross-check apakah field `x_studio_sales_team` sesuai buat "upsert sales team/sales division".

**Temuan field (dari screenshot, BUKAN asumsi):**
- `x_studio_sales_team` -- Model **Contact** (`res.partner`), Field Type **many2one**, Related Model **crm.team**, Label UI "Sales Team", Stored=Yes, Copied=Yes, Type "Custom Field". Ini field CUSTOM Odoo Studio, BUKAN field standar.
- Contoh data real: Contact "07 AM BAKERS CLUB" -- Salesperson = "[SALES] BAL FS04", Sales Team = "BALI FS AREA 2". Nama Sales Team ini KONSISTEN dengan nama `crm.team` yang sudah dipush ke Salesman Division.
- **PENTING -- field ini TIDAK dipakai & TIDAK dibutuhkan oleh push Salesman Division yang sudah ada.** `salesman_division_sync_service.py` query model `crm.team` LANGSUNG, sama sekali tidak lewat Contact/`x_studio_sales_team`.
- Fungsi field ini beda arah: dia ada di sisi **Customer**, isinya "Customer ini Sales Team-nya apa".

**Klarifikasi user soal arsitektur eSuite:** di Odoo, Customer -> Salesperson + Sales Team (2 field). Di eSuite, mapping Customer ada di `sales.branchs[]` + `sales.salesmans[]` (Branch + Salesman individual) -- **TIDAK ADA field mapping Customer langsung ke Salesman Division** di skema `/customers`. Salesman Division (`salesman_division[]`) baru muncul di skema **`POST /salesman`** (bikin akun Salesman individual), sebagai field di level akun Salesman itu sendiri -- BUKAN di level Customer, yang mana push-nya (`SalesmanSyncService`) MASIH DITUNDA.

**Keputusan operasional user (SEMENTARA):** Sales Team/Division di eSuite untuk SEMUA akun Salesman saat ini sengaja di-assign "All Division" (belum dikelompokkan per Sales Team asli) -- keputusan sementara sambil menunggu feedback tim sales yang mulai UAT app eWork. Bukan bug/gap teknis.

**Investigasi proposal user -- auto-sync Customer->Salesperson langsung dari Odoo, ganti proses manual `customer_sales_mapping_endpoint`:**

User observasi: semua Customer di Odoo SELALU punya Salesperson + Sales Team terisi (konsisten) -- muncul ide auto-push. **Dicek ke kode -- TERNYATA masih BLOCKED, root cause SAMA PERSIS dengan blocker Salesman individual lama:**
- `odoo_client.py::get_salespersons()` cuma expose field `id`/`name`/`login`/`email`/`active` -- **TIDAK ADA field yang menyimpan/berkorelasi dengan `employee_id` eSuite.**
- eSuite `employee_id` adalah kode BEBAS yang di-assign SAAT akun Salesman dibuat manual oleh dev via UI eSuite -- formatnya TIDAK ada hubungan dengan login/nama Odoo.
- **Kesimpulan: tidak ada "join key" antara Odoo Salesperson dan eSuite employee_id di mana pun di sistem sekarang.**
- **Supaya bisa auto-sync beneran, butuh salah satu dari:** (a) custom field BARU di Odoo (pola sama `x_studio_sales_team`) yang nyimpen `employee_id`/id eSuite per Salesperson; atau (b) tabel mapping eksternal yang di-maintain manual di bridge. **BELUM ada keputusan** (31 Agustus: DIKONFIRMASI TIDAK dibutuhkan dari sisi order-history-import).
- **Constraint tambahan:** environment eSuite MASIH SANDBOX -- mobile app eWork cuma bisa dipakai akun Salesman yang di-generate LANGSUNG oleh dev, BUKAN hasil upsert/push kita. Jadi walaupun auto-sync dibangun, belum bisa ditest end-to-end dari sisi app mobile sales.

## 🆕 18 Agustus 2026 -- Salesman Division: DIBANGUN & DICOMMIT, belum ditest live

**Temuan struktur Odoo CBU (dari screenshot user, BUKAN asumsi):**
- `crm.team` (Sales Team) = representasi WILAYAH/TERRITORY: "BALI FS AREA 1", "BALI GT AREA 1", "BALI MT AREA 1-4", "JKT MT", "JKT FS", "OUTER", "OFFICE", "ONLINE", "NKA", "Sales". Company = "Visible to all".
- Team Leader (mis. "Novanda Dwi Yuhastiko") = kelihatan kontak/orang asli.
- Members tiap team (mis. "[SALES] BAL FS01") = **BUKAN karyawan individual** -- cuma `res.users` polos, tanpa Employee link, email generik. **Dikonfirmasi user: "usernya bisa ganti-ganti tapi email ini tetap (seperti slot)"** -- artinya kode ini representasi SLOT/RUTE, bukan 1 orang tetap.

**Keputusan (18 Agustus 2026):**
1. Sales Team -> Salesman Division dipetakan 1:1, SEMUA active team dipush apa adanya -- tidak ada exclude.
2. Field `code` eSuite (wajib <=20 char, UPPERCASE+angka) di-generate OTOMATIS dari nama team.
3. TIDAK difilter company -- karena Sales Team Odoo CBU "Visible to all".

**Implementasi:** `odoo_client.py::get_sales_teams()`, `salesman_division_sync_service.py` (BARU, push ke `POST /salesman-division`, external_code prefix `"ODOO-SALESTEAM-{id}"`, `employees: []` sengaja kosong), `salesman_division.py` route BARU. **Status: kode sudah dicommit ke device, BELUM ditest live ke eSuite sandbox.**

## Salesman individual (per-orang) -- MASIH BLOCKED, sekarang ada bukti tambahan (SEKARANG DIJAWAB, lihat section paling atas file ini)

**🆕🆕 18 Agustus 2026 -- SKEMA RESMI Salesman/Salesman Division DIBACA LANGSUNG dari PDF (section 9.9/9.10):**

`POST /salesman` -- Required fields: `external_code` (Yes), `name` (Yes), `status` (No), `title` (Yes -- honorific), `employee_id` (Yes), `salesman_division` (Yes, Object), `department` (Yes, Object -- id master eSuite), `job_position` (Yes, Object -- id master eSuite), `branches` (Yes, Array<Object>).

Contoh payload real (27 Agustus, dari Postman collection):
```json
{
  "external_code": "PM-sm", "name": "PM SM", "title": "Mr.", "employee_id": "PM-EMP1",
  "status": "active", "department": {"id": "..."}, "job_position": {"id": "..."},
  "branches": [{"id": "..."}], "salesman_division": [{"id": "..."}]
}
```
`salesman_division` berupa ARRAY of object (bisa lebih dari 1 division per Salesman).

**KENAPA INI MASIH BLOCKED (bukti konkret dari Odoo CBU):**
1. Field `title`, `employee_id`, `department`, `job_position`, `identity_number`, `join_date`, `resign_date`, `tax_number` semua melekat ke SATU ORANG spesifik. **Dikonfirmasi 18 Agustus: akun "salesperson" di Odoo CBU adalah SLOT/RUTE (email tetap, orang bisa ganti-ganti)**, BUKAN identitas 1 karyawan tetap. Genuine MISMATCH model data.
2. Sheet "User" di template Go Live Excel (kolom Name/Username/Email/Phone/Password/External Employee ID/Branch) -- **KOSONG, cuma template header, tidak pernah diisi.**
3. `department` & `job_position` butuh id MASTER DATA milik eSuite sendiri -- belum ada endpoint GET buat pull master ini.
4. `employee_id` juga TIDAK ADA sumbernya dari Odoo (27 Agustus).

**PERTANYAAN BISNIS -- SUDAH DIJAWAB 17 September 2026, lihat section paling atas file ini.**

**KEPUTUSAN (18 Agustus 2026, tetap berlaku, DIKONFIRMASI ULANG 17 September): Build push `SalesmanSyncService` (individual) DITUNDA** -- bukan dibatalkan, tapi TIDAK dibangun blind dengan asumsi karena resikonya data Salesman salah/kosong tampil ke tim sales asli.

**🆕 21 Agustus 2026 -- Riset gitbook: cara bikin akun Salesman individual ternyata via UI, bukan cuma API.** Halaman gitbook "Cara Menambahkan Akun Salesman eWork di eSuite" jelasin flow: menu **Company User -> User Group management**, isi **name, username, email, phone, password, employee ID, branch**, lalu assign ke user group **"ework salesman"**. Field ini LEBIH SEDIKIT & BEDA dari skema `POST /salesman` PDF (tidak sebut title/department/job_position). Detail lengkap di `ESUITE_GITBOOK_NOTES.md` section 6 (device folder eDot).

**🆕 24 Agustus 2026 -- `GET /employee?employee_id=...` ditemukan.** Endpoint ini LOOKUP akun Salesman yang SUDAH ADA di eSuite (dipakai auto-resolve nama Salesman di endpoint mapping customer-sales), BEDA konteks dari blocker di atas (yang soal PUSH/CREATE akun baru).

- **Entity yang MASIH BELUM DIBANGUN (push-nya):** Salesman individual. Salesman Division SUDAH.

- **✅⚠️ Customer Group -- DIBANGUN 14 Agustus 2026, push CONFIRMED bekerja (dgn 4 hardcode lama), 4 September 2026 SUMBER DATA DIGANTI ke industry Odoo, belum ditest live versi baru. Duplikat record lama masih butuh keputusan user (PAUSED):**
  - **SUMBER DATA LAMA (14 Agustus - 4 September): 4 nama grup (FS/MT/GT/HORECA) BUKAN dari query Odoo** -- murni dari deskripsi bisnis user (14 Agustus), HARDCODED list. **Sekarang SUDAH TIDAK DIPAKAI SAMA SEKALI** -- diganti data industry Odoo real (18 record).
  - **Kandidat SSOT DIREVISI TOTAL, lalu DIKONFIRMASI:** `res.partner.category` DITURUNKAN jadi "Customer Label" (cuma tag bebas admin Odoo). SSOT yang DIKONFIRMASI: field standar Odoo `industry_id`.
  - **external_code SEKARANG pakai prefix `ODOO-CONTACT-INDUSTRY-{id}`** (diganti 4 September) -- prefix lama `CBU-CUSTGROUP-{CODE}` cuma dipakai 4 record lama yang sekarang orphan.
  - **✅ RESOLVED 14 Agustus 2026 (malam):** SEMUA 4 record LAMA ADA dan BENAR di eSuite: `CBU-CUSTGROUP-FS`, `-MT`, `-GT`, `-HORECA`. Status sekarang: orphan, dibiarkan.
  - **✅ Currency id:** benar untuk DEV 24 Agustus, SUDAH DIGANTI ke id PROD 4 September (`6a97ad0fba3a62f899d29060`), py_compile OK, BELUM ditest live. Field ini TIDAK ikut berubah lagi pas migrasi ke industry-based.
  - **🆕 TEMUAN (14 Agustus) -- KEMUNGKINAN DUPLIKAT, BUTUH KEPUTUSAN USER:** ada record LAMA "Modern Trade (MT)" (`code: CG-00002`) & "General Trade (GT)" (`code: CG-00001`) yang sudah ada SEBELUM push kita -- kemungkinan bukan seed data, dibuat manual sebelumnya.
  - **STATUS: PAUSED** -- keputusan: (a) cek ke admin CBU/vendor asal-usul 2 record lama itu; (b) pakai yang lama (perlu bantuan vendor assign external_code manual) atau hapus & pakai punya kita. **TIDAK memblokir Pricelist/Salesperson.** **17 September 2026: arah diperjelas -- pending sampai data sales masuk Odoo, bukan issue eDot, lihat section paling atas file ini.**
  - **🆕 26 Agustus 2026 -- dev eSuite WA note:** Customer Group built-in **TIDAK WAJIB dipilih** (cuma klasifikasi). **Constraint BARU:** utk `customer_group[]` di Pricelist, **HANYA BISA pilih customer group yang parent-nya "Customer Type"**. **⚠️ Belum diverifikasi apakah 18 group baru (industry-based) punya `parent` ini.** Contoh use-case lain: New Outlet Order (NOO) dari salesman auto-flag customer group `CG-00003` ("NOO") -- flow operasional internal eSuite.

- **🆕 KLARIFIKASI LANGSUNG DARI USER (16 Agustus 2026) -- Group vs Category:** "customer group itu sekelompok customer yang terafiliasi dalam suatu group.. contoh pepito canggu, pepito denpasar, pepito badung itu adalah 'pepito group' sedangkan FS/MT/GT/HORECA itu KATEGORI Industri dari customer" -- **PROVISIONAL**, STATUS TETAP PAUSED. SSOT Customer Group yang DIPAKAI SEKARANG (industry-based) beda konsep dari "grup afiliasi" (Pepito Group dst) -- kalau nanti butuh representasi "grup afiliasi" itu juga, itu kebutuhan TERPISAH, belum dibangun.

- **Payload `Customer` yang dikirim bridge sekarang MASIH minim di sync otomatis** -- field resmi `"price_list": {"id": ...}` dan `"sales": {"branchs": [...], "salesmans": [...]}` TIDAK PERNAH dikirim dari `POST /sync/customers` (sengaja, karena Odoo tidak punya sumber data assignment ini). **Task #4 SEKARANG LENGKAP via 2 endpoint mapping terpisah (manual/mass-assign, BUKAN otomatis dari Odoo):**
  1. `sales.branchs[]` + `sales.salesmans[]` -- `POST /api/mapping/customer-sales`. SELESAI 22-24 Agustus, BELUM ditest live dgn flow id-internal yang sudah diralat.
  2. `price_list.id` -- `POST /api/mapping/customer-pricelist`. BARU dibangun 26 Agustus 2026, BELUM ditest live.

  Kedua endpoint ini independen dan TIDAK butuh SalesmanSyncService individual (yang masih DITUNDA). **🆕 4 September 2026: endpoint mapping manual `POST /api/mapping/customer-grouping` juga masuk kategori ini** -- SEBELUMNYA satu-satunya cara set `customer_groups[]` Customer, KEMUNGKINAN akan digantikan auto-resolve dari `industry_id` begitu `customer_sync_service.py::_to_esuite_payload()` diubah (belum dikerjakan).

- **✅ KONFIRMASI BISNIS DARI USER (14 Agustus 2026) -- model pricing riil CBU, 2 dimensi:** Per Customer Group (FS/MT/GT/HORECA) DAN per PT/customer spesifik. Base price bukan harga final -- mekanisme harga lewat Pricelist assignment.

- **✅ KLARIFIKASI:** kategori Product yang namanya kayak nama PT (mis. "WAHANA INTERFOOD NUSANTARA PT") itu MEMANG DISENGAJA (representasi brand), bukan data kotor.

- **🆕 KLARIFIKASI LANGSUNG DARI USER (18 Agustus 2026) -- istilah "Outlet":** Dikonfirmasi: **"Outlet" yang muncul di eSuite mobile = Customer (`res.partner` dengan `customer_rank > 0`)** -- BUKAN entity terpisah.

- **KONFIRMASI PENTING dari chat grup vendor (13 Agustus 2026):** STOCK adalah syarat WAJIB produk muncul di app sales (dikonfirmasi admin vendor). "Kalau sudah termapping secara customer dan product itu sudah bisa muncul" -- customer mapping (salesman/pricelist/branch) JUGA syarat.

- **Status project (terakhir update 17 September 2026):** Customer Group sumber data diganti ke industry Odoo (18 record real), kode sudah dibangun & py_compile OK, belum ditest live -- arah pemakaiannya sekarang jelas: pending sampai data sales masuk Odoo. Duplikat record lama (CG-00001/CG-00002) tetap PAUSED, terpisah dari migrasi ini. Salesman Division selesai dibangun & dicommit, belum ditest live, sementara semua Salesman di-assign "All Division" (keputusan operasional, pending UAT sales). **Salesman individual (push akun baru) tetap DITUNDA** -- pertanyaan bisnis sudah dijawab 17 September (login per-orang, manual via UI, data karyawan belum ada di Odoo), tapi kesimpulannya justru memperkuat keputusan tunda. Task #4 (Customer -> Branch/Salesman/Pricelist) semua punya endpoint mapping -- branchs+salesmans & price_list lewat endpoint terpisah, customer_groups[] masih manual (auto-resolve dari industry_id belum dibangun). Proposal auto-sync Customer->Salesperson & gap join-key tidak diprioritaskan lagi sejak 31 Agustus.
</content>
