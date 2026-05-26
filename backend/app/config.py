from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "OATI Manuales API"
    debug: bool = False
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://oati:oati@localhost:5432/oati_manuales"
    sync_database_url: str = "postgresql+psycopg://oati:oati@localhost:5432/oati_manuales"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str | None = None
    s3_access_key: str = "minio"
    s3_secret_key: str = "minio123"
    s3_bucket_assets: str = "oati-manuales-assets"
    s3_region: str = "us-east-1"

    cors_origins: str = "http://localhost:4200"

    # Origen para resolver imágenes relativas / descargas cuando no hay Request (p.ej. PDF en servidor).
    asset_origin: str = "http://127.0.0.1:8000"

    # Si WeasyPrint falla en guías rápidas: orden por defecto Chrome → Edge Playwright env PLAYWRIGHT_PDF_CHANNEL (= chrome | msedge | chromium).
    playwright_pdf_channel: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
