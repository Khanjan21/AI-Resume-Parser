"""Application settings, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    PROJECT_NAME: str = "AI Resume Screening Platform"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- Postgres ---
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "resume"
    POSTGRES_PASSWORD: str = "resume"
    POSTGRES_DB: str = "resume_screening"

    # --- Storage ---
    STORAGE_DIR: Path = Field(default=BACKEND_DIR / "storage")
    MAX_UPLOAD_SIZE_MB: int = 10
    MAX_BULK_UPLOAD_FILES: int = 50

    # --- Behaviour flags ---
    SEED_ON_STARTUP: bool = True
    RUN_MIGRATIONS_ON_STARTUP: bool = False

    # --- CORS ---
    # NoDecode stops pydantic-settings from JSON-parsing the raw env value, so
    # the validator below can accept a plain comma-separated string.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a JSON array, a comma-separated string, or an actual list."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                import json

                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("STORAGE_DIR", mode="after")
    @classmethod
    def _absolute_storage(cls, value: Path) -> Path:
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()

    # --- Derived ---
    @property
    def database_url(self) -> str:
        """Async driver URL used by the app and Alembic."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_database_url(self) -> str:
        """Sync driver URL, handy for tooling that cannot await."""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def resume_dir(self) -> Path:
        return self.STORAGE_DIR / "resumes"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
