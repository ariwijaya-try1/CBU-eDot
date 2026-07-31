from fastapi import APIRouter, Request, Query
from app.core.limiter import limiter
from app.services.customer_service import CustomerService

router = APIRouter()
service = CustomerService()


@router.get("/customers")
@limiter.limit("20/minute")
def get_customers(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
):
    return service.get_customers(page=page, limit=limit)


@router.get("/customers/search")
@limiter.limit("20/minute")
def search_customers(
    request: Request,
    keyword: str = Query(min_length=2, max_length=50),
):
    return service.search_customers(keyword)
