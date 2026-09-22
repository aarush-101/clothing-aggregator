"""Connector inventory and health."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from app.deps import AppContext, get_context
from app.models.api import RetailerSummary

router = APIRouter(prefix="/api", tags=["retailers"])


def _connector_type(connector) -> str:
    name = type(connector).__name__
    if "Mock" in name:
        return "mock"
    if "Feed" in name:
        return "feed"
    if "Html" in name:
        return "html"
    return "api"


@router.get("/retailers", response_model=List[RetailerSummary], summary="List active connectors")
async def list_retailers(
    include_health: bool = False, context: AppContext = Depends(get_context)
) -> List[RetailerSummary]:
    health_by_key = {}
    if include_health:
        health_by_key = {item.key: item for item in await context.registry.health()}

    summaries: List[RetailerSummary] = []
    for connector in context.registry.all():
        health = health_by_key.get(connector.key)
        summaries.append(
            RetailerSummary(
                key=connector.key,
                name=connector.display_name,
                type=_connector_type(connector),
                ships_to=list(connector.ships_to),
                currency=connector.currency,
                requires_permission=connector.requires_permission,
                healthy=health.healthy if health else None,
                message=health.message if health else None,
                latency_ms=health.latency_ms if health else None,
            )
        )
    return summaries
