from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError

# Konstanta di bawah ini SENGAJA DIDUPLIKASI dari customer_sync_service.py
# (bukan cross-import antar service) -- konsisten dengan convention project
# ini (lihat komentar CURRENCY di customer_sync_service.py): tiap sync/upsert
# service tetap independen. KALAU value ini berubah (mis. id currency/tax
# transaction/address type baru dari vendor), update MANUAL di KEDUA file
# (di sini DAN customer_sync_service.py).
CURRENCY = {"id": "6a695cc1917e8fc836359505"}  # IDR, dari GET /currency

TAX_TRANSACTION = {
    "id": "697c890679e59420ead8ef36",
    "code": "04",
    "name": "DPP Nilai Lain",
}

ADDRESS_TYPE = {
    "id": "01KYNS4MBNF5GQKQN5VWV4DBWJ",
    "name": "Delivery Address",
}

COUNTRY = {"id": "ID", "name": "Indonesia", "code": ""}

CUSTOMER_TYPE_MAPPING = {
    "company": "company",
    "person": "individual",
}

EXTERNAL_CODE_PREFIX = "ODOO-PARTNER-"


class CustomerUpsertGeoBranchSalesService:
    """
    Upsert MANUAL 1 customer by id Odoo (bukan external_code) dalam SATU
    payload/SATU call ke eSuite -- gabungan dari 3 kebutuhan yang sebelumnya
    cuma bisa dilakukan lewat 3 endpoint terpisah:
      1. Data utama customer (name/type/phone/email/tax/currency/entity_type)
         -- ditarik dari Odoo, logic SAMA PERSIS dengan
         CustomerSyncService._to_esuite_payload() (duplikasi konstanta, lihat
         komentar di atas).
      2. Latitude/longitude -- MANUAL INPUT (dipakai gantiin
         partner_latitude/partner_longitude Odoo yang belum ada datanya),
         format sama dengan CustomerGeolocationService (1 string
         "latitude, longitude" hasil copas Google Maps).
      3. Branch + Salesman (sales.branchs[]/salesmans[]) -- OPSIONAL, kalau
         diisi WAJIB dua-duanya (aturan eSuite: branchs & salesmans di dalam
         `sales` harus di-set BERSAMAAN, info dev eSuite 22 Agustus 2026 --
         lihat CustomerSalesMappingService). Resolve logic (GET /employee,
         GET /branches) DIDUPLIKASI dari CustomerSalesMappingService, bukan
         di-reuse lewat import -- alasan sama seperti di atas.

    KEPUTUSAN ARSITEKTUR (dikonfirmasi user, 28 Agustus 2026): SATU payload
    gabungan + SATU call `esuite.push()`, BUKAN chaining 3 service existing
    (sync -> geo -> mapping) secara berurutan. Alasan: `addresses[]` selalu
    dikirim dengan "id": "" (address BARU tiap upsert, BUKAN update in-place
    -- lihat catatan risiko di CustomerGeolocationService), jadi kalau
    dipanggil berurutan (full sync dulu baru geo-update) berisiko numpuk 2
    address untuk 1 customer. Dengan 1 payload gabungan, address cuma
    dikirim 1x (langsung dengan lat/long manual di dalamnya) -- risiko itu
    hilang untuk use-case endpoint ini. Begitu juga `sales.branchs`/
    `salesmans` dikirim bersamaan dalam payload yang sama, tidak ada window
    salah satu kosong di antara call terpisah.

    ⚠️ Endpoint ini TIDAK menyelesaikan risiko address-numpuk untuk customer
    yang SUDAH PERNAH di-upsert sebelumnya (via /sync/customers ATAU
    endpoint ini sendiri, panggilan ke-2+) -- tiap panggilan tetap kirim
    address baru dengan "id": "". Endpoint ini didesain untuk use-case
    customer yang BELUM punya address/geo data di eSuite.
    """

    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def upsert(
        self,
        customer_id: int,
        coordinates: str,
        branch_external_codes: str | None = None,
        salesman_ids: str | None = None,
        salesman_names: str | None = None,
    ) -> dict:
        latitude, longitude = self._parse_coordinates(coordinates)

        customers = self.odoo.get_customers(ids=[customer_id])
        if not customers:
            raise ValidationError(
                f"Customer id Odoo {customer_id} tidak ditemukan (cek "
                "customer_rank > 0 dan active = True di Odoo)",
                details={"customer_id": customer_id},
            )
        customer = customers[0]

        payload_item = self._to_esuite_payload(customer, latitude, longitude)

        # branch/salesman OPSIONAL -- kalau salah satu diisi, WAJIB dua-duanya
        # (aturan eSuite: sales.branchs[]/salesmans[] harus di-set bersamaan).
        # Kalau KEDUANYA kosong, key "sales" TIDAK ditambahkan ke payload sama
        # sekali -- partial-merge upsert eSuite tetap berlaku di level TOP,
        # jadi mapping sales existing (kalau ada) TIDAK ikut ter-reset.
        sales_included = bool(branch_external_codes or salesman_ids)
        if sales_included:
            if not branch_external_codes or not salesman_ids:
                raise ValidationError(
                    "branch_external_codes dan salesman_ids WAJIB diisi "
                    "BERSAMAAN kalau salah satunya diisi -- eSuite "
                    "mewajibkan sales.branchs[] dan sales.salesmans[] "
                    "di-set bersamaan (info dev eSuite, 22 Agustus 2026)"
                )
            payload_item["sales"] = self._build_sales(
                branch_external_codes, salesman_ids, salesman_names
            )

        esuite_result = self.esuite.push("customers", event="upsert", data=[payload_item])

        return {
            "customer_id": customer_id,
            "external_code": payload_item["external_code"],
            "latitude": latitude,
            "longitude": longitude,
            "sales_included": sales_included,
            "payload_sent": [payload_item],
            "esuite_response": esuite_result,
        }

    # ------------------------------------------------------------------
    # Geo parsing -- IDENTIK dengan CustomerGeolocationService._parse_coordinates()
    # (duplikasi, bukan import silang -- lihat alasan di docstring class).
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_coordinates(coordinates: str) -> tuple[float, float]:
        raw = (coordinates or "").strip()
        parts = raw.split(",")
        if len(parts) != 2:
            raise ValidationError(
                "Format coordinates salah -- harus 'latitude, longitude' "
                "(1 field hasil copas dari Google Maps), contoh: "
                "-8.800799056816937, 115.18475651821433",
                details={"coordinates": coordinates},
            )

        try:
            latitude = float(parts[0].strip())
            longitude = float(parts[1].strip())
        except ValueError:
            raise ValidationError(
                "latitude/longitude bukan angka desimal yang valid",
                details={"coordinates": coordinates},
            )

        if not (-90 <= latitude <= 90):
            raise ValidationError(
                f"latitude di luar rentang valid (-90 s/d 90): {latitude} "
                "-- cek urutan, mungkin latitude/longitude tertukar",
                details={"coordinates": coordinates},
            )
        if not (-180 <= longitude <= 180):
            raise ValidationError(
                f"longitude di luar rentang valid (-180 s/d 180): {longitude} "
                "-- cek urutan, mungkin latitude/longitude tertukar",
                details={"coordinates": coordinates},
            )

        return latitude, longitude

    # ------------------------------------------------------------------
    # Payload utama customer -- IDENTIK dengan
    # CustomerSyncService._to_esuite_payload()/_to_esuite_address(), BEDA
    # cuma di address: lat/long SELALU dari input manual (bukan dari Odoo
    # partner_latitude/partner_longitude, bukan conditional truthy-check).
    # ------------------------------------------------------------------
    def _resolve_customer_type(self, company_type: str) -> str:
        mapped = CUSTOMER_TYPE_MAPPING.get(company_type)
        if not mapped:
            raise ValidationError(
                f"company_type Odoo '{company_type}' belum ada mapping-nya "
                "di CUSTOMER_TYPE_MAPPING",
                details={
                    "odoo_company_type": company_type,
                    "known_mappings": list(CUSTOMER_TYPE_MAPPING.keys()),
                },
            )
        return mapped

    @staticmethod
    def _only_digits(value: str | bool | None) -> str:
        import re

        return re.sub(r"\D", "", value or "")

    def _to_esuite_payload(self, customer: dict, latitude: float, longitude: float) -> dict:
        address = {
            "id": "",
            "address_type": ADDRESS_TYPE,
            "street_address": customer.get("street") or "",
            "country": COUNTRY,
            "is_primary_address": True,
            # lat/long -- SELALU dari input manual endpoint ini (beda dari
            # CustomerSyncService._to_esuite_address() yang truthy-check
            # partner_latitude/partner_longitude Odoo).
            "longitude": longitude,
            "latitude": latitude,
        }

        return {
            "name": customer["name"],
            "external_code": f"{EXTERNAL_CODE_PREFIX}{customer['id']}",
            "type": self._resolve_customer_type(customer.get("company_type")),
            "status": "active",
            "currency": CURRENCY,
            "invoice": {
                "tax": {
                    "tax_transaction": TAX_TRANSACTION,
                }
            },
            "entity_type": "customer",
            "phone": self._only_digits(customer.get("phone")),
            "email": customer.get("email") or "",
            "addresses": [address],
        }

    # ------------------------------------------------------------------
    # Sales (branch+salesman) -- IDENTIK dengan
    # CustomerSalesMappingService.map_to_sales()/_resolve_salesmen()/
    # _resolve_branches() (duplikasi, bukan import silang -- lihat alasan
    # di docstring class).
    # ------------------------------------------------------------------
    def _build_sales(
        self,
        branch_external_codes: str,
        salesman_ids: str,
        salesman_names: str | None,
    ) -> dict:
        branch_codes = [b.strip() for b in branch_external_codes.split(",") if b.strip()]
        if not branch_codes:
            raise ValidationError("branch_external_codes wajib diisi minimal 1")

        sid_list = [s.strip() for s in salesman_ids.split(",") if s.strip()]
        if not sid_list:
            raise ValidationError("salesman_ids wajib diisi minimal 1")

        resolved_salesmen = self._resolve_salesmen(sid_list)

        if salesman_names:
            sname_list = [n.strip() for n in salesman_names.split(",") if n.strip()]
            if len(sid_list) != len(sname_list):
                raise ValidationError(
                    "jumlah salesman_ids dan salesman_names harus SAMA "
                    "(berpasangan posisi 1-1)",
                    details={"salesman_ids": sid_list, "salesman_names": sname_list},
                )
            salesmans_payload = [
                {"id": r["id"], "name": sname}
                for r, sname in zip(resolved_salesmen, sname_list)
            ]
        else:
            salesmans_payload = resolved_salesmen

        resolved_branches = self._resolve_branches(set(branch_codes))
        missing_branches = [c for c in branch_codes if c not in resolved_branches]
        if missing_branches:
            raise ValidationError(
                "branch_external_codes tidak ditemukan di eSuite -- cek "
                "dulu via GET /branches (mungkin belum pernah di-sync "
                "lewat /sync/branch, atau salah ketik)",
                details={"not_found": missing_branches},
            )

        branchs_payload = [
            {"id": resolved_branches[c]["id"], "name": resolved_branches[c]["name"]}
            for c in branch_codes
        ]

        return {"branchs": branchs_payload, "salesmans": salesmans_payload}

    def _resolve_salesmen(self, sid_list: list[str]) -> list[dict]:
        resolved = []
        for sid in sid_list:
            result = self.esuite.pull_by_param("employee", "employee_id", sid)
            records = result.get("data") or []
            if not records:
                raise ValidationError(
                    f"salesman_id '{sid}' tidak ditemukan di eSuite (GET "
                    "/employee kosong) -- cek employee_id benar",
                    details={"salesman_id": sid},
                )
            record = records[0]
            resolved.append({"id": record.get("id") or "", "name": record.get("name") or ""})
        return resolved

    def _resolve_branches(self, codes_wanted: set) -> dict:
        result: dict = {}
        if not codes_wanted:
            return result

        page = 1
        limit = 200
        while True:
            pulled = self.esuite.pull("branches", page=page, limit=limit)
            for record in pulled.get("data") or []:
                code = (record.get("basic_info") or {}).get("external_code")
                if code in codes_wanted and record.get("id") and code not in result:
                    result[code] = {"id": record["id"], "name": record.get("name") or ""}

            meta = pulled.get("meta") or {}
            total_page = meta.get("total_page", 1)
            if page >= total_page or len(result) == len(codes_wanted):
                break
            page += 1

        return result
