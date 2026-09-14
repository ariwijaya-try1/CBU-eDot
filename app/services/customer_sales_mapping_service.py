from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError


class CustomerSalesMappingService:
    """
    Mass mapping Customer -> Branch + Salesman di eSuite sekaligus (field
    `sales.branchs[]` + `sales.salesmans[]`).

    GANTI/GABUNGAN dari CustomerSalesmanMappingService lama (customer_salesman_
    mapping_service.py, HAPUS -- BAHAYA, JANGAN DIPAKAI LAGI). Root cause:
    info langsung dari dev eSuite (WA, 22 Agustus 2026) -- `branchs` &
    `salesmans` di dalam object `sales` HARUS di-set BERSAMAAN dalam 1
    request. Kalau cuma kirim salah satu (mis. cuma `salesmans`), yang lain
    (`branchs`) JADI BLANK di eSuite -- BUKAN partial-merge seperti field
    top-level lain (name/status/dst tetap aman kalau tidak dikirim; tapi
    child DALAM `sales` saling menimpa/reset kalau tidak dikirim bersamaan).
    Endpoint lama cuma kirim `salesmans` -- kalau dipakai ke customer yang
    SUDAH punya branch ter-assign, itu bakal ke-blank-in tanpa peringatan.
    Endpoint ini WAJIB isi branch DAN salesman setiap panggilan, TIDAK ADA
    cara isi salah satu doang.

    Vendor eSuite juga konfirmasi: `name` WAJIB diisi di tiap entry
    branchs/salesmans -- kalau tidak, mapping "berhasil" secara data TAPI
    nama tidak muncul di UI company-platform (pola sama dengan
    customer_groups, lihat CustomerGroupingService).

    UPDATE 24 Agustus 2026 -- nama Salesman sekarang di-AUTO-RESOLVE dari
    eSuite (GET /employee?employee_id=...), BUKAN wajib manual lagi. Root
    cause lama ("bridge tidak punya sumber data Salesman") TERNYATA tidak
    berlaku -- eSuite sendiri punya endpoint lookup employee by id (info
    user). `salesman_names` sekarang OPSIONAL: kalau diisi, HANYA override
    NAME yang ditampilkan; kalau kosong (default), nama JUGA di-resolve
    otomatis.

    RALAT 24 Agustus 2026 (dikoreksi user, sama sesi): `id` di payload
    sales.salesmans[] BUKAN employee_id (`salesman_ids`), TAPI id INTERNAL
    eSuite yang di-resolve dari GET /employee. Konsekuensinya: GET /employee
    SEKARANG WAJIB dipanggil di SETIAP request (bahkan saat `salesman_names`
    diisi manual) -- `salesman_names` TIDAK BISA lagi jadi fallback total
    kalau GET /employee down (beda dari niat awal), karena id internal
    tidak ada sumber lain. Lihat `_resolve_salesmen()` untuk detail.

    UPDATE 14 September 2026 -- param baru `mode` ("reset"/"add") di
    map_to_sales(). Kebutuhan: customer bisa punya LEBIH DARI 1 salesman
    (mis. tambah salesman baru tanpa lepas salesman lama yang masih
    valid). Sebelum ini, tiap panggilan SELALU replace total salesmans[]
    dengan isi `salesman_ids` request (tidak ada cara "nambah" tanpa tau
    & ikut nulis ulang id salesman lama secara manual di request).

    - `mode="reset"` (default, PERILAKU LAMA, tidak ada breaking change
      utk caller existing) -- salesmans[] di payload = HANYA hasil
      resolve `salesman_ids` request ini, menimpa total salesmans
      existing di eSuite.
    - `mode="add"` -- salesmans[] di payload = salesman existing (hasil
      GET /customers by external_code, per code) DIGABUNG dengan
      salesman baru dari `salesman_ids` (dedupe by `id` internal eSuite,
      existing tidak diduplikasi kalau kebetulan sama). Extra 1x GET
      /customers per external_code HANYA dipanggil saat mode="add" (lihat
      `_get_existing_salesmen()`).

    `branchs_payload` TIDAK terpengaruh mode ini -- tetap APA ADANYA dari
    `branch_external_codes` request (tidak di-merge dengan branch existing),
    konsisten dengan aturan lama di atas (branch WAJIB diisi eksplisit tiap
    call).
    """

    def __init__(self):
        self.esuite = EsuiteClient()

    def map_to_sales(
        self,
        external_codes: str,
        branch_external_codes: str,
        salesman_ids: str,
        salesman_names: str | None = None,
        mode: str = "reset",
    ) -> dict:
        codes = [c.strip() for c in external_codes.split(",") if c.strip()]
        if not codes:
            raise ValidationError("external_codes wajib diisi minimal 1")

        if mode not in ("reset", "add"):
            raise ValidationError(
                "mode harus 'reset' atau 'add'",
                details={"mode": mode},
            )

        branch_codes = [b.strip() for b in branch_external_codes.split(",") if b.strip()]
        if not branch_codes:
            raise ValidationError(
                "branch_external_codes wajib diisi minimal 1 -- branchs & "
                "salesmans WAJIB di-set BERSAMAAN (info dev eSuite), tidak "
                "bisa isi salesman doang (branch existing akan ke-blank-in)"
            )

        sid_list = [s.strip() for s in salesman_ids.split(",") if s.strip()]
        if not sid_list:
            raise ValidationError(
                "salesman_ids wajib diisi minimal 1 -- branchs & salesmans "
                "WAJIB di-set BERSAMAAN (info dev eSuite), tidak bisa isi "
                "branch doang (salesman existing akan ke-blank-in)"
            )

        # RALAT 24 Agustus 2026 (dikoreksi user): `id` yang dikirim ke payload
        # sales.salesmans[] BUKAN employee_id (sid) -- HARUS id internal
        # eSuite (field "id" di response GET /employee, mis.
        # "6a695ce79b7307901e351f33"), BUKAN "employee_id" (mis. "202600002").
        # Makanya GET /employee sekarang WAJIB dipanggil selalu (bukan cuma
        # saat auto-resolve nama) -- id internal itu SATU-SATUNYA sumbernya,
        # tidak ada cara lain buat dapetin dari caller. Lihat _resolve_salesmen().
        resolved_salesmen = self._resolve_salesmen(sid_list)

        if salesman_names:
            # Override manual (opsional) -- HANYA override NAME yang
            # ditampilkan, `id` TETAP dari hasil resolve di atas (WAJIB id
            # internal eSuite, tidak bisa di-supply manual oleh caller).
            sname_list = [n.strip() for n in salesman_names.split(",") if n.strip()]
            if len(sid_list) != len(sname_list):
                raise ValidationError(
                    "jumlah salesman_ids dan salesman_names harus SAMA (berpasangan "
                    "posisi 1-1, salesman_ids[0] <-> salesman_names[0], dst)",
                    details={"salesman_ids": sid_list, "salesman_names": sname_list},
                )
            salesmans_payload = [
                {"id": r["id"], "name": sname}
                for r, sname in zip(resolved_salesmen, sname_list)
            ]
        else:
            # Default (24 Agustus 2026): auto-resolve id+nama dari eSuite,
            # hindari typo manual & id salah.
            salesmans_payload = resolved_salesmen

        resolved_branches = self._resolve_branches(set(branch_codes))
        missing_branches = [c for c in branch_codes if c not in resolved_branches]
        if missing_branches:
            raise ValidationError(
                "branch_external_codes tidak ditemukan di eSuite -- cek dulu "
                "via GET /branches (mungkin belum pernah di-sync lewat "
                "/sync/branch, atau salah ketik)",
                details={"not_found": missing_branches},
            )

        branchs_payload = [
            {"id": resolved_branches[c]["id"], "name": resolved_branches[c]["name"]}
            for c in branch_codes
        ]

        # mode="add" -- salesmans[] per customer = existing (GET /customers,
        # per external_code -- existing salesman BISA BEDA antar customer
        # walau salesman_ids request-nya sama) + salesman baru dari request,
        # dedupe by "id" internal eSuite (existing menang urutan duluan,
        # salesman baru yang id-nya belum ada baru ditambahkan). mode="reset"
        # (default) -- tidak ada perubahan, salesmans_payload APA ADANYA dari
        # request seperti perilaku lama.
        payload = []
        salesmans_per_code: dict[str, list[dict]] = {}
        for code in codes:
            code_salesmans = salesmans_payload
            if mode == "add":
                existing_salesmen = self._get_existing_salesmen(code)
                existing_ids = {s["id"] for s in existing_salesmen if s.get("id")}
                code_salesmans = existing_salesmen + [
                    s for s in salesmans_payload if s.get("id") not in existing_ids
                ]
            salesmans_per_code[code] = code_salesmans
            payload.append(
                {
                    "external_code": code,
                    "sales": {"branchs": branchs_payload, "salesmans": code_salesmans},
                }
            )
        esuite_result = self.esuite.push("customers", event="upsert", data=payload)

        return {
            "mapped_count": len(payload),
            "external_codes": codes,
            "mode": mode,
            "branchs_resolved": branchs_payload,
            "salesmans": salesmans_payload,  # salesman dari REQUEST ini saja (tidak berubah, backward-compat)
            "salesmans_per_code": salesmans_per_code,  # salesman FINAL yang dikirim ke eSuite per customer (beda per code kalau mode="add")
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def unmap_from_sales(self, external_codes: str, clear_value: str = "null") -> dict:
        """
        Hapus mapping Branch DAN Salesman dari Customer SEKALIGUS. Kebalikan
        dari map_to_sales(), pakai root cause YANG SAMA (info dev eSuite, 22
        Agustus 2026): branchs & salesmans di dalam object `sales` saling
        ikut ke-reset kalau salah satu di-set tanpa yang lain -- jadi
        mengosongkan salah satu otomatis mengosongkan yang lain juga. TIDAK
        ADA cara unmap branch/salesman secara terpisah (batasan yang sama
        dengan map_to_sales(), bukan keterbatasan baru).

        RALAT 25 Agustus 2026 (dikoreksi user -- BUKAN dari vendor, temuan
        testing user sendiri): versi awal kirim `sales.branchs: []` &
        `sales.salesmans: []` (array kosong) -- TERNYATA eSuite
        memperlakukan array kosong itu SAMA SEPERTI field tidak dikirim sama
        sekali (partial-merge tidak ke-trigger, data lama TETAP ada). Dugaan
        kuat: backend eSuite pakai truthy-check ("kalau array kosong,
        skip") -- konsisten dengan overall behavior partial-merge yang
        sudah dikonfirmasi user di endpoint lain (field yang TIDAK dikirim
        = TIDAK berubah, mis. `phone` aman kalau mapping cuma kirim `sales`).

        Ganti default jadi kirim `null` (bukan `[]`) -- konvensi umum
        JSON merge-patch: `null` = "hapus/kosongkan field ini", beda makna
        dari array kosong. **BELUM ada konfirmasi vendor bahwa `null` ini
        pasti jalan** -- ini best-guess berdasarkan konvensi umum, BUKAN
        instruksi eSuite. Makanya param `clear_value` disediakan supaya bisa
        di-toggle & ditest langsung dari Swagger tanpa ubah kode lagi kalau
        `null` ternyata juga tidak berefek -- kalau KEDUANYA (`null` & `[]`)
        terbukti tidak jalan, itu kesimpulan kuat perlu tanya vendor
        langsung cara resmi clear array field (kemungkinan API tidak
        mendukung ini sama sekali).

        Field Customer lain (name/addresses/invoice/dst) TIDAK ikut
        dikirim/direset -- partial-merge tetap berlaku di level TOP payload,
        cuma object `sales` yang diganti isinya.
        """
        codes = [c.strip() for c in external_codes.split(",") if c.strip()]
        if not codes:
            raise ValidationError("external_codes wajib diisi minimal 1")

        if clear_value not in ("null", "empty_array"):
            raise ValidationError(
                "clear_value harus 'null' atau 'empty_array'",
                details={"clear_value": clear_value},
            )
        empty = None if clear_value == "null" else []

        payload = [
            {"external_code": code, "sales": {"branchs": empty, "salesmans": empty}}
            for code in codes
        ]
        esuite_result = self.esuite.push("customers", event="upsert", data=payload)

        return {
            "unmapped_count": len(payload),
            "external_codes": codes,
            "clear_value": clear_value,
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _resolve_salesmen(self, sid_list: list[str]) -> list[dict]:
        """
        Resolve employee_id Salesman -> {id, name} via GET eSuite
        /employee?employee_id=... (per-id, BUKAN pull-list-lalu-filter
        seperti _resolve_branches() -- endpoint ini memang didesain lookup
        1 employee_id per call, response tetap bentuk {"data": [...]} berisi
        1 record). SELALU dipanggil (bukan cuma saat auto-resolve nama) --
        lihat RALAT di bawah, `id` payload WAJIB hasil resolve ini.

        RALAT 24 Agustus 2026 (dikoreksi user, sebelumnya SALAH): `id` yang
        dikirim ke payload sales.salesmans[] BUKAN sid/employee_id (mis.
        "202600002"), TAPI `id` INTERNAL eSuite (field "id" di response GET
        /employee, mis. "6a695ce79b7307901e351f33"). Asumsi lama ("id = sid,
        terbukti jalan di sample maping-customer-sales.json") SALAH --
        sample itu sekadar contoh awal yang belum benar-benar divalidasi
        eSuite, dikoreksi user dari hasil GET /customers nyata (2 entry nama
        sama, id beda -- yang dipakai eSuite adalah id internal, bukan
        employee_id).

        employee_id (sid) TETAP dipakai sebagai query param lookup (`GET
        /employee?employee_id=sid`) -- itu satu-satunya cara resolve id
        internal, caller tidak mungkin tau/isi id internal secara manual.

        Return: [{"id": <id internal eSuite>, "name": ...}, ...] urutan
        sama dengan sid_list.
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
            resolved.append({"id": record.get("id") or "", "name": record.get("name") or ""})
        return resolved

    def _get_existing_salesmen(self, external_code: str) -> list[dict]:
        """
        Cek salesmans[] yang SUDAH ada di eSuite untuk 1 customer -- dipakai
        KHUSUS mode="add" (lihat map_to_sales()), supaya salesman lama TIDAK
        ikut ke-reset saat nambah salesman baru. 1x GET /customers by
        external_code per customer, pola SAMA dengan
        CustomerUpsertGeoBranchSalesService._get_existing_branches() (lihat
        file itu untuk alasan pola pull_by_param() vs full-scan).

        Return: list salesmans[] apa adanya dari eSuite ([{"id","name"}, ...])
        -- [] kalau customer belum ketemu di eSuite ATAU ketemu tapi belum
        punya salesman.
        """
        result = self.esuite.pull_by_param("customers", "external_code", external_code)
        records = result.get("data") or []
        if not records:
            return []
        record = records[0]
        return (record.get("sales") or {}).get("salesmans") or []

    def _resolve_branches(self, codes_wanted: set) -> dict:
        """
        Resolve external_code Branch -> {id, name} eSuite. PAKAI PULL LOOP
        MANUAL (BUKAN EsuiteClient.find_by_external_codes() generik) --
        external_code Branch NESTED di `basic_info.external_code`, BUKAN
        top-level. Ini gotcha yang SUDAH DIKETAHUI & didokumentasikan (lihat
        PricelistSyncService._resolve_branches(), root cause & fix persis
        sama, 18 Agustus 2026) -- pola pull loop di sini SENGAJA disalin
        dari situ, BUKAN reinvent.

        Himpunan Branch kecil (<=4 company in-scope) -- full-pull semua
        halaman aman & simpel, tidak perlu early-exit.

        Return: {external_code: {"id": ..., "name": ...}}
        """
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
