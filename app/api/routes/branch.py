from fastapi import APIRouter, Query
from app.services.branch_sync_service import BranchSyncService

router = APIRouter()
service = BranchSyncService()


@router.post("/sync/branch")
def sync_branch(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL (21 Agustus 2026) -- upsert Branch TERTENTU saja, "
            "comma-separated, format 'ODOO-COMPANY-{id}' (mis. "
            "ODOO-COMPANY-1,ODOO-COMPANY-2). Kosongkan untuk semua company in-scope."
        ),
    ),
    limit: int | None = Query(
        default=None,
        description="OPSIONAL -- diagnostik, kirim cuma N company pertama. Kosongkan untuk semua.",
    ),
):
    """
    Trigger manual sync Branch: Odoo (res.company) -> eSuite.
    event=init  : dipakai sekali di awal (seed pertama kali).
    event=upsert: dipakai untuk sync berikutnya (default).
    """
    return service.sync(event=event, external_codes=external_codes, limit=limit)
