from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError

# Referensi eSuite yang diisi manual (mirip ADMINISTRATIVE_AREA di Branch) --
# nilai-nilai ini TIDAK datang dari Odoo, itu master data milik eSuite sendiri.
# Cara isi: GET /currency dan GET /product-type ke sandbox, cari baris yang
# cocok, copy id-nya ke sini.
#
# TODO: isi ID sebelum push dites ke sandbox.
CURRENCY = {"id": ""}  # asumsi cuma IDR (sales ke customer) -- lihat CONFIG_NOTES.md
PRODUCT_TYPE = {"id": ""}  # asumsi semua produk "Goods" -- lihat CONFIG_NOTES.md

# Mapping UOM: key = nama uom_id di Odoo (di-lowercase), value = id eSuite.
# TODO: isi persis nama UOM yang keluar dari Odoo (lihat payload_sent hasil
# test pertama untuk tau nama aslinya -- jangan tebak dari nama produk),
# lalu isi id eSuite dari hasil GET /uom.
UOM_MAPPING = {
    "units": {"id": ""},
    "pcs": {"id": ""},
    "pack": {"id": ""},
}


class ProductSyncService:
    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(self, event: str = "upsert"):
        products = self.odoo.get_products()

        # free_qty computed field -- tidak bisa difilter di domain Odoo,
        # jadi difilter di sini (pola sama seperti project referensi searchProduct).
        products = [p for p in products if (p.get("free_qty") or 0) > 0]

        if not products:
            raise ValidationError("Tidak ada produk Saleable dengan free_qty > 0 ditemukan di Odoo")

        category_id_map = self._resolve_category_ids()

        payload = [self._to_esuite_payload(p, category_id_map) for p in products]
        esuite_result = self.esuite.push("product", event=event, data=payload)

        return {
            "synced_count": len(payload),
            "external_codes": [item["external_code"] for item in payload],
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _resolve_category_ids(self) -> dict:
        """
        Sama seperti Warehouse->Branch: push tidak balikin ID, jadi pull
        balik /product-category & cocokkan external_code (ODOO-CAT-{id}).
        Return: {odoo_category_id: esuite_category_id}
        """
        pulled = self.esuite.pull("product-category", page=1, limit=200)
        records = pulled.get("data") or []

        result = {}
        for r in records:
            code = r.get("external_code") or (r.get("basic_info") or {}).get("external_code")
            if code and code.startswith("ODOO-CAT-"):
                odoo_id = int(code.replace("ODOO-CAT-", ""))
                result[odoo_id] = r.get("id")

        return result

    def _resolve_uom(self, uom_name: str) -> dict:
        key = (uom_name or "").strip().lower()
        mapped = UOM_MAPPING.get(key)
        if not mapped or not mapped.get("id"):
            raise ValidationError(
                f"UOM Odoo '{uom_name}' belum ada mapping-nya di UOM_MAPPING",
                details={"odoo_uom_name": uom_name, "known_mappings": list(UOM_MAPPING.keys())},
            )
        return mapped

    def _to_esuite_payload(self, product: dict, category_id_map: dict) -> dict:
        # categ_id & uom_id dari Odoo berbentuk [id, display_name] (many2one).
        categ = product.get("categ_id")
        uom = product.get("uom_id")

        category_esuite_id = category_id_map.get(categ[0]) if categ else None
        if not category_esuite_id:
            raise ValidationError(
                f"Product category untuk produk '{product['name']}' belum ada di eSuite -- jalankan /sync/product-category dulu",
                details={"odoo_categ_id": categ[0] if categ else None},
            )

        return {
            "external_code": f"ODOO-PROD-{product['id']}",
            "name": product["name"],
            "status": "active",
            "product_type": PRODUCT_TYPE,
            "product_category": {"id": category_esuite_id},
            "base_uom": self._resolve_uom(uom[1] if uom else ""),
            "cost": product.get("standard_price") or 0,
            "base_price": product.get("list_price") or 0,
            "currency": CURRENCY,
        }
