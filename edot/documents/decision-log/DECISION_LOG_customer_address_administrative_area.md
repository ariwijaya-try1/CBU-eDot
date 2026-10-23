# DECISION LOG -- Customer Address: Wilayah Administratif (administrative_level)

> **Version: v10** (10 Oktober 2026) -- diupdate 29 September 2026
> COPY read-only dari Decision Log utama di memory Claude (Project "eDot",
> file `customer_address_administrative_area`). Setiap keputusan baru di topik
> ini: file ini di-update (bukan dibuat baru) dan nomor versi dinaikkan.

---

## ✅ 29 September 2026 -- KEPUTUSAN USER: `administrative_level[]` DIISI dari modul regional Odoo

**Menggantikan:** keputusan 24 Agustus 2026 (docstring `customer_sync_service.py::_to_esuite_address()`) -- "`administrative_level` SENGAJA TIDAK dikirim karena Odoo tidak punya granularitas 4 level".

**Alasan:** Odoo sudah mengadopsi modul regional `ms_l10n_id_localization` (Provinsi / Kabupaten-Kota / Kecamatan / Desa).

**Padanan level Odoo -> eSuite:**
- `res.country.state` -> `province` (level 0)
- `res.city` -> `city` (level 1)
- `res.subdistrict` (Kecamatan) -> `district` (level 2)
- `res.village` (Desa/Kelurahan) -> `sub_district` (level 3)

**Aturan matching (fakta data, 29 September 2026):**
- ID Odoo = nomor urut modul (`res_city_00276`, `village_51068`), BUKAN kode resmi -> tidak bisa dicocokkan ke kode eSuite (`V51030602`). Matching by NAMA berjenjang, dinormalisasi (uppercase, buang tanda baca, rapikan spasi).
- Kode pos Odoo != eSuite (Kerobokan 80361 vs 80363) -> bukan kunci; `postal_code` yang dikirim ambil dari eSuite.
- Cukup map level desa -> object level 3 eSuite; `area[]` hasil lookup sudah berisi hierarki 0-3.
- Field lama `province`/`city`/`district`/`sub_district` di address Customer deprecated (dev eSuite, 22 September) -> tidak dikirim.

**Field Odoo TERKONFIRMASI (29 September 2026, via debug tooltip & dialog Export):**
- res.partner: `state_id` (Provinsi), `city_id` -> res.city, `subdistrict_id` -> res.subdistrict, `village_id` -> res.village. Field char `city` bawaan Odoo = teks bebas, TIDAK dipakai utk mapping.
- res.city {`name`, `state_id`}, res.subdistrict {`name`, `city_id`}, res.village {`name`, `subdistrict_id`}.

**API eSuite `GET /v1/webhook/administrative-areas` (screenshot dev, 29 September 2026):**
- Param: `level` 0|1|2|3 (default 0), `country` (default ID), `keyword` (nama persis), `search_name` (nama sebagian), `code` (kode persis), `page`/`limit` (default 1/10).
- Tidak ada filter parent -> resolve desa: `level=3&keyword=<nama desa>`, lalu pilih hasil yang `area[]` (province/city/district) cocok dengan Odoo (nama dinormalisasi).

## ✅ 29 September 2026 (lanjutan) -- KEPUTUSAN USER: cara resolve & behavior unmapped

- **Lookup LIVE + cache** (BUKAN file mapping JSON / tabel PostgreSQL): tiap desa unik dicari ke eSuite saat sync, hasil match di-cache di memori proses selama bridge jalan (hilang saat restart). Alasan: tanpa file/tabel baru, selalu up to date; konsekuensi: sync pertama setelah restart lebih lambat (1 GET per desa unik).
- **Desa tidak ketemu/ambigu di eSuite -> customer TETAP di-upsert tanpa `administrative_level`**, dilaporkan di response `administrative_area.unresolved` (pola sama customer_group/branch/pricelist unresolved -- bukan fail-fast).
- Hanya hasil MATCH yang di-cache; not_found/ambiguous dicoba ulang tiap sync.
- Branch (`ADMINISTRATIVE_AREA` di `branch_sync_service.py`): BELUM diputuskan.

**Status:** diimplementasi 29 September 2026 di `/sync/customers` (odoo_client `get_village_hierarchy()`, esuite_client `pull_with_params()`, customer_sync_service `_resolve_admin_area_map()`), belum live test.

## ✅ 5 Oktober 2026 -- `dry_run` di `/sync/customers`

- Ditambah param `dry_run` (default false). True = cek saja: lookup Odoo + GET eSuite tetap jalan, TIDAK ada push ke eSuite, tidak tulis CSV/sync_log. Dipakai utk melihat laporan `administrative_area` sebelum upsert massal.
- Urutan aman yang disepakati utk rollout wilayah: (1) dry_run 1 customer, (2) dry_run semua -> perbaiki `unresolved`, (3) cek risiko address `"id": ""` (address baru tiap upsert, bisa memutus link warehouse outlet), (4) baru upsert sungguhan bertahap.
- Masih terbuka: risiko address id kosong, 2 endpoint lain tanpa `administrative_level`, Branch, fallback nama bertanda baca.

## ✅ 7 Oktober 2026 -- Hasil live test (fakta, bukan keputusan baru)

- Lookup wilayah jalan di production: akun API Odoo bisa baca model regional; `keyword` huruf besar cocok di eSuite.
- eSuite MENYIMPAN `administrative_level` dari upsert Customer (ODOO-PARTNER-39353 & 1655). `postal_code` level 3 tidak dikembalikan GET.
- Upsert Customer MENGGANTI `addresses[]` (tetap 1 address; address tidak punya id sendiri di GET) -> tidak ada alamat ganda.
- `warehouse.address.id` (warehouse outlet) = `id` Customer eSuite -> link tidak terpengaruh upsert. Poin "risiko address id kosong" di v5 DITUTUP.
- Masih terbuka: 2 endpoint lain tanpa `administrative_level` (sekarang lebih penting: karena upsert MENGGANTI address, endpoint itu akan MENGHAPUS wilayah kalau dipakai setelah sync), Branch, fallback nama bertanda baca.

## ✅ 7 Oktober 2026 (13:48) -- KEPUTUSAN USER: cakupan rollout, 2 endpoint lain, aturan nama

- **Rollout wilayah = SEMUA customer** (`POST /api/sync/customers` tanpa filter), termasuk membuat customer yang belum ada di eSuite. User minta catatan khusus saat sync Jakarta (ada di `documents/TEST_PLAN_customer_regional_mapping.md`). Opsi "hanya customer yang punya Desa" (`only_with_village`) TIDAK dipilih.
- **Dua endpoint lain DISAMAKAN** dengan `/sync/customers`: `mapping/customer-upsert-geo-branch-sales` dan `update/customer-geolocation` ikut mengirim `administrative_level`. Alasan: upsert eSuite MENGGANTI `addresses[]`, jadi address tanpa wilayah menghapus wilayah. Untuk geolocation, address dibangun LENGKAP dari Odoo bila external_code `ODOO-PARTNER-{id}`; external_code legacy tetap koordinat saja + peringatan.
- **Aturan nama longgar** (dari bukti live Jakarta: Odoo `Jakarta > Kota Adm. Jakarta Pusat` vs eSuite `DKI JAKARTA > JAKARTA PUSAT`): dipakai hanya bila 4 nama persis tidak ketemu; kecamatan & desa tetap harus persis; provinsi/kota dibandingkan tanpa kata penanda (DKI, DI, DAERAH ISTIMEWA, KOTA, KAB, ADM, dst); harus tepat 1 hasil; selalu dilaporkan di `matched_by_relaxed_name`.
- **Struktur kode:** logic wilayah dipusatkan di `app/core/admin_area.py` (dipakai 3 service, 1 cache). Convention "service tidak saling import" tetap dijaga.
- Menggantikan butir "masih terbuka: 2 endpoint lain" di v5/v6. Masih terbuka: Branch `ADMINISTRATIVE_AREA`; `postal_code` tidak tampil di GET.

## ✅ 9 Oktober 2026 -- KEPUTUSAN USER: alias nama desa di bridge

- Kasus: Odoo "Semarapura Klod" (Bali / Kab. Klungkung / Klungkung) tidak ketemu di eSuite; eSuite menulis "SEMARAPURA KELOD". Master Odoo sendiri tidak konsisten (desa tetangga ditulis "Semarapura Kelod Kangin"). User: ejaan benar "Semarapura Kelod", master Odoo yang salah.
- Perbaikan lewat **alias di bridge** (`VILLAGE_NAME_ALIASES` di `app/core/admin_area.py`), bukan rename master Odoo. Kunci alias = jalur 4 level Odoo yang dinormalisasi, supaya tidak mengenai desa bernama sama di tempat lain. Desa yang cocok lewat alias dilaporkan di `matched_by_relaxed_name`.
- Kasus ejaan desa lain yang ketemu nanti ditambahkan ke daftar yang sama.
- Tambahan 9 Oktober: kalau `keyword` eSuite tidak menemukan apa pun, bridge mencari ulang dengan kata pertama nama desa HANYA untuk mengisi `esuite_candidates` (diagnosa).

## ✅ 9 Oktober 2026 (17:15) -- STATUS: rollout selesai (fakta, bukan keputusan baru)

- Rollout semua customer dijalankan: 3.581 terkirim tanpa gagal; 2.677 customer kini punya `administrative_level` di eSuite; 188/188 desa yang dipakai customer terpetakan.
- Fitur mapping wilayah Odoo -> eSuite dinyatakan BERJALAN di production. Pekerjaan lanjutan bersifat data (isi Desa 904 customer di Odoo) dan operasional (register customer Jakarta baru ke sales), bukan kode.

## ✅ 10 Oktober 2026 -- KEPUTUSAN USER: default `branch_external_codes` dikosongkan

- Endpoint `POST /api/mapping/customer-upsert-geo-branch-sales`: default `branch_external_codes` `"ODOO-COMPANY-2"` (28 Agustus 2026) DIGANTI menjadi `""`.
- Kosong = branch tidak dikirim, branch existing tidak berubah. Isi manual hanya kalau memang mau mengganti branch customer.
- Alasan: branch customer sudah otomatis dari company Odoo lewat `/sync/customers`; customer tersebar di 3 branch; default SFC memindahkan customer ke branch salah (tes F4, 7 Oktober).
