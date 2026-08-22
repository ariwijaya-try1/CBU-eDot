from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError


class CustomerGroupingService:
    """
    Mass mapping Customer -> Customer Group di eSuite (bukan sync Odoo -> eSuite
    biasa -- ini murni update relasi Customer yang SUDAH ada di eSuite ke
    Customer Group yang SUDAH ada di eSuite juga).

    REVISI 22 Agustus 2026 (setelah live test): payload AWAL cuma kirim
    `{"id": gid}` tanpa `name` -- terkonfirmasi dari data real GET /customers
    (sample/get_customer.txt) hasilnya `customer_groups[].name` SELALU KOSONG
    walau mapping "berhasil" secara data. Sekarang `name` di-RESOLVE OTOMATIS
    (bukan diminta manual dari caller) -- caller cukup kasih external_code
    Customer Group (format "CBU-CUSTGROUP-{code}", SAMA yang dipakai
    /sync/customer-group), lalu di sini di-pull & di-match ke eSuite
    (id + name asli eSuite) via EsuiteClient.find_by_external_codes(), pola
    yang sama dipakai product_sync_service.py resolve category/variant.
    Customer Group AMAN pakai find_by_external_codes() generik (BEDA dari
    Branch yang external_code-nya nested di basic_info -- lihat
    CustomerSalesMappingService._resolve_branches() untuk kasus itu) karena
    payload push Customer Group 100% flat/top-level (external_code, name,
    status, basic_transaction -- lihat customer_group_sync_service.py).
    """

    def __init__(self):
        self.esuite = EsuiteClient()

    def map_to_group(self, external_codes: str, customer_group_external_codes: str) -> dict:
        codes = [c.strip() for c in external_codes.split(",") if c.strip()]
        if not codes:
            raise ValidationError("external_codes wajib diisi minimal 1")

        group_codes = [g.strip() for g in customer_group_external_codes.split(",") if g.strip()]
        if not group_codes:
            raise ValidationError("customer_group_external_codes wajib diisi minimal 1")

        found = self.esuite.find_by_external_codes("customergroup", set(group_codes))
        missing = [c for c in group_codes if c not in found]
        if missing:
            raise ValidationError(
                "customer_group_external_codes tidak ditemukan di eSuite -- "
                "cek dulu via GET /customergroup (mungkin belum pernah "
                "di-sync lewat /sync/customer-group, atau salah ketik)",
                details={"not_found": missing},
            )

        customer_groups = [
            {"id": found[c].get("id", ""), "name": found[c].get("name") or ""}
            for c in group_codes
        ]

        payload = [
            {"external_code": code, "customer_groups": customer_groups}
            for code in codes
        ]
        esuite_result = self.esuite.push("customers", event="upsert", data=payload)

        return {
            "mapped_count": len(payload),
            "external_codes": codes,
            "customer_groups_resolved": customer_groups,
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }
