"""Rollout stok outlet otomatis per potongan (limit + offset).

Memanggil endpoint bridge yang SUDAH ADA (POST /api/sync/outlet-stock)
berulang-ulang -- tidak mengubah logic bridge.

Pakai (dari folder edot, Windows):
    set BRIDGE_API_KEY=xxxx
    python scripts\\rollout_outlet_stock.py            -> dry run (aman, tidak menulis)
    python scripts\\rollout_outlet_stock.py --push     -> push beneran
    python scripts\\rollout_outlet_stock.py --push --start-offset 1200   -> lanjut dari offset 1200

Berhenti otomatis kalau: aborted true, restore_failed_items berisi,
atau HTTP error (429/5xx/timeout) setelah 3x coba.
Item gagal per-item (failed_items) TIDAK menghentikan -- customer-nya
dikumpulkan lalu dijalankan ulang sekali di akhir.

Hanya pakai library standar Python (tanpa pip install).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ENDPOINT = "/api/sync/outlet-stock"
REQUEST_TIMEOUT_SECONDS = 900   # 1 potongan 100 customer bisa beberapa menit
HTTP_MAX_ATTEMPTS = 3
HTTP_RETRY_DELAY_SECONDS = 30
RETRY_CHUNK_SIZE = 20           # jumlah customer per call saat jalan ulang


def call_bridge(base_url, api_key, params):
    """POST ke bridge, return dict JSON. Raise RuntimeError kalau gagal 3x."""
    url = f"{base_url}{ENDPOINT}?{urllib.parse.urlencode(params)}"
    last_error = None
    for attempt in range(1, HTTP_MAX_ATTEMPTS + 1):
        req = urllib.request.Request(url, method="POST", data=b"",
                                     headers={"x-api-key": api_key})
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            last_error = f"HTTP {e.code}: {body}"
            if e.code < 500 and e.code != 429:
                break  # 4xx (selain 429) = salah parameter/api key, percuma diulang
        except Exception as e:  # timeout / koneksi putus
            last_error = repr(e)
            # PENTING: kalau timeout, request di server MUNGKIN masih jalan.
            # Jangan langsung ulang -- bisa 2 proses jalan bersamaan.
            break
        print(f"  ! percobaan {attempt} gagal: {last_error}; tunggu {HTTP_RETRY_DELAY_SECONDS}s")
        time.sleep(HTTP_RETRY_DELAY_SECONDS)
    raise RuntimeError(last_error)


def save(out_dir, name, data):
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def is_stop(result):
    """Kondisi wajib berhenti (sesuai aturan rollout di Decision Log)."""
    return bool(result.get("aborted")) or bool(result.get("restore_failed_items"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="push beneran (tanpa ini = dry run)")
    ap.add_argument("--start-offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--base-url", default=os.getenv("BRIDGE_URL", "http://localhost:8001"))
    args = ap.parse_args()

    api_key = os.getenv("BRIDGE_API_KEY")
    if not api_key:
        sys.exit("Set dulu environment variable BRIDGE_API_KEY")

    dry_run = "false" if args.push else "true"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("logs") / "outlet_stock_rollout" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Mode: {'PUSH' if args.push else 'DRY RUN'} | hasil disimpan di {out_dir}")

    offset = args.start_offset
    total = None
    failed_customers = []   # urut, tanpa duplikat
    totals = {"customer_count": 0, "item_count": 0, "pushed_count": 0,
              "failed_count": 0, "existing_stock_count": 0}

    while total is None or offset < total:
        t0 = time.time()
        print(f"[{datetime.now():%H:%M:%S}] offset={offset} ...", flush=True)
        try:
            result = call_bridge(args.base_url, api_key,
                                 {"dry_run": dry_run, "limit": args.limit, "offset": offset})
        except RuntimeError as e:
            print(f"BERHENTI di offset={offset}: {e}")
            print(f"Lanjutkan nanti dengan: --start-offset {offset} (cek dulu proses server sudah selesai)")
            break

        save(out_dir, f"offset_{offset:05d}", result)
        total = result.get("total_customers_in_scope", 0)
        for key in totals:
            totals[key] += int(result.get(key) or 0)
        for item in result.get("failed_items") or []:
            code = item.get("customer_external_code")
            if code and code not in failed_customers:
                failed_customers.append(code)

        print(f"  selesai {time.time() - t0:.0f}s | customer {result.get('customer_count')} "
              f"| item {result.get('item_count')} | pushed {result.get('pushed_count')} "
              f"| failed {result.get('failed_count')} | dikembalikan {result.get('existing_stock_count')} "
              f"| total scope {total}")

        if is_stop(result):
            print(f"BERHENTI: aborted={result.get('aborted')} reason={result.get('abort_reason')} "
                  f"restore_failed_items={len(result.get('restore_failed_items') or [])}. "
                  f"Kirim file offset_{offset:05d}.json ke sesi Claude sebelum lanjut.")
            save(out_dir, "summary", {"stopped_at_offset": offset, "totals": totals,
                                      "failed_customers": failed_customers})
            return

        offset += args.limit

    # Jalan ulang sekali untuk customer yang punya item gagal (mis. Good Stock location)
    retry_results = []
    if args.push and failed_customers:
        print(f"Jalan ulang {len(failed_customers)} customer dengan item gagal ...")
        for i in range(0, len(failed_customers), RETRY_CHUNK_SIZE):
            chunk = failed_customers[i:i + RETRY_CHUNK_SIZE]
            try:
                r = call_bridge(args.base_url, api_key,
                                {"dry_run": "false", "external_codes": ",".join(chunk)})
            except RuntimeError as e:
                print(f"  jalan ulang gagal: {e}")
                break
            save(out_dir, f"retry_{i:04d}", r)
            retry_results.append({"customers": chunk, "failed_count": r.get("failed_count"),
                                  "aborted": r.get("aborted"),
                                  "still_failed": r.get("failed_items")})
            print(f"  retry {len(chunk)} customer -> failed {r.get('failed_count')}")
            if is_stop(r):
                print("BERHENTI saat jalan ulang (aborted / restore_failed_items). Kirim file ke sesi Claude.")
                break

    summary = {"mode": "push" if args.push else "dry_run", "last_offset": offset,
               "total_customers_in_scope": total, "totals": totals,
               "failed_customers": failed_customers, "retry": retry_results}
    path = save(out_dir, "summary", summary)
    print(f"SELESAI. Ringkasan: {path}")


if __name__ == "__main__":
    main()
