from fastapi import FastAPI, HTTPException, Depends
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.customer import router as customer_router
from app.api.routes.product import router as product_router

from app.core.config import settings
from app.core.limiter import limiter
from app.core.security import verify_api_key

app = FastAPI(
    title=settings.APP_NAME,
    dependencies=[Depends(verify_api_key)],
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"success": False, "message": "Too Many Requests"},
    )


@app.exception_handler(HTTPException)
def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": exc.detail},
    )


app.include_router(customer_router, prefix="/api")
app.include_router(product_router, prefix="/api")


@app.get("/")
def root():
    return {"status": "ok"}
