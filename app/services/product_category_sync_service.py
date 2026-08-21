from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError

# Prefix external_code Product Category -- HARUS sama persis dengan yang
# dikirim _to_esuite_payload() ("ODOO-CAT-{id}"). Dipakai fitur "upsert by
# external_code" (21 Agustus 2026), pola sama customer_sync_service.py.
EXTERNAL_CODE_PREFIX = "ODOO-CAT-"


class ProductCategorySyncService:
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
        categories = self.odoo.get_product_categories(ids=odoo_ids)

        if not categories:
            raise ValidationError(
                "Tidak ada product.category aktif ditemukan di Odoo (cek juga external_codes kalau diisi)"
            )

        total_matched = len(categories)

        # limit -- diagnostic aid, pola sama service lain (kirim cuma N
        # kategori pertama). Default None -> behavior normal (semua kategori).
        if limit is not None:
            categories = categories[:limit]

        payload = [self._to_esuite_payload(c) for c in categories]
        esuite_result = self.esuite.push("product-category", event=event, data=payload)

        return {
            "total_matched_in_odoo": total_matched,
            "synced_count": len(payload),
            "external_codes": [item["external_code"] for item in payload],
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _parse_external_codes(self, external_codes: str) -> list[int]:
        """
        Parse "ODOO-CAT-1,ODOO-CAT-2" -> [1, 2] -- pola sama dengan
        customer_sync_service.py/product_sync_service.py, buat upsert
        kategori tertentu saja tanpa nyentuh yang lain.
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

    def _to_esuite_payload(self, category: dict) -> dict:
        return {
            "external_code": f"ODOO-CAT-{category['id']}",
            # Sengaja pakai "name" (nama leaf), bukan "complete_name" (path
            # lengkap "Induk / Anak"). Field "parent" eSuite juga sengaja
            # BELUM dipakai di sini -- kalau nanti kategori Odoo kamu
            # berjenjang dan hierarki itu penting buat eSuite, ini titik yang
            # perlu diperluas (parent butuh pola pull-resolve-ID kayak
            # Warehouse->Branch, karena parent.id yang diminta eSuite adalah
            # ID eSuite, bukan ID Odoo).
            "name": category["name"],
            "status": "active",
        }
