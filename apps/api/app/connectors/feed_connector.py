"""Generic JSON / XML affiliate feed connector.

Most affiliate networks (Awin, Impact, CJ, Rakuten, Shopify collections) publish
a product feed as JSON or XML. Rather than writing a class per network, this
connector is configured declaratively through ``AFFILIATE_FEEDS``: point it at a
URL, say where the product records live, and map the feed's field names onto our
:class:`Product` fields.

See ``docs/adding-a-connector.md`` for the full configuration reference.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx
from defusedxml.ElementTree import fromstring as parse_xml

from app.config import FeedConnectorConfig, Settings
from app.connectors.base import ConnectorError, ConnectorHealth, RetailerConnector
from app.connectors.filtering import passes_coarse_filter
from app.logging_config import get_logger
from app.models.intent import SearchIntent
from app.models.product import Product

log = get_logger(__name__)

DEFAULT_FIELD_MAP: Dict[str, str] = {
    "product_id": "id",
    "title": "name",
    "description": "description",
    "brand": "brand",
    "product_url": "link",
    "image_url": "image",
    "category": "category",
    "colours": "colour",
    "materials": "material",
    "available_sizes": "sizes",
    "price": "price",
    "original_price": "rrp",
    "currency": "price@currency",
    "in_stock": "availability",
    "shipping_cost": "shipping_cost",
    "source_updated_at": "updated",
}

_IN_STOCK_VALUES = {"in stock", "instock", "in_stock", "available", "true", "yes", "1", "y"}


def _resolve_json_path(record: Any, path: str) -> Any:
    """Walk a dotted path, supporting numeric list indices ("images.0.src")."""
    current = record
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, list):
            if not part.isdigit() or int(part) >= len(current):
                return None
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _resolve_xml_path(element: Any, path: str) -> Any:
    """Resolve "tag/child" or "tag@attribute" against an XML element."""
    attribute: Optional[str] = None
    if "@" in path:
        path, attribute = path.split("@", 1)
    target = element if not path else element.find(path)
    if target is None:
        return None
    if attribute:
        return target.get(attribute)
    return (target.text or "").strip() or None


class FeedConnector(RetailerConnector):
    """One configured product feed."""

    def __init__(self, settings: Settings, config: FeedConnectorConfig) -> None:
        super().__init__(settings)
        self.config = config
        self.key = config.key
        self.display_name = config.display_name
        self.ships_to = list(config.ships_to or [])
        self.currency = config.currency
        self._field_map = {**DEFAULT_FIELD_MAP, **config.field_map}
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------ API
    async def search(self, intent: SearchIntent) -> List[Product]:
        document = await self._fetch(intent)
        records = self._extract_records(document)

        products: List[Product] = []
        discarded = 0
        for record in records[: self.config.max_items]:
            product = self.normalise(record)
            if product is None:
                discarded += 1
                continue
            if passes_coarse_filter(product, intent):
                products.append(product)
        if discarded:
            log.info("feed.records_discarded", retailer=self.key, count=discarded)
        return products

    def normalise(self, raw_product: Any) -> Optional[Product]:
        get = _resolve_xml_path if not isinstance(raw_product, dict) else _resolve_json_path

        def field(name: str) -> Any:
            path = self._field_map.get(name)
            if not path:
                return None
            try:
                return get(raw_product, path)
            except Exception:
                return None

        availability = field("in_stock")
        in_stock = True
        if availability is not None:
            if isinstance(availability, bool):
                in_stock = availability
            else:
                in_stock = str(availability).strip().lower() in _IN_STOCK_VALUES

        return self.build_product(
            product_id=field("product_id"),
            title=field("title"),
            description=field("description"),
            brand=field("brand"),
            product_url=field("product_url"),
            image_url=field("image_url"),
            category=field("category"),
            colours=field("colours"),
            materials=field("materials"),
            available_sizes=field("available_sizes"),
            price=field("price"),
            original_price=field("original_price"),
            currency=field("currency") or self.config.currency,
            in_stock=in_stock,
            shipping_destination=self.ships_to[0] if self.ships_to else None,
            shipping_cost=field("shipping_cost"),
            source_updated_at=field("source_updated_at"),
            **self.config.defaults,
        )

    async def health_check(self) -> ConnectorHealth:
        started = time.perf_counter()
        try:
            document = await self._fetch(None)
            count = len(self._extract_records(document))
        except Exception as exc:
            return ConnectorHealth(
                key=self.key, name=self.display_name, healthy=False, message=str(exc)[:200]
            )
        return ConnectorHealth(
            key=self.key,
            name=self.display_name,
            healthy=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
            message=f"{count} records",
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -------------------------------------------------------------- helpers
    async def _fetch(self, intent: Optional[SearchIntent]) -> str:
        url = self.config.url
        if not url.lower().startswith(("http://", "https://")):
            # Local file - used by the bundled sample feed and by tests.
            path = Path(url)
            if not path.is_absolute():
                path = Path(__file__).resolve().parent.parent / url
            try:
                return path.read_text(encoding="utf-8")
            except OSError as exc:
                raise ConnectorError(f"could not read feed file: {exc}") from exc

        if self.config.query_param and intent is not None:
            terms = " ".join(intent.all_keywords()[:6]) or intent.original_query
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode({self.config.query_param: terms})}"

        client = self._ensure_client()
        try:
            response = await client.get(url, headers=self.config.headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"feed returned HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(f"feed request failed: {exc}") from exc
        return response.text

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "clothing-aggregator/0.1 (+affiliate-feed-reader)"},
            )
        return self._client

    def _extract_records(self, document: str) -> List[Any]:
        if self.config.format == "json":
            try:
                payload = json.loads(document)
            except json.JSONDecodeError as exc:
                raise ConnectorError(f"feed is not valid JSON: {exc}") from exc
            records = _resolve_json_path(payload, self.config.items_path)
            if records is None and isinstance(payload, list):
                records = payload
            if not isinstance(records, list):
                raise ConnectorError(
                    f"items_path '{self.config.items_path}' did not resolve to a list"
                )
            return records

        try:
            root = parse_xml(document)
        except Exception as exc:
            raise ConnectorError(f"feed is not valid XML: {exc}") from exc
        return list(root.findall(self.config.items_path))


# The bundled example: a local XML feed so the connector type is demonstrable
# without credentials or network access.
SAMPLE_FEED_CONFIG = FeedConnectorConfig(
    key="sample_feed",
    display_name="Loom & Last (sample feed)",
    url="data/sample_feed.xml",
    format="xml",
    currency="AUD",
    ships_to=["AU", "NZ"],
    items_path="products/product",
    field_map={"description": "description"},
)


def build_feed_connectors(settings: Settings, enabled_keys: List[str]) -> List[RetailerConnector]:
    connectors: List[RetailerConnector] = []
    configs = list(settings.feed_configs)
    if "sample_feed" in enabled_keys and not any(c.key == "sample_feed" for c in configs):
        configs.append(SAMPLE_FEED_CONFIG)
    for config in configs:
        if not config.enabled:
            continue
        if enabled_keys and config.key not in enabled_keys:
            continue
        connectors.append(FeedConnector(settings, config))
    return connectors
