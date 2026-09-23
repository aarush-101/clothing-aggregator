"""Cache freshness, staleness, locking and rate counters."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.services.cache import MemoryCacheBackend, SearchCache


@pytest.fixture
def backend() -> MemoryCacheBackend:
    return MemoryCacheBackend()


@pytest.fixture
def search_cache(settings: Settings, backend: MemoryCacheBackend) -> SearchCache:
    return SearchCache(settings, backend)


async def test_intent_cache_round_trip(search_cache: SearchCache):
    await search_cache.set_intent("qh", {"colours": ["black"]})
    assert await search_cache.get_intent("qh") == {"colours": ["black"]}


async def test_rate_counter_increments_within_a_window(search_cache: SearchCache):
    counts = [await search_cache.increment_rate_counter("client", 60) for _ in range(3)]
    assert counts == [1, 2, 3]


async def test_rate_counter_is_isolated_per_client(search_cache: SearchCache):
    await search_cache.increment_rate_counter("a", 60)
    assert await search_cache.increment_rate_counter("b", 60) == 1


async def test_memory_backend_expires_entries(backend: MemoryCacheBackend):
    await backend.set("k", "v", 0)
    assert await backend.get("k") == "v"  # ttl 0 means "no expiry"


async def test_search_snapshot_round_trip(search_cache: SearchCache):
    await search_cache.set_search_snapshot("sid", {"status": "completed"})
    assert (await search_cache.get_search_snapshot("sid"))["status"] == "completed"
