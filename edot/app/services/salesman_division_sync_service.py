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

    def sync(
        self,
        event: str = "upsert",
        external_codes: str | None = None,
        limit: int | None = None,
    ):
        odoo_ids = self._parse_external_codes(external_codes) if external_codes else None
        teams = self.odoo.get_sales_teams(ids=odoo_ids)

        if not teams:
            raise ValidationError(
                "Tidak ada crm.team (Sales Team) active ditemukan di Odoo (cek juga external_codes kalau diisi)"
            )

        total_matched = len(teams)

        # limit -- diagnostic aid, pola sama service lain (kirim cuma N
        # division pertama). Default None -> behavior normal (semua division).
        if limit is not None:
            teams = teams[:limit]

        payload = [self._to_esuite_payload(t) for t in teams]
        esuite_result = self.esuite.push("salesman-division", event=event, data=payload)

        return {
            "total_matched_in_odoo": total_matched,
            "synced_count": len(payload),
            "external_codes": [item["external_code"] for item in payload],
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def deactivate(self, external_codes: str) -> dict:
        """
        Nonaktifkan Salesman Division di eSuite (status -> "inactive") by
        external_code, TANPA re-pull data dari Odoo -- payload sengaja
        MINIMAL (cuma status + external_code, bukan full payload name/code/
        employees seperti sync()). Aman krn upsert eSuite partial-merge.
        Pola SAMA PERSIS dengan BranchSyncService.deactivate() &
        CustomerSyncService.deactivate() (convention endpoint deactivate,
        24 Agustus 2026 -- lihat [[branch_deactivate_endpoint]]).

        external_code diterima APA ADANYA (BEDA dari _parse_external_codes()
        yang dipakai sync() -- itu mewajibkan format 'ODOO-SALESTEAM-{id}'
        karena perlu resolve ke id Odoo). deactivate() tidak butuh id Odoo
        sama sekali.

        external_codes WAJIB diisi (tidak ada default "semua division").
        """
        codes = [c.strip() for c in external_codes.split(",") if c.strip()]
        if not codes:
            raise ValidationError("external_codes wajib diisi minimal 1")

        payload = [
            {"status": "inactive", "external_code": code}
            for code in codes
        ]
        esuite_result = self.esuite.push("salesman-division", event="upsert", data=payload)

        return {
            "deactivated_count": len(payload),
            "external_codes": codes,
            "payload_sent": payload,
            "esuite_response": esuite_result,
        }

    def _parse_external_codes(self, external_codes: str) -> list[int]:
        """
        Parse "ODOO-SALESTEAM-1,ODOO-SALESTEAM-2" -> [1, 2] -- pola sama
        dengan customer_sync_service.py/product_sync_service.py, buat
        upsert Salesman Division tertentu saja tanpa nyentuh yang lain.
        """
        ids = []
        for raw in external_codes.split(","):
            code = raw.strip()
            if not code:
                continue
            if not code.startswith(EXTERNAL_CODE_PREFIX):
                raise ValidationError(
                    f"external_code '{code}' tidak sesuai format '{EXTERNAL_CODE_PREFIX}{{id_odoo}}'",
                    details={"expected_prefix": EXTERNAL_CODE_PREFIX},
                )
            id_part = code[len(EXTERNAL_CODE_PREFIX):]
            if not id_part.isdigit():
                raise ValidationError(
                    f"external_code '{code}' -- bagian id bukan angka valid",
                    details={"external_code": code},
                )
            ids.append(int(id_part))
        return ids

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
