"""Parse prompts, query the persistent index, rank and stream results."""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.config import Settings
from app.logging_config import get_logger, search_id_var
from app.models.events import (
    EventType,
    intent_parsed_data,
    products_added_data,
    ranking_completed_data,
    retailer_completed_data,
    retailer_started_data,
    search_completed_data,
    search_started_data,
)
from app.models.intent import SearchIntent
from app.models.product import RetailerStatus, SearchResult, utcnow
from app.services.cache import SearchCache
from app.services.catalogue import Catalogue
from app.services.dedupe import group_products
from app.services.event_bus import EventBroker, SearchEventStream
from app.services.nlp.parser import IntentParser
from app.services.ranking import rank_groups

log = get_logger(__name__)


@dataclass
class SearchHandle:
    search_id: str
    query: str


class SearchAnalyticsSink:
    async def record_search(self, payload: Dict[str, Any]) -> None:
        return None


class SearchEngine:
    def __init__(
        self,
        settings: Settings,
        catalogue: Catalogue,
        parser: IntentParser,
        cache: SearchCache,
        broker: EventBroker,
        analytics: Optional[SearchAnalyticsSink] = None,
    ):
        self._settings = settings
        self._catalogue = catalogue
        self._parser = parser
        self._cache = cache
        self._broker = broker
        self._analytics = analytics or SearchAnalyticsSink()
        self._tasks: set = set()

    async def start_search(self, query: str) -> SearchHandle:
        search_id = uuid.uuid4().hex
        stream = self._broker.create(search_id)
        task = asyncio.create_task(self._execute(search_id, query, stream))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return SearchHandle(search_id, query)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _read_index(self, intent: SearchIntent):
        products = await self._catalogue.search(intent)
        groups = rank_groups(
            group_products(products), intent, limit=self._settings.search_max_results
        )
        states = await self._catalogue.source_states()
        statuses = []
        warnings = []
        for key, retailer in self._catalogue.retailers.items():
            state = states.get(key)
            status = RetailerStatus(
                key=key,
                name=retailer.name,
                state="completed",
                product_count=sum(p.retailer == key for p in products),
            )
            if state is None or state.last_success is None:
                status.state = "skipped"
                status.error = (
                    "First collection is pending" if not state or not state.error else state.error
                )
                warnings.append(f"{retailer.name}: no inventory has been collected yet.")
            elif state.error:
                warnings.append(
                    f"{retailer.name}: its latest refresh failed; showing unexpired inventory."
                )
            statuses.append(status)
        if any(p.freshness == "stale" for p in products):
            warnings.append(
                "Some prices need refreshing. Confirm price and availability at the retailer."
            )
        if not products and not await self._catalogue.active_offer_count():
            warnings.append(
                "The catalogue is being collected or its inventory has expired. "
                "Please try again after the next refresh."
            )
        updated_at = min((p.retrieved_at for p in products), default=None)
        return groups, statuses, warnings, updated_at

    async def get_snapshot(self, search_id: str) -> Optional[Dict[str, Any]]:
        snapshot = await self._cache.get_search_snapshot(search_id)
        if snapshot is None:
            stream = self._broker.get(search_id)
            snapshot = dict(stream.snapshot) if stream and stream.snapshot else None
        if snapshot is None or not snapshot.get("intent"):
            return snapshot
        # Re-query to honour deletions, changed prices and expiry on reconnect.
        intent = SearchIntent.model_validate(snapshot["intent"])
        groups, statuses, warnings, updated_at = await self._read_index(intent)
        snapshot.update(
            groups=[g.model_dump(mode="json") for g in groups],
            retailers=[r.model_dump() for r in statuses],
            total_products=sum(g.offer_count for g in groups),
            results_updated_at=updated_at.isoformat() if updated_at else None,
            warnings=list(snapshot.get("parse_warnings", [])) + warnings,
            status="partial" if any(r.state == "skipped" for r in statuses) else "completed",
        )
        return snapshot

    async def _execute(self, search_id: str, query: str, stream: SearchEventStream) -> None:
        search_id_var.set(search_id)
        began = time.perf_counter()
        statuses = [
            RetailerStatus(key=r.key, name=r.name) for r in self._catalogue.retailers.values()
        ]
        try:
            stream.publish(EventType.SEARCH_STARTED, search_started_data(query, "index", statuses))
            intent, parser, parse_ms, parse_warnings = await self._resolve_intent(query)
            intent = await self._catalogue.recognise_brands(query, intent)
            stream.publish(
                EventType.INTENT_PARSED,
                intent_parsed_data(intent.model_dump(mode="json"), parser, parse_ms, statuses),
            )
            for status in statuses:
                status.state = "running"
                stream.publish(EventType.RETAILER_STARTED, retailer_started_data(status))
            groups, statuses, warnings, updated_at = await self._read_index(intent)
            for status in statuses:
                stream.publish(EventType.RETAILER_COMPLETED, retailer_completed_data(status))
            warnings = parse_warnings + warnings
            total = sum(g.offer_count for g in groups)
            status = "partial" if any(r.state == "skipped" for r in statuses) else "completed"
            result = SearchResult(
                search_id=search_id,
                query=query,
                intent=intent.model_dump(mode="json"),
                groups=groups,
                retailers=statuses,
                status=status,
                cache_state="index",
                total_products=total,
                completed_at=utcnow(),
                results_updated_at=updated_at,
                warnings=warnings,
            )
            payload = result.model_dump(mode="json")
            payload.update(parser=parser, parse_warnings=parse_warnings)
            stream.snapshot = payload
            await self._cache.set_search_snapshot(search_id, payload)
            stream.publish(
                EventType.PRODUCTS_ADDED,
                products_added_data(groups, total, source="index", results_updated_at=updated_at),
            )
            stream.publish(EventType.RANKING_COMPLETED, ranking_completed_data(groups, total))
            stream.publish(
                EventType.SEARCH_COMPLETED,
                search_completed_data(
                    status=status,
                    cache_state="index",
                    total_products=total,
                    group_count=len(groups),
                    retailers=statuses,
                    warnings=warnings,
                    results_updated_at=updated_at,
                    duration_ms=int((time.perf_counter() - began) * 1000),
                ),
            )
            stream.close()
            try:
                await self._analytics.record_search(
                    {
                        "search_id": search_id,
                        "query": query,
                        "intent_fingerprint": intent.fingerprint(),
                        "intent": intent.model_dump(mode="json"),
                        "status": status,
                        "cache_state": "index",
                        "result_count": total,
                        "group_count": len(groups),
                        "duration_ms": int((time.perf_counter() - began) * 1000),
                    }
                )
            except Exception:
                log.exception("search.analytics_failed")
        except asyncio.CancelledError:
            stream.close()
            raise
        except Exception:
            log.exception("search.failed")
            failure = SearchResult(
                search_id=search_id,
                query=query,
                intent={},
                status="failed",
                completed_at=utcnow(),
                warnings=["Search is temporarily unavailable. Please try again."],
            ).model_dump(mode="json")
            stream.snapshot = failure
            await self._cache.set_search_snapshot(search_id, failure)
            stream.publish(
                EventType.SEARCH_COMPLETED,
                search_completed_data(
                    status="failed",
                    cache_state="index",
                    total_products=0,
                    group_count=0,
                    retailers=statuses,
                    warnings=["Search is temporarily unavailable. Please try again."],
                    results_updated_at=None,
                    duration_ms=int((time.perf_counter() - began) * 1000),
                ),
            )
            stream.close()

    async def _resolve_intent(self, query: str) -> Tuple[SearchIntent, str, int, List[str]]:
        query_hash = hashlib.sha256(query.strip().lower().encode()).hexdigest()[:32]
        cached = await self._cache.get_intent(query_hash)
        if cached:
            try:
                return (
                    SearchIntent.model_validate(cached["intent"]),
                    cached["parser"],
                    0,
                    cached.get("warnings", []),
                )
            except (ValueError, KeyError):
                pass
        outcome = await self._parser.parse(query)
        await self._cache.set_intent(
            query_hash,
            {
                "intent": outcome.intent.model_dump(mode="json"),
                "parser": outcome.parser,
                "warnings": outcome.warnings,
            },
        )
        return outcome.intent, outcome.parser, outcome.duration_ms, outcome.warnings
