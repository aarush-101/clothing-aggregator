"""In-process pub/sub for search progress events.

Each search gets a stream. Events are kept in order and retained briefly after
the search finishes, so a browser that reconnects with ``Last-Event-ID`` can
replay what it missed instead of restarting the search.

Scope: this broker is per-process. A multi-instance deployment needs either
sticky sessions or a Redis pub/sub implementation of the same interface - see
``docs/limitations.md``.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, List, Optional, Set, Tuple

from app.logging_config import get_logger
from app.models.events import EventType, SearchEvent

log = get_logger(__name__)

# How long a finished stream stays replayable.
RETENTION_SECONDS = 600
MAX_EVENTS_PER_SEARCH = 500
SUBSCRIBER_QUEUE_SIZE = 256


class SearchEventStream:
    """Ordered, replayable event log for one search."""

    def __init__(self, search_id: str) -> None:
        self.search_id = search_id
        self.events: List[SearchEvent] = []
        self.snapshot: Optional[dict] = None
        self.closed = False
        self.created_at = time.monotonic()
        self.finished_at: Optional[float] = None
        self._sequence = 0
        self._subscribers: Set[asyncio.Queue[Optional[SearchEvent]]] = set()

    def publish(self, event_type: EventType, data: dict) -> SearchEvent:
        self._sequence += 1
        event = SearchEvent(
            sequence=self._sequence,
            type=event_type,
            search_id=self.search_id,
            data=data,
        )
        self.events.append(event)
        if len(self.events) > MAX_EVENTS_PER_SEARCH:
            # Keep the tail; replay from an very old Last-Event-ID degrades to
            # "from the oldest retained event", which the client tolerates.
            self.events = self.events[-MAX_EVENTS_PER_SEARCH:]
        for queue in list(self._subscribers):
            self._offer(queue, event)
        return event

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.finished_at = time.monotonic()
        for queue in list(self._subscribers):
            self._offer(queue, None)

    @staticmethod
    def _offer(queue: asyncio.Queue[Optional[SearchEvent]], item: Optional[SearchEvent]) -> None:
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:  # pragma: no cover - a stalled client
            log.warning("events.subscriber_queue_full")

    @asynccontextmanager
    async def subscribe(
        self, from_sequence: int = 0
    ) -> AsyncIterator[Tuple[List[SearchEvent], asyncio.Queue[Optional[SearchEvent]]]]:
        """Yield (backlog, queue).

        The queue is registered *before* the backlog snapshot is taken, so no
        event can slip through the gap; duplicates are filtered by the caller
        using the monotonic sequence number.
        """
        queue: asyncio.Queue[Optional[SearchEvent]] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self._subscribers.add(queue)
        try:
            backlog = [event for event in self.events if event.sequence > from_sequence]
            if self.closed:
                self._offer(queue, None)
            yield (backlog, queue)
        finally:
            self._subscribers.discard(queue)

    @property
    def is_expired(self) -> bool:
        if self.finished_at is None:
            return False
        return (time.monotonic() - self.finished_at) > RETENTION_SECONDS


class EventBroker:
    def __init__(self) -> None:
        self._streams: Dict[str, SearchEventStream] = {}

    def create(self, search_id: str) -> SearchEventStream:
        self._evict_expired()
        stream = SearchEventStream(search_id)
        self._streams[search_id] = stream
        return stream

    def get(self, search_id: str) -> Optional[SearchEventStream]:
        stream = self._streams.get(search_id)
        if stream is not None and stream.is_expired:
            self._streams.pop(search_id, None)
            return None
        return stream

    def _evict_expired(self) -> None:
        for search_id in [sid for sid, s in self._streams.items() if s.is_expired]:
            self._streams.pop(search_id, None)

    @property
    def active_count(self) -> int:
        return sum(1 for stream in self._streams.values() if not stream.closed)
