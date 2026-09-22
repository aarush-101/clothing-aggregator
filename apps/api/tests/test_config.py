"""Environment validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import FeedConnectorConfig, Settings


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


def test_stale_ceiling_must_not_be_below_the_fresh_window():
    with pytest.raises(ValidationError):
        Settings(**base(cache_fresh_seconds=3600, cache_max_stale_seconds=60))


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


def test_affiliate_feeds_are_validated():
    settings = Settings(
        **base(
            affiliate_feeds=(
                '[{"key":"demo","display_name":"Demo","url":"https://f.example/x.json",'
                '"format":"json","items_path":"items"}]'
            )
        )
    )
    feeds = settings.feed_configs
    assert len(feeds) == 1 and feeds[0].key == "demo"


def test_malformed_affiliate_feeds_raise_a_clear_error():
    with pytest.raises(ValueError):
        _ = Settings(**base(affiliate_feeds="not json")).feed_configs


def test_feed_format_must_be_json_or_xml():
    with pytest.raises(ValidationError):
        FeedConnectorConfig(key="k", display_name="K", url="https://x.test", format="csv")


def test_feed_key_must_be_a_safe_slug():
    with pytest.raises(ValidationError):
        FeedConnectorConfig(key="Bad Key!", display_name="K", url="https://x.test")


def test_enabled_connector_keys_are_parsed():
    settings = Settings(**base(enabled_connectors="mock:*, sample_feed ,"))
    assert settings.enabled_connector_keys == ["mock:*", "sample_feed"]
