"""Example connector for a public, credential-free product API.

This demonstrates the shape of a real retailer/API integration - HTTP client
reuse, timeouts, defensive normalisation, health checks - against an API that
anyone can call without signing an affiliate agreement.

It is **disabled by default** (``ENABLE_EXAMPLE_PUBLIC_CONNECTOR=false``)
because it depends on a third party being reachable, and because the upstream
demo API returns placeholder catalogue data rather than a real storefront.
Treat it as a template, not as a product source.
"""

from __future__ import annotations

import time
from typing import Any, List, Optional

import httpx

from app.config import Settings
from app.connectors.base import ConnectorError, ConnectorHealth, RetailerConnector
from app.connectors.filtering import passes_coarse_filter
from app.logging_config import get_logger
from app.models.intent import SearchIntent
from app.models.product import Product

log = get_logger(__name__)

CATEGORY_PATH = "/products/category/men's clothing"


class ExamplePublicApiConnector(RetailerConnector):
    key = "example_public"
    display_name = "Example Public API (demo)"
    ships_to: List[str] = []  # unknown - treated as worldwide
    currency = "USD"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._base_url = settings.example_public_api_base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def search(self, intent: SearchIntent) -> List[Product]:
        client = self._ensure_client()
        try:
            response = await client.get(f"{self._base_url}{CATEGORY_PATH}")
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"upstream returned HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(f"upstream request failed: {exc}") from exc
        except ValueError as exc:
            raise ConnectorError("upstream returned a non-JSON body") from exc

        if not isinstance(payload, list):
            raise ConnectorError("upstream returned an unexpected payload shape")

        products: List[Product] = []
        for record in payload:
            product = self.normalise(record)
            if product is not None and passes_coarse_filter(product, intent):
                products.append(product)
        return products

    def normalise(self, raw_product: Any) -> Optional[Product]:
        if not isinstance(raw_product, dict):
            return None
        identifier = raw_product.get("id")
        if identifier is None:
            return None
        return self.build_product(
            product_id=str(identifier),
            title=raw_product.get("title"),
            description=raw_product.get("description"),
            brand=None,  # the demo API does not expose a brand field
            product_url=f"{self._base_url}/products/{identifier}",
            image_url=raw_product.get("image"),
            category=raw_product.get("category"),
            price=raw_product.get("price"),
            currency=self.currency,
            in_stock=True,
            available_sizes=[],
        )

    async def health_check(self) -> ConnectorHealth:
        started = time.perf_counter()
        try:
            client = self._ensure_client()
            response = await client.get(f"{self._base_url}/products?limit=1")
            response.raise_for_status()
        except Exception as exc:
            return ConnectorHealth(
                key=self.key, name=self.display_name, healthy=False, message=str(exc)[:200]
            )
        return ConnectorHealth(
            key=self.key,
            name=self.display_name,
            healthy=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.settings.search_retailer_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "clothing-aggregator/0.1 (+example-connector)"},
            )
        return self._client
