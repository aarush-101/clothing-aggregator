"""Server-Sent Event payloads emitted during a search."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.product import ProductGroup, RetailerStatus, utcnow


class EventType(str, Enum):
    SEARCH_STARTED = "search_started"
    INTENT_PARSED = "intent_parsed"
    RETAILER_STARTED = "retailer_started"
    RETAILER_COMPLETED = "retailer_completed"
    RETAILER_FAILED = "retailer_failed"
    PRODUCTS_ADDED = "products_added"
    RANKING_COMPLETED = "ranking_completed"
    SEARCH_COMPLETED = "search_completed"


class SearchEvent(BaseModel):
    """One frame on the SSE stream.

    ``sequence`` doubles as the SSE ``id:`` field so a reconnecting browser can
    resume with ``Last-Event-ID`` instead of replaying the whole search.
    """

    sequence: int
    type: EventType
    search_id: str
    timestamp: datetime = Field(default_factory=utcnow)
    data: Dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        payload = {
            "sequence": self.sequence,
            "type": self.type.value,
            "search_id": self.search_id,
            "timestamp": self.timestamp.isoformat(),
            **self.data,
        }
        body = json.dumps(payload, default=str, separators=(",", ":"))
        return f"id: {self.sequence}\nevent: {self.type.value}\ndata: {body}\n\n"


# --------------------------------------------------------------------------
# Typed payload helpers. Each returns the ``data`` dict for a SearchEvent so
# the shapes stay in one place and match `docs/api.md`.
# --------------------------------------------------------------------------


def search_started_data(query: str, cache_state: str, retailers: List[RetailerStatus]) -> Dict[str, Any]:
    return {
        "query": query,
        "cache_state": cache_state,
        "retailers": [r.model_dump() for r in retailers],
    }


def intent_parsed_data(
    intent: Dict[str, Any],
    parser: str,
    duration_ms: int,
    retailers: List[RetailerStatus],
) -> Dict[str, Any]:
    return {
        "intent": intent,
        "parser": parser,
        "duration_ms": duration_ms,
        "retailers": [r.model_dump() for r in retailers],
    }


def retailer_started_data(status: RetailerStatus) -> Dict[str, Any]:
    return {"retailer": status.model_dump()}


def retailer_completed_data(status: RetailerStatus) -> Dict[str, Any]:
    return {"retailer": status.model_dump()}


def retailer_failed_data(status: RetailerStatus, error: str) -> Dict[str, Any]:
    return {"retailer": status.model_dump(), "error": error}


def products_added_data(
    groups: List[ProductGroup],
    total_products: int,
    source: str,
    results_updated_at: Optional[datetime],
) -> Dict[str, Any]:
    return {
        "groups": [g.model_dump(mode="json") for g in groups],
        "total_products": total_products,
        "source": source,  # live | cache
        "results_updated_at": results_updated_at.isoformat() if results_updated_at else None,
    }


def ranking_completed_data(groups: List[ProductGroup], total_products: int) -> Dict[str, Any]:
    return {
        "groups": [g.model_dump(mode="json") for g in groups],
        "total_products": total_products,
        "group_count": len(groups),
    }


def search_completed_data(
    status: str,
    cache_state: str,
    total_products: int,
    group_count: int,
    retailers: List[RetailerStatus],
    warnings: List[str],
    results_updated_at: Optional[datetime],
    duration_ms: int,
) -> Dict[str, Any]:
    return {
        "status": status,
        "cache_state": cache_state,
        "total_products": total_products,
        "group_count": group_count,
        "retailers": [r.model_dump() for r in retailers],
        "warnings": warnings,
        "results_updated_at": results_updated_at.isoformat() if results_updated_at else None,
        "duration_ms": duration_ms,
    }
