# Session Transfer Note v2 — Odoo → eSuite Bridge

> Dibuat 29 Juli 2026. Ini **menggantikan** catatan v1 sebelumnya — sudah mencakup semua keputusan di v1 + keputusan baru dari sesi diskusi lanjutan. Tempel file ini di awal chat baru supaya langsung nyambung, nggak perlu ulang dari nol.

---

## 1. Scope App (FIXED — sudah final)

App ini **murni bridge**: populasi data dari **Odoo 19 (SSOT)** ke **eSuite/eDOT** (platform sales operation pihak ketiga), satu arah (**push-only, Odoo → eSuite**). Tidak menangani sales dashboard untuk karyawan (itu di luar scope app ini / mungkin project terpisah nanti).

**Konsekuensi scope ini:**
- Tidak butuh JWT auth. Auth cukup API key statis (`verify_api_key`, header `x-api-key`) — karena pemanggil app ini cuma tim internal/Odoo (server-to-server / manual trigger), bukan banyak user manusia yang login lewat browser.
- `app.zip` versi lama (isinya endpoint `/customers`, `/products` read-only) itu murni eksperimen belajar, **sudah di-deprecate total**, tidak dipakai sebagai basis. Full rewrite dari nol diizinkan.

---

## 2. Trigger Sync (FIXED untuk fase awal)

- **Fase awal: manual.** User trigger 1 endpoint per entity secara sengaja (misal `POST /sync/product`), bukan otomatis/terjadwal.
- **Goal jangka panjang: real-time** (misal update stok di Odoo langsung reflect ke eSuite), tapi ini masih nunggu perkembangan aplikasi eSuite sendiri — belum digarap sekarang.
- **Desain endpoint: 1 endpoint per entity** (`POST /sync/branch`, `POST /sync/product`, dst — bukan endpoint generik `POST /sync/{entity}`).
  - **Alasan:** endpoint generik cuma mindahin kompleksitas jadi percabangan `if/elif` besar di 1 fungsi, bukan menghilangkannya. Dengan 1 endpoint per entity, tiap file gampang dibaca berdiri sendiri — cocok untuk belajar alur bertahap.
  - **Tapi** logic yang genuinely sama antar entity (signing, retry, request-id) tetap ditaruh di 1 shared function (`EsuiteClient.push()`), supaya nggak ada duplikasi. Jadi "generalize di level low-level client, bukan di level routing".
  - Refactor ke endpoint generik ditunda sampai ada minimal 2-3 entity yang kelihatan pola sama persis (rule of three) — user bercanda ini masuk "phase 10".

## 3. NOO Flow (New Outlet Opening dari sisi eSuite)

Dokumen eSuite mendeskripsikan alur di mana customer baru bisa dibuat dari sisi eSuite (field sales via eWork), lalu perlu di-*pull* balik ke client. **Ini bertentangan dengan Odoo sebagai SSOT.**

**Keputusan: TIDAK di-handle di fase awal.** Kemungkinan besar tidak di-handle sama sekali, atau ditangani di fase selanjutnya sebagai fitur terpisah. Odoo tetap SSOT penuh di fase awal — artinya bridge ini **benar-benar one-directional tanpa pengecualian** (push Odoo→eSuite saja, tidak ada pull-back apa pun, termasuk untuk NOO).

## 4. Kenapa Tetap Butuh Tabel "Reference Cache" di Postgres (meski Odoo SSOT)

Ini sempat bikin bingung karena kelihatan kontradiktif dengan prinsip SSOT — sudah diklarifikasi:

- Tabel ini **bukan** menyimpan data bisnis (nama, harga, stok) — itu semua tetap 100% real-time dari Odoo tiap kali sync, tidak ada duplikasi.
- Tabel ini isinya **cuma ID internal milik eSuite** untuk data referensi yang eSuite kelola sendiri dan sama sekali tidak ada relasinya ke Odoo — contoh: kode wilayah administratif Indonesia (province/city/district/sub_district), yang di payload eSuite direpresentasikan sebagai `{ "id": "<mongo-objectid-esuite>", "name": "JAWA BARAT", "code": "V32" }`. ID itu cuma bisa didapat dengan `GET /administrative-areas` ke eSuite — Odoo nggak mungkin tahu.
- Kalau tabel ini dihapus, **tidak ada data bisnis yang hilang** — tinggal di-generate ulang dengan pull ulang dari eSuite. Sifatnya murni "kamus terjemahan" ID pihak ketiga, bukan sumber data.
- Pendekatan: **lazy-fetch**, bukan pull besar-besaran di awal. Begitu butuh translate suatu value dan belum ada di cache, baru saat itu nembak eSuite pull endpoint & simpan. Beberapa entity (misal Branch) kemungkinan besar nggak butuh cache ini sama sekali.

## 5. Excel "eDOT Template Master Data Go Live" — statusnya

Belum dikonfirmasi apakah ini bagian dari alur teknis bridge, atau cuma dokumen sisi bisnis (form manual buat tim CS/implementation isi data awal langsung ke eSuite, terpisah dari sistem yang dibangun). User bilang kemungkinan **excel ini akan diisi manual** untuk sementara. **Kesimpulan: excel ini dianggap referensi untuk memahami field wajib eSuite, bukan sesuatu yang di-parsing otomatis oleh bridge** — kecuali ada info baru yang bilang sebaliknya.

## 6. Urutan Pengembangan Entity (belajar bertahap, 1 per 1)

User sengaja mau belajar proses satu-satu, bukan sekaligus. Urutan yang disepakati (dari paling sedikit dependency ke paling banyak):

1. **Branch** — paling flat, kemungkinan besar tanpa reference cache. Jadi validasi awal: signing HMAC, X-Request-ID, response parsing. **← SEDANG DIKERJAKAN, lihat status di bagian 8.**
2. **Product** (+ Product Category, Brand, UOM, UOM Level) — mulai kenalan reference-id (`product_type.id`, `uom.id`), masih 1 domain (inventory).
3. **Customer** — paling kompleks: reference data berjenjang (administrative_level), tax, currency; butuh Branch sudah ke-push duluan (customer refer ke `sales.branchs[].id`).
4. **Pricelist** — butuh Product & Customer Group sudah ada duluan (refer ke product/variant id & branch id eSuite). **Catatan penting:** fitur pricelist di Odoo sempat di-rollback sebelumnya karena `_get_product_price()` diblokir dari RPC eksternal (private method, dihapus di Odoo 16-17). Ini jadi blocker nyata untuk step 4 — perlu diselesaikan (Opsi A: custom Odoo addon wrapper — direkomendasikan; Opsi B: manual query `product.pricelist.item` — fragile) sebelum sampai ke tahap ini.
5. **Customer Group / Salesman** — pelengkap, pola mirip Branch.

## 7. Pertanyaan Terbuka: Mapping "Branch" eSuite ↔ Struktur Perusahaan di Odoo

Ini masih didiskusikan, **belum final**, tapi progress diskusinya penting untuk dilanjutkan:

**Fakta di Odoo:**
- Ada 4 badan usaha (`res.company`): 3 CV + 1 PT.
- Ada fitur inter-company transaction aktif → konfirmasi ini 4 entitas legal beneran terpisah (pembukuan/pajak sendiri-sendiri).
- **UPDATE TERBARU:** Dari 4 badan usaha itu, **hanya 2 yang benar-benar dipakai** untuk sales operation via eSuite/eDOT — 2 lainnya (agro & branch office) di luar kota, di luar scope aplikasi ini.
- **UPDATE TERBARU:** 2 badan usaha yang dipakai itu kemungkinan **1 gedung fisik yang sama** → kemungkinan besar cukup **1 warehouse, 1 company** secara operasional, meskipun secara legal Odoo tetap catat sebagai 2 `res.company` berbeda (untuk keperluan pembukuan/pajak masing-masing CV/PT).

**Insight kunci yang muncul dari diskusi (dari dokumen eSuite):**
Dokumen eSuite menyebut dedup key push itu `(X-Request-ID, entity, company)` — mengindikasikan eSuite punya konsep **"company"** di level tenant/akun, kemungkinan besar ditentukan oleh **kredensial (`client_id`/`client_secret`) yang dipakai saat request**, bukan field yang diisi manual di payload. Field "Branch" di eSuite sendiri sifatnya operasional (alamat, jam kerja, radius absensi salesman) — bukan entitas legal.

**Ini artinya ada 2 skenario arsitektur yang hasilnya beda jauh di kode:**
- **Skenario 1:** eSuite kasih 1 pasang kredensial mencakup semua operasional → kedua badan usaha yang dipakai cukup jadi 2 "Branch" berbeda di dalam 1 "company" eSuite. Config cukup 1 `ESUITE_CLIENT_ID`/`ESUITE_CLIENT_SECRET`. **(Skenario default/asumsi sementara, karena "1 gedung, kemungkinan 1 warehouse 1 company" makin memperkuat skenario ini jadi masuk akal.)**
- **Skenario 2:** eSuite kasih kredensial terpisah per badan usaha → butuh config berbentuk map `{company_id_odoo: {client_id, client_secret}}`, dan `EsuiteClient` perlu tahu badan usaha mana yang lagi di-push sebelum sign request.

**Belum terjawab, perlu dicek user ke tim eSuite:** apakah kredensial yang mereka punya itu 1 pasang atau beda-beda per badan usaha.

**Sumber data Odoo yang disarankan untuk Branch:** `stock.warehouse` (bukan `res.company` langsung) — karena representasi fisik depo/operasional lebih cocok dengan sifat data Branch di eSuite, dan tiap `stock.warehouse` tetap punya field `company_id` yang membawa info badan usaha pemiliknya kalau nanti dibutuhkan (skenario 2).

**Dengan update terbaru (2 BU dipakai, mungkin 1 gedung)** — kemungkinan besar setup akhirnya jadi lebih simpel dari perkiraan awal: mungkin cukup **1 Branch** kalau 2 badan usaha itu memang beroperasi sebagai 1 lokasi/1 gudang fisik secara sales-operasional, terlepas dari status legal terpisah di pembukuan Odoo. **Ini perlu dikonfirmasi eksplisit sebelum nulis `branch_sync_service.py`** — jangan diasumsikan sepihak oleh AI.

---

## 8. Progress Kode Saat Ini

Struktur project baru (rewrite total dari zip lama):

```
app/
├── main.py                        # BELUM dibuat
├── core/
│   ├── config.py                  # ✅ SUDAH — + ESUITE_BASE_URL, ESUITE_CLIENT_ID, ESUITE_CLIENT_SECRET
│   ├── exceptions.py              # ✅ SUDAH — + EsuiteAuthError, EsuiteDuplicateRequestError, EsuiteRPCError
│   └── security.py                # dari zip lama, dipertahankan apa adanya (verify_api_key)
├── clients/
│   ├── odoo_client.py             # dari zip lama, dipertahankan
│   └── esuite_client.py           # ✅ SUDAH — push()/pull() generik, HMAC-SHA256 signing
├── services/
│   └── branch_sync_service.py     # BELUM — nunggu klarifikasi poin 7 di atas
└── api/routes/
    └── branch.py                  # BELUM

app/schemas/                       # sengaja dikosongkan dulu, isi kalau kebutuhan Pydantic model jelas
```

**Detail penting `esuite_client.py` yang sudah ditulis (semua sudah lolos `python3 -m py_compile`):**
- `push(entity_path, event, data, request_id=None)` — POST, body di-`json.dumps` **sekali** lalu dipakai untuk sign & kirim (disiplin single-serialization, sesuai gotcha yang sudah diketahui sebelumnya).
- `pull(entity_path, page, limit)` — GET, sign string kosong.
- Auth header: `Basic base64(client_id:client_secret)`.
- Signature: `HMAC-SHA256(raw_body_bytes, key=client_secret)` → base64.
- Header lain: `X-Timestamp` (epoch), `X-Request-ID` (hex uuid4, di-generate otomatis kalau tidak dikasih — disiapkan supaya nanti retry bisa reuse ID yang sama, belum diimplementasi logic retry-nya).
- Response handling: 401 → `EsuiteAuthError`; 400 dengan pesan "already exists" → `EsuiteDuplicateRequestError` (dipetakan ke HTTP 409 di sisi bridge kita, bukan 400 apa adanya — supaya jelas ini bukan salah request si pemanggil); 400+ lainnya → `EsuiteRPCError`.

**Belum dikerjakan:**
- `branch_sync_service.py` + `api/routes/branch.py` — **diblokir oleh pertanyaan di poin 7.**
- `main.py` baru (registrasi router, exception handler — bisa dicontek dari pola `main.py` versi lama yang sudah punya handler untuk `AppError`, `HTTPException`, `RateLimitExceeded`).
- Tabel Postgres untuk reference cache (belum dibuat karena Branch kemungkinan nggak butuh — baru relevan mulai entity Product/Customer).
- Query di `OdooClient` untuk ambil data `stock.warehouse` (atau model lain, tergantung hasil klarifikasi poin 7).

---

## 9. Referensi Dokumen (sudah dibaca penuh, insight sudah diekstrak ke catatan ini)

- `eSuite_Synchronization_Document_v2_0_0.pdf` (39 halaman) — auth (§3), request format (§4), idempotency (§5), response format (§6), data limits (§7: max 5.000 record/request, all-or-nothing untuk `init`), entity index push/pull (§8), detail tiap entity push (§9), NOO flow (§12), changelog v1→v2 (§18).
- `eDOT_Template_Master_Data_Go_Live__Cahaya_Boga_Utama.xlsx` — 6 sheet: Basic Info, Branch, User, Customer, Product, Pricelist. Urutan sheet ini match dengan urutan dependency entity di dokumen eSuite.

---

## 10. Yang Perlu Dilakukan di Chat Baru (urutan langsung lanjut)

1. **Jawab pertanyaan poin 7** (konfirmasi ke tim eSuite: kredensial 1 pasang atau per-badan-usaha; dan konfirmasi apakah 2 BU yang dipakai itu memang 1 lokasi fisik / cukup 1 Branch).
2. Tulis `branch_sync_service.py` — ambil data dari Odoo (`stock.warehouse`, kemungkinan), bentuk payload sesuai spec §9.1, panggil `EsuiteClient.push()`.
3. Tulis `api/routes/branch.py` — `POST /sync/branch`, thin layer manggil service.
4. Update `main.py` — registrasi router baru + exception handler (bisa reuse pola dari versi lama).
5. Test end-to-end ke sandbox eSuite (butuh kredensial sandbox — pastikan sudah ada di `.env`: `ESUITE_BASE_URL`, `ESUITE_CLIENT_ID`, `ESUITE_CLIENT_SECRET`).
6. Lanjut entity berikutnya sesuai urutan poin 6 (Product).

---

**Cara pakai:** upload file ini di chat baru + source code yang sudah ada (`esuite_client.py`, `exceptions.py`, `config.py` — kalau perlu saya generate ulang filenya juga, tinggal minta), lalu lanjut dari poin 10 di atas.
