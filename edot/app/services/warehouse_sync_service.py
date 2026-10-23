from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError
from app.core.scope import IN_SCOPE_COMPANY_NAMES

# Prefix external_code Warehouse -- HARUS sama persis dengan yang dikirim
# _to_esuite_payload() ("ODOO-WH-{id}"). Dipakai fitur "upsert by
# external_code" (21 Agustus 2026), pola sama customer_sync_service.py.
EXTERNAL_CODE_PREFIX = "ODOO-WH-"


class WarehouseSyncService:
    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(
        self,
        event: str = "upsert",
        external_codes: str | None = None,
        limit: int | None = None,
    ):
        companies = self.odoo.get_companies(IN_SCOPE_COMPANY_NAMES)
        if not companies:
            raise ValidationError(
                "Tidak ada res.company yang cocok dengan IN_SCOPE_COMPANY_NAMES",
                details={"expected_names": IN_SCOPE_COMPANY_NAMES},
            )

        odoo_ids = self._parse_external_codes(external_codes) if external_codes else None
        company_ids = [c["id"] for c in companies]
        warehouses = self.odoo.get_warehouses(company_ids, ids=odoo_ids)
        if not warehouses:
            raise ValidationError(
                "Tidak ada stock.warehouse aktif untuk badan usaha in-scope (cek juga external_codes kalau diisi)"
            )

        total_matched = len(warehouses)

        # limit -- diagnostic aid, pola sama service lain (kirim cuma N
        # warehouse pertama). Default None -> behavior normal (semua warehouse).
        if limit is not None:
            warehouses = warehouses[:limit]

        # Branch WAJIB sudah di-push duluan supaya bisa di-resolve -- resolve
        # tetap untuk SEMUA company in-scope (bukan cuma yang kepakai di
        # warehouse hasil filter), murah karena cuma ~2-3 company.
        branch_id_by_company = self._resolve_branch_ids(companies)

        payload = [self._to_esuite_payload(wh, branch_id_by_company) for wh in warehouses]
        esuite_result = self.esuite.push("warehouse", event=event, data=payload)

        return {
            "total_matched_in_odoo": total_matched,
            "synced_count": len(payload),
            "external_codes": [item["external_code"] for item in payload],
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _parse_external_codes(self, external_codes: str) -> list[int]:
        """
        Parse "ODOO-WH-1,ODOO-WH-2" -> [1, 2] -- pola sama dengan
        customer_sync_service.py/product_sync_service.py, buat upsert
        Warehouse tertentu saja tanpa nyentuh yang lain.
        """
        ids = []
        for raw in external_codes.split(","):
            code = raw.strip()
            if not code:
                continue
            if not code.startswith(EXTERNAL_CODE_PREFIX):
                raise ValidationError(
                    f"external_code '{code}' tidak sesuai format '{EXTERNAL_CODE_PREFIX}{{id_odoo}}'",
                    details={"expected_prefix": EXTERNAL_CODE_PREFIX},
                )
            id_part = code[len(EXTERNAL_CODE_PREFIX):]
            if not id_part.isdigit():
                raise ValidationError(
                    f"external_code '{code}' -- bagian id bukan angka valid",
                    details={"external_code": code},
                )
            ids.append(int(id_part))
        return ids

    def _resolve_branch_ids(self, companies: list) -> dict:
        """
        eSuite TIDAK balikin ID hasil push (§6 dokumen: response push cuma
        {"data": "success"}, tanpa ID). Jadi ID Branch yang baru dibuat harus
        di-PULL balik & dicocokkan lewat external_code kita sendiri.

        Loop semua halaman (bukan cuma page 1) -- sama seperti bug yang
        ketauan di resolve Product Category, dicegah di sini juga.

        Return: {odoo_company_id: esuite_branch_id}
        """
        by_external_code = {}
        page = 1
        limit = 100

        while True:
            pulled = self.esuite.pull("branches", page=page, limit=limit)
            records = pulled.get("data") or []

            for r in records:
                code = r.get("external_code") or (r.get("basic_info") or {}).get("external_code")
                if code:
                    by_external_code[code] = r.get("id")

            meta = pulled.get("meta") or {}
            total_page = meta.get("total_page", 1)
            if page >= total_page:
                break
            page += 1

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
