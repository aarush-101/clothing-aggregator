"""Search caching.

Two caches, both keyed by content rather than by user:

``intent:<sha256(query)>``     parsed SearchIntent, so repeating a query never
                               pays for the LLM twice.
``results:<intent fingerprint>`` completed search results, so two shoppers who
                               ask for the same thing in different words share
                               one set of retailer requests.

Freshness policy (see ``docs/architecture.md``):

* younger than ``CACHE_FRESH_SECONDS`` (30 min) - served immediately, no refresh
* older, but younger than ``CACHE_MAX_STALE_SECONDS`` (24 h) - served
  immediately **and** refreshed in the background, because a user just asked
* older than that, or missing - a live search runs

Retailer data is never refreshed on a timer. A user searching is the only
event that causes an outbound retailer request.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.config import Settings
from app.logging_config import get_logger

log = get_logger(__name__)

FRESH = "fresh"
STALE = "stale"
MISS = "miss"


class CacheBackend:
    """Minimal async key/value interface shared by Redis and the memory store."""

    async def get(self, key: str) -> Optional[str]:
        raise NotImplementedError

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def incr(self, key: str, ttl_seconds: int) -> int:
        raise NotImplementedError

    async def set_if_absent(self, key: str, value: str, ttl_seconds: int) -> bool:
        raise NotImplementedError

    async def ping(self) -> bool:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


class MemoryCacheBackend(CacheBackend):
    """In-process fallback.

    Perfectly usable for local development and single-instance deployments;
    it is *not* shared between processes, so a multi-instance deployment must
    configure Redis (enforced for ``APP_ENV=production`` in ``config.py``).
    """

    def __init__(self) -> None:
        self._store: Dict[str, Tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    def _expired(self, expires_at: float) -> bool:
        return expires_at > 0 and expires_at < time.time()

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if self._expired(expires_at):
                self._store.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        async with self._lock:
            self._store[key] = (value, time.time() + ttl_seconds if ttl_seconds else 0)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def incr(self, key: str, ttl_seconds: int) -> int:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None or self._expired(entry[1]):
                self._store[key] = ("1", time.time() + ttl_seconds)
                return 1
            value, expires_at = entry
            count = int(value) + 1
            self._store[key] = (str(count), expires_at)
            return count

    async def set_if_absent(self, key: str, value: str, ttl_seconds: int) -> bool:
        async with self._lock:
            entry = self._store.get(key)
            if entry is not None and not self._expired(entry[1]):
                return False
            self._store[key] = (value, time.time() + ttl_seconds)
            return True

    async def ping(self) -> bool:
        return True


class RedisCacheBackend(CacheBackend):
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis  # imported lazily so Redis stays optional

        self._redis = redis.from_url(
            url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            health_check_interval=30,
        )

    async def get(self, key: str) -> Optional[str]:
        return await self._redis.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        await self._redis.set(key, value, ex=ttl_seconds or None)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def incr(self, key: str, ttl_seconds: int) -> int:
        pipeline = self._redis.pipeline()
        pipeline.incr(key)
        pipeline.expire(key, ttl_seconds, nx=True)
        results = await pipeline.execute()
        return int(results[0])

    async def set_if_absent(self, key: str, value: str, ttl_seconds: int) -> bool:
        return bool(await self._redis.set(key, value, ex=ttl_seconds, nx=True))

    async def ping(self) -> bool:
        return bool(await self._redis.ping())

    async def aclose(self) -> None:
        await self._redis.aclose()


def build_cache_backend(settings: Settings) -> CacheBackend:
    if not settings.redis_url:
        log.warning("cache.using_memory_backend", reason="REDIS_URL not set")
        return MemoryCacheBackend()
    try:
        return RedisCacheBackend(settings.redis_url)
    except Exception as exc:  # pragma: no cover - import/URL failure
        log.error("cache.redis_unavailable", error=str(exc))
        return MemoryCacheBackend()


@dataclass
class CachedResults:
    payload: Dict[str, Any]
    stored_at: datetime
    state: str

    @property
    def age_seconds(self) -> int:
        return int((datetime.now(timezone.utc) - self.stored_at).total_seconds())


class SearchCache:
    """Domain wrapper around a :class:`CacheBackend`."""

    def __init__(self, settings: Settings, backend: CacheBackend) -> None:
        self._settings = settings
        self._backend = backend
        self._namespace = settings.cache_namespace

    # ------------------------------------------------------------------ keys
    def _key(self, kind: str, identifier: str) -> str:
        return f"{self._namespace}:{kind}:v1:{identifier}"

    # ---------------------------------------------------------------- intent
    async def get_intent(self, query_hash: str) -> Optional[Dict[str, Any]]:
        raw = await self._safe_get(self._key("intent", query_hash))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set_intent(self, query_hash: str, intent_payload: Dict[str, Any]) -> None:
        await self._safe_set(
            self._key("intent", query_hash),
            json.dumps(intent_payload, default=str),
            self._settings.cache_intent_ttl_seconds,
        )

    # --------------------------------------------------------------- results
    async def get_results(self, fingerprint: str) -> Optional[CachedResults]:
        raw = await self._safe_get(self._key("results", fingerprint))
        if not raw:
            return None
        try:
            envelope = json.loads(raw)
            stored_at = datetime.fromisoformat(envelope["stored_at"])
        except (json.JSONDecodeError, KeyError, ValueError):
            return None
        if stored_at.tzinfo is None:
            stored_at = stored_at.replace(tzinfo=timezone.utc)

        age = (datetime.now(timezone.utc) - stored_at).total_seconds()
        if age > self._settings.cache_max_stale_seconds:
            return None
        state = FRESH if age <= self._settings.cache_fresh_seconds else STALE
        return CachedResults(payload=envelope["payload"], stored_at=stored_at, state=state)

    async def set_results(self, fingerprint: str, payload: Dict[str, Any]) -> None:
        envelope = {
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        await self._safe_set(
            self._key("results", fingerprint),
            json.dumps(envelope, default=str),
            self._settings.cache_max_stale_seconds,
        )

    async def invalidate_results(self, fingerprint: str) -> None:
        await self._backend.delete(self._key("results", fingerprint))

    # ------------------------------------------------------------ search jobs
    async def get_search_snapshot(self, search_id: str) -> Optional[Dict[str, Any]]:
        raw = await self._safe_get(self._key("search", search_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set_search_snapshot(self, search_id: str, payload: Dict[str, Any]) -> None:
        await self._safe_set(
            self._key("search", search_id),
            json.dumps(payload, default=str),
            self._settings.cache_max_stale_seconds,
        )

    # ------------------------------------------------------------------ lock
    async def acquire_lock(self, fingerprint: str) -> Optional[str]:
        """Prevent two identical searches from hitting retailers at once."""
        token = uuid.uuid4().hex
        acquired = await self._backend.set_if_absent(
            self._key("lock", fingerprint), token, self._settings.cache_lock_timeout_seconds
        )
        return token if acquired else None

    async def release_lock(self, fingerprint: str, token: str) -> None:
        key = self._key("lock", fingerprint)
        current = await self._safe_get(key)
        if current == token:
            await self._backend.delete(key)

    # ------------------------------------------------------------ rate limits
    async def increment_rate_counter(self, identifier: str, window_seconds: int) -> int:
        window = int(time.time() // window_seconds)
        key = self._key("rate", f"{identifier}:{window}")
        try:
            return await self._backend.incr(key, window_seconds)
        except Exception as exc:
            log.warning("cache.rate_counter_failed", error=str(exc))
            return 0  # fail open rather than lock everyone out

    async def healthy(self) -> bool:
        try:
            return await self._backend.ping()
        except Exception:
            return False

    # ---------------------------------------------------------------- helpers
    async def _safe_get(self, key: str) -> Optional[str]:
        try:
            return await self._backend.get(key)
        except Exception as exc:
            log.warning("cache.get_failed", key=key, error=str(exc))
            return None

    async def _safe_set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            await self._backend.set(key, value, ttl_seconds)
        except Exception as exc:
            log.warning("cache.set_failed", key=key, error=str(exc))

    async def aclose(self) -> None:
        await self._backend.aclose()
