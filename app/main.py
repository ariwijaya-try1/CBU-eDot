from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.api.routes.branch import router as branch_router
from app.core.config import settings
from app.core.security import verify_api_key
from app.core.exceptions import AppError

app = FastAPI(
    title=settings.APP_NAME,
    dependencies=[Depends(verify_api_key)],
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


app.include_router(branch_router, prefix="/api")


@app.get("/")
def root():
    return {"status": "ok"}
