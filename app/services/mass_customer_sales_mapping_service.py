from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import AppError, ValidationError

DEFAULT_BATCH_SIZE = 1000  # sama dengan customer_sync_service.py, konsisten convention project

# GET /customers -- page size internal utk pull-loop pull SEMUA customer
# (BUKAN dipakai user, murni tuning internal). 200 sama dengan page_size
# yang sudah dipakai _resolve_branches() di service lain.
PULL_PAGE_SIZE = 200


class MassCustomerSalesMappingService:
    """
    🆕 7 September 2026, BARU -- Mass mapping SEMUA customer (yang sudah ada
    di eSuite) ke 1 SALESMAN yang SAMA sekaligus, KHUSUS masa PRE-LIVE
    (utility sekali pakai buat percepat setup awal, BUKAN endpoint permanen
    jangka panjang seperti /mapping/customer-sales).

    KONDISI dari user (instruksi eksplisit): customer HANYA eligible di-map
    ke salesman ini kalau branch customer (sales.branchs[] yang SUDAH ada di
    eSuite, dibawa dari /sync/customers company_id auto-resolve ATAU dari
    endpoint upsert manual) SAMA dengan branch salesman (branches[] di data
    Salesman/employee eSuite). Customer yang branch-nya BEDA (atau belum
    punya branch sama sekali) -- DI-SKIP + dicatat di response["skipped"],
    TIDAK menghentikan proses customer lain (bukan fail-fast per-customer).

    ⚠️ ASUMSI BELUM DIKONFIRMASI VENDOR: field "branches[]" di response GET
    /employee. Bukti yang ADA baru dari skema POST /salesman (upsert, lihat
    postman/eSuite-Webhook.postman_collection.json) yang PASTI punya field
    "branches": [{"id": ...}] -- BELUM ada bukti GET /employee meng-echo
    balik field yang SAMA PERSIS (beda kasus dari sales.branchs[] Customer
    yang polanya sudah lebih establish di project ini). Kalau field ini
    kosong/nama beda di response nyata, method ini FAIL-FAST dengan pesan
    jelas (lihat _resolve_salesman()), BUKAN diam-diam skip semua customer.

    Desain LOKAL-FILTER (bukan per-request-eSuite): pencocokan branch
    customer vs salesman dihitung SELURUHNYA dari data yang sudah di-GET
    (tidak perlu call tambahan per customer), BARU customer yang LOLOS
    filter di-push ke eSuite lewat batch (pola sama persis
    customer_sync_service.py -- per-batch independen, 1 batch gagal TIDAK
    menghentikan batch lain). Payload push SENGAJA MINIMAL (cuma
    `external_code` + `sales.salesmans[]`, TANPA field lain) -- pola SAMA
    dengan customer_geolocation_service.py/deactivate endpoints, partial-
    merge upsert eSuite tidak akan reset field lain (branch existing customer
    TIDAK disentuh sama sekali, karena key "branchs" tidak ikut dikirim).
    """

    def __init__(self):
        self.esuite = EsuiteClient()

    def map_all_to_one_salesman(
        self,
        salesman_id: str,
        limit: int | None = None,
        dry_run: bool = False,
        batch_size: int | None = None,
    ) -> dict:
        salesman_internal, salesman_branch_ids = self._resolve_salesman(salesman_id)

        all_customers = self._pull_all_customers()
        total_customers = len(all_customers)

        eligible_codes: list[str] = []
        skipped: list[dict] = []
        for record in all_customers:
            external_code = record.get("external_code") or ""
            customer_branch_ids = self._branch_ids_of(record)

            if not customer_branch_ids:
                skipped.append(
                    {"external_code": external_code, "reason": "customer_no_branch"}
                )
                continue

            if not (customer_branch_ids & salesman_branch_ids):
                skipped.append(
                    {
                        "external_code": external_code,
                        "reason": "branch_mismatch",
                        "customer_branch_ids": sorted(customer_branch_ids),
                        "salesman_branch_ids": sorted(salesman_branch_ids),
                    }
                )
                continue

            eligible_codes.append(external_code)

        # limit -- diagnostic aid buat test bertahap (mis. 5 dulu) sebelum
        # full run, pola sama customer_sync_service.py::sync(). Diterapkan
        # SETELAH filtering, supaya limit=5 artinya "5 customer ELIGIBLE
        # pertama", bukan "5 customer PERTAMA dari eSuite" yang belum tentu
        # eligible.
        if limit is not None:
            eligible_codes = eligible_codes[:limit]

        payload = [
            {"external_code": code, "sales": {"salesmans": [salesman_internal]}}
            for code in eligible_codes
        ]

        result: dict = {
            "salesman_id": salesman_id,
            "salesman_resolved": salesman_internal,
            "salesman_branch_ids": sorted(salesman_branch_ids),
            "total_customers_checked": total_customers,
            "eligible_count": len(eligible_codes),
            "skipped_count": len(skipped),
            "skipped": skipped,
            "dry_run": dry_run,
        }

        if dry_run:
            # dry_run -- TIDAK ADA push ke eSuite sama sekali, cuma preview
            # payload yang AKAN dikirim -- dipakai buat cek jumlah
            # eligible/skipped masuk akal SEBELUM full run beneran.
            result["payload_preview"] = payload
            return result

        size = batch_size or DEFAULT_BATCH_SIZE
        batches = [payload[i : i + size] for i in range(0, len(payload), size)]

        batch_results = []
        synced_count = 0
        failed_count = 0
        for idx, batch in enumerate(batches, start=1):
            try:
                esuite_result = self.esuite.push("customers", event="upsert", data=batch)
                batch_results.append(
                    {
                        "batch": idx,
                        "size": len(batch),
                        "status": "success",
                        "external_codes": [item["external_code"] for item in batch],
                        "esuite_response": esuite_result,
                    }
                )
                synced_count += len(batch)
            except AppError as e:
                # Sengaja di-catch PER BATCH (bukan biar propagate) -- supaya
                # batch lain tetap lanjut jalan kalau 1 batch gagal, pola
                # SAMA PERSIS customer_sync_service.py::sync().
                batch_results.append(
                    {
                        "batch": idx,
                        "size": len(batch),
                        "status": "failed",
                        "external_codes": [item["external_code"] for item in batch],
                        "error": e.to_dict()["error"],
                    }
                )
                failed_count += len(batch)

        result["batch_size"] = size
        result["batch_count"] = len(batches)
        result["synced_count"] = synced_count
        result["failed_count"] = failed_count
        result["batches"] = batch_results
        return result

    # ------------------------------------------------------------------
    def _resolve_salesman(self, salesman_id: str) -> tuple[dict, set]:
        """
        Resolve 1 salesman_id (employee_id) -> ({"id","name"} internal
        eSuite, set branch_id yang jadi tempat salesman ini terdaftar).
        Pola resolve SAMA dengan _resolve_salesmen() di service lain (GET
        /employee?employee_id=...), tapi di sini juga ambil "branches[]".
        """
        result = self.esuite.pull_by_param("employee", "employee_id", salesman_id)
        records = result.get("data") or []
        if not records:
            raise ValidationError(
                f"salesman_id '{salesman_id}' tidak ditemukan di eSuite (GET "
                "/employee kosong) -- cek employee_id benar",
                details={"salesman_id": salesman_id},
            )
        record = records[0]
        salesman_internal = {"id": record.get("id") or "", "name": record.get("name") or ""}

        branch_ids = {
            b.get("id") for b in (record.get("branches") or []) if b.get("id")
        }
        if not branch_ids:
            raise ValidationError(
                f"Salesman '{salesman_id}' tidak punya branches[] di response GET "
                "/employee (atau field 'branches' tidak ada/nama beda -- BELUM "
                "dikonfirmasi vendor, lihat docstring class) -- mass mapping "
                "dihentikan karena tidak ada customer yang bisa match branch.",
                details={"salesman_id": salesman_id, "employee_record": record},
            )
        return salesman_internal, branch_ids

    def _pull_all_customers(self) -> list[dict]:
        """GET /customers, paginated, SEMUA halaman (bukan cuma sampai code tertentu ketemu)."""
        all_customers: list[dict] = []
        page = 1
        while True:
            pulled = self.esuite.pull("customers", page=page, limit=PULL_PAGE_SIZE)
            batch = pulled.get("data") or []
            all_customers.extend(batch)

            meta = pulled.get("meta") or {}
            total_page = meta.get("total_page", page)
            if page >= total_page or not batch:
                break
            page += 1

        return all_customers

    @staticmethod
    def _branch_ids_of(customer_record: dict) -> set:
        """
        Ambil set branch_id dari 1 record GET /customers -- field
        `sales.branchs[]` (TANPA 'e', pola sama yang sudah dipakai
        customer_upsert_geo_branch_sales_service.py::_get_existing_branches()).
        """
        branchs = (customer_record.get("sales") or {}).get("branchs") or []
        return {b.get("id") for b in branchs if b.get("id")}
