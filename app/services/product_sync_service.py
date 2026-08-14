from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import AppError, ValidationError
from app.core.sync_logger import log_sync_result

# Referensi eSuite yang diisi manual (mirip ADMINISTRATIVE_AREA di Branch) --
# nilai-nilai ini TIDAK datang dari Odoo, itu master data milik eSuite sendiri.
CURRENCY = {"id": "6a695cc1917e8fc836359505"}  # IDR, dari GET /currency
PRODUCT_TYPE = {
    "id": "664191ad236dfcd5a4000001"
}  # "Storable Product" (PD-003), dari GET /product-type

# Product UOM Level -- ENTITY TERPISAH dari UOM master (dikonfirmasi vendor
# 11 Agustus 2026 via PDF Sync Document section 9.4; "id" contoh yang dikira
# dokumentasi ternyata id ASLI record "Low" dari GET /uom-level).
# KEPUTUSAN (12 Agustus 2026, dikonfirmasi user): reuse Level "Low" untuk
# SEMUA produk, sementara -- CBU cuma pakai 2 UOM fisik (units & kg), tidak
# ada kebutuhan tier packaging beneran (Karton/Pack/Pcs dst), jadi 1 Level
# generic cukup. Kalau nanti kebutuhan tier berubah, bikin Level baru lewat
# POST /uom-level dan ganti constant ini.
PRODUCT_UOM_LEVEL = {"id": "01KZ5895R0T1JTR4QTVFGE3GHF"}  # "Low", dari GET /uom-level

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

# Prefix external_code Product -- dipakai juga buat parse balik id Odoo dari
# external_code (fitur "upsert by external_code", 12 Agustus 2026).
EXTERNAL_CODE_PREFIX = "ODOO-PROD-"

# Default batch_size KALAU batch_size tidak diisi -- diisi None DI SINI
# (bukan angka fixed kayak customer_sync_service.py) supaya behavior lama
# (1 request buat semua produk sekaligus, sudah tervalidasi ke sandbox
# 1247 produk tanpa masalah 502 seperti kasus Customer) TETAP SAMA PERSIS
# kalau caller tidak isi batch_size -- minimal invasive, tidak mengubah
# behavior existing yang sudah jalan.
DEFAULT_BATCH_SIZE = None


class ProductSyncService:
    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(
        self,
        event: str = "upsert",
        limit: int | None = None,
        batch_size: int | None = None,
        external_codes: str | None = None,
        with_variant: bool = False,
        include_payload: bool = False,
    ):
        odoo_ids = self._parse_external_codes(external_codes) if external_codes else None
        products = self.odoo.get_products(ids=odoo_ids)

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
            raise ValidationError("Tidak ada produk Saleable ditemukan di Odoo (cek juga external_codes kalau diisi)")

        total_matched = len(products)

        # limit -- TEMPORARY diagnostic aid (7 Agustus 2026), pola sama persis
        # dengan customer_sync_service.py (lihat komentar di sana untuk
        # konteks lengkap: dipakai buat isolasi bertahap kalau ada masalah
        # push full batch, mis. 502 Bad Gateway). Default None -> behavior
        # sama seperti sebelumnya (semua produk).
        if limit is not None:
            products = products[:limit]

        category_id_map = self._resolve_category_ids(products)

        # with_variant -- REVISI 13 Agustus 2026 (rombak total). Sebelumnya
        # push "/product-variant" TERPISAH setelah "/product" -- vendor
        # konfirmasi ini SALAH untuk tujuan tampil di halaman produk (tab
        # "Attribute & Variant" baca dari field "variants[]" yang di-EMBED
        # di dalam dokumen /product itu sendiri, bukan dari collection
        # /product-variant berdiri sendiri). Sekarang variants[] di-embed
        # LANGSUNG di payload /product, tidak ada push terpisah lagi.
        #
        # WAJIB resolve id variant yang SUDAH ADA dulu sebelum push --
        # matching update di sisi eSuite pakai "id", BUKAN "external_code".
        # Kalau id dikosongkan tiap kali push, eSuite generate variant BARU
        # tiap sync -> duplikat menumpuk (instruksi eksplisit vendor,
        # 13 Agustus 2026). Lihat SESSION_TRANSFER_NOTE.md poin 25.
        existing_variant_ids = {}
        if with_variant:
            codes_wanted = {f"{EXTERNAL_CODE_PREFIX}{p['id']}" for p in products}
            existing_variant_ids = self._resolve_existing_variant_ids(codes_wanted)

        payload = [
            self._to_esuite_payload(p, category_id_map, with_variant, existing_variant_ids)
            for p in products
        ]

        # Batching -- REVISI 12 Agustus 2026, opsional (beda dari Customer yang
        # SELALU batch). Kalau batch_size tidak diisi, 1 batch = semua produk
        # (behavior lama, tidak berubah). Kalau diisi, dipecah sama seperti
        # customer_sync_service.py -- 1 batch gagal TIDAK menggagalkan batch lain.
        size = batch_size or len(payload)
        batches = [payload[i : i + size] for i in range(0, len(payload), size)] or [[]]

        batch_results = []
        synced_count = 0
        failed_count = 0

        for idx, batch in enumerate(batches, start=1):
            try:
                esuite_result = self.esuite.push("product", event=event, data=batch)
                batch_entry = {
                    "batch": idx,
                    "size": len(batch),
                    "status": "success",
                    "external_codes": [item["external_code"] for item in batch],
                    "esuite_response": esuite_result,
                }
                # payload_sent -- REVISI 13 Agustus 2026: sekarang OPT-IN
                # (default False), bukan lagi selalu tampil. Alasan: Swagger
                # jadi lambat kalau batch besar (payload penuh tiap produk
                # ikut di-render browser). Aturan FIXED lama poin 2 ("selalu
                # include payload_sent") DIGANTI keputusan baru user --
                # sudah dikonfirmasi & dicatat di SESSION_TRANSFER_NOTE.md
                # poin 20. external_codes tetap selalu tampil (cukup buat
                # tracking mana yang sukses/gagal tanpa payload penuh).
                # Catatan: kalau with_variant=True, "variants[]" sudah
                # ke-embed di tiap item batch -- jadi payload_sent di sini
                # OTOMATIS include variant-nya juga, tidak perlu key terpisah.
                if include_payload:
                    batch_entry["payload_sent"] = batch
                batch_results.append(batch_entry)
                synced_count += len(batch)
            except AppError as e:
                # Pola sama dengan customer_sync_service.py -- di-catch per
                # batch, batch lain tetap lanjut.
                batch_entry = {
                    "batch": idx,
                    "size": len(batch),
                    "status": "failed",
                    "external_codes": [item["external_code"] for item in batch],
                    "error": e.to_dict()["error"],
                }
                if include_payload:
                    batch_entry["payload_sent"] = batch
                batch_results.append(batch_entry)
                failed_count += len(batch)

        result = {
            "total_matched_in_odoo": total_matched,
            "total_sent": len(payload),
            "batch_size": size,
            "batch_count": len(batches),
            "synced_count": synced_count,
            "failed_count": failed_count,
            "batches": batch_results,
        }
        if with_variant:
            # variant_summary -- ganti "variant_sync" lama (13 Agustus 2026).
            # Tidak ada push terpisah lagi buat dilaporkan -- variant sudah
            # ke-embed di payload /product di atas. Ini cuma ringkasan
            # berapa yang linked ke variant id existing (update, aman dari
            # duplikat) vs berapa yang baru (id dikosongkan, eSuite generate).
            result["variant_summary"] = {
                "total": len(payload),
                "linked_to_existing_variant": len(existing_variant_ids),
                "new_variant": len(payload) - len(existing_variant_ids),
            }

        log_sync_result("product", event, result)
        return result

    def _parse_external_codes(self, external_codes: str) -> list[int]:
        """
        Parse "ODOO-PROD-123,ODOO-PROD-456" -> [123, 456] -- dipakai fitur
        "upsert by external_code" (12 Agustus 2026), supaya bisa push 1/
        beberapa produk tertentu saja tanpa nyentuh yang lain. Format harus
        persis sesuai EXTERNAL_CODE_PREFIX (external_code yang KITA generate
        sendiri di _to_esuite_payload(), bukan bebas string apapun).
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

    def _resolve_existing_variant_ids(self, codes_wanted: set[str]) -> dict[str, str]:
        """
        Resolve id variant yang SUDAH ADA di eSuite (by external_code)
        SEBELUM push -- ROMBAK TOTAL 13 Agustus 2026 sesuai instruksi vendor
        (lihat SESSION_TRANSFER_NOTE.md poin 25). Root cause lama: variant
        di-push ke "/product-variant" TERPISAH dari "/product" -- itu cuma
        bikin record "mandiri" yang TIDAK ter-link ke field "variants[]"
        milik produk induknya (makanya kosong di tab "Attribute & Variant"
        halaman Detail Produk). Fix vendor: embed "variants[]" LANGSUNG di
        payload "/product" (lihat _to_esuite_payload()).

        WAJIB resolve dulu -- matching update variant di sisi eSuite pakai
        "id", BUKAN "external_code". Kalau "variants[].id" dikosongkan tiap
        kali push (padahal variant-nya sudah pernah ada), eSuite generate
        variant BARU tiap sync -> duplikat menumpuk. external_code variant
        = SAMA PERSIS dengan external_code product induknya.

        Return: {external_code: variant_id} -- cuma untuk yang SUDAH ADA
        (ketemu di GET /product-variant). external_code yang tidak ada di
        return dict berarti produk baru -- _to_esuite_payload() akan
        kosongkan "variants[0].id" supaya eSuite auto-generate.
        """
        if not codes_wanted:
            return {}
        resolved = self.esuite.find_by_external_codes("product-variant", codes_wanted)
        return {
            code: record["id"]
            for code, record in resolved.items()
            if record and record.get("id")
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

    def _to_esuite_payload(
        self,
        product: dict,
        category_id_map: dict,
        with_variant: bool = False,
        existing_variant_ids: dict | None = None,
    ) -> dict:
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

        payload = {
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
            # "id" -- REVISI 12 Agustus 2026: pendekatan lama (id = base_uom["id"],
            # id UOM master) TERBUKTI SALAH KONSEP & gagal diam-diam di skala penuh
            # (dicek dari GET /product 1250 record: 1245/1250 uom_levels KOSONG).
            # Product UOM Level itu entity terpisah dari UOM master (lihat
            # PRODUCT_UOM_LEVEL di atas + CONFIG_NOTES.md). Sekarang pakai id
            # Level "Low" yang sudah terbukti valid & tersimpan (test manual
            # 12 Agustus, produk ODOO-PROD-18374).
            "uom_levels": [
                {
                    "id": PRODUCT_UOM_LEVEL["id"],
                    "uom": base_uom,
                    "qty": 1,
                    "convertion": 1,
                }
            ],
            # "cost" dikirim sebagai 0 fixed -- BUKAN dari standard_price
            # (instruksi boss, 6 Agustus 2026: data cost/harga beli asli tidak
            # boleh dikirim ke eSuite, cuma base_price/harga jual yang boleh).
            # User maunya null, tapi eSuite render null jadi 0 juga di UI --
            # jadi 0 eksplisit dipakai langsung, tidak ada bedanya secara hasil.
            #
            # ROOT CAUSE FINAL (13 Agustus 2026, mengoreksi dugaan lama di
            # bawah): BUKAN bug falsy-skip di endpoint eSuite. Penyebab
            # sebenarnya ADA DUA, gabungan:
            #   1) uom_levels.id & uom sempat salah (id UOM master dipakai,
            #      padahal harus id Product UOM Level -- lihat komentar di
            #      atas) -- field ini MANDATORY dan harus valid, kalau salah
            #      seluruh record gagal diproses dengan benar oleh eSuite
            #      (bukan cuma uom_levels yang kosong, field lain di record
            #      yang sama termasuk cost ikut tidak ter-apply).
            #   2) Delay yang kelihatan kayak "cost tidak berubah" sebagian
            #      juga karena antrian job async eSuite numpuk pas bulk
            #      insert banyak produk sekaligus (silent queue backlog),
            #      bukan berarti request-nya ditolak/di-skip.
            # Setelah uom_levels.id difix (poin di atas, 12 Agustus 2026) dan
            # uom_levels sudah terbukti valid & tersimpan benar, cost = 0
            # sekarang aman dipakai -- dugaan lama "eSuite treat 0 sebagai
            # falsy" DITARIK, itu cuma efek samping dari record yang gagal
            # diproses gara-gara uom_levels salah, bukan soal value cost itu
            # sendiri.
            # Field standard_price tetap diambil dari Odoo
            # (odoo_client.py::get_products()) tapi tidak pernah dipetakan ke
            # sini. Lihat CONFIG_NOTES.md.
            "cost": 0,
            "base_price": product.get("list_price") or 0,
            "currency": CURRENCY,
        }

        # variants -- EMBED LANGSUNG di payload /product (13 Agustus 2026,
        # rombak sesuai fix vendor -- lihat _resolve_existing_variant_ids()
        # & SESSION_TRANSFER_NOTE.md poin 25). Keputusan bisnis lama tetap
        # berlaku: Product : Product Variant = 1:1 (tidak ada variant asli
        # secara operasional CBU, cuma 1 variant generic per produk).
        #
        # "id": kalau produk ini SUDAH pernah punya variant (ketemu di
        # existing_variant_ids, hasil resolve GET /product-variant by
        # external_code), WAJIB isi id yang sama supaya eSuite UPDATE
        # variant yang sudah ada -- bukan generate baru (matching di sisi
        # eSuite pakai id, BUKAN external_code). Kalau belum pernah ada,
        # dikosongkan ("") -- eSuite auto-generate & langsung link ke
        # product.variants[].
        #
        # Field lain ikut PERSIS skema resmi dari vendor (bukan skema lama
        # /product-variant standalone yang kita pakai sebelumnya) -- TIDAK
        # ADA "base_price" di level variant (kemungkinan inherit dari
        # base_price produk induk di payload yang sama, BELUM dikonfirmasi
        # eksplisit -- perlu ditest). "extra_price" field baru, diisi 0
        # (markup di atas base_price, kalau ada).
        if with_variant:
            existing_id = (existing_variant_ids or {}).get(external_code, "")
            payload["variants"] = [
                {
                    "id": existing_id,
                    "name": product["name"],
                    "external_code": external_code,
                    "attributes": [],
                    "sku": "",
                    "barcode": "",
                    "cost": 0,
                    "extra_price": 0,
                    "status": "active",
                }
            ]

        return payload
