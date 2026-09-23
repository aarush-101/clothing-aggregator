"""Health and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.deps import AppContext, get_context
from app.models.api import HealthResponse

router = APIRouter(tags=["health"])

VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(context: AppContext = Depends(get_context)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=VERSION,
        environment=context.settings.app_env,
        checks={"connectors": len(context.catalogue.retailers)},
    )


@router.get("/health/ready", response_model=HealthResponse, summary="Readiness probe")
async def readiness(
    response: Response, context: AppContext = Depends(get_context)
) -> HealthResponse:
    cache_ok = await context.cache.healthy()
    database_ok = await context.database.healthy() if context.database else None
    connectors = context.catalogue.retailers
    inventory = await context.catalogue.active_offer_count() if database_ok else 0

    ready = cache_ok and database_ok and bool(connectors)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if ready else "degraded",
        version=VERSION,
        environment=context.settings.app_env,
        checks={
            "cache": "ok" if cache_ok else "unavailable",
            "database": (
                "not configured"
                if database_ok is None
                else ("ok" if database_ok else "unavailable")
            ),
            "connectors": len(connectors),
            "indexed_variant_offers": inventory,
            "inventory": "available" if inventory else "empty",
            "active_searches": context.broker.active_count,
            "query_parser": "anthropic" if context.settings.anthropic_enabled else "deterministic",
        },
    )
