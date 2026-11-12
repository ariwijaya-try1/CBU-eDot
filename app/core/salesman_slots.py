"""
Tabel mapping slot Salesperson Odoo -> akun salesman eSuite -- 12 Oktober 2026.

Keputusan user (Decision Log visit cycle, 7 & 12 Oktober 2026):
- Tabel ini disimpan DI BRIDGE (bukan field Odoo).
- Slot Odoo & username eDot TETAP; orang di balik slot boleh berganti
  (resign, izin, dst). Kolom `person` hanya keterangan, bukan kunci.
- Tim FS tidak masuk visit cycle -> tidak ada di tabel ini.

odoo_slot          : nama res.users (Salesperson / res.partner.user_id) PERSIS
                     seperti di Odoo. Di-resolve ke id res.users saat jalan;
                     kalau nama slot di Odoo diganti, endpoint berhenti dgn
                     pesan jelas (bukan diam-diam salah orang).
esuite_employee_id : `employee_id` akun eSuite (GET /employee?employee_id=..),
                     di-resolve ke id internal + branch saat jalan.

Sumber employee_id: hasil GET /employee PROD yang dikirim user 6 Oktober 2026.
14 Oktober 2026: orang di Salesman_3 (MT04) & Salesman_5 (MT02) ditukar
(Winaya <-> Fani) -- hanya label `person`, slot & akun tetap.
21 Oktober 2026 (konfirmasi user, data Nesa/sales manager): AKUN ikut orang --
Winaya tetap pakai Salesman_3 (data input lamanya tetap ada) & kini pegang
slot MT02; Fani pakai Salesman_5 & pegang slot MT04. Akun MT02<->MT04 ditukar.
4 November 2026 (tabel user): orang MT01 = Yoni (sebelumnya tertulis Yona).
7 November 2026 (keputusan user): akun UTAMA MT01 = Akbar (Salesman_8, SMD,
kunjungan rutin); Yoni (Salesman_6, sales, visit insidentil) jadi MIRROR Akbar
-- sementara, sampai mapping sales user di Odoo berubah.
"""

SALESMAN_SLOTS = [
    {"odoo_slot": "[SALES] BAL GT02", "esuite_employee_id": "202600016", "esuite_username": "Salesman_1", "person": "Ali (GT)"},
    {"odoo_slot": "[SALES] BAL GT01", "esuite_employee_id": "202600019", "esuite_username": "Salesman_2", "person": "Angga (GT)"},
    {"odoo_slot": "[SALES] BAL MT04", "esuite_employee_id": "202600020", "esuite_username": "Salesman_5", "person": "Fani (MT)"},
    {"odoo_slot": "[SALES] BAL MT03", "esuite_employee_id": "202600014", "esuite_username": "Salesman_4", "person": "Anda (MT)"},
    {"odoo_slot": "[SALES] BAL MT02", "esuite_employee_id": "202600009", "esuite_username": "Salesman_3", "person": "Winaya (MT)"},
    {"odoo_slot": "[SALES] BAL MT01", "esuite_employee_id": "202600011", "esuite_username": "Salesman_8", "person": "Akbar (SMD MT)"},
]

SLOTS_BY_NAME = {s["odoo_slot"]: s for s in SALESMAN_SLOTS}

# 4 November 2026 (keputusan user): AKUN MIRROR -- 1 slot Odoo dipakai >1 akun
# eDot. Akun mirror dapat call plan SAMA PERSIS dgn akun utama slot (outlet &
# tanggal sama); pembagian tidak bisa ditrace dari Odoo, dilihat di eDot.
# Sengaja DI LUAR SALESMAN_SLOTS -> Swagger, export Excel & GET visit tetap
# per slot Odoo (1 akun utama). Kode call plan mirror beda (lihat
# call_plan_sync_service.MIRROR_CODE_PREFIX) supaya tidak menimpa akun utama.
# esuite_employee_id kosong = belum diisi -> dilewati + dilaporkan saat push.
# 202600017 = "Sales Cahaya 6" (screenshot list Employee UI eSuite, 4 Nov 2026).
# 7 Nov 2026: dibalik -- Yoni (sales, insidentil) mirror Akbar (SMD, akun utama).
MIRROR_ACCOUNTS = [
    {"odoo_slot": "[SALES] BAL MT01", "esuite_employee_id": "202600017", "esuite_username": "Salesman_6", "person": "Yoni (sales MT, mirror Akbar)"},
]

MIRRORS_BY_SLOT: dict[str, list[dict]] = {}
for _m in MIRROR_ACCOUNTS:
    MIRRORS_BY_SLOT.setdefault(_m["odoo_slot"], []).append(_m)

# 21 Oktober 2026 (user): mode tes call plan SELALU ke akun testing Salesman_12
# ("Sales Cahaya 12", employee_id terverifikasi UI eSuite 21 Okt). Sengaja DI
# LUAR SALESMAN_SLOTS -- bukan slot Odoo.
TEST_EMPLOYEE_ID = "202600012"
TEST_USERNAME = "Salesman_12"
