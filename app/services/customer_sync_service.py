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
CURRENCY = {"id": "6a695cc1917e8fc836359505"}  # IDR, dari GET /currency

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
            customers, name_search_report = self._match_customers_by_name(requested_names)
        else:
            odoo_ids = self._parse_external_codes(external_codes) if external_codes else None
            customers = self.odoo.get_customers(ids=odoo_ids)

        if not customers:
            raise ValidationError("Tidak ada res.partner dengan customer_rank > 0 ditemukan di Odoo (cek juga external_codes/names kalau diisi)")

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

        payload = [self._to_esuite_payload(c) for c in customers]

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

    def _match_customers_by_name(self, requested_names: list[str]) -> tuple[list[dict], dict]:
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
        """
        customers = self.odoo.get_customers(names=requested_names)

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

    def _to_esuite_payload(self, customer: dict) -> dict:
        return {
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
            "email": customer.get("email") or "",
            # addresses -- ditambahkan 24 Agustus 2026 atas instruksi user,
            # lihat _to_esuite_address() untuk detail field & keputusan
            # administrative_level (sengaja TIDAK dikirim, PENDING vendor).
            "addresses": [self._to_esuite_address(customer)],
        }

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
