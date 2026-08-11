from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError

# Currency -- sama dengan yang dipakai product_sync_service.py (IDR, satu-satunya
# currency yang dipakai di seluruh bisnis, lihat CONFIG_NOTES.md). Didefinisikan
# lagi di sini (bukan import silang antar service) supaya tiap sync service tetap
# independen -- konsisten dengan pola konstanta lain di project ini
# (ADMINISTRATIVE_AREA di branch_sync_service.py, UOM_MAPPING di product_sync_service.py).
CURRENCY = {"id": "6a695cc1917e8fc836359505"}  # IDR, dari GET /currency

# Mapping company_type (Odoo) -> type (eSuite). Dikonfirmasi user 7 Agustus 2026:
# field Odoo yang benar itu company_type, BUKAN res.partner.type (itu jenis alamat).
CUSTOMER_TYPE_MAPPING = {
    "company": "company",
    "person": "individual",
}


class CustomerSyncService:
    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(self, event: str = "upsert", limit: int | None = None):
        customers = self.odoo.get_customers()

        if not customers:
            raise ValidationError("Tidak ada res.partner dengan customer_rank > 0 ditemukan di Odoo")

        total_matched = len(customers)

        # limit -- TEMPORARY diagnostic aid (7 Agustus 2026), BUKAN fitur bisnis
        # permanen. Ditambahkan buat isolasi root cause 502 Bad Gateway dari
        # eSuite saat push full batch customer (lihat SESSION_TRANSFER_NOTE.md):
        # test manual 1 record via Postman sukses, push full batch via bridge
        # 502 dua kali berturut-turut. limit memungkinkan test bertahap
        # (5, 50, 500 record, dst) buat cari tau apakah soal jumlah record
        # atau soal isi data tertentu, tanpa perlu ubah kode tiap kali coba.
        # Default None -> behavior sama seperti sebelumnya (semua customer).
        if limit is not None:
            customers = customers[:limit]

        payload = [self._to_esuite_payload(c) for c in customers]
        esuite_result = self.esuite.push("customers", event=event, data=payload)

        return {
            "synced_count": len(payload),
            "total_matched_in_odoo": total_matched,
            "external_codes": [item["external_code"] for item in payload],
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _resolve_customer_type(self, company_type: str) -> str:
        mapped = CUSTOMER_TYPE_MAPPING.get(company_type)
        if not mapped:
            raise ValidationError(
                f"company_type Odoo '{company_type}' belum ada mapping-nya di CUSTOMER_TYPE_MAPPING",
                details={"odoo_company_type": company_type, "known_mappings": list(CUSTOMER_TYPE_MAPPING.keys())},
            )
        return mapped

    def _to_esuite_payload(self, customer: dict) -> dict:
        return {
            "name": customer["name"],
            # external_code = key upsert/delete di eSuite -- prefix "ODOO-PARTNER-"
            # konsisten dengan pola prefix entity lain (ODOO-COMPANY-, ODOO-PROD-).
            "external_code": f"ODOO-PARTNER-{customer['id']}",
            "type": self._resolve_customer_type(customer.get("company_type")),
            "status": "active",
            "currency": CURRENCY,
        }
