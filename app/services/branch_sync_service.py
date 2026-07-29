from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError

# Kode wilayah administratif eSuite untuk lokasi gedung yang dipakai.
# Diisi MANUAL (bukan pull otomatis) karena jumlah Branch cuma 1-2 dan
# lokasinya jarang berubah -- cara dapetinnya: panggil GET /administrative-areas
# ke eSuite sandbox sekali, cari baris yang cocok sama alamat gedung asli,
# lalu isi code & name di bawah ini persis seperti yang eSuite kasih.
#
# TODO: isi 3 baris ini sebelum endpoint /sync/branch dites ke sandbox.
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
        warehouses = self.odoo.get_warehouses()

        if not warehouses:
            raise ValidationError("Tidak ada warehouse aktif ditemukan di Odoo")

        payload = [self._to_esuite_payload(wh) for wh in warehouses]
        esuite_result = self.esuite.push("branches", event=event, data=payload)

        return {
            "synced_count": len(payload),
            "external_codes": [item["basic_info"]["external_code"] for item in payload],
            "esuite_response": esuite_result,
        }

    def _to_esuite_payload(self, warehouse: dict) -> dict:
        # partner_id dari Odoo berbentuk [id, display_name] (many2one),
        # bukan langsung int -- lihat catatan gotcha RPC yang sudah diketahui.
        partner = warehouse.get("partner_id")
        address_data = self.odoo.get_partner_address(partner[0]) if partner else {}
        address_data = address_data or {}

        return {
            "name": warehouse["name"],
            "status": "active",
            "basic_info": {
                # external_code = key upsert/delete di eSuite -- harus stabil & unik.
                # Prefix "ODOO-WH-" biar jelas asalnya dari stock.warehouse Odoo.
                "external_code": f"ODOO-WH-{warehouse['id']}",
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
