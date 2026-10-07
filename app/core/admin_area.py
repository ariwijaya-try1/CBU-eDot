"""
Resolver wilayah administratif: res.partner.village_id (Odoo, modul regional
ms_l10n_id_localization) -> administrative_level[] eSuite.

Dibuat 7 Oktober 2026 -- logic ini awalnya ada di customer_sync_service.py
(29 September 2026). Dipindah ke app/core supaya DIPAKAI BERSAMA oleh 3
service yang mengirim addresses[] Customer (customer_sync_service,
customer_upsert_geo_branch_sales_service, customer_geolocation_service) --
keputusan user 7 Oktober: ketiganya harus kirim wilayah yang SAMA, karena
upsert Customer eSuite MENGGANTI addresses[] (terbukti live), jadi endpoint
yang kirim address tanpa wilayah akan MENGHAPUS wilayah yang sudah ada.
Ditaruh di core (bukan import silang antar service) supaya convention "tiap
service independen" tetap terjaga, dan cache-nya cuma 1 untuk semua service.

Keputusan yang berlaku (lihat DECISION_LOG_customer_address_administrative_area.md):
- Padanan level: res.country.state -> province (0), res.city -> city (1),
  res.subdistrict -> district (2), res.village -> sub_district (3).
- Lookup LIVE ke eSuite GET /administrative-areas + cache di memori proses
  (hilang saat restart). Hanya hasil MATCH yang di-cache.
- Desa tidak ketemu/ambigu -> customer TETAP di-upsert tanpa wilayah,
  dilaporkan di report["unresolved"] (bukan fail-fast).
"""
import re

from app.core.exceptions import AppError

# key = jalur nama Odoo dinormalisasi "PROVINSI|KOTA|KECAMATAN|DESA"
# value = {"levels": administrative_level[], "esuite_path": str | None}
#   esuite_path cuma terisi kalau cocoknya lewat aturan nama longgar (lihat
#   _relaxed_path()) -- supaya tetap dilaporkan walau hasilnya dari cache.
_ADMIN_AREA_CACHE: dict[str, dict] = {}
ADMIN_AREA_LOOKUP_LIMIT = 100  # per page ke eSuite (default eSuite cuma 10)
ADMIN_AREA_MAX_PAGES = 20  # pengaman loop paging (nama desa umum bisa ratusan hasil)

# Aturan nama longgar (7 Oktober 2026) -- dipakai HANYA kalau 4 nama persis
# tidak ketemu. Bukti live: Odoo "Jakarta > Kota Adm. Jakarta Pusat" vs
# eSuite "DKI JAKARTA > JAKARTA PUSAT". Kata-kata di bawah diabaikan saat
# membandingkan nama provinsi / kota; kecamatan & desa TETAP harus persis.
# "DI"/"DAERAH ISTIMEWA" (Yogyakarta) belum terbukti live -- dimasukkan
# dengan pola yang sama, hasilnya tetap terlihat di matched_by_relaxed_name.
PROVINCE_NOISE_WORDS = {"DKI", "DI", "DAERAH", "ISTIMEWA", "KHUSUS", "IBUKOTA", "PROVINSI"}
CITY_NOISE_WORDS = {"KOTA", "KAB", "KABUPATEN", "ADM", "ADMINISTRASI"}

_LEVEL_KEYS = ("province", "city", "district", "village")


def normalize_area_name(value) -> str:
    """
    Normalisasi nama wilayah utk dibandingkan Odoo vs eSuite: uppercase,
    semua selain huruf/angka jadi spasi, spasi dirapikan.
    Contoh: "Kab. Badung" -> "KAB BADUNG".
    """
    text = re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper())
    return " ".join(text.split())


def _drop_words(name: str, noise: set) -> str:
    kept = [w for w in name.split() if w not in noise]
    # kalau semua kata terbuang (nama cuma berisi kata "noise"), pakai nama asli
    return " ".join(kept) if kept else name


def _relaxed_path(path: list[str]) -> list[str]:
    """[provinsi, kota, kecamatan, desa] -> versi longgar (provinsi & kota saja)."""
    return [
        _drop_words(path[0], PROVINCE_NOISE_WORDS),
        _drop_words(path[1], CITY_NOISE_WORDS),
        path[2],
        path[3],
    ]


def to_administrative_level(area: list[dict]) -> list[dict]:
    """
    area[] hasil lookup -> administrative_level[] payload, urut level 0->3
    (aturan dev eSuite 22 September 2026). Field PERSIS dari lookup:
    id/name/code/type/level, + postal_code kalau ada (level 3).
    """
    levels = []
    for a in area:
        item = {k: a.get(k) for k in ("id", "name", "code", "type", "level")}
        if a.get("postal_code"):
            item["postal_code"] = a["postal_code"]
        levels.append(item)
    return levels


class AdminAreaResolver:
    def __init__(self, odoo, esuite):
        self.odoo = odoo
        self.esuite = esuite

    def resolve_map(self, customers: list[dict]) -> tuple[dict[int, list[dict]], dict]:
        """
        customers = baris res.partner dari OdooClient.get_customers() (butuh
        field "id" dan "village_id").

        Alur:
        1. Kumpulkan desa UNIK dari customer (bukan per customer).
        2. Telusuri nama provinsi/kota/kecamatan/desa di Odoo
           (OdooClient.get_village_hierarchy(), 4 query bulk).
        3. Per desa: cek cache; kalau belum ada, cari ke eSuite (_lookup()).
        4. Desa yang tidak ketemu/ambigu/error -> masuk report["unresolved"].

        Return: ({partner_id: administrative_level[]}, report)
        """
        report = {
            "resolved_customers": 0,
            "customers_without_village_in_odoo": 0,
            # ringkasan per DESA (bukan per customer)
            "unique_villages": 0,
            "resolved_villages": 0,
            # desa yang cocok lewat aturan nama longgar (provinsi/kota beda
            # penulisan) -- supaya bisa dicek mata, bukan diam-diam
            "matched_by_relaxed_name": [],
            "unresolved": [],
        }

        customers_by_village: dict[int, list[int]] = {}
        for c in customers:
            village = c.get("village_id")  # many2one: [id, display_name] / False
            if village:
                customers_by_village.setdefault(village[0], []).append(c["id"])
            else:
                report["customers_without_village_in_odoo"] += 1

        if not customers_by_village:
            return {}, report

        hierarchy = self.odoo.get_village_hierarchy(list(customers_by_village.keys()))

        village_levels: dict[int, list[dict]] = {}
        for village_id, partner_ids in customers_by_village.items():
            names = hierarchy.get(village_id)
            if not names:
                report["unresolved"].append({
                    "odoo_village_id": village_id,
                    "reason": "odoo_hierarchy_incomplete",
                    "customer_ids": partner_ids,
                })
                continue

            key = "|".join(normalize_area_name(names[k]) for k in _LEVEL_KEYS)
            entry = _ADMIN_AREA_CACHE.get(key)

            if entry is None:
                try:
                    levels, reason, candidates, esuite_path = self._lookup(names)
                except AppError as e:
                    report["unresolved"].append({
                        "odoo_path": key,
                        "reason": "lookup_error",
                        "error": e.to_dict()["error"].get("message", ""),
                        "customer_ids": partner_ids,
                    })
                    continue

                if not levels:
                    report["unresolved"].append({
                        "odoo_path": key,
                        "reason": reason,
                        # jalur di eSuite yang paling mirip (maks 5) -- bantu
                        # diagnosa beda ejaan
                        "esuite_candidates": candidates[:5],
                        "customer_ids": partner_ids,
                    })
                    continue

                entry = {"levels": levels, "esuite_path": esuite_path}
                _ADMIN_AREA_CACHE[key] = entry

            village_levels[village_id] = entry["levels"]
            if entry["esuite_path"]:
                report["matched_by_relaxed_name"].append({
                    "odoo_path": key,
                    "esuite_path": entry["esuite_path"],
                    "customer_count": len(partner_ids),
                })

        partner_levels: dict[int, list[dict]] = {}
        for village_id, levels in village_levels.items():
            for pid in customers_by_village[village_id]:
                partner_levels[pid] = levels
        report["resolved_customers"] = len(partner_levels)
        report["unique_villages"] = len(customers_by_village)
        report["resolved_villages"] = len(village_levels)
        return partner_levels, report

    def _lookup(self, names: dict) -> tuple[list[dict] | None, str, list[str], str | None]:
        """
        Cari 1 desa di eSuite: GET /administrative-areas?level=3&keyword=<desa>.
        eSuite TIDAK punya filter induk dan `keyword` cocok SEBAGIAN (bukti
        live 7 Oktober: "MENTENG" ikut balikin "MENTENG KARYA"), jadi semua
        hasil disaring di sini:
          1. PERSIS: 4 nama (provinsi/kota/kecamatan/desa) sama setelah
             normalize_area_name() -- mis. "Kab. Badung" == "KAB BADUNG".
          2. LONGGAR (hanya kalau 1. kosong): kecamatan & desa persis,
             provinsi & kota dibandingkan tanpa kata di *_NOISE_WORDS.
        Di tiap tahap harus ketemu TEPAT 1; lebih dari 1 = "ambiguous".

        Return: (administrative_level | None, reason, kandidat, esuite_path)
        reason: "matched" | "ambiguous" | "not_found_in_esuite"
        esuite_path: terisi hanya kalau cocoknya lewat tahap LONGGAR.
        """
        target = [normalize_area_name(names[k]) for k in _LEVEL_KEYS]
        target_relaxed = _relaxed_path(target)

        exact: list[list[dict]] = []
        relaxed: list[list[dict]] = []
        # (skor, teks) -- skor = jumlah level yang namanya sama dgn Odoo,
        # dihitung dari desa ke atas; dipakai mengurutkan kandidat di laporan.
        scored: list[tuple[int, str]] = []

        page = 1
        while page <= ADMIN_AREA_MAX_PAGES:
            result = self.esuite.pull_with_params(
                "administrative-areas",
                {
                    "level": 3,
                    "keyword": (names["village"] or "").strip().upper(),
                    "page": page,
                    "limit": ADMIN_AREA_LOOKUP_LIMIT,
                },
            )
            for record in result.get("data") or []:
                area = sorted(record.get("area") or [], key=lambda a: int(a.get("level") or 0))
                path = [normalize_area_name(a.get("name")) for a in area]
                if path == target:
                    exact.append(area)
                    continue
                if len(path) == 4 and _relaxed_path(path) == target_relaxed:
                    relaxed.append(area)
                    continue
                score = 0
                if len(path) == len(target):
                    for mine, theirs in zip(reversed(target), reversed(path)):
                        if mine != theirs:
                            break
                        score += 1
                scored.append((score, self._path_text(area)))

            total_page = (result.get("meta") or {}).get("total_page") or 1
            if page >= total_page:
                break
            page += 1

        for matches, is_relaxed in ((exact, False), (relaxed, True)):
            if len(matches) == 1:
                esuite_path = self._path_text(matches[0]) if is_relaxed else None
                return to_administrative_level(matches[0]), "matched", [], esuite_path
            if len(matches) > 1:
                return None, "ambiguous", [
                    " > ".join(f"{a.get('name')} ({a.get('code')})" for a in m) for m in matches
                ], None

        # sort stabil: skor tertinggi dulu, urutan asli eSuite dipertahankan
        scored.sort(key=lambda item: -item[0])
        return None, "not_found_in_esuite", [text for _, text in scored], None

    @staticmethod
    def _path_text(area: list[dict]) -> str:
        return " > ".join(a.get("name") or "" for a in area)
