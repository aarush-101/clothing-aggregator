"""Search uses persistent inventory, including when retailer access is unavailable."""

import httpx
from sqlalchemy import delete

from app.db.tables import CatalogueOffer
from app.models.events import EventType
from app.models.product import utcnow
from app.sources.shopify import normalise_variants
from tests.catalogue_fixtures import raw_product, source
from tests.conftest import drain_events

QUERY = "black linen shirt size M under $120"


async def populate(catalogue):
    token = await catalogue.claim(source().key, force=True)
    await catalogue.publish(
        source().key, token, normalise_variants(raw_product(), source(), utcnow())
    )


async def test_search_returns_real_shaped_indexed_products_without_outbound_http(
    engine, catalogue, broker, monkeypatch
):
    await populate(catalogue)

    async def no_network(*args, **kwargs):
        raise AssertionError("Search must not contact a retailer")

    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    handle = await engine.start_search(QUERY)
    events = await drain_events(broker, handle.search_id)
    assert events[0].type == EventType.SEARCH_STARTED
    assert events[-1].type == EventType.SEARCH_COMPLETED
    snapshot = await engine.get_snapshot(handle.search_id)
    assert snapshot["groups"][0]["primary"]["price"] == 100
    assert snapshot["groups"][0]["primary"]["product_url"].endswith("variant=102")
    assert snapshot["cache_state"] == "index"
    await engine.shutdown()


async def test_empty_index_reports_pending_inventory_without_mock_fallback(engine, broker):
    handle = await engine.start_search(QUERY)
    await drain_events(broker, handle.search_id)
    snapshot = await engine.get_snapshot(handle.search_id)
    assert snapshot["groups"] == []
    assert any("collected" in warning for warning in snapshot["warnings"])
    await engine.shutdown()


async def test_repeated_search_and_old_snapshot_cannot_resurrect_removed_offers(
    engine, catalogue, broker
):
    await populate(catalogue)
    first = await engine.start_search(QUERY)
    await drain_events(broker, first.search_id)
    assert (await engine.get_snapshot(first.search_id))["groups"]
    async with catalogue.database.session() as session:
        await session.execute(delete(CatalogueOffer))
    assert not (await engine.get_snapshot(first.search_id))["groups"]
    second = await engine.start_search(QUERY)
    await drain_events(broker, second.search_id)
    assert not (await engine.get_snapshot(second.search_id))["groups"]
    await engine.shutdown()


async def test_parser_metadata_is_preserved_in_intent_cache(engine):
    first = await engine._resolve_intent(QUERY)
    second = await engine._resolve_intent(QUERY)
    assert first[1] == second[1]
    assert first[3] == second[3]
    assert second[2] == 0
    await engine.shutdown()


async def test_failed_search_remains_readable_after_completion(
    engine, catalogue, broker, monkeypatch
):
    async def unavailable(intent):
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(catalogue, "search", unavailable)
    handle = await engine.start_search(QUERY)
    events = await drain_events(broker, handle.search_id)
    assert events[-1].data["status"] == "failed"
    assert (await engine.get_snapshot(handle.search_id))["status"] == "failed"
    await engine.shutdown()


async def test_completed_search_survives_snapshot_cache_outage(
    engine, catalogue, broker, cache, monkeypatch
):
    await populate(catalogue)
    handle = await engine.start_search(QUERY)
    await drain_events(broker, handle.search_id)

    async def missing_snapshot(search_id):
        return None

    monkeypatch.setattr(cache, "get_search_snapshot", missing_snapshot)
    assert (await engine.get_snapshot(handle.search_id))["groups"]
    async with catalogue.database.session() as session:
        await session.execute(delete(CatalogueOffer))
    assert not (await engine.get_snapshot(handle.search_id))["groups"]
    await engine.shutdown()
