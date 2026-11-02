"""
Export call plan HITUNGAN (visit cycle Odoo) ke Excel utk direview sales
manager (Nesa) -- 2 November 2026.

Dipakai GET /api/odoo/visit-schedule/export. Read-only: tidak menulis ke
Odoo / eSuite, tidak cek eSuite (customer ada/branch) -- yang direview Nesa
adalah jadwalnya, bukan status sinkron.

Aturan tanggal SAMA PERSIS dgn POST /sync/call-plan: `visit_dates()`
(call_plan_sync_service.py) + aturan minggu `week_of_month()`
(visit_schedule_service.py, Decision Log visit cycle 5 & 7 Okt 2026).

Periode "bulan" = Senin minggu ke-1 s/d Minggu minggu terakhir bulan itu
menurut aturan minggu sales (bukan tgl 1 s/d akhir bulan). Contoh Nov 2026:
26 Okt - 29 Nov (30 Nov = minggu ke-1 Desember).

Isi workbook:
- Ringkasan      : per sales (jumlah outlet, kunjungan, invalid) + rekap
                   review (rumus, otomatis dari sheet sales).
- Beban Harian   : jumlah kunjungan per tanggal per sales.
- 1 sheet/sales  : 1 baris per outlet, kolom per minggu berisi tanggal
                   kunjungan; kolom KUNING diisi Nesa (Review OK/Revisi,
                   usulan cycle/hari, catatan).
- Perlu Dicek    : visit cycle tidak valid + (mode semua sales) customer
                   ber-visit yang Salesperson-nya tidak ada di tabel slot.
- Detail Kunjungan: 1 baris per kunjungan (= calon call plan + kodenya).
"""
from datetime import date, datetime, timedelta
from enum import Enum
from io import BytesIO

from app.clients.odoo_client import OdooClient
from app.core.exceptions import AppError, ValidationError
from app.core.salesman_slots import SALESMAN_SLOTS, SLOTS_BY_NAME
from app.services.call_plan_sync_service import DELIVERY_ROUTE_FIELD, EXTERNAL_CODE_PREFIX, visit_dates
from app.services.visit_schedule_service import (
    CYCLE_RULES,
    DAY_LABELS,
    DAY_NAMES,
    VISIT_CYCLE_FIELD,
    VISIT_DAY_FIELD,
    VISIT_FIELDS,
    VISIT_FREQUENCY_FIELD,
    WITA,
    VisitScheduleService,
    _normalize,
    week_of_month,
)

MAX_EXPORT_DAYS = 62  # pengaman (2 bulan); 1 bulan aturan sales maks 35 hari
MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
REVIEW_OPTIONS = ["OK", "Revisi"]
WEEKDAY_LABELS = DAY_LABELS[:5]  # visit day Senin-Jumat


class ExportPeriode(str, Enum):
    """Pilihan rentang (select box Swagger). Dihitung saat request (WITA)."""
    bulan_ini = "bulan_ini"
    bulan_depan = "bulan_depan"
    minggu_ini = "minggu_ini"      # Senin-Minggu minggu berjalan
    minggu_depan = "minggu_depan"


def month_range(year: int, month: int) -> tuple[date, date]:
    """Senin minggu ke-1 s/d Minggu minggu terakhir bulan itu (aturan minggu sales)."""
    first = date(year, month, 1)
    start = first - timedelta(days=first.weekday())
    last = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
    end = last - timedelta(days=(last.weekday() + 1) % 7)  # mundur ke hari Minggu
    return start, end


def resolve_period(periode: ExportPeriode, date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """date_from diisi = manual (periode diabaikan)."""
    if date_from:
        return date_from, date_to or date_from
    today = datetime.now(WITA).date()
    monday = today - timedelta(days=today.weekday())
    if periode == ExportPeriode.minggu_ini:
        return monday, monday + timedelta(days=6)
    if periode == ExportPeriode.minggu_depan:
        return monday + timedelta(days=7), monday + timedelta(days=13)
    year, month, _ = week_of_month(today)  # bulan menurut aturan minggu sales
    if periode == ExportPeriode.bulan_depan:
        year, month = year + month // 12, month % 12 + 1
    return month_range(year, month)


def _fmt(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def _sheet_title(slot: dict) -> str:
    # "[SALES] BAL GT02" + "Ali (GT)" -> "GT02 Ali" (maks 31 char, tanpa []:*?/\)
    short = slot["odoo_slot"].replace("[SALES]", "").replace("BAL", "").strip()
    title = f"{short} {slot['person'].split(' ')[0]}"
    return "".join(c for c in title if c not in "[]:*?/\\")[:31]


class VisitScheduleExportService:
    def __init__(self):
        self.odoo = OdooClient()

    def build(self, date_from: date, date_to: date, slots: list[str] | None = None) -> tuple[bytes, str]:
        """Return (isi file .xlsx, nama file)."""
        if date_to < date_from:
            raise ValidationError(
                "date_to tidak boleh sebelum date_from",
                details={"date_from": str(date_from), "date_to": str(date_to)},
            )
        days = (date_to - date_from).days + 1
        if days > MAX_EXPORT_DAYS:
            raise ValidationError(
                f"Rentang maksimal {MAX_EXPORT_DAYS} hari (diminta {days} hari)",
                details={"date_from": str(date_from), "date_to": str(date_to)},
            )

        slot_names = list(dict.fromkeys(slots)) if slots else [s["odoo_slot"] for s in SALESMAN_SLOTS]
        selections = {f: VisitScheduleService()._selection_map(f) for f in VISIT_FIELDS}
        partners = self.odoo.get_customers_with_visit_schedule(VISIT_FIELDS)
        routes = self._delivery_routes()

        outlets_by_slot: dict[str, list[dict]] = {name: [] for name in slot_names}
        problems: list[dict] = []
        for p in partners:
            salesperson = p["user_id"][1] if p.get("user_id") else None
            row = {
                "partner_id": p["id"],
                "name": p.get("name") or "",
                "route": routes.get(p["id"], ""),
                "cycle": _normalize(p.get(VISIT_CYCLE_FIELD), selections[VISIT_CYCLE_FIELD]),
                "day": _normalize(p.get(VISIT_DAY_FIELD), selections[VISIT_DAY_FIELD]),
                "freq": _normalize(p.get(VISIT_FREQUENCY_FIELD), selections[VISIT_FREQUENCY_FIELD]),
                "salesperson": salesperson or "(tanpa Salesperson)",
            }
            if salesperson not in outlets_by_slot:
                # Mode semua sales: laporkan outlet ber-visit di luar tabel slot.
                if not slots:
                    problems.append({**row, "reason": "Salesperson tidak ada di tabel slot sales (app/core/salesman_slots.py)"})
                continue
            reason = VisitScheduleService._invalid_reason(row["cycle"], row["day"], row["freq"])
            if reason:
                problems.append({**row, "reason": reason})
                continue
            dates = visit_dates(row["cycle"], row["day"], date_from, date_to)
            if dates:  # outlet tanpa kunjungan di periode ini (mis. M4C2 di minggu lain) tidak ditampilkan
                outlets_by_slot[salesperson].append({**row, "dates": dates})

        for rows in outlets_by_slot.values():
            rows.sort(key=lambda r: (DAY_NAMES[r["day"]], r["route"], r["name"]))

        content = self._workbook(date_from, date_to, slot_names, outlets_by_slot, problems)
        filename = f"callplan_review_{date_from:%Y%m%d}-{date_to:%Y%m%d}.xlsx"
        return content, filename

    def _delivery_routes(self) -> dict[int, str]:
        """id partner -> rute (`x_studio_delivery_route`), info saja; gagal = kosong."""
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

    # ------------------------------------------------------------------ Excel
    def _workbook(self, date_from, date_to, slot_names, outlets_by_slot, problems) -> bytes:
        # Import di sini: bridge tetap bisa start walau openpyxl belum terpasang.
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
            from openpyxl.worksheet.datavalidation import DataValidation
        except ImportError:
            raise AppError(
                code="DEPENDENCY_MISSING",
                message="Library openpyxl belum terpasang di environment bridge -- jalankan: pip install openpyxl",
                status_code=500,
            )

        bold = Font(bold=True)
        title_font = Font(bold=True, size=14)
        head_fill = PatternFill("solid", fgColor="1F4E78")
        head_font = Font(bold=True, color="FFFFFF")
        yellow = PatternFill("solid", fgColor="FFF2CC")
        grey = PatternFill("solid", fgColor="F2F2F2")

        def header(ws, row, labels, widths=None):
            for i, label in enumerate(labels, start=1):
                c = ws.cell(row=row, column=i, value=label)
                c.fill, c.font, c.alignment = head_fill, head_font, Alignment(wrap_text=True, vertical="center")
                if widths:
                    ws.column_dimensions[get_column_letter(i)].width = widths[i - 1]

        def dropdown(ws, options, cell_range):
            dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(cell_range)

        # Minggu-minggu dalam periode (Senin), label "Mg-2 Nov (2 Nov)".
        weeks, d = [], date_from - timedelta(days=date_from.weekday())
        while d <= date_to:
            _, m, w = week_of_month(d)
            weeks.append((d, f"Mg-{w} {MONTHS[m - 1]}\n({d.day}/{d.month})"))
            d += timedelta(days=7)
        period_text = f"{_fmt(date_from)} s/d {_fmt(date_to)}"
        generated = datetime.now(WITA).strftime("%d/%m/%Y %H:%M WITA")

        wb = Workbook()
        ws_sum = wb.active
        ws_sum.title = "Ringkasan"

        # ---- 1 sheet per sales
        sheet_refs = {}  # slot -> (judul sheet, kolom review, baris akhir)
        all_visits = []
        for name in slot_names:
            slot = SLOTS_BY_NAME.get(name) or {"odoo_slot": name, "person": name, "esuite_username": "-", "esuite_employee_id": "-"}
            rows = outlets_by_slot[name]
            ws = wb.create_sheet(_sheet_title(slot))
            ws["A1"] = f"Call Plan {slot['person']} -- {name} -- Akun eDot {slot['esuite_username']}"
            ws["A1"].font = title_font
            ws["A2"] = (f"Periode {period_text} | {len(rows)} outlet, {sum(len(r['dates']) for r in rows)} kunjungan | "
                        "Kolom KUNING diisi reviewer, kolom lain jangan diubah")
            labels = ["No", "Hari", "Outlet", "Partner ID", "Rute", "Cycle", "Freq"] + [w[1] for w in weeks] + [
                "Jml", "Review (OK/Revisi)", "Usulan Cycle", "Usulan Hari", "Catatan"]
            widths = [5, 9, 38, 10, 18, 9, 6] + [11] * len(weeks) + [6, 12, 12, 12, 40]
            header(ws, 4, labels, widths)
            ws.row_dimensions[4].height = 32
            first_week_col = 8
            review_col = first_week_col + len(weeks) + 1
            for i, r in enumerate(rows, start=1):
                excel_row = 4 + i
                by_week = {dt - timedelta(days=dt.weekday()): dt for dt in r["dates"]}
                values = [i, DAY_LABELS[DAY_NAMES[r["day"]]], r["name"], r["partner_id"], r["route"], r["cycle"], r["freq"]]
                values += [f"{by_week[w[0]].day}/{by_week[w[0]].month}" if w[0] in by_week else None for w in weeks]
                values += [len(r["dates"])]
                for col, v in enumerate(values, start=1):
                    ws.cell(row=excel_row, column=col, value=v)
                for col in range(review_col, review_col + 4):
                    ws.cell(row=excel_row, column=col).fill = yellow
                for dt in r["dates"]:
                    all_visits.append((dt, slot, r))
            last_row = 4 + max(len(rows), 1)
            if rows:
                L = get_column_letter
                dropdown(ws, REVIEW_OPTIONS, f"{L(review_col)}5:{L(review_col)}{last_row}")
                dropdown(ws, list(CYCLE_RULES), f"{L(review_col + 1)}5:{L(review_col + 1)}{last_row}")
                dropdown(ws, WEEKDAY_LABELS, f"{L(review_col + 2)}5:{L(review_col + 2)}{last_row}")
                ws.auto_filter.ref = f"A4:{L(review_col + 3)}{last_row}"
            ws.freeze_panes = "D5"
            sheet_refs[name] = (ws.title, get_column_letter(review_col), last_row, slot, rows)

        # ---- Ringkasan
        ws_sum["A1"] = "Review Call Plan Sales"
        ws_sum["A1"].font = title_font
        info = [
            f"Periode: {period_text}",
            f"Dibuat: {generated} | Sumber: visit cycle Odoo (jadwal HITUNGAN bridge, BUKAN call plan yang sudah masuk eDot)",
            "Aturan minggu: minggu (Senin-Minggu) yang memuat tgl 1 = minggu ke-1. M1 tiap minggu; M2C13 minggu 1 & 3; "
            "M2C24 minggu 2 & 4; M4C2 minggu 2; M4C3 minggu 3; minggu ke-5 tanpa kunjungan M2/M4.",
            "Cara review: buka sheet tiap sales -> isi kolom KUNING per outlet (Review OK / Revisi; kalau Revisi isi usulan "
            "cycle / hari / catatan). Cek juga sheet 'Perlu Dicek'. Tabel di bawah terisi otomatis.",
        ]
        for i, text in enumerate(info, start=2):
            ws_sum.cell(row=i, column=1, value=text).alignment = Alignment(wrap_text=False)
        problems_by_slot: dict[str, int] = {}
        for pr in problems:
            problems_by_slot[pr["salesperson"]] = problems_by_slot.get(pr["salesperson"], 0) + 1
        header(ws_sum, 7, ["Slot Odoo", "Sales", "Akun eDot", "Outlet terjadwal", "Total kunjungan",
                           "Perlu dicek", "Review OK", "Review Revisi", "Belum direview"],
               [20, 16, 13, 10, 10, 10, 10, 10, 10])
        ws_sum.row_dimensions[7].height = 32
        r_i = 8
        for name in slot_names:
            title, col, last_row, slot, rows = sheet_refs[name]
            rng = f"'{title}'!${col}$5:${col}${last_row}"
            values = [name, slot["person"], slot["esuite_username"], len(rows), sum(len(r["dates"]) for r in rows),
                      problems_by_slot.get(name, 0), f'=COUNTIF({rng},"OK")', f'=COUNTIF({rng},"Revisi")',
                      f"=D{r_i}-G{r_i}-H{r_i}"]
            for c, v in enumerate(values, start=1):
                ws_sum.cell(row=r_i, column=c, value=v)
            r_i += 1
        ws_sum.cell(row=r_i, column=1, value="TOTAL").font = bold
        for c in range(4, 10):
            L = get_column_letter(c)
            ws_sum.cell(row=r_i, column=c, value=f"=SUM({L}8:{L}{r_i - 1})").font = bold
        outside = len([p for p in problems if p["salesperson"] not in sheet_refs])
        if outside:
            ws_sum.cell(row=r_i + 2, column=1,
                        value=f"Info: {outside} outlet ber-visit milik Salesperson di luar tabel slot -> lihat sheet 'Perlu Dicek'.")
        r_w = r_i + 4
        ws_sum.cell(row=r_w, column=1, value="Minggu dalam periode").font = bold
        for i, (monday, label) in enumerate(weeks, start=1):
            ws_sum.cell(row=r_w + i, column=1, value=label.replace("\n", " "))
            ws_sum.cell(row=r_w + i, column=2, value=f"{_fmt(monday)} - {_fmt(monday + timedelta(days=6))}")

        # ---- Beban Harian
        ws_day = wb.create_sheet("Beban Harian", 1)
        ws_day["A1"] = "Jumlah kunjungan per hari"
        ws_day["A1"].font = title_font
        persons = [sheet_refs[n][3]["person"] for n in slot_names]
        header(ws_day, 3, ["Tanggal", "Hari", "Minggu"] + persons + ["Total"],
               [14, 9, 10] + [12] * len(persons) + [8])
        counts: dict[tuple[date, str], int] = {}
        for dt, slot, _ in all_visits:
            counts[(dt, slot["odoo_slot"])] = counts.get((dt, slot["odoo_slot"]), 0) + 1
        row_i, d = 4, date_from
        while d <= date_to:
            if d.weekday() < 5:
                _, m, w = week_of_month(d)
                values = [d, DAY_LABELS[d.weekday()], f"Mg-{w} {MONTHS[m - 1]}"]
                values += [counts.get((d, n), 0) for n in slot_names]
                values += [f"=SUM(D{row_i}:{get_column_letter(3 + len(slot_names))}{row_i})"]
                for c, v in enumerate(values, start=1):
                    cell = ws_day.cell(row=row_i, column=c, value=v)
                    if c == 1:
                        cell.number_format = "DD/MM/YYYY"
                if d.weekday() == 0:
                    for c in range(1, len(values) + 1):
                        ws_day.cell(row=row_i, column=c).fill = grey
                row_i += 1
            d += timedelta(days=1)
        ws_day.freeze_panes = "D4"

        # ---- Perlu Dicek
        ws_p = wb.create_sheet("Perlu Dicek")
        ws_p["A1"] = "Perlu dicek di Odoo -- tidak masuk jadwal"
        ws_p["A1"].font = title_font
        header(ws_p, 3, ["Salesperson Odoo", "Outlet", "Partner ID", "Rute", "Cycle", "Hari", "Freq", "Masalah",
                         "Usulan Cycle", "Usulan Hari", "Catatan"],
               [20, 38, 10, 18, 9, 9, 6, 50, 12, 12, 40])
        for i, pr in enumerate(sorted(problems, key=lambda x: (x["salesperson"], x["name"])), start=4):
            values = [pr["salesperson"], pr["name"], pr["partner_id"], pr["route"], pr["cycle"] or None,
                      pr["day"] or None, pr["freq"] or None, pr["reason"]]
            for c, v in enumerate(values, start=1):
                ws_p.cell(row=i, column=c, value=v)
            for c in range(9, 12):
                ws_p.cell(row=i, column=c).fill = yellow
        if problems:
            last = 3 + len(problems)
            dropdown(ws_p, list(CYCLE_RULES), f"I4:I{last}")
            dropdown(ws_p, WEEKDAY_LABELS, f"J4:J{last}")
            ws_p.auto_filter.ref = f"A3:K{last}"
        ws_p.freeze_panes = "C4"

        # ---- Detail Kunjungan
        ws_d = wb.create_sheet("Detail Kunjungan")
        header(ws_d, 1, ["Tanggal", "Hari", "Minggu", "Slot Odoo", "Sales", "Akun eDot", "Outlet", "Partner ID",
                         "Rute", "Cycle", "Freq", "Kode call plan"],
               [12, 9, 10, 18, 14, 12, 38, 10, 18, 8, 6, 28])
        all_visits.sort(key=lambda v: (v[0], v[1]["odoo_slot"], v[2]["route"], v[2]["name"]))
        for i, (dt, slot, r) in enumerate(all_visits, start=2):
            _, m, w = week_of_month(dt)
            values = [dt, DAY_LABELS[dt.weekday()], f"Mg-{w} {MONTHS[m - 1]}", slot["odoo_slot"], slot["person"],
                      slot["esuite_username"], r["name"], r["partner_id"], r["route"], r["cycle"], r["freq"],
                      f"{EXTERNAL_CODE_PREFIX}{r['partner_id']}-{dt:%Y%m%d}"]
            for c, v in enumerate(values, start=1):
                cell = ws_d.cell(row=i, column=c, value=v)
                if c == 1:
                    cell.number_format = "DD/MM/YYYY"
        if all_visits:
            ws_d.auto_filter.ref = f"A1:L{len(all_visits) + 1}"
        ws_d.freeze_panes = "A2"

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()
