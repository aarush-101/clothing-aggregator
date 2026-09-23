"""Normalised retailer variant offers and search responses."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_serializer, field_validator

_SAFE_SCHEMES = ("http://", "https://")
_WHITESPACE = re.compile(r"\s+")
_HTML_TAG = re.compile(r"<[^>]+>")
_MAX_TEXT = 2000
# Control characters other than tab and newline.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f]")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sanitise_text(value: Any, limit: int = _MAX_TEXT) -> Optional[str]:
    """Strip markup and control characters out of retailer-supplied text.

    Retailer feeds are untrusted input: they end up in our logs, our LLM
    prompts and the browser, so everything is flattened to plain text here.
    """
    if value is None:
        return None
    text = _HTML_TAG.sub(" ", str(value))
    text = text.replace("\u0000", " ")
    text = _CONTROL_CHARS.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:limit] or None


def sanitise_url(value: Any) -> Optional[str]:
    """Return the URL only if it is a plain http(s) link.

    Blocks ``javascript:``, ``data:`` and protocol-relative URLs that would
    otherwise be rendered as clickable links in the UI.
    """
    if value is None:
        return None
    url = str(value).strip()
    if not url or len(url) > 2048:
        return None
    if not url.lower().startswith(_SAFE_SCHEMES):
        return None
    if any(ch in url for ch in ("\n", "\r", "\t", " ", "\u0000")):
        return None
    return url


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = re.sub(r"[^\d.\-]", "", str(value))
    if not text or text in {"-", ".", "-."}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


class Product(BaseModel):
    """A single offer from a single retailer, normalised."""

    model_config = ConfigDict(extra="ignore")

    product_id: str
    listing_id: Optional[str] = None
    variant_size: Optional[str] = None
    title: str
    description: Optional[str] = None
    brand: Optional[str] = None
    retailer: str
    retailer_name: Optional[str] = None
    product_url: str
    image_url: Optional[str] = None
    category: Optional[str] = None
    colours: List[str] = Field(default_factory=list)
    materials: List[str] = Field(default_factory=list)
    available_sizes: List[str] = Field(default_factory=list)
    price: Decimal = Field(ge=0)
    original_price: Optional[Decimal] = Field(default=None, ge=0)
    currency: str = "AUD"
    in_stock: Optional[bool] = None
    shipping_destination: Optional[str] = None
    shipping_cost: Optional[Decimal] = Field(default=None, ge=0)
    source_updated_at: Optional[datetime] = None
    retrieved_at: datetime = Field(default_factory=utcnow)
    stale_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    freshness: str = "fresh"
    match_score: float = 0.0
    match_reasons: List[str] = Field(default_factory=list)

    # ----------------------------------------------------------- validation
    @field_validator("title", "description", "brand", "category", "retailer_name", mode="before")
    @classmethod
    def _clean_text(cls, value: Any) -> Optional[str]:
        return sanitise_text(value)

    @field_validator("product_url", "image_url", mode="before")
    @classmethod
    def _clean_url(cls, value: Any) -> Optional[str]:
        return sanitise_url(value)

    @field_validator("colours", "materials", "available_sizes", mode="before")
    @classmethod
    def _clean_list(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = re.split(r"[,/|]", value)
        if not isinstance(value, (list, tuple, set)):
            return []
        out: List[str] = []
        for item in value:
            text = sanitise_text(item, limit=40)
            if text:
                lowered = text.lower()
                if lowered not in out:
                    out.append(lowered)
        return out[:30]

    @field_validator("price", "original_price", "shipping_cost", mode="before")
    @classmethod
    def _clean_money(cls, value: Any) -> Any:
        return _to_decimal(value)

    @field_validator("currency", mode="before")
    @classmethod
    def _clean_currency(cls, value: Any) -> str:
        code = str(value or "AUD").strip().upper()
        return code if re.fullmatch(r"[A-Z]{3}", code) else "AUD"

    @field_validator("match_score")
    @classmethod
    def _clamp_score(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @field_validator("source_updated_at", "retrieved_at", "stale_at", "expires_at", mode="before")
    @classmethod
    def _aware_datetime(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @field_serializer("price", "original_price", "shipping_cost")
    def _serialise_money(self, value: Optional[Decimal]) -> Optional[float]:
        return None if value is None else round(float(value), 2)

    # -------------------------------------------------------------- derived
    @computed_field  # type: ignore[prop-decorator]
    @property
    def discount_percent(self) -> Optional[int]:
        if self.original_price is None or self.original_price <= 0:
            return None
        if self.original_price <= self.price:
            return None
        return round((1 - (self.price / self.original_price)) * 100)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_price(self) -> float:
        """Listed price plus known shipping; unknown shipping is not a free-delivery claim."""
        return round(float(self.price + (self.shipping_cost or Decimal("0"))), 2)

    @property
    def uid(self) -> str:
        return f"{self.retailer}:{self.product_id}"


class ProductGroup(BaseModel):
    """One garment, with every retailer offer we found for it."""

    group_id: str
    primary: Product
    offers: List[Product]
    match_score: float = 0.0
    match_reasons: List[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def offer_count(self) -> int:
        return len(self.offers)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def retailers(self) -> List[str]:
        seen: List[str] = []
        for offer in self.offers:
            label = offer.retailer_name or offer.retailer
            if label not in seen:
                seen.append(label)
        return seen

    @computed_field  # type: ignore[prop-decorator]
    @property
    def lowest_total_price(self) -> float:
        """Cheapest price a shopper can actually buy at, including shipping.

        Out-of-stock offers are ignored unless nothing in the group is
        available - quoting a price you cannot buy is worse than no price.
        """
        purchasable = [offer.total_price for offer in self.offers if offer.in_stock]
        return min(purchasable) if purchasable else min(o.total_price for o in self.offers)


class RetailerStatus(BaseModel):
    """Per-retailer index coverage, surfaced in the UI while a search runs."""

    key: str
    name: str
    state: str = "pending"  # pending | running | completed | failed | skipped
    product_count: int = 0
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    attempts: int = 0

    @field_validator("error", mode="before")
    @classmethod
    def _clean_error(cls, value: Any) -> Optional[str]:
        return sanitise_text(value, limit=240)


class SearchResult(BaseModel):
    """The complete state of one search, cached and served to the client."""

    search_id: str
    intent: Dict[str, Any]
    query: str
    groups: List[ProductGroup] = Field(default_factory=list)
    retailers: List[RetailerStatus] = Field(default_factory=list)
    status: str = "running"  # running | completed | partial | failed
    cache_state: str = "index"
    total_products: int = 0
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: Optional[datetime] = None
    results_updated_at: Optional[datetime] = None
    warnings: List[str] = Field(default_factory=list)
