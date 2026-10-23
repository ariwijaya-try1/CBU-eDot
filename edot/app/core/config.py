from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Odoo-eSuite Bridge"
    ENV: str = "development"
    REQUEST_TIMEOUT: int = 15

    # Odoo (JSON-RPC, source of truth)
    ODOO_BASE_URL: str
    ODOO_DB: str
    ODOO_UID: int
    ODOO_API_KEY: str

    # eSuite (push target)
    # Sandbox ID contoh: https://openapistg.esuite.edot.id/v1/webhook
    ESUITE_BASE_URL: str
    ESUITE_CLIENT_ID: str
    ESUITE_CLIENT_SECRET: str

    # Auth bridge sendiri (dipanggil manual oleh tim internal)
    API_KEY: str

    CORS_ORIGINS: List[str] = []


settings = Settings()
