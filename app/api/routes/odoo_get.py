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


@router.get("/odoo/customer-label")
def get_odoo_customer_label(
    limit: int | None = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """
    GET mentah res.partner.category (Contact Tags) -- RENAMED dari
    /odoo/customer-category (4 September 2026, konsisten dgn
    OdooClient.get_customer_labels()). Istilah "Customer Category"
    DIGANTI "Customer Label" -- sepertinya cuma tag bebas admin Odoo,
    BUKAN representasi Customer Group eSuite yang sebenarnya (lihat
    sales_entities_gap.md). Kandidat SSOT Customer Group yang lebih kuat
    sekarang GET /odoo/industry di bawah.
    """
    return odoo.get_customer_labels(limit=limit)


@router.get("/odoo/industry")
def get_odoo_industry(
    limit: int | None = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """
    GET mentah res.partner.industry (field standar Odoo "Industry") --
    ditambahkan 4 September 2026, kandidat SSOT BARU utk Customer Group
    eSuite (belum 100% dikonfirmasi user, lihat sales_entities_gap.md).
    Cek di sini dulu apakah granularitas industry Odoo CBU sama/lebih
    detail dari 4 grup CBU (FS/MT/GT/HORECA) sebelum diputuskan
    mapping/logic sync-nya.
    """
    return odoo.get_industries(limit=limit)


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


@router.get("/odoo/order-history-by-customer")
def get_odoo_order_history_by_customer(
    customer_id: int = Query(..., description="id res.partner (Customer) -- lihat GET /odoo/customer."),
    limit: int | None = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description=f"Batasi jumlah SALES ORDER (bukan baris item), default {DEFAULT_LIMIT}, maksimal {MAX_LIMIT}."),
):
    """
    DIAGNOSTIC-ONLY (28 Agustus 2026) -- GET mentah riwayat Sales Order
    (sale.order) milik 1 Customer, LENGKAP dengan baris item-nya
    (sale.order.line, key "lines" per order). TIDAK push apapun ke eSuite.

    Konteks: user butuh repopulate history order lama (yang selama ini
    cuma ada di Odoo, belum kelihatan di app eDot) lewat webhook terpisah
    POST /v1/webhook/orders/import (BELUM ada di Postman collection kita,
    lihat order_history_import.md di project memory) -- endpoint ini
    LANGKAH RISET PERTAMA, lihat dulu bentuk data asli sale.order/
    sale.order.line Odoo 19 CBU sebelum dipetakan ke payload webhook itu
    (proses mapping & push ke webhook SENGAJA DITUNDA sampai data ini
    dicek user).

    customer_id yang tidak ditemukan/tidak punya order TIDAK menghasilkan
    error -- balik list kosong (konsisten dengan
    GET /odoo/customer-by-salesperson).
    """
    return odoo.get_order_history_by_customer(customer_id=customer_id, limit=limit)


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
    product_id: int | None = Query(default=None, description="OPSIONAL -- filter ke field product_id product.pricelist.item. CATATAN (25 Agustus 2026): untuk data CBU field ini HAMPIR SELALU KOSONG (item selalu pakai product_tmpl_id, bukan product_id) -- pakai parameter product_tmpl_id di bawah untuk cari pricelist per produk."),
    product_tmpl_id: int | None = Query(
        default=None,
        description=(
            "OPSIONAL (25 Agustus 2026) -- filter baris harga milik 1 "
            "product_tmpl_id tertentu. INI YANG SEHARUSNYA DIPAKAI (bukan "
            "product_id di atas) buat cari 'pricelist mana saja yang memuat "
            "produk X' -- item Odoo CBU selalu isi product_tmpl_id, bukan "
            "product_id (lihat FIX 18 Agustus di [[pricelist_progress]]). "
            "Ambil product_tmpl_id dari GET /odoo/product (field "
            "product_tmpl_id, ditambahkan di response 25 Agustus). Hasil "
            "baris di sini punya field 'pricelist_id' -- kumpulkan semua id "
            "unik-nya lalu push manual lewat POST /sync/pricelist?ids=<id1,id2,...>."
        ),
    ),
    limit: int | None = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
):
    """
    GET mentah product.pricelist.item (baris aturan harga per produk/
    kategori dalam 1 Pricelist) dari Odoo 19. Kosongkan semua filter untuk
    lihat semua baris (semua pricelist tercampur) -- isi pricelist_id (dari
    GET /odoo/pricelist) untuk drill-down 1 pricelist tertentu, atau isi
    product_tmpl_id (dari GET /odoo/product) untuk lihat semua harga 1
    produk lintas pricelist (mis. harga produk X di pricelist Tiktok vs
    pricelist Coco Mart) -- bisa dikombinasikan (AND).

    Cara push manual SEMUA pricelist untuk 1 produk/variant (25 Agustus
    2026, lihat [[pricelist_progress]]):
    1. GET /odoo/product?name=<nama produk> -- catat id & product_tmpl_id.
    2. POST /sync/product?product_id=<id> -- pastikan produk sudah ada di eSuite.
    3. GET /odoo/pricelist-item?product_tmpl_id=<product_tmpl_id> -- catat
       SEMUA nilai pricelist_id yang muncul (unik).
    4. POST /sync/pricelist?ids=<pricelist_id1,pricelist_id2,...> -- push
       HANYA pricelist yang memuat produk itu, bukan full 316 pricelist.

    BELUM DIVALIDASI -- lihat odoo_client.py::get_pricelist_items().
    """
    return odoo.get_pricelist_items(
        pricelist_id=pricelist_id,
        product_id=product_id,
        product_tmpl_id=product_tmpl_id,
        limit=limit,
    )


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
