"""
Snapshot & diff baris Product Stock outlet (GET stock-matrix?warehouse_id=) -- 17 Nov 2026.

Read-only (GET saja). Dipakai uji perilaku created_by/updated_by eSuite saat sales
mengubah stok di eWork (TEST_PLAN_outlet_stock.md Tahap 9). Snapshot disimpan di
logs/stock_snapshot_<label>.json (label sama = ditimpa).
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import NotFoundError, ValidationError

WITA = timezone(timedelta(hours=8))
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"  # sejajar app/, sama dgn sync_log.csv
LABEL_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,50}$")  # cegah path traversal lewat label
DIFF_FIELDS = ["batch", "on_hand", "created_by", "created_by_name", "updated_by", "updated_by_name",
               "created_at", "updated_at", "objectid_time"]


def _wita(epoch) -> str:
    """epoch detik/milidetik -> 'YYYY-mm-dd HH:MM:SS' WITA; kosong/0 -> ''."""
    try:
        value = float(epoch)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    if value > 1e12:
        value /= 1000
    return datetime.fromtimestamp(value, WITA).strftime("%Y-%m-%d %H:%M:%S")


def _row(r: dict) -> dict:
    rid = str(r.get("id") or "")
    oid = int(rid[:8], 16) if len(rid) == 24 else None  # 8 hex pertama ObjectId = waktu baris dibuat
    variant = r.get("product_variant") or {}
    return {
        "id": rid,
        "product": variant.get("code", ""),
        "product_name": variant.get("name", ""),
        "batch": (r.get("batch") or {}).get("code", ""),
        "on_hand": r.get("on_hand"),
        "created_by": r.get("created_by"),
        "created_by_name": r.get("created_by_name"),
        "updated_by": r.get("updated_by"),
        "updated_by_name": r.get("updated_by_name"),
        "created_at": _wita(r.get("created_at")),
        "updated_at": _wita(r.get("updated_at")),
        "objectid_time": _wita(oid) if oid else "",
    }


def _path(label: str) -> Path:
    if not LABEL_PATTERN.match(label or ""):
        raise ValidationError("label hanya boleh huruf, angka, _ atau - (maks 50)", details={"label": label})
    return LOG_DIR / f"stock_snapshot_{label}.json"


def snapshot(warehouse_id: str, products: str | None = None, label: str | None = None,
             client: EsuiteClient | None = None) -> dict:
    """Ambil baris stok 1 warehouse outlet (opsional filter kode MPV), simpan kalau label diisi."""
    wanted = {p.strip() for p in (products or "").split(",") if p.strip()}
    path = _path(label) if label else None  # validasi label sebelum call eSuite
    result = (client or EsuiteClient()).pull_with_params("stock-matrix", {"warehouse_id": warehouse_id})
    rows = sorted(
        (_row(r) for r in result.get("data") or []
         if (r.get("warehouse") or {}).get("id") == warehouse_id
         and (not wanted or (r.get("product_variant") or {}).get("code") in wanted)),
        key=lambda x: (x["product"], x["batch"]),
    )
    data = {"warehouse_id": warehouse_id, "products": sorted(wanted), "label": label,
            "taken_at": datetime.now(WITA).strftime("%Y-%m-%d %H:%M:%S"), "row_count": len(rows), "rows": rows}
    if path:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        data["saved_to"] = f"logs/{path.name}"
    return data


def diff(before_label: str, after_label: str) -> dict:
    """Bandingkan 2 snapshot tersimpan: baris baru / berubah (field apa) / hilang."""
    def load(label):
        p = _path(label)
        if not p.exists():
            raise NotFoundError(f"snapshot '{label}' belum ada", details={"label": label})
        snap = json.loads(p.read_text(encoding="utf-8"))
        return snap, {x["id"]: x for x in snap["rows"]}

    b_snap, before = load(before_label)
    a_snap, after = load(after_label)
    new, changed, removed = [], [], []
    for rid, x in after.items():
        if rid not in before:
            new.append(x)
            continue
        delta = {k: {"before": before[rid][k], "after": x[k]} for k in DIFF_FIELDS if before[rid][k] != x[k]}
        if delta:
            changed.append({"id": rid, "product": x["product"], "batch": x["batch"], "changes": delta})
    removed = [x for rid, x in before.items() if rid not in after]
    return {
        "before": {"label": before_label, "taken_at": b_snap["taken_at"], "row_count": len(before)},
        "after": {"label": after_label, "taken_at": a_snap["taken_at"], "row_count": len(after)},
        "new_rows": new, "changed_rows": changed, "removed_rows": removed,
    }


WAREHOUSE_PAGE_SIZE = 200
WAREHOUSE_MAX_PAGES = 50  # pengaman loop paging (warehouse saat ini ~21)


def find_warehouses(name: str, client: EsuiteClient) -> dict:
    """
    17 Nov 2026 -- cari id warehouse eSuite by nama (case-insensitive, mengandung `name`).
    Warehouse outlet external_code kosong -> tidak bisa dicari lewat external_codes, jadi
    dicocokkan dari GET /warehouse (semua halaman). address.id = id customer eSuite.
    """
    keyword = (name or "").strip().lower()
    if not keyword:
        raise ValidationError("name wajib diisi", details={"name": name})

    rows, page = [], 1
    while page <= WAREHOUSE_MAX_PAGES:
        result = client.pull("warehouse", page=page, limit=WAREHOUSE_PAGE_SIZE)
        batch = result.get("data") or []
        rows.extend(batch)
        total_page = (result.get("meta") or {}).get("total_page") or 0
        if not batch or page >= total_page:
            break
        page += 1

    matches = [
        {
            "id": w.get("id") or "",
            "name": w.get("name") or "",
            "external_code": w.get("external_code") or "",
            "type": "internal" if str(w.get("external_code") or "").startswith("ODOO-WH-") else "outlet",
            "customer_id": (w.get("address") or {}).get("id") or "",  # = id customer eSuite (warehouse outlet)
            "created_at": _wita(w.get("created_at")) or w.get("created_at") or "",
        }
        for w in rows
        if keyword in str(w.get("name") or "").lower()
    ]
    return {"status": 200, "message": "", "data": matches,
            "meta": {"name": name, "match_count": len(matches), "warehouse_scanned": len(rows)}}
