from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError

# Customer Group -- HARDCODED (bukan ditarik dinamis dari Odoo). res.partner di
# Odoo saat ini BELUM punya field/tag yang bisa dipetakan ke grup ini (dicek
# 14 Agustus 2026, odoo_client.py::get_customers() cuma tarik id/name/company_type).
# Pola hardcode ini sama dengan CURRENCY (customer_sync_service.py) dan
# PRODUCT_TYPE (product_sync_service.py) -- pertanyaan "apakah sebaiknya nanti
# ditarik dinamis dari Odoo" sengaja DITUNDA per instruksi user (to be confirmed,
# not urgent), lihat SESSION_TRANSFER_NOTE.md.
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
            # parent / customers[] / transaction_rules -- sengaja BELUM dikirim
            # (opsional di skema PDF section 9.14). customers[] akan relevan
            # begitu ada mapping customer->group di sisi Odoo (belum ada, lihat
            # SESSION_TRANSFER_NOTE.md pending tasks).
        }
