from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError


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
    """

    def __init__(self):
        self.esuite = EsuiteClient()

    def update(self, external_code: str, coordinates: str) -> dict:
        code = (external_code or "").strip()
        if not code:
            raise ValidationError("external_code wajib diisi")

        latitude, longitude = self._parse_coordinates(coordinates)

        # Payload PERSIS sesuai contoh yang dikonfirmasi user (27 Agustus 2026)
        # -- addresses[] cuma berisi longitude/latitude, TANPA "id"/"address_type"/
        # "country"/"street_address" seperti full payload CustomerSyncService.
        # CATATAN (lihat customer_sync_service.py::_to_esuite_address): pola
        # eSuite selama ini "id": "" pada addresses[] = bikin address BARU tiap
        # upsert (bukan update address existing). Payload ini malah TANPA "id"
        # sama sekali -- belum ada konfirmasi apakah eSuite treat ini sebagai
        # update in-place atau tetap bikin address baru. BELUM ditest live.
        payload = [
            {
                "external_code": code,
                "addresses": [
                    {
                        "longitude": longitude,
                        "latitude": latitude,
                    }
                ],
            }
        ]

        esuite_result = self.esuite.push("customers", event="upsert", data=payload)

        return {
            "external_code": code,
            "latitude": latitude,
            "longitude": longitude,
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

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
