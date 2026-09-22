"""Transparent weighted ranking.

Every product is scored on the dimensions the shopper actually specified. A
dimension they did not mention contributes nothing and its weight is
redistributed, so "black linen shirt" is not penalised for saying nothing about
brand or size.

The score is deterministic: the same intent and the same product always produce
the same number and the same human-readable reasons. Embeddings are a planned
enhancement (see ``docs/limitations.md``), not a hidden dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from app.models.intent import SearchIntent, SortPreference
from app.models.product import Product, ProductGroup
from app.services.currency import comparable_amount
from app.services.nlp.lexicon import (
    CATEGORY_SYNONYMS,
    COLOUR_SYNONYMS,
    FIT_SYNONYMS,
    MATERIAL_SYNONYMS,
    canonicalise,
    canonicalise_all,
    content_tokens,
    find_terms,
    normalise_size,
)


@dataclass(frozen=True)
class RankingWeights:
    """Relative importance of each scoring dimension.

    Exposed via ``GET /api/ranking`` so the ranking is inspectable rather than
    a black box.
    """

    keyword: float = 0.25
    category: float = 0.12
    price: float = 0.13
    colour: float = 0.09
    material: float = 0.07
    fit: float = 0.06
    size: float = 0.08
    brand: float = 0.06
    shipping: float = 0.07
    stock: float = 0.07

    def as_dict(self) -> dict:
        return {
            "keyword_relevance": self.keyword,
            "category_match": self.category,
            "price_fit": self.price,
            "colour_match": self.colour,
            "material_match": self.material,
            "fit_match": self.fit,
            "size_availability": self.size,
            "brand_preference": self.brand,
            "shipping_availability": self.shipping,
            "stock_status": self.stock,
        }


DEFAULT_WEIGHTS = RankingWeights()

# Price tolerance: an item this far above the stated maximum is still shown,
# flagged as slightly over, because shoppers routinely mean "about $120".
PRICE_TOLERANCE = Decimal("0.10")


def _sentence_case(text: str) -> str:
    """Upper-case the first letter only - `str.capitalize` would lower-case
    currency codes and place names in the rest of the phrase."""
    return text[:1].upper() + text[1:] if text else text


@dataclass
class Dimension:
    name: str
    weight: float
    score: float
    detail: Optional[str] = None


def _haystack(product: Product) -> str:
    parts = [product.title, product.description, product.brand, product.category]
    parts.extend(product.colours)
    parts.extend(product.materials)
    return " ".join(part for part in parts if part).lower()


def _keyword_score(product: Product, intent: SearchIntent) -> Tuple[float, List[str]]:
    keywords = intent.all_keywords()
    if not keywords:
        return (0.6, [])  # nothing to match against - neutral, not zero
    text = _haystack(product)
    tokens = set(content_tokens(text))
    matched: List[str] = []
    for keyword in keywords:
        parts = keyword.split()
        if all(part in tokens or part in text for part in parts):
            matched.append(keyword)
    return (len(matched) / len(keywords), matched)


def _category_score(product: Product, intent: SearchIntent) -> Tuple[float, Optional[str]]:
    wanted = intent.product_categories
    candidates = {
        c
        for c in (
            canonicalise(product.category or "", CATEGORY_SYNONYMS),
            canonicalise(product.title or "", CATEGORY_SYNONYMS),
        )
        if c
    }
    if not candidates:
        return (0.4, None)
    hit = candidates & set(wanted)
    if hit:
        return (1.0, sorted(hit)[0])
    return (0.0, None)


def _term_score(
    product_terms: Sequence[str], wanted: Sequence[str], text: str, table
) -> Tuple[float, List[str]]:
    canonical = set(canonicalise_all(list(product_terms), table))
    if not canonical:
        canonical = set(find_terms(text, table))
    hits = sorted(canonical & set(wanted))
    if not wanted:
        return (0.5, [])
    return (len(hits) / len(wanted), hits)


def _price_score(product: Product, intent: SearchIntent) -> Tuple[float, Optional[str]]:
    price = comparable_amount(product.price, product.currency, intent.currency)
    if price is None:
        return (0.5, None)  # currencies not comparable - stay neutral
    minimum = intent.minimum_price
    maximum = intent.maximum_price
    if maximum is not None and price > maximum:
        over = (price - maximum) / maximum
        return (max(0.0, float(1 - (over / PRICE_TOLERANCE))) * 0.5, "slightly over budget")
    if minimum is not None and price < minimum:
        return (0.4, None)
    if maximum is not None:
        # Comfortably under budget scores best; right at the limit still passes.
        headroom = float((maximum - price) / maximum)
        return (min(1.0, 0.7 + headroom), f"under your {intent.currency} {maximum:.0f} budget")
    return (0.7, None)


def _size_score(product: Product, intent: SearchIntent) -> Tuple[float, Optional[str]]:
    wanted = normalise_size(intent.size or "")
    if not wanted:
        return (0.5, None)
    if not product.available_sizes:
        return (0.35, None)  # unknown, not absent
    available = {normalise_size(size) for size in product.available_sizes}
    if wanted in available:
        return (1.0, f"size {wanted.upper()} available")
    return (0.0, None)


def _brand_score(product: Product, intent: SearchIntent) -> Tuple[float, Optional[str]]:
    brand = (product.brand or "").lower()
    if not intent.brands:
        return (0.5, None)
    if brand and any(wanted in brand or brand in wanted for wanted in intent.brands):
        return (1.0, product.brand)
    return (0.25, None)


def _shipping_score(product: Product, intent: SearchIntent) -> Tuple[float, Optional[str]]:
    destination = product.shipping_destination
    if not destination:
        return (0.5, None)
    if destination.upper() == intent.destination_country.upper():
        label = intent.destination_city or intent.destination_country
        return (1.0, f"ships to {label}")
    return (0.1, None)


def score_product(
    product: Product, intent: SearchIntent, weights: RankingWeights = DEFAULT_WEIGHTS
) -> Tuple[float, List[str]]:
    """Return ``(score, reasons)`` for one product."""
    text = _haystack(product)
    dimensions: List[Dimension] = []
    matched_attributes: List[str] = []
    extra_reasons: List[str] = []

    keyword_score, matched_keywords = _keyword_score(product, intent)
    dimensions.append(Dimension("keyword", weights.keyword, keyword_score))

    if intent.product_categories:
        score, detail = _category_score(product, intent)
        dimensions.append(Dimension("category", weights.category, score))
        if detail:
            matched_attributes.append(detail)

    if intent.colours:
        score, hits = _term_score(product.colours, intent.colours, text, COLOUR_SYNONYMS)
        dimensions.append(Dimension("colour", weights.colour, score))
        matched_attributes.extend(f"{hit} colour" for hit in hits)

    if intent.materials:
        score, hits = _term_score(product.materials, intent.materials, text, MATERIAL_SYNONYMS)
        dimensions.append(Dimension("material", weights.material, score))
        matched_attributes.extend(f"{hit} material" for hit in hits)

    if intent.fits:
        score, hits = _term_score([], intent.fits, text, FIT_SYNONYMS)
        dimensions.append(Dimension("fit", weights.fit, score))
        matched_attributes.extend(f"{hit} fit" for hit in hits)

    if intent.minimum_price is not None or intent.maximum_price is not None:
        score, detail = _price_score(product, intent)
        dimensions.append(Dimension("price", weights.price, score))
        if detail:
            extra_reasons.append(_sentence_case(detail))

    if intent.size:
        score, detail = _size_score(product, intent)
        dimensions.append(Dimension("size", weights.size, score))
        if detail:
            extra_reasons.append(_sentence_case(detail))

    if intent.brands:
        score, detail = _brand_score(product, intent)
        dimensions.append(Dimension("brand", weights.brand, score))
        if detail:
            extra_reasons.append(f"From {detail}")

    if product.shipping_destination:
        score, detail = _shipping_score(product, intent)
        dimensions.append(Dimension("shipping", weights.shipping, score))
        if detail:
            extra_reasons.append(_sentence_case(detail))

    dimensions.append(Dimension("stock", weights.stock, 1.0 if product.in_stock else 0.15))
    if not product.in_stock:
        extra_reasons.append("Currently out of stock")

    total_weight = sum(d.weight for d in dimensions) or 1.0
    score = sum(d.weight * d.score for d in dimensions) / total_weight

    if product.discount_percent and product.discount_percent >= 10:
        extra_reasons.append(f"{product.discount_percent}% off")

    reasons = _build_reasons(matched_attributes, matched_keywords, extra_reasons, intent)
    return (round(min(1.0, max(0.0, score)), 4), reasons)


def _build_reasons(
    matched_attributes: List[str],
    matched_keywords: List[str],
    extra_reasons: List[str],
    intent: SearchIntent,
) -> List[str]:
    reasons: List[str] = []
    attributes = list(dict.fromkeys(matched_attributes))
    if attributes:
        if len(attributes) == 1:
            phrase = attributes[0]
        else:
            phrase = ", ".join(attributes[:-1]) + " and " + attributes[-1]
        reasons.append(f"Matches your requested {phrase}.")
    elif matched_keywords:
        reasons.append(f"Matches “{matched_keywords[0]}” from your search.")
    elif not intent.all_keywords():
        reasons.append("Popular menswear pick for this search.")

    for reason in extra_reasons:
        if reason not in reasons:
            reasons.append(reason)
    return reasons[:4]


# --------------------------------------------------------------------------
# Hard filters - constraints a shopper states as requirements, not preferences
# --------------------------------------------------------------------------


def passes_hard_filters(product: Product, intent: SearchIntent) -> bool:
    brand = (product.brand or "").lower()
    if brand and any(excluded in brand for excluded in intent.excluded_brands):
        return False
    if product.retailer in intent.excluded_brands:
        return False

    price = comparable_amount(product.price, product.currency, intent.currency)
    if price is None:
        return True  # cannot compare currencies - do not silently exclude
    if intent.maximum_price is not None and price > intent.maximum_price * (1 + PRICE_TOLERANCE):
        return False
    return not (intent.minimum_price is not None and price < intent.minimum_price * Decimal("0.75"))


def filter_products(products: List[Product], intent: SearchIntent) -> List[Product]:
    return [product for product in products if passes_hard_filters(product, intent)]


# --------------------------------------------------------------------------
# Group-level ranking
# --------------------------------------------------------------------------


def _group_sort_key(group: ProductGroup, intent: SearchIntent):
    primary = group.primary
    if intent.sort_preference == SortPreference.PRICE_LOW_TO_HIGH:
        return (group.lowest_total_price, -group.match_score)
    if intent.sort_preference == SortPreference.BIGGEST_DISCOUNT:
        best_discount = max((offer.discount_percent or 0) for offer in group.offers)
        return (-best_discount, -group.match_score)
    if intent.sort_preference == SortPreference.NEWEST:
        newest = max((offer.source_updated_at or offer.retrieved_at) for offer in group.offers)
        return (-newest.timestamp(), -group.match_score)
    return (-group.match_score, group.lowest_total_price, primary.uid)


def rank_groups(
    groups: List[ProductGroup],
    intent: SearchIntent,
    weights: RankingWeights = DEFAULT_WEIGHTS,
    limit: Optional[int] = None,
) -> List[ProductGroup]:
    """Score every offer, promote the best-scoring one, and sort the groups."""
    for group in groups:
        best_score = 0.0
        best_reasons: List[str] = []
        for offer in group.offers:
            score, reasons = score_product(offer, intent, weights)
            offer.match_score = score
            offer.match_reasons = reasons
            if score > best_score:
                best_score = score
                best_reasons = reasons
        group.match_score = best_score
        group.match_reasons = best_reasons
        if group.offer_count > 1:
            cheapest = group.offers[0]
            label = cheapest.retailer_name or cheapest.retailer
            note = f"Cheapest of {group.offer_count} retailers ({label})."
            if note not in group.match_reasons:
                group.match_reasons = [*group.match_reasons, note][:4]

    ranked = sorted(groups, key=lambda g: _group_sort_key(g, intent))
    return ranked[:limit] if limit else ranked
