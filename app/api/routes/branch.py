from fastapi import APIRouter, Query
from app.services.branch_sync_service import BranchSyncService

router = APIRouter()
service = BranchSyncService()


@router.post("/sync/branch")
def sync_branch(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
):
    """
    Trigger manual sync Branch: Odoo (res.company) -> eSuite.
    event=init  : dipakai sekali di awal (seed pertama kali).
    event=upsert: dipakai untuk sync berikutnya (default).
    """
    return service.sync(event=event)
