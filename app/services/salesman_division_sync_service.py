from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import ValidationError

# Prefix external_code Salesman Division -- konsisten pola "ODOO-*" (id Odoo
# jadi bagian key upsert/delete di eSuite), sama seperti ODOO-COMPANY- di
# branch_sync_service.py dan ODOO-PARTNER- di customer_sync_service.py.
EXTERNAL_CODE_PREFIX = "ODOO-SALESTEAM-"


class SalesmanDivisionSyncService:
    """
    Sync Salesman Division: Odoo crm.team (Sales Team) -> eSuite
    POST /salesman-division.

    KEPUTUSAN 18 Agustus 2026 (dikonfirmasi user setelah investigasi
    struktur Sales Team CBU langsung di UI Odoo -- lihat sales_entities_gap.md
    untuk detail lengkap gap Salesman individual, yang MASIH TERPISAH & belum
    dikerjakan):
    - Sales Team Odoo = representasi WILAYAH/TERRITORY (mis. "BALI FS AREA
      1"), BUKAN representasi 1 karyawan -- anggota tiap team cuma kode
      slot/rute (mis. "[SALES] BAL FS01") yang orangnya bisa berganti-ganti,
      bukan identitas personal. Cocok dipetakan 1:1 jadi Salesman Division
      di eSuite (entity terpisah yang wajib ada duluan sebelum push Salesman
      individual).
    - SEMUA active Sales Team dipush apa adanya, termasuk yang non-territory
      ("Sales"/"OFFICE"/"ONLINE") -- tidak ada filter exclude.
    - `employees` SENGAJA dikirim kosong ([]) -- push Salesman individual
      MASIH DITUNDA (gap identitas personal per-slot belum selesai, lihat
      sales_entities_gap.md). Field ini BUKAN circular blocker (dikonfirmasi
      dari skema PDF) -- boleh diisi belakangan lewat upsert begitu Salesman
      sudah ada di eSuite, tanpa perlu re-push Division dari awal.
    - `product_groups` (opsional di skema) SENGAJA belum dikirim -- butuh id
      master data eSuite yang belum ada cara resolve-nya, sama seperti
      department/job_position di gap Salesman individual.
    - TIDAK difilter company -- lihat catatan di
      OdooClient.get_sales_teams().
    """

    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(self, event: str = "upsert"):
        teams = self.odoo.get_sales_teams()

        if not teams:
            raise ValidationError("Tidak ada crm.team (Sales Team) active ditemukan di Odoo")

        payload = [self._to_esuite_payload(t) for t in teams]
        esuite_result = self.esuite.push("salesman-division", event=event, data=payload)

        return {
            "total_matched_in_odoo": len(teams),
            "synced_count": len(payload),
            "external_codes": [item["external_code"] for item in payload],
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _to_esuite_payload(self, team: dict) -> dict:
        return {
            # external_code = key upsert/delete di eSuite -- harus stabil & unik.
            "external_code": f"{EXTERNAL_CODE_PREFIX}{team['id']}",
            "name": team["name"],
            "code": self._to_code(team["name"]),
            "status": "active",
            # employees kosong -- lihat catatan lengkap di docstring class.
            "employees": [],
        }

    @staticmethod
    def _to_code(name: str) -> str:
        """
        "BALI FS AREA 1" -> "BALIFSAREA1" -- eSuite wajib `code` <=20 char,
        UPPERCASE + angka saja (tanpa spasi/simbol). Auto-generate dari nama
        Sales Team (dikonfirmasi user 18 Agustus 2026), bukan convention
        kode manual terpisah.
        """
        code = "".join(ch for ch in name.upper() if ch.isalnum())
        return code[:20]
