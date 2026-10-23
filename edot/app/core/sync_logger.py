import csv
from datetime import datetime, timezone
from pathlib import Path

from app.core.exceptions import ValidationError

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


# 🆕 10 September 2026 -- kolom CSV snapshot upsert_customer_*.csv (lihat
# write_customer_upsert_csv() di bawah). Terpisah dari FIELDNAMES di atas
# (itu punya sync_log.csv, agregat per-CALL) -- ini snapshot per-CUSTOMER.
UPSERT_CUSTOMER_CSV_FIELDNAMES = [
    "customer_id",
    "external_code",
    "name",
    "status",
    "batch",
    "timestamp",
    "error",
]


def write_customer_upsert_csv(rows: list[dict]) -> str | None:
    """
    🆕 10 September 2026 -- snapshot hasil /sync/customers per-customer,
    dipakai user utk 3 kebutuhan (dikonfirmasi eksplisit): (a) filter input
    /sync/order-history -- cuma proses customer yang CONFIRMED sukses di
    eSuite, (b) checkpoint/resume -- kalau run ribuan customer terhenti di
    tengah, run berikutnya bisa skip yang sudah sukses, (c) log/audit
    histori upsert customer. Project ini TIDAK PUNYA DB (lihat
    CONFIG_NOTES.md) -- CSV ini pengganti state yang biasanya disimpan di
    tabel, bukan sekadar log tambahan.

    ⚠️ Granularity BATCH-LEVEL (bukan per-customer individual dari eSuite)
    -- keputusan user 10 September 2026: status "success"/"failed" diambil
    dari status BATCH (HTTP push ke eSuite via CustomerSyncService.sync()),
    diasumsikan SEMUA customer dalam 1 batch yang sukses ikut ke-upsert.
    Ini ASUMSI, BUKAN konfirmasi per-record dari eSuite -- endpoint
    POST /customers TIDAK diketahui punya `data.results[]` per-customer
    seperti POST /orders/import (yang memang terbukti punya itu, lihat
    order_history_import.md). Kalau nanti ketemu bukti eSuite diam-diam
    skip 1 customer dalam batch yang HTTP-nya sukses, granularity ini
    PERLU direvisi jadi per-customer beneran (perlu verifikasi raw
    response /customers dulu, jangan asumsikan sebelum ada bukti).

    SELALU file BARU per panggilan (nama `upsert_customer_{DD-MM-YYYY_
    HH-MM-SS}.csv`, timestamp lokal saat file dibuat) -- BUKAN overwrite/
    append ke file yang sama, supaya tiap run /sync/customers punya
    snapshot sendiri (bisa dibandingkan/di-diff antar run, konsisten dgn
    kebutuhan checkpoint/resume di atas). Ditulis di folder yang SAMA
    dengan sync_log.csv (LOG_FILE.parent, "logs/" sejajar app/ -- lihat
    komentar LOG_FILE di atas soal volume mount Docker).

    Dipanggil SETELAH SEMUA batch selesai diproses (bukan per-batch) --
    caller (CustomerSyncService.sync()) yang kumpulkan `rows` selama loop
    batch, method ini cuma nulis file di langkah PALING TERAKHIR.

    Best-effort & silent-fail, SAMA POLA dgn log_sync_result() -- CSV ini
    bukan business logic, jangan sampai bikin sync utama gagal gara-gara
    disk penuh/permission.

    Return: path file (str) kalau sukses, None kalau gagal tulis.
    """
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        filename = f"upsert_customer_{datetime.now().strftime('%d-%m-%Y_%H-%M-%S')}.csv"
        path = LOG_FILE.parent / filename

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=UPSERT_CUSTOMER_CSV_FIELDNAMES)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        return str(path)
    except Exception:
        # Silent-fail disengaja -- lihat docstring di atas.
        return None


def read_latest_customer_upsert_csv(
    explicit_path: str | None = None,
) -> tuple[list[int], str]:
    """
    🆕 10 September 2026 -- baca balik file upsert_customer_*.csv (hasil
    write_customer_upsert_csv() di atas) dan kembalikan list customer_id
    (int, id Odoo res.partner) yang berstatus "success". Ini bagian yang
    tadinya BELUM ada (CSV sudah bisa dibuat, tapi belum ada yang
    mengonsumsinya) -- dipakai app/api/routes/order_history.py sbg filter
    `customer_ids` ke /sync/order-history (jawab temuan log 10 September:
    mayoritas skip eSuite = "customer ... not resolved", artinya customer
    itu belum sukses di-upsert -- jadi tidak usah dicoba kirim order-nya).

    explicit_path: kalau diisi, baca file itu PERSIS (mis. mau pakai
    snapshot lama/tertentu, bukan yang terbaru). Kalau None, otomatis pilih
    file upsert_customer_*.csv dengan mtime PALING BARU di folder yang sama
    dengan sync_log.csv (LOG_FILE.parent).

    ⚠️ Granularity BATCH-LEVEL -- WARISAN dari write_customer_upsert_csv()
    (lihat docstring di atas): "success" di sini BUKAN konfirmasi
    per-customer dari eSuite, cuma proksi dari status HTTP batch saat
    /sync/customers dijalankan. Belum ada perubahan pada keterbatasan ini.

    Raise ValidationError (BUKAN silent-fail seperti fungsi log lain di
    file ini) kalau file tidak ketemu atau tidak ada baris "success" sama
    sekali -- SENGAJA beda pola: fungsi ini dipakai sbg INPUT filter yang
    menentukan customer_ids yang akan diproses, bukan sekadar logging, jadi
    caller WAJIB tahu kalau filternya kosong/salah alih-alih diam-diam
    lanjut dengan list kosong.

    Return: (customer_ids, path_file_yang_dipakai) -- path ikut dibalikin
    supaya caller (route) bisa taruh di response, biar user tahu snapshot
    mana yang dipakai.
    """
    if explicit_path:
        path = Path(explicit_path)
        # 🐛 FIX 10 September 2026 -- kalau caller kirim NAMA FILE saja
        # (bukan path lengkap, mis. "upsert_customer_10-09-2026_03-51-34.csv"),
        # Path() polos di-resolve relatif ke CWD proses ("/app"), BUKAN ke
        # folder logs/ ("/app/logs") tempat file itu sebenarnya ditulis oleh
        # write_customer_upsert_csv() -- selalu "tidak ketemu" walau filenya
        # ADA. Kalau bukan absolute path, asumsikan itu nama file di folder
        # yang SAMA dengan auto-pick di bawah (LOG_FILE.parent).
        if not path.is_absolute():
            path = LOG_FILE.parent / path
    else:
        candidates = sorted(
            LOG_FILE.parent.glob("upsert_customer_*.csv"),
            key=lambda p: p.stat().st_mtime,
        )
        path = candidates[-1] if candidates else None

    if not path or not path.exists():
        raise ValidationError(
            "Tidak ketemu file upsert_customer_*.csv -- jalankan "
            "POST /sync/customers dulu (tanpa limit kecil, supaya file "
            "snapshot ter-generate) sebelum pakai use_upsert_csv=true.",
            details={"looked_in": str(LOG_FILE.parent), "explicit_path": explicit_path},
        )

    customer_ids: list[int] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") == "success":
                try:
                    customer_ids.append(int(row["customer_id"]))
                except (TypeError, ValueError):
                    continue  # baris rusak/kosong -- skip, jangan gagalkan semua

    if not customer_ids:
        raise ValidationError(
            f"File {path.name} ketemu tapi tidak ada baris status=success -- "
            "cek isi file, atau pastikan /sync/customers yang menghasilkannya "
            "memang berhasil.",
            details={"file": str(path)},
        )

    return customer_ids, str(path)
