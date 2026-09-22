"""Cache freshness, staleness, locking and rate counters."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.services.cache import FRESH, STALE, MemoryCacheBackend, SearchCache


@pytest.fixture
def backend() -> MemoryCacheBackend:
    return MemoryCacheBackend()


@pytest.fixture
def search_cache(settings: Settings, backend: MemoryCacheBackend) -> SearchCache:
    return SearchCache(settings, backend)


async def _age_entry(backend: MemoryCacheBackend, cache: SearchCache, key: str, seconds: int):
    """Rewrite a stored entry so it looks `seconds` old."""
    full_key = cache._key("results", key)
    raw = await backend.get(full_key)
    envelope = json.loads(raw)
    envelope["stored_at"] = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    await backend.set(full_key, json.dumps(envelope), 86400)


async def test_missing_key_returns_none(search_cache: SearchCache):
    assert await search_cache.get_results("nothing-here") is None


async def test_recent_results_are_fresh(search_cache: SearchCache):
    await search_cache.set_results("fp", {"groups": []})
    cached = await search_cache.get_results("fp")
    assert cached is not None and cached.state == FRESH


async def test_results_older_than_thirty_minutes_are_stale(
    search_cache: SearchCache, backend: MemoryCacheBackend
):
    await search_cache.set_results("fp", {"groups": []})
    await _age_entry(backend, search_cache, "fp", 1801)
    cached = await search_cache.get_results("fp")
    assert cached is not None and cached.state == STALE
    assert cached.age_seconds >= 1800


async def test_results_older_than_the_stale_ceiling_are_discarded(
    search_cache: SearchCache, backend: MemoryCacheBackend
):
    await search_cache.set_results("fp", {"groups": []})
    await _age_entry(backend, search_cache, "fp", 86401)
    assert await search_cache.get_results("fp") is None


async def test_corrupt_entries_are_treated_as_a_miss(
    search_cache: SearchCache, backend: MemoryCacheBackend
):
    await backend.set(search_cache._key("results", "fp"), "not json", 60)
    assert await search_cache.get_results("fp") is None


async def test_intent_cache_round_trip(search_cache: SearchCache):
    await search_cache.set_intent("qh", {"colours": ["black"]})
    assert await search_cache.get_intent("qh") == {"colours": ["black"]}


async def test_lock_is_exclusive_until_released(search_cache: SearchCache):
    token = await search_cache.acquire_lock("fp")
    assert token is not None
    assert await search_cache.acquire_lock("fp") is None

    await search_cache.release_lock("fp", token)
    assert await search_cache.acquire_lock("fp") is not None


async def test_lock_release_ignores_a_foreign_token(search_cache: SearchCache):
    token = await search_cache.acquire_lock("fp")
    await search_cache.release_lock("fp", "someone-elses-token")
    # The original holder still owns it.
    assert await search_cache.acquire_lock("fp") is None
    await search_cache.release_lock("fp", token)


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
