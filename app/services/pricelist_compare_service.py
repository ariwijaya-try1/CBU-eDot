from app.clients.esuite_client import EsuiteClient
from app.clients.odoo_client import OdooClient
from app.core.exceptions import NotFoundError, ValidationError

# Prefix external_code -- HARUS sama dgn pricelist_sync_service.py /
# product_sync_service.py / customer_sync_service.py.
PRICELIST_PREFIX = "ODOO-PRICELIST-"
PRODUCT_PREFIX = "ODOO-PROD-"
PARTNER_PREFIX = "ODOO-PARTNER-"

# Page size pull GET /pricelists eSuite (tiap record pricelist bisa bawa
# ratusan produk, jadi tidak dibesarkan supaya response per halaman tetap kecil).
ESUITE_PAGE_SIZE = 50


class PricelistCompareService:
    """
    🆕 23 Oktober 2026 -- DIAGNOSTIC READ-ONLY (tidak push apa pun).
    Bandingkan harga 1+ produk (cari by nama/kode) antara pricelist Odoo
    (product.pricelist.item) dan pricelist eSuite (GET /pricelists,
    products[].variant[].store_price). Dibuat utk tracing kasus field test
    "harga app beda dgn Odoo" (BINTANG SUPERMARKET HAYAM WURUK), krn UI
    pricelist Odoo tidak bisa search produk.

    Mode:
    - customer diisi -> hanya pricelist customer itu (property_product_pricelist
      company-aware, sama logic /sync/customers).
    - customer kosong -> semua pricelist Odoo yang memuat produk itu.
    Pricelist eSuite yang memuat produk tapi TIDAK ada di daftar Odoo di atas
    dilaporkan terpisah (esuite_only) -- kandidat "harga tertimpa".
    """

    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def compare(self, product_name: str, customer: str | None = None, product_limit: int = 5) -> dict:
        product_name = (product_name or "").strip()
        if len(product_name) < 3:
            raise ValidationError("product_name minimal 3 karakter")

        products = self.odoo.get_products_raw(limit=product_limit, name=product_name)
        if not products:
            raise NotFoundError(
                "Produk tidak ditemukan di Odoo (name ilike, produk aktif)",
                details={"product_name": product_name},
            )

        customer_info = self._resolve_customer(customer) if customer else None

        # --- Odoo: baris harga per produk ---
        odoo_rows = {}  # product_id -> list baris
        pricelist_ids = set()
        for p in products:
            items = self.odoo.get_pricelist_items(product_tmpl_id=p["product_tmpl_id"][0])
            # Item level variant (applied_on=0_product_variant) -- jarang di CBU, tetap dicek.
            items += [i for i in self.odoo.get_pricelist_items(product_id=p["id"])
                      if i["id"] not in {x["id"] for x in items}]
            if customer_info:
                pl_id = customer_info.get("odoo_pricelist_id")
                items = [i for i in items if i["pricelist_id"] and i["pricelist_id"][0] == pl_id]
            odoo_rows[p["id"]] = items
            pricelist_ids.update(i["pricelist_id"][0] for i in items if i.get("pricelist_id"))

        if customer_info and customer_info.get("odoo_pricelist_id"):
            pricelist_ids.add(customer_info["odoo_pricelist_id"])

        # Pricelist aktif di Odoo (search_read default skip yang di-archive).
        active_pl = {pl["id"] for pl in self.odoo.get_pricelists(ids=list(pricelist_ids))} if pricelist_ids else set()

        # --- eSuite: 1x scan semua pricelist, ambil entri produk yang dicari ---
        wanted_codes = {f"{PRODUCT_PREFIX}{p['id']}" for p in products}
        esuite_hits, esuite_pricelist_codes = self._scan_esuite(wanted_codes)

        results = []
        for p in products:
            code = f"{PRODUCT_PREFIX}{p['id']}"
            hits = esuite_hits.get(code, [])
            rows = []
            odoo_codes = set()

            for item in odoo_rows[p["id"]]:
                pl_code = f"{PRICELIST_PREFIX}{item['pricelist_id'][0]}"
                odoo_codes.add(pl_code)
                odoo_price = item.get("fixed_price") if item.get("compute_price") == "fixed" else None
                es = [h for h in hits if h["pricelist_external_code"] == pl_code]
                rows.append(self._row(item, pl_code, odoo_price, es, pl_code in esuite_pricelist_codes,
                                      item["pricelist_id"][0] in active_pl))

            # Customer mode tapi produk tidak punya baris di pricelist customer.
            if customer_info and not rows and customer_info.get("odoo_pricelist_id"):
                pl_code = f"{PRICELIST_PREFIX}{customer_info['odoo_pricelist_id']}"
                odoo_codes.add(pl_code)
                es = [h for h in hits if h["pricelist_external_code"] == pl_code]
                rows.append({
                    "pricelist_external_code": pl_code,
                    "odoo_pricelist": customer_info.get("odoo_pricelist_name"),
                    "odoo_price": None,
                    "odoo_note": "produk TIDAK punya baris di pricelist ini (Odoo pakai harga dasar/list_price)",
                    "esuite_pricelist": es[0]["pricelist_name"] if es else None,
                    "esuite_price": [h["store_price"] for h in es] or None,
                    "status": "tidak_ada_di_pricelist_odoo",
                })

            esuite_only = [
                {k: h[k] for k in ("pricelist_external_code", "pricelist_name", "store_price",
                                   "base_price", "customer_group", "status")}
                for h in hits if h["pricelist_external_code"] not in odoo_codes
            ]
            # Customer mode: tampilkan semua pricelist eSuite lain yg memuat produk
            # (bisa banyak). Mode tanpa customer: sudah tercakup di rows.
            results.append({
                "product_external_code": code,
                "product_name": p["name"],
                "default_code": p.get("default_code") or "",
                "uom": p["uom_id"][1] if p.get("uom_id") else "",
                "odoo_list_price": p.get("list_price"),
                "comparisons": rows,
                "esuite_only": esuite_only,
            })

        return {
            "product_name": product_name,
            "customer": customer_info,
            "products_found": len(products),
            "product_limit": product_limit,
            "note": (
                "Harga Odoo = fixed_price pricelist item (belum termasuk pajak). "
                "Harga eSuite = products[].variant[].store_price GET /pricelists. "
                "Kalau harga di app beda dgn keduanya, cek PPN/UoM/cache app."
            ),
            "results": results,
        }

    # ------------------------------------------------------------------
    def _row(self, item, pl_code, odoo_price, es_hits, pl_in_esuite, pl_active):
        if odoo_price is None:
            status = "odoo_bukan_fixed"
        elif not pl_in_esuite:
            status = "pricelist_tidak_ada_di_esuite"
        elif not es_hits:
            status = "produk_tidak_ada_di_pricelist_esuite"
        elif len(es_hits) > 1:
            status = "dobel_di_esuite"
        elif es_hits[0]["store_price"] == odoo_price:
            status = "sama"
        else:
            status = "beda"
        return {
            "pricelist_external_code": pl_code,
            "odoo_pricelist": item["pricelist_id"][1],
            "odoo_pricelist_active": pl_active,
            "odoo_price": odoo_price,
            "odoo_compute_price": item.get("compute_price"),
            "odoo_min_quantity": item.get("min_quantity"),
            "odoo_date_start": item.get("date_start") or None,
            "odoo_date_end": item.get("date_end") or None,
            "esuite_pricelist": es_hits[0]["pricelist_name"] if es_hits else None,
            "esuite_price": [h["store_price"] for h in es_hits] or None,
            "esuite_base_price": es_hits[0]["base_price"] if es_hits else None,
            "esuite_customer_group": es_hits[0]["customer_group"] if es_hits else None,
            "status": status,
        }

    def _resolve_customer(self, customer: str) -> dict:
        raw = customer.strip().upper().replace(PARTNER_PREFIX, "")
        try:
            partner_id = int(raw)
        except ValueError:
            raise ValidationError("customer harus ODOO-PARTNER-<id> atau id angka", details={"customer": customer})

        partner = self.odoo.get_partner_basic(partner_id)
        if not partner:
            raise NotFoundError("Customer tidak ditemukan di Odoo", details={"customer": customer})

        company = partner.get("company_id")
        pricelist_id = None
        if company:
            # property_product_pricelist company-dependent -> resolve dgn context
            # company partner (sama logic /sync/customers).
            pricelist_id = self.odoo.get_pricelist_by_company({company[0]: [partner_id]}).get(partner_id)
        elif partner.get("property_product_pricelist"):
            pricelist_id = partner["property_product_pricelist"][0]

        pricelist_name = None
        if pricelist_id:
            pls = self.odoo.get_pricelists(ids=[pricelist_id])
            pricelist_name = pls[0]["name"] if pls else None
        return {
            "external_code": f"{PARTNER_PREFIX}{partner_id}",
            "name": partner.get("name"),
            "company": company[1] if company else None,
            "odoo_pricelist_id": pricelist_id,
            "odoo_pricelist_name": pricelist_name,
        }

    def _scan_esuite(self, wanted_codes: set[str]):
        """
        Pull SEMUA pricelist eSuite (paging), kumpulkan entri products[] yang
        external_code-nya dicari. Return (hits_by_product_code, set pricelist codes).
        Struktur dibaca defensif ("products"/"product", "variant"/"variants")
        krn schema GET /pricelists belum pernah divalidasi live per field.
        """
        hits: dict[str, list] = {}
        pricelist_codes: set[str] = set()
        page, total_page = 1, 1
        while page <= total_page:
            result = self.esuite.pull("pricelists", page=page, limit=ESUITE_PAGE_SIZE)
            for pl in result.get("data") or []:
                pl_code = pl.get("external_code") or ""
                pricelist_codes.add(pl_code)
                groups = [g.get("name") for g in (pl.get("customer_group") or []) if isinstance(g, dict)]
                for prod in pl.get("products") or pl.get("product") or []:
                    code = prod.get("external_code")
                    if code not in wanted_codes:
                        continue
                    variants = prod.get("variant") or prod.get("variants") or [{}]
                    v = variants[0] if variants else {}
                    hits.setdefault(code, []).append({
                        "pricelist_external_code": pl_code,
                        "pricelist_name": pl.get("name"),
                        "status": pl.get("status"),
                        "customer_group": groups,
                        "store_price": v.get("store_price", prod.get("min_store_price")),
                        "base_price": v.get("base_price", prod.get("min_base_price")),
                    })
            total_page = (result.get("meta") or {}).get("total_page", page)
            page += 1
        return hits, pricelist_codes
