from fastapi import APIRouter, Query
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError
from app.services import (
    customer_group_sync_service,
    customer_sync_service,
    customer_upsert_geo_branch_sales_service,
    pricelist_sync_service,
    product_sync_service,
)

router = APIRouter()
client = EsuiteClient()

# Whitelist entity_path (28 Agustus 2026) -- FIX dari security audit
# 16 Agustus (temuan #1): sebelumnya entity_path diterima BEBAS dari user
# lalu langsung disambung ke URL eSuite tanpa validasi -- siapapun pemegang
# API key bridge ini bisa GET path APAPUN di bawah host eSuite (bukan cuma
# entity referensi yang dimaksud endpoint ini), risiko probing/enumerasi
# endpoint eSuite yang tidak dimaksud. Daftar di bawah = entity yang MEMANG
# dipakai project ini (referensi lookup + entity utama), sesuai saran fix
# di security_audit.md. Kalau nanti butuh entity baru yang belum ada di
# sini, tambahkan ke set ini (bukan dibuka bebas lagi).
ALLOWED_ENTITY_PATHS = {
    "currency", "uom", "product-type", "uom-level", "administrative-areas",
    "product", "product-category", "branches", "warehouse", "customers",
    "customergroup", "stock-matrix",
}


@router.get("/debug/pull/{entity_path}")
def pull_reference(
    entity_path: str,
    page: int = Query(default=1),
    limit: int = Query(default=50),
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL (12 Agustus 2026, REVISI) -- filter hasil ke external_code "
            "tertentu saja, pisah pakai koma (mis. ODOO-PROD-18374,ODOO-PROD-8857). "
            "Kalau diisi, endpoint ini paging INTERNAL sendiri (200/halaman ke "
            "eSuite) dan berhenti begitu semua code ketemu -- parameter page/limit "
            "di atas DIABAIKAN. Ini menghindari harus tarik semua record (mis. 1250, "
            "~9MB) sekaligus yang bikin Swagger lambat/timeout -- cukup buat cari "
            "beberapa produk tertentu langsung dari Swagger tanpa jq/terminal."
        ),
    ),
):
    """
    Endpoint bantu buat lookup reference/master data eSuite (currency,
    product-type, uom, administrative-areas, dst) langsung dari sini --
    nggak perlu buka Postman terpisah tiap kali butuh cari 1 ID.

    Read-only (GET pull ke eSuite), tidak mengubah/push apa pun.

    Contoh pemakaian:
    GET /api/debug/pull/currency
    GET /api/debug/pull/product-type
    GET /api/debug/pull/uom?limit=100
    GET /api/debug/pull/product?external_codes=ODOO-PROD-18374,ODOO-PROD-8857
    """
    if entity_path not in ALLOWED_ENTITY_PATHS:
        raise ValidationError(
            f"entity_path '{entity_path}' tidak dikenal -- daftar yang diizinkan: "
            f"{', '.join(sorted(ALLOWED_ENTITY_PATHS))}",
            details={"entity_path": entity_path, "allowed": sorted(ALLOWED_ENTITY_PATHS)},
        )

    if external_codes:
        codes_wanted = {c.strip() for c in external_codes.split(",") if c.strip()}
        # Logic paging dipusatkan di EsuiteClient.find_by_external_codes()
        # (12 Agustus 2026, revisi) -- dipakai bareng oleh product_sync_service.py
        # buat resolve id produk sebelum push product-variant.
        found = client.find_by_external_codes(entity_path, codes_wanted)

        return {
            "status": 200,
            "message": "",
            "data": list(found.values()),
            "meta": {
                "requested": sorted(codes_wanted),
                "found": sorted(found.keys()),
                "not_found": sorted(codes_wanted - found.keys()),
            },
        }

    return client.pull(entity_path, page=page, limit=limit)


# Daftar reference constant hardcode (id master-data eSuite sendiri, BUKAN
# dari Odoo) yang PERLU direverifikasi tiap ganti environment -- ditambahkan
# 4 September 2026 pasca insiden currency/uom-level id DEV kepakai di PROD
# (lihat esuite_prod_cutover.md; keputusan user: TETAP hardcode + tambah
# validasi, BUKAN pindah ke dynamic resolve/env var). Kalau nanti nambah
# constant hardcode baru yang polanya sama (id eSuite native, bukan Odoo),
# tambahkan ke sini juga.
#
# (label ditampilkan ke user, entity_path GET yang dipakai buat verifikasi
# [HARUS ada di ALLOWED_ENTITY_PATHS di atas], id yang diharapkan)
REFERENCE_CONSTANT_CHECKS: list[tuple[str, str, str]] = [
    ("product_sync_service.CURRENCY", "currency", product_sync_service.CURRENCY["id"]),
    ("customer_sync_service.CURRENCY", "currency", customer_sync_service.CURRENCY["id"]),
    ("customer_group_sync_service.CURRENCY", "currency", customer_group_sync_service.CURRENCY["id"]),
    (
        "customer_upsert_geo_branch_sales_service.CURRENCY",
        "currency",
        customer_upsert_geo_branch_sales_service.CURRENCY["id"],
    ),
    ("pricelist_sync_service.CURRENCY", "currency", pricelist_sync_service.CURRENCY["id"]),
    ("product_sync_service.PRODUCT_TYPE", "product-type", product_sync_service.PRODUCT_TYPE["id"]),
    ("product_sync_service.PRODUCT_UOM_LEVEL", "uom-level", product_sync_service.PRODUCT_UOM_LEVEL["id"]),
    (
        'product_sync_service.UOM_MAPPING["units"]',
        "uom",
        product_sync_service.UOM_MAPPING["units"]["id"],
    ),
    (
        'product_sync_service.UOM_MAPPING["kg"]',
        "uom",
        product_sync_service.UOM_MAPPING["kg"]["id"],
    ),
    (
        "pricelist_sync_service.CUSTOMER_GROUP_ALL",
        "customergroup",
        pricelist_sync_service.CUSTOMER_GROUP_ALL["id"],
    ),
]

# Constant lain yang POLANYA SAMA (id eSuite native hardcode, berisiko sama
# kena bug DEV-vs-PROD) tapi TIDAK ikut dicek REFERENCE_CONSTANT_CHECKS di
# atas karena entity_path GET-nya belum ada di ALLOWED_ENTITY_PATHS (belum
# ada endpoint diagnostic-nya di bridge ini) -- ditampilkan di response biar
# tidak terlupakan, bukan diam-diam diasumsikan aman.
NOT_VERIFIED_CONSTANTS = [
    "customer_sync_service.TAX_TRANSACTION",
    "customer_sync_service.ADDRESS_TYPE",
    "customer_upsert_geo_branch_sales_service.ADDRESS_TYPE",
    "pricelist_sync_service.SALES_CHANNEL_DEFAULT",
]


@router.get("/debug/verify-reference-constants")
def verify_reference_constants():
    """
    Pre-flight check -- verifikasi semua reference constant hardcode (id
    master-data eSuite sendiri: currency, product-type, uom, uom-level,
    customergroup) MASIH VALID di environment eSuite yang aktif SEKARANG
    (ikut ESUITE_BASE_URL saat ini). Read-only, TIDAK push/ubah apa pun,
    TIDAK menyentuh logic payload service manapun.

    Jalankan endpoint ini SETIAP KALI ganti environment (base_url) SEBELUM
    push produk/customer/dst yang pertama -- supaya id yang salah ketahuan
    di sini (pesan jelas: constant mana, entity_path mana, id apa yang
    dicari), bukan lewat pola "response 200 tapi diam-diam gagal" yang
    sudah berkali-kali kejadian di project ini (lihat riwayat panjang
    `uom_levels.id` & currency PROD di esuite_prod_cutover.md/CONFIG_NOTES.md).

    Constant yang TIDAK ikut diverifikasi (belum ada entity_path yang
    di-whitelist utk itu) dilaporkan di `data.not_verified` -- bukan berarti
    aman, cuma belum bisa dicek otomatis dari sini.
    """
    ids_by_entity_path: dict[str, set[str]] = {}
    for _label, entity_path, expected_id in REFERENCE_CONSTANT_CHECKS:
        ids_by_entity_path.setdefault(entity_path, set()).add(expected_id)

    records_by_entity_path: dict[str, dict[str, dict]] = {
        entity_path: client.find_by_ids(entity_path, ids)
        for entity_path, ids in ids_by_entity_path.items()
    }

    checks = []
    for label, entity_path, expected_id in REFERENCE_CONSTANT_CHECKS:
        record = records_by_entity_path[entity_path].get(expected_id)
        checks.append(
            {
                "constant": label,
                "entity_path": entity_path,
                "expected_id": expected_id,
                "found": record is not None,
                "record_name": (record or {}).get("name") or (record or {}).get("currency"),
            }
        )

    return {
        "status": 200,
        "message": "",
        "data": {
            "esuite_base_url": client.base_url,
            "ok": all(c["found"] for c in checks),
            "checks": checks,
            "not_verified": NOT_VERIFIED_CONSTANTS,
        },
    }
