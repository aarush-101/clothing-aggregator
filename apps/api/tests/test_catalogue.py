"""Persistence, expiry, variant selection, snapshot reconciliation and worker leases."""

import time
from datetime import timedelta

from sqlalchemy import update

from app.db.session import Database
from app.db.tables import CatalogueOffer, CatalogueSource
from app.models.product import utcnow
from app.services.catalogue import Catalogue
from app.services.nlp.fallback_parser import parse_query
from app.sources.shopify import normalise_variants
from tests.catalogue_fixtures import raw_product, source


async def publish(catalogue, products=None):
    token = await catalogue.claim(source().key, force=True)
    assert token
    rows = normalise_variants(raw_product(), source(), utcnow()) if products is None else products
    assert await catalogue.publish(source().key, token, rows)


async def test_size_and_colour_filters_never_use_a_cheaper_different_variant(catalogue):
    await publish(catalogue)
    products = await catalogue.search(parse_query("black linen shirt size M under $120"))
    assert len(products) == 1
    assert products[0].product_id == "102" and products[0].price == 100
    assert products[0].available_sizes == ["m"]
    assert not await catalogue.search(parse_query("black linen shirt size L"))
    assert not await catalogue.search(parse_query("black linen shirt size M under $60"))


async def test_general_search_lists_sizes_only_at_the_displayed_price(catalogue):
    await publish(catalogue)
    products = await catalogue.search(parse_query("black linen shirt"))
    assert products[0].price == 70 and products[0].available_sizes == ["s"]


async def test_inventory_survives_a_new_database_connection(catalogue, settings):
    await publish(catalogue)
    other_db = Database(catalogue.database.url)
    try:
        other = Catalogue(other_db, [source()], settings)
        assert await other.search(parse_query("linen shirt"))
    finally:
        await other_db.dispose()


async def test_failed_refresh_preserves_inventory_and_sets_a_cooldown(catalogue):
    await publish(catalogue)
    token = await catalogue.claim(source().key, force=True)
    await catalogue.fail(source().key, token, "HTTP 429", 7200, blocked=True)
    assert await catalogue.search(parse_query("linen shirt"))
    assert await catalogue.claim(source().key) is None
    state = (await catalogue.source_states())[source().key]
    assert state.state == "blocked" and state.next_due > time.time() + 7100


async def test_complete_snapshot_removes_absent_offers_and_is_idempotent(catalogue):
    await publish(catalogue)
    await publish(catalogue)
    assert await catalogue.active_offer_count() == 4
    await publish(catalogue, [])
    assert await catalogue.active_offer_count() == 0
    assert not await catalogue.search(parse_query("linen shirt"))


async def test_lease_prevents_two_workers_and_expired_writer_cannot_commit(catalogue):
    key = source().key
    old = await catalogue.claim(key, force=True)
    assert await catalogue.claim(key, force=True) is None
    async with catalogue.database.session() as session:
        await session.execute(
            update(CatalogueSource).where(CatalogueSource.key == key).values(lease_until=0)
        )
    current = await catalogue.claim(key, force=True)
    rows = normalise_variants(raw_product(), source(), utcnow())
    assert await catalogue.publish(key, old, rows) is False
    assert await catalogue.publish(key, current, rows) is True


async def test_stale_stock_is_unknown_and_expired_inventory_is_hidden(catalogue, settings):
    rows = normalise_variants(
        raw_product(), source(), utcnow() - timedelta(seconds=settings.catalogue_stale_seconds + 10)
    )
    await publish(catalogue, rows)
    products = await catalogue.search(parse_query("black linen shirt"))
    assert products and all(
        p.freshness == "stale" and p.in_stock is None and not p.available_sizes for p in products
    )
    assert not await catalogue.search(parse_query("black linen shirt size M"))
    async with catalogue.database.session() as session:
        await session.execute(update(CatalogueOffer).values(expires_at=time.time() - 1))
    assert not await catalogue.search(parse_query("linen shirt"))


async def test_worker_failure_preserves_inventory_and_respects_cooldown(catalogue, monkeypatch):
    from app.services.ingestion import IngestionWorker
    from app.sources.shopify import ShopifySource, SourceError

    await publish(catalogue)
    attempts = []

    async def failed_fetch(self, heartbeat=None):
        attempts.append(self.retailer.key)
        raise SourceError("HTTP 429", retry_after=7200, blocked=True)

    monkeypatch.setattr(ShopifySource, "fetch", failed_fetch)
    worker = IngestionWorker(catalogue)
    assert not await worker.refresh(source().key, force=True)
    await worker.tick()
    assert attempts == [source().key]
    assert await catalogue.active_offer_count() == 4
    assert await catalogue.search(parse_query("linen shirt"))


async def test_failed_publication_rolls_back_removal_and_source_state(catalogue):
    import pytest
    from sqlalchemy import event

    await publish(catalogue)
    before = (await catalogue.source_states())[source().key].last_success
    token = await catalogue.claim(source().key, force=True)

    def fail_insert(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO catalogue_offers"):
            raise RuntimeError("simulated disk failure during publication")

    engine = catalogue.database.engine.sync_engine
    event.listen(engine, "before_cursor_execute", fail_insert)
    try:
        with pytest.raises(RuntimeError, match="disk failure"):
            await catalogue.publish(
                source().key, token, normalise_variants(raw_product(), source(), utcnow())
            )
    finally:
        event.remove(engine, "before_cursor_execute", fail_insert)
    assert await catalogue.active_offer_count() == 4
    state = (await catalogue.source_states())[source().key]
    assert state.last_success == before and state.lease_token == token
