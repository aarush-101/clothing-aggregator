"""Application context and FastAPI dependencies.

Everything with a lifecycle (HTTP clients, Redis, the database engine) is
created once at startup and torn down once at shutdown, and reached through
``request.app.state.context``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.connectors.registry import ConnectorRegistry
from app.db.repository import AccountRepository, DatabaseAnalyticsSink
from app.db.session import Database, build_database
from app.logging_config import get_logger
from app.services.cache import SearchCache, build_cache_backend
from app.services.event_bus import EventBroker
from app.services.nlp.parser import IntentParser
from app.services.ratelimit import RateLimiter, optional_bearer_token
from app.services.search_engine import SearchEngine

log = get_logger(__name__)


@dataclass
class AppContext:
    settings: Settings
    cache: SearchCache
    registry: ConnectorRegistry
    parser: IntentParser
    broker: EventBroker
    engine: SearchEngine
    rate_limiter: RateLimiter
    accounts: AccountRepository
    database: Optional[Database]

    @classmethod
    def create(cls, settings: Optional[Settings] = None) -> "AppContext":
        settings = settings or get_settings()
        cache = SearchCache(settings, build_cache_backend(settings))
        registry = ConnectorRegistry(settings)
        parser = IntentParser(settings)
        broker = EventBroker()
        database = build_database(settings)
        engine = SearchEngine(
            settings=settings,
            registry=registry,
            parser=parser,
            cache=cache,
            broker=broker,
            analytics=DatabaseAnalyticsSink(database),
        )
        return cls(
            settings=settings,
            cache=cache,
            registry=registry,
            parser=parser,
            broker=broker,
            engine=engine,
            rate_limiter=RateLimiter(settings, cache),
            accounts=AccountRepository(database),
            database=database,
        )

    async def shutdown(self) -> None:
        await self.engine.shutdown()
        await self.registry.aclose()
        await self.parser.aclose()
        await self.cache.aclose()
        if self.database is not None:
            await self.database.dispose()


def get_context(request: Request) -> AppContext:
    context: Optional[AppContext] = getattr(request.app.state, "context", None)
    if context is None:  # pragma: no cover - only if lifespan did not run
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application is not ready",
        )
    return context


def get_search_engine(context: AppContext = Depends(get_context)) -> SearchEngine:
    return context.engine


def get_accounts(context: AppContext = Depends(get_context)) -> AccountRepository:
    return context.accounts


def get_rate_limiter(context: AppContext = Depends(get_context)) -> RateLimiter:
    return context.rate_limiter


def get_app_settings(context: AppContext = Depends(get_context)) -> Settings:
    return context.settings


async def get_optional_user(
    request: Request, accounts: AccountRepository = Depends(get_accounts)
):
    """Resolve the bearer token to a user, or None.

    Anonymous use is a first-class path: every account feature is additive.
    """
    token = optional_bearer_token(request)
    if not token or not accounts.available:
        return None
    try:
        return await accounts.get_user_by_token(token)
    except Exception as exc:
        log.warning("auth.lookup_failed", error=str(exc))
        return None


async def require_user(user=Depends(get_optional_user)):
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to use this feature.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
