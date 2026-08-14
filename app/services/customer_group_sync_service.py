from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError

# Customer Group -- HARDCODED (bukan ditarik dinamis dari Odoo, dan bukan
# ditarik dari Odoo sama sekali). res.partner di Odoo saat ini BELUM punya
# field/tag yang bisa dipetakan ke grup ini (dicek 14 Agustus 2026,
# odoo_client.py::get_customers() cuma tarik id/name/company_type -- tidak ada
# grouping field apapun). 4 nama grup di bawah ini murni dari deskripsi bisnis
# yang disampaikan user langsung di chat (14 Agustus 2026), BUKAN hasil query
# Odoo -- Odoo BUKAN sumber data untuk isi list ini karena datanya memang belum
# ada di Odoo. Pola hardcode-constant ini sama dengan CURRENCY
# (customer_sync_service.py) dan PRODUCT_TYPE (product_sync_service.py) --
# pertanyaan "apakah sebaiknya nanti ditarik dinamis dari Odoo (kalau field-nya
# sudah ada)" sengaja DITUNDA per instruksi user (to be confirmed, not urgent).
#
# 4 grup bisnis CBU (dikonfirmasi user 14 Agustus 2026):
# - Food Service (FS)
# - Modern Trade (MT)
# - General Trade (GT)
# - HORECA (Hotel, Restaurant, Cafe/Catering)
#
# ASUMSI (belum eksplisit dikonfirmasi user) -- external_code pakai prefix
# "CBU-CUSTGROUP-" (BUKAN "ODOO-...") karena entity ini TIDAK bersumber dari
# id record Odoo manapun (beda dengan Product/Customer/Warehouse yang id-nya
# = id record Odoo). Kalau boss/vendor punya konvensi kode lain, tinggal ganti
# "code" di bawah -- external_code lama vs baru akan dianggap 2 record berbeda
# oleh eSuite (upsert by external_code), jadi ganti prefix/code SEBELUM push
# pertama ke sandbox, bukan sesudah.
CUSTOMER_GROUPS = [
    {"code": "FS", "name": "Food Service"},
    {"code": "MT", "name": "Modern Trade"},
    {"code": "GT", "name": "General Trade"},
    {"code": "HORECA", "name": "HORECA"},
]

# Currency -- sama persis dengan CURRENCY di customer_sync_service.py (IDR,
# satu-satunya currency di seluruh bisnis). Didefinisikan ulang di sini
# (bukan import silang antar service) konsisten dengan pola tiap sync service
# independen yang sudah dipakai di project ini.
#
# DITAMBAHKAN 14 Agustus 2026 -- root cause dugaan kenapa 4 record pertama
# tidak muncul di GET /customergroup meski POST balas 200 OK: PDF section 9.14
# cuma nyebut "Required fields: external_code, name; status optional", TAPI
# payload Postman kamu yang TERBUKTI jalan untuk entity ini menyertakan
# "basic_transaction": {"currency": {...}}. Pola ini SAMA dengan kasus
# `entity_type` di Customer (11 Agustus 2026) -- field yang didokumentasikan
# "opsional"/tidak disebut di teks "Required fields", ternyata di backend
# eSuite tetap wajib, dan pelanggarannya bukan error eksplisit tapi silent
# failure (200 OK, record tidak benar-benar tersimpan). Ini MASIH DUGAAN
# (belum dikonfirmasi vendor) -- tapi karena additive & rendah risiko, field
# ini ditambahkan supaya payload konsisten dengan contoh Postman yang sudah
# terbukti bekerja.
CURRENCY = {"id": "6a695cc1917e8fc836359505"}  # IDR, dari GET /currency


class CustomerGroupSyncService:
    def __init__(self):
        self.esuite = EsuiteClient()

    def sync(self, event: str = "upsert"):
        if not CUSTOMER_GROUPS:
            raise ValidationError("CUSTOMER_GROUPS kosong -- tidak ada yang bisa disync")

        payload = [self._to_esuite_payload(g) for g in CUSTOMER_GROUPS]
        esuite_result = self.esuite.push("customergroup", event=event, data=payload)

        return {
            "synced_count": len(payload),
            "external_codes": [item["external_code"] for item in payload],
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _to_esuite_payload(self, group: dict) -> dict:
        return {
            "external_code": f"CBU-CUSTGROUP-{group['code']}",
            "name": group["name"],
            "status": "active",
            # basic_transaction.currency -- lihat komentar CURRENCY di atas
            # (14 Agustus 2026, dugaan silent-required-field, belum dikonfirmasi
            # vendor, tapi cocokkan dulu dengan contoh Postman yang jalan).
            "basic_transaction": {"currency": CURRENCY},
            # parent / customers[] / transaction_rules -- sengaja BELUM dikirim
            # (benar-benar opsional, tidak ada di contoh Postman minimal kamu
            # juga). customers[] akan relevan begitu ada mapping customer->group
            # di sisi Odoo (belum ada, lihat SESSION_TRANSFER_NOTE.md pending tasks).
        }
