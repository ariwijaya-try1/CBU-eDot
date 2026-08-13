import csv
from datetime import datetime, timezone
from pathlib import Path

# Lokasi log -- SEJAJAR app/ (bukan di dalam package), supaya kalau nanti
# app/ ini dibundle jadi Docker image, folder logs/ tetap gampang di-mount
# sebagai volume terpisah (biar tidak hilang tiap container di-rebuild).
# PENTING: kalau logs/ belum ada mount volume di docker-compose, isi log
# akan reset tiap container baru -- perlu ditambahkan manual kalau mau
# log persisten antar deploy.
LOG_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "sync_log.csv"

FIELDNAMES = [
    "timestamp",
    "entity",
    "event",
    "total_matched_in_odoo",
    "synced_count",
    "failed_count",
    "batch_count",
    "status",
    "actor",  # kosong untuk sekarang -- belum ada diferensiasi user di auth
    # (cuma API key statis, lihat CONFIG_NOTES.md). Kolom disiapkan supaya
    # gampang diisi nanti kalau auth berubah, tanpa perlu ubah struktur CSV.
    "note",
]


def log_sync_result(entity: str, event: str, result: dict, note: str = "") -> None:
    """
    Catat 1 baris ringkasan tiap kali sync dijalankan (kapan, entity apa,
    event apa, berapa berhasil/gagal) ke logs/sync_log.csv. Dipanggil di
    akhir tiap *_sync_service.py::sync(), setelah push ke eSuite selesai.

    Best-effort & silent-fail SENGAJA: kalau nulis log gagal (mis. disk
    penuh, permission), JANGAN sampai bikin sync utamanya ikut gagal --
    logging itu observability, bukan business logic. Errors di sini
    di-swallow, bukan di-raise.
    """
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        is_new = not LOG_FILE.exists()

        synced = result.get("synced_count")
        failed = result.get("failed_count", 0) or 0
        if failed and synced:
            status = "partial"
        elif failed:
            status = "failed"
        else:
            status = "success"

        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entity": entity,
            "event": event,
            "total_matched_in_odoo": result.get("total_matched_in_odoo", ""),
            "synced_count": synced if synced is not None else "",
            "failed_count": failed,
            "batch_count": result.get("batch_count", ""),
            "status": status,
            "actor": "",
            "note": note,
        }

        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if is_new:
                writer.writeheader()
            writer.writerow(row)
    except Exception:
        # Silent-fail disengaja -- lihat docstring di atas.
        pass
