from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError

# Referensi eSuite yang diisi manual (mirip ADMINISTRATIVE_AREA di Branch) --
# nilai-nilai ini TIDAK datang dari Odoo, itu master data milik eSuite sendiri.
# Cara isi: GET /currency dan GET /product-type ke sandbox, cari baris yang
# cocok, copy id-nya ke sini.
#
# TODO: isi ID sebelum push dites ke sandbox.
CURRENCY = {"id": "6a695cc1917e8fc836359505"}  # IDR, dari GET /currency
PRODUCT_TYPE = {"id": "664191ad236dfcd5a4000001"}  # "Storable Product" (PD-003), dari GET /product-type

# Mapping UOM: key = nama uom_id di Odoo (di-lowercase), value = id eSuite.
# TODO: isi persis nama UOM yang keluar dari Odoo (lihat payload_sent hasil
# test pertama untuk tau nama aslinya -- jangan tebak dari nama produk),
# lalu isi id eSuite dari hasil GET /uom.
UOM_MAPPING = {
    "units": {"id": "664219e2236dfcd5a400001a"},  # UM-0001, dari GET /uom
    "kg": {"id": "664219e2236dfcd5a4000015"},  # Kilogram / UM-0006, dari GET /uom
    "pcs": {"id": ""},
    "pack": {"id": ""},
}


class ProductSyncService:
    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(self, event: str = "upsert"):
        products = self.odoo.get_products()

        # REVISI 5 Agustus 2026: filter free_qty > 0 DIHAPUS dari sini.
        # Keputusan bisnis: produk dengan free_qty = 0 tetap disync & tetap
        # ditampilkan di eSuite (asumsi: stok belum diupdate / masih proses
        # produksi, tapi tetap boleh ditawarkan sales -- bukan berarti tidak
        # boleh dijual). Stok "Free to Use" tetap dikirim apa adanya (termasuk
        # 0) lewat entity Stock Matrix terpisah (lihat CONFIG_NOTES.md) --
        # jadi eSuite tetap tahu stok aktualnya, cuma produknya tidak
        # disembunyikan dari katalog.
        # Filter yang MASIH berlaku: category Saleable + list_price > 0
        # (domain Odoo, di odoo_client.py::get_products()).

        if not products:
            raise ValidationError("Tidak ada produk Saleable ditemukan di Odoo")

        category_id_map = self._resolve_category_ids(products)

        payload = [self._to_esuite_payload(p, category_id_map) for p in products]
        esuite_result = self.esuite.push("product", event=event, data=payload)

        return {
            "synced_count": len(payload),
            "external_codes": [item["external_code"] for item in payload],
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _resolve_category_ids(self, products: list) -> dict:
        """
        KHUSUS entity Product Category: dicek langsung dari response nyata,
        GET /product-category eSuite TIDAK balikin external_code sama
        sekali (beda dari Branch/Warehouse yang balikin, walau posisinya
        beda-beda). Jadi matching di sini terpaksa pakai NAME, bukan
        external_code seperti pola Warehouse->Branch.

        Struktur khusus entity ini: info kategori asli ada nested di
        dalam key "product_category" tiap record, bukan di top-level.

        Risiko: kalau ada 2 category Odoo dengan nama leaf sama persis,
        bisa salah match. Sejauh ini nama-nama kategori di bawah Saleable
        unik, tapi ini best-effort, bukan garansi -- lihat CONFIG_NOTES.md.

        Return: {odoo_category_id: esuite_category_id}
        """
        odoo_categ_ids = list({p["categ_id"][0] for p in products if p.get("categ_id")})
        odoo_name_by_id = self.odoo.get_categories_by_ids(odoo_categ_ids)

        esuite_id_by_name = {}
        page = 1
        limit = 100

        while True:
            pulled = self.esuite.pull("product-category", page=page, limit=limit)
            records = pulled.get("data") or []

            for r in records:
                cat = r.get("product_category") or {}
                name = cat.get("name")
                if name:
                    esuite_id_by_name[name] = cat.get("id")

            meta = pulled.get("meta") or {}
            total_page = meta.get("total_page", 1)
            if page >= total_page:
                break
            page += 1

        result = {}
        for odoo_id, name in odoo_name_by_id.items():
            esuite_id = esuite_id_by_name.get(name)
            if esuite_id:
                result[odoo_id] = esuite_id

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
