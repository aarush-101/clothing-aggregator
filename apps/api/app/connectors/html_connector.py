"""Permission-gated HTML connector. DISABLED BY DEFAULT.

Why this exists at all: some retailers will grant a partner permission to read
their public product pages before an affiliate feed is available. This class is
the only sanctioned way to do that in this codebase, and it is deliberately
restrictive:

* It refuses to run unless ``ENABLE_HTML_CONNECTORS=true`` **and** the specific
  retailer config carries ``permission_granted: true``.
* It reads ``robots.txt`` and obeys it. No override exists.
* It sends an honest, identifiable User-Agent with a contact URL.
* It rate-limits itself to one request per ``min_request_interval`` seconds.
* It reads **schema.org Product JSON-LD** - the structured data retailers
  publish for exactly this purpose - and never attempts to defeat, evade or
  work around bot protection, CAPTCHAs, rate limits or paywalls.

If a retailer blocks us, that is the answer: we stop. Do not add evasion here.
See ``docs/adding-a-connector.md`` for the policy in full.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.robotparser
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx

from app.config import Settings
from app.connectors.base import (
    ConnectorError,
    ConnectorHealth,
    ConnectorPermissionError,
    RetailerConnector,
)
from app.connectors.filtering import passes_coarse_filter
from app.logging_config import get_logger
from app.models.intent import SearchIntent
from app.models.product import Product

log = get_logger(__name__)

USER_AGENT = (
    "clothing-aggregator/0.1 (+https://example.org/clothing-aggregator/bot; "
    "authorised partner crawler)"
)


class _JsonLdCollector(HTMLParser):
    """Collects the contents of <script type="application/ld+json"> blocks."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks: List[str] = []
        self._capturing = False
        self._buffer: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Any]) -> None:
        if tag.lower() != "script":
            return
        attributes = {key.lower(): (value or "").lower() for key, value in attrs}
        if attributes.get("type") == "application/ld+json":
            self._capturing = True
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capturing:
            self.blocks.append("".join(self._buffer))
            self._capturing = False
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._buffer.append(data)


def extract_jsonld_products(html: str) -> List[Dict[str, Any]]:
    """Return every schema.org Product object found in the page."""
    collector = _JsonLdCollector()
    try:
        collector.feed(html)
    except Exception:  # malformed markup - keep whatever we collected
        pass

    products: List[Dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict):
            return
        node_type = node.get("@type")
        types = node_type if isinstance(node_type, list) else [node_type]
        if any(str(t).lower() == "product" for t in types if t):
            products.append(node)
        for value in node.values():
            if isinstance(value, (list, dict)):
                visit(value)

    for block in collector.blocks:
        try:
            visit(json.loads(block))
        except json.JSONDecodeError:
            continue
    return products


class HtmlRetailerConnector(RetailerConnector):
    """Reads schema.org product data from a retailer's own pages, with consent."""

    requires_permission = True

    def __init__(
        self,
        settings: Settings,
        key: str,
        display_name: str,
        search_url_template: str,
        permission_granted: bool = False,
        ships_to: Optional[List[str]] = None,
        currency: str = "AUD",
        min_request_interval: float = 1.0,
    ) -> None:
        super().__init__(settings)
        self.key = key
        self.display_name = display_name
        self.ships_to = list(ships_to or [])
        self.currency = currency
        self._search_url_template = search_url_template
        self._permission_granted = permission_granted
        self._min_request_interval = min_request_interval
        self._last_request_at = 0.0
        self._client: Optional[httpx.AsyncClient] = None
        self._robots: Optional[urllib.robotparser.RobotFileParser] = None

    # ----------------------------------------------------------- guardrails
    def _assert_allowed(self) -> None:
        if not self.settings.enable_html_connectors:
            raise ConnectorPermissionError(
                f"HTML connector '{self.key}' is disabled. Set ENABLE_HTML_CONNECTORS=true "
                "only for retailers who have given written permission."
            )
        if not self._permission_granted:
            raise ConnectorPermissionError(
                f"HTML connector '{self.key}' has no recorded permission from the retailer."
            )

    def supports(self, intent: SearchIntent) -> bool:
        if not self.settings.enable_html_connectors or not self._permission_granted:
            return False
        return super().supports(intent)

    async def _robots_allows(self, url: str) -> bool:
        if self._robots is None:
            parsed = urlparse(url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            parser = urllib.robotparser.RobotFileParser()
            client = self._ensure_client()
            try:
                response = await client.get(robots_url)
                parser.parse(response.text.splitlines())
            except httpx.HTTPError:
                # Unreachable robots.txt is treated as "do not crawl".
                parser.disallow_all = True
            self._robots = parser
        return self._robots.can_fetch(USER_AGENT, url)

    async def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_at = time.monotonic()

    # ------------------------------------------------------------------ API
    async def search(self, intent: SearchIntent) -> List[Product]:
        self._assert_allowed()

        terms = " ".join(intent.all_keywords()[:5]) or intent.original_query
        url = self._search_url_template.format(query=httpx.QueryParams({"q": terms})["q"])

        if not await self._robots_allows(url):
            raise ConnectorError("robots.txt disallows this path - not fetching")

        await self._throttle()
        client = self._ensure_client()
        try:
            response = await client.get(url)
            if response.status_code in (401, 403, 429):
                # The retailer is telling us to stop. We stop.
                raise ConnectorError(
                    f"retailer declined the request (HTTP {response.status_code})"
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(f"request failed: {exc}") from exc

        products: List[Product] = []
        for record in extract_jsonld_products(response.text):
            product = self.normalise({"record": record, "base_url": url})
            if product is not None and passes_coarse_filter(product, intent):
                products.append(product)
        return products

    def normalise(self, raw_product: Any) -> Optional[Product]:
        record = raw_product["record"] if isinstance(raw_product, dict) else {}
        base_url = raw_product.get("base_url", "") if isinstance(raw_product, dict) else ""
        if not isinstance(record, dict):
            return None

        offers = record.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if not isinstance(offers, dict):
            offers = {}

        image = record.get("image")
        if isinstance(image, list):
            image = image[0] if image else None

        brand = record.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")

        product_url = offers.get("url") or record.get("url")
        if product_url and base_url:
            product_url = urljoin(base_url, str(product_url))

        availability = str(offers.get("availability") or "").lower()
        return self.build_product(
            product_id=str(record.get("sku") or record.get("productID") or product_url or ""),
            title=record.get("name"),
            description=record.get("description"),
            brand=brand,
            product_url=product_url,
            image_url=image,
            category=record.get("category"),
            colours=record.get("color"),
            materials=record.get("material"),
            price=offers.get("price"),
            currency=offers.get("priceCurrency") or self.currency,
            in_stock="outofstock" not in availability.replace("_", "").replace("-", ""),
        )

    async def health_check(self) -> ConnectorHealth:
        if not self.settings.enable_html_connectors:
            return ConnectorHealth(
                key=self.key,
                name=self.display_name,
                healthy=False,
                message="disabled (ENABLE_HTML_CONNECTORS=false)",
            )
        if not self._permission_granted:
            return ConnectorHealth(
                key=self.key,
                name=self.display_name,
                healthy=False,
                message="no recorded retailer permission",
            )
        return ConnectorHealth(key=self.key, name=self.display_name, healthy=True)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.settings.search_retailer_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
        return self._client
