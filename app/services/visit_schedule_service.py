"""
Jadwal kunjungan sales dari visit cycle Odoo -- 12 Oktober 2026.

Dipakai GET /odoo/visit-today: daftar outlet yang dikunjungi sales pada 1
tanggal (6 Nov 2026: juga minggu ini / bulan ini / rentang tanggal),
supaya stok outlet cukup diisi utk outlet itu saja (keputusan user
12 Oktober, menggantikan rollout semua outlet). Read-only, tidak menulis ke
Odoo / eSuite. Logic hitung minggu disiapkan agar bisa dipakai ulang utk
call plan nanti.

Aturan minggu (Decision Log visit cycle, 3 November 2026 -- aturan Nesa,
MENGGANTI aturan Senin-Minggu 5 Okt & "minggu ke-5 dilewati" 7 Okt):
- Minggu = Minggu s/d Sabtu, dihitung DI DALAM bulan tanggal itu sendiri
  (tgl 1 selalu minggu ke-1, walau cuma 1-2 hari).
  Contoh Nov 2026: 1-7 = Mg-1, 8-14 = Mg-2, 15-21 = Mg-3, 22-28 = Mg-4,
  29-30 = Mg-1.
- Baris ke-5 = minggu ke-1 (ganjil), baris ke-6 = minggu ke-2 (genap).
- M1 = tiap minggu; M2C13 = minggu 1 & 3 (ganjil); M2C24 = minggu 2 & 4
  (genap); M4C1/M4C2/M4C3/M4C4 = minggu 1/2/3/4 (M4C1 & M4C4 BARU 4 Nov,
  handoff Odoo DL-093). Visit day Senin-Sabtu (Sabtu BARU 4 Nov).
- Bridge membaca LABEL selection Odoo, bukan key (key [M4C1] berlabel M4C2,
  [MI C13] berlabel M2C13, dst. -- lihat `_normalize`).
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
    "M4C1": ({1}, "F1"),  # 4 Nov 2026 (handoff Odoo DL-093)
    "M4C2": ({2}, "F1"),
    "M4C3": ({3}, "F1"),
    "M4C4": ({4}, "F1"),  # 4 Nov 2026 (handoff Odoo DL-093)
}

# Nama hari -> weekday Python (0 = Senin). Data Odoo campur huruf besar/kecil.
DAY_NAMES = {
    "SENIN": 0, "SELASA": 1, "RABU": 2, "KAMIS": 3, "JUMAT": 4,
    "SABTU": 5, "MINGGU": 6,
    "MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3, "FRIDAY": 4,
    "SATURDAY": 5, "SUNDAY": 6,
}
DAY_LABELS = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
WORKING_DAYS = {0, 1, 2, 3, 4, 5}  # definisi visit day: Senin-Sabtu (Sabtu sejak 4 Nov 2026)


def week_of_month(d: date) -> tuple[int, int, int]:
    """
    Return (tahun, bulan, minggu_ke 1-4) utk tanggal d -- aturan Nesa 3 Nov 2026.
    Baris kalender Minggu-Sabtu di dalam bulan d; baris 5 -> 1, baris 6 -> 2.
    """
    first = d.replace(day=1)
    offset = (first.weekday() + 1) % 7  # hari ke-berapa tgl 1 (Minggu=0 .. Sabtu=6)
    row = (d.day - 1 + offset) // 7 + 1  # baris kalender 1..6
    return d.year, d.month, (row - 1) % 4 + 1


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

    def get_visits_between(
        self,
        date_from: date,
        date_to: date,
        salesperson_ids: list[int] | None = None,
        company_id: int | None = None,
    ) -> dict:
        """
        6 November 2026 -- versi RENTANG dari get_visits_on (minggu ini /
        bulan ini / date_from-date_to). Aturan minggu & validasi SAMA; data
        Odoo dibaca 1x lalu dihitung per tanggal. Read-only.
        """
        selections = {f: self._selection_map(f) for f in VISIT_FIELDS}
        partners = self.odoo.get_customers_with_visit_schedule(
            VISIT_FIELDS, salesperson_ids=salesperson_ids, company_id=company_id
        )

        # Parse sekali: (row, weekday kunjungan, set minggu / None = tiap minggu)
        schedules, invalid_rows = [], []
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
            schedules.append((row, DAY_NAMES[day], CYCLE_RULES[cycle][0]))

        days, unique_codes = [], {}  # dict dipakai sbg "ordered set" kode outlet
        per_salesperson: dict[str, int] = {}
        d = date_from
        while d <= date_to:
            year, month, week_no = week_of_month(d)
            outlets = [
                row for row, weekday, weeks in schedules
                if weekday == d.weekday() and (weeks is None or week_no in weeks)
            ]
            for o in outlets:
                unique_codes[o["customer_external_code"]] = True
                key = o["salesperson"] or "(tanpa salesperson)"
                per_salesperson[key] = per_salesperson.get(key, 0) + 1
            days.append({
                "visit_date": d.isoformat(),
                "visit_day": DAY_LABELS[d.weekday()],
                "week_of_month": week_no,
                "week_month": f"{year}-{month:02d}",
                "outlet_count": len(outlets),
                "external_codes_csv": ",".join(o["customer_external_code"] for o in outlets),
                "outlets": outlets,
            })
            d += timedelta(days=1)

        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "filters": {"salesperson_ids": salesperson_ids, "company_id": company_id},
            "customers_with_visit_data": len(partners),
            "valid_schedule_count": len(schedules),
            "total_visits": sum(x["outlet_count"] for x in days),
            "unique_outlet_count": len(unique_codes),
            # per_salesperson = jumlah KUNJUNGAN (bukan outlet unik) dalam rentang
            "per_salesperson": dict(sorted(per_salesperson.items())),
            # Outlet unik dalam rentang -- siap ke POST /api/sync/outlet-stock?external_codes=...
            "external_codes_csv": ",".join(unique_codes),
            "days": days,
            "invalid_count": len(invalid_rows),
            "invalid_rows": invalid_rows,
        }

    @staticmethod
    def _invalid_reason(cycle: str, day: str, freq: str) -> str | None:
        missing = [n for n, v in (("cycle", cycle), ("day", day), ("frequency", freq)) if not v]
        if missing:
            return f"data visit terisi sebagian (kosong: {', '.join(missing)})"
        if cycle not in CYCLE_RULES:
            return f"kode cycle '{cycle}' di luar daftar ({', '.join(CYCLE_RULES)})"
        if day not in DAY_NAMES:
            return f"visit day '{day}' tidak dikenali"
        if DAY_NAMES[day] not in WORKING_DAYS:
            return f"visit day '{day}' di luar Senin-Sabtu"
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
