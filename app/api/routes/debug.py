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
        found: dict[str, dict] = {}

        page_size = 200  # aman di bawah timeout 30s esuite_client, jauh lebih kecil dari 9MB sekali tarik
        current_page = 1
        total_page = 1  # placeholder, diisi ulang dari meta setelah pull pertama

        while current_page <= total_page and len(found) < len(codes_wanted):
            result = client.pull(entity_path, page=current_page, limit=page_size)
            for record in result.get("data") or []:
                code = record.get("external_code")
                if code in codes_wanted and code not in found:
                    found[code] = record

            total_page = (result.get("meta") or {}).get("total_page", current_page)
            current_page += 1

        return {
            "status": 200,
            "message": "",
            "data": list(found.values()),
            "meta": {
                "requested": sorted(codes_wanted),
                "found": sorted(found.keys()),
                "not_found": sorted(codes_wanted - found.keys()),
                "pages_scanned": current_page - 1,
            },
        }

    return client.pull(entity_path, page=page, limit=limit)
