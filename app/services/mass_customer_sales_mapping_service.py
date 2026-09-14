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
    di eSuite) ke SALESMAN sekaligus, KHUSUS masa PRE-LIVE (utility sekali
    pakai buat percepat setup awal, BUKAN endpoint permanen jangka panjang
    seperti /mapping/customer-sales).

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
    jelas (lihat _resolve_salesmen()), BUKAN diam-diam skip semua customer.

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

    UPDATE 14 September 2026 -- MULTI salesman + param `mode` ("add"/"reset"),
    root cause: `salesman_id` TUNGGAL lama selalu OVERWRITE total
    `salesmans[]` existing customer (payload cuma isi 1 salesman), jadi run
    kedua dgn salesman lain BUKAN nambah tapi GANTIKAN salesman run pertama
    -- ditemukan user dari kasus nyata (4 salesman pindah branch, coba
    tambahkan bertahap, salesman lama ke-hapus tiap run baru). Redesign
    (dikonfirmasi user via AskUserQuestion, 14 September 2026):
    - `salesman_id` -> `salesman_ids` (comma-separated, MULTI, employee_id).
    - `mode="add"` (BARU, JADI DEFAULT -- keputusan eksplisit user, BUKAN
      rekomendasi awal Claude yang sarankan "reset" demi backward-compat;
      endpoint ini PRE-LIVE utility TANPA caller existing yang bergantung ke
      perilaku lama, jadi user pilih default paling sering dibutuhkan) --
      salesman EXISTING di eSuite per customer (dibaca LANGSUNG dari record
      hasil `_pull_all_customers()` yang SUDAH di-GET di awal, TANPA call
      tambahan -- lihat `_salesmans_of()`) DIPERTAHANKAN + salesman baru yang
      match branch DITAMBAHKAN (dedupe by id). `mode="reset"` -- salesmans
      customer DITIMPA total, HANYA berisi salesman yang match branch dari
      request ini (perilaku setara versi lama, tapi generalized ke multi).
    - Filter branch PER-CUSTOMER (dikonfirmasi user, opsi "Recommended" dari
      2 opsi yang diajukan): kalau `salesman_ids` isinya salesman dari BEDA
      branch, 1 customer HANYA dapat subset salesman yang branch-nya BENERAN
      cocok sama branch customer itu -- BUKAN semua salesman yang diminta
      (hindari assign salesman salah branch ke customer). Customer yang
      branch-nya tidak cocok SATU PUN dari `salesman_ids` -- tetap DI-SKIP
      (reason "branch_mismatch"), sama seperti perilaku lama.
    - `_salesmans_of()` (BARU) mengasumsikan record `GET /customers` yang
      sudah ditarik `_pull_all_customers()` juga bawa `sales.salesmans[]`
      (sibling field dari `sales.branchs[]` yang SUDAH terbukti ada di
      record yang sama, dipakai `_branch_ids_of()`) -- BELUM eksplisit
      diverifikasi live utk field spesifik ini, cek response nyata pas
      dry_run pertama pasca update ini.
    """

    def __init__(self):
        self.esuite = EsuiteClient()

    def map_all_to_salesmen(
        self,
        salesman_ids: str,
        mode: str = "add",
        limit: int | None = None,
        dry_run: bool = False,
        batch_size: int | None = None,
    ) -> dict:
        if mode not in ("add", "reset"):
            raise ValidationError(
                "mode harus 'add' atau 'reset'",
                details={"mode": mode},
            )

        sid_list = [s.strip() for s in salesman_ids.split(",") if s.strip()]
        if not sid_list:
            raise ValidationError("salesman_ids wajib diisi minimal 1")

        resolved_salesmen = self._resolve_salesmen(sid_list)
        # Union SEMUA branch dari salesman yang diminta -- dipakai cuma buat
        # laporan/ringkasan di response, BUKAN dipakai langsung filter
        # eligibility (filter sebenarnya PER-CUSTOMER, lihat loop bawah).
        all_requested_branch_ids: set = set()
        for r in resolved_salesmen:
            all_requested_branch_ids |= r["branch_ids"]

        all_customers = self._pull_all_customers()
        total_customers = len(all_customers)

        eligible_codes: list[str] = []
        payload_by_code: dict[str, dict] = {}
        skipped: list[dict] = []
        for record in all_customers:
            external_code = record.get("external_code") or ""
            customer_branch_ids = self._branch_ids_of(record)

            if not customer_branch_ids:
                skipped.append(
                    {"external_code": external_code, "reason": "customer_no_branch"}
                )
                continue

            # Filter PER-CUSTOMER (opsi "Recommended" dikonfirmasi user,
            # 14 September 2026): customer ini cuma dapat SUBSET
            # salesman_ids yang branch-nya BENERAN cocok -- bukan semua
            # salesman yang diminta kalau salesman_ids dicampur beda branch.
            matching_salesmen = [
                r["internal"] for r in resolved_salesmen if r["branch_ids"] & customer_branch_ids
            ]
            if not matching_salesmen:
                skipped.append(
                    {
                        "external_code": external_code,
                        "reason": "branch_mismatch",
                        "customer_branch_ids": sorted(customer_branch_ids),
                        "requested_salesman_branch_ids": sorted(all_requested_branch_ids),
                    }
                )
                continue

            if mode == "add":
                existing_salesmen = self._salesmans_of(record)
                existing_ids = {s["id"] for s in existing_salesmen if s.get("id")}
                final_salesmans = existing_salesmen + [
                    s for s in matching_salesmen if s.get("id") not in existing_ids
                ]
            else:  # mode == "reset"
                final_salesmans = matching_salesmen

            eligible_codes.append(external_code)
            payload_by_code[external_code] = {
                "external_code": external_code,
                "sales": {"salesmans": final_salesmans},
            }

        # limit -- diagnostic aid buat test bertahap (mis. 5 dulu) sebelum
        # full run, pola sama customer_sync_service.py::sync(). Diterapkan
        # SETELAH filtering, supaya limit=5 artinya "5 customer ELIGIBLE
        # pertama", bukan "5 customer PERTAMA dari eSuite" yang belum tentu
        # eligible.
        # total eligible SEBELUM limit dipotong -- dipakai di response biar
        # total_eligible_found + skipped_count selalu == total_customers_checked,
        # tidak tergantung nilai limit (eligible_count di bawah TETAP jumlah
        # setelah limit, itu yang benar2 di-push/preview).
        total_eligible_found = len(eligible_codes)

        if limit is not None:
            eligible_codes = eligible_codes[:limit]

        payload = [payload_by_code[code] for code in eligible_codes]

        result: dict = {
            "salesman_ids": sid_list,
            "mode": mode,
            "salesmen_resolved": [
                {"internal": r["internal"], "branch_ids": sorted(r["branch_ids"])}
                for r in resolved_salesmen
            ],
            "total_customers_checked": total_customers,
            "total_eligible_found": total_eligible_found,
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
    def _resolve_salesmen(self, sid_list: list[str]) -> list[dict]:
        """
        Resolve BANYAK salesman_id (employee_id) -> list [{"internal":
        {"id","name"}, "branch_ids": set}, ...], urutan sama dengan
        sid_list. Pola resolve SAMA dengan _resolve_salesmen() di service
        lain (GET /employee?employee_id=...), tapi di sini juga ambil
        "branches[]" per salesman.

        FAIL-FAST per salesman (SAMA seperti perilaku lama _resolve_salesman()
        tunggal) -- kalau SATU SAJA dari salesman_ids tidak ketemu ATAU tidak
        punya branches[], SELURUH request dihentikan dgn error jelas (bukan
        skip diam-diam salesman itu doang) -- konsisten dgn convention
        project ini (surface masalah data eksplisit, jangan degrade diam2).
        """
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
            salesman_internal = {"id": record.get("id") or "", "name": record.get("name") or ""}

            branch_ids = {
                b.get("id") for b in (record.get("branches") or []) if b.get("id")
            }
            if not branch_ids:
                raise ValidationError(
                    f"Salesman '{sid}' tidak punya branches[] di response GET "
                    "/employee (atau field 'branches' tidak ada/nama beda -- BELUM "
                    "dikonfirmasi vendor, lihat docstring class) -- mass mapping "
                    "dihentikan karena salesman ini tidak akan pernah bisa match "
                    "branch customer manapun.",
                    details={"salesman_id": sid, "employee_record": record},
                )
            resolved.append({"internal": salesman_internal, "branch_ids": branch_ids})
        return resolved

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

    @staticmethod
    def _salesmans_of(customer_record: dict) -> list[dict]:
        """
        Ambil salesmans[] EXISTING dari 1 record GET /customers -- dipakai
        KHUSUS mode="add" (🆕 14 September 2026), supaya salesman lama TIDAK
        ke-reset saat nambah salesman baru. Field `sales.salesmans[]`,
        sibling dari `sales.branchs[]` yang dipakai `_branch_ids_of()` --
        TIDAK BUTUH call tambahan, record ini SUDAH di-GET oleh
        `_pull_all_customers()` di awal `map_all_to_salesmen()`.

        Return: list apa adanya dari eSuite ([{"id","name"}, ...]) -- []
        kalau customer belum punya salesman.
        """
        return (customer_record.get("sales") or {}).get("salesmans") or []
