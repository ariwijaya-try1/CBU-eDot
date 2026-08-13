from fastapi import APIRouter, Query
from app.clients.esuite_client import EsuiteClient

router = APIRouter()
client = EsuiteClient()


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
