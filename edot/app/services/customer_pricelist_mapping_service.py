from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError

# Entity path Pricelist di eSuite -- HARUS sama persis dengan
# pricelist_sync_service.py (push ke "pricelists", plural).
ENTITY_PATH = "pricelists"


class CustomerPricelistMappingService:
    """
    Mass mapping Customer -> Pricelist di eSuite (field `customer_price_list.id`
    -- ⚠️ REVISI 8 September 2026: dev eSuite konfirmasi via sample payload
    real bahwa nama field-nya "customer_price_list", BUKAN "price_list"
    seperti tertulis di PDF v2.0.0 section 9.8 -- PDF ternyata stale utk
    field ini, lihat pricelist_progress.md) -- BAGIAN TERAKHIR Task #4
    (lihat sales_entities_gap.md project memory), melengkapi
    `sales.branchs[]`/`sales.salesmans[]` yang SUDAH ADA lewat
    CustomerSalesMappingService (pola/convention endpoint SAMA persis
    dengan itu -- lihat customer_sales_mapping_service.py).

    BEDA dari mapping sales (branch+salesman WAJIB bersamaan, keduanya
    array): field `customer_price_list` di Customer itu 1 OBJECT TUNGGAL
    (bukan array) -- sesuai model bisnis "harga per toko" yang sudah dikonfirmasi
    (lihat pricelist_progress.md), 1 customer cuma bisa punya 1 pricelist
    aktif dalam satu waktu. Endpoint ini assign 1 pricelist yang SAMA ke
    banyak customer sekaligus (mass mapping) -- BUKAN matrix N customer x N
    pricelist berbeda dalam 1 panggilan; kalau ada customer yang butuh
    pricelist lain, panggil lagi terpisah per grup.

    Pricelist di-resolve by external_code (format "ODOO-PRICELIST-{id}",
    lihat pricelist_sync_service.py) lewat EsuiteClient.pull_by_param() --
    🆕 9 September 2026: DIUBAH dari find_by_external_codes() (full-scan,
    narik semua pricelist per halaman lalu filter manual) ke 1x
    GET /pricelists?external_code=<code> langsung (filter SERVER-SIDE,
    CONFIRMED LIVE oleh user -- lihat customer_sync_service.py::
    _resolve_price_list_map() utk detail lengkap & alasan perubahan ini,
    termasuk catatan soal field external_code yang tidak tampil balik di
    response GET pricelist).

    ASUMSI (26 Agustus 2026, BELUM dikonfirmasi vendor eksplisit -- tapi
    konsisten dgn pola branchs/salesmans/customer_groups yang SUDAH
    dikonfirmasi vendor: "name WAJIB diisi supaya nama muncul di UI
    company-platform, walau data-nya tetap 'berhasil' tanpa itu"): payload
    kirim `{"id", "name"}`, bukan cuma `{"id"}`. Kalau ternyata field `name`
    di sini tidak diperlukan/malah bikin error, tinggal hapus key ini di
    `map_to_pricelist()` -- bukan perubahan breaking, gampang di-revert.
    """

    def __init__(self):
        self.esuite = EsuiteClient()

    def map_to_pricelist(self, external_codes: str, pricelist_external_code: str) -> dict:
        codes = [c.strip() for c in external_codes.split(",") if c.strip()]
        if not codes:
            raise ValidationError("external_codes wajib diisi minimal 1")

        pricelist_code = pricelist_external_code.strip()
        if not pricelist_code:
            raise ValidationError("pricelist_external_code wajib diisi")

        # GET /pricelists?external_code=<code> -- filter SERVER-SIDE
        # (CONFIRMED LIVE 9 September 2026 oleh user, lihat
        # customer_sync_progress.md) -- 1x request langsung, gantikan
        # find_by_external_codes() (full-scan, dulu jadi penyebab
        # ResourceExhausted & lambat di customer_sync_service.py). Response
        # GET pricelist eSuite TIDAK menampilkan balik field "external_code"
        # record itu sendiri (selalu kosong "" -- bug tampilan eSuite,
        # sudah direquest user ke dev utk diperbaiki), tapi filter
        # query-nya sendiri TERBUKTI benar (meta.total sesuai code yang
        # diminta) -- jadi kita percaya data[0] apa adanya, TIDAK re-match
        # ke field external_code.
        result = self.esuite.pull_by_param(ENTITY_PATH, "external_code", pricelist_code)
        records = result.get("data") or []
        record = records[0] if records else None
        if not record or not record.get("id"):
            raise ValidationError(
                f"pricelist_external_code '{pricelist_code}' tidak ditemukan di eSuite -- "
                "cek dulu via GET /debug/pull/pricelists?external_codes=... (mungkin belum "
                "pernah di-push lewat POST /sync/pricelist, atau salah ketik)",
                details={"pricelist_external_code": pricelist_code},
            )

        price_list_payload = {"id": record["id"], "name": record.get("name") or ""}

        payload = [
            {"external_code": code, "customer_price_list": price_list_payload}
            for code in codes
        ]
        esuite_result = self.esuite.push("customers", event="upsert", data=payload)

        return {
            "mapped_count": len(payload),
            "external_codes": codes,
            "price_list_resolved": price_list_payload,
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }
