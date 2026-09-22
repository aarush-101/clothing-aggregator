"""Shopify storefront connector.

Many independent menswear brands run on Shopify, which serves a standard
``/products.json`` endpoint describing the products already published on the
storefront. This connector reads that endpoint, normalises it into our
:class:`Product` shape, and filters it against the shopper's intent.

STATUS: DISABLED BY DEFAULT - the public endpoint is not reachable server-side.
----------------------------------------------------------------------------
On 2026-09-22 all 93 verified storefronts in ``shopify_stores.json`` returned
``HTTP 429`` with ``cf-mitigated: challenge`` to this connector: Cloudflare is
challenging automated clients on the stores' behalf. Getting past that would
need TLS-fingerprint spoofing, a headless browser or proxy rotation - all of
which are anti-bot evasion, which this project does not do.

The connector is kept because it is correct and immediately useful for the two
legitimate routes:

1. A store that has granted you access (allow-listed User-Agent or IP).
2. Shopify's **Storefront API** with a merchant-issued access token, which is
   the sanctioned interface and is not challenged. See
   ``docs/real-retailer-data.md``.

Boundaries this connector keeps:

* It reads only the public storefront JSON a store already publishes. It does
  not log in, does not touch checkout or account endpoints, and does not
  attempt to reach anything a shopper's browser could not.
* It identifies itself honestly in the User-Agent.
* A ``401``/``403``/``429`` means the store does not want automated requests.
  The connector stops and reports a failure - it never retries around a block.
* Each store's catalogue is cached, so repeat searches cost the retailer
  nothing. One shopper's search does not become N requests to every brand.

Store list: ``app/data/shopify_stores.json``.
"""

from __future__ import annotations

import json
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings
from app.connectors.base import (
    ConnectorError,
    ConnectorHealth,
    ConnectorSkipped,
    RetailerConnector,
)
from app.connectors.filtering import passes_coarse_filter
from app.logging_config import get_logger
from app.models.intent import Gender, SearchIntent
from app.models.product import Product, sanitise_text
from app.services.nlp.lexicon import (
    CATEGORY_SYNONYMS,
    COLOUR_SYNONYMS,
    MATERIAL_SYNONYMS,
    canonicalise,
    find_terms,
)

log = get_logger(__name__)

# Set per search by the search engine. Reading a store's catalogue for the
# first time costs a real HTTP round trip, so only a bounded number of cold
# reads happen per search; already-cached stores are free and always run.
# Coverage therefore grows across searches instead of making the first one
# unusably slow - and nothing is ever fetched without a user searching.
cold_fetch_budget: ContextVar[Optional[List[int]]] = ContextVar(
    "shopify_cold_fetch_budget", default=None
)


def new_cold_fetch_budget(size: int) -> List[int]:
    """A mutable counter shared by every connector in one search."""
    return [max(0, size)]


def _claim_cold_fetch() -> bool:
    budget = cold_fetch_budget.get()
    if budget is None:
        return True  # no budget in force (tests, health checks)
    if budget[0] <= 0:
        return False
    budget[0] -= 1
    return True


STORES_PATH = Path(__file__).resolve().parent.parent / "data" / "shopify_stores.json"

USER_AGENT = (
    "Mozilla/5.0 (compatible; marle-menswear-search/0.1; "
    "+https://example.org/marle/bot) storefront-json-reader"
)

PAGE_SIZE = 250

# Product types / tags that mean "not menswear".
_WOMENS = re.compile(r"\b(women|womens|women's|ladies|girls|female)\b", re.I)
_KIDS = re.compile(r"\b(kids?|child|children|youth|baby|toddler|infant)\b", re.I)
_GIFT_CARD = re.compile(r"\b(gift ?card|e-?gift)\b", re.I)

_COLOUR_OPTION = re.compile(r"^colou?r", re.I)
_SIZE_OPTION = re.compile(r"^size", re.I)


@dataclass
class ShopifyStore:
    """One storefront, as configured in ``shopify_stores.json``."""

    key: str
    name: str
    domain: str
    currency: str = "USD"
    ships_to: List[str] = field(default_factory=list)
    enabled: bool = True
    # How many 250-product pages to read. Most brands fit in one or two.
    max_pages: int = 2
    country: Optional[str] = None
    notes: Optional[str] = None

    @property
    def base_url(self) -> str:
        return f"https://{self.domain}"

    def product_url(self, handle: str) -> str:
        return f"{self.base_url}/products/{handle}"


def load_stores(path: Path = STORES_PATH) -> List[ShopifyStore]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return [ShopifyStore(**entry) for entry in payload.get("stores", [])]


def _strip_html(value: Optional[str], limit: int = 600) -> Optional[str]:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return sanitise_text(text, limit=limit)


def _looks_like_menswear(product: Dict[str, Any], intent: SearchIntent) -> bool:
    """Filter out women's, children's and non-garment listings."""
    tags = product.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    haystack = " ".join(
        [
            str(product.get("title") or ""),
            str(product.get("product_type") or ""),
            " ".join(str(tag) for tag in tags),
        ]
    )

    if _GIFT_CARD.search(haystack):
        return False
    if _KIDS.search(haystack):
        return False
    if intent.gender is Gender.MEN and _WOMENS.search(haystack):
        # Multi-brand stores mix departments; "mens" beats a stray "womens" tag.
        return bool(re.search(r"\b(men|mens|men's)\b", haystack, re.I))
    return not (intent.gender is Gender.WOMEN and not _WOMENS.search(haystack))


def _option_values(product: Dict[str, Any], matcher: re.Pattern) -> List[str]:
    for option in product.get("options") or []:
        if isinstance(option, dict) and matcher.match(str(option.get("name") or "")):
            return [str(value) for value in option.get("values") or []]
    return []


def _available_sizes(product: Dict[str, Any]) -> List[str]:
    """Sizes with at least one purchasable variant."""
    size_index = None
    for index, option in enumerate(product.get("options") or [], start=1):
        if isinstance(option, dict) and _SIZE_OPTION.match(str(option.get("name") or "")):
            size_index = index
            break
    if size_index is None:
        return []

    key = f"option{size_index}"
    sizes: List[str] = []
    for variant in product.get("variants") or []:
        if not isinstance(variant, dict) or not variant.get("available"):
            continue
        value = variant.get(key)
        if value and str(value) not in sizes:
            sizes.append(str(value))
    return sizes


def _cheapest_variant(product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The cheapest purchasable variant, else the cheapest of any."""
    variants = [v for v in (product.get("variants") or []) if isinstance(v, dict)]
    if not variants:
        return None

    def price_of(variant: Dict[str, Any]) -> float:
        try:
            return float(variant.get("price") or 0)
        except (TypeError, ValueError):
            return float("inf")

    available = [v for v in variants if v.get("available")]
    return min(available or variants, key=price_of)


class ShopifyConnector(RetailerConnector):
    def __init__(self, settings: Settings, store: ShopifyStore, cache: Any = None) -> None:
        super().__init__(settings)
        self.store = store
        self.key = store.key
        self.display_name = store.name
        self.ships_to = list(store.ships_to)
        self.currency = store.currency
        self._cache = cache
        self._client: Optional[httpx.AsyncClient] = None
        self._memory_catalogue: Optional[List[Dict[str, Any]]] = None
        self._memory_expires_at: float = 0.0

    # ------------------------------------------------------------------ API
    def _filter_ok(self, raw: Dict[str, Any], intent: SearchIntent) -> bool:
        """True if this listing belongs to the department being searched."""
        return _looks_like_menswear(raw, intent)

    async def search(self, intent: SearchIntent) -> List[Product]:
        raw_products = await self._catalogue()

        products: List[Product] = []
        for raw in raw_products:
            if not _looks_like_menswear(raw, intent):
                continue
            product = self.normalise(raw)
            if product is not None and passes_coarse_filter(product, intent):
                products.append(product)
        return products

    def normalise(self, raw_product: Any) -> Optional[Product]:
        if not isinstance(raw_product, dict):
            return None

        handle = raw_product.get("handle")
        identifier = raw_product.get("id")
        if not handle or identifier is None:
            return None

        variant = _cheapest_variant(raw_product)
        if variant is None:
            return None

        title = str(raw_product.get("title") or "")
        description = _strip_html(raw_product.get("body_html"))
        tags = raw_product.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        attribute_text = " ".join(
            [title, str(raw_product.get("product_type") or ""), " ".join(map(str, tags))]
        )

        # Colour: the Color option if the store has one, else read it out of
        # the title ("... Hooded Fleece Ecru Marle").
        colour_values = _option_values(raw_product, _COLOUR_OPTION)
        colours: List[str] = []
        for value in colour_values:
            canonical = canonicalise(value, COLOUR_SYNONYMS)
            if canonical and canonical not in colours:
                colours.append(canonical)
        if not colours:
            colours = find_terms(attribute_text, COLOUR_SYNONYMS)

        materials = find_terms(" ".join([attribute_text, description or ""]), MATERIAL_SYNONYMS)

        category = canonicalise(str(raw_product.get("product_type") or ""), CATEGORY_SYNONYMS)
        if not category:
            category = canonicalise(title, CATEGORY_SYNONYMS)

        images = raw_product.get("images") or []
        image_url = None
        if images and isinstance(images[0], dict):
            image_url = images[0].get("src")

        # Shopify repeats the price in compare_at_price when nothing is on
        # sale; Product treats that as "no discount".
        original_price = variant.get("compare_at_price")

        return self.build_product(
            product_id=f"{self.key}-{identifier}",
            title=title,
            description=description,
            brand=raw_product.get("vendor") or self.display_name,
            product_url=self.store.product_url(str(handle)),
            image_url=image_url,
            category=category,
            colours=colours,
            materials=materials,
            available_sizes=_available_sizes(raw_product),
            price=variant.get("price"),
            original_price=original_price,
            currency=self.store.currency,
            in_stock=bool(variant.get("available")),
            shipping_destination=self.ships_to[0] if self.ships_to else None,
            source_updated_at=raw_product.get("updated_at"),
        )

    async def health_check(self) -> ConnectorHealth:
        started = time.perf_counter()
        try:
            page = await self._fetch_page(1, limit=1)
        except Exception as exc:
            return ConnectorHealth(
                key=self.key, name=self.display_name, healthy=False, message=str(exc)[:200]
            )
        return ConnectorHealth(
            key=self.key,
            name=self.display_name,
            healthy=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
            message=f"{len(page)} products on first page",
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -------------------------------------------------------------- helpers
    async def _catalogue(self) -> List[Dict[str, Any]]:
        """The store's published products, cached so repeats cost nothing."""
        now = time.monotonic()
        if self._memory_catalogue is not None and now < self._memory_expires_at:
            return self._memory_catalogue

        ttl = self.settings.shopify_catalogue_ttl_seconds
        cache_key = f"shopify:{self.key}"

        if self._cache is not None:
            cached = await self._cache.get_catalogue(cache_key)
            if cached is not None:
                self._memory_catalogue = cached
                self._memory_expires_at = now + min(ttl, 300)
                return cached

        if not _claim_cold_fetch():
            raise ConnectorSkipped("not loaded yet - will be included next search")

        products: List[Dict[str, Any]] = []
        for page in range(1, max(1, self.store.max_pages) + 1):
            batch = await self._fetch_page(page)
            products.extend(batch)
            if len(batch) < PAGE_SIZE:
                break

        if self._cache is not None:
            await self._cache.set_catalogue(cache_key, products, ttl)
        self._memory_catalogue = products
        self._memory_expires_at = now + min(ttl, 300)
        log.info("shopify.catalogue_fetched", retailer=self.key, products=len(products))
        return products

    async def _fetch_page(self, page: int, limit: int = PAGE_SIZE) -> List[Dict[str, Any]]:
        url = f"{self.store.base_url}/products.json"
        client = self._ensure_client()
        try:
            response = await client.get(url, params={"limit": limit, "page": page})
        except httpx.HTTPError as exc:
            raise ConnectorError(f"request failed: {exc}") from exc

        if response.status_code in (401, 403, 429):
            # The store is telling automated clients to stop. We stop.
            raise ConnectorError(f"store declined automated requests (HTTP {response.status_code})")
        if response.status_code == 404:
            raise ConnectorError("store does not publish products.json")
        if response.status_code >= 400:
            raise ConnectorError(f"HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorError("response was not JSON") from exc

        products = payload.get("products") if isinstance(payload, dict) else None
        if not isinstance(products, list):
            raise ConnectorError("unexpected products.json shape")
        return [p for p in products if isinstance(p, dict)]

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.settings.search_retailer_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
        return self._client


def build_shopify_connectors(
    settings: Settings, cache: Any = None, stores: Optional[List[ShopifyStore]] = None
) -> List[RetailerConnector]:
    if not settings.enable_shopify_connectors:
        return []
    catalogue = stores if stores is not None else load_stores()
    return [ShopifyConnector(settings, store, cache) for store in catalogue if store.enabled]
