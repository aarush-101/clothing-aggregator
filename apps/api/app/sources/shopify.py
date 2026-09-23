"""Read public men's collections, preserving variant price and stock identity."""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Awaitable, Callable, List, Optional
from urllib.parse import quote, urljoin, urlsplit

import httpx
from protego import Protego

from app.models.product import Product, sanitise_text, sanitise_url, utcnow
from app.services.nlp.lexicon import (
    COLOUR_SYNONYMS,
    MATERIAL_SYNONYMS,
    classify_category,
    find_terms,
    normalise_size,
)
from app.sources.registry import Retailer

USER_AGENT = "Marle/0.1 (menswear product index)"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MIN_PRICE = Decimal("1.00")
_INTERNAL_TAG = re.compile(r"\s*\[(?:merged|archived?|old|duplicate)\b[^\]]*\]", re.I)


def _decimal(value) -> Optional[Decimal]:
    try:
        number = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None
    return number if value is not None and number.is_finite() and number >= 0 else None


class SourceError(RuntimeError):
    def __init__(self, message: str, *, retry_after: float = 3600, blocked: bool = False):
        super().__init__(message)
        self.retry_after = retry_after
        self.blocked = blocked


def retry_delay(value: Optional[str]) -> float:
    try:
        return max(3600, float(value))
    except (TypeError, ValueError):
        try:
            return max(3600, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return 3600


def normalise_variants(raw: dict, retailer: Retailer, observed_at: datetime) -> List[Product]:
    """One stored offer per variant. A bad record fails the snapshot, never deletes data."""
    # Some stores leave internal merge/archive markers in public titles.
    title = sanitise_text(_INTERNAL_TAG.sub("", str(raw.get("title") or "")))
    product_id = str(raw.get("id") or "")
    handle = raw.get("handle")
    if not title or not product_id or not isinstance(handle, str) or not handle:
        raise SourceError("Product is missing its id, title or handle")
    product_type = str(raw.get("product_type") or "")
    tags = raw.get("tags") or []
    tags = tags if isinstance(tags, list) else tags.split(",")
    department = " ".join([title, product_type, *tags]).lower()
    # Collections are men's scoped; reject explicit non-menswear and gift cards.
    if re.search(r"\b(women|womens|women's|girls|boys|kids|baby|gift card)\b", department):
        return []
    brand = sanitise_text(raw.get("vendor"))
    if brand and brand.lower() in {"mens", "men", "womens", "women", "unisex"}:
        brand = None  # Some stores use vendor as a department, not a brand.
    brand = brand or retailer.ingestion.default_brand
    description = sanitise_text(raw.get("body_html"))
    # Multi-brand titles lead with the brand; "Tommy Jeans ... Card Holder" is not jeans.
    garment = title
    if brand and title.lower().startswith(brand.lower()):
        garment = title[len(brand) :]
    category = classify_category(garment) or classify_category(product_type)
    materials = find_terms(description or "", MATERIAL_SYNONYMS)
    options = {
        str(option.get("name", "")).lower(): int(option.get("position", index + 1))
        for index, option in enumerate(raw.get("options") or [])
    }
    colour_pos = options.get("color", options.get("colour"))
    size_pos = options.get("size")
    images = raw.get("images") or []
    image = images[0].get("src") if images else None
    variants = raw.get("variants")
    if not isinstance(variants, list) or not variants:
        raise SourceError(f"Product {product_id} has no variants")
    products = []
    for variant in variants:
        variant_id = str(variant.get("id") or "")
        if not variant_id:
            raise SourceError(f"Product {product_id} has a variant without an id")
        price = Decimal(str(variant.get("price")))
        if not price.is_finite() or price < 0:
            raise SourceError(f"Product {product_id} has an invalid price")
        original = _decimal(variant.get("compare_at_price"))
        original = original if original is not None and original > price else None
        # Free gifts and placeholder variants ($0-$1, or >90% off) are not real offers.
        if price <= MIN_PRICE or (original is not None and price < original * Decimal("0.1")):
            continue
        colour = str(variant.get(f"option{colour_pos}") or "") if colour_pos else ""
        colours = find_terms(colour, COLOUR_SYNONYMS) if colour else []
        colours = colours or find_terms(title, COLOUR_SYNONYMS)
        # A named but unknown colour remains visible instead of being invented.
        colours = colours or ([colour.lower()] if colour else [])
        size = normalise_size(str(variant.get(f"option{size_pos}") or "")) if size_pos else ""
        availability = variant.get("available")
        stock = availability if isinstance(availability, bool) else None
        url = (
            f"{retailer.website_url.rstrip('/')}/products/{quote(handle, safe='-')}"
            f"?variant={quote(variant_id, safe='')}"
        )
        variant_image = variant.get("featured_image") or {}
        products.append(
            Product(
                product_id=variant_id,
                listing_id=product_id,
                variant_size=size or None,
                title=title,
                description=description,
                brand=brand,
                retailer=retailer.key,
                retailer_name=retailer.name,
                product_url=url,
                affiliate_url=url,
                image_url=sanitise_url(variant_image.get("src") or image),
                category=category or product_type.lower() or None,
                colours=colours,
                materials=materials,
                available_sizes=[size] if size and stock is True else [],
                price=price,
                original_price=original,
                currency=retailer.ingestion.currency,
                in_stock=stock,
                shipping_destination=None,
                shipping_cost=None,
                source_updated_at=raw.get("updated_at"),
                retrieved_at=observed_at,
            )
        )
    return products


class ShopifySource:
    def __init__(
        self,
        retailer: Retailer,
        *,
        client: Optional[httpx.AsyncClient] = None,
        request_delay: float = 1.0,
    ):
        self.retailer = retailer
        self._client = client
        self._owned_client = client is None
        self.delay = request_delay
        self._last_request = 0.0
        self._robots: Optional[Protego] = None

    async def _get(self, url: str, *, robots: bool = False) -> httpx.Response:
        for _ in range(5):
            parts = urlsplit(url)
            if (
                parts.scheme != "https"
                or parts.netloc != urlsplit(self.retailer.website_url).netloc
            ):
                raise SourceError(
                    "Source redirected outside its configured HTTPS host", blocked=True
                )
            if not robots and self._robots and not self._robots.can_fetch(url, USER_AGENT):
                raise SourceError(
                    "Collection access is disallowed by robots.txt", blocked=True, retry_after=86400
                )
            await asyncio.sleep(max(0, self.delay - (time.monotonic() - self._last_request)))
            self._last_request = time.monotonic()
            async with self._client.stream("GET", url, follow_redirects=False) as response:
                if (
                    response.status_code in {401, 403, 429}
                    or response.headers.get("cf-mitigated") == "challenge"
                ):
                    raise SourceError(
                        f"Source paused after HTTP {response.status_code}",
                        blocked=True,
                        retry_after=retry_delay(response.headers.get("retry-after")),
                    )
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise SourceError("Source response exceeded the size limit")
                if not (robots and response.status_code == 404) and response.status_code != 200:
                    raise SourceError(
                        f"Source returned HTTP {response.status_code}",
                        retry_after=retry_delay(response.headers.get("retry-after")),
                    )
                headers = dict(response.headers)
                # aiter_bytes has already decoded HTTP content encodings.
                headers.pop("content-encoding", None)
                headers.pop("content-length", None)
                return httpx.Response(
                    response.status_code,
                    headers=headers,
                    content=bytes(body),
                    request=response.request,
                )
        raise SourceError("Too many source redirects")

    async def fetch(
        self, heartbeat: Optional[Callable[[], Awaitable[None]]] = None
    ) -> List[Product]:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=25,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain"},
            )
        try:
            robots = await self._get(
                self.retailer.website_url.rstrip("/") + "/robots.txt", robots=True
            )
            if robots.status_code == 200 and "<html" in robots.text.lower():
                raise SourceError("robots.txt returned HTML instead of rules", blocked=True)
            self._robots = Protego.parse(robots.text if robots.status_code == 200 else "")
            rate = self._robots.request_rate(USER_AGENT)
            self.delay = max(
                self.delay,
                self._robots.crawl_delay(USER_AGENT) or 0,
                rate.seconds / rate.requests if rate else 0,
            )
            observed_at = utcnow()
            seen = set()
            products: List[Product] = []
            for page in range(1, self.retailer.ingestion.max_pages + 1):
                if heartbeat:
                    await heartbeat()
                response = await self._get(f"{self.retailer.catalogue_url}?limit=250&page={page}")
                try:
                    data = response.json()
                except ValueError as exc:
                    raise SourceError("Source did not return product JSON", blocked=True) from exc
                rows = data.get("products") if isinstance(data, dict) else None
                if not isinstance(rows, list):
                    raise SourceError("Source response has no products array")
                if not rows:
                    return products
                for row in rows:
                    identifier = str(row.get("id") or "")
                    if identifier in seen:
                        raise SourceError("Pagination repeated a product; snapshot is incomplete")
                    seen.add(identifier)
                    products.extend(normalise_variants(row, self.retailer, observed_at))
            raise SourceError("Page budget reached before a complete snapshot")
        finally:
            if self._owned_client and self._client:
                await self._client.aclose()
                self._client = None
