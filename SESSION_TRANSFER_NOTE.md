# Session Transfer Note v4 — Odoo → eSuite Bridge

> Dibuat 30 Juli 2026. **Menggantikan v3.** Update besar: kredensial sandbox real sudah didapat & terverifikasi live, ditemukan & diperbaiki kesalahan mapping entity (Branch vs Warehouse), Warehouse jadi entity baru. Tempel file ini di awal chat baru.

---

## 1. Scope App (FIXED)

App ini **murni bridge**: populasi data dari **Odoo 19 (SSOT)** ke **eSuite/eDOT**, satu arah (**push-only, Odoo → eSuite**), tanpa pengecualian (termasuk NOO flow — poin 3). Tidak menangani sales dashboard karyawan.

- Auth: API key statis (`verify_api_key`, header `x-api-key`). Tidak butuh JWT.
- `app.zip` eksperimen lama: deprecated total.
- `slowapi` & `CORSMiddleware`: sengaja dibuang dari `main.py` (tidak relevan untuk bridge internal-only).

## 2. Trigger Sync (FIXED untuk fase awal)

- **Manual**, 1 endpoint per entity (`POST /api/sync/branch`, `POST /api/sync/warehouse`, dst). Goal jangka panjang real-time, ditunda.
- Alasan endpoint per-entity (bukan generik `/sync/{entity}`): endpoint generik cuma mindahin kompleksitas jadi percabangan besar. Logic yang sama (signing, retry) di-share lewat `EsuiteClient`, bukan lewat routing. Refactor ke generik ditunda sampai 3+ entity berpola identik ("phase 10", becandaan user).

## 3. NOO Flow — Tidak di-handle di fase awal

Odoo tetap SSOT penuh, bridge one-directional tanpa pengecualian.

## 4. Reference Cache / ID Mapping — Kenapa Dibutuhkan (UPDATE PENTING)

**Temuan baru yang mengubah timeline:** ternyata **push ke eSuite TIDAK mengembalikan ID yang di-generate** (§6 dokumen: response push cuma `{"status":200,"message":"","data":"success"}`, tanpa ID). Dokumen eksplisit bilang *"reconcile via the pull (GET) endpoints"*.

Ini artinya pola "pull untuk resolve ID eSuite" **sudah dibutuhkan mulai entity Warehouse** (bukan baru mulai di Customer seperti dugaan awal). Warehouse butuh ID Branch yang di-generate eSuite untuk field `branches: [{id}]` — satu-satunya cara dapetin itu adalah `GET /branches` lalu cocokkan lewat `external_code` kita sendiri.

**Pendekatan saat ini (masih sengaja sederhana):** pull langsung on-the-fly tiap kali `/sync/warehouse` dipanggil (data dikit — cuma 2 Branch — jadi murah), **belum** disimpan ke tabel Postgres permanen. Cache Postgres beneran baru dibangun mulai entity **Customer**, di mana skalanya (reference wilayah administratif, ratusan/ribuan kombinasi) baru masuk akal untuk diotomatisasi & disimpan permanen.

Prinsip dasar tetap sama seperti sebelumnya: tabel ini **bukan** data bisnis (itu tetap 100% dari Odoo), cuma "kamus terjemahan" ID pihak ketiga.

## 5. Excel "eDOT Template Master Data Go Live" — statusnya

Belum dikonfirmasi bagian dari alur teknis atau cuma form manual sisi bisnis. Dianggap referensi field saja, bukan diparsing otomatis.

## 6. KOREKSI BESAR: Sumber Dokumen & Mapping Entity

### 6a. Prioritas dokumen — FIXED
**Postman collection (`eSuite-Webhook_postman_collection.json`) + environment (`eSuite-Webhook-DEV_postman_environment.json`) adalah sumber kebenaran di atas PDF**, karena PDF terbukti mengandung info yang sudah usang (base URL salah — lihat poin 7). PDF tetap dipakai untuk detail field/required-fields yang tidak ada di collection, tapi kalau bentrok, **collection menang**.

### 6b. Branch vs Warehouse — ternyata 2 entity terpisah, bukan 1

**Kesalahan yang sempat terjadi:** kode awal (v1-v3) memetakan `stock.warehouse` (Odoo) langsung ke endpoint `/branches` (eSuite). Ini salah — collection punya `POST /warehouse` yang terpisah dari `POST /branches`, dan `/warehouse` payload-nya punya field `branches: [{id: <esuite_branch_id>}]` — Warehouse **mereferensi** Branch, bukan Branch itu sendiri. Dikonfirmasi juga ada di PDF §9.11 (terlewat saat baca awal, cuma fokus di §9.1).

**Mapping yang benar sekarang:**
| Konsep eSuite | Sumber Odoo | Alasan |
|---|---|---|
| **Branch** (`/branches`) | `res.company` | Representasi lokasi/legal entity tingkat lebih tinggi (alamat, jam kerja) |
| **Warehouse** (`/warehouse`) | `stock.warehouse` | Representasi gudang fisik, referensi ke Branch via `branches[].id` |

**Konsekuensi:** `external_code` Branch berubah convention dari `ODOO-WH-*` → `ODOO-COMPANY-*`. 4 record lama (`ODOO-WH-1/3/5/6`) yang sempat ke-push minggu lalu (sebelum koreksi ini) sekarang "nyasar" di eSuite sandbox sebagai Branch yang salah kaprah — **dibiarkan saja** (sandbox, data buangan), tidak perlu dibersihkan.

## 7. URL & Kredensial — SUDAH DIDAPAT & TERVERIFIKASI LIVE

**PDF salah / usang.** PDF bilang sandbox = `https://openapistg.esuite.edot.id/v1/webhook` — ini **NXDOMAIN**, sempat didebug lama (dikira masalah DNS Docker/jaringan user, ternyata bukan — domain di dokumennya sendiri yang sudah tidak dipakai).

**URL & kredensial REAL** (dari `eSuite-Webhook-DEV_postman_environment.json`, dikirim tim eSuite 29 Juli 2026):
```
ESUITE_BASE_URL=https://openapi-esuite.edot-dev.com/v1/webhook
ESUITE_CLIENT_ID=6a6973780f67da70ae33824a
ESUITE_CLIENT_SECRET=Password123!
```
**Sudah dites `GET /health` → sukses (`status: 200`).** Sudah diisi di `.env` user, sudah dikonfirmasi sinyal signing (Basic Auth + HMAC) di `esuite_client.py` match dengan pre-request script Postman collection — tidak perlu diubah.

**Progres relasi dengan tim eSuite:** akses sandbox sudah dikasih 29 Juli 2026. **Sync teknis dijadwalkan Senin depan** dengan tim IT eSuite untuk bahas implementation flow — daftar pertanyaan sudah disiapkan (lihat poin 11).

## 8. Mapping "Branch" ↔ Struktur Perusahaan Odoo — SUDAH DIJAWAB SEBAGIAN

Nama 2 badan usaha in-scope (dari user, perlu divalidasi persis ke `res.company.name` di Odoo — kode pakai `ilike` biar toleran variasi format):
- **Cahaya Boga Utama** (CV)
- **Sunshine Food and Co** (CV)

Disimpan sebagai `IN_SCOPE_COMPANY_NAMES` di `core/scope.py` — single source of truth dipakai bareng oleh Branch & Warehouse service.

**Masih belum terjawab (bukan blocking lagi, tapi penting buat ditanya Senin):** apakah kredensial sandbox ini nanti di production tetap 1 pasang untuk kedua badan usaha, atau beda-beda? (Lihat daftar pertanyaan poin 11 no. 1-3.)

## 9. Urutan Pengembangan Entity

1. **Branch** — ✅ kode selesai (v4, source `res.company`). **Belum dites ulang** setelah koreksi mapping — TODO `ADMINISTRATIVE_AREA` di `branch_sync_service.py` masih kosong (province/city/district).
2. **Warehouse** — ✅ **BARU**, kode selesai. Belum pernah dites sama sekali (nunggu Branch sukses dulu, karena butuh pull ID Branch).
3. **Product** (+ Category, Brand, UOM, UOM Level) — belum dikerjakan.
4. **Customer** — belum. Di sinilah reference-cache Postgres beneran mulai dibangun.
5. **Pricelist** — belum. **Blocker belum selesai:** `_get_product_price()` diblokir RPC eksternal Odoo. Opsi A (custom addon wrapper, direkomendasikan) vs Opsi B (manual query, fragile).
6. **Customer Group / Salesman** — belum, pelengkap.

---

## 10. Progress Kode Saat Ini (`bridge_app_v3.zip` — nama file, isinya versi ke-4 iterasi)

```
app/
├── main.py                          # ✅ router branch + warehouse, exception handler
├── core/
│   ├── config.py                    # ✅ ODOO_*, ESUITE_BASE_URL/CLIENT_ID/CLIENT_SECRET, API_KEY
│   ├── exceptions.py                # ✅ + EsuiteConnectionError (nangkep DNS/timeout, bukan cuma HTTP error)
│   ├── scope.py                     # ✅ BARU — IN_SCOPE_COMPANY_NAMES
│   └── security.py                  # dari zip lama, tetap
├── clients/
│   ├── odoo_client.py               # ✅ get_companies(names) [Branch] + get_warehouses(company_ids) [Warehouse, scoped]
│   └── esuite_client.py             # ✅ push()/pull() + _safe_request() (nangkep ConnectionError/Timeout)
├── services/
│   ├── branch_sync_service.py       # ✅ source res.company, external_code=ODOO-COMPANY-{id}, TODO admin area
│   └── warehouse_sync_service.py    # ✅ BARU — pull /branches utk resolve ID, external_code=ODOO-WH-{id}
└── api/routes/
    ├── branch.py                    # ✅ POST /api/sync/branch?event=init|upsert
    └── warehouse.py                 # ✅ BARU — POST /api/sync/warehouse?event=init|upsert
```

Semua lolos `python3 -m py_compile`.

**Detail teknis penting:**
- `OdooClient.get_companies(names)`: domain `name ilike` (OR antar nama), fields `id, name, partner_id`.
- `OdooClient.get_warehouses(company_ids)`: domain `company_id in company_ids AND active=True`, fields `id, name, code, company_id`.
- `WarehouseSyncService._resolve_branch_ids()`: pull `GET /branches`, cocokkan `external_code` (dicek 2 kemungkinan lokasi field — top-level ATAU nested `basic_info.external_code`, karena dokumen nggak jelas soal ini untuk response GET — **perlu divalidasi begitu dites beneran**).
- Field Branch yang **belum** dimasukkan (sengaja, tunggu sandbox nolak dulu baru nambah sesuai errornya): `parent_branch`, `basic_info.sales_organization`, `basic_info.timezone`, `coverage`, `ework_setting`.

---

## 11. Daftar Pertanyaan untuk Sync Teknis Senin dengan Tim IT eSuite

**Arsitektur (paling penting):**
1. Kredensial sandbox ini — di production nanti 1 pasang untuk semua, atau beda per badan usaha?
2. Konsep "company" di eSuite (dedup key `X-Request-ID+entity+company`) — ditentukan dari kredensial yang dipakai, atau ada cara lain?
3. 2 badan usaha kami — perlu 2 Branch terpisah, atau cukup 1 kalau memang 1 lokasi fisik?

**Data & field:**
4. Field `parent_branch`, `basic_info.sales_organization/timezone`, `ework_setting` di Branch — wajib dari awal atau boleh nyusul?
5. Cara efisien dapetin kode wilayah administratif yang cocok buat lokasi kami — pull semua & cari manual, atau ada search by name?
6. Pricelist: beda `base_price` vs `store_price` itu apa? Per customer group atau general per branch?

**Flow & proses:**
7. NOO flow — wajib di-handle dari awal, atau boleh di-skip (Odoo tetap satu-satunya sumber customer di fase awal)?
8. Roadmap real-time sync — bakal ada webhook callback dari eSuite, atau tetap client yang polling?

**Operasional:**
9. Ada rate limit request per detik/menit yang perlu diperhatikan buat push batch besar?
10. Retry pakai `X-Request-ID` yang sama pas network timeout — aman? Ada window waktu tertentu?
11. Migrasi sandbox → production — perlu push ulang semua dari nol, atau ada mekanisme migrasi?

**(Baru, dari sesi ini) Soal response GET:**
12. Struktur response `GET /branches` (dan entity lain) — field `external_code` itu di top-level record atau nested di dalam objek tertentu (mis. `basic_info`)? Ini nentuin cara kita cocokkan record pull-back ke data Odoo kami.

---

## 12. TODO Sebelum Test Ulang ke Sandbox

1. **Isi `ADMINISTRATIVE_AREA`** di `branch_sync_service.py` (province/city/district — 3 baris kosong).
2. **Test `POST /api/sync/branch?event=upsert`** dengan kode v4 (source sudah `res.company`, bukan `stock.warehouse` lagi).
3. **Test `POST /api/sync/warehouse?event=upsert`** setelah Branch sukses — perhatikan apakah `_resolve_branch_ids()` berhasil cocokkan `external_code` dari hasil pull (poin 10, bagian yang masih perlu divalidasi).
4. Kalau ada error field/format dari eSuite, kirim response mentahnya — field opsional (`parent_branch`, dll) ditambah sesuai kebutuhan nyata, bukan ditebak.
5. Siapkan diri untuk sync Senin (poin 11) — bisa dibawa juga ke tim eSuite langsung sebagai agenda.

---

## 13. Referensi Dokumen

- `eSuite_Synchronization_Document_v2_0_0.pdf` (39 halaman) — **prioritas di bawah collection**, dipakai untuk detail field & required-fields table.
- `eSuite-Webhook_postman_collection.json` + `eSuite-Webhook-DEV_postman_environment.json` — **prioritas utama**, sumber base_url, kredensial, & contoh payload yang sudah tervalidasi HMAC signing-nya (pre-request script-nya jadi acuan `esuite_client.py`).
- `eDOT_Template_Master_Data_Go_Live__Cahaya_Boga_Utama.xlsx` — referensi field, bukan diparsing otomatis.

---

## 14. Yang Perlu Dilakukan di Chat Baru (urutan langsung lanjut)

1. Selesaikan TODO poin 12 di atas (isi kode wilayah, test Branch, test Warehouse).
2. Kalau Branch & Warehouse sukses mulus, lanjut entity **Product**.
3. Sebelum/sesudah sync Senin dengan tim eSuite, update catatan ini lagi dengan jawaban dari poin 11.

---

**Cara pakai:** upload file ini + `bridge_app_v3.zip` (kode terbaru, sudah termasuk fix Branch/Warehouse) di chat baru, lalu lanjut dari poin 14.
