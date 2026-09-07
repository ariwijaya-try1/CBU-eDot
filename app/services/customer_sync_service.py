import re

from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import AppError, ValidationError
from app.core.sync_logger import log_sync_result

# Currency -- sama dengan yang dipakai product_sync_service.py (IDR, satu-satunya
# currency yang dipakai di seluruh bisnis, lihat CONFIG_NOTES.md). Didefinisikan
# lagi di sini (bukan import silang antar service) supaya tiap sync service tetap
# independen -- konsisten dengan pola konstanta lain di project ini
# (ADMINISTRATIVE_AREA di branch_sync_service.py, UOM_MAPPING di product_sync_service.py).
CURRENCY = {"id": "6a97ad0fba3a62f899d29060"}  # IDR PROD -- direvisi 4 September 2026
# (id lama "6a695cc1917e8fc836359505" itu id DEV/sandbox, TERBUKTI SALAH di PROD,
# lihat esuite_prod_cutover.md). BELUM ditest live pasca fix ini.

# Tax Transaction (kode "04", "DPP Nilai Lain") -- WAJIB diisi, dikonfirmasi
# LANGSUNG oleh dev vendor eSuite: field "invoice.tax.tax_transaction" MANDATORY
# di endpoint upsert Customer (root cause kalau tidak diisi). Fixed value SAMA
# untuk SEMUA customer (bukan dari Odoo, tidak ada sumber data per-customer) --
# pola sama dengan CURRENCY & "entity_type" di _to_esuite_payload() (konstanta
# wajib yang di-hardcode, bukan hasil resolve dari Odoo).
TAX_TRANSACTION = {
    "id": "697c890679e59420ead8ef36",
    "code": "04",
    "name": "DPP Nilai Lain",
}

# Address Type -- fixed "Delivery Address" utk SEMUA address customer,
# DIINSTRUKSIKAN LANGSUNG user 24 Agustus 2026 sebagai default (bukan
# di-resolve per customer, tidak ada sumber data lain di Odoo utk field
# ini). Id sesuai contoh payload resmi vendor.
ADDRESS_TYPE = {
    "id": "01KYNS4MBNF5GQKQN5VWV4DBWJ",
    "name": "Delivery Address",
}

# Country -- fixed Indonesia utk SEMUA address customer (bisnis 100%
# domestik), pola sama dengan CURRENCY/TAX_TRANSACTION di atas -- BUKAN
# hasil resolve dari Odoo, dikonfirmasi user 24 Agustus 2026 pakai contoh
# resmi vendor apa adanya.
COUNTRY = {"id": "ID", "name": "Indonesia", "code": ""}

# Mapping company_type (Odoo) -> type (eSuite). Dikonfirmasi user 7 Agustus 2026:
# field Odoo yang benar itu company_type, BUKAN res.partner.type (itu jenis alamat).
CUSTOMER_TYPE_MAPPING = {
    "company": "company",
    "person": "individual",
}

# Batch size default -- REVISI 11 Agustus 2026: full bulk upsert (>2000 record
# dalam 1 request) kena 502 Bad Gateway dari eSuite. Push sekarang dipecah per
# batch, default 1000 record/batch (instruksi user). Tiap batch = 1 request_id
# terpisah ke eSuite (bukan retry dari request yang sama).
DEFAULT_BATCH_SIZE = 1000

# Prefix external_code Customer -- dipakai buat parse balik id Odoo dari
# external_code (fitur "upsert by external_code", 12 Agustus 2026, pola
# sama dengan product_sync_service.py).
EXTERNAL_CODE_PREFIX = "ODOO-PARTNER-"

# Prefix external_code Customer Group -- HARUS SAMA PERSIS dengan
# EXTERNAL_CODE_PREFIX di customer_group_sync_service.py (didefinisikan
# ulang di sini, bukan import silang, konsisten dgn pola CURRENCY di atas).
# Dipakai 4 September 2026 buat AUTO-RESOLVE customer_groups[] dari
# res.partner.industry_id Odoo saat upsert Customer (dikonfirmasi user --
# lihat customer_grouping_endpoint.md). KALAU prefix di
# customer_group_sync_service.py berubah, prefix ini WAJIB ikut diubah juga.
CUSTOMER_GROUP_EXTERNAL_CODE_PREFIX = "ODOO-CONTACT-INDUSTRY-"

# Prefix external_code Branch -- HARUS SAMA PERSIS dengan EXTERNAL_CODE_PREFIX
# di branch_sync_service.py (didefinisikan ulang di sini, bukan import
# silang, konsisten dgn pola CUSTOMER_GROUP_EXTERNAL_CODE_PREFIX di atas).
# Dipakai 5 September 2026 buat AUTO-RESOLVE sales.branchs[] dari
# res.partner.company_id Odoo saat upsert Customer (instruksi user -- branch
# customer sekarang mengikuti company_id-nya sendiri di Odoo, BUKAN lagi
# harus di-mapping manual satu-satu). KALAU prefix di branch_sync_service.py
# berubah, prefix ini WAJIB ikut diubah juga.
BRANCH_EXTERNAL_CODE_PREFIX = "ODOO-COMPANY-"


class CustomerSyncService:
    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(
        self,
        event: str = "upsert",
        limit: int | None = None,
        batch_size: int | None = None,
        external_codes: str | None = None,
        names: str | None = None,
        include_payload: bool = False,
        only_with_coordinates: bool = False,
    ):
        # names (31 Agustus 2026) -- ALTERNATIF dari external_codes: upsert
        # customer tertentu dicari BY NAMA (bukan id Odoo). Mutually exclusive
        # dengan external_codes (bukan digabung/di-OR) -- disengaja supaya
        # semantik "customer mana yang mau diupsert" selalu jelas 1 cara per
        # panggilan, tidak ambigu.
        if external_codes and names:
            raise ValidationError(
                "external_codes dan names tidak bisa dipakai BERSAMAAN -- "
                "pilih salah satu cara pilih customer (by id Odoo/external_code, "
                "atau by nama)"
            )

        name_search_report = None
        if names:
            requested_names = [n.strip() for n in names.split(",") if n.strip()]
            if not requested_names:
                raise ValidationError("names wajib diisi minimal 1 nama kalau param ini dipakai")
            customers, name_search_report = self._match_customers_by_name(
                requested_names, only_with_coordinates=only_with_coordinates
            )
        else:
            odoo_ids = self._parse_external_codes(external_codes) if external_codes else None
            customers = self.odoo.get_customers(ids=odoo_ids, only_with_coordinates=only_with_coordinates)

        if not customers:
            raise ValidationError(
                "Tidak ada res.partner dengan customer_rank > 0 ditemukan di Odoo "
                "(cek juga external_codes/names/only_with_coordinates kalau diisi)"
            )

        total_matched = len(customers)

        # limit -- TEMPORARY diagnostic aid (7 Agustus 2026), BUKAN fitur bisnis
        # permanen. Ditambahkan buat isolasi root cause 502 Bad Gateway dari
        # eSuite saat push full batch customer (lihat SESSION_TRANSFER_NOTE.md):
        # test manual 1 record via Postman sukses, push full batch via bridge
        # 502 dua kali berturut-turut. limit memungkinkan test bertahap
        # (5, 50, 500 record, dst) buat cari tau apakah soal jumlah record
        # atau soal isi data tertentu, tanpa perlu ubah kode tiap kali coba.
        # Default None -> behavior sama seperti sebelumnya (semua customer).
        if limit is not None:
            customers = customers[:limit]

        # customer_groups auto-resolve (4 September 2026) -- 1x bulk lookup
        # utk SEMUA customer yang BENAR-BENAR mau di-push (bukan per-customer,
        # hindari N+1 call ke eSuite) -- SENGAJA setelah slicing `limit` di
        # atas, supaya lookup ke eSuite juga ikut terbatas saat `limit`
        # dipakai buat diagnostic/test bertahap (konsisten dgn tujuan `limit`
        # itu sendiri). Lihat _resolve_customer_group_map() utk detail.
        group_map, unresolved_groups = self._resolve_customer_group_map(customers)

        # branch auto-resolve (5 September 2026) -- sama pola dgn
        # group_map di atas: 1x bulk pull utk SEMUA customer di batch ini,
        # lihat _resolve_branch_map() utk detail.
        branch_map, unresolved_branch_codes = self._resolve_branch_map(customers)

        payload = [self._to_esuite_payload(c, group_map, branch_map) for c in customers]

        # Batching -- REVISI 11 Agustus 2026: user konfirmasi bulk upsert di atas
        # ~2000 record kena 502. Push sekarang selalu lewat batch (bukan 1 request
        # raksasa), default DEFAULT_BATCH_SIZE (1000). Tiap batch di-push
        # terpisah & independen: kalau 1 batch gagal (mis. 502 lagi), batch lain
        # TETAP lanjut jalan (tidak saling abort) -- supaya kegagalan parsial
        # kelihatan jelas per batch alih-alih 1 error generic yang nutupin
        # batch mana yang sebenarnya sukses.
        size = batch_size or DEFAULT_BATCH_SIZE
        batches = [payload[i : i + size] for i in range(0, len(payload), size)]

        batch_results = []
        synced_count = 0
        failed_count = 0

        for idx, batch in enumerate(batches, start=1):
            try:
                esuite_result = self.esuite.push("customers", event=event, data=batch)
                batch_entry = {
                    "batch": idx,
                    "size": len(batch),
                    "status": "success",
                    "external_codes": [item["external_code"] for item in batch],
                    "esuite_response": esuite_result,
                }
                # payload_sent -- REVISI 13 Agustus 2026: sekarang OPT-IN
                # (default False), bukan lagi selalu tampil. Pola sama
                # dengan product_sync_service.py -- lihat komentar di sana
                # & SESSION_TRANSFER_NOTE.md poin 20 buat alasan lengkap
                # (Swagger lambat kalau payload penuh selalu ikut render).
                if include_payload:
                    batch_entry["payload_sent"] = batch
                batch_results.append(batch_entry)
                synced_count += len(batch)
            except AppError as e:
                # Sengaja di-catch per batch (bukan biar propagate ke exception
                # handler global) -- supaya batch berikutnya tetap lanjut jalan
                # dan hasil akhirnya tetap melaporkan status semua batch, bukan
                # cuma batch pertama yang gagal.
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
        # customer_group_unresolved_industries -- HANYA muncul kalau ADA
        # industry_id yang direferensikan customer di batch ini TAPI Customer
        # Group-nya belum ketemu di eSuite (belum pernah di-sync lewat
        # /sync/customer-group). Customer yang bersangkutan TETAP ke-upsert
        # (field lain jalan normal), cuma customer_groups utk row itu di-skip
        # -- dilaporkan di sini supaya kelihatan industry mana yang perlu
        # di-sync-group-kan dulu (keputusan user 4 September 2026, bukan
        # fail-fast).
        if unresolved_groups:
            result["customer_group_unresolved_industries"] = sorted(unresolved_groups)

        # branch_unresolved_companies -- HANYA muncul kalau ADA company_id
        # yang direferensikan customer di batch ini TAPI Branch-nya belum
        # ketemu di eSuite (company di luar IN_SCOPE_COMPANY_NAMES ATAU
        # belum pernah di-/sync/branch). Customer TETAP ke-upsert (field
        # lain jalan normal), cuma key "sales" utk row itu di-skip --
        # dilaporkan di sini, pola sama customer_group_unresolved_industries
        # (keputusan user 5 September 2026, bukan fail-fast).
        if unresolved_branch_codes:
            result["branch_unresolved_companies"] = sorted(unresolved_branch_codes)

        # name_search -- HANYA ada kalau param `names` dipakai (additive,
        # tidak mengubah struktur response untuk pemakaian external_codes/
        # default yang sudah ada).
        if name_search_report is not None:
            result["name_search"] = name_search_report
        log_sync_result("customer", event, result)
        return result

    def deactivate(self, external_codes: str) -> dict:
        """
        Nonaktifkan Customer di eSuite (status -> "inactive") by external_code,
        TANPA re-pull data dari Odoo -- payload yang dikirim sengaja MINIMAL
        (cuma status + external_code, bukan full payload name/type/addresses/
        dst seperti sync()). Aman karena upsert eSuite bersifat partial-merge
        (lihat CONFIG_NOTES.md) -- field yang tidak dikirim TIDAK ikut
        ter-reset/hilang. Pola SAMA PERSIS dengan BranchSyncService.deactivate()
        (24 Agustus 2026, convention endpoint deactivate entity lain -- lihat
        [[branch_deactivate_endpoint]]).

        external_code diterima APA ADANYA (BEDA dari _parse_external_codes()
        yang dipakai sync() -- itu mewajibkan format 'ODOO-PARTNER-{id}' karena
        perlu resolve ke id Odoo buat query res.partner). deactivate() tidak
        butuh id Odoo sama sekali, jadi tidak boleh dibatasi ke format itu --
        termasuk buat nonaktifkan data pre-existing/legacy eSuite yang bukan
        hasil sync kita.

        external_codes WAJIB diisi (tidak ada default "semua customer") supaya
        tidak ada risiko nonaktifkan customer secara tidak sengaja.
        """
        codes = [c.strip() for c in external_codes.split(",") if c.strip()]
        if not codes:
            raise ValidationError("external_codes wajib diisi minimal 1")

        payload = [
            {"status": "inactive", "external_code": code}
            for code in codes
        ]
        esuite_result = self.esuite.push("customers", event="upsert", data=payload)

        return {
            "deactivated_count": len(payload),
            "external_codes": codes,
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _match_customers_by_name(
        self, requested_names: list[str], only_with_coordinates: bool = False
    ) -> tuple[list[dict], dict]:
        """
        Cari Customer di Odoo BY NAMA (bukan id/external_code) -- 1 query
        bulk (OR "=ilike" per nama, lihat OdooClient.get_customers(names=...)),
        lalu di-group ULANG per nama yang diminta supaya bisa dilaporkan mana
        yang gagal -- keputusan user 31 Agustus 2026: exact match (case-
        insensitive) + kalau ada nama tidak ketemu/ambigu, SKIP nama itu saja
        (bukan fail-fast seluruh request), nama lain yang valid tetap diproses.

        Return: (customers_to_upsert, report) --
          report = {"requested": [...], "matched": [...], "not_found": [...],
                     "ambiguous": {nama: [id_odoo, ...]}}
        - not_found: nama yang 0 record Odoo cocok persis.
        - ambiguous: nama yang justru cocok ke LEBIH DARI 1 record Odoo
          (nama Odoo literally duplikat) -- di-skip juga, TIDAK asal comot
          salah satu, supaya tidak salah upsert customer yang salah.
        - Kalau 2 nama request yang berbeda kebetulan match ke id Odoo yang
          SAMA, customer itu tetap cuma di-upsert 1x (dedup by id).

        only_with_coordinates (4 September 2026) -- diteruskan APA ADANYA ke
        get_customers(). ⚠️ CATATAN PENTING: kalau True, nama yang match
        persis di Odoo TAPI lat/long-nya belum terisi TIDAK akan ke-fetch
        sama sekali dari query ini -- makanya nama itu bakal muncul di
        report["not_found"], PADAHAL customer-nya sebenarnya ADA (cuma
        di-exclude krn belum ada koordinat, BUKAN benar-benar tidak
        ketemu). Ini trade-off yang disengaja (filter di level Odoo domain
        biar efisien, bukan post-filter Python) -- kalau butuh bedakan
        "nama tidak ada" vs "nama ada tapi belum ada koordinat", perlu
        query terpisah (belum diimplementasi, bukan kebutuhan saat ini).
        """
        customers = self.odoo.get_customers(
            names=requested_names, only_with_coordinates=only_with_coordinates
        )

        matched_by_lower: dict[str, list[dict]] = {}
        for c in customers:
            key = (c.get("name") or "").strip().lower()
            matched_by_lower.setdefault(key, []).append(c)

        to_upsert: list[dict] = []
        matched_names: list[str] = []
        not_found: list[str] = []
        ambiguous: dict[str, list[int]] = {}
        seen_ids: set = set()

        for requested in requested_names:
            records = matched_by_lower.get(requested.strip().lower()) or []
            if len(records) == 0:
                not_found.append(requested)
            elif len(records) > 1:
                ambiguous[requested] = [r["id"] for r in records]
            else:
                record = records[0]
                matched_names.append(requested)
                if record["id"] not in seen_ids:
                    seen_ids.add(record["id"])
                    to_upsert.append(record)

        report = {
            "requested": requested_names,
            "matched": matched_names,
            "not_found": not_found,
            "ambiguous": ambiguous,
        }
        return to_upsert, report

    def _resolve_customer_group_map(self, customers: list[dict]) -> tuple[dict[int, dict], set[str]]:
        """
        Resolve res.partner.industry_id (Odoo) -> Customer Group eSuite
        {id, name}, 1x bulk lookup utk SEMUA customer di batch (bukan
        per-customer) -- reuse EsuiteClient.find_by_external_codes() yang
        SAMA dipakai CustomerGroupingService (lihat
        customer_grouping_endpoint.md), external_code format SAMA PERSIS
        dgn CustomerGroupSyncService ("ODOO-CONTACT-INDUSTRY-{id}").

        Sumber grouping SAAT INI cuma res.partner.industry_id (Many2one
        Odoo, 1 customer = 1 industry) -- dikonfirmasi user 4 September
        2026. Return map per-industry (BUKAN per-customer) sengaja supaya
        _resolve_customer_groups() bisa dipanggil per-customer & hasilnya
        LIST (future-proof kalau nanti ada sumber grouping tambahan selain
        industry_id, instruksi user -- BELUM diimplementasi, cuma prasyarat
        desain, lihat _resolve_customer_groups()).

        Return: (industry_id_to_group, unresolved_external_codes)
        - industry_id_to_group: {35: {"id": "6a9a...", "name": "FS-Restaurant"}, ...}
        - unresolved_external_codes: external_code yang direferensikan
          customer di batch ini TAPI belum ketemu di eSuite (Customer Group
          itu belum pernah di-sync lewat /sync/customer-group) -- caller
          (sync()) yang laporkan ke response, BUKAN raise error (customer
          tetap harus bisa ke-upsert walau groupnya belum lengkap).
        """
        industry_ids: set[int] = set()
        for c in customers:
            industry = c.get("industry_id")
            if industry:  # Odoo many2one: [id, display_name], False kalau kosong
                industry_ids.add(industry[0])

        if not industry_ids:
            return {}, set()

        external_codes = {
            f"{CUSTOMER_GROUP_EXTERNAL_CODE_PREFIX}{iid}" for iid in industry_ids
        }
        found = self.esuite.find_by_external_codes("customergroup", external_codes)

        industry_id_to_group: dict[int, dict] = {}
        for iid in industry_ids:
            code = f"{CUSTOMER_GROUP_EXTERNAL_CODE_PREFIX}{iid}"
            record = found.get(code)
            if record:
                industry_id_to_group[iid] = {
                    "id": record.get("id", ""),
                    "name": record.get("name") or "",
                }

        unresolved = external_codes - set(found.keys())
        return industry_id_to_group, unresolved

    def _resolve_customer_groups(self, customer: dict, group_map: dict[int, dict]) -> list[dict]:
        """
        customer_groups[] utk payload eSuite -- SAAT INI cuma 1 sumber
        (res.partner.industry_id), TAPI ditulis sbg LIST dari awal (bukan
        dict tunggal) supaya kalau nanti ada sumber grouping tambahan,
        tinggal di-extend di sini tanpa ubah bentuk payload/caller
        (instruksi user 4 September 2026).

        Return [] (bukan [{}] atau None) kalau industry_id kosong di Odoo
        ATAU groupnya belum ke-resolve (belum pernah di-sync ke eSuite) --
        caller (_to_esuite_payload()) TIDAK menyertakan key "customer_groups"
        sama sekali kalau hasilnya [], supaya partial-merge upsert eSuite
        tidak reset customer_groups yang mungkin sudah di-set manual lewat
        /api/mapping/customer-grouping.
        """
        industry = customer.get("industry_id")
        if not industry:
            return []
        group = group_map.get(industry[0])
        return [group] if group else []

    def _resolve_branch_map(self, customers: list[dict]) -> tuple[dict[int, dict], set[str]]:
        """
        Resolve res.partner.company_id (Odoo) -> Branch eSuite {id, name},
        1x bulk pull utk SEMUA customer di batch ini (bukan per-customer) --
        instruksi user 5 September 2026: sales.branchs[] di payload Customer
        SEKARANG auto-mengikuti company_id customer di Odoo (BUKAN lagi
        harus di-mapping manual satu-satu lewat /mapping/customer-sales
        atau default branch_external_codes di
        /mapping/customer-upsert-geo-branch-sales).

        Branch eSuite = res.company (SSOT SAMA dgn branch_sync_service.py),
        external_code "ODOO-COMPANY-{company_id}". Field "external_code"
        Branch NESTED di "basic_info.external_code" (BUKAN top-level spt
        Product/Customer/Product-Category) -- TIDAK bisa pakai
        EsuiteClient.find_by_external_codes() generik (gagal silent utk
        Branch, root cause sudah ditemukan 18 Agustus 2026 di
        pricelist_sync_service.py::_resolve_branches()). Pull-loop manual
        yang SAMA DIDUPLIKASI ke sini (bukan cross-import, konsisten
        convention "tiap service independen" project ini).

        Kalau company_id kosong di Odoo ATAU company itu belum ke-push sbg
        Branch ke eSuite (di luar IN_SCOPE_COMPANY_NAMES / belum pernah
        di-/sync/branch), code-nya otomatis tidak ada di dict hasil --
        caller (_resolve_branch()) return [] utk customer itu, key "sales"
        TIDAK disisipkan sama sekali (partial-merge aman, keputusan user 5
        September: customer TETAP ke-upsert normal tanpa sales, bukan
        fail-fast). unresolved dilaporkan ke response oleh sync(), pola
        sama _resolve_customer_group_map().

        Return: (company_id_to_branch, unresolved_external_codes)
        """
        company_ids: set[int] = set()
        for c in customers:
            company = c.get("company_id")
            if company:  # Odoo many2one: [id, display_name], False kalau kosong
                company_ids.add(company[0])

        if not company_ids:
            return {}, set()

        codes_wanted = {f"{BRANCH_EXTERNAL_CODE_PREFIX}{cid}" for cid in company_ids}

        found_by_code: dict[str, dict] = {}
        page = 1
        limit = 200
        while True:
            pulled = self.esuite.pull("branches", page=page, limit=limit)
            for record in pulled.get("data") or []:
                code = (record.get("basic_info") or {}).get("external_code")
                if code in codes_wanted and record.get("id") and code not in found_by_code:
                    found_by_code[code] = {"id": record["id"], "name": record.get("name") or ""}

            meta = pulled.get("meta") or {}
            total_page = meta.get("total_page", 1)
            if page >= total_page or len(found_by_code) == len(codes_wanted):
                break
            page += 1

        company_id_to_branch: dict[int, dict] = {}
        for cid in company_ids:
            code = f"{BRANCH_EXTERNAL_CODE_PREFIX}{cid}"
            record = found_by_code.get(code)
            if record:
                company_id_to_branch[cid] = record

        unresolved = codes_wanted - set(found_by_code.keys())
        return company_id_to_branch, unresolved

    def _resolve_branch(self, customer: dict, branch_map: dict[int, dict]) -> list[dict]:
        """
        sales.branchs[] utk payload eSuite -- auto dari res.partner.company_id
        (lihat _resolve_branch_map()). SENGAJA HANYA branchs[] (TANPA
        salesmans[]) -- instruksi eksplisit user 5 September 2026: salesman
        tetap di-assign terpisah manual lewat endpoint /mapping/customer-sales
        (BUKAN di sini). ⚠️ Ini beda dari aturan eSuite lama (24 Agustus
        2026, dikonfirmasi dev eSuite) bahwa branchs & salesmans dalam
        "sales" WAJIB di-set bersamaan -- BELUM ditest live apakah eSuite
        terima branchs-only lewat endpoint /sync/customers ini (beda
        endpoint dari /mapping/customer-sales yang sudah terbukti perlu
        keduanya, lihat customer_sales_mapping_endpoint.md).

        Return [] (bukan [{}]) kalau company_id kosong ATAU belum
        ke-resolve -- caller (_to_esuite_payload()) TIDAK menyertakan key
        "sales" sama sekali kalau hasilnya [], konsisten dgn pola
        _resolve_customer_groups().
        """
        company = customer.get("company_id")
        if not company:
            return []
        branch = branch_map.get(company[0])
        return [branch] if branch else []

    def _parse_external_codes(self, external_codes: str) -> list[int]:
        """
        Parse "ODOO-PARTNER-1,ODOO-PARTNER-2" -> [1, 2] -- pola sama dengan
        product_sync_service.py::_parse_external_codes(), buat upsert
        customer tertentu saja tanpa nyentuh yang lain.
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

    @staticmethod
    def _only_digits(value: str | bool | None) -> str:
        """
        Buang semua karakter selain angka (spasi/+/-/kurung/dst) -- instruksi
        user 25 Agustus 2026: eSuite terima phone ANGKA SAJA. Odoo balikin
        `False` untuk char field kosong (bukan None/"") -- `value or ""`
        menormalkan itu dulu sebelum regex, pola sama dengan `or ""` yang
        sudah dipakai di field phone/email lain (lihat _to_esuite_payload()).
        """
        return re.sub(r"\D", "", value or "")

    def _resolve_customer_type(self, company_type: str) -> str:
        mapped = CUSTOMER_TYPE_MAPPING.get(company_type)
        if not mapped:
            raise ValidationError(
                f"company_type Odoo '{company_type}' belum ada mapping-nya di CUSTOMER_TYPE_MAPPING",
                details={"odoo_company_type": company_type, "known_mappings": list(CUSTOMER_TYPE_MAPPING.keys())},
            )
        return mapped

    def _to_esuite_payload(self, customer: dict, group_map: dict[int, dict] | None = None, branch_map: dict[int, dict] | None = None) -> dict:
        payload = {
            "name": customer["name"],
            # external_code = key upsert/delete di eSuite -- prefix "ODOO-PARTNER-"
            # konsisten dengan pola prefix entity lain (ODOO-COMPANY-, ODOO-PROD-).
            "external_code": f"ODOO-PARTNER-{customer['id']}",
            "type": self._resolve_customer_type(customer.get("company_type")),
            "status": "active",
            "currency": CURRENCY,
            # invoice.tax.tax_transaction -- WAJIB, ditambahkan 24 Agustus 2026
            # setelah dev vendor eSuite konfirmasi field ini mandatory di endpoint
            # upsert Customer. Nested 3 level sesuai skema resmi vendor -- lihat
            # TAX_TRANSACTION di atas untuk detail.
            "invoice": {
                "tax": {
                    "tax_transaction": TAX_TRANSACTION,
                }
            },
            # entity_type -- WAJIB, ditambahkan 11 Agustus 2026 setelah revisi
            # payload dari vendor eSuite (root cause gagal upsert customer).
            # Fixed "customer" untuk semua record entity ini (bukan dari Odoo).
            "entity_type": "customer",
            # phone/email -- ditambahkan 21 Agustus 2026. Skema `/customers`
            # di Postman collection cuma contoh bare minimum, BUKAN daftar
            # lengkap field yang diterima eSuite -- dikonfirmasi lewat live
            # test manual (`?external_codes=ODOO-PARTNER-39353`), kedua
            # field ini SUKSES tersimpan & tampil balik di GET eSuite.
            # Odoo balikin `False` (bukan None/"") untuk char field kosong --
            # `or ""` menormalkan itu jadi string kosong, BUKAN bikin field-nya
            # hilang dari payload (eSuite tetap butuh key-nya ada).
            #
            # "mobile" SENGAJA DIHAPUS LAGI (21 Agustus 2026, beberapa jam
            # setelah ditambahkan) -- Odoo 19 instance CBU error "Invalid
            # field 'mobile'" pas query res.partner. Field ini sudah resmi
            # dihapus dari Contacts di Odoo 19 (di-merge ke `phone`,
            # dikonfirmasi user). Tidak ada sumber data Odoo lagi untuk field
            # ini, jadi tidak dikirim ke eSuite -- lihat odoo_client.py::get_customers().
            # phone -- REVISI 25 Agustus 2026 (instruksi user): kirim ANGKA
            # SAJA ke eSuite (tanpa spasi/+/-), mis. data Odoo "+62 812-3456"
            # -> "628123456". Format asli Odoo bebas (user isi manual), jadi
            # dibersihkan di sini (bukan di Odoo) supaya konsisten & aman
            # walau nomor ditulis format apapun. Lihat _only_digits().
            "phone": self._only_digits(customer.get("phone")),
            # mobile -- SEMENTARA disamakan dgn phone (instruksi user 7
            # September 2026): Odoo 19 CBU cuma punya 1 field nomor telepon
            # ("phone") -- field "mobile" resmi sudah dihapus dari Contacts
            # (lihat komentar "mobile" DIHAPUS LAGI di atas, itu soal QUERY
            # dari Odoo, BUKAN soal payload eSuite ini). eWork app (mobile
            # app) HANYA baca field "mobile" eSuite utk nomor telepon, jadi
            # dikirim juga dgn value SAMA seperti "phone" supaya eWork app
            # tetap dapat nomornya. Revisit kalau Odoo 19 CBU nanti punya
            # field nomor seluler terpisah lagi.
            "mobile": self._only_digits(customer.get("phone")),
            "email": customer.get("email") or "",
            # addresses -- ditambahkan 24 Agustus 2026 atas instruksi user,
            # lihat _to_esuite_address() untuk detail field & keputusan
            # administrative_level (sengaja TIDAK dikirim, PENDING vendor).
            "addresses": [self._to_esuite_address(customer)],
        }

        # customer_groups -- auto-resolve dari res.partner.industry_id (4
        # September 2026, lihat _resolve_customer_groups()). Key HANYA
        # disisipkan kalau ada hasil ([]  -> key tidak ditambah sama sekali,
        # BUKAN dikirim customer_groups: [] eksplisit) -- partial-merge
        # eSuite tidak akan reset customer_groups yang sudah ada kalau kita
        # tidak punya data buat isi ulang.
        groups = self._resolve_customer_groups(customer, group_map or {})
        if groups:
            payload["customer_groups"] = groups

        # sales.branchs -- auto-resolve dari res.partner.company_id (5
        # September 2026, lihat _resolve_branch()). SENGAJA HANYA branchs[]
        # (TANPA salesmans[]) -- instruksi eksplisit user: salesman tetap
        # di-assign terpisah manual lewat /mapping/customer-sales, BUKAN di
        # sini. Key "sales" HANYA disisipkan kalau ada hasil ([] -> key
        # tidak ditambah sama sekali), sama pola dgn customer_groups di
        # atas -- partial-merge eSuite tidak akan reset sales yang sudah
        # ada kalau kita tidak punya data buat isi ulang.
        branch = self._resolve_branch(customer, branch_map or {})
        if branch:
            payload["sales"] = {"branchs": branch}

        return payload

    def _to_esuite_address(self, customer: dict) -> dict:
        """
        Bangun 1 objek address dari data alamat res.partner (street/
        partner_latitude/partner_longitude -- field sama yang dipakai
        branch_sync_service.py::get_partner_address(), tapi di sini diambil
        LANGSUNG dari get_customers() -- lihat catatan di
        odoo_client.py::get_customers()).

        Keputusan user (24 Agustus 2026):
        - "id": "" tetap (address baru tiap upsert, sesuai contoh payload
          resmi vendor -- BUKAN id address eSuite yang sudah ada).
        - "address_type": fixed ADDRESS_TYPE ("Delivery Address") utk semua
          customer, bukan per-customer.
        - "street_address": dari field Odoo "street" (res.partner) apa
          adanya -- tidak digabung field lain (street2/city/dll).
        - "country": fixed COUNTRY (Indonesia) utk semua customer.
        - "longitude"/"latitude": HANYA dikirim kalau ADA datanya di Odoo
          ("tidak usah kirim jika tidak ada dari odoo" -- instruksi user).
          Field float Odoo yang kosong balik 0.0 (BUKAN None/False seperti
          field char) -- truthy check di sini SENGAJA (bukan "is not None")
          supaya 0.0 juga dianggap "tidak ada data", konsisten dengan pola
          `or ""` yang sudah dipakai buat phone/email & get_partner_address().
        - "administrative_level" (province/city/district/sub_district, skema
          eSuite pakai kode BPS) SENGAJA TIDAK dikirim -- Odoo tidak punya
          granularitas 4-level itu (beda dari Branch yang cukup diisi manual
          via ADMINISTRATIVE_AREA karena cuma ~3 record; Customer bisa
          ribuan). Kalau ternyata field ini mandatory di endpoint /customers,
          upsert akan reject -- itu jadi bukti konkret buat tanya vendor cara
          resolve yang benar, keputusan user supaya tidak nebak sekarang.
        """
        address = {
            "id": "",
            "address_type": ADDRESS_TYPE,
            "street_address": customer.get("street") or "",
            "country": COUNTRY,
            "is_primary_address": True,
        }

        lat = customer.get("partner_latitude")
        lon = customer.get("partner_longitude")
        if lat and lon:
            address["longitude"] = lon
            address["latitude"] = lat

        return address
