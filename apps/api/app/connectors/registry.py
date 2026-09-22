"""Builds the set of connectors this deployment should query.

Which connectors exist is a configuration decision (``ENABLED_CONNECTORS``),
not a code decision, so a deployment can run with only mocks, only real feeds,
or any mixture.
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

from app.config import Settings
from app.connectors.base import ConnectorHealth, RetailerConnector
from app.connectors.example_public import ExamplePublicApiConnector
from app.connectors.feed_connector import build_feed_connectors
from app.connectors.mock_retailer import build_mock_connectors
from app.logging_config import get_logger
from app.models.intent import SearchIntent

log = get_logger(__name__)

MOCK_WILDCARD = "mock:*"
MOCK_PREFIX = "mock:"


class ConnectorRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connectors: Dict[str, RetailerConnector] = {}
        self._build()

    def _build(self) -> None:
        keys = self._settings.enabled_connector_keys
        wants_all_mocks = MOCK_WILDCARD in keys
        explicit_mocks = {k[len(MOCK_PREFIX) :] for k in keys if k.startswith(MOCK_PREFIX)}
        explicit_mocks.discard("*")

        for connector in build_mock_connectors(self._settings):
            if wants_all_mocks or connector.key in explicit_mocks or connector.key in keys:
                self._connectors[connector.key] = connector

        for connector in build_feed_connectors(self._settings, keys):
            self._connectors[connector.key] = connector

        if self._settings.enable_example_public_connector:
            connector = ExamplePublicApiConnector(self._settings)
            self._connectors[connector.key] = connector

        # HTML connectors are never registered automatically - a deployment
        # must add them explicitly once permission is in place. See
        # docs/adding-a-connector.md.

        log.info(
            "connectors.registered",
            count=len(self._connectors),
            keys=sorted(self._connectors.keys()),
        )

    # ------------------------------------------------------------------ API
    def all(self) -> List[RetailerConnector]:
        return list(self._connectors.values())

    def get(self, key: str) -> Optional[RetailerConnector]:
        return self._connectors.get(key)

    def register(self, connector: RetailerConnector) -> None:
        """Add a connector at runtime (used by tests and custom deployments)."""
        self._connectors[connector.key] = connector

    def for_intent(self, intent: SearchIntent) -> List[RetailerConnector]:
        """The connectors relevant to this search, in stable order."""
        selected = []
        for connector in self._connectors.values():
            try:
                if connector.supports(intent):
                    selected.append(connector)
            except Exception as exc:  # a broken supports() must not kill the search
                log.warning("connector.supports_failed", retailer=connector.key, error=str(exc))
        return sorted(selected, key=lambda c: c.key)

    async def health(self) -> List[ConnectorHealth]:
        connectors = self.all()
        if not connectors:
            return []
        results = await asyncio.gather(
            *(self._safe_health(connector) for connector in connectors)
        )
        return list(results)

    @staticmethod
    async def _safe_health(connector: RetailerConnector) -> ConnectorHealth:
        try:
            return await asyncio.wait_for(connector.health_check(), timeout=5.0)
        except Exception as exc:
            return ConnectorHealth(
                key=connector.key,
                name=connector.display_name,
                healthy=False,
                message=str(exc)[:200],
            )

    async def aclose(self) -> None:
        await asyncio.gather(
            *(connector.aclose() for connector in self._connectors.values()),
            return_exceptions=True,
        )
