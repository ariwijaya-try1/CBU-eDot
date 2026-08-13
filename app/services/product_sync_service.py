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
        payload = [self._to_esuite_payload(p, category_id_map) for p in products]

        # Batching -- REVISI 12 Agustus 2026, opsional (beda dari Customer yang
        # SELALU batch). Kalau batch_size tidak diisi, 1 batch = semua produk
        # (behavior lama, tidak berubah). Kalau diisi, dipecah sama seperti
        # customer_sync_service.py -- 1 batch gagal TIDAK menggagalkan batch lain.
        size = batch_size or len(payload)
        batches = [payload[i : i + size] for i in range(0, len(payload), size)] or [[]]

        batch_results = []
        variant_results = []
        synced_count = 0
        failed_count = 0

        for idx, batch in enumerate(batches, start=1):
            try:
                esuite_result = self.esuite.push("product", event=event, data=batch)
                batch_results.append(
                    {
                        "batch": idx,
                        "size": len(batch),
                        "status": "success",
                        "external_codes": [item["external_code"] for item in batch],
                        # payload_sent -- WAJIB sesuai aturan FIXED di
                        # SESSION_TRANSFER_NOTE.md poin 2 ("Response tiap
                        # endpoint selalu include payload_sent"). Sempat
                        # hilang pas batching ditambahkan 12 Agustus 2026 --
                        # dikembalikan setelah ditegur user.
                        "payload_sent": batch,
                        "esuite_response": esuite_result,
                    }
                )
                synced_count += len(batch)

                # with_variant -- BARU 12 Agustus 2026, DEFAULT FALSE (opt-in).
                # Belum divalidasi end-to-end skala besar, jadi sengaja tidak
                # otomatis nyala biar tidak ada efek samping tak terduga ke
                # produk yang belum ditest. Lihat _sync_variants_for_batch().
                if with_variant:
                    variant_results.append(self._sync_variants_for_batch(batch, event))
            except AppError as e:
                # Pola sama dengan customer_sync_service.py -- di-catch per
                # batch, batch lain tetap lanjut.
                batch_results.append(
                    {
                        "batch": idx,
                        "size": len(batch),
                        "status": "failed",
                        "external_codes": [item["external_code"] for item in batch],
                        "payload_sent": batch,
                        "error": e.to_dict()["error"],
                    }
                )
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
            result["variant_sync"] = variant_results

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

    def _sync_variants_for_batch(self, product_batch: list[dict], event: str) -> dict:
        """
        Push 1 product-variant per product (1:1) buat 1 batch produk yang
        BARU SAJA berhasil di-push -- BARU 12 Agustus 2026, konfirmasi
        vendor: dashboard sales eSuite nampilin data Product VARIANT, bukan
        Product langsung. Karena CBU tidak punya konsep variant asli (tiap
        ukuran/kemasan = product.product Odoo terpisah), 1 variant generic
        per produk sudah cukup mewakili -- BUKAN karena ada variant beneran.

        Alur: POST /product tidak balikin id eSuite (reconcile via
        external_code, lihat SESSION_TRANSFER_NOTE.md poin 4) -- jadi resolve
        dulu id-nya lewat EsuiteClient.find_by_external_codes(), baru push
        ke /product-variant referensi "product": {"id": ...}.

        external_code variant = SAMA PERSIS dengan external_code product
        induknya (bukan prefix baru) -- berdasarkan data nyata yang sudah
        diobservasi (variant existing yang external_code-nya identik dengan
        product induk, lihat CONFIG_NOTES.md).

        Best-effort: eSuite proses async, jadi id produk yang baru dipush
        BISA SAJA belum ke-resolve (belum selesai diproses). Produk yang
        gagal resolve di-skip & dilaporkan di "skipped" -- TIDAK bikin
        seluruh batch product gagal. Re-run manual buat yang skip.
        """
        codes_wanted = {item["external_code"] for item in product_batch}
        resolved = self.esuite.find_by_external_codes("product", codes_wanted)

        variant_payload = []
        skipped = []
        for item in product_batch:
            code = item["external_code"]
            record = resolved.get(code)
            esuite_id = record.get("id") if record else None
            if not esuite_id:
                skipped.append(code)
                continue
            variant_payload.append(
                {
                    "product": {"id": esuite_id},
                    "external_code": code,
                    "name": item["name"],
                    "status": "active",
                    "product_type": item["product_type"],
                    "product_category": item["product_category"],
                    "base_uom": item["base_uom"],
                    "currency": item["currency"],
                }
            )

        if not variant_payload:
            return {"pushed": 0, "skipped": skipped, "esuite_response": None}

        try:
            esuite_result = self.esuite.push("product-variant", event=event, data=variant_payload)
            return {
                "pushed": len(variant_payload),
                "skipped": skipped,
                "external_codes": [v["external_code"] for v in variant_payload],
                "esuite_response": esuite_result,
            }
        except AppError as e:
            # Kegagalan push variant TIDAK di-propagate -- produk induknya
            # sudah berhasil, jangan sampai laporan sync product jadi error
            # gara-gara variant. Caller cek "variant_sync" di response.
            return {
                "pushed": 0,
                "skipped": skipped,
                "attempted": [v["external_code"] for v in variant_payload],
                "error": e.to_dict()["error"],
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
            #   4) (11 Agustus 2026) TEMUAN BARU, BELUM ACTION: update cost ke 0
            #      lewat UI dashboard eSuite BERHASIL -- jadi falsy-skip ini
            #      kemungkinan besar bug spesifik di endpoint API, bukan
            #      keterbatasan sistem eSuite secara umum. Sudah dilaporkan ke
            #      vendor (masih 1 laporan lagi terkait uom_levels.id di atas
            #      yang juga lagi ditunggu). JANGAN ganti "cost": 1 -> 0 di sini
            #      sampai ada konfirmasi endpoint sudah benar (kemungkinan
            #      root cause-nya sama dengan uom_levels.id di atas -- payload
            #      lama ikut gagal ter-apply gara-gara id yang salah).
            # Field standard_price tetap diambil dari Odoo
            # (odoo_client.py::get_products()) tapi tidak pernah dipetakan ke
            # sini. Lihat CONFIG_NOTES.md.
            "cost": 1,
            "base_price": product.get("list_price") or 0,
            "currency": CURRENCY,
        }
