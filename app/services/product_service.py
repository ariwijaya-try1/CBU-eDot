import math
from app.clients.odoo_client import OdooClient
from app.core.exceptions import NotFoundError


class ProductService:
    def __init__(self):
        self.client = OdooClient()

    def get_products(self, page: int, limit: int):
        total, records = self.client.get_products(page=page, limit=limit)
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

    def search_products(self, keyword: str):
        records = self.client.search_products(keyword)

        return {
            "data": records,
            "meta": {
                "total": len(records),
            },
        }

    def get_product(self, product_id: int):
        record = self.client.get_product_by_id(product_id)

        if record is None:
            raise NotFoundError(
                message=f"Product with id {product_id} not found",
                details={"product_id": product_id},
            )

        return {"data": record}
