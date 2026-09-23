"""Relevance filtering over indexed retailer offers before ranking."""

from __future__ import annotations

from typing import Iterable

from app.models.intent import SearchIntent
from app.models.product import Product
from app.services.nlp.lexicon import (
    CATEGORY_SYNONYMS,
    COLOUR_SYNONYMS,
    MATERIAL_SYNONYMS,
    canonicalise,
    canonicalise_all,
    classify_category,
    content_tokens,
)


def _overlaps(left: Iterable[str], right: Iterable[str]) -> bool:
    return bool(set(left) & set(right))


def passes_coarse_filter(product: Product, intent: SearchIntent) -> bool:
    """True if ``product`` is worth ranking for ``intent``."""
    brand = (product.brand or "").lower()
    if brand and brand in intent.excluded_brands:
        return False

    haystack = " ".join(
        part for part in (product.title, product.description, product.category) if part
    ).lower()

    if intent.product_categories:
        # The stored category was classified from the title at import.
        product_category = canonicalise(product.category or "", CATEGORY_SYNONYMS)
        title_category = None if product_category else classify_category(product.title or "")
        candidates = {c for c in (product_category, title_category) if c}
        if candidates and not _overlaps(candidates, intent.product_categories):
            return False
        if not candidates:
            return False

    if intent.colours:
        colours = set(canonicalise_all(product.colours, COLOUR_SYNONYMS))
        if not colours:
            colours = {c for c in intent.colours if c in haystack}
        if not _overlaps(colours, intent.colours):
            return False

    if intent.materials:
        materials = set(canonicalise_all(product.materials, MATERIAL_SYNONYMS))
        if not materials:
            materials = {m for m in intent.materials if m in haystack}
        if not _overlaps(materials, intent.materials):
            return False

    if not (intent.product_categories or intent.colours or intent.materials or intent.brands):
        # Nothing structural to filter on - fall back to keyword overlap so a
        # bare "summer wedding" query still narrows the feed a little.
        keywords = set(intent.all_keywords()) | set(intent.brands)
        if keywords:
            tokens = set(content_tokens(haystack))
            if not any(any(part in tokens for part in kw.split()) for kw in keywords):
                return False

    return True
