from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError


class CustomerGroupingService:
    """
    Mass mapping Customer -> Customer Group di eSuite (bukan sync Odoo -> eSuite
    biasa -- ini murni update relasi Customer yang SUDAH ada di eSuite ke
    Customer Group yang SUDAH ada di eSuite juga). Dibuat 22 Agustus 2026 supaya
    tidak perlu assign group 1 per 1 lewat UI eSuite.
    """

    def __init__(self):
        self.esuite = EsuiteClient()

    def map_to_group(self, external_codes: str, customer_group_ids: str) -> dict:
        """
        Payload SENGAJA MINIMAL (cuma external_code + customer_groups), pola
        sama dengan BranchSyncService.deactivate() -- memanfaatkan upsert
        eSuite yang bersifat partial-merge (lihat CONFIG_NOTES.md, kasus
        field `cost` produk), jadi field Customer lain (name/type/phone/dst)
        TIDAK ikut dikirim/ter-reset.

        external_codes & customer_group_ids diterima APA ADANYA (comma-
        separated, TIDAK divalidasi format 'ODOO-PARTNER-{id}') -- endpoint
        ini tidak butuh resolve id Odoo sama sekali, cuma neruskan ke eSuite.
        Pelajaran dari bug validasi deactivate Branch (22 Agustus 2026):
        endpoint yang cuma neruskan external_code ke eSuite JANGAN dibatasi
        format prefix kita sendiri.

        customer_group_ids -- 1 atau lebih id Customer Group eSuite (ObjectId
        dari GET /customergroup). Kalau lebih dari 1, SEMUA grup itu di-assign
        ke SEMUA external_codes yang dikirim (mass mapping, bukan mapping
        custom per customer -- kalau butuh itu, panggil endpoint ini beberapa
        kali per grup).
        """
        codes = [c.strip() for c in external_codes.split(",") if c.strip()]
        if not codes:
            raise ValidationError("external_codes wajib diisi minimal 1")

        group_ids = [g.strip() for g in customer_group_ids.split(",") if g.strip()]
        if not group_ids:
            raise ValidationError("customer_group_ids wajib diisi minimal 1")

        customer_groups = [{"id": gid} for gid in group_ids]

        payload = [
            {"external_code": code, "customer_groups": customer_groups}
            for code in codes
        ]
        esuite_result = self.esuite.push("customers", event="upsert", data=payload)

        return {
            "mapped_count": len(payload),
            "external_codes": codes,
            "customer_group_ids": group_ids,
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }
