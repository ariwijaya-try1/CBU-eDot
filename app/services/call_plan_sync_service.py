"""
Call plan (jadwal kunjungan sales) Odoo -> eSuite -- 12 Oktober 2026.

Sumber: visit cycle Odoo (3 field Studio di Contact) per slot Salesperson,
dihitung jadi TANGGAL kunjungan oleh bridge (aturan minggu sales, lihat
visit_schedule_service.py), lalu dikirim ke webhook `POST /call-plan`
(jalur "Call Plan List" bertanggal, keputusan user 7 Oktober).

Format payload = contoh dev eDot 12 Oktober 2026 (contoh Postman vendor lama
SALAH): `employee.id` (id internal GET /employee), `customer.id`, `branch.id`,
`date_plan: {"date": <unix epoch detik>, "timezone": "+08:00"}`, `type`.
21 Oktober 2026 (jawaban dev): `type` = "generated" (tampil "Call Plan",
dihitung di KPI/laporan); kirim ulang external_code sama = update type.

Aturan:
- Mapping slot Odoo -> akun eDot: app/core/salesman_slots.py (di bridge).
- Baris visit tidak valid -> dilewati + dilaporkan (diperbaiki di Odoo).
- Customer belum ada di eSuite / branch-nya beda dgn branch salesman ->
  dilewati + dilaporkan (eSuite menolak beda branch).
- `external_code` = ODOO-CP-{id partner}-{YYYYMMDD}: tetap sama tiap kirim,
  supaya kirim ulang tidak membuat jadwal baru (KALAU eSuite upsert by
  external_code -- BELUM dites).
- `date_plan` = tanggal kunjungan jam 00:00 UTC (= 07:00 WIB / 08:00 WITA,
  tanggalnya sama di semua zona; sama dgn contoh dev).
"""
import time
from datetime import date, datetime, timedelta, timezone

from app.clients.esuite_client import EsuiteClient
from app.clients.odoo_client import OdooClient
from app.core.exceptions import AppError, ValidationError
from app.core.salesman_slots import SLOTS_BY_NAME
from app.core.sync_logger import log_sync_result
from app.services.visit_schedule_service import (
    CUSTOMER_EXTERNAL_CODE_PREFIX,
    CYCLE_RULES,
    DAY_LABELS,
    DAY_NAMES,
    VISIT_CYCLE_FIELD,
    VISIT_DAY_FIELD,
    VISIT_FIELDS,
    VISIT_FREQUENCY_FIELD,
    VisitScheduleService,
    _normalize,
    week_of_month,
)

ENTITY_PATH = "call-plan"
DELIVERY_ROUTE_FIELD = "x_studio_delivery_route"  # info saja di response
EXTERNAL_CODE_PREFIX = "ODOO-CP-"
# 16 Oktober 2026 -- mode tes (test_employee_id): data visit slot Odoo dikirim
# ke akun eSuite lain (akun testing). Kode dibedakan supaya TIDAK menimpa
# call plan asli slot tsb (upsert by external_code, terbukti 12 Oktober).
TEST_EXTERNAL_CODE_PREFIX = "ODOO-CP-TEST-"

# 21 Oktober 2026 (dev): "generated" = jadwal rutin -> tampil "Call Plan" &
# dihitung di KPI. Wajib huruf kecil persis (salah ketik tampil "Random").
# Sebelumnya "non_generated" (Non - Call Plan).
CALL_PLAN_TYPE = "generated"
# 21 Oktober 2026 (dev): tanpa timezone tanggal dihitung UTC. Semua slot
# sales saat ini Bali (WITA). Epoch tetap 00:00 UTC (= 08:00 WITA, tgl sama).
CALL_PLAN_TIMEZONE = "+08:00"

MAX_RANGE_DAYS = 31          # batas rentang tanggal per request (pengaman)
DEFAULT_BATCH_SIZE = 50
MAX_BATCH_SIZE = 100
BATCH_DELAY_SECONDS = 1.0    # jeda antar batch, sama pola outlet-stock


def epoch_utc_midnight(d: date) -> int:
    """Tanggal -> unix epoch (detik) jam 00:00 UTC. Contoh: 13 Okt 2026 -> 1791849600."""
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def visit_dates(cycle: str, day: str, date_from: date, date_to: date) -> list[date]:
    """Semua tanggal kunjungan dalam rentang utk 1 kombinasi cycle + hari (sudah valid)."""
    weeks, _ = CYCLE_RULES[cycle]
    target_weekday = DAY_NAMES[day]
    result = []
    d = date_from
    while d <= date_to:
        if d.weekday() == target_weekday and (weeks is None or week_of_month(d)[2] in weeks):
            result.append(d)
        d += timedelta(days=1)
    return result


class CallPlanSyncService:
    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(
        self,
        slots: list[str],
        date_from: date,
        date_to: date,
        dry_run: bool = True,
        batch_size: int | None = None,
        include_payload: bool = False,
        test_employee_id: str | None = None,
        external_codes: str | None = None,
        limit: int | None = None,
    ) -> dict:
        self._validate_range(date_from, date_to)
        if not slots:
            raise ValidationError("Pilih minimal 1 slot sales", details={"slots": slots})
        test_employee_id = (test_employee_id or "").strip() or None
        if test_employee_id and len(set(slots)) != 1:
            raise ValidationError(
                "Mode tes (test_employee_id) hanya boleh 1 slot",
                details={"slots": slots, "test_employee_id": test_employee_id},
            )
        # Filter customer tertentu (opsional), format ODOO-PARTNER-{id}.
        wanted_codes = {c.strip() for c in (external_codes or "").split(",") if c.strip()}
        resolved_batch_size = min(batch_size or DEFAULT_BATCH_SIZE, MAX_BATCH_SIZE)

        # 1. Customer ber-visit (semua) -> id Salesperson diambil dari field
        # user_id customer itu sendiri, bukan cari res.users (12 Oktober:
        # cari res.users by nama mengembalikan 0 di live -- kemungkinan akses
        # akun API / user slot tidak aktif / share).
        partners_all = self.odoo.get_customers_with_visit_schedule(VISIT_FIELDS)
        user_ids_by_name: dict[str, set[int]] = {}
        for p in partners_all:
            if p.get("user_id"):
                user_ids_by_name.setdefault(p["user_id"][1], set()).add(p["user_id"][0])

        # 2. Resolve slot: id Odoo (dari customer) + akun eSuite (id internal & branch).
        slot_infos = [self._resolve_slot(name, user_ids_by_name, test_employee_id) for name in dict.fromkeys(slots)]
        by_user_id = {s["odoo_user_id"]: s for s in slot_infos}

        # 3. Customer ber-visit milik slot terpilih -> tanggal kunjungan.
        vs = VisitScheduleService()
        selections = {f: vs._selection_map(f) for f in VISIT_FIELDS}
        partners = [p for p in partners_all if p.get("user_id") and p["user_id"][0] in by_user_id]
        if wanted_codes:
            partners = [p for p in partners if f"{CUSTOMER_EXTERNAL_CODE_PREFIX}{p['id']}" in wanted_codes]

        invalid_rows, planned = [], []
        for p in partners:
            slot = by_user_id.get(p["user_id"][0]) if p.get("user_id") else None
            if not slot:
                continue
            slot["customers_with_visit_data"] += 1
            cycle = _normalize(p.get(VISIT_CYCLE_FIELD), selections[VISIT_CYCLE_FIELD])
            day = _normalize(p.get(VISIT_DAY_FIELD), selections[VISIT_DAY_FIELD])
            freq = _normalize(p.get(VISIT_FREQUENCY_FIELD), selections[VISIT_FREQUENCY_FIELD])
            base = {
                "odoo_slot": slot["odoo_slot"],
                "odoo_partner_id": p["id"],
                "customer_external_code": f"{CUSTOMER_EXTERNAL_CODE_PREFIX}{p['id']}",
                "customer_name": p.get("name"),
                "visit_cycle": cycle or None,
                "visit_day": day or None,
                "visit_frequency": freq or None,
            }
            reason = VisitScheduleService._invalid_reason(cycle, day, freq)
            if reason:
                slot["invalid_count"] += 1
                invalid_rows.append({**base, "reason": reason})
                continue
            slot["valid_schedule_count"] += 1
            for d in visit_dates(cycle, day, date_from, date_to):
                planned.append({**base, "date": d, "slot": slot})

        # 3. Guard customer eSuite (harus ada + branch sama dgn salesman).
        codes = {v["customer_external_code"] for v in planned}
        esuite_customers = self.esuite.find_by_external_codes("customers", codes) if codes else {}

        routes = self._delivery_routes() if planned else {}

        visits, items, skipped = [], [], []
        not_mapped_codes = set()
        for v in planned:
            slot = v.pop("slot")
            d = v.pop("date")
            row = {
                **v,
                "date": d.isoformat(),
                "day": DAY_LABELS[d.weekday()],
                "week_of_month": week_of_month(d)[2],
                "call_plan_external_code": f"{slot['call_plan_code_prefix']}{v['odoo_partner_id']}-{d:%Y%m%d}",
                "delivery_route": routes.get(v["odoo_partner_id"]),
            }
            customer = esuite_customers.get(v["customer_external_code"])
            if not customer:
                skipped.append({**row, "reason": "customer belum ada di eSuite"})
                continue
            sales = customer.get("sales") or {}
            customer_branch_ids = [b.get("id") for b in (sales.get("branchs") or [])]
            branch_id = next((b for b in slot["esuite_branch_ids"] if b in customer_branch_ids), None)
            if not branch_id:
                skipped.append({
                    **row,
                    "reason": "branch customer di eSuite beda dgn branch salesman",
                    "customer_branch_ids": customer_branch_ids,
                    "salesman_branch_ids": slot["esuite_branch_ids"],
                })
                continue

            # Info saja (tidak di-skip): syarat ini belum dikonfirmasi dev.
            mapped = slot["esuite_id"] in {s.get("id") for s in (sales.get("salesmans") or [])}
            if not mapped:
                not_mapped_codes.add(v["customer_external_code"])
            row["salesman_mapped_on_customer"] = mapped

            if limit and len(visits) >= limit:
                continue  # batas jumlah jadwal (tes kecil); sisanya tidak dikirim
            visits.append(row)
            slot["visit_count"] += 1
            items.append({
                "external_code": row["call_plan_external_code"],
                "type": CALL_PLAN_TYPE,
                "employee": {"id": slot["esuite_id"]},
                "customer": {"id": customer.get("id")},
                "branch": {"id": branch_id},
                "date_plan": {"date": epoch_utc_midnight(d), "timezone": CALL_PLAN_TIMEZONE},
            })

        # Ringkasan per tanggal -> rute (info utk dicocokkan dgn jadwal sales).
        per_date_route: dict[str, dict[str, int]] = {}
        for r in visits:
            day_routes = per_date_route.setdefault(f"{r['date']} {r['day']}", {})
            key = r["delivery_route"] or "(tanpa rute)"
            day_routes[key] = day_routes.get(key, 0) + 1

        batches = [items[i:i + resolved_batch_size] for i in range(0, len(items), resolved_batch_size)]
        result = {
            "dry_run": dry_run,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "call_plan_type": CALL_PLAN_TYPE,
            "test_mode": bool(test_employee_id),
            "limit": limit,
            "slots": [dict(s) for s in slot_infos],
            "visit_count": len(items),
            "skipped_count": len(skipped),
            "invalid_count": len(invalid_rows),
            "customer_not_mapped_to_salesman_count": len(not_mapped_codes),
            "batch_size": resolved_batch_size,
            "batch_count": len(batches),
            "per_date_route": per_date_route,
            "visits": visits,
            "skipped": skipped,
            "invalid_rows": invalid_rows,
            "note": (
                "Respons 200 dari eSuite BELUM bukti tersimpan -- cek di eSuite: "
                "ework -> Call Plan List (filter tanggal + salesman)."
            ),
        }
        if include_payload:
            result["payload"] = {"event": "upsert", "data": items}
        if dry_run:
            return result

        # 4. Push berurutan per batch; 1 batch gagal tidak menghentikan batch lain.
        pushed, failed, batch_results = 0, 0, []
        for idx, batch in enumerate(batches, start=1):
            entry = {"batch": idx, "size": len(batch)}
            try:
                response = self.esuite.push(ENTITY_PATH, "upsert", batch)
                pushed += len(batch)
                entry["status"] = "sent"
                entry["esuite_response"] = response
            except AppError as exc:
                failed += len(batch)
                entry["status"] = "failed"
                entry["error"] = exc.to_dict().get("error")
                entry["external_codes"] = [i["external_code"] for i in batch]
            batch_results.append(entry)
            if idx < len(batches):
                time.sleep(BATCH_DELAY_SECONDS)

        result.update({"pushed_count": pushed, "failed_count": failed, "batches": batch_results})
        log_sync_result(
            "call_plan",
            "upsert",
            {"synced_count": pushed, "failed_count": failed, "total_matched_in_odoo": len(items)},
            note=f"{date_from}..{date_to} slots={','.join(s['odoo_slot'] for s in slot_infos)}",
        )
        return result

    def _delivery_routes(self) -> dict[int, str]:
        """
        id partner -> rute pengiriman (`x_studio_delivery_route`), INFO saja
        utk cek jadwal vs rute sales (12 Oktober). Gagal baca = kosong, tidak
        menggagalkan sync.
        """
        try:
            rows = self.odoo.get_customer_field_values(DELIVERY_ROUTE_FIELD)
        except AppError:
            return {}
        result = {}
        for r in rows:
            value = r.get(DELIVERY_ROUTE_FIELD)
            if isinstance(value, list):  # many2one [id, name]
                value = value[1] if len(value) > 1 else None
            if value:
                result[r["id"]] = str(value)
        return result

    @staticmethod
    def _validate_range(date_from: date, date_to: date) -> None:
        if date_to < date_from:
            raise ValidationError(
                "date_to tidak boleh sebelum date_from",
                details={"date_from": str(date_from), "date_to": str(date_to)},
            )
        days = (date_to - date_from).days + 1
        if days > MAX_RANGE_DAYS:
            raise ValidationError(
                f"Rentang maksimal {MAX_RANGE_DAYS} hari per request (diminta {days} hari) -- jalankan bertahap",
                details={"date_from": str(date_from), "date_to": str(date_to)},
            )

    def _resolve_slot(
        self, odoo_slot: str, user_ids_by_name: dict[str, set[int]], test_employee_id: str | None = None
    ) -> dict:
        mapping = SLOTS_BY_NAME.get(odoo_slot)
        if not mapping:
            raise ValidationError(
                f"Slot '{odoo_slot}' tidak ada di tabel mapping (app/core/salesman_slots.py)",
                details={"odoo_slot": odoo_slot},
            )

        # Odoo: nama slot harus PERSIS sama dgn Salesperson di customer ber-visit,
        # dan menunjuk tepat 1 id.
        user_ids = sorted(user_ids_by_name.get(odoo_slot, set()))
        if len(user_ids) != 1:
            raise ValidationError(
                f"Slot Odoo '{odoo_slot}' ditemukan di {len(user_ids)} Salesperson customer ber-visit "
                "(harus tepat 1) -- cek nama Salesperson di Odoo atau tabel mapping",
                details={
                    "odoo_slot": odoo_slot,
                    "found_user_ids": user_ids,
                    "salespersons_with_visit_data": sorted(user_ids_by_name),
                },
            )

        # eSuite: employee_id -> id internal + branch. Mode tes: akun pengganti.
        employee_id = test_employee_id or mapping["esuite_employee_id"]
        records = (self.esuite.pull_by_param("employee", "employee_id", employee_id).get("data") or [])
        if not records:
            raise ValidationError(
                f"Akun eSuite employee_id '{employee_id}' (slot '{odoo_slot}') tidak ditemukan",
                details={"odoo_slot": odoo_slot, "esuite_employee_id": employee_id},
            )
        emp = records[0]
        branch_ids = [b.get("id") for b in (emp.get("branches") or []) if b.get("id")]
        if not branch_ids:
            raise ValidationError(
                f"Akun eSuite '{emp.get('name')}' (slot '{odoo_slot}') tidak punya branch",
                details={"odoo_slot": odoo_slot, "esuite_employee_id": employee_id},
            )

        warnings = []
        if test_employee_id:
            warnings.append(f"MODE TES: jadwal slot '{odoo_slot}' dikirim ke akun '{emp.get('username')}', bukan '{mapping['esuite_username']}'")
        elif emp.get("username") and emp.get("username") != mapping["esuite_username"]:
            warnings.append(
                f"username eSuite '{emp.get('username')}' beda dgn tabel mapping '{mapping['esuite_username']}'"
            )
        if emp.get("status") and emp.get("status") != "active":
            warnings.append(f"status akun eSuite '{emp.get('status')}'")

        return {
            "odoo_slot": odoo_slot,
            "odoo_user_id": user_ids[0],
            "person": "TEST" if test_employee_id else mapping["person"],
            "esuite_employee_id": employee_id,
            "call_plan_code_prefix": (
                f"{TEST_EXTERNAL_CODE_PREFIX}{employee_id}-" if test_employee_id else EXTERNAL_CODE_PREFIX
            ),
            "esuite_id": emp.get("id"),
            "esuite_name": emp.get("name"),
            "esuite_username": emp.get("username"),
            "esuite_branch_ids": branch_ids,
            "warnings": warnings,
            "customers_with_visit_data": 0,
            "valid_schedule_count": 0,
            "invalid_count": 0,
            "visit_count": 0,
        }
