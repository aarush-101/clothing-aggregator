"""Application settings.

Every value is read from the environment (or a local ``.env``) and validated by
Pydantic at import time, so a misconfigured deployment fails fast and loudly
instead of half-working.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SAFE_URL_SCHEMES = ("http://", "https://")


class FeedConnectorConfig(BaseSettings):
    """Declarative configuration for a generic affiliate feed connector."""

    model_config = SettingsConfigDict(extra="forbid")

    key: str
    display_name: str
    url: str
    format: str = "json"  # json | xml
    enabled: bool = True
    currency: str = "AUD"
    ships_to: List[str] = Field(default_factory=lambda: ["AU"])
    # Where the product records live inside the document.
    items_path: str = "products"  # dotted path (JSON) or element path (XML)
    # Maps our Product fields to the feed's own field names.
    field_map: Dict[str, str] = Field(default_factory=dict)
    # Static values merged into every normalised product.
    defaults: Dict[str, Any] = Field(default_factory=dict)
    headers: Dict[str, str] = Field(default_factory=dict)
    query_param: Optional[str] = None  # if set, the feed is searchable server-side
    timeout_seconds: float = 8.0
    max_items: int = 250

    @field_validator("format")
    @classmethod
    def _valid_format(cls, value: str) -> str:
        normalised = value.strip().lower()
        if normalised not in {"json", "xml"}:
            raise ValueError("feed format must be 'json' or 'xml'")
        return normalised

    @field_validator("key")
    @classmethod
    def _valid_key(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9_\-]{2,40}", value):
            raise ValueError("feed key must be lowercase alphanumeric with - or _")
        return value


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
    search_max_concurrent_retailers: int = 6
    search_retailer_timeout_seconds: float = 8.0
    search_total_timeout_seconds: float = 25.0
    search_retailer_max_attempts: int = 2
    search_retailer_backoff_seconds: float = 0.4
    search_max_results: int = 120

    # --- Cache --------------------------------------------------------------
    cache_fresh_seconds: int = 1800
    cache_max_stale_seconds: int = 86400
    cache_intent_ttl_seconds: int = 86400
    cache_lock_timeout_seconds: int = 30
    cache_namespace: str = "ca"

    # --- Rate limiting ------------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_searches_per_minute: int = 20
    rate_limit_requests_per_minute: int = 120

    # --- Connectors ---------------------------------------------------------
    enabled_connectors: str = "mock:*,sample_feed"
    mock_include_flaky_retailer: bool = False
    mock_latency_multiplier: float = 1.0
    affiliate_feeds: str = "[]"
    enable_shopify_connectors: bool = True
    # How long a store's published catalogue is reused before re-reading it.
    # Keeps repeat searches free for the retailer.
    shopify_catalogue_ttl_seconds: int = 1800
    # Optional allow-list of store keys; empty means "every enabled store".
    shopify_stores: str = ""
    enable_example_public_connector: bool = False
    example_public_api_base_url: str = "https://fakestoreapi.com"
    enable_html_connectors: bool = False

    # --- Affiliate links ----------------------------------------------------
    affiliate_subid_prefix: str = "ca"
    affiliate_templates: str = "{}"

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
        if self.cache_max_stale_seconds < self.cache_fresh_seconds:
            raise ValueError("CACHE_MAX_STALE_SECONDS must be >= CACHE_FRESH_SECONDS")
        if self.search_max_concurrent_retailers < 1:
            raise ValueError("SEARCH_MAX_CONCURRENT_RETAILERS must be >= 1")
        if self.search_retailer_timeout_seconds <= 0:
            raise ValueError("SEARCH_RETAILER_TIMEOUT_SECONDS must be > 0")
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
    def shopify_store_keys(self) -> List[str]:
        return [key.strip() for key in self.shopify_stores.split(",") if key.strip()]

    @property
    def enabled_connector_keys(self) -> List[str]:
        return [key.strip() for key in self.enabled_connectors.split(",") if key.strip()]

    @property
    def feed_configs(self) -> List[FeedConnectorConfig]:
        try:
            raw = json.loads(self.affiliate_feeds or "[]")
        except json.JSONDecodeError as exc:  # pragma: no cover - config error path
            raise ValueError(f"AFFILIATE_FEEDS is not valid JSON: {exc}") from exc
        if not isinstance(raw, list):
            raise ValueError("AFFILIATE_FEEDS must be a JSON array")
        return [FeedConnectorConfig(**item) for item in raw]

    @property
    def affiliate_template_map(self) -> Dict[str, str]:
        try:
            raw = json.loads(self.affiliate_templates or "{}")
        except json.JSONDecodeError as exc:  # pragma: no cover - config error path
            raise ValueError(f"AFFILIATE_TEMPLATES is not valid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError("AFFILIATE_TEMPLATES must be a JSON object")
        templates: Dict[str, str] = {}
        for retailer, template in raw.items():
            if not isinstance(template, str) or not template.startswith(_SAFE_URL_SCHEMES):
                raise ValueError(f"affiliate template for '{retailer}' must be an http(s) URL")
            templates[str(retailer)] = template
        return templates

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
