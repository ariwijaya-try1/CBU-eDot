from fastapi import APIRouter, Query
from app.clients.odoo_client import OdooClient
from app.core.exceptions import NotFoundError, ValidationError
from app.core.scope import IN_SCOPE_COMPANY_NAMES

router = APIRouter()
odoo = OdooClient()

# Batas atas "limit" -- SEMUA endpoint di file ini WAJIB pakai le=MAX_LIMIT
# (16 Agustus 2026, hasil security review). Tanpa batas atas, siapapun yang
# pegang API key bisa minta limit sangat besar (mis. limit=999999999) dan
# maksa Odoo balikin semua record sekaligus -- boros resource Odoo & bridge
# ini sendiri (DoS-adjacent). 500 dipilih cukup besar buat kebutuhan
# inspeksi manual, tapi tetap ada batas keras.
MAX_LIMIT = 500

# Default limit -- REVISI 18 Agustus 2026 (instruksi user): 10, bukan 50/100
# seperti sebelumnya. Cukup buat sekilas cek data tanpa Swagger kebanjiran
# baris; naikkan manual lewat parameter limit kalau butuh lebih banyak.
DEFAULT_LIMIT = 10


def _parse_ids(ids: str | None) -> list[int] | None:
    """
    Parse "18374,8857" -> [18374, 8857]. Dibungkus try/except (16 Agustus
    2026, hasil security review) -- SEBELUMNYA int() dipanggil langsung
    tanpa validasi, jadi input bukan-angka (mis. ids=abc) bikin ValueError
    mentah nembus ke atas (tidak ke-handle AppError/HTTPException manapun
    -> unhandled 500 generic). Sekarang errornya jadi ValidationError (422)
    yang rapi, konsisten dengan pola _parse_external_codes() di service lain.
    """
    if not ids:
        return None
    try:
        return [int(i.strip()) for i in ids.split(",") if i.strip()]
    except ValueError:
        raise ValidationError(
            f"Parameter 'ids' harus angka semua, pisah koma (mis. 18374,8857) -- dapat: '{ids}'",
            details={"ids": ids},
        )


@router.get("/odoo/product")
def get_odoo_product(
    limit: int | None = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description=f"Batasi jumlah baris (default {DEFAULT_LIMIT}, maksimal {MAX_LIMIT})."),
    ids: str | None = Query(default=None, description="OPSIONAL -- filter product.product id, comma-separated (mis. 18374,8857)."),
    name: str | None = Query(default=None, description="OPSIONAL -- filter name ilike (partial match)."),
):
    """
    GET mentah product.product dari Odoo 19 -- TANPA filter Saleable/
    list_price seperti proses sync (lihat POST /sync/product). Cuma buat
    cek cepat data asli lewat Swagger/Postman, tidak push apapun.
    """
    return odoo.get_products_raw(limit=limit, ids=_parse_ids(ids), name=name)


@router.get("/odoo/uom")
def get_odoo_uom(
    limit: int | None = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    name: str | None = Query(default=None, description="OPSIONAL -- filter name ilike."),
):
    """GET mentah uom.uom (Unit of Measure) dari Odoo 19."""
    return odoo.get_uoms(limit=limit, name=name)


@router.get("/odoo/customer")
def get_odoo_customer(
    limit: int | None = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    name: str | None = Query(default=None, description="OPSIONAL -- filter name ilike."),
):
    """
    GET mentah res.partner dengan customer_rank > 0 (kontak yang pernah/
    bisa dianggap Customer) + active=True -- filter SAMA dengan proses sync
    (POST /sync/customers), tapi endpoint ini murni buat cek data.
    """
    return odoo.get_contacts(limit=limit, name=name, customer_only=True)


@router.get("/odoo/contact")
def get_odoo_contact(
    limit: int | None = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    name: str | None = Query(default=None, description="OPSIONAL -- filter name ilike."),
    customer_only: bool = Query(default=False, description="OPSIONAL -- kalau True, sama dengan GET /odoo/customer (customer_rank > 0)."),
    supplier_only: bool = Query(default=False, description="OPSIONAL -- kalau True, filter supplier_rank > 0 (vendor)."),
    include_inactive: bool = Query(default=False, description="OPSIONAL -- kalau True, ikut sertakan kontak yang sudah diarsip (active=False)."),
):
    """
    GET mentah res.partner, SEMUA kontak apa adanya (tidak difilter
    customer_rank/supplier_rank secara default) -- beda dari
    GET /odoo/customer yang selalu difilter customer_rank > 0.

    Konvensi Odoo (dikonfirmasi user 16 Agustus 2026):
    - customer_rank > 0 -> kontak dianggap Customer (customer_rank = 0 -> belum pernah)
    - supplier_rank > 0 -> kontak pernah/merupakan Vendor
    Field customer_rank & supplier_rank selalu ikut di response biar kelihatan jelas.
    """
    return odoo.get_contacts(
        limit=limit,
        name=name,
        customer_only=customer_only,
        supplier_only=supplier_only,
        active_only=not include_inactive,
    )


@router.get("/odoo/customer-category")
def get_odoo_customer_category(
    limit: int | None = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """
    GET mentah res.partner.category (Contact Tags) -- dipakai buat cek
    apakah Odoo sudah punya tag FS/MT/GT/HORECA atau grup afiliasi
    customer (mis. "Pepito Group") di sini. Lihat sales_entities_gap.md
    untuk konteks kenapa endpoint ini relevan (open question Customer
    Group/Category SSOT).
    """
    return odoo.get_customer_categories(limit=limit)


@router.get("/odoo/salesperson")
def get_odoo_salesperson(
    limit: int | None = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    name: str | None = Query(default=None, description="OPSIONAL -- filter name ilike."),
):
    """
    GET mentah res.users (Salesperson) dari Odoo 19 -- cuma internal user
    (share=False, exclude portal/user eksternal).

    ASUMSI, BELUM DIKONFIRMASI (lihat sales_entities_gap.md): "Salesperson"
    di sini = res.users, konvensi standar Odoo Sales App (field
    res.partner.user_id, label UI "Salesperson"). BELUM dicek apakah CBU
    justru nyimpen data Salesman di hr.employee terpisah -- kalau hasil
    endpoint ini kelihatan gak sesuai (mis. isinya cuma akun admin/teknis,
    bukan tim sales beneran), kabari biar didesain ulang.
    """
    return odoo.get_salespersons(limit=limit, name=name)


@router.get("/odoo/customer-by-salesperson")
def get_odoo_customer_by_salesperson(
    salesperson_id: int = Query(..., description="id res.users (Salesperson) -- lihat GET /odoo/salesperson."),
    limit: int | None = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """
    GET res.partner (Customer/Contact) yang field Salesperson (user_id)-nya
    = salesperson_id ini. Kebalikan dari GET /odoo/salesperson-by-customer.
    """
    return odoo.get_customers_by_salesperson(salesperson_id=salesperson_id, limit=limit)


@router.get("/odoo/salesperson-by-customer")
def get_odoo_salesperson_by_customer(
    customer_id: int = Query(..., description="id res.partner (Customer/Contact) -- lihat GET /odoo/customer atau /odoo/contact."),
):
    """
    GET Salesperson (res.users) yang di-assign ke customer_id ini (field
    res.partner.user_id). Kebalikan dari GET /odoo/customer-by-salesperson.
    404 kalau customer_id tidak ditemukan di Odoo.
    """
    result = odoo.get_salesperson_by_customer(customer_id=customer_id)
    if not result:
        raise NotFoundError(f"res.partner id {customer_id} tidak ditemukan di Odoo")
    return result


@router.get("/odoo/pricelist")
def get_odoo_pricelist(
    limit: int | None = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    ids: str | None = Query(default=None, description="OPSIONAL -- filter product.pricelist id, comma-separated (mis. 3,5)."),
    name: str | None = Query(default=None, description="OPSIONAL -- filter name ilike."),
):
    """
    GET mentah product.pricelist (header Pricelist) dari Odoo 19 -- LANGKAH
    AWAL riset entity Pricelist eSuite (POST /pricelists, BELUM pernah
    di-push, lihat sales_entities_gap.md). `item_ids` di response cuma list
    id -- drill-down detail baris harga lewat GET /odoo/pricelist-item.

    BELUM DIVALIDASI ke live Odoo CBU -- field dipilih dari model standar
    Odoo Sales (product.pricelist), lihat odoo_client.py::get_pricelists()
    untuk detail. Kalau muncul error RPC (field/model tidak ada/tidak
    accessible), kabari pesan errornya biar disesuaikan.
    """
    return odoo.get_pricelists(limit=limit, ids=_parse_ids(ids), name=name)


@router.get("/odoo/pricelist-item")
def get_odoo_pricelist_item(
    pricelist_id: int | None = Query(default=None, description="OPSIONAL -- filter baris harga milik 1 pricelist_id tertentu (lihat GET /odoo/pricelist)."),
    product_id: int | None = Query(default=None, description="OPSIONAL -- filter baris harga milik 1 product.product id tertentu (setara tab 'Prices' di form produk Odoo -- lihat semua pricelist yang punya harga utk produk ini)."),
    limit: int | None = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """
    GET mentah product.pricelist.item (baris aturan harga per produk/
    kategori dalam 1 Pricelist) dari Odoo 19. Kosongkan pricelist_id/product_id
    untuk lihat semua baris (semua pricelist tercampur) -- isi pricelist_id
    (dari GET /odoo/pricelist) untuk drill-down 1 pricelist tertentu, atau isi
    product_id (dari GET /odoo/product) untuk lihat semua harga 1 produk lintas
    pricelist (mis. harga produk X di pricelist Tiktok vs pricelist Coco Mart)
    -- bisa diisi keduanya sekaligus (AND).

    BELUM DIVALIDASI -- lihat odoo_client.py::get_pricelist_items().
    """
    return odoo.get_pricelist_items(pricelist_id=pricelist_id, product_id=product_id, limit=limit)


@router.get("/odoo/stock-fraction")
def get_odoo_stock_fraction(
    result_limit: int | None = Query(default=5, ge=1, le=50, description="Batasi jumlah CONTOH yang ditampilkan (default 5, maksimal 50)."),
):
    """
    DIAGNOSTIC-ONLY (17 Agustus 2026) -- BUKAN bagian alur sync manapun,
    tidak push apapun. Cari produk yang qty_available-nya BUKAN bilangan
    bulat (mis. produk kg/timbang), dipakai kumpulin contoh nyata sebelum
    putuskan kebijakan pembulatan quantity di POST /sync/stock-matrix
    (eSuite API field quantity/on_hand HARUS int64 -- lihat
    stock_sync_progress.md).

    REVISI 17 Agustus 2026 (bug ditemukan user): versi PERTAMA endpoint ini
    pakai get_products_raw() -- qty_available TANPA context warehouse/
    company, jadi ke-aggregate lintas SEMUA company yang bisa diakses API
    user (termasuk 2 company DI LUAR scope, lihat app/core/scope.py) --
    hasilnya MELESET JAUH dari Odoo UI (contoh nyata: produk id 9169
    "PAULS Butter Unsalted 25kg" tampil 16.72 di endpoint lama, padahal UI
    Odoo nunjukin 9.000 Units). SEKARANG dipakai pola SAMA PERSIS dengan
    stock_sync_service.py (yang beneran dipush ke eSuite): resolve company
    in-scope -> warehouse -> get_stock_by_warehouse() PER WAREHOUSE (pakai
    context 'warehouse' Odoo, sudah terbukti akurat & konsisten dipakai
    proses sync beneran) -- supaya contoh yang ditemukan di sini match
    dengan apa yang ACTUALLY bakal dipush ke eSuite, bukan angka gado-gado
    lintas company.
    """
    companies = odoo.get_companies(IN_SCOPE_COMPANY_NAMES)
    warehouses = odoo.get_warehouses([c["id"] for c in companies])

    fractional = []
    for wh in warehouses:
        if len(fractional) >= result_limit:
            break
        for row in odoo.get_stock_by_warehouse(wh["id"]):
            qty = row["qty_available"]
            # toleransi kecil (1e-6) -- hindari false positive dari noise
            # pembulatan float, bukan produk yang genuinely fractional.
            if abs(qty - round(qty)) > 1e-6:
                fractional.append({
                    "product_id": row["id"],
                    "warehouse_id": wh["id"],
                    "warehouse_name": wh["name"],
                    "qty_available": qty,
                })

    results = fractional[:result_limit]
    # lookup nama produk biar gampang dibaca -- pakai get_products_raw()
    # CUMA buat resolve id -> name, BUKAN sumber angka qty (lihat revisi di atas).
    product_ids = list({r["product_id"] for r in results})
    names = {p["id"]: p["name"] for p in odoo.get_products_raw(ids=product_ids)} if product_ids else {}
    for r in results:
        r["name"] = names.get(r["product_id"])

    return {
        "warehouses_scanned": [w["name"] for w in warehouses],
        "fractional_found": len(fractional),
        "results": results,
    }


@router.get("/odoo/stock-location")
def get_odoo_stock_location(
    usage: str | None = Query(default="internal", description="OPSIONAL -- filter stock.location.usage (internal/supplier/customer/inventory/transit/view/production). Kosongkan utk semua usage."),
):
    """
    DIAGNOSTIC-ONLY (18 Agustus 2026) -- list SEMUA stock.location Odoo
    (bukan cuma yang nyangkut ke 1 produk seperti GET /odoo/stock-quant-raw).

    Dibuat buat verifikasi konfirmasi bisnis (lihat stock_sync_progress.md):
    filter location di get_stock_by_warehouse() sekarang cuma usage=
    "internal" -- lagi dibahas apakah perlu ditambah syarat complete_name
    mengandung "Stock". Karena complete_name itu human input, cek dulu ke
    SEMUA baris usage="internal" yang ASLI ADA di Odoo -- kalau ada yang
    contains_stock=false, itu KANDIDAT typo/pengecualian yang perlu
    diputuskan manual sebelum filter tambahan diterapkan.
    """
    return odoo.get_stock_locations(usage=usage)


@router.get("/odoo/stock-quant-raw")
def get_odoo_stock_quant_raw(
    product_id: int = Query(..., description="id product.product -- lihat GET /odoo/product."),
):
    """
    DIAGNOSTIC-ONLY (17 Agustus 2026) -- baca stock.quant MENTAH (bukan
    computed qty_available) buat 1 produk, TERMASUK detail lokasi
    (complete_name/usage/warehouse_id/company_id per baris quant).

    Dibuat buat investigasi dugaan ICT (Inter-Company Transfer) bikin
    context {"warehouse": id} di get_stock_by_warehouse() ke-leak lintas
    company -- lihat stock_sync_progress.md utk bukti awal (qty_available
    warehouse CBU = 16.72, padahal fisik CBU 9.00 + Sunshine Food Free
    Stock 7.72 = 16.72 persis). Bandingkan `location_detail.warehouse_id`
    tiap baris di sini -- kalau ada baris yang warehouse_id-nya BUKAN
    warehouse CBU tapi tetap ikut kehitung di get_stock_by_warehouse(1),
    itu bukti langsung sumber leak-nya.
    """
    return odoo.get_stock_quants(product_id=product_id)
