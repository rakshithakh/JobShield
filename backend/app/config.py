"""Application settings, read from environment variables (see .env.example)."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./jobsentinel_dev.db"
    cors_origins: str = "http://localhost:5173"

    input_text_retention_days: int = Field(default=0, ge=0, le=365)
    max_text_chars: int = 20000
    max_upload_bytes: int = 5 * 1024 * 1024
    max_pdf_pages: int = 30
    rate_limit_per_minute: int = 20
    rate_limit_backend: str = "memory"   # memory | database
    trusted_proxy_count: int = 0  # number of reverse proxies in front (Render = 1) for X-Forwarded-For

    url_fetch_timeout_seconds: float = 8.0
    url_fetch_max_bytes: int = 1_000_000
    url_fetch_max_redirects: int = 3

    mca_api_key: str = ""
    mca_resource_id: str = "4dbe5667-7b6b-41d7-82af-211562424d9a"
    mca_timeout_seconds: float = 6.0
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "in"
    adzuna_salary_benchmarks: bool = True   # use Adzuna salary data when keys are set (falls back to the unsourced table)
    adzuna_timeout_seconds: float = 6.0
    distilbert_model_dir: str = ""

    model_artifact_dir: str = str(BASE_DIR / "ml" / "artifacts")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("database_url")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        # Render/Heroku style URLs use the bare "postgres://" or "postgresql://" scheme.
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+psycopg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
