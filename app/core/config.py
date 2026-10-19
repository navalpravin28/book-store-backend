from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    PROJECT_NAME: str = "BookStore API"
    ENVIRONMENT: str = "development"  # development | production
    API_PREFIX: str = "/api/v1"
    APP_TIMEZONE: str = "Asia/Kolkata"  # used for "today" / daily analytics buckets

    # ---- Mongo ----
    MONGO_URI: str
    MONGO_DB_NAME: str = "bookstore"

    # ---- JWT ----
    JWT_SECRET_KEY: str = Field(min_length=8)
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "bookstore-api"
    JWT_AUDIENCE: str = "bookstore-clients"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ---- First admin (seeded on startup if no admin exists) ----
    ADMIN_NAME: str = "Store Admin"
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD: str | None = None

    # ---- Brute-force protection ----
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_MINUTES: int = 15

    # ---- Network hardening ----
    CORS_ORIGINS: str = "http://localhost:3000"
    ALLOWED_HOSTS: str = "localhost,127.0.0.1,testserver"
    MAX_REQUEST_BODY_MB: int = 6

    # ---- Business limits ----
    MAX_IMAGE_SIZE_MB: int = 2
    MAX_CSV_SIZE_MB: int = 2
    MAX_CSV_ROWS: int = 1000
    MAX_ACTIVE_ADS_PER_USER: int = 5
    LOW_STOCK_THRESHOLD: int = 5

    @model_validator(mode="after")
    def _production_guards(self):
        if self.ENVIRONMENT == "production":
            if "*" in self.CORS_ORIGINS or "*" in self.ALLOWED_HOSTS:
                raise ValueError("Wildcard CORS_ORIGINS / ALLOWED_HOSTS not allowed in production")
            if "change-this" in self.JWT_SECRET_KEY.lower():
                raise ValueError("Set a real JWT_SECRET_KEY in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]

    @property
    def UPLOAD_ROOT(self) -> Path:
        return BASE_DIR / "app" / "static" / "uploads"

    @property
    def STATIC_ROOT(self) -> Path:
        return BASE_DIR / "app" / "static"


settings = Settings()
