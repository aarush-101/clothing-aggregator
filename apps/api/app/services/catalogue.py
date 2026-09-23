"""Persistent variant index and atomic, leased ingestion publication."""

from __future__ import annotations

import re
import time
import uuid
from datetime import timedelta
from typing import Dict, List, Optional

from sqlalchemy import delete, func, insert, not_, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.db.session import Database
from app.db.tables import CatalogueOffer, CatalogueSource, IngestionRun
from app.models.intent import SearchIntent
from app.models.product import Product, utcnow
from app.services.dedupe import normalise_brand, spelling_key
from app.services.filtering import passes_coarse_filter
from app.services.nlp.lexicon import (
    CATEGORY_SYNONYMS,
    COLOUR_SYNONYMS,
    FIT_SYNONYMS,
    MATERIAL_SYNONYMS,
    OCCASION_TERMS,
    SEASON_TERMS,
    STYLE_TERMS,
    expand_categories,
    normalise_size,
)
from app.services.ranking import passes_hard_filters
from app.sources.registry import Retailer

LEASE_SECONDS = 300
BRAND_CACHE_SECONDS = 60
_NEGATED = re.compile(
    r"\b(?:no|not|without|except|excluding|avoid|anything but|non)(?:\s+(?:from|by))?\s*$"
)
# A brand called "Linen" or "Black" must not turn every such query into a brand filter.
_VOCABULARY_TERMS = {
    term
    for table in (
        CATEGORY_SYNONYMS,
        COLOUR_SYNONYMS,
        MATERIAL_SYNONYMS,
        FIT_SYNONYMS,
        STYLE_TERMS,
        OCCASION_TERMS,
        SEASON_TERMS,
    )
    for canonical, aliases in table.items()
    for term in {canonical, *aliases}
}


def search_text(product: Product) -> str:
    """Lowercased text every relevance filter reads; a superset for SQL LIKE."""
    parts = [
        product.title,
        product.brand,
        product.category,
        " ".join(product.colours),
        " ".join(product.materials),
        product.description,
    ]
    return " " + " ".join(part for part in parts if part).lower() + " "


def _any_term(terms) -> Optional[object]:
    clauses = [
        CatalogueOffer.search_text.contains(term.lower(), autoescape=True) for term in terms if term
    ]
    return or_(*clauses) if clauses else None


def apply_freshness(product: Product) -> Product:
    if product.stale_at and product.stale_at <= utcnow():
        product.freshness = "stale"
        if product.in_stock is True:
            product.in_stock = None
        product.available_sizes = []
    return product


class Catalogue:
    def __init__(self, database: Database, retailers: List[Retailer], settings: Settings):
        self.database = database
        self.retailers = {r.key: r for r in retailers}
        self.settings = settings
        self._brands: Dict[str, List[str]] = {}
        self._brand_display: Dict[str, str] = {}
        self._brands_loaded = 0.0

    async def initialise(self) -> None:
        for key in self.retailers:
            # Concurrent API/worker boots may race; the unique key settles it.
            try:
                async with self.database.session() as session:
                    if await session.get(CatalogueSource, key) is None:
                        session.add(CatalogueSource(key=key))
            except IntegrityError:
                pass

    async def source_states(self) -> Dict[str, CatalogueSource]:
        async with self.database.session() as session:
            rows = (
                await session.scalars(
                    select(CatalogueSource).where(CatalogueSource.key.in_(self.retailers))
                )
            ).all()
            return {row.key: row for row in rows}

    async def claim(self, key: str, *, force: bool = False) -> Optional[str]:
        now = time.time()
        token = uuid.uuid4().hex
        async with self.database.session() as session:
            statement = update(CatalogueSource).where(
                CatalogueSource.key == key, CatalogueSource.lease_until <= now
            )
            if not force:
                statement = statement.where(CatalogueSource.next_due <= now)
            claimed = await session.execute(
                statement.values(
                    lease_token=token,
                    lease_until=now + LEASE_SECONDS,
                    state="running",
                    last_attempt=now,
                )
            )
            if not claimed.rowcount:
                return None
            await session.execute(
                update(IngestionRun)
                .where(IngestionRun.source_key == key, IngestionRun.state == "running")
                .values(state="abandoned", completed_at=now, error="Previous worker lease expired")
            )
            session.add(IngestionRun(id=token, source_key=key, started_at=now, state="running"))
        return token

    async def heartbeat(self, key: str, token: str) -> None:
        async with self.database.session() as session:
            result = await session.execute(
                update(CatalogueSource)
                .where(
                    CatalogueSource.key == key,
                    CatalogueSource.lease_token == token,
                    CatalogueSource.lease_until > time.time(),
                )
                .values(lease_until=time.time() + LEASE_SECONDS)
            )
            if not result.rowcount:
                raise RuntimeError("Ingestion lease expired")

    async def publish(self, key: str, token: str, products: List[Product]) -> bool:
        now = time.time()
        if len({p.product_id for p in products}) != len(products):
            raise ValueError("Snapshot contains duplicate variant ids")
        if any(p.retailer != key for p in products):
            raise ValueError("Snapshot contains another retailer's offers")
        rows = []
        for product in products:
            product.stale_at = product.retrieved_at + timedelta(
                seconds=self.settings.catalogue_stale_seconds
            )
            product.expires_at = product.retrieved_at + timedelta(
                seconds=self.settings.catalogue_expire_seconds
            )
            rows.append(
                {
                    "source_key": key,
                    "variant_id": product.product_id,
                    "category": product.category,
                    "expires_at": product.expires_at.timestamp(),
                    "price": float(product.price),
                    "currency": product.currency,
                    "in_stock": product.in_stock,
                    "size": normalise_size(product.variant_size or "") or None,
                    "brand": product.brand,
                    "search_text": search_text(product),
                    "payload": product.model_dump(mode="json"),
                }
            )
        async with self.database.session() as session:
            result = await session.execute(
                update(CatalogueSource)
                .where(
                    CatalogueSource.key == key,
                    CatalogueSource.lease_token == token,
                    CatalogueSource.lease_until > now,
                )
                .values(
                    state="ok",
                    lease_token=None,
                    lease_until=0,
                    next_due=now + self.retailers[key].ingestion.refresh_seconds,
                    last_success=now,
                    error=None,
                    offer_count=len(rows),
                )
            )
            if not result.rowcount:
                return False
            # Only a complete, validated snapshot reaches this transaction.
            await session.execute(delete(CatalogueOffer).where(CatalogueOffer.source_key == key))
            for start in range(0, len(rows), 250):
                await session.execute(insert(CatalogueOffer), rows[start : start + 250])
            await session.execute(
                update(IngestionRun)
                .where(IngestionRun.id == token)
                .values(state="completed", completed_at=now, offer_count=len(rows))
            )
        return True

    async def fail(
        self, key: str, token: str, error: str, retry_after: float, blocked: bool = False
    ) -> None:
        now = time.time()
        async with self.database.session() as session:
            result = await session.execute(
                update(CatalogueSource)
                .where(
                    CatalogueSource.key == key,
                    CatalogueSource.lease_token == token,
                    CatalogueSource.lease_until > now,
                )
                .values(
                    state="blocked" if blocked else "failed",
                    lease_token=None,
                    lease_until=0,
                    next_due=now + max(60, retry_after),
                    error=error[:400],
                )
            )
            if result.rowcount:
                await session.execute(
                    update(IngestionRun)
                    .where(IngestionRun.id == token)
                    .values(state="failed", completed_at=now, error=error[:400])
                )

    async def search(self, intent: SearchIntent) -> List[Product]:
        if intent.gender.value not in {"men", "unisex"}:
            return []
        if intent.product_categories:
            intent = intent.model_copy(
                update={"product_categories": expand_categories(intent.product_categories)}
            )
        statement = select(CatalogueOffer.payload).where(
            CatalogueOffer.source_key.in_(self.retailers),
            CatalogueOffer.expires_at > time.time(),
            or_(CatalogueOffer.in_stock.is_(None), CatalogueOffer.in_stock.is_(True)),
        )
        # SQL narrows to a superset of what the Python filters below accept.
        if intent.product_categories:
            statement = statement.where(CatalogueOffer.category.in_(intent.product_categories))
        if intent.size:
            statement = statement.where(
                CatalogueOffer.size == normalise_size(intent.size),
                CatalogueOffer.in_stock.is_(True),
            )
        if intent.maximum_price is not None:
            statement = statement.where(
                or_(
                    CatalogueOffer.currency != intent.currency,
                    CatalogueOffer.price <= float(intent.maximum_price),
                )
            )
        if intent.minimum_price is not None:
            statement = statement.where(
                or_(
                    CatalogueOffer.currency != intent.currency,
                    CatalogueOffer.price >= float(intent.minimum_price),
                )
            )
        if intent.brands or intent.excluded_brands:
            brands = await self._brand_vocabulary()
            if intent.brands:
                statement = statement.where(
                    CatalogueOffer.brand.in_(_brand_names(brands, intent.brands))
                )
            excluded = _brand_names(brands, intent.excluded_brands)
            if excluded:
                statement = statement.where(
                    or_(CatalogueOffer.brand.is_(None), not_(CatalogueOffer.brand.in_(excluded)))
                )
        for wanted, table in (
            (intent.colours, COLOUR_SYNONYMS),
            (intent.materials, MATERIAL_SYNONYMS),
        ):
            if wanted:
                terms = {term for w in wanted for term in {w, *table.get(w, ())}}
                statement = statement.where(_any_term(terms))
        if not (intent.product_categories or intent.colours or intent.materials or intent.brands):
            keywords = set(intent.all_keywords()) | set(intent.brands)
            clause = _any_term({part for kw in keywords for part in kw.split()})
            if clause is not None:
                statement = statement.where(clause)
        await self._brand_vocabulary()  # refreshes display spellings (cached)
        matches: Dict[tuple, List[Product]] = {}
        async with self.database.session() as session:
            for raw in await session.scalars(statement):
                product = apply_freshness(Product.model_validate(raw))
                if product.in_stock is False:
                    continue
                if intent.size and (
                    product.in_stock is not True
                    or normalise_size(product.variant_size or "") != normalise_size(intent.size)
                ):
                    continue
                if not passes_coarse_filter(product, intent) or not passes_hard_filters(
                    product, intent
                ):
                    continue
                key = (product.retailer, product.listing_id, tuple(product.colours))
                matches.setdefault(key, []).append(product)
        products = []
        for variants in matches.values():
            variants.sort(key=lambda p: (p.in_stock is not True, p.price, p.product_id))
            primary = variants[0]
            # Display only sizes available at the displayed variant price.
            primary.available_sizes = sorted(
                {
                    size
                    for p in variants
                    if p.price == primary.price and p.in_stock is True
                    for size in p.available_sizes
                }
            )
            if primary.brand:
                # One spelling per label across stores: "LEVIS" and "Levis" show as "Levi's".
                primary.brand = self._brand_display.get(
                    normalise_brand(primary.brand), primary.brand
                )
            products.append(primary)
        return products

    async def _brand_vocabulary(self) -> Dict[str, List[str]]:
        """Normalised brand -> stored spellings, from the brands actually indexed."""
        if time.time() - self._brands_loaded > BRAND_CACHE_SECONDS:
            async with self.database.session() as session:
                rows = await session.execute(
                    select(CatalogueOffer.brand, func.count())
                    .where(
                        CatalogueOffer.source_key.in_(self.retailers),
                        CatalogueOffer.brand.is_not(None),
                    )
                    .group_by(CatalogueOffer.brand)
                )
                vocabulary: Dict[str, List[str]] = {}
                counts: Dict[str, int] = {}
                for name, count in rows:
                    key = normalise_brand(name)
                    if key:
                        vocabulary.setdefault(key, []).append(name)
                        counts[name] = count
            self._brand_display = {
                key: min(names, key=lambda n, k=key: _display_rank(n, k, counts[n]))
                for key, names in vocabulary.items()
            }
            self._brands, self._brands_loaded = vocabulary, time.time()
        return self._brands

    async def recognise_brands(self, query: str, intent: SearchIntent) -> SearchIntent:
        """Find indexed brand names in a prompt, e.g. "levis 501 jeans" or "no nike"."""
        vocabulary = await self._brand_vocabulary()
        aliases = _brand_aliases(vocabulary)
        text = f" {normalise_brand(query)} "
        preferred = list(intent.brands)
        excluded = list(intent.excluded_brands)
        taken: List[tuple] = []
        for alias in sorted(aliases, key=len, reverse=True):
            key = aliases[alias]
            if len(alias) < 3 or alias in _VOCABULARY_TERMS:
                continue
            start = text.find(f" {alias} ")
            if start < 0 or any(a <= start + 1 < b for a, b in taken):
                continue
            taken.append((start + 1, start + 1 + len(alias)))
            name = self._brand_display.get(key, vocabulary[key][0])
            target = excluded if _NEGATED.search(text[:start]) else preferred
            if not any(normalise_brand(b) == key for b in preferred + excluded):
                target.append(name)
        if preferred == intent.brands and excluded == intent.excluded_brands:
            return intent
        return intent.model_copy(update={"brands": preferred, "excluded_brands": excluded})

    async def active_offer_count(self) -> int:
        async with self.database.session() as session:
            return (
                await session.scalar(
                    select(func.count())
                    .select_from(CatalogueOffer)
                    .where(
                        CatalogueOffer.source_key.in_(self.retailers),
                        CatalogueOffer.expires_at > time.time(),
                    )
                )
                or 0
            )


# First words too generic to stand for a brand on their own ("clothing the gaps").
_GENERIC_FIRST_WORDS = {
    "american",
    "clothing",
    "common",
    "original",
    "reality",
    "service",
    "universal",
    "vintage",
    "museum",
    "former",
    "open",
    "front",
    "still",
    "song",
    "hard",
    "billy",
    "kiss",
    "status",
}


def _brand_aliases(vocabulary: Dict[str, List[str]]) -> Dict[str, str]:
    """Phrases shoppers type for each brand: its name, without "the", or a distinctive
    first word shared by one brand family ("carhartt" -> "Carhartt WIP")."""
    aliases = {key: key for key in vocabulary}
    for key in vocabulary:
        if key.startswith("the "):
            aliases.setdefault(key[4:], key)
    families: Dict[str, set] = {}
    for key in vocabulary:
        first = key.split()[0]
        if " " in key and len(first) >= 5 and first not in _GENERIC_FIRST_WORDS:
            families.setdefault(first, set()).add(key)
    for first, keys in families.items():
        if first not in aliases and len(keys) == 1:
            aliases[first] = next(iter(keys))
    return aliases


def _display_rank(name: str, key: str, count: int) -> tuple:
    """Order spellings of one label: its own name over a retailer abbreviation
    ("Barney Cools" over "B.Cools"), mixed case over capitals, punctuation and
    accents kept ("Levi's", "Stüssy"), then the most common."""
    return (
        spelling_key(name) != key,
        name.isupper() or name.islower(),
        name.isascii() and name.replace(" ", "").isalnum(),
        -count,
    )


def _brand_names(vocabulary: Dict[str, List[str]], wanted: List[str]) -> List[str]:
    """Stored spellings of each wanted brand and its sub-labels ("Nike" -> "Nike ACG")."""
    keys = {normalise_brand(brand) for brand in wanted} - {""}
    names = set(wanted)
    for key, spellings in vocabulary.items():
        if any(key == k or key.startswith(k + " ") for k in keys):
            names.update(spellings)
    return sorted(names)
