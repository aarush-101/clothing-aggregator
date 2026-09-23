"""Persistent variant index and atomic, leased ingestion publication."""

from __future__ import annotations

import time
import uuid
from datetime import timedelta
from typing import Dict, List, Optional

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.db.session import Database
from app.db.tables import CatalogueOffer, CatalogueSource, IngestionRun
from app.models.intent import SearchIntent
from app.models.product import Product, utcnow
from app.services.affiliate import build_affiliate_url
from app.services.filtering import passes_coarse_filter
from app.services.nlp.lexicon import normalise_size
from app.services.ranking import passes_hard_filters
from app.sources.registry import Retailer

LEASE_SECONDS = 300


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
        statement = select(CatalogueOffer.payload).where(
            CatalogueOffer.source_key.in_(self.retailers), CatalogueOffer.expires_at > time.time()
        )
        if intent.product_categories:
            statement = statement.where(CatalogueOffer.category.in_(intent.product_categories))
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
            primary.affiliate_url = build_affiliate_url(
                product_url=primary.product_url,
                retailer=primary.retailer,
                product_id=primary.product_id,
                templates=self.settings.affiliate_template_map,
                subid_prefix=self.settings.affiliate_subid_prefix,
            )
            products.append(primary)
        return products

    async def active_offer_count(self) -> int:
        from sqlalchemy import func

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
