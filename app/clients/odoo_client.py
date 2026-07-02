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

    def get_product_by_id(self, product_id: int):
        domain = [
            [
                ("sale_ok", "=", True),
                ("id", "=", product_id),
            ]
        ]

        records = self._execute(
            "product.template",
            "search_read",
            domain,
            {
                "fields": ["id", "name", "list_price", "qty_available"],
                "limit": 1,
            },
        )

        # search_read selalu return list, jadi ambil elemen pertama kalau ada
        return records[0] if records else None

    def get_product_lots(self, product_tmpl_id: int):
        """
        Ambil quantity per lot dari stock.quant (di-group by lot_id),
        lalu digabung dengan detail lot (nama + expiration_date) dari stock.lot.
        Butuh module 'product_expiry' agar field expiration_date tersedia.
        """
        # read_group: hitung total quantity per lot_id.
        # Filter location_id.usage='internal' supaya cuma stok gudang beneran
        # (bukan lokasi virtual seperti Customer/Inventory Adjustment).
        quants = self._execute(
            "stock.quant",
            "read_group",
            [
                [
                    ("product_id.product_tmpl_id", "=", product_tmpl_id),
                    ("lot_id", "!=", False),
                    ("location_id.usage", "=", "internal"),
                ]
            ],
            {
                "fields": ["lot_id", "quantity"],
                "groupby": ["lot_id"],
            },
        )

        # Di hasil read_group, many2one field (lot_id) berbentuk [id, display_name]
        lot_ids = [q["lot_id"][0] for q in quants if q.get("lot_id")]
        if not lot_ids:
            return []

        lots = self._execute(
            "stock.lot",
            "search_read",
            [[("id", "in", lot_ids)]],
            {"fields": ["id", "name", "expiration_date"]},
        )
        lot_map = {lot["id"]: lot for lot in lots}

        result = []
        for q in quants:
            if not q.get("lot_id"):
                continue
            lot_id = q["lot_id"][0]
            lot_info = lot_map.get(lot_id, {})
            result.append(
                {
                    "lot_id": lot_id,
                    "lot_name": lot_info.get("name"),
                    "qty": q["quantity"],
                    "expiration_date": lot_info.get("expiration_date"),
                }
            )

        return result
