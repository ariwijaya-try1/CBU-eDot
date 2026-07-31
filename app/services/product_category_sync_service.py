from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError


class ProductCategorySyncService:
    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(self, event: str = "upsert"):
        categories = self.odoo.get_product_categories()

        if not categories:
            raise ValidationError("Tidak ada product.category aktif ditemukan di Odoo")

        payload = [self._to_esuite_payload(c) for c in categories]
        esuite_result = self.esuite.push("product-category", event=event, data=payload)

        return {
            "synced_count": len(payload),
            "external_codes": [item["external_code"] for item in payload],
            "esuite_response": esuite_result,
        }

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
