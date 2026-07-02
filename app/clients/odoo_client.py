import requests
from app.core.config import settings
from app.core.exceptions import AppError


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
            res = self.session.post(self.url, json=payload, timeout=15)
            res.raise_for_status()
            data = res.json()

            if "error" in data:
                raise AppError("ODOO_RPC_ERROR", data["error"])

            return data.get("result", [])

        except requests.Timeout:
            raise AppError("ODOO_TIMEOUT", "Odoo timeout")

        except requests.RequestException:
            raise AppError("ODOO_CONNECTION_FAILED", "Connection failed")

    def get_customers(self, page: int, limit: int):
        offset = (page - 1) * limit
        domain = [[("customer_rank", ">", 0)]]

        total = self._execute(
            "res.partner",
            "search_count",
            domain,
        )

        records = self._execute(
            "res.partner",
            "search_read",
            domain,
            {
                "fields": ["id", "name", "email", "phone"],
                "limit": limit,
                "offset": offset,
            },
        )

        return total, records

    def search_customers(self, keyword: str):
        domain = [
            [
                ("customer_rank", ">", 0),
                ("name", "ilike", keyword),
            ]
        ]

        records = self._execute(
            "res.partner",
            "search_read",
            domain,
            {
                "fields": ["id", "name", "email", "phone"],
                "limit": 50,
            },
        )

        return records

    def get_products(self, page: int, limit: int):
        offset = (page - 1) * limit
        domain = [[("sale_ok", "=", True)]]

        total = self._execute(
            "product.template",
            "search_count",
            domain,
        )

        records = self._execute(
            "product.template",
            "search_read",
            domain,
            {
                "fields": ["id", "name", "list_price", "qty_available"],
                "limit": limit,
                "offset": offset,
            },
        )

        return total, records

    def search_products(self, keyword: str):
        domain = [
            [
                ("sale_ok", "=", True),
                ("name", "ilike", keyword),
            ]
        ]

        records = self._execute(
            "product.template",
            "search_read",
            domain,
            {
                "fields": ["id", "name", "list_price", "qty_available"],
                "limit": 50,
            },
        )

        return records
