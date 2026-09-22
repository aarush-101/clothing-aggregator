"""Fixed-window rate limiting backed by the cache.

Two independent budgets per client: a broad request budget and a much tighter
search budget, because a search fans out to every retailer and is the only
expensive endpoint.

The limiter fails **open**: if the cache is unavailable the site keeps working
rather than locking everyone out. Abuse protection that takes the product down
is not protection.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Optional

from fastapi import Request

from app.config import Settings
from app.logging_config import get_logger
from app.services.cache import SearchCache

log = get_logger(__name__)

WINDOW_SECONDS = 60


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


def client_identifier(request: Request) -> str:
    """Best-effort client identity.

    ``X-Forwarded-For`` is trusted because the service is expected to run
    behind a single managed proxy (Railway / Render / Fly / Vercel). If you
    deploy without one, strip the header at the edge.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    client = request.client
    return client.host if client else "unknown"


class RateLimiter:
    def __init__(self, settings: Settings, cache: SearchCache) -> None:
        self._settings = settings
        self._cache = cache

    async def check(self, identifier: str, bucket: str, limit: int) -> RateLimitResult:
        if not self._settings.rate_limit_enabled or limit <= 0:
            return RateLimitResult(True, limit, limit, 0)
        count = await self._cache.increment_rate_counter(f"{bucket}:{identifier}", WINDOW_SECONDS)
        if count <= 0:  # cache unavailable - fail open
            return RateLimitResult(True, limit, limit, 0)
        remaining = max(0, limit - count)
        return RateLimitResult(count <= limit, limit, remaining, WINDOW_SECONDS)

    async def check_request(self, request: Request) -> RateLimitResult:
        return await self.check(
            client_identifier(request), "req", self._settings.rate_limit_requests_per_minute
        )

    async def check_search(self, request: Request) -> RateLimitResult:
        return await self.check(
            client_identifier(request), "search", self._settings.rate_limit_searches_per_minute
        )


def rate_limit_headers(result: RateLimitResult) -> dict:
    headers = {
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(result.remaining),
    }
    if not result.allowed:
        headers["Retry-After"] = str(result.retry_after)
    return headers


def optional_bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        return token or None
    return None
