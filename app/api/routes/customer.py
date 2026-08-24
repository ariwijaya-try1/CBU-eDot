from fastapi import APIRouter, Query
from app.services.customer_sync_service import CustomerSyncService

router = APIRouter()
# Router terpisah -- supaya endpoint deactivate ke-grup di Swagger tag
# "Deactivate" sendiri (bukan numpuk di "Sync"), didaftarkan terpisah di
# main.py (`tags=["Deactivate"]`). Pola SAMA dengan branch.py (convention
# endpoint deactivate, lihat [[branch_deactivate_endpoint]]).
deactivate_router = APIRouter()
service = CustomerSyncService()


@router.post("/sync/customers")
def sync_customers(
    event: str = Query(default="upsert", pattern="^(init|upsert)$"),
    limit: int | None = Query(
        default=None,
        description=(
            "TEMPORARY, buat diagnostik push full batch (7 Agustus 2026) -- "
            "kirim cuma N customer pertama, bukan semua. Kosongkan (default) "
            "untuk behavior normal (semua customer)."
        ),
    ),
    batch_size: int | None = Query(
        default=None,
        ge=1,
        description=(
            "Jumlah record per batch ke eSuite (11 Agustus 2026, root cause "
            "502 di atas ~2000 record dalam 1 request). Kosongkan untuk pakai "
            "default 1000."
        ),
    ),
    external_codes: str | None = Query(
        default=None,
        description=(
            "OPSIONAL (12 Agustus 2026) -- upsert customer TERTENTU saja, "
            "comma-separated, format 'ODOO-PARTNER-{id}' (mis. "
            "ODOO-PARTNER-1,ODOO-PARTNER-2). Kosongkan untuk semua customer."
        ),
    ),
    include_payload: bool = Query(
        default=False,
        description=(
            "OPSIONAL (13 Agustus 2026) -- kalau True, response sertakan "
            "payload_sent penuh per batch. Default False supaya Swagger "
            "tetap responsif untuk batch besar -- external_codes tetap "
            "selalu tampil."
        ),
    ),
):
    """
    Trigger manual sync Customer: Odoo (res.partner, customer_rank > 0) -> eSuite.
    Field `type` di payload eSuite dipetakan dari `company_type` Odoo
    ("company" -> "company", "person" -> "individual") -- BUKAN dari
    `res.partner.type` (itu jenis alamat, bukan tipe customer).
    Push selalu dipecah per batch (default 1000 record/batch) -- lihat
    CustomerSyncService.sync() untuk detail penanganan kegagalan per batch.
    """
    return service.sync(
        event=event,
        limit=limit,
        batch_size=batch_size,
        external_codes=external_codes,
        include_payload=include_payload,
    )


@deactivate_router.post("/deactivate/customer")
def deactivate_customer(
    external_codes: str = Query(
        ...,
        description=(
            "WAJIB -- external_code Customer di eSuite yang mau dinonaktifkan "
            "(status -> inactive), comma-separated. Diterima APA ADANYA "
            "(TIDAK divalidasi format 'ODOO-PARTNER-{id}') -- bisa data hasil "
            "sync kita maupun data pre-existing/legacy eSuite."
        ),
    ),
):
    """
    Nonaktifkan Customer di eSuite by external_code (status: "inactive").
    Payload yang dikirim ke eSuite MINIMAL -- cuma status + external_code,
    field lain (name/type/addresses/invoice/dst) TIDAK ikut dikirim/direset
    (upsert eSuite bersifat partial-merge). Pola sama dengan
    POST /deactivate/branch.
    """
    return service.deactivate(external_codes=external_codes)
