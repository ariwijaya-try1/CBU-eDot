"""
Call plan (jadwal kunjungan sales) Odoo -> eSuite -- 12 Oktober 2026.

Sumber: visit cycle Odoo (3 field Studio di Contact) per slot Salesperson,
dihitung jadi TANGGAL kunjungan oleh bridge (aturan minggu sales, lihat
visit_schedule_service.py), lalu dikirim ke webhook `POST /call-plan`
(jalur "Call Plan List" bertanggal, keputusan user 7 Oktober).

Format payload = contoh dev eDot 12 Oktober 2026 (contoh Postman vendor lama
SALAH): `employee.id` (id internal GET /employee), `customer.id`, `branch.id`,
`date_plan: {"date": <unix epoch detik>}`, `type`. Terverifikasi tampil di
UI Call Plan List (13/10/2026, type "Non - Call Plan").

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
EXTERNAL_CODE_PREFIX = "ODOO-CP-"

# Satu-satunya nilai yang terbukti tersimpan (dev 12 Oktober). Tampil di UI
# sebagai "Non - Call Plan" -- MENUNGGU jawaban dev nilai utk tipe "Call Plan".
CALL_PLAN_TYPE = "non_generated"

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
    ) -> dict:
        self._validate_range(date_from, date_to)
        if not slots:
            raise ValidationError("Pilih minimal 1 slot sales", details={"slots": slots})
        resolved_batch_size = min(batch_size or DEFAULT_BATCH_SIZE, MAX_BATCH_SIZE)

        # 1. Resolve slot: Odoo res.users id + akun eSuite (id internal & branch).
        slot_infos = [self._resolve_slot(name) for name in dict.fromkeys(slots)]
        by_user_id = {s["odoo_user_id"]: s for s in slot_infos}

        # 2. Customer ber-visit milik slot terpilih -> tanggal kunjungan.
        vs = VisitScheduleService()
        selections = {f: vs._selection_map(f) for f in VISIT_FIELDS}
        partners = self.odoo.get_customers_with_visit_schedule(
            VISIT_FIELDS, salesperson_ids=list(by_user_id)
        )

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
                "call_plan_external_code": f"{EXTERNAL_CODE_PREFIX}{v['odoo_partner_id']}-{d:%Y%m%d}",
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

            visits.append(row)
            slot["visit_count"] += 1
            items.append({
                "external_code": row["call_plan_external_code"],
                "type": CALL_PLAN_TYPE,
                "employee": {"id": slot["esuite_id"]},
                "customer": {"id": customer.get("id")},
                "branch": {"id": branch_id},
                "date_plan": {"date": epoch_utc_midnight(d)},
            })

        batches = [items[i:i + resolved_batch_size] for i in range(0, len(items), resolved_batch_size)]
        result = {
            "dry_run": dry_run,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "call_plan_type": CALL_PLAN_TYPE,
            "slots": [dict(s) for s in slot_infos],
            "visit_count": len(items),
            "skipped_count": len(skipped),
            "invalid_count": len(invalid_rows),
            "customer_not_mapped_to_salesman_count": len(not_mapped_codes),
            "batch_size": resolved_batch_size,
            "batch_count": len(batches),
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

    def _resolve_slot(self, odoo_slot: str) -> dict:
        mapping = SLOTS_BY_NAME.get(odoo_slot)
        if not mapping:
            raise ValidationError(
                f"Slot '{odoo_slot}' tidak ada di tabel mapping (app/core/salesman_slots.py)",
                details={"odoo_slot": odoo_slot},
            )

        # Odoo: nama slot harus PERSIS 1 res.users (ilike lalu disaring exact).
        users = [u for u in self.odoo.get_salespersons(name=odoo_slot) if u.get("name") == odoo_slot]
        if len(users) != 1:
            raise ValidationError(
                f"Slot Odoo '{odoo_slot}' ditemukan {len(users)} res.users (harus tepat 1) -- "
                "cek nama Salesperson di Odoo atau tabel mapping",
                details={"odoo_slot": odoo_slot, "found": users},
            )

        # eSuite: employee_id -> id internal + branch.
        records = (self.esuite.pull_by_param("employee", "employee_id", mapping["esuite_employee_id"]).get("data") or [])
        if not records:
            raise ValidationError(
                f"Akun eSuite employee_id '{mapping['esuite_employee_id']}' (slot '{odoo_slot}') tidak ditemukan",
                details={"odoo_slot": odoo_slot, "esuite_employee_id": mapping["esuite_employee_id"]},
            )
        emp = records[0]
        branch_ids = [b.get("id") for b in (emp.get("branches") or []) if b.get("id")]
        if not branch_ids:
            raise ValidationError(
                f"Akun eSuite '{emp.get('name')}' (slot '{odoo_slot}') tidak punya branch",
                details={"odoo_slot": odoo_slot, "esuite_employee_id": mapping["esuite_employee_id"]},
            )

        warnings = []
        if emp.get("username") and emp.get("username") != mapping["esuite_username"]:
            warnings.append(
                f"username eSuite '{emp.get('username')}' beda dgn tabel mapping '{mapping['esuite_username']}'"
            )
        if emp.get("status") and emp.get("status") != "active":
            warnings.append(f"status akun eSuite '{emp.get('status')}'")

        return {
            "odoo_slot": odoo_slot,
            "odoo_user_id": users[0]["id"],
            "person": mapping["person"],
            "esuite_employee_id": mapping["esuite_employee_id"],
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
