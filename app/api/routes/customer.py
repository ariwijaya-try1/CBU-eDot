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
            "ODOO-PARTNER-1,ODOO-PARTNER-2). Kosongkan untuk semua customer. "
            "TIDAK BISA dipakai bersamaan dengan `names`."
        ),
    ),
    names: str | None = Query(
        default=None,
        description=(
            "OPSIONAL (31 Agustus 2026) -- ALTERNATIF dari external_codes: "
            "upsert customer TERTENTU dicari BY NAMA (bukan id Odoo), "
            "comma-separated kalau >1, mis. 'Swan Mart,NINE MART,PADANG "
            "PADANG MART'. Match EXACT (case-insensitive, TAPI harus sama "
            "persis susunan/spasi kata dengan nama di Odoo -- BUKAN partial/"
            "substring). Nama yang TIDAK ketemu atau ketemu LEBIH DARI 1 "
            "record (ambigu) akan DI-SKIP (tidak diupsert) dan dilaporkan di "
            "response['name_search'] -- nama lain yang valid tetap diproses. "
            "TIDAK BISA dipakai bersamaan dengan `external_codes`."
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
    only_with_coordinates: bool = Query(
        default=False,
        description=(
            "OPSIONAL (4 September 2026) -- True: cuma upsert customer yang "
            "partner_latitude & partner_longitude-nya SUDAH terisi di Odoo "
            "(keduanya != 0). False (default): semua customer, ada/tidak "
            "ada koordinat -- behavior lama, tidak berubah. Berlaku sebagai "
            "filter TAMBAHAN, bareng dgn external_codes/names/limit kalau "
            "dipakai. ⚠️ Kalau dipakai BARENG `names`: nama yang match "
            "persis tapi belum ada koordinat akan muncul di "
            "response['name_search']['not_found'] (bukan berarti customer-"
            "nya tidak ada)."
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

    `names` (31 Agustus 2026) -- cara ALTERNATIF pilih customer BY NAMA,
    lihat deskripsi param di bawah. Nama yang tidak ketemu/ambigu dilaporkan
    di response['name_search'], tidak menghentikan nama lain yang valid.

    `only_with_coordinates` (4 September 2026) -- filter opsional, True =
    cuma customer yang lat/long-nya sudah terisi di Odoo yang di-upsert.
    Lihat deskripsi param di bawah untuk detail & catatan interaksi dgn
    `names`.

    `customer_groups` (4 September 2026) -- SEKARANG di-AUTO-RESOLVE dari
    `res.partner.industry_id` Odoo (bukan perlu panggil endpoint mapping
    manual `/api/mapping/customer-grouping` terpisah lagi). SYARAT: Customer
    Group yang bersangkutan HARUS SUDAH pernah di-sync ke eSuite duluan lewat
    `POST /sync/customer-group` (sumbernya SAMA, res.partner.industry).
    Customer yang industry_id-nya belum ke-resolve (belum pernah di-sync
    customer-group-nya) TETAP di-upsert normal (field lain jalan), cuma
    `customer_groups` utk row itu di-skip -- dilaporkan di
    response['customer_group_unresolved_industries'] (key ini HANYA muncul
    kalau ada yang belum ke-resolve). Endpoint manual
    `/api/mapping/customer-grouping` TETAP ada untuk override/koreksi di luar
    industry_id.
    """
    return service.sync(
        event=event,
        limit=limit,
        batch_size=batch_size,
        external_codes=external_codes,
        names=names,
        include_payload=include_payload,
        only_with_coordinates=only_with_coordinates,
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
