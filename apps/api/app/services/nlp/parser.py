"""Query -> SearchIntent orchestration.

Chooses between the Anthropic parser and the deterministic one, and guarantees
that a :class:`SearchIntent` always comes back for any query that passed
validation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from app.config import Settings
from app.logging_config import get_logger
from app.models.intent import SearchIntent
from app.services.nlp.anthropic_parser import AnthropicIntentParser, IntentParseError
from app.services.nlp.fallback_parser import parse_query as deterministic_parse
from app.services.nlp.sanitise import normalise_query, should_bypass_llm

log = get_logger(__name__)


@dataclass
class ParseOutcome:
    intent: SearchIntent
    parser: str
    duration_ms: int
    warnings: List[str] = field(default_factory=list)


class IntentParser:
    def __init__(self, settings: Settings, llm: Optional[AnthropicIntentParser] = None) -> None:
        self._settings = settings
        self._llm = llm if llm is not None else AnthropicIntentParser(settings)

    async def parse(self, raw_query: str) -> ParseOutcome:
        """Parse ``raw_query``; raises QueryValidationError for unusable input."""
        started = time.perf_counter()
        query = normalise_query(
            raw_query,
            max_length=self._settings.search_max_query_length,
            min_length=self._settings.search_min_query_length,
        )

        warnings: List[str] = []
        deterministic = deterministic_parse(query)

        bypass, triggers = should_bypass_llm(query)
        if bypass:
            log.warning("intent.llm_bypassed", reason="prompt_injection", triggers=triggers)
            warnings.append("This query was interpreted without AI assistance.")
            return self._finish(deterministic, "deterministic", started, warnings)

        if not self._llm.available:
            return self._finish(deterministic, "deterministic", started, warnings)

        try:
            intent = await self._llm.parse(query)
        except IntentParseError as exc:
            log.warning("intent.llm_failed", error=str(exc))
            warnings.append("AI query understanding was unavailable; used keyword parsing.")
            return self._finish(deterministic, "deterministic", started, warnings)
        except Exception as exc:  # defensive: never fail a search on the parser
            log.exception("intent.llm_unexpected_error", error=str(exc))
            warnings.append("AI query understanding was unavailable; used keyword parsing.")
            return self._finish(deterministic, "deterministic", started, warnings)

        # Emptiness is judged on the model's own output, before backfilling -
        # otherwise a backfilled price would disguise an empty interpretation.
        if not self._has_signal(intent) and self._has_signal(deterministic):
            log.info("intent.llm_empty_using_fallback")
            return self._finish(deterministic, "deterministic", started, warnings)

        intent = self._backfill(intent, deterministic)
        return self._finish(intent, "anthropic", started, warnings)

    @staticmethod
    def _has_signal(intent: SearchIntent) -> bool:
        return bool(
            intent.product_categories
            or intent.colours
            or intent.materials
            or intent.fits
            or intent.brands
            or intent.styles
            or intent.occasion
            or intent.maximum_price is not None
            or intent.additional_keywords
        )

    @staticmethod
    def _backfill(intent: SearchIntent, deterministic: SearchIntent) -> SearchIntent:
        """Fill objective fields the model left blank.

        Prices and sizes are stated explicitly in the sentence, so the regex
        parser is authoritative when the model omits them.
        """
        updates = {}
        if intent.maximum_price is None and deterministic.maximum_price is not None:
            updates["maximum_price"] = deterministic.maximum_price
        if intent.minimum_price is None and deterministic.minimum_price is not None:
            updates["minimum_price"] = deterministic.minimum_price
        if intent.size is None and deterministic.size is not None:
            updates["size"] = deterministic.size
        if not updates:
            return intent
        return intent.model_copy(update=updates)

    @staticmethod
    def _finish(
        intent: SearchIntent, parser: str, started: float, warnings: List[str]
    ) -> ParseOutcome:
        duration_ms = int((time.perf_counter() - started) * 1000)
        log.info(
            "intent.parsed",
            parser=parser,
            duration_ms=duration_ms,
            categories=intent.product_categories,
            max_price=float(intent.maximum_price) if intent.maximum_price else None,
        )
        return ParseOutcome(
            intent=intent, parser=parser, duration_ms=duration_ms, warnings=warnings
        )

    async def aclose(self) -> None:
        await self._llm.aclose()
