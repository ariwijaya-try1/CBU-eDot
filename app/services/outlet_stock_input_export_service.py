"""
Export progress input Product Stock outlet (eWork) per outlet & per sales
-- 9 November 2026 (requirement monitoring management: "sales X input 30
dari 70 SKU").

Dipakai GET /api/outlet-stock/input-progress/export (grup Swagger "Export").
Read-only: tidak menulis ke Odoo / eSuite.

Keputusan user 9 Nov 2026:
- Acuan Y (total SKU) = LIST APP: semua produk di Product Stock outlet
  (warehouse outlet eSuite) = hasil pre-fill bridge + tambahan sales.
- "Sudah input" (rekomendasi Claude, disetujui): per PRODUK (bukan per
  baris), minimal 1 baris memenuhi salah satu:
    * on_hand >= 1, ATAU
    * punya expired (batch.code "EWORK{YYYYMMDD}", bukan "EWORK" polos), ATAU
    * baris dibuat user app (created_by terisi; baris webhook/pre-fill
      created_by kosong).
  Batasan: sales yang mengisi 0 pada baris pre-fill (tanpa expired) TIDAK
  bisa dibedakan dari "belum input" -> terhitung belum.
- Atribusi: "Diinput oleh" = updated_by/created_by eSuite kalau terisi
  (pre-fill yang diupdate sales tercatat "-" oleh eDot) + kolom Salesperson
  Odoo (res.partner.user_id) sbg pegangan.

- 13 Nov 2026 (user): produk DISCONTINUE (= di-archive di Odoo,
  product.product.active False) tidak perlu diinput -> DIKECUALIKAN dari
  Total SKU / Sudah / Belum walau barisnya masih ada di Product Stock
  outlet (sisa pre-fill on_hand 0 sebelum produk di-archive). Variant
  eSuite -> ODOO-PROD-{id} lewat GET /product (variants[] ter-embed).

Rantai data (fakta 7 Okt 2026, outlet_stock_requirement):
stock-matrix.warehouse.id -> GET warehouse.address.id = id CUSTOMER eSuite
-> customer.external_code "ODOO-PARTNER-{id}".
"""
from collections import defaultdict
from datetime import datetime
from io import BytesIO

from app.clients.esuite_client import EsuiteClient
from app.clients.odoo_client import OdooClient
from app.core.exceptions import AppError, ValidationError
from app.services.visit_schedule_service import WITA

CUSTOMER_EXTERNAL_CODE_PREFIX = "ODOO-PARTNER-"
INTERNAL_WAREHOUSE_PREFIX = "ODOO-WH-"
PRODUCT_EXTERNAL_CODE_PREFIX = "ODOO-PROD-"
NO_EXPIRED_BATCH = "EWORK"  # batch tanpa expired (isian app & pre-fill bridge)
PULL_PAGE_SIZE = 200
MAX_PAGES = 500  # pengaman loop paging
# 12 Nov 2026: GET stock-matrix tanpa filter ditolak eSuite (response > 4 MB gRPC) & limit diabaikan
# -> tarik per warehouse outlet pakai query param ini (terbukti live: 07 AM BAKERS CLUB = 3 baris)
STOCK_MATRIX_WAREHOUSE_PARAM = "warehouse_id"
EMPTY_USER_VALUES = {"", "0", "-", "none", "null"}


def _user(value) -> str:
    """created_by/updated_by eSuite -> teks; kosong/0/'-' = tidak tercatat."""
    if isinstance(value, dict):  # jaga-jaga kalau dikirim sbg object
        value = value.get("name") or value.get("username") or value.get("id")
    text = str(value).strip() if value is not None else ""
    return "" if text.lower() in EMPTY_USER_VALUES else text


def _row_created_wita(row: dict) -> datetime | None:
    """Waktu baris stok DIBUAT. 13 Nov 2026: GET stock-matrix mengisi created_at/updated_at baris
    batch baru dgn nilai baris placeholder (ACETAIA Pepito: API 10/10, UI 06/11). Id baris = MongoDB
    ObjectId -> 8 hex pertama = unix detik pembuatan, cocok dgn UI. Fallback ke created_at."""
    row_id = str(row.get("id") or "")
    if len(row_id) == 24:
        try:
            return _to_wita(int(row_id[:8], 16))
        except ValueError:
            pass
    return _to_wita(row.get("created_at"))


def _to_wita(epoch) -> datetime | None:
    """updated_at eSuite = epoch int (detik; kalau > 1e12 dianggap milidetik)."""
    try:
        value = float(epoch)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    if value > 1e12:
        value /= 1000
    return datetime.fromtimestamp(value, WITA)


class OutletStockInputExportService:
    def __init__(self):
        self.esuite = EsuiteClient()
        self.odoo = OdooClient()
        self._employee_labels: dict[str, str] | None = None  # cache login -> nama employee eSuite

    def build(self, external_codes: list[str] | None = None) -> tuple[bytes, str]:
        """Return (isi file .xlsx, nama file)."""
        wanted = {c.strip() for c in external_codes or [] if c.strip()}
        bad = sorted(c for c in wanted if not c.startswith(CUSTOMER_EXTERNAL_CODE_PREFIX))
        if bad:
            raise ValidationError(
                f"external_codes harus format '{CUSTOMER_EXTERNAL_CODE_PREFIX}{{id}}'",
                details={"invalid": bad},
            )

        # 1. customer eSuite (id -> record), hanya yang berasal dari Odoo
        customers = {
            c["id"]: c
            for c in self._pull_all("customers")
            if c.get("id") and str(c.get("external_code") or "").startswith(CUSTOMER_EXTERNAL_CODE_PREFIX)
            and (not wanted or c.get("external_code") in wanted)
        }

        # 2. warehouse outlet -> customer (lewat address.id)
        wh_customer: dict[str, dict] = {}
        for wh in self._pull_all("warehouse"):
            if str(wh.get("external_code") or "").startswith(INTERNAL_WAREHOUSE_PREFIX):
                continue
            customer = customers.get((wh.get("address") or {}).get("id"))
            if wh.get("id") and customer:
                wh_customer[wh["id"]] = customer

        # 3. baris stok outlet -> dikelompokkan per (warehouse, produk)
        products: dict[str, dict[str, dict]] = defaultdict(dict)
        seen_rows = set()
        for row in self._stock_rows_per_warehouse(list(wh_customer)):
            if row.get("id"):
                if row["id"] in seen_rows:
                    continue
                seen_rows.add(row["id"])
            wh_id = (row.get("warehouse") or {}).get("id")
            if wh_id not in wh_customer:
                continue
            pv = row.get("product_variant") or {}
            key = pv.get("id") or pv.get("code") or pv.get("external_code")
            if not key:
                continue
            item = products[wh_id].setdefault(key, {
                "code": pv.get("code") or "",
                "name": pv.get("name") or (row.get("product") or {}).get("name") or "",
                "input": False, "last": None, "by": set(), "row_count": 0,
            })
            item["row_count"] += 1
            if self._is_input(row):
                item["input"] = True
                # 12 Nov 2026 (keputusan user): pakai created_at, bukan updated_at -- updated_at ikut
                # berubah saat push store-stock bridge. Baris placeholder pre-fill (tanpa expired,
                # created_by kosong) yang cuma diubah qty-nya: waktu input tidak diketahui -> kosong.
                when = _row_created_wita(row) if self._is_user_row(row) else None
                if when and (item["last"] is None or when > item["last"]):
                    item["last"] = when
                who = (_user(row.get("updated_by_name")) or _user(row.get("updated_by"))
                       or _user(row.get("created_by_name")) or _user(row.get("created_by")))
                if who:
                    item["by"].add(self._employee_label(who))

        # 3b. 13 Nov 2026 -- produk discontinue (archived di Odoo) tidak dihitung
        archived = self._archived_variant_ids({key for items in products.values() for key in items})

        # 4. Salesperson Odoo per outlet
        partner_ids = [
            int(c["external_code"][len(CUSTOMER_EXTERNAL_CODE_PREFIX):])
            for c in wh_customer.values()
            if c["external_code"][len(CUSTOMER_EXTERNAL_CODE_PREFIX):].isdigit()
        ]
        salespersons = self._salespersons(partner_ids)

        # 5. rekap per outlet (1 customer bisa >1 warehouse -> digabung)
        outlets: dict[str, dict] = {}
        for wh_id, items in products.items():
            c = wh_customer[wh_id]
            code = c["external_code"]
            pid = code[len(CUSTOMER_EXTERNAL_CODE_PREFIX):]
            o = outlets.setdefault(code, {
                "external_code": code,
                "cust_code": c.get("code") or "",
                "name": c.get("name") or "",
                "salesperson": salespersons.get(int(pid), "(tanpa Salesperson)") if pid.isdigit() else "-",
                "items": {},
            })
            for key, item in items.items():
                if key in archived:
                    continue
                prev = o["items"].get(key)
                if prev is None:
                    o["items"][key] = item
                else:  # produk sama di warehouse lain milik customer yang sama
                    prev["input"] = prev["input"] or item["input"]
                    prev["by"] |= item["by"]
                    if item["last"] and (prev["last"] is None or item["last"] > prev["last"]):
                        prev["last"] = item["last"]

        rows = sorted(outlets.values(), key=lambda o: (o["salesperson"], o["name"]))
        for o in rows:
            items = list(o["items"].values())
            o["total"] = len(items)
            o["done"] = sum(1 for i in items if i["input"])
            lasts = [i["last"] for i in items if i["last"]]
            o["last"] = max(lasts) if lasts else None
            o["by"] = sorted({b for i in items for b in i["by"]})

        content = self._workbook(rows, wanted)
        filename = f"progress_input_stok_outlet_{datetime.now(WITA):%Y%m%d_%H%M}.xlsx"
        return content, filename

    def _employee_label(self, login: str) -> str:
        """13 Nov 2026 (permintaan user): login app eWork (mis. "Salesman_3") -> nama employee
        eSuite (mis. "MT02 Winaya"). Dicocokkan ke GET /employee: username, atau bagian email
        sebelum "@" (Salesman_3@yopmail.com). Tidak ketemu / GET gagal -> login apa adanya."""
        if self._employee_labels is None:
            self._employee_labels = {}
            try:
                for emp in self._pull_all("employee"):
                    name = str(emp.get("name") or "").strip()
                    if not name:
                        continue
                    keys = {str(emp.get("username") or "").strip().lower(),
                            str(emp.get("email") or "").split("@")[0].strip().lower()}
                    for key in keys - {""}:
                        self._employee_labels.setdefault(key, name)
            except Exception:  # label saja -- export tetap jalan
                pass
        return self._employee_labels.get(login.strip().lower(), login)

    @staticmethod
    def _is_user_row(row: dict) -> bool:
        """Baris dibuat dari app (punya expired / created_by terisi), bukan placeholder pre-fill."""
        batch_code = str((row.get("batch") or {}).get("code") or "").strip().upper()
        has_expired = bool(batch_code) and batch_code != NO_EXPIRED_BATCH
        return has_expired or bool(_user(row.get("created_by")))

    @staticmethod
    def _is_input(row: dict) -> bool:
        try:
            on_hand = float(row.get("on_hand") or 0)
        except (TypeError, ValueError):
            on_hand = 0
        batch_code = str((row.get("batch") or {}).get("code") or "").strip().upper()
        has_expired = bool(batch_code) and batch_code != NO_EXPIRED_BATCH
        return on_hand >= 1 or has_expired or bool(_user(row.get("created_by")))

    def _archived_variant_ids(self, variant_ids: set[str]) -> set[str]:
        """
        13 Nov 2026 -- id variant eSuite yang produk Odoo-nya di-ARCHIVE
        (active=False = discontinue) atau sudah terhapus dari Odoo.
        GET stock-matrix tidak membawa external_code variant -> dipetakan
        lewat GET /product (variants[].id -> variants[].external_code).
        Variant tanpa external_code ODOO-PROD-* (bukan dari Odoo) tetap dihitung.
        Lookup Odoo gagal -> AppError diteruskan (export tidak diam-diam
        menghitung produk discontinue sbg "Belum").
        """
        if not variant_ids:
            return set()
        product_id_by_variant: dict[str, int] = {}
        for record in self._pull_all("product"):
            for v in record.get("variants") or []:
                code = str(v.get("external_code") or "")
                raw = code[len(PRODUCT_EXTERNAL_CODE_PREFIX):]
                if v.get("id") in variant_ids and code.startswith(PRODUCT_EXTERNAL_CODE_PREFIX) and raw.isdigit():
                    product_id_by_variant[v["id"]] = int(raw)
        if not product_id_by_variant:
            return set()
        status = self.odoo.get_products_sync_status(sorted(set(product_id_by_variant.values())))
        return {
            vid for vid, pid in product_id_by_variant.items()
            if not (status.get(pid) or {}).get("active")
        }

    def _stock_rows_per_warehouse(self, warehouse_ids: list[str]) -> list[dict]:
        """GET stock-matrix?warehouse_id=... per warehouse outlet (1 call per warehouse).
        Baris dgn warehouse.id lain dibuang -- jaga-jaga kalau filter suatu saat diabaikan eSuite."""
        rows = []
        for wh_id in warehouse_ids:
            result = self.esuite.pull_with_params("stock-matrix", {STOCK_MATRIX_WAREHOUSE_PARAM: wh_id})
            rows.extend(
                r for r in result.get("data") or []
                if (r.get("warehouse") or {}).get("id") == wh_id
            )
        return rows

    def _pull_all(self, entity: str, timeout=None) -> list[dict]:
        """GET semua halaman. stock-matrix mengabaikan limit & balas total_page 0 -> berhenti di halaman 1."""
        rows, page = [], 1
        while True:
            result = self.esuite.pull(entity, page=page, limit=PULL_PAGE_SIZE, timeout=timeout)
            batch = result.get("data") or []
            rows.extend(batch)
            total_page = (result.get("meta") or {}).get("total_page") or 0
            if not batch or page >= total_page:
                return rows
            page += 1
            if page > MAX_PAGES:
                raise AppError(
                    code="ESUITE_PAGING_LIMIT",
                    message=f"GET /{entity} melebihi {MAX_PAGES} halaman -- dihentikan",
                    status_code=502,
                )

    def _salespersons(self, partner_ids: list[int]) -> dict[int, str]:
        """id partner -> nama Salesperson Odoo; gagal baca Odoo = kosong (export tetap jalan)."""
        try:
            return self.odoo.get_partner_salespersons(partner_ids)
        except AppError:
            return {}

    # ------------------------------------------------------------------ Excel
    def _workbook(self, outlets: list[dict], wanted: set[str]) -> bytes:
        # Import di sini: bridge tetap bisa start walau openpyxl belum terpasang.
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
        except ImportError:
            raise AppError(
                code="DEPENDENCY_MISSING",
                message="Library openpyxl belum terpasang di environment bridge -- jalankan: pip install openpyxl",
                status_code=500,
            )

        head_fill = PatternFill("solid", fgColor="1F4E78")
        head_font = Font(bold=True, color="FFFFFF")
        red = PatternFill("solid", fgColor="FCE4D6")
        generated = datetime.now(WITA).strftime("%d/%m/%Y %H:%M WITA")

        def sheet(ws, title, labels, widths, data):
            ws["A1"] = title
            ws["A1"].font = Font(bold=True, size=14)
            ws["A2"] = f"Dibuat {generated}" + (f" | filter {len(wanted)} outlet" if wanted else " | semua outlet")
            for i, label in enumerate(labels, start=1):
                c = ws.cell(row=4, column=i, value=label)
                c.fill, c.font, c.alignment = head_fill, head_font, Alignment(wrap_text=True, vertical="center")
                ws.column_dimensions[get_column_letter(i)].width = widths[i - 1]
            for r, values in enumerate(data, start=5):
                for col, v in enumerate(values, start=1):
                    ws.cell(row=r, column=col, value=v)
            ws.freeze_panes = "A5"
            ws.auto_filter.ref = f"A4:{get_column_letter(len(labels))}{max(4, 4 + len(data))}"

        def pct(done, total):
            return round(done * 100 / total, 1) if total else 0

        def fmt(d):
            return d.strftime("%d/%m/%Y %H:%M") if d else "-"

        wb = Workbook()

        # ---- Per Sales
        per_sales = defaultdict(lambda: [0, 0, 0])
        for o in outlets:
            s = per_sales[o["salesperson"]]
            s[0] += 1
            s[1] += o["total"]
            s[2] += o["done"]
        ws = wb.active
        ws.title = "Per Sales"
        sheet(
            ws, "Progress Input Stok Outlet -- per Salesperson Odoo",
            ["Salesperson Odoo", "Jumlah Outlet", "Total SKU", "Sudah Input", "Belum Input", "% Input"],
            [32, 14, 12, 13, 13, 10],
            [[name, v[0], v[1], v[2], v[1] - v[2], pct(v[2], v[1])] for name, v in sorted(per_sales.items())],
        )

        # ---- Per Outlet
        ws = wb.create_sheet("Per Outlet")
        sheet(
            ws, "Progress Input Stok Outlet -- per Outlet",
            ["External Code", "Kode Customer", "Outlet", "Salesperson Odoo", "Total SKU", "Sudah Input",
             "Belum Input", "% Input", "Input Terakhir (WITA)", "Diinput Oleh (eSuite)"],
            [22, 14, 36, 28, 10, 12, 12, 9, 20, 28],
            [[o["external_code"], o["cust_code"], o["name"], o["salesperson"], o["total"], o["done"],
              o["total"] - o["done"], pct(o["done"], o["total"]), fmt(o["last"]),
              ", ".join(o["by"]) or "-"] for o in outlets],
        )

        # ---- Belum Input
        ws = wb.create_sheet("Belum Input")
        pending = [
            [o["external_code"], o["name"], o["salesperson"], i["code"], i["name"]]
            for o in outlets
            for i in sorted(o["items"].values(), key=lambda x: x["name"])
            if not i["input"]
        ]
        sheet(
            ws, "SKU Belum Diinput",
            ["External Code Outlet", "Outlet", "Salesperson Odoo", "Kode Produk", "Produk"],
            [22, 36, 28, 14, 50],
            pending,
        )

        # ---- Detail
        ws = wb.create_sheet("Detail")
        detail = [
            [o["external_code"], o["name"], o["salesperson"], i["code"], i["name"],
             "Sudah" if i["input"] else "Belum", fmt(i["last"]), ", ".join(sorted(i["by"])) or "-", i["row_count"]]
            for o in outlets
            for i in sorted(o["items"].values(), key=lambda x: x["name"])
        ]
        sheet(
            ws, "Detail SKU per Outlet",
            ["External Code Outlet", "Outlet", "Salesperson Odoo", "Kode Produk",
             "Produk", "Status", "Input Terakhir (WITA)", "Diinput Oleh (eSuite)", "Jumlah Baris"],
            [22, 36, 28, 14, 50, 9, 20, 24, 8],
            detail,
        )
        for r in range(5, 5 + len(detail)):
            if ws.cell(row=r, column=6).value == "Belum":
                ws.cell(row=r, column=6).fill = red

        # ---- Catatan
        ws = wb.create_sheet("Catatan")
        ws.column_dimensions["A"].width = 120
        for r, text in enumerate([
            "Catatan",
            "Total SKU = semua produk di Product Stock outlet (eSuite) = pre-fill bridge (riwayat order Odoo) + tambahan sales.",
            "Sudah Input = minimal 1 baris produk itu: stok >= 1, ATAU punya expired, ATAU baris dibuat user app (created_by terisi).",
            "Batasan: sales yang mengisi 0 pada baris pre-fill tanpa expired TIDAK bisa dibedakan dari belum input -> terhitung Belum.",
            "Diinput Oleh = updated_by/created_by eSuite. Pre-fill bridge yang diupdate sales tercatat '-' oleh eDot -> lihat Salesperson Odoo.",
            "Input Terakhir = waktu baris ber-expired / buatan app DIBUAT (dari id baris eSuite, sama dgn kolom Created At di UI Stocks), WITA. Bukan created_at/updated_at API (ikut terisi waktu push bridge). Placeholder pre-fill yang hanya diubah qty-nya: waktu tidak diketahui ('-').",
            "Produk discontinue (di-archive di Odoo) TIDAK dihitung (tidak perlu diinput), walau barisnya masih ada di Product Stock outlet.",
            "Outlet yang belum punya warehouse outlet di eSuite (belum pernah di-pre-fill / diinput) tidak muncul.",
            "Status stok bersifat kumulatif (bukan per kunjungan): produk yang pernah diisi tetap terhitung Sudah.",
        ], start=1):
            ws.cell(row=r, column=1, value=text).font = Font(bold=(r == 1))

        buffer = BytesIO()
        wb.save(buffer)
        return buffer.getvalue()
