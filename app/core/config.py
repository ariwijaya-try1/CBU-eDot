from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
from dotenv import load_dotenv
import os

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "CBU FastAPI SaaS"
    ENV: str = "development"
    REQUEST_TIMEOUT: int = 15

    ODOO_BASE_URL: str
    ODOO_DB: str
    ODOO_UID: int
    ODOO_API_KEY: str

    API_KEY: str

    # CORS (auto parse dari env string)
    CORS_ORIGINS: List[str] = ["https://cekat.ai"]


settings = Settings()
