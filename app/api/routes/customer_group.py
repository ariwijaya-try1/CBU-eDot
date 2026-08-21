from fastapi import APIRouter, Query
from app.services.customer_group_sync_service import CustomerGroupSyncService

router = APIRouter()
service = CustomerGroupSyncService()


@router.post("/sync/customer-group")
def sync_customer_group(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL (21 Agustus 2026) -- upsert grup TERTENTU saja, "
            "comma-separated, format 'CBU-CUSTGROUP-{code}' (mis. "
            "CBU-CUSTGROUP-FS,CBU-CUSTGROUP-MT). Kosongkan untuk semua 4 grup."
        ),
    ),
    limit: int | None = Query(
        default=None,
        description="OPSIONAL -- diagnostik, kirim cuma N grup pertama. Kosongkan untuk semua.",
    ),
):
    """
    Trigger manual sync Customer Group: hardcoded list (FS/MT/GT/HORECA) -> eSuite.
    BUKAN dari Odoo -- lihat komentar CUSTOMER_GROUPS di service untuk alasan
    & catatan soal external_code (ASUMSI penamaan, belum dikonfirmasi user).
    event=init  : dipakai sekali di awal (seed pertama kali).
    event=upsert: dipakai untuk sync berikutnya (default).
    """
    return service.sync(event=event, external_codes=external_codes, limit=limit)
