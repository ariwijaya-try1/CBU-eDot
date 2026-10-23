# Perubahan 17 Agustus 2026 — Pricelist GET-inspeksi (tahap 1)

## File yang berubah (2 file, ADDITIF -- tidak ada baris lama yang diubah/dihapus)
1. `app/clients/odoo_client.py` -- 2 method baru: `get_pricelists()`, `get_pricelist_items()` (ditambahkan sebelum `_name_in_domain`).
2. `app/api/routes/odoo_get.py` -- 2 endpoint baru: `GET /odoo/pricelist`, `GET /odoo/pricelist-item` (ditambahkan di akhir file).

Tidak ada perubahan `main.py`, database, Docker, env var, atau dependency -- router "odoo - Get" sudah terdaftar sebelumnya. Syntax sudah dicek (`python3 -m py_compile`), belum dijalankan end-to-end (uvicorn) di sandbox ini.

## Kenapa cuma GET dulu, belum push
Pricelist belum pernah disentuh sama sekali sebelumnya di kode. Skema `POST /pricelists` eSuite (PDF section 9.13) baru dibaca lengkap sesi ini -- 2 temuan penting:

1. Field `product[].id`, `variant[].id`, `branch[].id`, `customer_group[].id` di payload eSuite semuanya pakai **id internal eSuite**, bukan `external_code` langsung -- beda dari kebanyakan entity lain, push nanti wajib resolve id dulu (pola sama seperti guard di `stock_sync_service.py`).
2. Pricelist di eSuite cuma bisa di-scope ke `branch[]`/`customer_group[]` (grup) -- TIDAK ada field per-customer/PT. Dimensi harga per-PT kemungkinan besar jalan lewat field `price_list.id` di entity Customer sendiri (belum pernah dikirim -- gap lama), bukan dari Pricelist itu sendiri.

Push (`PricelistSyncService`) SENGAJA belum dibangun -- field/model Odoo (`product.pricelist`) belum pernah tervalidasi live, dan ini data **harga**: kalau field ditebak salah lalu langsung dipush, resikonya bukan cuma internal, harga salah bisa kelihatan customer beneran di app sales. GET read-only dulu supaya bisa dicek live lewat Swagger, baru push dibangun dari bentuk data yang sudah pasti benar.

## Next step
1. Coba `GET /odoo/pricelist` lewat Swagger.
   - Error RPC -> kabari pesan errornya persis, field/model disesuaikan.
   - Kosong/cuma 1 record default -> kemungkinan CBU belum setup multiple pricelist di Odoo, sumber data perlu didiskusikan ulang.
   - Ada data -> kirim contoh hasilnya, baru dibangun `PricelistSyncService` (push ke `/pricelists`).
2. `customer_group[]` scope boleh langsung pakai external_code yang sudah confirmed jalan (`CBU-CUSTGROUP-FS/MT/GT/HORECA`) -- TIDAK perlu nunggu keputusan duplikat MT/GT lama (isu itu soal 2 record LAMA yang beda id, bukan soal record kita sendiri).

## Catatan tambahan (di luar scope Pricelist)
Ditemukan kode yang sudah ada tapi belum tercatat di catatan project manapun sebelumnya: endpoint GET Salesperson (`/odoo/salesperson`, `/odoo/customer-by-salesperson`, `/odoo/salesperson-by-customer`, model `res.users`) -- read-only, belum ada push Salesman/Salesman Division. Sudah disinkronkan ke catatan project (Cowork project memory: `sales_entities_gap.md`, `pricelist_progress.md` baru).

Detail lengkap (skema PDF, analisa, riwayat) ada di Cowork project memory (`pricelist_progress.md`, `sales_entities_gap.md`) -- bukan file di repo ini, cuma dicatat singkat di sini biar ada jejak lokal juga.
