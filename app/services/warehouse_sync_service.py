from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError
from app.core.scope import IN_SCOPE_COMPANY_NAMES


class WarehouseSyncService:
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

        company_ids = [c["id"] for c in companies]
        warehouses = self.odoo.get_warehouses(company_ids)
        if not warehouses:
            raise ValidationError("Tidak ada stock.warehouse aktif untuk badan usaha in-scope")

        branch_id_by_company = self._resolve_branch_ids(companies)

        payload = [self._to_esuite_payload(wh, branch_id_by_company) for wh in warehouses]
        esuite_result = self.esuite.push("warehouse", event=event, data=payload)

        return {
            "synced_count": len(payload),
            "external_codes": [item["external_code"] for item in payload],
            "esuite_response": esuite_result,
        }

    def _resolve_branch_ids(self, companies: list) -> dict:
        """
        eSuite TIDAK balikin ID hasil push (§6 dokumen: response push cuma
        {"data": "success"}, tanpa ID). Jadi ID Branch yang baru dibuat harus
        di-PULL balik & dicocokkan lewat external_code kita sendiri.

        Return: {odoo_company_id: esuite_branch_id}
        """
        pulled = self.esuite.pull("branches", page=1, limit=100)
        records = pulled.get("data") or []

        by_external_code = {}
        for r in records:
            # Dicek 2 kemungkinan lokasi field -- dokumen nggak eksplisit
            # apakah GET balikin external_code di top-level atau di dalam
            # basic_info (bentuk PUSH-nya nested, GET belum pernah dites).
            code = r.get("external_code") or (r.get("basic_info") or {}).get("external_code")
            if code:
                by_external_code[code] = r.get("id")

        result = {}
        for company in companies:
            expected_code = f"ODOO-COMPANY-{company['id']}"
            esuite_id = by_external_code.get(expected_code)
            if not esuite_id:
                raise ValidationError(
                    f"Branch untuk company '{company['name']}' belum ada di eSuite -- jalankan /sync/branch dulu",
                    details={"expected_external_code": expected_code},
                )
            result[company["id"]] = esuite_id

        return result

    def _to_esuite_payload(self, warehouse: dict, branch_id_by_company: dict) -> dict:
        company = warehouse.get("company_id")  # [id, display_name]
        company_id = company[0] if company else None
        branch_esuite_id = branch_id_by_company.get(company_id)

        short_name = (warehouse.get("code") or warehouse["name"])[:10]

        return {
            "name": warehouse["name"],
            "short_name": short_name,
            # external_code = key upsert/delete -- prefix beda dari Branch
            # supaya nggak ketuker meski dua-duanya asalnya dari Odoo.
            "external_code": f"ODOO-WH-{warehouse['id']}",
            "owner_type": "Company",
            "branches": [{"id": branch_esuite_id}],
        }
