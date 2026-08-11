import hashlib

from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError

# Referensi eSuite yang diisi manual (mirip ADMINISTRATIVE_AREA di Branch) --
# nilai-nilai ini TIDAK datang dari Odoo, itu master data milik eSuite sendiri.
CURRENCY = {"id": "6a695cc1917e8fc836359505"}  # IDR, dari GET /currency
PRODUCT_TYPE = {
    "id": "664191ad236dfcd5a4000001"
}  # "Storable Product" (PD-003), dari GET /product-type

# Mapping UOM: key = nama uom_id di Odoo (di-lowercase), value = id eSuite.
# TERKONFIRMASI & SELESAI (5-7 Agustus 2026): cuma "units" & "kg" yang dipakai
# di seluruh 731 produk Saleable -- "pcs"/"pack" (dugaan awal diskusi bisnis)
# TIDAK dipakai literal sebagai uom_id di Odoo. Kedua id di bawah sudah
# divalidasi cocok persis terhadap GET /uom eSuite (26 UOM master, dicek
# 7 Agustus 2026) -- tidak ada entity "Pieces"/"Pack" sama sekali di sana,
# jadi kalaupun nanti Odoo ternyata pakai istilah itu, perlu tanya vendor dulu
# mau dipetakan ke UOM eSuite yang mana (bukan sekadar isi ID yang belum ada).
UOM_MAPPING = {
    "units": {"id": "664219e2236dfcd5a400001a"},  # UM-0001 "Units", dari GET /uom
    "kg": {"id": "664219e2236dfcd5a4000015"},  # UM-0006 "Kilogram", dari GET /uom
}


class ProductSyncService:
    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(self, event: str = "upsert", limit: int | None = None):
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

        total_matched = len(products)

        # limit -- TEMPORARY diagnostic aid (7 Agustus 2026), pola sama persis
        # dengan customer_sync_service.py (lihat komentar di sana untuk
        # konteks lengkap: dipakai buat isolasi bertahap kalau ada masalah
        # push full batch, mis. 502 Bad Gateway). Default None -> behavior
        # sama seperti sebelumnya (semua produk).
        if limit is not None:
            products = products[:limit]

        category_id_map = self._resolve_category_ids(products)

        payload = [self._to_esuite_payload(p, category_id_map) for p in products]
        esuite_result = self.esuite.push("product", event=event, data=payload)

        return {
            "synced_count": len(payload),
            "total_matched_in_odoo": total_matched,
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
                details={
                    "odoo_uom_name": uom_name,
                    "known_mappings": list(UOM_MAPPING.keys()),
                },
            )
        return mapped

    def _generate_uom_level_id(self, external_code: str, uom_id: str) -> str:
        """
        id untuk tiap item uom_levels[] -- WAJIB diisi. Dikonfirmasi 7 Agustus
        2026 lewat GET /api/debug/pull/product (data production real, 1247
        produk): tanpa id, eSuite terima push (status 200) tapi diam-diam
        TIDAK menyimpan uom_levels sama sekali (balik uom_levels: [] kosong
        saat di-GET lagi). Detail bukti & sisa pertanyaan terbuka (format id,
        risiko duplikasi saat re-upsert) ada di CONFIG_NOTES.md.

        Digenerate DETERMINISTIK (bukan random ULID) dari external_code+uom,
        supaya id yang sama selalu keluar untuk kombinasi produk+uom yang
        sama tiap kali di-upsert ulang -- menghindari kemungkinan uom_levels
        numpuk/duplikat kalau eSuite ternyata append array alih-alih replace
        (belum dites, jadi ini pendekatan aman/konservatif).
        """
        raw = f"{external_code}:{uom_id}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:26].upper()

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

        external_code = f"ODOO-PROD-{product['id']}"
        base_uom = self._resolve_uom(uom[1] if uom else "")

        return {
            "external_code": external_code,
            "name": product["name"],
            "status": "active",
            "product_type": PRODUCT_TYPE,
            "product_category": {"id": category_esuite_id},
            "base_uom": base_uom,
            # purchase_uom & uom_levels -- REVISI 5 Agustus 2026, ditambahkan setelah
            # dicek langsung ke Postman collection eSuite (contoh payload POST /product).
            # Odoo kami tidak punya konsep purchase UOM terpisah dari sales/base UOM,
            # dan tidak ada packaging multi-level (tiap ukuran = product.product id
            # sendiri, lihat CONFIG_NOTES.md), jadi keduanya diisi konsisten dari
            # base_uom yang sama -- 1 level, qty=1, convertion=1.
            "purchase_uom": base_uom,
            # "id" -- REVISI 7 Agustus 2026, lihat _generate_uom_level_id() di atas
            # untuk alasan lengkap kenapa field ini ditambahkan & kenapa deterministik.
            "uom_levels": [
                {
                    "id": self._generate_uom_level_id(external_code, base_uom["id"]),
                    "uom": base_uom,
                    "qty": 1,
                    "convertion": 1,
                }
            ],
            # "cost" dikirim sebagai 1 (Rp 1) fixed -- BUKAN dari standard_price
            # (instruksi boss, 6 Agustus 2026: data cost/harga beli asli tidak
            # boleh dikirim ke eSuite, cuma base_price/harga jual yang boleh).
            # Riwayat revisi field ini (semua 6 Agustus 2026):
            #   1) key dihapus total dari payload -> value lama nyangkut di UI.
            #   2) diganti kirim eksplisit 0 -> TETAP nyangkut, ternyata eSuite
            #      treat 0 sebagai falsy dan skip update (bug backend eSuite,
            #      dikonfirmasi via test manual: cost=1 -> UI berubah,
            #      cost=0 -> UI tidak berubah sama sekali).
            #   3) (sekarang) pakai 1 sebagai sentinel -- bukan nilai cost asli,
            #      cuma workaround supaya bukan falsy dan benar-benar ke-apply.
            #      Efeknya di UI eSuite: "Rp 1", bukan "Rp 0" -- disepakati user
            #      sebagai kompromi sampai IT eSuite kasih cara resmi clear ke 0.
            # Field standard_price tetap diambil dari Odoo
            # (odoo_client.py::get_products()) tapi tidak pernah dipetakan ke
            # sini. Lihat CONFIG_NOTES.md.
            "cost": 1,
            "base_price": product.get("list_price") or 0,
            "currency": CURRENCY,
        }
