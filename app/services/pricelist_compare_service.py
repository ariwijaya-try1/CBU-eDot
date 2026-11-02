from app.clients.esuite_client import EsuiteClient
from app.clients.odoo_client import OdooClient
from app.core.exceptions import AppError, NotFoundError, ValidationError

# Prefix external_code -- HARUS sama dgn pricelist_sync_service.py /
# product_sync_service.py / customer_sync_service.py.
PRICELIST_PREFIX = "ODOO-PRICELIST-"
PRODUCT_PREFIX = "ODOO-PROD-"
PARTNER_PREFIX = "ODOO-PARTNER-"

# Page size AWAL pull GET /pricelists eSuite. 23 Oktober 2026 (live): page 50
# gagal "grpc: received message larger than max (4394601 vs. 4194304)" -- eSuite
# batasi response gRPC 4MB, tiap pricelist bawa ratusan produk. Sekarang mulai
# 8 & otomatis dibagi 2 tiap kena error ukuran (lihat _scan_esuite()).
# WAJIB pangkat 2 (8/4/2/1) supaya offset tetap kelipatan page size baru.
ESUITE_PAGE_SIZE = 8

# Key nested yang BUKAN milik header pricelist (dilewati saat cari external_code).
PL_SKIP_KEYS = {"products", "product", "branch", "customer_group", "sales_channel", "currency", "effective_date"}


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

    def compare(
        self, product_name: str, customer: str | None = None, product_limit: int = 5, diagnostic: bool = False
    ) -> dict:
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
        odoo_pls = self.odoo.get_pricelists(ids=list(pricelist_ids)) if pricelist_ids else []
        active_pl = {pl["id"] for pl in odoo_pls}
        # Fallback cocokkan pricelist eSuite by NAMA (23 Okt 2026: live GET
        # /pricelists tidak punya external_code top-level). Nama dikirim apa
        # adanya oleh /sync/pricelist (pricelist["name"]).
        name_to_code = {(pl.get("name") or "").strip().lower(): f"{PRICELIST_PREFIX}{pl['id']}" for pl in odoo_pls}

        # --- eSuite: produk (id + base_price) by external_code (top-level, terbukti) ---
        wanted_codes = {f"{PRODUCT_PREFIX}{p['id']}" for p in products}
        esuite_products = self.esuite.find_by_external_codes("product", wanted_codes)
        id_to_code = {rec["id"]: code for code, rec in esuite_products.items() if rec.get("id")}

        # --- eSuite: 1x scan semua pricelist, ambil entri produk yang dicari ---
        esuite_hits, esuite_pricelist_codes, esuite_unreadable, esuite_diag = self._scan_esuite(
            wanted_codes, id_to_code, name_to_code
        )

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

            # Kalau ada pricelist eSuite yang tidak terbaca (>4MB), "tidak ada"
            # belum pasti -- bisa jadi pricelist itu yang tidak terbaca.
            if esuite_unreadable:
                for r in rows:
                    if r["status"] == "pricelist_tidak_ada_di_esuite":
                        r["status"] = "pricelist_tidak_ditemukan_ada_yang_tidak_terbaca"

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
                "esuite_product_found": code in esuite_products,
                "esuite_product_base_price": (esuite_products.get(code) or {}).get("base_price"),
                "comparisons": rows,
                "esuite_only": esuite_only,
            })

        if not diagnostic:
            return self._concise(customer_info, results, esuite_unreadable, len(esuite_pricelist_codes))

        return {
            "product_name": product_name,
            "customer": customer_info,
            "products_found": len(products),
            "esuite_pricelists_scanned": len(esuite_pricelist_codes),
            "esuite_scan_diag": esuite_diag,
            # Posisi pricelist eSuite (urutan GET /pricelists) yang > 4MB walau
            # dibaca 1 per halaman -- hasil compare utk pricelist ini TIDAK lengkap.
            "esuite_pricelists_unreadable": esuite_unreadable,
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

    def _scan_esuite(self, wanted_codes: set[str], id_to_code: dict, name_to_code: dict):
        """
        Pull SEMUA pricelist eSuite (paging), kumpulkan entri products[] yang
        external_code-nya dicari. Return (hits_by_product_code, set pricelist codes,
        list offset pricelist yang tidak bisa dibaca).
        Struktur dibaca defensif ("products"/"product", "variant"/"variants")
        krn schema GET /pricelists belum pernah divalidasi live per field.

        Paging berbasis offset: kalau 1 halaman > 4MB (error gRPC ResourceExhausted),
        page size dibagi 2 lalu halaman yang sama diulang. Offset selalu kelipatan
        page size baru (size awal dibagi 2 berulang), jadi page = offset // size + 1
        tetap tepat. Kalau size 1 pun masih gagal, pricelist itu dilewati & dilaporkan.
        """
        hits: dict[str, list] = {}
        pricelist_codes: set[str] = set()
        unreadable: list[int] = []
        # Diagnostik (23 Okt 2026): live pertama cuma "scanned 1" -- catat jumlah
        # record & jejak paging supaya ketahuan scan berhenti di mana.
        diag = {
            "records_read": 0, "pages": [], "empty_external_code": 0, "sample_structure": None,
            "pricelist_matched_by_name": 0, "product_matched_by_id": 0,
        }
        size = ESUITE_PAGE_SIZE
        offset = 0
        while True:
            page = offset // size + 1
            try:
                result = self.esuite.pull("pricelists", page=page, limit=size)
            except AppError as e:
                too_large = "ResourceExhausted" in e.message or "larger than max" in e.message
                if not too_large:
                    raise
                if size > 1:
                    size //= 2
                    continue
                unreadable.append(offset + 1)  # posisi pricelist ke-n (1-based)
                offset += 1
                continue

            data = result.get("data") or []
            total_page = (result.get("meta") or {}).get("total_page")
            diag["records_read"] += len(data)
            if len(diag["pages"]) < 60:
                diag["pages"].append({"page": page, "limit": size, "got": len(data), "total_page": total_page})
            if data and diag["sample_structure"] is None:
                diag["sample_structure"] = self._describe(data[0])
            for pl in data:
                pl_code = pl.get("external_code") or self._deep_find(pl, "external_code", PL_SKIP_KEYS) or ""
                if not pl_code:
                    diag["empty_external_code"] += 1
                    pl_code = name_to_code.get((pl.get("name") or "").strip().lower(), "")
                    if pl_code:
                        diag["pricelist_matched_by_name"] += 1
                pricelist_codes.add(pl_code)
                groups = [g.get("name") for g in (pl.get("customer_group") or []) if isinstance(g, dict)]
                for prod in pl.get("products") or pl.get("product") or []:
                    code = prod.get("external_code")
                    if code not in wanted_codes and prod.get("id") in id_to_code:
                        # Fallback: entri produk cuma bawa id eSuite.
                        code = id_to_code[prod["id"]]
                        diag["product_matched_by_id"] += 1
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
            # Berhenti kalau halaman kosong, atau halaman tidak penuh DAN sudah
            # halaman terakhir menurut meta.total_page (kalau ada).
            if not data:
                break
            if len(data) < size and (total_page is None or page >= total_page):
                break
            offset += size
            # Naikkan lagi page size (maks ESUITE_PAGE_SIZE) setelah lolos, supaya
            # 1 pricelist besar tidak bikin sisa scan jalan 1-per-halaman.
            if size < ESUITE_PAGE_SIZE and offset % (size * 2) == 0:
                size *= 2
        return hits, pricelist_codes, unreadable, diag

    @staticmethod
    def _deep_find(value, key: str, skip: set, depth: int = 0):
        """Cari key di dict bertingkat (bukan di dalam list / key di skip), maks 3 level."""
        if depth > 3 or not isinstance(value, dict):
            return None
        if value.get(key):
            return value[key]
        for k, v in value.items():
            if k in skip:
                continue
            found = PricelistCompareService._deep_find(v, key, skip, depth + 1)
            if found:
                return found
        return None

    @staticmethod
    def _concise(customer_info, results, unreadable, scanned) -> dict:
        """
        Output ringkas (diagnostic=false, DEFAULT) -- 1 baris per produk per
        pricelist: pricelist + harga Odoo, pricelist + harga eDot, status, keterangan.
        """
        out = []
        for r in results:
            produk = f"[{r['default_code']}] {r['product_name']}" if r["default_code"] else r["product_name"]
            base_edot = r["esuite_product_base_price"]
            for c in r["comparisons"]:
                pl_name = c.get("odoo_pricelist")
                prices = c.get("esuite_price") or []
                edot_price = prices[0] if prices else None
                st = c["status"]
                if st == "tidak_ada_di_pricelist_odoo":
                    odoo_price = r["odoo_list_price"]
                    ket = f"tidak ada di pricelist {pl_name} -> Odoo pakai harga dasar"
                    if edot_price is None:
                        edot_price = base_edot
                        ket += "; eDot juga tidak ada di pricelist -> harga dasar eDot"
                    else:
                        ket += "; TAPI di eDot ada di pricelist ini"
                elif st == "produk_tidak_ada_di_pricelist_esuite":
                    odoo_price = c["odoo_price"]
                    edot_price = base_edot
                    ket = f"ada di pricelist Odoo {pl_name}, TIDAK ada di pricelist eDot -> eDot kemungkinan pakai harga dasar"
                elif st.startswith("pricelist_tidak"):
                    odoo_price = c["odoo_price"]
                    ket = f"pricelist {pl_name} tidak ditemukan di eDot"
                elif st == "odoo_bukan_fixed":
                    odoo_price = None
                    ket = f"baris Odoo di {pl_name} bukan harga fixed (tidak dikirim bridge)"
                else:
                    odoo_price = c["odoo_price"]
                    ket = "ada di 2 pricelist, harga dobel di eDot" if st == "dobel_di_esuite" else ""
                if not r["esuite_product_found"]:
                    ket = (ket + "; " if ket else "") + "produk belum ada di eDot"
                hasil = "sama" if odoo_price is not None and edot_price == odoo_price else "beda"
                out.append({
                    "produk": produk,
                    "pricelist_odoo": pl_name,
                    "harga_odoo": odoo_price,
                    "pricelist_edot": c.get("esuite_pricelist"),
                    "harga_edot": edot_price,
                    "hasil": hasil,
                    "keterangan": ket or ("harga sama" if hasil == "sama" else "harga beda"),
                })
            # Mode customer (keputusan user 23 Okt 2026): HANYA pricelist customer
            # yang ditanyakan -- pricelist eDot lain tidak ditampilkan (tetap ada
            # di diagnostic=true, field esuite_only).
            for e in ([] if customer_info else r["esuite_only"]):
                out.append({
                    "produk": produk,
                    "pricelist_odoo": None,
                    "harga_odoo": None,
                    "pricelist_edot": e["pricelist_name"],
                    "harga_edot": e["store_price"],
                    "hasil": "hanya_di_edot",
                    "keterangan": f"pricelist eDot memuat produk ini tapi Odoo tidak (customer group: {', '.join(e['customer_group']) or '-'})",
                })
        warnings = []
        if unreadable:
            warnings.append(f"{len(unreadable)} pricelist eDot tidak terbaca (>4MB), hasil bisa tidak lengkap")
        if scanned <= 1:
            warnings.append("pricelist eDot tidak bisa dicocokkan (external_code/nama) -- jalankan diagnostic=true")
        return {
            "customer": f"{customer_info['name']} ({customer_info['external_code']})" if customer_info else None,
            "pricelist_customer_odoo": customer_info.get("odoo_pricelist_name") if customer_info else None,
            "catatan": "Harga Odoo belum termasuk pajak. Kalau app beda tepat 11% = PPN.",
            "peringatan": warnings,
            "hasil": out,
        }

    @staticmethod
    def _describe(value, depth: int = 0):
        """
        🆕 23 Okt 2026 -- ringkas STRUKTUR 1 record GET /pricelists (key + tipe,
        list cuma elemen pertama, string dipotong) utk cari letak external_code
        (live: 268/268 pricelist tanpa external_code top-level).
        """
        if depth > 7:
            return "..."
        if isinstance(value, dict):
            return {k: PricelistCompareService._describe(v, depth + 1) for k, v in value.items()}
        if isinstance(value, list):
            return [PricelistCompareService._describe(value[0], depth + 1), f"(+{len(value) - 1} item)"] if value else []
        if isinstance(value, str):
            return value[:60]
        return value
