"""
Jadwal kunjungan sales dari visit cycle Odoo -- 12 Oktober 2026.

Dipakai GET /odoo/visit-today: daftar outlet yang dikunjungi sales pada 1
tanggal, supaya stok outlet cukup diisi utk outlet itu saja (keputusan user
12 Oktober, menggantikan rollout semua outlet). Read-only, tidak menulis ke
Odoo / eSuite. Logic hitung minggu disiapkan agar bisa dipakai ulang utk
call plan nanti.

Aturan (Decision Log visit cycle, 5 & 7 Oktober 2026):
- Minggu = minggu kalender Senin-Minggu. Minggu yang memuat tanggal 1 =
  minggu ke-1 bulan itu (boleh mulai di akhir bulan sebelumnya).
  Contoh: Senin 28 Sep 2026 = minggu ke-1 Oktober; Senin 26 Okt 2026 =
  minggu ke-1 November.
- M1 = tiap minggu (termasuk minggu ke-5); M2C13 = minggu 1 & 3;
  M2C24 = minggu 2 & 4; M4C2 = minggu 2; M4C3 = minggu 3. Minggu ke-5
  dilewati utk M2/M4.
- Pasangan frequency wajib: M1-F4, M2Cxx-F2, M4Cx-F1. Baris yang melanggar /
  terisi sebagian / kode di luar daftar = TIDAK VALID: dilewati + dilaporkan
  (diperbaiki di Odoo, bukan ditebak bridge).
"""
import re
from datetime import date, datetime, timedelta, timezone

from app.clients.odoo_client import OdooClient
from app.core.exceptions import NotFoundError
from app.core.salesman_slots import SLOTS_BY_NAME

CUSTOMER_EXTERNAL_CODE_PREFIX = "ODOO-PARTNER-"
VISIT_MODEL = "res.partner"
VISIT_CYCLE_FIELD = "x_studio_visit_cycle"
VISIT_DAY_FIELD = "x_studio_visit_day"
VISIT_FREQUENCY_FIELD = "x_studio_visit_frequency"
VISIT_FIELDS = [VISIT_CYCLE_FIELD, VISIT_DAY_FIELD, VISIT_FREQUENCY_FIELD]

# "Hari ini" dihitung dalam WITA (UTC+8) -- asumsi user 7 Oktober (Bali).
# Pakai offset tetap, bukan zoneinfo, supaya tidak bergantung tzdata di container.
WITA = timezone(timedelta(hours=8))

# Kode cycle -> (minggu kunjungan, frequency pasangannya). None = tiap minggu.
CYCLE_RULES = {
    "M1": (None, "F4"),
    "M2C13": ({1, 3}, "F2"),
    "M2C24": ({2, 4}, "F2"),
    "M4C2": ({2}, "F1"),
    "M4C3": ({3}, "F1"),
}

# Nama hari -> weekday Python (0 = Senin). Data Odoo campur huruf besar/kecil.
DAY_NAMES = {
    "SENIN": 0, "SELASA": 1, "RABU": 2, "KAMIS": 3, "JUMAT": 4,
    "SABTU": 5, "MINGGU": 6,
    "MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3, "FRIDAY": 4,
    "SATURDAY": 5, "SUNDAY": 6,
}
DAY_LABELS = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
WORKING_DAYS = {0, 1, 2, 3, 4}  # definisi visit day: Senin-Jumat


def week_of_month(d: date) -> tuple[int, int, int]:
    """
    Return (tahun, bulan, minggu_ke) utk tanggal d sesuai aturan sales.
    Minggu milik bulan dari hari Minggu-nya: minggu yang memuat tgl 1
    selalu berakhir (hari Minggu) di bulan baru, minggu lain Senin & Minggu-nya
    di bulan yang sama.
    """
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    first = date(sunday.year, sunday.month, 1)
    week1_monday = first - timedelta(days=first.weekday())
    return sunday.year, sunday.month, (monday - week1_monday).days // 7 + 1


def _normalize(value, selection: dict) -> str:
    """Nilai field Odoo -> teks huruf besar tanpa spasi/tanda. Selection key -> label."""
    if value in (False, None):
        return ""
    if isinstance(value, list):  # many2one [id, name]
        value = value[1]
    text = selection.get(value, value) if selection else value
    return re.sub(r"[^A-Z0-9]", "", str(text).upper())


class VisitScheduleService:
    def __init__(self):
        self.odoo = OdooClient()

    def _selection_map(self, field: str) -> dict:
        info = self.odoo.get_field_info(VISIT_MODEL, field)
        if not info:
            raise NotFoundError(
                f"Field '{field}' tidak ditemukan di model '{VISIT_MODEL}' (atau akun API tidak punya akses)",
                details={"model": VISIT_MODEL, "field": field},
            )
        return {key: label for key, label in (info.get("selection") or [])}

    def get_visits_on(
        self,
        visit_date: date | None = None,
        salesperson_ids: list[int] | None = None,
        company_id: int | None = None,
    ) -> dict:
        visit_date = visit_date or datetime.now(WITA).date()
        year, month, week_no = week_of_month(visit_date)
        weekday = visit_date.weekday()

        selections = {f: self._selection_map(f) for f in VISIT_FIELDS}
        partners = self.odoo.get_customers_with_visit_schedule(
            VISIT_FIELDS, salesperson_ids=salesperson_ids, company_id=company_id
        )

        outlets, invalid_rows = [], []
        valid_count = 0
        for p in partners:
            cycle = _normalize(p.get(VISIT_CYCLE_FIELD), selections[VISIT_CYCLE_FIELD])
            day = _normalize(p.get(VISIT_DAY_FIELD), selections[VISIT_DAY_FIELD])
            freq = _normalize(p.get(VISIT_FREQUENCY_FIELD), selections[VISIT_FREQUENCY_FIELD])
            row = {
                "odoo_partner_id": p["id"],
                "customer_external_code": f"{CUSTOMER_EXTERNAL_CODE_PREFIX}{p['id']}",
                "customer_name": p.get("name"),
                "salesperson": p["user_id"][1] if p.get("user_id") else None,
                "company": p["company_id"][1] if p.get("company_id") else None,
                "visit_cycle": cycle or None,
                "visit_day": day or None,
                "visit_frequency": freq or None,
            }

            reason = self._invalid_reason(cycle, day, freq)
            if reason:
                invalid_rows.append({**row, "reason": reason})
                continue
            valid_count += 1

            weeks, _ = CYCLE_RULES[cycle]
            if DAY_NAMES[day] == weekday and (weeks is None or week_no in weeks):
                outlets.append(row)

        codes = [o["customer_external_code"] for o in outlets]
        per_salesperson: dict[str, int] = {}
        for o in outlets:
            key = o["salesperson"] or "(tanpa salesperson)"
            per_salesperson[key] = per_salesperson.get(key, 0) + 1

        return {
            "visit_date": visit_date.isoformat(),
            "visit_day": DAY_LABELS[weekday],
            "week_of_month": week_no,
            "week_month": f"{year}-{month:02d}",
            "filters": {"salesperson_ids": salesperson_ids, "company_id": company_id},
            "customers_with_visit_data": len(partners),
            "valid_schedule_count": valid_count,
            "outlet_count": len(outlets),
            "per_salesperson": dict(sorted(per_salesperson.items())),
            # Siap copy-paste ke POST /api/sync/outlet-stock?external_codes=...
            "external_codes_csv": ",".join(codes),
            "outlets": outlets,
            "invalid_count": len(invalid_rows),
            "invalid_rows": invalid_rows,
        }

    @staticmethod
    def _invalid_reason(cycle: str, day: str, freq: str) -> str | None:
        missing = [n for n, v in (("cycle", cycle), ("day", day), ("frequency", freq)) if not v]
        if missing:
            return f"data visit terisi sebagian (kosong: {', '.join(missing)})"
        if cycle not in CYCLE_RULES:
            return f"kode cycle '{cycle}' di luar daftar (M1, M2C13, M2C24, M4C2, M4C3)"
        if day not in DAY_NAMES:
            return f"visit day '{day}' tidak dikenali"
        if DAY_NAMES[day] not in WORKING_DAYS:
            return f"visit day '{day}' di luar Senin-Jumat"
        expected_freq = CYCLE_RULES[cycle][1]
        if freq != expected_freq:
            return f"pasangan tidak cocok: {cycle} harus {expected_freq}, tercatat {freq}"
        return None

    def get_outlet_schedule(self, partner_ids: list[int], date_from: date | None = None, weeks: int = 4) -> dict:
        """
        16 Oktober 2026 -- jadwal kunjungan OUTLET TERTENTU (by id partner)
        dalam N minggu ke depan, dihitung dari visit cycle Odoo (aturan sama
        get_visits_on). Read-only. Sales = Salesperson Odoo (`user_id`) +
        akun eDot dari tabel app/core/salesman_slots.py (kalau slotnya ada).
        """
        date_from = date_from or datetime.now(WITA).date()
        date_to = date_from + timedelta(days=weeks * 7 - 1)
        selections = {f: self._selection_map(f) for f in VISIT_FIELDS}
        partners = self.odoo.get_customers_with_visit_schedule(VISIT_FIELDS, partner_ids=partner_ids)

        outlets = []
        for p in partners:
            cycle = _normalize(p.get(VISIT_CYCLE_FIELD), selections[VISIT_CYCLE_FIELD])
            day = _normalize(p.get(VISIT_DAY_FIELD), selections[VISIT_DAY_FIELD])
            freq = _normalize(p.get(VISIT_FREQUENCY_FIELD), selections[VISIT_FREQUENCY_FIELD])
            salesperson = p["user_id"][1] if p.get("user_id") else None
            slot = SLOTS_BY_NAME.get(salesperson) if salesperson else None
            row = {
                "customer_external_code": f"{CUSTOMER_EXTERNAL_CODE_PREFIX}{p['id']}",
                "customer_name": p.get("name"),
                "company": p["company_id"][1] if p.get("company_id") else None,
                "salesperson": salesperson,
                # None = slot belum ada di tabel mapping -> tidak dikirim ke eDot
                "esuite_username": slot["esuite_username"] if slot else None,
                "sales_person_name": slot["person"] if slot else None,
                "visit_cycle": cycle or None,
                "visit_day": day or None,
                "visit_frequency": freq or None,
            }
            reason = self._invalid_reason(cycle, day, freq)
            if reason:
                outlets.append({**row, "valid": False, "reason": reason, "next_visit": None, "visit_dates": []})
                continue

            weeks_rule, _ = CYCLE_RULES[cycle]
            dates = []
            d = date_from
            while d <= date_to:
                if d.weekday() == DAY_NAMES[day] and (weeks_rule is None or week_of_month(d)[2] in weeks_rule):
                    y, m, w = week_of_month(d)
                    dates.append({"date": d.isoformat(), "day": DAY_LABELS[d.weekday()], "week": f"minggu ke-{w} {y}-{m:02d}"})
                d += timedelta(days=1)
            outlets.append({
                **row,
                "valid": True,
                "next_visit": dates[0]["date"] if dates else None,
                "visit_dates": dates,
            })

        found = {p["id"] for p in partners}
        not_found = [
            {"customer_external_code": f"{CUSTOMER_EXTERNAL_CODE_PREFIX}{i}",
             "reason": "bukan customer aktif / tidak punya data visit (mis. tim FS)"}
            for i in partner_ids if i not in found
        ]
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "outlet_count": len(outlets),
            "outlets": outlets,
            "not_found": not_found,
            "note": "Jadwal hitungan dari visit cycle Odoo, BUKAN data call plan yang sudah masuk eSuite.",
        }
