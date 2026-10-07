from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.admin_area import AdminAreaResolver
from app.core.exceptions import ValidationError

# Konstanta di bawah SENGAJA DIDUPLIKASI dari customer_sync_service.py (bukan
# import silang antar service, convention project). Dipakai sejak 7 Oktober
# 2026 utk membangun address LENGKAP. KALAU value berubah, update juga di
# customer_sync_service.py & customer_upsert_geo_branch_sales_service.py.
ADDRESS_TYPE = {
    "id": "01KYNS4MBNF5GQKQN5VWV4DBWJ",
    "name": "Delivery Address",
}
COUNTRY = {"id": "ID", "name": "Indonesia", "code": ""}
EXTERNAL_CODE_PREFIX = "ODOO-PARTNER-"


class CustomerGeolocationService:
    """
    Update longitude/latitude SAJA untuk 1 Customer di eSuite, TERPISAH dari
    CustomerSyncService.sync() (upsert full payload) -- dibuat 27 Agustus 2026
    atas kebutuhan user: banyak customer eSuite yang belum ada data lat-long-nya,
    tapi edit manual lewat UI eSuite mewajibkan banyak field lain yang tidak
    relevan. Endpoint ini isi lat-long tanpa nyentuh field lain sama sekali.

    Convention SAMA dengan CustomerSyncService.deactivate() -- payload ke
    eSuite sengaja MINIMAL, mengandalkan upsert eSuite yang partial-merge
    (field yang tidak dikirim TIDAK ikut ter-reset/hilang, lihat CONFIG_NOTES.md).

    🆕 7 Oktober 2026 (keputusan user: disamakan dgn /sync/customers) --
    partial-merge itu berlaku di level field ATAS customer, TAPI addresses[]
    DIGANTI utuh tiap upsert (terbukti live). Jadi address yang cuma berisi
    longitude/latitude akan MENGHAPUS street, address_type, dan wilayah
    (administrative_level). Sekarang, untuk external_code hasil sync kita
    ("ODOO-PARTNER-{id}") yang ketemu di Odoo, address dibangun LENGKAP
    (street + wilayah dari Odoo, koordinat dari input). Untuk external_code
    lain (data legacy eSuite, tidak ada sumber di Odoo) perilaku lama
    dipertahankan + field "warning" di response.
    """

    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()
        self.admin_area = AdminAreaResolver(self.odoo, self.esuite)

    def update(self, external_code: str, coordinates: str) -> dict:
        code = (external_code or "").strip()
        if not code:
            raise ValidationError("external_code wajib diisi")

        latitude, longitude = self._parse_coordinates(coordinates)

        customer = self._find_odoo_customer(code)
        admin_area_report = None
        warning = None

        if customer:
            # Address LENGKAP -- field sama dgn
            # CustomerSyncService._to_esuite_address(), bedanya koordinat
            # SELALU dari input endpoint ini (bukan dari Odoo).
            address = {
                "id": "",
                "address_type": ADDRESS_TYPE,
                "street_address": customer.get("street") or "",
                "country": COUNTRY,
                "is_primary_address": True,
                "longitude": longitude,
                "latitude": latitude,
            }
            admin_area_map, admin_area_report = self.admin_area.resolve_map([customer])
            levels = admin_area_map.get(customer["id"])
            if levels:
                address["administrative_level"] = levels
            address_mode = "full"
        else:
            # Perilaku LAMA (27 Agustus 2026) -- external_code bukan hasil
            # sync kita / tidak ketemu di Odoo, jadi tidak ada sumber data
            # utk street & wilayah.
            address = {"longitude": longitude, "latitude": latitude}
            address_mode = "coordinates_only"
            warning = (
                "external_code ini tidak ketemu di Odoo (bukan format "
                "ODOO-PARTNER-{id}, atau customer tidak aktif) -- address "
                "dikirim HANYA berisi koordinat. eSuite mengganti addresses[] "
                "utuh, jadi street/tipe alamat/wilayah yang sudah ada di "
                "eSuite untuk customer ini kemungkinan ikut terhapus."
            )

        payload = [{"external_code": code, "addresses": [address]}]

        esuite_result = self.esuite.push("customers", event="upsert", data=payload)

        result = {
            "external_code": code,
            "latitude": latitude,
            "longitude": longitude,
            "address_mode": address_mode,
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }
        if admin_area_report is not None:
            result["administrative_area"] = admin_area_report
        if warning:
            result["warning"] = warning
        return result

    def _find_odoo_customer(self, external_code: str) -> dict | None:
        """
        "ODOO-PARTNER-{id}" -> baris res.partner dari Odoo (filter sama dgn
        sync: customer_rank > 0, active). Return None kalau format lain atau
        tidak ketemu -- caller jatuh ke perilaku lama (koordinat saja).
        """
        if not external_code.startswith(EXTERNAL_CODE_PREFIX):
            return None
        id_part = external_code[len(EXTERNAL_CODE_PREFIX):]
        if not id_part.isdigit():
            return None
        customers = self.odoo.get_customers(ids=[int(id_part)])
        return customers[0] if customers else None

    @staticmethod
    def _parse_coordinates(coordinates: str) -> tuple[float, float]:
        """
        Parse 1 field "latitude, longitude" (format hasil copas langsung dari
        Google Maps -- klik kanan titik lokasi -> klik koordinat teratas)
        menjadi (latitude, longitude) terpisah. Google Maps SELALU urutan
        lat dulu baru long -- urutan ini dipertahankan sama persis di sini,
        JANGAN dibalik.
        """
        raw = (coordinates or "").strip()
        parts = raw.split(",")
        if len(parts) != 2:
            raise ValidationError(
                "Format coordinates salah -- harus 'latitude, longitude' "
                "(1 field hasil copas dari Google Maps), contoh: "
                "-8.800799056816937, 115.18475651821433",
                details={"coordinates": coordinates},
            )

        try:
            latitude = float(parts[0].strip())
            longitude = float(parts[1].strip())
        except ValueError:
            raise ValidationError(
                "latitude/longitude bukan angka desimal yang valid",
                details={"coordinates": coordinates},
            )

        if not (-90 <= latitude <= 90):
            raise ValidationError(
                f"latitude di luar rentang valid (-90 s/d 90): {latitude} "
                "-- cek urutan, mungkin latitude/longitude tertukar",
                details={"coordinates": coordinates},
            )
        if not (-180 <= longitude <= 180):
            raise ValidationError(
                f"longitude di luar rentang valid (-180 s/d 180): {longitude} "
                "-- cek urutan, mungkin latitude/longitude tertukar",
                details={"coordinates": coordinates},
            )

        return latitude, longitude
