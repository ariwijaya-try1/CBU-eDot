# Session Transfer Note v8 — Odoo → eSuite Bridge

> Dibuat 6 Agustus 2026. **Menggantikan v7.** Update sesi ini: (1) fix docstring salah di `branch.py` (nyebut `stock.warehouse`, seharusnya `res.company`), (2) `cost` di payload direvisi jadi eksplisit `0` -- **UI eSuite tetap tidak 0**. Postman collection dicek: `cost` field VALID & terdokumentasi resmi (bukan computed). Dugaan sekarang: kemungkinan bug backend eSuite yang treat `0` sebagai falsy (skip update). **Perlu 1 test manual dari user (kirim `cost: 1` langsung via Swagger) sebelum lanjut ubah kode** -- lihat poin 7c. (3) Info baru dari vendor (belum divalidasi): produk tidak bisa hard-delete, cuma inactive; `uom_levels` di payload `/product` butuh field `id` tambahan yang belum kita kirim -- kemungkinan terkait pola "upsert sukses tapi ada anomali data" yang juga kelihatan di kasus `cost`. Lihat poin 7d. Mulai sesi ini, **file ini + Postman collection dibundle di dalam zip kode**, sejajar `app/` dan `CONFIG_NOTES.md`.
>
> **PENTING:** ada file kedua yang WAJIB dibaca bareng ini: **`CONFIG_NOTES.md`**. File itu isinya aturan bisnis & konfigurasi PERMANEN (filter Saleable, currency, UOM, dll) yang beda fungsi dari catatan sesi ini -- jangan diskip.

---

## 1. Scope App (FIXED)

Bridge murni: **Odoo 19 (SSOT) → eSuite/eDOT**, satu arah (push-only), tanpa pengecualian. Auth: API key statis. Tidak pakai JWT, slowapi, CORS.

## 2. Trigger Sync (FIXED)

Manual, 1 endpoint per entity. Response tiap endpoint selalu include `payload_sent` (data lengkap yang dikirim ke eSuite).

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
| Product (`/product`) | `product.product` | ✅✅ Filter tervalidasi (1247 produk, 5 Agustus). 🟡 `cost` dikirim eksplisit 0 tapi **UI eSuite masih nampilin nominal (bukan bug kode kita)** -- dugaan computed di sisi eSuite, belum dikonfirmasi. **Belum bisa dianggap selesai**, lihat poin 7c/9. |
| Customer | `res.partner`, filter `customer_rank > 0` + `active=True` | 🟡 `entity_type` fix + batching (default 1000/batch) sudah diterapkan (11 Agustus 2026). Full push 3038 record sukses (delay awal cuma soal async processing eSuite, sudah beres). Belum dianggap "selesai" penuh karena belum ada reconciliation test end-to-end. |
| Pricelist | — | Belum, blocker RPC Odoo masih ada |
| Customer Group / Salesman | — | Belum |

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

0. **[⚠️ ROOT CAUSE `cost` TERISOLASI 12 Agustus 2026 -- `uom_levels` sudah terbukti benar, `cost` masih gagal sendiri]** Test manual (Level id "Low" valid) terbukti berhasil update `uom_levels` (dikonfirmasi via `GET /product`), tapi `cost` tetap `0`, bukan nilai yang dikirim. Jadi bug sekarang murni soal `cost`, bukan lagi `uom_levels[].id`. **Belum ada root cause/fix** -- next step tergantung jawaban vendor. Detail di `CONFIG_NOTES.md`.
0e. **[BARU, BELUM DILAPORKAN]** Produk BARU (`ODOO-PROD-18374-test`) gagal tersimpan TOTAL (tidak ada di `GET /product` sama sekali, walau response 200) -- bug terpisah dari poin 0, belum ada dugaan penyebab.
0f. **[🚨 PRIORITAS BISNIS, BUKAN CUMA TEKNIS]** 1138/1250 produk (91%) di eSuite masih tampilkan `cost` asli (belum ke-mask) -- kontradiksi instruksi awal "cost tidak boleh disclose". Perlu di-flag ke tim/atasan soal timeline go-live, independen dari kapan bug teknis `cost` API selesai.
0b. **[✅ SELESAI 11 Agustus 2026]** Bulk upsert Customer (3038 record, batch_size=500) -- UI dashboard sempat cuma nunjukin 2002 pas awal dicek. **Dikonfirmasi vendor: eSuite proses upsert secara asynchronous** (response 200 = diterima ke antrian, bukan langsung tersimpan; worker proses belakangan). Bukan bug -- cuma delay pemrosesan. Semua 3038 sudah masuk sekarang. **Insight buat ke depan:** response 200 dari eSuite endpoint manapun tidak bisa langsung dianggap final buat volume besar -- kasih jeda / retry pull kalau perlu verifikasi cepat.
0c. **[✅ FIX DITERAPKAN 11 Agustus 2026]** Root cause gagal upsert Customer (beda dari 0b -- ini soal payload, bukan volume): field `entity_type: "customer"` wajib, sebelumnya tidak dikirim. Dikonfirmasi resmi lewat revisi payload vendor. Sudah ditambahkan ke `customer_sync_service.py`.
0d. **[✅ DITERAPKAN 11 Agustus 2026]** Push Customer sekarang selalu per-batch (default 1000/batch, bisa di-override lewat query param `batch_size`) -- root cause 502 di atas ~2000 record dalam 1 request dikonfirmasi user. Gagal di 1 batch tidak menggagalkan batch lain.
1. **[PALING PRIORITAS, lihat poin 0]** Root cause `cost` API sekarang terisolasi (bukan lagi soal `uom_levels`). Perlu lapor ke vendor dengan bukti konkret: payload lengkap test (Level id "Low" valid, `cost: 13344`) + hasil `GET /product` yang nunjukin `uom_levels` berhasil tapi `cost` tetap `0`. Tunggu jawaban vendor soal ini sebelum ubah kode.
1b. Tanya IT eSuite tetap jalan paralel (bukan blocking): apa cara resmi clear field numerik ke 0 (kalau nanti dijawab, ganti `1` -> `0` & re-push ulang lagi). Juga masih pending: update `cost` ke `0` gagal lewat endpoint API tapi berhasil lewat UI dashboard (lihat `CONFIG_NOTES.md` Tahap 7) -- kemungkinan root cause sama dengan poin 0.
2. Setelah root cause dikonfirmasi & fix yang benar ketemu: **re-push semua produk yang sempat ke-upsert dengan payload lama** (cost dihapus total / cost 0 yang ternyata belum fix) supaya konsisten.
2c. **[MENUNGGU USER]** Tunggu hasil validasi user soal "produk tidak bisa hard-delete, cuma inactive" -- belum ada aksi kode sampai dikonfirmasi. Lihat poin 7d.
3. Flag ke tim data produk soal `base_price: 1` sebelum go-live (non-coding, lihat `CONFIG_NOTES.md`).
4. **Customer** -- source model (`res.partner`), `entity_type` fix, & batching sudah selesai (lihat 0b/0c/0d). Belum ada full end-to-end reconciliation test (pull balik semua & diff external_code) -- opsional, cuma kalau ada indikasi masalah lagi.
5. **Blocker Stock Matrix vs `/product-variant`** -- no-variant sudah final, cara teknis nyambungin Stock Matrix masih belum jelas. Belum sekarang.
6. Update `CONFIG_NOTES.md` tiap ada aturan bisnis baru -- terpisah dari session transfer note.

## 13. Daftar Pertanyaan Sync dengan Tim IT eSuite

(Belum berubah -- lihat isi lengkap di v6/v7 kalau perlu.) Field opsional Branch, cara efisien dapetin kode wilayah administratif, beda `base_price`/`store_price` di Pricelist, NOO flow wajib/opsional, roadmap webhook vs polling, rate limit, retry safety, migrasi sandbox->production, field `parent` di Product Category/Brand.
**Baru, TERKONFIRMASI perlu ditanyakan (prioritas tinggi):** falsy-skip bug `cost` sudah dibuktikan lewat test manual (`cost: 1` -> UI jadi Rp 1; `cost: 0` -> UI tidak berubah). Tanyakan ke IT eSuite: apa cara resmi buat clear field `cost` ke 0 lewat API upsert (konvensi `null`? field terpisah buat "clear"? atau memang bug backend mereka yang perlu di-fix)?

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

1. **[BARU, PALING PRIORITAS]** Re-test fix `uom_levels[].id` lewat bridge: `/sync/product?limit=5` dulu, lalu `GET /product` verifikasi `uom_levels` terisi Level "Low" utk produk yg baru di-push (bukan cuma test manual). Kalau sukses, lanjut ke batch lebih besar.
2. Tetap tunggu jawaban vendor soal `cost` (lihat poin 13, pertanyaan sudah dikirim) -- independen dari poin 1, tidak saling blocking.
3. **[BARU]** Test manual `POST /product-variant` 1x lewat Postman (product yang sudah ada di eSuite) -- validasi hipotesis alur di poin 16/`CONFIG_NOTES.md` sebelum bikin `product_variant_sync_service.py`.
4. Setelah 1 & 2 selesai: re-push semua produk yang sempat ke-upsert dengan payload lama (`uom_levels` kosong / `cost` belum fix) supaya konsisten.
5. Sisanya sama seperti poin 12 lama (poin 2c, 3, 4, 5, 6) -- belum berubah.

---

**Cara pakai:** upload `bridge_app_vXX.zip` (sudah membundle `app/` + `CONFIG_NOTES.md` + `SESSION_TRANSFER_NOTE.md`) di chat baru, lanjut dari poin 17.
