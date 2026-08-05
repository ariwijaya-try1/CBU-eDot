from fastapi import APIRouter, Query
from app.clients.esuite_client import EsuiteClient

router = APIRouter()
client = EsuiteClient()


@router.get("/debug/pull/{entity_path}")
def pull_reference(
    entity_path: str,
    page: int = Query(default=1),
    limit: int = Query(default=50),
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
    """
    return client.pull(entity_path, page=page, limit=limit)
