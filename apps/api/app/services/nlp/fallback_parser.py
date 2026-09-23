"""Deterministic natural-language parser.

Used whenever the Anthropic API is unavailable, disabled, too slow, or when a
query trips the prompt-injection heuristics. It is pure, synchronous and fully
unit-tested, so the product keeps working without an LLM - the LLM makes
parsing *better*, it is not load-bearing.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import List, Optional, Tuple

from app.models.intent import (
    DEFAULT_CITY,
    DEFAULT_COUNTRY,
    DEFAULT_CURRENCY,
    Gender,
    SearchIntent,
    SortPreference,
)
from app.services.nlp.lexicon import (
    BRAND_STYLE_HINTS,
    CATEGORY_SYNONYMS,
    CITY_COUNTRY,
    COLOUR_SYNONYMS,
    COUNTRY_NAMES,
    CURRENCY_CODES,
    CURRENCY_SYMBOLS,
    FIT_SYNONYMS,
    MATERIAL_SYNONYMS,
    OCCASION_TERMS,
    SEASON_TERMS,
    STOPWORDS,
    STYLE_TERMS,
    content_tokens,
    find_terms,
    normalise_size,
)

_AMOUNT = r"(?:\$|£|€|¥)?\s?(\d[\d,]*(?:\.\d{1,2})?)\s?(k\b)?"

_RANGE_PATTERNS = [
    re.compile(r"\bbetween\s+" + _AMOUNT + r"\s+and\s+" + _AMOUNT, re.I),
    # The en dashes in these patterns are intentional: shoppers paste price
    # ranges straight out of retailer pages, which use them.
    re.compile(r"\bfrom\s+" + _AMOUNT + r"\s+(?:to|-|–)\s+" + _AMOUNT, re.I),  # noqa: RUF001
    re.compile(_AMOUNT + r"\s*(?:-|–|to)\s*" + _AMOUNT, re.I),  # noqa: RUF001
]
_MAX_PATTERNS = [
    re.compile(
        r"\b(?:under|below|less than|lower than|no more than|up to|max(?:imum)?|"
        r"within|budget of|budget)\s+(?:of\s+)?" + _AMOUNT,
        re.I,
    ),
    re.compile(_AMOUNT + r"\s*(?:or less|or under|max)\b", re.I),
]
_MIN_PATTERNS = [
    re.compile(
        r"\b(?:over|above|more than|at least|min(?:imum)?|starting (?:at|from))\s+" + _AMOUNT,
        re.I,
    ),
]
_APPROX_PATTERNS = [
    re.compile(r"\b(?:around|about|approximately|circa|roughly|near)\s+" + _AMOUNT, re.I),
]

_SIZE_PATTERNS = [
    re.compile(r"\bsize\s+(x?x?x?s|m|small|medium|med|large|x?x?x?l|\d{1,3})\b", re.I),
    re.compile(r"\b(?:in|a)\s+(xs|x-small|small|medium|large|xl|xxl|x-large)\b", re.I),
    re.compile(r"\b(\d{2})\s*(?:inch|in|\")?\s*waist\b", re.I),
    re.compile(r"\bw(\d{2})\b", re.I),
    re.compile(r"\b(xs|s|m|l|xl|xxl|xxxl)\s+size\b", re.I),
]

_BRAND_PREFERENCE_TRIGGERS = re.compile(
    r"\b(?:from|by|at|stocked at)\s+([A-Z][\w&'.-]*(?:\s+[A-Z][\w&'.-]*){0,2})", re.U
)
_BRAND_SIMILARITY_TRIGGERS = re.compile(
    r"\b(?:similar to|like|in the style of|such as|vibe of|alternative to|dupe for)\s+"
    r"([A-Z][\w&'.-]*(?:\s+[A-Z][\w&'.-]*){0,2})",
    re.U,
)
_BRAND_EXCLUSION_TRIGGERS = re.compile(
    r"\b(?:not|no|except|excluding|avoid|without|other than|apart from)\s+"
    r"([A-Z][\w&'.-]*(?:\s+[A-Z][\w&'.-]*){0,2})",
    re.U,
)

# Capitalised words that are never brands.
_BRAND_BLOCKLIST = {
    "i",
    "find",
    "me",
    "a",
    "an",
    "the",
    "show",
    "looking",
    "need",
    "want",
    "sydney",
    "melbourne",
    "brisbane",
    "perth",
    "adelaide",
    "australia",
    "london",
    "new york",
    "nyc",
    "singapore",
    "auckland",
    "canada",
    "japan",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "summer",
    "winter",
    "autumn",
    "spring",
    "aud",
    "usd",
    "gbp",
    "eur",
    "black",
    "white",
    "cream",
    "navy",
    "grey",
    "gray",
    "beige",
    "olive",
    "medium",
    "small",
    "large",
}

_DESTINATION_TRIGGER = re.compile(
    r"\b(?:ships?\s+to|shipping\s+to|deliver(?:ed|y)?\s+to|send\s+to|to)\s+"
    r"([A-Za-z][A-Za-z\s]{2,30}?)(?=\b(?:\s+(?:and|with|under|for|in|that|which)\b)|[,.;]|$)",
    re.I,
)
_POSTCODE = re.compile(
    r"\b(?:postcode|post code|zip(?:\s?code)?|ships? to|deliver(?:y)? to)\s+([A-Za-z0-9]{3,8})\b",
    re.I,
)

_CHEAP_HINTS = re.compile(
    r"\b(cheap|cheaper|cheapest|affordable|budget|bargain|best price)\b", re.I
)
_DISCOUNT_HINTS = re.compile(
    r"\b(sale|discount|discounted|reduced|markdown|clearance|deal)\b", re.I
)
_NEWEST_HINTS = re.compile(r"\b(new in|newest|latest|just dropped|new arrivals?)\b", re.I)

_WOMEN_HINTS = re.compile(r"\b(women'?s?|womens|female|ladies|her)\b", re.I)
_UNISEX_HINTS = re.compile(r"\b(unisex|gender[- ]neutral)\b", re.I)


def _to_amount(digits: str, thousands: Optional[str]) -> Decimal:
    value = Decimal(digits.replace(",", ""))
    if thousands:
        value *= 1000
    return value


def _extract_prices(
    text: str,
) -> Tuple[Optional[Decimal], Optional[Decimal], List[Tuple[int, int]]]:
    """Return (minimum, maximum, consumed spans)."""
    spans: List[Tuple[int, int]] = []

    for pattern in _RANGE_PATTERNS:
        match = pattern.search(text)
        if match:
            low = _to_amount(match.group(1), match.group(2))
            high = _to_amount(match.group(3), match.group(4))
            spans.append(match.span())
            return (min(low, high), max(low, high), spans)

    minimum: Optional[Decimal] = None
    maximum: Optional[Decimal] = None

    for pattern in _MAX_PATTERNS:
        match = pattern.search(text)
        if match:
            maximum = _to_amount(match.group(1), match.group(2))
            spans.append(match.span())
            break

    for pattern in _MIN_PATTERNS:
        match = pattern.search(text)
        if match:
            minimum = _to_amount(match.group(1), match.group(2))
            spans.append(match.span())
            break

    if minimum is None and maximum is None:
        for pattern in _APPROX_PATTERNS:
            match = pattern.search(text)
            if match:
                target = _to_amount(match.group(1), match.group(2))
                minimum = (target * Decimal("0.8")).quantize(Decimal("1"))
                maximum = (target * Decimal("1.2")).quantize(Decimal("1"))
                spans.append(match.span())
                break

    return (minimum, maximum, spans)


def _extract_currency(text: str) -> str:
    for code in CURRENCY_CODES:
        if re.search(r"(?<![a-z])" + code + r"(?![a-z])", text, re.I):
            return code.upper()
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    return DEFAULT_CURRENCY


def _extract_size(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int]]]:
    """Return (normalised size, the span it was found in)."""
    for pattern in _SIZE_PATTERNS:
        match = pattern.search(text)
        if match:
            size = normalise_size(match.group(1))
            if size:
                return (size, match.span())
    return (None, None)


def _clean_brand(candidate: str) -> Optional[str]:
    brand = re.sub(r"[^\w&'.\- ]", " ", candidate).strip()
    brand = re.sub(r"\s+", " ", brand)
    if not brand:
        return None
    lowered = brand.lower()
    if lowered in _BRAND_BLOCKLIST:
        return None
    # Drop trailing filler words that the greedy capture picked up.
    words = [w for w in brand.split(" ") if w.lower() not in STOPWORDS | _BRAND_BLOCKLIST]
    if not words:
        return None
    brand = " ".join(words)
    if len(brand) < 2 or len(brand) > 40:
        return None
    return brand.lower()


def _extract_brands(original: str) -> Tuple[List[str], List[str], List[str]]:
    """Return (preferred_brands, excluded_brands, style_hints)."""
    preferred: List[str] = []
    excluded: List[str] = []
    hints: List[str] = []

    for match in _BRAND_EXCLUSION_TRIGGERS.finditer(original):
        brand = _clean_brand(match.group(1))
        if brand and brand not in excluded:
            excluded.append(brand)

    for match in _BRAND_SIMILARITY_TRIGGERS.finditer(original):
        brand = _clean_brand(match.group(1))
        if not brand:
            continue
        # "similar to X" is a style request, not a brand filter: filtering to X
        # would exclude exactly the cheaper alternatives the shopper wants.
        for hint in BRAND_STYLE_HINTS.get(brand, []):
            if hint not in hints:
                hints.append(hint)
        if brand not in BRAND_STYLE_HINTS and brand not in hints:
            hints.append(brand)

    for match in _BRAND_PREFERENCE_TRIGGERS.finditer(original):
        brand = _clean_brand(match.group(1))
        if brand and brand not in preferred and brand not in excluded:
            preferred.append(brand)

    return (preferred, excluded, hints)


def _extract_destination(text: str, original: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Return (country_code, city, postcode)."""
    country = DEFAULT_COUNTRY
    city: Optional[str] = None
    postcode: Optional[str] = None

    postcode_match = _POSTCODE.search(original)
    if postcode_match:
        candidate = postcode_match.group(1)
        if any(ch.isdigit() for ch in candidate):
            postcode = candidate.upper()

    for name, code in COUNTRY_NAMES.items():
        if re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text, re.I):
            country = code
            break

    for match in _DESTINATION_TRIGGER.finditer(original):
        candidate = match.group(1).strip().lower()
        candidate = re.sub(r"\b(that|which|and|with|for|in)\b", " ", candidate).strip()
        if candidate in CITY_COUNTRY:
            city = candidate.title()
            country = CITY_COUNTRY[candidate]
            break
        if candidate in COUNTRY_NAMES:
            country = COUNTRY_NAMES[candidate]
            break

    if city is None:
        for name, code in CITY_COUNTRY.items():
            if re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text, re.I):
                city = name.title()
                country = code
                break

    if city is None and country == DEFAULT_COUNTRY:
        city = DEFAULT_CITY

    return (country, city, postcode)


def _extract_sort(text: str, has_max_price: bool) -> SortPreference:
    if _DISCOUNT_HINTS.search(text):
        return SortPreference.BIGGEST_DISCOUNT
    if _NEWEST_HINTS.search(text):
        return SortPreference.NEWEST
    if _CHEAP_HINTS.search(text):
        return SortPreference.PRICE_LOW_TO_HIGH
    if has_max_price and re.search(r"\bcheap|\bvalue\b", text, re.I):
        return SortPreference.PRICE_LOW_TO_HIGH
    return SortPreference.RELEVANCE


def _extract_gender(text: str) -> Gender:
    if _UNISEX_HINTS.search(text):
        return Gender.UNISEX
    if _WOMEN_HINTS.search(text):
        return Gender.WOMEN
    return Gender.MEN


def parse_query(query: str) -> SearchIntent:
    """Convert a shopper's sentence into a :class:`SearchIntent`, no LLM required.

    ``query`` is expected to have passed :func:`app.services.nlp.sanitise.normalise_query`.
    """
    original = (query or "").strip()
    if not original:
        raise ValueError("query must not be empty")
    lowered = original.lower()

    minimum, maximum, price_spans = _extract_prices(lowered)

    # Remove matched price text so "$120" cannot be mistaken for a size.
    residual = lowered
    for start, end in sorted(price_spans, reverse=True):
        residual = residual[:start] + " " + residual[end:]

    size, size_span = _extract_size(residual)
    if size_span:
        residual = residual[: size_span[0]] + " " + residual[size_span[1] :]

    categories = find_terms(residual, CATEGORY_SYNONYMS)
    colours = find_terms(residual, COLOUR_SYNONYMS)
    materials = find_terms(residual, MATERIAL_SYNONYMS)
    fits = find_terms(residual, FIT_SYNONYMS)
    styles = find_terms(residual, STYLE_TERMS)
    occasions = find_terms(residual, OCCASION_TERMS)
    seasons = find_terms(residual, SEASON_TERMS)

    preferred_brands, excluded_brands, brand_style_hints = _extract_brands(original)
    for hint in brand_style_hints:
        if hint not in styles:
            styles.append(hint)

    country, city, postcode = _extract_destination(lowered, original)

    # Tokens already represented by a structured field must not be repeated as
    # loose keywords - including the alias the shopper actually typed
    # ("jumper" when we recorded the canonical category "knitwear").
    matched = set()
    for group, table in (
        (categories, CATEGORY_SYNONYMS),
        (colours, COLOUR_SYNONYMS),
        (materials, MATERIAL_SYNONYMS),
        (fits, FIT_SYNONYMS),
        (styles, STYLE_TERMS),
        (occasions, OCCASION_TERMS),
        (seasons, SEASON_TERMS),
    ):
        for term in group:
            matched.update(term.split())
            for alias in table.get(term, set()):
                matched.update(alias.split())
    for brand in preferred_brands + excluded_brands:
        matched.update(brand.split())
    if city:
        matched.update(city.lower().split())

    keywords = [
        token
        for token in content_tokens(residual)
        if token not in matched and token not in STOPWORDS
    ][:6]
    for season in seasons:
        if season not in keywords:
            keywords.insert(0, season)

    return SearchIntent(
        original_query=original,
        product_categories=categories,
        occasion=occasions[0] if occasions else None,
        styles=styles,
        colours=colours,
        materials=materials,
        fits=fits,
        brands=preferred_brands,
        excluded_brands=excluded_brands,
        size=size,
        minimum_price=minimum,
        maximum_price=maximum,
        currency=_extract_currency(original),
        destination_country=country,
        destination_postcode=postcode,
        destination_city=city,
        gender=_extract_gender(lowered),
        sort_preference=_extract_sort(lowered, maximum is not None),
        additional_keywords=keywords[:8],
    )
