from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError


class CustomerSalesmanMappingService:
    """
    Mass mapping Customer -> Salesman (employee eSuite) -- pola PERSIS sama
    dengan CustomerGroupingService (customer_grouping_service.py), cuma beda
    field payload eSuite (`sales.salesmans[]` bukan `customer_groups[]`).
    Dibuat 22 Agustus 2026, alasan & desain sama: supaya tidak perlu assign
    salesman 1-per-1 lewat UI eSuite.
    """

    def __init__(self):
        self.esuite = EsuiteClient()

    def map_to_salesman(self, external_codes: str, salesman_ids: str) -> dict:
        """
        Payload SENGAJA MINIMAL (cuma external_code + sales.salesmans),
        memanfaatkan upsert eSuite yang partial-merge -- field Customer lain
        (name/type/phone/customer_groups/dst) TIDAK ikut dikirim/ter-reset.

        external_codes & salesman_ids diterima APA ADANYA (comma-separated,
        TIDAK divalidasi format) -- pola sama dengan CustomerGroupingService,
        lihat komentar di sana untuk alasan lengkap (pelajaran dari bug
        validasi deactivate Branch, 22 Agustus 2026).

        salesman_ids -- 1 atau lebih employee_id eSuite. Kalau lebih dari 1,
        SEMUA salesman itu di-assign ke SEMUA external_codes yang dikirim
        (mass mapping seragam, bukan mapping custom per customer).
        """
        codes = [c.strip() for c in external_codes.split(",") if c.strip()]
        if not codes:
            raise ValidationError("external_codes wajib diisi minimal 1")

        ids = [s.strip() for s in salesman_ids.split(",") if s.strip()]
        if not ids:
            raise ValidationError("salesman_ids wajib diisi minimal 1")

        salesmans = [{"id": sid} for sid in ids]

        payload = [
            {"external_code": code, "sales": {"salesmans": salesmans}}
            for code in codes
        ]
        esuite_result = self.esuite.push("customers", event="upsert", data=payload)

        return {
            "mapped_count": len(payload),
            "external_codes": codes,
            "salesman_ids": ids,
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }
