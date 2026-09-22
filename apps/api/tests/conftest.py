"""Shared pytest fixtures.

Tests run against the in-process cache and a temporary SQLite database, so the
whole suite works with no Docker, no Redis, no Postgres and no API keys.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import tempfile

import pytest

TEST_DB_PATH = pathlib.Path(tempfile.gettempdir()) / "clothing_aggregator_test.sqlite3"

# Must be set before app.config is imported anywhere.
os.environ.update(
    {
        "APP_ENV": "test",
        "REDIS_URL": "",
        "DATABASE_URL": f"sqlite+aiosqlite:///{TEST_DB_PATH}",
        "ANTHROPIC_API_KEY": "",
        "MOCK_LATENCY_MULTIPLIER": "0",
        "MOCK_INCLUDE_FLAKY_RETAILER": "false",
        "RATE_LIMIT_ENABLED": "false",
        "LOG_LEVEL": "WARNING",
        "ENABLED_CONNECTORS": "mock:*,sample_feed",
        # The suite must never reach the public internet: real storefronts are
        # exercised by a separate, explicitly opt-in live check.
        "ENABLE_SHOPIFY_CONNECTORS": "false",
    }
)

from app.config import Settings, reset_settings_cache  # noqa: E402
from app.connectors.registry import ConnectorRegistry  # noqa: E402
from app.db.session import Database  # noqa: E402
from app.services.cache import MemoryCacheBackend, SearchCache  # noqa: E402
from app.services.event_bus import EventBroker  # noqa: E402
from app.services.nlp.parser import IntentParser  # noqa: E402
from app.services.search_engine import SearchEngine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def prepared_database():
    TEST_DB_PATH.unlink(missing_ok=True)

    async def _create() -> None:
        database = Database(f"sqlite+aiosqlite:///{TEST_DB_PATH}")
        await database.create_all()
        await database.dispose()

    asyncio.run(_create())
    yield
    TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture
def settings() -> Settings:
    reset_settings_cache()
    return Settings()


@pytest.fixture
def cache(settings: Settings) -> SearchCache:
    return SearchCache(settings, MemoryCacheBackend())


@pytest.fixture
def registry(settings: Settings) -> ConnectorRegistry:
    return ConnectorRegistry(settings)


@pytest.fixture
def broker() -> EventBroker:
    return EventBroker()


@pytest.fixture
def engine(settings, registry, cache, broker) -> SearchEngine:
    return SearchEngine(
        settings=settings,
        registry=registry,
        parser=IntentParser(settings),
        cache=cache,
        broker=broker,
    )


@pytest.fixture
def api_client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client


async def drain_events(broker: EventBroker, search_id: str, timeout: float = 20.0):
    """Collect every event for a search until it completes."""
    stream = broker.get(search_id)
    assert stream is not None
    async with stream.subscribe(0) as (backlog, queue):
        events = list(backlog)
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=timeout)
            if event is None:
                break
            events.append(event)
    return events
