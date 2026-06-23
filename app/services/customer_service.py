import math
from app.clients.odoo_client import OdooClient


class CustomerService:
    def __init__(self):
        self.client = OdooClient()

    def get_customers(self, page: int, limit: int):
        total, records = self.client.get_customers(page=page, limit=limit)
        total_pages = math.ceil(total / limit) if limit else 0

        return {
            "data": records,
            "meta": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
            },
        }

    def search_customers(self, keyword: str):  # ← ini yang belum ada
        records = self.client.search_customers(keyword)

        return {
            "data": records,
            "meta": {
                "total": len(records),
            },
        }
