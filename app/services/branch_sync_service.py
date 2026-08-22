from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError
from app.core.scope import IN_SCOPE_COMPANY_NAMES

# Prefix external_code Branch -- HARUS sama persis dengan yang dikirim
# _to_esuite_payload() ("ODOO-COMPANY-{id}"). Dipakai fitur "upsert by
# external_code" (21 Agustus 2026), pola sama customer_sync_service.py.
EXTERNAL_CODE_PREFIX = "ODOO-COMPANY-"

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

    def sync(
        self,
        event: str = "upsert",
        external_codes: str | None = None,
        limit: int | None = None,
    ):
        odoo_ids = self._parse_external_codes(external_codes) if external_codes else None
        companies = self.odoo.get_companies(IN_SCOPE_COMPANY_NAMES, ids=odoo_ids)

        if not companies:
            raise ValidationError(
                "Tidak ada res.company yang cocok dengan IN_SCOPE_COMPANY_NAMES (cek juga external_codes kalau diisi)",
                details={"expected_names": IN_SCOPE_COMPANY_NAMES},
            )

        total_matched = len(companies)

        # limit -- diagnostic aid, pola sama service lain (kirim cuma N
        # company pertama). Default None -> behavior normal (semua company
        # in-scope).
        if limit is not None:
            companies = companies[:limit]

        payload = [self._to_esuite_payload(c) for c in companies]
        esuite_result = self.esuite.push("branches", event=event, data=payload)

        return {
            "total_matched_in_odoo": total_matched,
            "synced_count": len(payload),
            "external_codes": [item["basic_info"]["external_code"] for item in payload],
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def deactivate(self, external_codes: str) -> dict:
        """
        Nonaktifkan Branch di eSuite (status -> "inactive") by external_code,
        TANPA re-pull data dari Odoo -- payload yang dikirim sengaja MINIMAL
        (cuma status + external_code, bukan full payload name/address seperti
        sync()). Ini aman karena upsert eSuite terkonfirmasi bersifat
        partial-merge (lihat CONFIG_NOTES.md, kasus field `cost` produk) --
        field yang tidak dikirim TIDAK ikut ter-reset/hilang.

        external_codes WAJIB diisi (tidak ada default "semua company") supaya
        tidak ada risiko nonaktifkan branch secara tidak sengaja.
        """
        ids = self._parse_external_codes(external_codes)
        if not ids:
            raise ValidationError(
                "external_codes wajib diisi minimal 1 (format 'ODOO-COMPANY-{id}')"
            )

        payload = [
            {
                "status": "inactive",
                "basic_info": {"external_code": f"{EXTERNAL_CODE_PREFIX}{odoo_id}"},
            }
            for odoo_id in ids
        ]
        esuite_result = self.esuite.push("branches", event="upsert", data=payload)

        return {
            "deactivated_count": len(payload),
            "external_codes": [item["basic_info"]["external_code"] for item in payload],
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _parse_external_codes(self, external_codes: str) -> list[int]:
        """
        Parse "ODOO-COMPANY-1,ODOO-COMPANY-2" -> [1, 2] -- pola sama dengan
        customer_sync_service.py/product_sync_service.py, buat upsert Branch
        tertentu saja tanpa nyentuh yang lain.
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
