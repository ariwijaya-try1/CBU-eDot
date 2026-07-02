from fastapi import APIRouter, Request, Query
from app.core.limiter import limiter
from app.services.product_service import ProductService

router = APIRouter()
service = ProductService()


@router.get("/products")
@limiter.limit("20/minute")
def get_products(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
):
    return service.get_products(page=page, limit=limit)


@router.get("/products/search")
@limiter.limit("20/minute")
def search_products(
    request: Request,
    keyword: str = Query(min_length=2, max_length=50),
):
    return service.search_products(keyword)
