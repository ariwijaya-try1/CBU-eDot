from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError
from app.core.scope import IN_SCOPE_COMPANY_NAMES

# Kode wilayah administratif eSuite untuk lokasi gedung yang dipakai.
# Diisi MANUAL (bukan pull otomatis) karena jumlah Branch cuma 2 dan
# lokasinya jarang berubah -- cara dapetinnya: panggil GET /administrative-areas
# ke eSuite sandbox sekali, cari baris yang cocok sama alamat gedung asli,
# lalu isi code & name di bawah ini persis seperti yang eSuite kasih.
#
# TODO: isi 3 baris ini sebelum push dites lagi ke sandbox.
ADMINISTRATIVE_AREA = {
    "country": {"name": "Indonesia", "code": "ID"},
    "province": {"name": "", "code": ""},
    "city": {"name": "", "code": ""},
    "district": {"name": "", "code": ""},
}


class BranchSyncService:
    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(self, event: str = "upsert"):
        companies = self.odoo.get_companies(IN_SCOPE_COMPANY_NAMES)

        if not companies:
            raise ValidationError(
                "Tidak ada res.company yang cocok dengan IN_SCOPE_COMPANY_NAMES",
                details={"expected_names": IN_SCOPE_COMPANY_NAMES},
            )

        payload = [self._to_esuite_payload(c) for c in companies]
        esuite_result = self.esuite.push("branches", event=event, data=payload)

        return {
            "synced_count": len(payload),
            "external_codes": [item["basic_info"]["external_code"] for item in payload],
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _to_esuite_payload(self, company: dict) -> dict:
        # partner_id dari Odoo berbentuk [id, display_name] (many2one).
        partner = company.get("partner_id")
        address_data = self.odoo.get_partner_address(partner[0]) if partner else {}
        address_data = address_data or {}

        return {
            "name": company["name"],
            "status": "active",
            "basic_info": {
                # external_code = key upsert/delete di eSuite -- harus stabil & unik.
                # Prefix "ODOO-COMPANY-" karena sumbernya sekarang res.company,
                # bukan stock.warehouse lagi (lihat catatan koreksi mapping entity).
                "external_code": f"ODOO-COMPANY-{company['id']}",
            },
            "address": {
                "country": ADMINISTRATIVE_AREA["country"],
                "province": ADMINISTRATIVE_AREA["province"],
                "city": ADMINISTRATIVE_AREA["city"],
                "district": ADMINISTRATIVE_AREA["district"],
                "street_address": address_data.get("street") or "",
                "postal_code": address_data.get("zip") or "",
                "geo": {
                    "lat": str(address_data.get("partner_latitude") or ""),
                    "long": str(address_data.get("partner_longitude") or ""),
                },
            },
        }
