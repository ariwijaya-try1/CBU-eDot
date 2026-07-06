from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

# ==========================
# Database (Auth)
# ==========================
from app.database.database import Base, engine
from app.models.user import User

# ==========================
# Routers
# ==========================
from app.routers.auth import router as auth_router
from app.api.routes.customer import router as customer_router
from app.api.routes.product import router as product_router

# ==========================
# Core
# ==========================
from app.core.config import settings
from app.core.limiter import limiter
from app.core.security import verify_api_key

# ==========================
# FastAPI App
# ==========================
app = FastAPI(
    title=settings.APP_NAME,
)

# ==========================
# Database Initialization
# ==========================
Base.metadata.create_all(bind=engine)

# ==========================
# Rate Limiter
# ==========================
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# ==========================
# CORS
# ==========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.56.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================
# Exception Handlers
# ==========================
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "message": "Too Many Requests",
        },
    )


@app.exception_handler(HTTPException)
def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
        },
    )

# ==========================
# Routers
# ==========================
app.include_router(auth_router)

app.include_router(
    customer_router,
    prefix="/api",
    dependencies=[Depends(verify_api_key)]
)

app.include_router(
    product_router,
    prefix="/api",
    dependencies=[Depends(verify_api_key)]
)

# ==========================
# Root Endpoint
# ==========================
@app.get("/")
def root():
    return {
        "status": "ok"
    }