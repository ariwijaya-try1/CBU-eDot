from fastapi import APIRouter, Query
from app.services.branch_sync_service import BranchSyncService

router = APIRouter()
# Router terpisah -- supaya endpoint deactivate ke-grup di Swagger tag
# "Deactivate" sendiri (bukan numpuk di "Sync"), didaftarkan terpisah di
# main.py (`tags=["Deactivate"]`). Tetap 1 file (branch.py) karena masih
# entity yang sama, cuma beda router object buat keperluan tag saja.
deactivate_router = APIRouter()
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


@deactivate_router.post("/deactivate/branch")
def deactivate_branch(
    external_codes: str = Query(
        ...,
        description=(
            "WAJIB -- external_code Branch di eSuite yang mau dinonaktifkan "
            "(status -> inactive), comma-separated. Diterima APA ADANYA "
            "(TIDAK divalidasi format 'ODOO-COMPANY-{id}') -- bisa data hasil "
            "sync kita maupun data pre-existing/legacy eSuite (mis. "
            "'ODOO-BR-001')."
        ),
    ),
):
    """
    Nonaktifkan Branch di eSuite by external_code (status: "inactive").
    Payload yang dikirim ke eSuite MINIMAL -- cuma status + external_code,
    field lain (name/address) TIDAK ikut dikirim/direset (upsert eSuite
    bersifat partial-merge).
    """
    return service.deactivate(external_codes=external_codes)
