import requests
from app.core.config import settings
from app.core.exceptions import OdooConnectionError, OdooRPCError, OdooTimeoutError


class OdooClient:
    def __init__(self):
        self.session = requests.Session()
        self.url = f"{settings.ODOO_BASE_URL}/jsonrpc"

    def _execute(self, model, method, args, kwargs=None):
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    settings.ODOO_DB,
                    settings.ODOO_UID,
                    settings.ODOO_API_KEY,
                    model,
                    method,
                    args,
                    kwargs or {},
                ],
            },
        }

        try:
            res = self.session.post(self.url, json=payload, timeout=settings.REQUEST_TIMEOUT)
            res.raise_for_status()
            data = res.json()

            if "error" in data:
                raise OdooRPCError(message=str(data["error"]))

            return data.get("result", [])

        except requests.Timeout:
            raise OdooTimeoutError()

        except requests.RequestException as e:
            raise OdooConnectionError(details={"raw": str(e)})

    def get_warehouses(self):
        """
        Sumber data untuk entity Branch di eSuite.
        active=True saja -- warehouse yang di-archive di Odoo nggak ikut disync.
        """
        domain = [[("active", "=", True)]]

        return self._execute(
            "stock.warehouse",
            "search_read",
            domain,
            {"fields": ["id", "name", "code", "partner_id", "company_id"]},
        )

    def get_partner_address(self, partner_id: int):
        """Detail alamat pemilik warehouse (res.partner), dipakai untuk isi field address Branch."""
        records = self._execute(
            "res.partner",
            "read",
            [[partner_id]],
            {
                "fields": [
                    "street",
                    "zip",
                    "partner_latitude",
                    "partner_longitude",
                ]
            },
        )
        return records[0] if records else None
