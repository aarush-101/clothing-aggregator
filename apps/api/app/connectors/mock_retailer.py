"""Mock retailer connectors backed by a seeded catalogue.

These exist so the whole pipeline - streaming, ranking, de-duplication,
caching - can be exercised end to end without depending on any third party.
The catalogue uses fictional brands and retailers on the reserved ``.example``
TLD: nothing here impersonates a real shop, and no real site is contacted.

Each retailer deliberately responds at a different speed so progressive
result streaming is visible in development.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.connectors.base import ConnectorError, ConnectorHealth, RetailerConnector
from app.models.intent import SearchIntent
from app.models.product import Product, utcnow
from app.services.nlp.lexicon import canonicalise_all, COLOUR_SYNONYMS, MATERIAL_SYNONYMS

CATALOGUE_PATH = Path(__file__).resolve().parent.parent / "data" / "mock_catalogue.json"

# Per-retailer simulated round-trip latency, in seconds.
_LATENCY = {
    "northbound": 0.35,
    "harbour": 0.75,
    "ridgeline": 1.30,
    "meridian": 0.55,
}


@lru_cache(maxsize=1)
def load_catalogue() -> Dict[str, Any]:
    with CATALOGUE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class MockRetailerConnector(RetailerConnector):
    """A single fictional retailer's slice of the seeded catalogue."""

    def __init__(self, settings: Settings, key: str, meta: Dict[str, Any]) -> None:
        super().__init__(settings)
        self.key = key
        self.display_name = meta["name"]
        self.ships_to = list(meta.get("ships_to") or [])
        self.currency = meta.get("currency", "AUD")
        self._latency = _LATENCY.get(key, 0.5)

    # ------------------------------------------------------------------ API
    async def search(self, intent: SearchIntent) -> List[Product]:
        delay = self._latency * max(0.0, self.settings.mock_latency_multiplier)
        if delay:
            await asyncio.sleep(delay)

        catalogue = load_catalogue()
        products: List[Product] = []
        for garment in catalogue["garments"]:
            offer = self._offer_for_retailer(garment)
            if offer is None:
                continue
            if not self._is_candidate(garment, intent):
                continue
            product = self.normalise({"garment": garment, "offer": offer})
            if product is not None:
                products.append(product)
        return products

    def normalise(self, raw_product: Any) -> Optional[Product]:
        garment = raw_product["garment"]
        offer = raw_product["offer"]
        updated = utcnow() - timedelta(days=int(offer.get("updated_days_ago", 0)))
        return self.build_product(
            product_id=offer["product_id"],
            title=f"{garment['brand']} {garment['title']}",
            description=garment.get("description"),
            brand=garment.get("brand"),
            product_url=offer["product_url"],
            image_url=garment.get("image_url"),
            category=garment.get("category"),
            colours=garment.get("colours", []),
            materials=garment.get("materials", []),
            available_sizes=offer.get("sizes", []),
            price=offer["price"],
            original_price=offer.get("original_price"),
            in_stock=bool(offer.get("in_stock", True)),
            shipping_destination=self.ships_to[0] if self.ships_to else None,
            shipping_cost=offer.get("shipping_cost"),
            source_updated_at=updated,
        )

    async def health_check(self) -> ConnectorHealth:
        try:
            load_catalogue()
        except Exception as exc:  # pragma: no cover - only on a corrupt install
            return ConnectorHealth(
                key=self.key, name=self.display_name, healthy=False, message=str(exc)
            )
        return ConnectorHealth(
            key=self.key,
            name=self.display_name,
            healthy=True,
            latency_ms=int(self._latency * 1000),
            message="seeded catalogue",
        )

    # -------------------------------------------------------------- helpers
    def _offer_for_retailer(self, garment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for offer in garment.get("offers", []):
            if offer.get("retailer") == self.key:
                return offer
        return None

    def _is_candidate(self, garment: Dict[str, Any], intent: SearchIntent) -> bool:
        """Coarse server-side filter, the way a retailer's search API would."""
        brand = (garment.get("brand") or "").lower()
        if brand in intent.excluded_brands:
            return False

        if intent.product_categories and garment.get("category") not in intent.product_categories:
            # Allow a near-miss when nothing else in the query narrows it down.
            if intent.colours or intent.materials or intent.fits:
                return False
            return False

        if intent.colours:
            garment_colours = canonicalise_all(garment.get("colours", []), COLOUR_SYNONYMS)
            if not set(garment_colours) & set(intent.colours):
                return False

        if intent.materials:
            garment_materials = canonicalise_all(garment.get("materials", []), MATERIAL_SYNONYMS)
            if not set(garment_materials) & set(intent.materials):
                return False

        return True


class FlakyMockConnector(MockRetailerConnector):
    """A retailer that fails on purpose, to exercise partial-result handling."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            key="atlas",
            meta={"name": "Atlas Trading Co.", "ships_to": ["AU", "NZ"]},
        )
        self._latency = 0.9

    async def search(self, intent: SearchIntent) -> List[Product]:
        await asyncio.sleep(self._latency * max(0.0, self.settings.mock_latency_multiplier))
        raise ConnectorError("Upstream returned HTTP 503 (simulated outage)")

    async def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(
            key=self.key,
            name=self.display_name,
            healthy=False,
            message="simulated outage - enabled by MOCK_INCLUDE_FLAKY_RETAILER",
        )


def build_mock_connectors(settings: Settings) -> List[RetailerConnector]:
    catalogue = load_catalogue()
    connectors: List[RetailerConnector] = [
        MockRetailerConnector(settings, key, meta)
        for key, meta in catalogue["retailers"].items()
    ]
    if settings.mock_include_flaky_retailer:
        connectors.append(FlakyMockConnector(settings))
    return connectors


def mock_retailer_keys() -> List[str]:
    return list(load_catalogue()["retailers"].keys())


__all__ = [
    "MockRetailerConnector",
    "FlakyMockConnector",
    "build_mock_connectors",
    "mock_retailer_keys",
    "load_catalogue",
    "random",
]
