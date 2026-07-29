# Session Transfer Note — Odoo-eSuite Integration Project

> Catatan ini dibuat 29 Juli 2026, berdasarkan riwayat keputusan project + hasil cek langsung isi `app.7z` yang diupload. Tempel file ini di awal chat baru supaya Claude langsung punya konteks penuh.

---

## 1. Konteks & Tujuan Project

Membangun backend FastAPI sebagai **integration layer** antara:
- **Odoo 19** (single source of truth, diakses via JSON-RPC)
- **Aplikasi internal perusahaan** (dashboard sales — produk, customer, stock, pricing)
- **eSuite** (platform sales operations pihak ketiga)

Tujuan arsitektur utama: mengevaluasi eSuite sebagai aplikasi pendukung operasional tim sales, dengan FastAPI sebagai **bridge layer** antara Odoo dan eSuite.

**Stack:** Python, FastAPI, PostgreSQL, psycopg2, SQLAlchemy, bcrypt, PyJWT, slowapi, JSON-RPC, Docker, Git, VS Code.

**Preferensi kerja (penting untuk Claude di sesi baru):**
- Programmer berpengalaman (PHP/Laravel/MySQL/JS), tapi masih pemula di Python → jelaskan singkat kalau pakai sintaks Python yang kurang umum.
- Solusi praktis, production-ready, tidak overengineering.
- Untuk perubahan kode existing: **minimal invasive change**, jangan ubah flow/nama fungsi/style yang tidak relevan, tunjukkan bagian yang ditambah/diubah/dihapus dengan jelas.
- Build order: **bottom-up** — OdooClient method → service method → route → registrasi di `main.py`.
- Validasi `python3 -m py_compile` di tiap file yang diubah sebelum diserahkan.
- Komunikasi teknis dalam Bahasa Indonesia.

---

## 2. Kondisi Kode Saat Ini (hasil cek `app.7z`)

Struktur project saat ini:
```
app/
├── main.py
├── api/routes/
│   ├── customer.py      (GET /customers, GET /customers/search)
│   └── product.py       (GET /products, GET /products/search, GET /products/{id})
├── clients/
│   └── odoo_client.py   (JSON-RPC execute_kw wrapper)
├── core/
│   ├── config.py        (pydantic Settings: ODOO_*, API_KEY, CORS_ORIGINS)
│   ├── exceptions.py    (AppError + subclass: OdooConnectionError, OdooTimeoutError, OdooRPCError, ValidationError, NotFoundError)
│   ├── limiter.py        (slowapi Limiter, key_func=get_remote_address)
│   └── security.py       (verify_api_key — cek header x-api-key)
├── schemas/              (kosong)
└── services/
    ├── customer_service.py
    └── product_service.py
```

Pola yang dipakai konsisten: **route → service → client**, response format `{"data": ..., "meta": {...}}`, rate limit `20/minute` di semua route, exception handler global untuk `AppError`, `HTTPException`, dan `RateLimitExceeded` di `main.py`.

### ⚠️ Perlu diklarifikasi di chat baru
Riwayat sebelumnya menyebut sudah ada **sistem auth JWT lengkap** (access token + refresh token opaque di-hash SHA-256, bcrypt, credential store terpisah di PostgreSQL, rate limit login ketat). **Tapi di `app.7z` yang saya cek, auth yang aktif di `main.py` masih `verify_api_key` sederhana (header `x-api-key`) — tidak ada folder/file terkait JWT, model user, atau endpoint login/refresh sama sekali.**

Kemungkinan:
1. File JWT auth belum sempat digabung ke folder yang di-zip (ada di tempat lain), atau
2. Baru sebatas didesain/didiskusikan tapi belum diimplementasi ke codebase ini, atau
3. `app.7z` adalah snapshot lama sebelum auth JWT ditambahkan.

**→ Tanyakan ke user di awal chat baru mana yang benar**, supaya tidak salah asumsi soal state auth saat lanjut kerja.

---

## 3. Keputusan & Temuan Teknis Penting

### Odoo 19 RPC
- `read_group` mengembalikan field many2one sebagai tuple `[id, display_name]`.
- Key object di JSON-RPC selalu string → pakai `str(id)` untuk lookup.
- Method private (prefix `_`) diblokir dari RPC eksternal oleh security model Odoo — ini yang bikin fitur pricelist di-rollback (lihat bawah).
- Route ordering: pakai pattern `/resource/search` (bukan `/resource/{id}`) supaya tidak konflik dengan path parameterized.

### Pricelist (di-rollback)
- `product.pricelist.price_get()` sudah dihapus di Odoo 16–17.
- Penggantinya, `_get_product_price()`, diblokir dari RPC eksternal (private method).
- Dua opsi yang belum dieksekusi:
  - **Opsi A (direkomendasikan):** buat custom Odoo addon kecil yang expose public wrapper di sekitar `_get_product_price`.
  - **Opsi B:** query manual `product.pricelist.item` + resolve rule di sisi Python (lebih fragile, dihindari kalau bisa).

### Timezone
- Model SQLAlchemy pakai naive UTC datetime — hindari bug perbandingan timezone-aware vs naive.

### Exception handling
- Subclass `AppError` wajib punya handler eksplisit di `main.py`, kalau tidak akan silently jadi response 500.

### Bridge Odoo ↔ eSuite (dari analisis eSuite Synchronization Document v2.0.0)
- Model **inbound webhook pasif** di eSuite: push via POST, pull via GET.
- Request signing: **HMAC-SHA256** atas raw bytes, dengan disiplin **single-serialization** (JSON hanya di-serialize sekali sebelum sign — re-serialize akan merusak signature).
- Idempotency via header `X-Request-ID`.
- Batch limit **5.000 record per request**, sifatnya **all-or-nothing**.
- **Tidak ada async callback** dari eSuite → butuh polling kalau perlu status.
- Ada flow bidirectional untuk **NOO (New Outlet Opening)**.

### ✅ Keputusan terbaru: arah bridge
**Bridge dikonfirmasi one-directional: push saja dari Odoo → eSuite.** Tidak ada pull-back data transaksi dari eSuite ke Odoo untuk saat ini. Ini menyelesaikan open question sebelumnya soal strategi polling — polling untuk pull-back transaksi **tidak diperlukan** di scope saat ini (NOO flow yang bidirectional kemungkinan tetap perlu ditangani terpisah, perlu dikonfirmasi ulang apakah NOO termasuk pengecualian).

---

## 4. Yang Masih Perlu Dikerjakan (Backlog)

1. **Klarifikasi state auth JWT** (lihat poin ⚠️ di atas) sebelum lanjut kerja apa pun terkait auth.
2. Kalau JWT auth memang belum ada di codebase ini → perlu diimplementasi/diintegrasi ke `app.7z` yang sekarang (yang masih pakai `verify_api_key`).
3. Endpoint pembuatan user / seed script untuk credential store JWT.
4. Terapkan dependency `get_current_user` ke route customer & product yang sudah ada (saat ini masih pakai `verify_api_key` global di level `FastAPI(dependencies=[...])`).
5. Desain komponen bridge Odoo→eSuite:
   - Utility signing HMAC-SHA256 terpusat (dengan disiplin single-serialization).
   - Tabel mapping ID Odoo ↔ eSuite di Postgres.
   - Idempotency store (berbasis `X-Request-ID`).
   - Logic batching (limit 5.000 record, all-or-nothing).
   - Retry policy dengan `X-Request-ID` yang sama saat retry.
   - Klarifikasi ulang: apakah NOO flow butuh pull-back meskipun bridge utama one-directional.
6. Implementasi pricing pricelist — pilih Opsi A (custom Odoo addon wrapper) atau Opsi B (manual query, fallback).
7. `schemas/` masih kosong — perlu diisi kalau mau mulai pakai Pydantic response models yang lebih terstruktur (opsional, sesuaikan kebutuhan).

---

## 5. File Referensi di Project
- `eSuite_Synchronization_Document_v2_0_0.pdf` — dokumen sync eSuite v2.0.0 (sumber temuan di bagian 3).
- `eDOT_Template_Master_Data_Go_Live__Cahaya_Boga_Utama.xlsx` — template master data go-live (customer: Cahaya Boga Utama).
- `app.7z` — snapshot kode backend FastAPI terkini (struktur di bagian 2).

---

**Cara pakai catatan ini di chat baru:** upload ulang file ini (atau paste isinya) + `app.7z`/file project relevan lainnya, lalu langsung lanjutkan dari poin di bagian 4 (Backlog), dimulai dari klarifikasi state auth JWT.
