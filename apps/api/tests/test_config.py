"""Environment validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def base(**overrides) -> dict:
    values = {"app_env": "development", "redis_url": "", "database_url": ""}
    values.update(overrides)
    return values


def test_blank_optional_urls_become_none():
    settings = Settings(**base())
    assert settings.redis_url is None
    assert settings.database_url is None


def test_postgres_urls_are_upgraded_to_the_async_driver():
    assert Settings(**base(database_url="postgres://u:p@host:5432/db")).database_url.startswith(
        "postgresql+asyncpg://"
    )
    assert Settings(**base(database_url="postgresql://u:p@host:5432/db")).database_url.startswith(
        "postgresql+asyncpg://"
    )


def test_production_requires_redis_and_a_database():
    with pytest.raises(ValidationError):
        Settings(**base(app_env="production"))


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError):
        Settings(
            **base(
                app_env="production",
                redis_url="redis://localhost:6379/0",
                database_url="postgresql+asyncpg://u:p@h/db",
                cors_allow_origins="*",
            )
        )


def test_invalid_log_level_is_rejected():
    with pytest.raises(ValidationError):
        Settings(**base(log_level="chatty"))


def test_cors_origins_are_parsed_from_a_comma_separated_list():
    settings = Settings(**base(cors_allow_origins="http://a.test, http://b.test ,"))
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_affiliate_templates_must_be_http_urls():
    settings = Settings(**base(affiliate_templates='{"shop": "javascript:alert(1)"}'))
    with pytest.raises(ValueError):
        _ = settings.affiliate_template_map


def test_catalogue_expiry_must_exceed_stale_threshold():
    with pytest.raises(ValidationError):
        Settings(**base(catalogue_stale_seconds=3600, catalogue_expire_seconds=3600))


def test_background_ingestion_is_enabled_by_default():
    assert Settings(_env_file=None, ingestion_enabled=True).ingestion_enabled
