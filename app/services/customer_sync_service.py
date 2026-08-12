from app.clients.odoo_client import OdooClient
from app.clients.esuite_client import EsuiteClient
from app.core.exceptions import AppError, ValidationError

# Currency -- sama dengan yang dipakai product_sync_service.py (IDR, satu-satunya
# currency yang dipakai di seluruh bisnis, lihat CONFIG_NOTES.md). Didefinisikan
# lagi di sini (bukan import silang antar service) supaya tiap sync service tetap
# independen -- konsisten dengan pola konstanta lain di project ini
# (ADMINISTRATIVE_AREA di branch_sync_service.py, UOM_MAPPING di product_sync_service.py).
CURRENCY = {"id": "6a695cc1917e8fc836359505"}  # IDR, dari GET /currency

# Mapping company_type (Odoo) -> type (eSuite). Dikonfirmasi user 7 Agustus 2026:
# field Odoo yang benar itu company_type, BUKAN res.partner.type (itu jenis alamat).
CUSTOMER_TYPE_MAPPING = {
    "company": "company",
    "person": "individual",
}

# Batch size default -- REVISI 11 Agustus 2026: full bulk upsert (>2000 record
# dalam 1 request) kena 502 Bad Gateway dari eSuite. Push sekarang dipecah per
# batch, default 1000 record/batch (instruksi user). Tiap batch = 1 request_id
# terpisah ke eSuite (bukan retry dari request yang sama).
DEFAULT_BATCH_SIZE = 1000


class CustomerSyncService:
    def __init__(self):
        self.odoo = OdooClient()
        self.esuite = EsuiteClient()

    def sync(self, event: str = "upsert", limit: int | None = None, batch_size: int | None = None):
        customers = self.odoo.get_customers()

        if not customers:
            raise ValidationError("Tidak ada res.partner dengan customer_rank > 0 ditemukan di Odoo")

        total_matched = len(customers)

        # limit -- TEMPORARY diagnostic aid (7 Agustus 2026), BUKAN fitur bisnis
        # permanen. Ditambahkan buat isolasi root cause 502 Bad Gateway dari
        # eSuite saat push full batch customer (lihat SESSION_TRANSFER_NOTE.md):
        # test manual 1 record via Postman sukses, push full batch via bridge
        # 502 dua kali berturut-turut. limit memungkinkan test bertahap
        # (5, 50, 500 record, dst) buat cari tau apakah soal jumlah record
        # atau soal isi data tertentu, tanpa perlu ubah kode tiap kali coba.
        # Default None -> behavior sama seperti sebelumnya (semua customer).
        if limit is not None:
            customers = customers[:limit]

        payload = [self._to_esuite_payload(c) for c in customers]

        # Batching -- REVISI 11 Agustus 2026: user konfirmasi bulk upsert di atas
        # ~2000 record kena 502. Push sekarang selalu lewat batch (bukan 1 request
        # raksasa), default DEFAULT_BATCH_SIZE (1000). Tiap batch di-push
        # terpisah & independen: kalau 1 batch gagal (mis. 502 lagi), batch lain
        # TETAP lanjut jalan (tidak saling abort) -- supaya kegagalan parsial
        # kelihatan jelas per batch alih-alih 1 error generic yang nutupin
        # batch mana yang sebenarnya sukses.
        size = batch_size or DEFAULT_BATCH_SIZE
        batches = [payload[i : i + size] for i in range(0, len(payload), size)]

        batch_results = []
        synced_count = 0
        failed_count = 0

        for idx, batch in enumerate(batches, start=1):
            try:
                esuite_result = self.esuite.push("customers", event=event, data=batch)
                batch_results.append(
                    {
                        "batch": idx,
                        "size": len(batch),
                        "status": "success",
                        "external_codes": [item["external_code"] for item in batch],
                        "esuite_response": esuite_result,
                    }
                )
                synced_count += len(batch)
            except AppError as e:
                # Sengaja di-catch per batch (bukan biar propagate ke exception
                # handler global) -- supaya batch berikutnya tetap lanjut jalan
                # dan hasil akhirnya tetap melaporkan status semua batch, bukan
                # cuma batch pertama yang gagal.
                batch_results.append(
                    {
                        "batch": idx,
                        "size": len(batch),
                        "status": "failed",
                        "external_codes": [item["external_code"] for item in batch],
                        "error": e.to_dict()["error"],
                    }
                )
                failed_count += len(batch)

        return {
            "total_matched_in_odoo": total_matched,
            "total_sent": len(payload),
            "batch_size": size,
            "batch_count": len(batches),
            "synced_count": synced_count,
            "failed_count": failed_count,
            "batches": batch_results,
        }

    def _resolve_customer_type(self, company_type: str) -> str:
        mapped = CUSTOMER_TYPE_MAPPING.get(company_type)
        if not mapped:
            raise ValidationError(
                f"company_type Odoo '{company_type}' belum ada mapping-nya di CUSTOMER_TYPE_MAPPING",
                details={"odoo_company_type": company_type, "known_mappings": list(CUSTOMER_TYPE_MAPPING.keys())},
            )
        return mapped

    def _to_esuite_payload(self, customer: dict) -> dict:
        return {
            "name": customer["name"],
            # external_code = key upsert/delete di eSuite -- prefix "ODOO-PARTNER-"
            # konsisten dengan pola prefix entity lain (ODOO-COMPANY-, ODOO-PROD-).
            "external_code": f"ODOO-PARTNER-{customer['id']}",
            "type": self._resolve_customer_type(customer.get("company_type")),
            "status": "active",
            "currency": CURRENCY,
            # entity_type -- WAJIB, ditambahkan 11 Agustus 2026 setelah revisi
            # payload dari vendor eSuite (root cause gagal upsert customer).
            # Fixed "customer" untuk semua record entity ini (bukan dari Odoo).
            "entity_type": "customer",
        }
