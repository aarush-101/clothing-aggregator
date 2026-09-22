"""The structured representation of a natural-language search."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

DEFAULT_GENDER = "men"
DEFAULT_CURRENCY = "AUD"
DEFAULT_COUNTRY = "AU"
DEFAULT_CITY = "Sydney"

_WHITESPACE = re.compile(r"\s+")
_MAX_LIST_ITEMS = 12
_MAX_TERM_LENGTH = 60


class SortPreference(str, Enum):
    RELEVANCE = "relevance"
    PRICE_LOW_TO_HIGH = "price_low_to_high"
    BIGGEST_DISCOUNT = "biggest_discount"
    NEWEST = "newest"


class Gender(str, Enum):
    MEN = "men"
    WOMEN = "women"
    UNISEX = "unisex"


def _clean_term(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = _WHITESPACE.sub(" ", str(value)).strip().lower()
    if not text:
        return None
    return text[:_MAX_TERM_LENGTH]


def _clean_terms(values: Any) -> List[str]:
    """Lowercase, de-duplicate and bound a list of free-text terms."""
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    seen: List[str] = []
    for raw in values:
        term = _clean_term(raw)
        if term and term not in seen:
            seen.append(term)
        if len(seen) >= _MAX_LIST_ITEMS:
            break
    return seen


class SearchIntent(BaseModel):
    """Structured filters derived from a shopper's sentence.

    This is the single source of truth for what the user asked for: connectors
    decide relevance from it, the ranker scores against it, and its normalised
    fingerprint is the cache key.
    """

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    original_query: str = Field(min_length=1, max_length=2000)
    product_categories: List[str] = Field(default_factory=list)
    occasion: Optional[str] = None
    styles: List[str] = Field(default_factory=list)
    colours: List[str] = Field(default_factory=list)
    materials: List[str] = Field(default_factory=list)
    fits: List[str] = Field(default_factory=list)
    brands: List[str] = Field(default_factory=list)
    excluded_brands: List[str] = Field(default_factory=list)
    size: Optional[str] = None
    minimum_price: Optional[Decimal] = Field(default=None, ge=0)
    maximum_price: Optional[Decimal] = Field(default=None, ge=0)
    currency: str = DEFAULT_CURRENCY
    destination_country: str = DEFAULT_COUNTRY
    destination_postcode: Optional[str] = None
    destination_city: Optional[str] = DEFAULT_CITY
    gender: Gender = Gender.MEN
    sort_preference: SortPreference = SortPreference.RELEVANCE
    additional_keywords: List[str] = Field(default_factory=list)

    # ----------------------------------------------------------- validation
    @field_validator(
        "product_categories",
        "styles",
        "colours",
        "materials",
        "fits",
        "brands",
        "excluded_brands",
        "additional_keywords",
        mode="before",
    )
    @classmethod
    def _normalise_lists(cls, value: Any) -> List[str]:
        return _clean_terms(value)

    @field_validator("occasion", "size", mode="before")
    @classmethod
    def _normalise_optional_terms(cls, value: Any) -> Optional[str]:
        return _clean_term(value)

    @field_validator("original_query", mode="before")
    @classmethod
    def _normalise_query(cls, value: Any) -> str:
        return _WHITESPACE.sub(" ", str(value or "")).strip()

    @field_validator("currency", mode="before")
    @classmethod
    def _normalise_currency(cls, value: Any) -> str:
        code = str(value or DEFAULT_CURRENCY).strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            return DEFAULT_CURRENCY
        return code

    @field_validator("destination_country", mode="before")
    @classmethod
    def _normalise_country(cls, value: Any) -> str:
        code = str(value or DEFAULT_COUNTRY).strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", code):
            return DEFAULT_COUNTRY
        return code

    @field_validator("destination_postcode", mode="before")
    @classmethod
    def _normalise_postcode(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        code = re.sub(r"[^A-Za-z0-9 ]", "", str(value)).strip().upper()
        return code[:12] or None

    @field_validator("destination_city", mode="before")
    @classmethod
    def _normalise_city(cls, value: Any) -> Optional[str]:
        city = _clean_term(value)
        if not city:
            return None
        return city.title()

    @field_validator("gender", mode="before")
    @classmethod
    def _normalise_gender(cls, value: Any) -> Any:
        if value is None:
            return Gender.MEN
        if isinstance(value, Gender):
            return value
        text = str(value).strip().lower()
        aliases = {
            "man": "men", "mens": "men", "men's": "men", "male": "men",
            "woman": "women", "womens": "women", "women's": "women", "female": "women",
            "any": "unisex", "all": "unisex", "neutral": "unisex",
        }
        return aliases.get(text, text)

    @field_validator("sort_preference", mode="before")
    @classmethod
    def _normalise_sort(cls, value: Any) -> Any:
        if value is None:
            return SortPreference.RELEVANCE
        if isinstance(value, SortPreference):
            return value
        text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "price": "price_low_to_high",
            "price_asc": "price_low_to_high",
            "lowest_price": "price_low_to_high",
            "cheapest": "price_low_to_high",
            "discount": "biggest_discount",
            "largest_discount": "biggest_discount",
            "biggest_discounts": "biggest_discount",
            "sale": "biggest_discount",
            "latest": "newest",
            "new": "newest",
        }
        text = aliases.get(text, text)
        if text not in {item.value for item in SortPreference}:
            return SortPreference.RELEVANCE
        return text

    @model_validator(mode="after")
    def _reconcile(self) -> SearchIntent:
        minimum = self.minimum_price
        maximum = self.maximum_price
        if minimum is not None and maximum is not None and minimum > maximum:
            # A model (or a user) occasionally inverts the bounds; trust the range.
            object.__setattr__(self, "minimum_price", maximum)
            object.__setattr__(self, "maximum_price", minimum)
        # A brand cannot be both wanted and excluded - exclusion wins.
        if self.brands and self.excluded_brands:
            excluded = set(self.excluded_brands)
            object.__setattr__(self, "brands", [b for b in self.brands if b not in excluded])
        return self

    @field_serializer("minimum_price", "maximum_price")
    def _serialise_price(self, value: Optional[Decimal]) -> Optional[float]:
        return None if value is None else float(value)

    # ------------------------------------------------------------- helpers
    def normalised_payload(self) -> Dict[str, Any]:
        """Canonical dict used for cache fingerprinting.

        The raw sentence is deliberately excluded so that two differently
        worded queries with identical meaning share a cache entry.
        """
        def money(value: Optional[Decimal]) -> Optional[str]:
            return None if value is None else format(Decimal(value).quantize(Decimal("0.01")), "f")

        return {
            "product_categories": sorted(self.product_categories),
            "occasion": self.occasion,
            "styles": sorted(self.styles),
            "colours": sorted(self.colours),
            "materials": sorted(self.materials),
            "fits": sorted(self.fits),
            "brands": sorted(self.brands),
            "excluded_brands": sorted(self.excluded_brands),
            "size": self.size,
            "minimum_price": money(self.minimum_price),
            "maximum_price": money(self.maximum_price),
            "currency": self.currency,
            "destination_country": self.destination_country,
            "destination_postcode": self.destination_postcode,
            "gender": self.gender.value,
            "additional_keywords": sorted(self.additional_keywords),
        }

    def fingerprint(self) -> str:
        """Stable hash of the normalised intent (the results cache key)."""
        canonical = json.dumps(self.normalised_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    def all_keywords(self) -> List[str]:
        """Every descriptive term the shopper used, de-duplicated in order."""
        terms: List[str] = []
        for group in (
            self.product_categories,
            self.styles,
            self.colours,
            self.materials,
            self.fits,
            self.additional_keywords,
        ):
            for term in group:
                if term not in terms:
                    terms.append(term)
        if self.occasion and self.occasion not in terms:
            terms.append(self.occasion)
        return terms

    def describe(self) -> str:
        """Short human summary, used in logs and the UI fallback."""
        bits: List[str] = []
        if self.colours:
            bits.append("/".join(self.colours))
        if self.fits:
            bits.append("/".join(self.fits))
        if self.materials:
            bits.append("/".join(self.materials))
        bits.extend(self.product_categories or ["clothing"])
        summary = " ".join(bits)
        if self.maximum_price is not None:
            summary += f" under {self.currency} {float(self.maximum_price):.0f}"
        return summary
