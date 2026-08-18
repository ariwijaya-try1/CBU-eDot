from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.api.routes.branch import router as branch_router
from app.api.routes.warehouse import router as warehouse_router
from app.api.routes.product_category import router as product_category_router
from app.api.routes.product import router as product_router
from app.api.routes.customer import router as customer_router
from app.api.routes.customer_group import router as customer_group_router
from app.api.routes.stock_matrix import router as stock_matrix_router
from app.api.routes.pricelist import router as pricelist_router
from app.api.routes.salesman_division import router as salesman_division_router
from app.api.routes.odoo_get import router as odoo_get_router
from app.api.routes.debug import router as debug_router
from app.core.config import settings
from app.core.security import verify_api_key
from app.core.exceptions import AppError

app = FastAPI(
    title=settings.APP_NAME,
    dependencies=[Depends(verify_api_key)],
    # persistAuthorization -- API key yang diisi lewat tombol Authorize
    # disimpan browser (localStorage), jadi tetap ke-fill otomatis walau
    # Swagger di-reload (mis. setelah uvicorn --reload restart karena ada
    # update code). Tidak ada hubungannya dengan expiry token -- auth kita
    # tetap static API key tanpa masa berlaku, ini cuma soal state UI.
    swagger_ui_parameters={"persistAuthorization": True},
)


@app.exception_handler(HTTPException)
def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": exc.detail},
    )


@app.exception_handler(AppError)
def app_error_handler(request, exc: AppError):
    # Menangkap semua turunan AppError (Odoo*, Esuite*, Validation, NotFound)
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, **exc.to_dict()},
    )


# tags= di sini CUMA ngatur pengelompokan judul di Swagger UI -- tidak
# mengubah path/behavior endpoint apapun. Sebelumnya semua router nggak
# dikasih tags jadi numpuk di grup "default"; sekarang dikelompokkan biar
# gampang dibedain endpoint sync vs endpoint get-inspeksi Odoo (16 Agustus 2026).
app.include_router(branch_router, prefix="/api", tags=["Sync"])
app.include_router(warehouse_router, prefix="/api", tags=["Sync"])
app.include_router(product_category_router, prefix="/api", tags=["Sync"])
app.include_router(product_router, prefix="/api", tags=["Sync"])
app.include_router(customer_router, prefix="/api", tags=["Sync"])
app.include_router(customer_group_router, prefix="/api", tags=["Sync"])
app.include_router(stock_matrix_router, prefix="/api", tags=["Sync"])
app.include_router(pricelist_router, prefix="/api", tags=["Sync"])
app.include_router(salesman_division_router, prefix="/api", tags=["Sync"])
app.include_router(odoo_get_router, prefix="/api", tags=["odoo - Get"])
app.include_router(debug_router, prefix="/api", tags=["Debug"])


@app.get("/")
def root():
    return {"status": "ok"}
