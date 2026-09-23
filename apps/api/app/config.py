"""Application settings.

Every value is read from the environment (or a local ``.env``) and validated by
Pydantic at import time, so a misconfigured deployment fails fast and loudly
instead of half-working.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, List, Optional

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Later files win in pydantic-settings, so the app-local .env
        # overrides the shared one at the repository root.
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core ---------------------------------------------------------------
    app_env: str = "development"
    app_name: str = "clothing-aggregator-api"
    log_level: str = "INFO"
    log_format: str = "console"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Raw comma-separated string; use `cors_origins` for the parsed list.
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Infrastructure -----------------------------------------------------
    database_url: Optional[str] = None
    redis_url: Optional[str] = None

    # --- Anthropic ----------------------------------------------------------
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-opus-5"
    anthropic_timeout_seconds: float = 12.0
    anthropic_max_tokens: int = 4000

    # --- Search -------------------------------------------------------------
    search_max_query_length: int = 400
    search_min_query_length: int = 2
    search_max_results: int = 120

    # --- Cache --------------------------------------------------------------
    cache_snapshot_ttl_seconds: int = 3600
    cache_intent_ttl_seconds: int = 86400
    cache_namespace: str = "ca"

    # --- Rate limiting ------------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_searches_per_minute: int = 20
    rate_limit_requests_per_minute: int = 120

    # --- Persistent catalogue ------------------------------------------------
    ingestion_enabled: bool = True
    ingestion_poll_seconds: int = Field(default=60, ge=1)
    # Minimum gap between any two retailer requests, across all sources.
    ingestion_request_interval_seconds: float = Field(default=2.0, ge=0)
    catalogue_stale_seconds: int = Field(default=43200, ge=60)
    catalogue_expire_seconds: int = Field(default=172800, ge=60)

    # ------------------------------------------------------------------ utils
    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"unsupported LOG_LEVEL: {value}")
        return level

    @field_validator("log_format")
    @classmethod
    def _valid_log_format(cls, value: str) -> str:
        fmt = value.strip().lower()
        if fmt not in {"console", "json"}:
            raise ValueError("LOG_FORMAT must be 'console' or 'json'")
        return fmt

    @field_validator("app_env")
    @classmethod
    def _valid_env(cls, value: str) -> str:
        env = value.strip().lower()
        if env not in {"development", "test", "staging", "production"}:
            raise ValueError("APP_ENV must be development, test, staging or production")
        return env

    @field_validator("database_url", "redis_url", "anthropic_api_key", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def _async_database_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value.startswith("postgres://"):
            # Heroku/Neon style URL - upgrade to the async driver.
            value = "postgresql+asyncpg://" + value[len("postgres://") :]
        elif value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value[len("postgresql://") :]
        return value

    @field_validator("search_max_query_length")
    @classmethod
    def _sane_query_length(cls, value: int) -> int:
        if not 20 <= value <= 2000:
            raise ValueError("SEARCH_MAX_QUERY_LENGTH must be between 20 and 2000")
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> Settings:
        if self.catalogue_expire_seconds <= self.catalogue_stale_seconds:
            raise ValueError("CATALOGUE_EXPIRE_SECONDS must exceed CATALOGUE_STALE_SECONDS")
        if self.app_env == "production":
            if not self.redis_url:
                raise ValueError("REDIS_URL is required in production")
            if not self.database_url:
                raise ValueError("DATABASE_URL is required in production")
            if "*" in self.cors_allow_origins:
                raise ValueError("Wildcard CORS origins are not allowed in production")
        return self

    # --------------------------------------------------------------- derived
    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def anthropic_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    try:
        return Settings()
    except ValidationError as exc:  # pragma: no cover - startup failure path
        raise RuntimeError(f"Invalid environment configuration:\n{exc}") from exc


def reset_settings_cache() -> None:
    """Testing helper - drop the cached settings so env changes take effect."""
    get_settings.cache_clear()
