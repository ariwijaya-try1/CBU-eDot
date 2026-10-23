from fastapi import Header, HTTPException, Depends
from fastapi.security import APIKeyHeader
from app.core.config import settings
import secrets

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


def verify_api_key(
    x_api_key: str | None = Header(default=None),
    # token: str | None = Header(default=None),
    api_key: str | None = Depends(api_key_header),
):
    # key = x_api_key or token or api_key
    key = x_api_key or api_key

    if not key:
        raise HTTPException(
            status_code=401,
            # detail="Missing API key (x-api-key or token required)",
            detail="Missing API key (x-api-key required)",
        )

    if not secrets.compare_digest(key, settings.API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")

    return True
