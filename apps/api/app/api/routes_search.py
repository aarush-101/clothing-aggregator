"""Search endpoints: create a search, stream its progress, read its snapshot."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from app.deps import AppContext, get_context
from app.logging_config import get_logger, search_id_var
from app.models.api import SearchCreatedResponse, SearchRequest
from app.models.events import EventType, SearchEvent
from app.services.nlp.sanitise import QueryValidationError, normalise_query
from app.services.ratelimit import rate_limit_headers
from app.services.ranking import DEFAULT_WEIGHTS

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["search"])

# How long to wait before sending an SSE comment to keep proxies from closing
# an idle connection.
HEARTBEAT_SECONDS = 15.0


@router.post(
    "/search",
    response_model=SearchCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a search job",
)
async def create_search(
    payload: SearchRequest,
    request: Request,
    response: Response,
    context: AppContext = Depends(get_context),
) -> SearchCreatedResponse:
    limit = await context.rate_limiter.check_search(request)
    for key, value in rate_limit_headers(limit).items():
        response.headers[key] = value
    if not limit.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many searches. Please wait a moment and try again.",
            headers={"Retry-After": str(limit.retry_after)},
        )

    try:
        query = normalise_query(
            payload.query,
            max_length=context.settings.search_max_query_length,
            min_length=context.settings.search_min_query_length,
        )
    except QueryValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    handle = await context.engine.start_search(query)
    log.info("search.created", query_length=len(query))
    return SearchCreatedResponse(
        search_id=handle.search_id,
        query=query,
        events_url=f"/api/search/{handle.search_id}/events",
        snapshot_url=f"/api/search/{handle.search_id}",
    )


@router.get(
    "/search/{search_id}/events",
    summary="Stream search progress as Server-Sent Events",
    response_class=StreamingResponse,
)
async def stream_search_events(
    search_id: str,
    request: Request,
    context: AppContext = Depends(get_context),
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    search_id_var.set(search_id)
    from_sequence = _parse_last_event_id(last_event_id)
    stream = context.broker.get(search_id)

    if stream is None:
        # The in-process stream has expired (or this instance never had it).
        # Replay the persisted snapshot so a reconnecting client still ends up
        # in a correct final state.
        snapshot = await context.engine.get_snapshot(search_id)
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown or expired search"
            )
        return StreamingResponse(
            _replay_snapshot(search_id, snapshot),
            media_type="text/event-stream",
            headers=_sse_headers(),
        )

    async def event_generator() -> AsyncIterator[str]:
        sent = from_sequence
        async with stream.subscribe(from_sequence) as (backlog, queue):
            for event in backlog:
                if event.sequence > sent:
                    sent = event.sequence
                    yield event.to_sse()
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if event is None:
                    break
                if event.sequence <= sent:
                    continue
                sent = event.sequence
                yield event.to_sse()

    return StreamingResponse(
        event_generator(), media_type="text/event-stream", headers=_sse_headers()
    )


@router.get("/search/{search_id}", summary="Read the current state of a search")
async def get_search(search_id: str, context: AppContext = Depends(get_context)) -> dict:
    snapshot = await context.engine.get_snapshot(search_id)
    if snapshot is None:
        stream = context.broker.get(search_id)
        if stream is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown or expired search"
            )
        return {"search_id": search_id, "status": "running", "groups": [], "retailers": []}
    return snapshot


@router.get("/ranking", summary="Explain how results are ranked")
async def get_ranking_explanation() -> dict:
    return {
        "weights": DEFAULT_WEIGHTS.as_dict(),
        "notes": [
            "Only the dimensions present in your query are scored; the rest are "
            "excluded and their weight is redistributed.",
            "Scoring is deterministic - no model call is involved in ranking.",
            "Offers for the same garment are grouped and the cheapest available "
            "option (including shipping) is shown first.",
        ],
    }


def _sse_headers() -> dict:
    return {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        # Tells nginx-style proxies not to buffer the stream.
        "X-Accel-Buffering": "no",
    }


def _parse_last_event_id(value: Optional[str]) -> int:
    try:
        return max(0, int(value)) if value else 0
    except (TypeError, ValueError):
        return 0


async def _replay_snapshot(search_id: str, snapshot: dict) -> AsyncIterator[str]:
    """Emit a minimal, correct event sequence from a stored snapshot."""
    groups = snapshot.get("groups", [])
    total = snapshot.get("total_products", 0)
    retailers = snapshot.get("retailers", [])
    updated = snapshot.get("results_updated_at")

    frames = [
        (EventType.INTENT_PARSED, {
            "intent": snapshot.get("intent", {}),
            "parser": "snapshot",
            "duration_ms": 0,
            "retailers": retailers,
        }),
        (EventType.PRODUCTS_ADDED, {
            "groups": groups,
            "total_products": total,
            "source": "cache",
            "results_updated_at": updated,
        }),
        (EventType.RANKING_COMPLETED, {
            "groups": groups,
            "total_products": total,
            "group_count": len(groups),
        }),
        (EventType.SEARCH_COMPLETED, {
            "status": snapshot.get("status", "completed"),
            "cache_state": snapshot.get("cache_state", "fresh"),
            "total_products": total,
            "group_count": len(groups),
            "retailers": retailers,
            "warnings": snapshot.get("warnings", []),
            "results_updated_at": updated,
            "duration_ms": 0,
        }),
    ]
    for index, (event_type, data) in enumerate(frames, start=1):
        yield SearchEvent(
            sequence=index, type=event_type, search_id=search_id, data=data
        ).to_sse()
