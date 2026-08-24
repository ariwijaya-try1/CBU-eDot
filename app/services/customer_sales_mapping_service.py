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
    user). `salesman_names` sekarang OPSIONAL: kalau diisi, dipakai apa
    adanya (override manual, mis. kalau GET /employee down atau nama di
    eSuite mau dikoreksi paksa); kalau kosong (default), nama di-resolve
    otomatis per salesman_id lewat `_resolve_salesmen()`.
    """

    def __init__(self):
        self.esuite = EsuiteClient()

    def map_to_sales(
        self,
        external_codes: str,
        branch_external_codes: str,
        salesman_ids: str,
        salesman_names: str | None = None,
    ) -> dict:
        codes = [c.strip() for c in external_codes.split(",") if c.strip()]
        if not codes:
            raise ValidationError("external_codes wajib diisi minimal 1")

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

        if salesman_names:
            # Override manual (opsional) -- caller tetap bisa paksa isi nama
            # sendiri, mis. kalau GET /employee lagi down.
            sname_list = [n.strip() for n in salesman_names.split(",") if n.strip()]
            if len(sid_list) != len(sname_list):
                raise ValidationError(
                    "jumlah salesman_ids dan salesman_names harus SAMA (berpasangan "
                    "posisi 1-1, salesman_ids[0] <-> salesman_names[0], dst)",
                    details={"salesman_ids": sid_list, "salesman_names": sname_list},
                )
            salesmans_payload = [
                {"id": sid, "name": sname} for sid, sname in zip(sid_list, sname_list)
            ]
        else:
            # Default (24 Agustus 2026): auto-resolve nama dari eSuite,
            # hindari typo manual.
            salesmans_payload = self._resolve_salesmen(sid_list)

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

        payload = [
            {
                "external_code": code,
                "sales": {"branchs": branchs_payload, "salesmans": salesmans_payload},
            }
            for code in codes
        ]
        esuite_result = self.esuite.push("customers", event="upsert", data=payload)

        return {
            "mapped_count": len(payload),
            "external_codes": codes,
            "branchs_resolved": branchs_payload,
            "salesmans": salesmans_payload,
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _resolve_salesmen(self, sid_list: list[str]) -> list[dict]:
        """
        Resolve employee_id Salesman -> {id, name} via GET eSuite
        /employee?employee_id=... (per-id, BUKAN pull-list-lalu-filter
        seperti _resolve_branches() -- endpoint ini memang didesain lookup
        1 employee_id per call, response tetap bentuk {"data": [...]} berisi
        1 record). Dipakai sebagai default (24 Agustus 2026) supaya caller
        cukup kasih salesman_ids, tidak perlu ketik nama manual (hindari
        typo -- nama tidak muncul benar di UI eSuite kalau typo, pola sama
        seperti gap customer_groups[].name).

        `id` yang dikirim balik ke payload sales.salesmans[] TETAP sid asli
        (employee_id, mis. "202600002") -- BUKAN `id` internal eSuite (mis.
        "6a695ce7..."), karena field itu yang sudah terbukti dipakai &
        bekerja di payload sales.salesmans[] sebelumnya (lihat sample
        maping-customer-sales.json) -- cuma nama-nya yang di-auto-resolve.

        Return: [{"id": sid, "name": ...}, ...] urutan sama dengan sid_list.
        """
        resolved = []
        for sid in sid_list:
            result = self.esuite.pull_by_param("employee", "employee_id", sid)
            records = result.get("data") or []
            if not records:
                raise ValidationError(
                    f"salesman_id '{sid}' tidak ditemukan di eSuite (GET "
                    "/employee kosong) -- cek employee_id benar, atau isi "
                    "salesman_names manual sebagai override",
                    details={"salesman_id": sid},
                )
            resolved.append({"id": sid, "name": records[0].get("name") or ""})
        return resolved

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
