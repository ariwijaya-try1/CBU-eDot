from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError

# Prefix external_code Product Category -- HARUS sama persis dengan yang
# dikirim _to_esuite_payload() ("ODOO-CAT-{id}"). Dipakai fitur "upsert by
# external_code" (21 Agustus 2026), pola sama customer_sync_service.py, DAN
# (27 Agustus 2026) buat hitung balik external_code parent dari parent_id
# Odoo di fase resolve hierarki -- lihat sync()/_resolve_parent_ids().
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
        with_parent: bool = False,
    ):
        """
        Sync Product Category: Odoo (product.category) -> eSuite.

        with_parent (OPSIONAL, default False, BARU 27 Agustus 2026):
        kalau True, sekalian kirim field "parent" (hierarki) ke eSuite --
        dikonfirmasi ADA di skema resmi PDF section 9.2 (Object, opsional,
        "Nest under another category", format {"id": ...}), TAPI sebelumnya
        SENGAJA belum dipakai (lihat riwayat di _to_esuite_payload()).
        Alasan dibikin opt-in (bukan langsung default True):

        1. Behavior lama (kirim "name" doang, kategori flat di eSuite) TIDAK
           BERUBAH kalau param ini tidak diisi -- endpoint existing yang
           sudah dipakai otomatis (mis. dari n8n/automation lain) TETAP
           aman, tidak ada risiko regresi dari perubahan ini.
        2. ROLLBACK: kalau with_parent sempat dipakai (True) lalu dimatikan
           lagi, sync BERIKUTNYA berhenti *mengirim* "parent" -- tapi
           (⚠️ BELUM DIKONFIRMASI VENDOR) berdasarkan pola partial-merge
           eSuite yang sudah terbukti konsisten di entity lain project ini
           (field top-level yang tidak dikirim = TIDAK berubah, BUKAN
           direset ke kosong), kemungkinan besar parent yang SUDAH
           TERLANJUR ke-set TIDAK ikut kehapus otomatis cuma dengan
           mematikan flag ini. Kalau nanti butuh benar-benar MENGHAPUS
           parent yang salah, itu perlu ditest terpisah (kirim eksplisit
           "parent": null) -- BELUM diimplementasi di sini, JANGAN
           diasumsikan jalan tanpa test (ambiguitas sama seperti
           CustomerSalesMappingService.unmap_from_sales(), lihat komentar
           di sana soal null vs [] utk clear field eSuite).
        3. Bisa ditest aman ke SUBSET kecil dulu -- gabungkan dengan param
           `external_codes` yang sudah ada (mis.
           `?with_parent=true&external_codes=ODOO-CAT-123`) sebelum
           dijalankan ke semua kategori.

        Kenapa 2 fase push (bukan 1x langsung isi parent): field "parent"
        eSuite butuh ID INTERNAL eSuite dari kategori induknya, yang cuma
        bisa didapat lewat GET SETELAH kategori induk itu sendiri ke-push --
        makanya fase 1 SELALU push dulu tanpa parent (menjamin external_code
        semua kategori, termasuk yang baru pertama kali sync, sudah ADA di
        eSuite), baru fase 2 (kalau with_parent=True) resolve id lewat pull
        & push ulang cuma kategori yang punya parent. Pola sama dgn resolve
        Branch/Salesman di PricelistSyncService/CustomerSalesMappingService.
        """
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

        # Fase 1 -- SELALU jalan (baik with_parent True atau False), payload
        # TANPA parent. Ini juga behavior LENGKAP kalau with_parent=False
        # (sama persis dengan sebelum perubahan ini).
        payload = [self._to_esuite_payload(c) for c in categories]
        esuite_result = self.esuite.push("product-category", event=event, data=payload)

        result = {
            "total_matched_in_odoo": total_matched,
            "synced_count": len(payload),
            "external_codes": [item["external_code"] for item in payload],
            "with_parent": with_parent,
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

        if not with_parent:
            return result

        # Fase 2 (opt-in) -- resolve & kirim ulang "parent" utk kategori
        # yang di Odoo punya parent_id.
        esuite_id_by_external_code = self._pull_esuite_category_map()

        payload_with_parent = []
        unresolved = []
        for c in categories:
            parent = c.get("parent_id")
            if not parent:
                # Root di Odoo (tidak punya parent sama sekali) -- tidak ada
                # yang perlu di-resolve, biarkan flat spt fase 1.
                continue

            parent_odoo_id = parent[0]
            parent_code = f"{EXTERNAL_CODE_PREFIX}{parent_odoo_id}"
            parent_esuite_id = esuite_id_by_external_code.get(parent_code)

            if not parent_esuite_id:
                # Parent ADA di Odoo tapi TIDAK ketemu di eSuite -- paling
                # sering karena parent itu di LUAR scope filter "Saleable"
                # (mis. induk paling atas "ALL", lihat get_product_categories()
                # di odoo_client.py), jadi memang tidak pernah kita push --
                # BUKAN error, dicatat sbg diagnostic saja.
                unresolved.append(
                    {
                        "external_code": f"{EXTERNAL_CODE_PREFIX}{c['id']}",
                        "parent_odoo_id": parent_odoo_id,
                        "expected_parent_external_code": parent_code,
                    }
                )
                continue

            payload_with_parent.append(
                self._to_esuite_payload(c, parent_esuite_id=parent_esuite_id)
            )

        result["parent_resolved_count"] = len(payload_with_parent)
        result["parent_unresolved"] = unresolved

        if payload_with_parent:
            esuite_result_parent_phase = self.esuite.push(
                "product-category", event=event, data=payload_with_parent
            )
            # payload_sent diganti ke payload FASE 2 -- ini yang benar2
            # nge-set field "parent" (payload fase 1 sengaja tidak diganti
            # di "esuite_response", tetap disimpan sbg "esuite_response"
            # supaya kompatibel dgn caller lama yang baca key ini).
            result["payload_sent"] = payload_with_parent
            result["esuite_response_parent_phase"] = esuite_result_parent_phase

        return result

    def _pull_esuite_category_map(self) -> dict:
        """
        Full-pull GET /product-category, bangun map external_code -> id
        eSuite. PAKAI PULL LOOP MANUAL (BUKAN EsuiteClient.find_by_external_
        codes() generik) -- struktur response entity ini NYELENEH: field
        "external_code" ADA di top-level record, TAPI id eSuite yang
        sebenarnya NESTED di "product_category.id" (bukan record["id"]
        langsung). Gotcha yang SAMA PERSIS sudah didokumentasikan & dipakai
        di product_sync_service.py::_resolve_category_ids() -- pola di sini
        SENGAJA disalin dari situ, BUKAN reinvent (lihat juga
        CONFIG_NOTES.md soal struktur response ini).

        Return: {external_code: esuite_category_id}
        """
        result: dict = {}
        page = 1
        limit = 200

        while True:
            pulled = self.esuite.pull("product-category", page=page, limit=limit)
            for record in pulled.get("data") or []:
                code = record.get("external_code")
                cat = record.get("product_category") or {}
                if code and cat.get("id"):
                    result[code] = cat["id"]

            meta = pulled.get("meta") or {}
            total_page = meta.get("total_page", 1)
            if page >= total_page:
                break
            page += 1

        return result

    def _parse_external_codes(self, external_codes: str) -> list:
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

    def _to_esuite_payload(self, category: dict, parent_esuite_id: str | None = None) -> dict:
        payload = {
            "external_code": f"{EXTERNAL_CODE_PREFIX}{category['id']}",
            # Sengaja pakai "name" (nama leaf), bukan "complete_name" (path
            # lengkap "Induk / Anak") -- hierarki direpresentasikan lewat
            # field "parent" terpisah (lihat di bawah), BUKAN digabung ke
            # nama.
            "name": category["name"],
            "status": "active",
        }
        if parent_esuite_id:
            # OPSIONAL, BARU 27 Agustus 2026 (sebelumnya SENGAJA belum
            # dipakai, lihat komentar lama di sync()) -- field "parent"
            # dikonfirmasi ADA di skema resmi eSuite (PDF section 9.2:
            # Object, opsional, "Nest under another category", format
            # {"id": ...}). Cuma diisi kalau caller (sync(), fase 2) sudah
            # berhasil resolve id eSuite parent-nya.
            payload["parent"] = {"id": parent_esuite_id}
        return payload
