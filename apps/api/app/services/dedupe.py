"""Duplicate detection across retailers.

The same garment is routinely listed by several retailers with slightly
different titles and prices. We group those offers so the shopper sees one
card per garment with the cheapest available option first, rather than the
same shirt five times.

Matching is deterministic and explainable - normalised brand, normalised
title, model/SKU identifier, colour and image fingerprint. No embeddings, no
model calls.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Tuple

from app.models.product import Product, ProductGroup
from app.services.nlp.lexicon import COLOUR_SYNONYMS, SIZE_ALIASES, canonicalise_all

_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")
_LEGAL_SUFFIX = re.compile(r"\b(ltd|limited|inc|llc|co|company|pty|gmbh|sa|bv)\b")
# Tokens that describe a variant rather than the garment itself.
_NOISE_TOKENS = {
    "mens",
    "men",
    "man",
    "male",
    "unisex",
    "the",
    "a",
    "an",
    "and",
    "in",
    "with",
    "new",
    "season",
    "ss",
    "aw",
    "fw",
    "collection",
    "edition",
    "size",
    "fit",
    "colour",
    "color",
    "style",
    "online",
    "exclusive",
    "sale",
}
_NOISE_TOKENS |= set(SIZE_ALIASES.keys()) | set(SIZE_ALIASES.values())

_MODEL_ID = re.compile(
    r"\b(?=[A-Za-z0-9-]*\d)[A-Za-z]{2,}[-_]?[A-Za-z0-9]{2,}(?:[-_][A-Za-z0-9]{2,})+\b"
)
_IMAGE_FILE = re.compile(r"/([^/?#]+)(?:\?|#|$)")


def normalise_brand(brand: Optional[str]) -> str:
    if not brand:
        return ""
    text = _PUNCT.sub(" ", brand.lower())
    text = _LEGAL_SUFFIX.sub(" ", text)
    return _WS.sub(" ", text).strip()


def normalise_title(title: str, brand: Optional[str], colours: List[str]) -> str:
    """Title reduced to the tokens that identify the garment itself."""
    text = _PUNCT.sub(" ", (title or "").lower())
    brand_tokens = set(normalise_brand(brand).split())
    colour_tokens = set()
    for colour in canonicalise_all(colours or [], COLOUR_SYNONYMS):
        colour_tokens.update(colour.split())
        colour_tokens.update(COLOUR_SYNONYMS.get(colour, set()))
    tokens = [
        token
        for token in text.split()
        if token
        and token not in brand_tokens
        and token not in colour_tokens
        and token not in _NOISE_TOKENS
        and not token.isdigit()
    ]
    return " ".join(sorted(set(tokens)))


def extract_model_id(product: Product) -> Optional[str]:
    """A SKU-like identifier, if the retailer exposed one we can compare."""
    for candidate in (product.title or "", product.product_id or ""):
        match = _MODEL_ID.search(candidate)
        if match:
            value = re.sub(r"[^A-Za-z0-9]", "", match.group(0)).upper()
            if len(value) >= 6 and any(ch.isdigit() for ch in value):
                return value
    return None


def image_fingerprint(image_url: Optional[str]) -> Optional[str]:
    """Filename portion of an image URL - identical across retailers when they
    syndicate the brand's own imagery."""
    if not image_url:
        return None
    match = _IMAGE_FILE.search(image_url)
    if not match:
        return None
    name = match.group(1).rsplit(".", 1)[0].lower()
    name = re.sub(r"[^a-z0-9]", "", name)
    if len(name) < 6 or name in {"product", "image", "default", "placeholder"}:
        return None
    return name


def _primary_colour(product: Product) -> str:
    colours = canonicalise_all(product.colours, COLOUR_SYNONYMS)
    return colours[0] if colours else ""


def identity_keys(product: Product) -> List[Tuple[str, str]]:
    """Every key that, if shared, means two offers are the same garment."""
    keys: List[Tuple[str, str]] = []

    brand = normalise_brand(product.brand)
    title = normalise_title(product.title, product.brand, product.colours)
    if brand and title:
        keys.append(("brand_title", f"{brand}|{title}|{_primary_colour(product)}"))

    model_id = extract_model_id(product)
    if model_id:
        keys.append(("model", model_id))

    fingerprint = image_fingerprint(product.image_url)
    if fingerprint:
        keys.append(("image", fingerprint))

    return keys


class _UnionFind:
    def __init__(self) -> None:
        self._parent: Dict[int, int] = {}

    def find(self, item: int) -> int:
        parent = self._parent.setdefault(item, item)
        while parent != item:
            item, parent = parent, self._parent.setdefault(parent, parent)
        return item

    def union(self, left: int, right: int) -> None:
        root_left, root_right = self.find(left), self.find(right)
        if root_left != root_right:
            self._parent[root_right] = root_left


def _offer_sort_key(product: Product) -> Tuple[int, float, str]:
    # In-stock first, then cheapest including shipping, then a stable tiebreak.
    return (0 if product.in_stock else 1, product.total_price, product.uid)


def group_products(products: List[Product]) -> List[ProductGroup]:
    """Collapse offers for the same garment into :class:`ProductGroup` objects."""
    if not products:
        return []

    union = _UnionFind()
    seen_keys: Dict[Tuple[str, str], int] = {}
    for index, product in enumerate(products):
        union.find(index)
        for key in identity_keys(product):
            existing = seen_keys.get(key)
            if existing is None:
                seen_keys[key] = index
            else:
                union.union(existing, index)

    clusters: Dict[int, List[Product]] = {}
    for index, product in enumerate(products):
        clusters.setdefault(union.find(index), []).append(product)

    groups: List[ProductGroup] = []
    for members in clusters.values():
        # One retailer can legitimately list the same URL twice; keep one.
        unique: Dict[str, Product] = {}
        for product in members:
            existing = unique.get(product.uid)
            if existing is None or product.total_price < existing.total_price:
                unique[product.uid] = product
        offers = sorted(unique.values(), key=_offer_sort_key)
        primary = offers[0]
        groups.append(
            ProductGroup(
                group_id=group_id_for(primary),
                primary=primary,
                offers=offers,
                match_score=primary.match_score,
                match_reasons=list(primary.match_reasons),
            )
        )
    return groups


def group_id_for(product: Product) -> str:
    brand = normalise_brand(product.brand)
    title = normalise_title(product.title, product.brand, product.colours)
    seed = f"{brand}|{title}|{_primary_colour(product)}" if brand and title else product.uid
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def merge_groups(existing: List[ProductGroup], incoming: List[ProductGroup]) -> List[ProductGroup]:
    """Re-group an accumulated result set with newly arrived products.

    Used as retailers respond one at a time: flattening and re-grouping keeps
    the result identical to a single batch run, which keeps streaming honest.
    """
    products: List[Product] = []
    for group in list(existing) + list(incoming):
        products.extend(group.offers)
    return group_products(products)
