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
            "OPSIONAL (diganti 4 September 2026) -- upsert grup TERTENTU saja, "
            "comma-separated, format 'ODOO-CONTACT-INDUSTRY-{id_odoo}' (mis. "
            "ODOO-CONTACT-INDUSTRY-34,ODOO-CONTACT-INDUSTRY-35). Kosongkan "
            "untuk semua industry."
        ),
    ),
    limit: int | None = Query(
        default=None,
        description="OPSIONAL -- diagnostik, kirim cuma N grup pertama. Kosongkan untuk semua.",
    ),
):
    """
    Trigger manual sync Customer Group: Odoo res.partner.industry -> eSuite.

    🆕 4 September 2026 -- DIGANTI dari hardcoded list (FS/MT/GT/HORECA) ke
    data DINAMIS dari Odoo (OdooClient.get_industries()), dikonfirmasi user
    setelah data real industry Odoo ternyata jauh lebih granular & beda nama
    total dari 4 grup lama (lihat komentar CUSTOMER_GROUPS di service &
    sales_entities_gap.md utk histori lengkap). 4 record lama (external_code
    prefix "CBU-CUSTGROUP-") TIDAK disentuh oleh perubahan ini, jadi orphan.
    event=init  : dipakai sekali di awal (seed pertama kali).
    event=upsert: dipakai untuk sync berikutnya (default).
    """
    return service.sync(event=event, external_codes=external_codes, limit=limit)
