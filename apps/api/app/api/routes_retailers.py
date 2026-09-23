"""Retailer coverage and the health of its persistent inventory."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.deps import AppContext, get_context
from app.sources.registry import load_retailers

router = APIRouter(prefix="/api", tags=["retailers"])


@router.get("/retailers", summary="List reviewed retailers and inventory coverage")
async def list_retailers(
    include_health: bool = False, context: AppContext = Depends(get_context)
) -> list:
    states = await context.catalogue.source_states()
    output = []
    for retailer in load_retailers():
        state = states.get(retailer.key)
        enabled = retailer.key in context.catalogue.retailers
        output.append(
            {
                "key": retailer.key,
                "name": retailer.name,
                "type": "index",
                "website_url": retailer.website_url,
                "menswear_url": retailer.menswear_url,
                "ships_to": [],
                "currency": retailer.ingestion.currency if retailer.ingestion else None,
                "enabled": enabled,
                "requires_permission": False,
                "website_verification": retailer.website_verification,
                "data_access": retailer.data_access,
                "state": state.state
                if state
                else "blocked"
                if retailer.data_access.get("status") == "blocked"
                else "not_configured",
                "offer_count": state.offer_count if state else 0,
                "last_success": datetime.fromtimestamp(state.last_success, timezone.utc).isoformat()
                if state and state.last_success
                else None,
                "healthy": bool(state and state.state == "ok") if include_health else None,
                "message": state.error if state else "Product ingestion is not configured",
                "latency_ms": None,
            }
        )
    return output
