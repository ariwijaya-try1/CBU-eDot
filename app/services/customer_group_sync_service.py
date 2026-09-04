from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError

# 🆕 4 September 2026 (lanjutan) -- DIGANTI TOTAL: Customer Group SEKARANG
# ditarik DINAMIS dari Odoo `res.partner.industry` (bukan hardcode lagi).
# Alasan & histori lengkap: 4 grup hardcode di bawah (FS/MT/GT/HORECA, dibuat
# 14 Agustus 2026 dari deskripsi bisnis chat, BUKAN dari Odoo) sempat dipush &
# CONFIRMED ada di eSuite -- TAPI 4 September 2026 direvisi jadi ASUMSI
# sandbox-only (lihat sales_entities_gap.md), lalu user cek data industry
# REAL dari Odoo (GET /odoo/industry) dan hasilnya JAUH lebih granular & BEDA
# nama sama sekali dari 4 grup lama (18 industry: FS-Catering/FS-Hotel/
# FS-Industry/FS-Restaurant/GT-Buah/GT-Frozen/GT-Retail/GT-Specialty Store/
# GT-Supplier/LMT-A/B/C/D/NKA-A/B/C/Distributor/ONLINE -- TIDAK ADA "MT" atau
# "HORECA" polos). User KONFIRMASI: pakai data industry Odoo ini sbg SSOT
# Customer Group, gantikan hardcode sepenuhnya (proses: ambil res.partner.
# industry dari Odoo -> upsert 1:1 jadi Customer Group eSuite), pola SAMA
# PERSIS dengan SalesmanDivisionSyncService (crm.team -> Salesman Division).
#
# CUSTOMER_GROUPS di bawah ini DIPERTAHANKAN sengaja (histori/referensi,
# BUKAN dihapus) -- TAPI TIDAK DIPAKAI LAGI oleh sync() di bawah. 4 record
# lama yang sudah kepush ke eSuite (external_code prefix "CBU-CUSTGROUP-")
# TIDAK disentuh/dihapus oleh perubahan ini (tidak ada delete API dipakai) --
# jadi orphan (tidak ke-update lagi lewat sync ini), keputusan diapain
# (biarkan / nonaktifkan manual) diserahkan ke user, di luar scope perubahan
# ini (dikonfirmasi user 4 September 2026: "biarkan" adalah default aman
# karena tidak dijawab eksplisit, TIDAK ada tindakan destruktif diambil).
CUSTOMER_GROUPS = [
    {"code": "FS", "name": "Food Service"},
    {"code": "MT", "name": "Modern Trade"},
    {"code": "GT", "name": "General Trade"},
    {"code": "HORECA", "name": "HORECA"},
]

# Prefix external_code Customer Group BARU (4 September 2026) -- konsisten
# pola "ODOO-*" project ini (id Odoo jadi bagian key upsert/delete di eSuite),
# sama seperti ODOO-SALESTEAM- (salesman_division_sync_service.py),
# ODOO-COMPANY- (branch_sync_service.py), ODOO-PARTNER- (customer_sync_
# service.py). Format dikonfirmasi LANGSUNG oleh user: "ODOO-CONTACT-
# INDUSTRY-{ID}" (id = res.partner.industry id Odoo). BEDA dari prefix lama
# "CBU-CUSTGROUP-" (yang itu bukan id Odoo, cuma kode manual FS/MT/GT/HORECA)
# -- 2 prefix ini dianggap 2 grup entity berbeda oleh eSuite (upsert by
# external_code), makanya 4 record lama TIDAK ke-update oleh prefix baru ini.
EXTERNAL_CODE_PREFIX = "ODOO-CONTACT-INDUSTRY-"

# Currency -- sama persis dengan CURRENCY di customer_sync_service.py (IDR,
# satu-satunya currency di seluruh bisnis). Didefinisikan ulang di sini
# (bukan import silang antar service) konsisten dengan pola tiap sync service
# independen yang sudah dipakai di project ini.
#
# DITAMBAHKAN 14 Agustus 2026 -- root cause dugaan kenapa 4 record pertama
# tidak muncul di GET /customergroup meski POST balas 200 OK: PDF section 9.14
# cuma nyebut "Required fields: external_code, name; status optional", TAPI
# payload Postman kamu yang TERBUKTI jalan untuk entity ini menyertakan
# "basic_transaction": {"currency": {...}}. Pola ini SAMA dengan kasus
# `entity_type` di Customer (11 Agustus 2026) -- field yang didokumentasikan
# "opsional"/tidak disebut di teks "Required fields", ternyata di backend
# eSuite tetap wajib, dan pelanggarannya bukan error eksplisit tapi silent
# failure (200 OK, record tidak benar-benar tersimpan).
#
# ✅ ID DIKONFIRMASI user 24 Agustus 2026: "6a695cc1917e8fc836359505" =
# IDR (currency default satu-satunya di seluruh bisnis) -- id ini WAJIB
# PERSIS benar (salah id currency = upsert customer group berpotensi
# gagal/salah). Value di bawah SUDAH BENAR, tidak perlu diubah.
CURRENCY = {"id": "6a97ad0fba3a62f899d29060"}  # IDR PROD -- direvisi 4 September 2026, dev
# konfirmasi langsung id lama ("6a695cc1917e8fc836359505") itu id DEV/sandbox, BUKAN PROD
# (lihat esuite_prod_cutover.md). BELUM ditest live pasca fix ini.


class CustomerGroupSyncService:
    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(
        self,
        event: str = "upsert",
        external_codes: str | None = None,
        limit: int | None = None,
    ):
        odoo_ids = self._parse_external_codes(external_codes) if external_codes else None
        industries = self.odoo.get_industries(ids=odoo_ids)

        if not industries:
            raise ValidationError(
                "Tidak ada res.partner.industry ditemukan di Odoo (cek juga external_codes kalau diisi)"
            )

        total_matched = len(industries)

        # limit -- diagnostic aid, pola sama service lain (kirim cuma N
        # group pertama). Default None -> behavior normal (semua industry).
        if limit is not None:
            industries = industries[:limit]

        payload = [self._to_esuite_payload(i) for i in industries]
        esuite_result = self.esuite.push("customergroup", event=event, data=payload)

        return {
            "total_matched_in_odoo": total_matched,
            "synced_count": len(payload),
            "external_codes": [item["external_code"] for item in payload],
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _parse_external_codes(self, external_codes: str) -> list[int]:
        """
        Parse "ODOO-CONTACT-INDUSTRY-34,ODOO-CONTACT-INDUSTRY-35" -> [34, 35]
        -- pola sama SalesmanDivisionSyncService._parse_external_codes()
        (4 September 2026, diganti dari parsing "code" string FS/MT/GT/HORECA
        ke id Odoo numerik, karena sumber data sekarang res.partner.industry).
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

    def _to_esuite_payload(self, industry: dict) -> dict:
        return {
            # external_code = key upsert/delete di eSuite -- harus stabil &
            # unik, sekarang bersumber dari id res.partner.industry Odoo
            # (BEDA dari skema lama yang pakai "code" manual FS/MT/GT/HORECA).
            "external_code": f"{EXTERNAL_CODE_PREFIX}{industry['id']}",
            "name": industry["name"],
            "status": "active",
            # basic_transaction.currency -- lihat komentar CURRENCY di atas
            # (14 Agustus 2026, dugaan silent-required-field, belum dikonfirmasi
            # vendor, tapi cocokkan dulu dengan contoh Postman yang jalan).
            "basic_transaction": {"currency": CURRENCY},
            # parent / customers[] / transaction_rules -- sengaja BELUM dikirim
            # (sama seperti sebelumnya). ⚠️ CATATAN 4 September 2026: dev eSuite
            # WA note (26 Agustus) bilang customer_group[] di Pricelist HANYA
            # BISA pilih customer group yang PARENT-nya "Customer Type" --
            # kalau constraint ini juga berlaku di sini, 18 group baru ini
            # BELUM PASTI otomatis kepilihable di Pricelist tanpa field
            # "parent" diisi. BELUM diverifikasi/dikerjakan (perlu tau id
            # eSuite dari parent "Customer Type" dulu) -- lihat
            # sales_entities_gap.md, PENDING follow-up terpisah.
        }
