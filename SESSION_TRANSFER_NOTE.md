# Session Transfer Note v3 — Odoo → eSuite Bridge

> Dibuat 29 Juli 2026. Ini **menggantikan** catatan v2 sebelumnya — sudah mencakup semua keputusan v1+v2 + progress kode terbaru (entity Branch selesai ditulis, siap dites). Tempel file ini di awal chat baru supaya langsung nyambung.

---

## 1. Scope App (FIXED)

App ini **murni bridge**: populasi data dari **Odoo 19 (SSOT)** ke **eSuite/eDOT**, satu arah (**push-only, Odoo → eSuite**), tanpa pengecualian (termasuk NOO flow — lihat poin 3). Tidak menangani sales dashboard karyawan (di luar scope / project terpisah nanti).

**Konsekuensi:**
- Auth: cukup API key statis (`verify_api_key`, header `x-api-key`). Tidak butuh JWT — karena pemanggil cuma tim internal (manual trigger), bukan banyak user manusia login browser.
- `app.zip` versi eksperimen lama (endpoint `/customers`, `/products` read-only) **sudah di-deprecate total**, sudah tidak dipakai sebagai basis kode.
- `slowapi` (rate limiter) & `CORSMiddleware` **sengaja dibuang** dari `main.py` baru — relevan untuk API publik yang diakses banyak client browser, tidak relevan untuk bridge yang dipanggil manual oleh tim internal via Postman/curl. Bisa ditambah lagi kalau kebutuhan berubah.

## 2. Trigger Sync (FIXED untuk fase awal)

- **Manual** — user trigger 1 endpoint per entity secara sengaja (`POST /sync/branch`, dst). Goal jangka panjang real-time, tapi ditunda sampai eSuite makin matang.
- **Desain endpoint: 1 endpoint per entity**, bukan endpoint generik `POST /sync/{entity}`. Alasan: endpoint generik cuma mindahin kompleksitas jadi percabangan besar, bukan menghilangkannya; per-entity lebih gampang dibaca & cocok untuk belajar bertahap. Logic yang genuinely sama (signing, retry) tetap di-share lewat `EsuiteClient`, bukan lewat routing generik. Refactor ke generik ditunda sampai ada 3+ entity dengan pola identik (rule of three) — becanda masuk "phase 10".

## 3. NOO Flow (customer baru dari sisi eSuite)

**Tidak di-handle di fase awal.** Odoo tetap SSOT penuh — bridge benar-benar one-directional tanpa pengecualian apa pun.

## 4. Kenapa Tetap Ada "Reference Cache" Meski Odoo SSOT

Tabel ini **bukan** data bisnis (itu tetap 100% dari Odoo real-time). Isinya cuma ID/kode internal milik eSuite untuk data referensi yang mereka kelola sendiri dan sama sekali nggak ada relasinya ke Odoo — contoh: kode wilayah administratif (`{ "id": "...", "name": "JAWA BARAT", "code": "V32" }`, dari `GET /administrative-areas`). Kalau tabelnya hilang, tidak ada data bisnis yang hilang — tinggal pull ulang. Pendekatan: **lazy-fetch**, bukan pull besar di awal.

**Koreksi dari catatan sebelumnya:** awalnya dikira cuma Customer yang butuh kode wilayah administratif ini — ternyata **Branch juga butuh** (field `address.province/city/district` di payload Branch juga pakai format kode eSuite yang sama). Keputusan praktis: untuk Branch (cuma 1-2 record, lokasi jarang berubah), kode wilayah **diisi manual sekali** di konstanta (`ADMINISTRATIVE_AREA` di `branch_sync_service.py`), **bukan** dibangun sistem pull+cache otomatis. Sistem pull+cache beneran baru dibangun mulai entity **Customer**, karena di situ skalanya (banyak record, alamat variatif) baru masuk akal untuk diotomatisasi.

## 5. Excel "eDOT Template Master Data Go Live" — statusnya

Belum dikonfirmasi apakah bagian dari alur teknis bridge atau cuma form manual sisi bisnis (diisi manual sementara). **Dianggap referensi field wajib eSuite saja, bukan di-parsing otomatis oleh bridge**, kecuali ada info baru.

## 6. Urutan Pengembangan Entity

1. **Branch** — ✅ **SUDAH SELESAI DITULIS**, lihat detail di poin 8. Belum dites ke sandbox (masih ada TODO, lihat poin 9).
2. **Product** (+ Category, Brand, UOM, UOM Level) — **BERIKUTNYA**. Mulai kenalan reference-id (`product_type.id`, `uom.id`), masih 1 domain (inventory).
3. **Customer** — paling kompleks (administrative_level berjenjang, tax, currency); butuh Branch sudah ke-push duluan. **Di sinilah sistem reference-cache otomatis (Postgres) mulai dibangun beneran.**
4. **Pricelist** — butuh Product & Customer Group duluan. **Blocker belum selesai:** fitur pricelist Odoo di-rollback sebelumnya karena `_get_product_price()` diblokir RPC eksternal. Perlu Opsi A (custom Odoo addon wrapper, direkomendasikan) atau Opsi B (manual query `product.pricelist.item`, fragile) sebelum sampai tahap ini.
5. **Customer Group / Salesman** — pelengkap, pola mirip Branch.

## 7. Mapping "Branch" eSuite ↔ Struktur Perusahaan Odoo — Status: ASUMSI SEMENTARA, JALAN TERUS

Belum ada konfirmasi final dari tim eSuite. **Keputusan: lanjut pakai asumsi paling sederhana dulu (Skenario 1) daripada macet nunggu**, dengan risiko perubahan kecil kalau ternyata salah.

**Fakta di Odoo:** 4 `res.company` (3 CV + 1 PT), inter-company transaction aktif → 4 entitas legal beneran terpisah. Tapi **cuma 2 badan usaha yang dipakai** untuk sales operation via eSuite (2 lainnya: agro & branch office luar kota, di luar scope). 2 badan usaha yang dipakai itu **kemungkinan 1 gedung fisik yang sama**.

**Insight dari dokumen eSuite:** dedup key push itu `(X-Request-ID, entity, company)` → eSuite punya konsep "company" di level tenant/akun, kemungkinan ditentukan oleh kredensial (`client_id`/`client_secret`) yang dipakai, bukan field di payload. "Branch" di eSuite sifatnya operasional (alamat, jam kerja, radius absensi), bukan entitas legal.

**Skenario 1 (ASUMSI YANG DIPAKAI SEKARANG):** 1 pasang kredensial eSuite mencakup semua. Config cukup 1 `ESUITE_CLIENT_ID`/`SECRET` (sudah begini di `config.py`). Karena 2 badan usaha = kemungkinan 1 gedung, `get_warehouses()` di `OdooClient` akan me-return apa adanya jumlah `stock.warehouse` aktif yang ada — **belum dipaksa jadi 1**, biar apa adanya sesuai data Odoo asli, gampang dites langsung ke sandbox untuk lihat hasil sebenarnya.

**Skenario 2 (kalau ternyata salah):** eSuite kasih kredensial terpisah per badan usaha → config perlu jadi map `{company_id_odoo: {client_id, client_secret}}`, dan `EsuiteClient` perlu tahu badan usaha mana yang di-push sebelum sign request. **Perubahan yang dibutuhkan kalau ini terjadi:** `core/config.py` (struktur kredensial), `clients/esuite_client.py` (constructor terima client_id/secret per-call, bukan fix di `__init__`), `services/branch_sync_service.py` (grouping warehouse per company sebelum push).

**Belum terjawab — perlu dicek user ke tim eSuite kapan pun sempat:** 1 kredensial atau per-badan-usaha? Ini nggak lagi blocking (sudah jalan dengan asumsi), tapi penting dikonfirmasi sebelum go-live beneran.

---

## 8. Progress Kode Saat Ini

Struktur project (rewrite total dari zip eksperimen lama, sudah dipaketkan sebagai `bridge_app_v1.zip`):

```
app/
├── main.py                        # ✅ SELESAI — router branch + exception handler AppError/HTTPException
├── core/
│   ├── config.py                  # ✅ SELESAI — ODOO_*, ESUITE_BASE_URL/CLIENT_ID/CLIENT_SECRET, API_KEY
│   ├── exceptions.py              # ✅ SELESAI — AppError + Odoo(Connection/Timeout/RPC)Error + Esuite(Auth/DuplicateRequest/RPC)Error + Validation/NotFound
│   └── security.py                # dari zip lama, dipertahankan apa adanya (verify_api_key, x-api-key header)
├── clients/
│   ├── odoo_client.py             # ✅ SELESAI — ditulis ULANG bersih, cuma get_warehouses() & get_partner_address()
│   └── esuite_client.py           # ✅ SELESAI — push()/pull() generik, HMAC-SHA256 signing
├── services/
│   └── branch_sync_service.py     # ✅ SELESAI — ada TODO (lihat poin 9)
└── api/routes/
    └── branch.py                  # ✅ SELESAI — POST /api/sync/branch?event=init|upsert

app/schemas/                       # masih sengaja kosong
```

Semua file sudah lolos `python3 -m py_compile`.

**Detail teknis yang perlu diingat:**
- `OdooClient.get_warehouses()`: query `stock.warehouse`, `domain=[("active","=",True)]`, fields `id, name, code, partner_id, company_id`. `company_id` di-fetch tapi **belum dipakai** di payload — disiapkan untuk Skenario 2 di poin 7 kalau nanti dibutuhkan.
- `OdooClient.get_partner_address()`: query `res.partner` via `read`, fields `street, zip, partner_latitude, partner_longitude`.
- `BranchSyncService._to_esuite_payload()`: bentuk payload sesuai spec §9.1 (`name`, `status`, `basic_info.external_code`, `address`). **Field opsional di spec yang BELUM dimasukkan** (sengaja, biar nggak nebak-nebak): `parent_branch`, `basic_info.sales_organization`, `basic_info.timezone`, `coverage`, `ework_setting`. Kalau sandbox nolak karena butuh field ini, baru ditambah sesuai pesan error asli, bukan ditebak di depan.
- `external_code` convention: `f"ODOO-WH-{warehouse['id']}"`.
- `EsuiteClient`: `push()`/`pull()` generik, HMAC-SHA256 atas raw body (single-serialization: `json.dumps` sekali, dipakai untuk sign & kirim), Basic Auth (`client_id:client_secret`), `X-Timestamp`, `X-Request-ID` (uuid4 hex, bisa direuse untuk retry — logic retry belum diimplementasi). Response handling: 401→`EsuiteAuthError`, 400 "already exists"→`EsuiteDuplicateRequestError` (dipetakan ke HTTP 409 di sisi bridge kita), 400+ lainnya→`EsuiteRPCError`.

---

## 9. TODO Sebelum `/sync/branch` Bisa Dites ke Sandbox

1. **Isi `ADMINISTRATIVE_AREA` di `branch_sync_service.py`** (3 baris kosong: `province`, `city`, `district`, masing-masing `name` + `code`). Cara dapetin: panggil `GET /administrative-areas` ke eSuite sandbox (Postman), cari baris yang cocok alamat gedung asli, copy persis.
2. **Isi `.env`**: `ESUITE_BASE_URL` (sandbox ID: `https://openapistg.esuite.edot.id/v1/webhook`), `ESUITE_CLIENT_ID`, `ESUITE_CLIENT_SECRET` (dari tim eSuite), plus `ODOO_BASE_URL`, `ODOO_DB`, `ODOO_UID`, `ODOO_API_KEY`, `API_KEY` (punya sendiri, bukan dari eSuite).
3. Setelah dites: kalau eSuite balikin error minta field tambahan (`parent_branch`, dll — lihat poin 8), tambahkan sesuai pesan error asli.
4. (Nggak blocking, tapi baik dicek kapan-kapan) Konfirmasi ke tim eSuite soal poin 7 — 1 kredensial atau per-badan-usaha.

---

## 10. Referensi Dokumen (sudah dibaca penuh)

- `eSuite_Synchronization_Document_v2_0_0.pdf` (39 halaman) — auth §3, request format §4, idempotency §5, response format §6, data limits §7 (max 5.000 record/request, `init` all-or-nothing), entity index §8, detail entity §9, NOO flow §12, changelog §18.
- `eDOT_Template_Master_Data_Go_Live__Cahaya_Boga_Utama.xlsx` — 6 sheet (Basic Info, Branch, User, Customer, Product, Pricelist), urutan match dependency entity eSuite.

---

## 11. Yang Perlu Dilakukan di Chat Baru (urutan langsung lanjut)

1. Selesaikan 4 TODO di poin 9 (isi kode wilayah, isi `.env`, siap-siap sesuaikan field kalau sandbox nolak).
2. Test `POST /api/sync/branch?event=init` ke sandbox. Bawa `bridge_app_v1.zip` supaya Claude di chat baru bisa langsung lihat kode aktual, bukan cuma deskripsi.
3. Kalau Branch sudah jalan mulus, lanjut entity **Product** — mulai kenalan konsep reference-id (`product_type.id`, `uom.id`) yang butuh pull dari eSuite (`/product-type`, `/uom`, dst.) — ini kandidat pertama untuk mulai bangun tabel reference cache Postgres beneran.

---

**Cara pakai:** upload file ini + `bridge_app_v1.zip` (atau ZIP terbaru kalau sudah ada perubahan) di chat baru, lalu lanjut dari poin 11.
