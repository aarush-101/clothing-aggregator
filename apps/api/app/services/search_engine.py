"""Search orchestration.

One search is one background task that:

1. parses the query into a :class:`SearchIntent` (LLM, or deterministic)
2. decides which connectors are relevant
3. serves cached results immediately when we have them
4. queries the relevant connectors concurrently, with per-retailer timeouts,
   bounded concurrency and bounded retries
5. filters, de-duplicates and ranks after every retailer responds
6. streams each step to the browser as a Server-Sent Event
7. caches the completed result

Retailers are only ever contacted because a user searched. There is no
scheduled crawl and no preloaded catalogue.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config import Settings
from app.connectors.base import ConnectorError, ConnectorPermissionError, RetailerConnector
from app.connectors.registry import ConnectorRegistry
from app.logging_config import get_logger, search_id_var
from app.models.events import (
    EventType,
    intent_parsed_data,
    products_added_data,
    ranking_completed_data,
    retailer_completed_data,
    retailer_failed_data,
    retailer_started_data,
    search_completed_data,
    search_started_data,
)
from app.models.intent import SearchIntent
from app.models.product import Product, ProductGroup, RetailerStatus, SearchResult
from app.services.cache import FRESH, MISS, STALE, SearchCache
from app.services.dedupe import group_products
from app.services.event_bus import EventBroker, SearchEventStream
from app.services.nlp.parser import IntentParser
from app.services.ranking import DEFAULT_WEIGHTS, filter_products, rank_groups

log = get_logger(__name__)

REFRESHED = "refreshed"
COALESCED = "coalesced"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SearchHandle:
    search_id: str
    query: str


class SearchAnalyticsSink:
    """Hook for persistence. The default implementation does nothing."""

    async def record_search(self, payload: Dict[str, Any]) -> None:
        return None

    async def record_connector_result(self, payload: Dict[str, Any]) -> None:
        return None


class SearchEngine:
    def __init__(
        self,
        settings: Settings,
        registry: ConnectorRegistry,
        parser: IntentParser,
        cache: SearchCache,
        broker: EventBroker,
        analytics: Optional[SearchAnalyticsSink] = None,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._parser = parser
        self._cache = cache
        self._broker = broker
        self._analytics = analytics or SearchAnalyticsSink()
        self._tasks: set = set()

    # ------------------------------------------------------------------ API
    async def start_search(self, query: str) -> SearchHandle:
        """Create a search job and return immediately with its id."""
        search_id = uuid.uuid4().hex
        stream = self._broker.create(search_id)
        task = asyncio.create_task(self._execute(search_id, query, stream))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return SearchHandle(search_id=search_id, query=query)

    async def get_snapshot(self, search_id: str) -> Optional[Dict[str, Any]]:
        return await self._cache.get_search_snapshot(search_id)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    # ------------------------------------------------------------- lifecycle
    async def _execute(self, search_id: str, query: str, stream: SearchEventStream) -> None:
        search_id_var.set(search_id)
        started = time.perf_counter()
        warnings: List[str] = []

        statuses: Dict[str, RetailerStatus] = {
            connector.key: RetailerStatus(key=connector.key, name=connector.display_name)
            for connector in self._registry.all()
        }

        try:
            stream.publish(
                EventType.SEARCH_STARTED,
                search_started_data(query, MISS, list(statuses.values())),
            )

            intent, parser_name, parse_ms, parse_warnings = await self._resolve_intent(query)
            warnings.extend(parse_warnings)

            selected = self._registry.for_intent(intent)
            selected_keys = {connector.key for connector in selected}
            for key, status in statuses.items():
                if key not in selected_keys:
                    status.state = "skipped"

            stream.publish(
                EventType.INTENT_PARSED,
                intent_parsed_data(
                    intent.model_dump(mode="json"),
                    parser_name,
                    parse_ms,
                    list(statuses.values()),
                ),
            )

            fingerprint = intent.fingerprint()
            cache_state = MISS
            cached_groups: List[ProductGroup] = []

            cached = await self._cache.get_results(fingerprint)
            if cached is not None:
                cached_groups = self._groups_from_payload(cached.payload)
                cached_statuses = self._statuses_from_payload(cached.payload) or list(
                    statuses.values()
                )
                stream.publish(
                    EventType.PRODUCTS_ADDED,
                    products_added_data(
                        cached_groups,
                        sum(g.offer_count for g in cached_groups),
                        source="cache",
                        results_updated_at=cached.stored_at,
                    ),
                )
                if cached.state == FRESH:
                    await self._complete(
                        search_id=search_id,
                        stream=stream,
                        query=query,
                        intent=intent,
                        groups=cached_groups,
                        statuses=cached_statuses,
                        cache_state=FRESH,
                        warnings=warnings,
                        started=started,
                        results_updated_at=cached.stored_at,
                        persist=False,
                        fingerprint=fingerprint,
                    )
                    return
                cache_state = STALE
                warnings.append("Showing recent results while we refresh them.")

            if not selected:
                warnings.append("No retailers matched this search.")
                await self._complete(
                    search_id=search_id,
                    stream=stream,
                    query=query,
                    intent=intent,
                    groups=cached_groups,
                    statuses=list(statuses.values()),
                    cache_state=cache_state,
                    warnings=warnings,
                    started=started,
                    results_updated_at=utcnow(),
                    persist=False,
                    fingerprint=fingerprint,
                )
                return

            lock_token = await self._cache.acquire_lock(fingerprint)
            if lock_token is None:
                coalesced = await self._await_inflight(fingerprint)
                if coalesced is not None:
                    groups = self._groups_from_payload(coalesced.payload)
                    stream.publish(
                        EventType.PRODUCTS_ADDED,
                        products_added_data(
                            groups,
                            sum(g.offer_count for g in groups),
                            source="cache",
                            results_updated_at=coalesced.stored_at,
                        ),
                    )
                    await self._complete(
                        search_id=search_id,
                        stream=stream,
                        query=query,
                        intent=intent,
                        groups=groups,
                        statuses=self._statuses_from_payload(coalesced.payload)
                        or list(statuses.values()),
                        cache_state=COALESCED,
                        warnings=warnings,
                        started=started,
                        results_updated_at=coalesced.stored_at,
                        persist=False,
                        fingerprint=fingerprint,
                    )
                    return
                log.info("search.lock_wait_timeout", fingerprint=fingerprint)

            try:
                products = await self._fan_out(intent, selected, statuses, stream)
            finally:
                if lock_token:
                    await self._cache.release_lock(fingerprint, lock_token)

            groups = rank_groups(
                group_products(products),
                intent,
                DEFAULT_WEIGHTS,
                limit=self._settings.search_max_results,
            )
            if not groups and cached_groups:
                # A refresh that returns nothing should not blank the page.
                groups = cached_groups
                warnings.append("Refresh returned no results; showing the previous set.")

            failed = [s for s in statuses.values() if s.state == "failed"]
            for status in failed:
                warnings.append(f"{status.name} could not be searched ({status.error}).")

            await self._complete(
                search_id=search_id,
                stream=stream,
                query=query,
                intent=intent,
                groups=groups,
                statuses=list(statuses.values()),
                cache_state=REFRESHED if cache_state == STALE else MISS,
                warnings=warnings,
                started=started,
                results_updated_at=utcnow(),
                persist=True,
                fingerprint=fingerprint,
                partial=bool(failed),
            )
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            stream.close()
            raise
        except Exception as exc:
            log.exception("search.failed", error=str(exc))
            stream.publish(
                EventType.SEARCH_COMPLETED,
                search_completed_data(
                    status="failed",
                    cache_state=MISS,
                    total_products=0,
                    group_count=0,
                    retailers=list(statuses.values()),
                    warnings=["The search could not be completed. Please try again."],
                    results_updated_at=None,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                ),
            )
            stream.close()

    # ---------------------------------------------------------------- intent
    async def _resolve_intent(self, query: str) -> Tuple[SearchIntent, str, int, List[str]]:
        """Parse the query, reusing a cached interpretation when we have one.

        The parser that produced the intent and any warnings it raised are
        cached alongside it: "this was interpreted without AI assistance" stays
        true on the second search, and the UI keeps telling the truth.
        """
        query_hash = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()[:32]
        cached = await self._cache.get_intent(query_hash)
        if cached:
            try:
                envelope = cached if "intent" in cached else {"intent": cached}
                intent = SearchIntent.model_validate(envelope["intent"])
                return (
                    intent,
                    str(envelope.get("parser") or "cache"),
                    0,
                    list(envelope.get("warnings") or []),
                )
            except Exception:
                log.warning("intent.cache_invalid", query_hash=query_hash)

        outcome = await self._parser.parse(query)
        await self._cache.set_intent(
            query_hash,
            {
                "intent": outcome.intent.model_dump(mode="json"),
                "parser": outcome.parser,
                "warnings": outcome.warnings,
            },
        )
        return (outcome.intent, outcome.parser, outcome.duration_ms, outcome.warnings)

    # --------------------------------------------------------------- fan-out
    async def _fan_out(
        self,
        intent: SearchIntent,
        connectors: List[RetailerConnector],
        statuses: Dict[str, RetailerStatus],
        stream: SearchEventStream,
    ) -> List[Product]:
        semaphore = asyncio.Semaphore(self._settings.search_max_concurrent_retailers)
        accumulated: List[Product] = []
        published: Dict[str, Tuple[int, float]] = {}

        async def run_one(connector: RetailerConnector) -> None:
            status = statuses[connector.key]
            status.state = "running"
            stream.publish(EventType.RETAILER_STARTED, retailer_started_data(status))
            began = time.perf_counter()

            async with semaphore:
                products, error = await self._search_with_retries(connector, intent, status)

            status.duration_ms = int((time.perf_counter() - began) * 1000)

            if error is not None:
                status.state = "failed"
                status.error = error
                stream.publish(EventType.RETAILER_FAILED, retailer_failed_data(status, error))
                log.warning(
                    "retailer.failed",
                    retailer=connector.key,
                    error=error,
                    attempts=status.attempts,
                )
            else:
                relevant = filter_products(products, intent)
                status.state = "completed"
                status.product_count = len(relevant)
                stream.publish(EventType.RETAILER_COMPLETED, retailer_completed_data(status))
                log.info(
                    "retailer.completed",
                    retailer=connector.key,
                    returned=len(products),
                    kept=len(relevant),
                    duration_ms=status.duration_ms,
                )
                if relevant:
                    accumulated.extend(relevant)
                    # No awaits below: the regroup/rank/publish block runs to
                    # completion before another retailer's callback can start.
                    ranked = rank_groups(
                        group_products(accumulated),
                        intent,
                        DEFAULT_WEIGHTS,
                        limit=self._settings.search_max_results,
                    )
                    changed = [
                        group
                        for group in ranked
                        if published.get(group.group_id) != (group.offer_count, group.match_score)
                    ]
                    for group in ranked:
                        published[group.group_id] = (group.offer_count, group.match_score)
                    if changed:
                        stream.publish(
                            EventType.PRODUCTS_ADDED,
                            products_added_data(
                                changed,
                                sum(g.offer_count for g in ranked),
                                source="live",
                                results_updated_at=utcnow(),
                            ),
                        )

            await self._record_connector_result(connector, status)

        tasks = [asyncio.create_task(run_one(connector)) for connector in connectors]
        _, pending = await asyncio.wait(tasks, timeout=self._settings.search_total_timeout_seconds)
        if pending:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for status in statuses.values():
                if status.state in {"pending", "running"}:
                    status.state = "failed"
                    status.error = "search timed out"
                    stream.publish(
                        EventType.RETAILER_FAILED,
                        retailer_failed_data(status, status.error),
                    )

        return accumulated

    async def _search_with_retries(
        self, connector: RetailerConnector, intent: SearchIntent, status: RetailerStatus
    ) -> Tuple[List[Product], Optional[str]]:
        attempts = max(1, self._settings.search_retailer_max_attempts)
        last_error = "unknown error"

        for attempt in range(1, attempts + 1):
            status.attempts = attempt
            try:
                products = await asyncio.wait_for(
                    connector.search(intent),
                    timeout=self._settings.search_retailer_timeout_seconds,
                )
                return (list(products), None)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                last_error = (
                    f"timed out after {self._settings.search_retailer_timeout_seconds:.0f}s"
                )
            except ConnectorPermissionError as exc:
                return ([], str(exc))  # configuration problem - retrying cannot help
            except ConnectorError as exc:
                last_error = str(exc)
            except Exception as exc:
                log.exception("retailer.unexpected_error", retailer=connector.key)
                last_error = f"unexpected error: {type(exc).__name__}"

            if attempt < attempts:
                backoff = self._settings.search_retailer_backoff_seconds * (2 ** (attempt - 1))
                await asyncio.sleep(backoff + random.uniform(0, 0.15))

        return ([], last_error)

    # ----------------------------------------------------------- completion
    async def _complete(
        self,
        *,
        search_id: str,
        stream: SearchEventStream,
        query: str,
        intent: SearchIntent,
        groups: List[ProductGroup],
        statuses: List[RetailerStatus],
        cache_state: str,
        warnings: List[str],
        started: float,
        results_updated_at: Optional[datetime],
        persist: bool,
        fingerprint: str,
        partial: bool = False,
    ) -> None:
        total_products = sum(group.offer_count for group in groups)
        duration_ms = int((time.perf_counter() - started) * 1000)
        status = "partial" if partial else "completed"

        payload = {
            "query": query,
            "intent": intent.model_dump(mode="json"),
            "groups": [group.model_dump(mode="json") for group in groups],
            "retailers": [item.model_dump() for item in statuses],
        }
        if persist:
            await self._cache.set_results(fingerprint, payload)

        snapshot = SearchResult(
            search_id=search_id,
            intent=intent.model_dump(mode="json"),
            query=query,
            groups=groups,
            retailers=statuses,
            status=status,
            cache_state=cache_state,
            total_products=total_products,
            completed_at=utcnow(),
            results_updated_at=results_updated_at,
            warnings=warnings,
        )
        await self._cache.set_search_snapshot(search_id, snapshot.model_dump(mode="json"))

        # Emitted from here so cached, coalesced and live searches all produce
        # the same event sequence and the client needs only one code path.
        stream.publish(
            EventType.RANKING_COMPLETED,
            ranking_completed_data(groups, total_products),
        )
        stream.publish(
            EventType.SEARCH_COMPLETED,
            search_completed_data(
                status=status,
                cache_state=cache_state,
                total_products=total_products,
                group_count=len(groups),
                retailers=statuses,
                warnings=warnings,
                results_updated_at=results_updated_at,
                duration_ms=duration_ms,
            ),
        )
        stream.close()

        log.info(
            "search.completed",
            status=status,
            cache_state=cache_state,
            groups=len(groups),
            products=total_products,
            duration_ms=duration_ms,
        )
        await self._record_search(
            {
                "search_id": search_id,
                "query": query,
                "intent_fingerprint": fingerprint,
                "intent": intent.model_dump(mode="json"),
                "status": status,
                "cache_state": cache_state,
                "result_count": total_products,
                "group_count": len(groups),
                "duration_ms": duration_ms,
            }
        )

    # -------------------------------------------------------------- helpers
    async def _await_inflight(self, fingerprint: str):
        """Wait briefly for the search holding the lock to publish its result."""
        deadline = time.monotonic() + min(self._settings.cache_lock_timeout_seconds, 20)
        while time.monotonic() < deadline:
            await asyncio.sleep(0.25)
            cached = await self._cache.get_results(fingerprint)
            if cached is not None and cached.state == FRESH:
                return cached
        return None

    @staticmethod
    def _groups_from_payload(payload: Dict[str, Any]) -> List[ProductGroup]:
        groups: List[ProductGroup] = []
        for raw in payload.get("groups", []) or []:
            try:
                groups.append(ProductGroup.model_validate(raw))
            except Exception:
                continue
        return groups

    @staticmethod
    def _statuses_from_payload(payload: Dict[str, Any]) -> List[RetailerStatus]:
        statuses: List[RetailerStatus] = []
        for raw in payload.get("retailers", []) or []:
            try:
                statuses.append(RetailerStatus.model_validate(raw))
            except Exception:
                continue
        return statuses

    async def _record_search(self, payload: Dict[str, Any]) -> None:
        try:
            await self._analytics.record_search(payload)
        except Exception as exc:
            log.warning("analytics.record_search_failed", error=str(exc))

    async def _record_connector_result(
        self, connector: RetailerConnector, status: RetailerStatus
    ) -> None:
        try:
            await self._analytics.record_connector_result(
                {
                    "connector_key": connector.key,
                    "connector_name": connector.display_name,
                    "healthy": status.state == "completed",
                    "state": status.state,
                    "duration_ms": status.duration_ms,
                    "product_count": status.product_count,
                    "error": status.error,
                    "attempts": status.attempts,
                }
            )
        except Exception as exc:
            log.warning("analytics.record_connector_failed", error=str(exc))
