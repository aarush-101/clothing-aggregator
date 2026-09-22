"""Connector interface, registry, mocks, feeds and permission gating."""

from __future__ import annotations

import httpx
import pytest

from app.config import FeedConnectorConfig, Settings
from app.connectors.base import ConnectorError, ConnectorPermissionError, RetailerConnector
from app.connectors.example_public import ExamplePublicApiConnector
from app.connectors.feed_connector import SAMPLE_FEED_CONFIG, FeedConnector
from app.connectors.html_connector import HtmlRetailerConnector, extract_jsonld_products
from app.connectors.mock_retailer import build_mock_connectors, load_catalogue
from app.connectors.registry import ConnectorRegistry
from app.models.intent import SearchIntent
from app.services.nlp.fallback_parser import parse_query


def test_every_connector_implements_the_interface(registry: ConnectorRegistry):
    for connector in registry.all():
        assert isinstance(connector, RetailerConnector)
        assert connector.key and connector.display_name
        for method in ("supports", "search", "normalise", "health_check"):
            assert callable(getattr(connector, method))


def test_registry_builds_the_configured_connectors(registry: ConnectorRegistry):
    keys = {connector.key for connector in registry.all()}
    assert {"northbound", "harbour", "ridgeline", "meridian"} <= keys
    assert "sample_feed" in keys


def test_registry_excludes_connectors_that_do_not_ship_to_the_destination(
    registry: ConnectorRegistry,
):
    # Ridgeline ships only within Australia.
    au = parse_query("black linen shirt shipping to Sydney")
    gb = parse_query("black linen shirt shipping to London")
    assert "ridgeline" in {c.key for c in registry.for_intent(au)}
    assert "ridgeline" not in {c.key for c in registry.for_intent(gb)}


def test_registry_excludes_explicitly_excluded_retailers(registry: ConnectorRegistry):
    intent = SearchIntent(original_query="shirt", excluded_brands=["harbour"])
    assert "harbour" not in {c.key for c in registry.for_intent(intent)}


async def test_mock_connector_returns_normalised_products(settings: Settings):
    connector = next(c for c in build_mock_connectors(settings) if c.key == "northbound")
    products = await connector.search(parse_query("relaxed black linen shirt"))
    assert products
    for product in products:
        assert product.retailer == "northbound"
        assert product.product_url.startswith("https://")
        assert product.affiliate_url.startswith("https://")
        assert product.price > 0
        assert product.currency == "AUD"


async def test_mock_connector_filters_by_colour_and_material(settings: Settings):
    connector = next(c for c in build_mock_connectors(settings) if c.key == "harbour")
    products = await connector.search(parse_query("cream linen overshirt"))
    assert products
    for product in products:
        assert "cream" in product.colours
        assert "linen" in product.materials


async def test_the_catalogue_contains_cross_retailer_duplicates():
    catalogue = load_catalogue()
    multi = [g for g in catalogue["garments"] if len(g["offers"]) > 1]
    assert len(multi) >= 10, "the seed data must exercise de-duplication"


async def test_mock_connector_health_check(settings: Settings):
    connector = next(c for c in build_mock_connectors(settings) if c.key == "meridian")
    health = await connector.health_check()
    assert health.healthy is True
    assert health.key == "meridian"


async def test_flaky_connector_is_opt_in(settings: Settings):
    assert not any(c.key == "atlas" for c in build_mock_connectors(settings))
    enabled = settings.model_copy(update={"mock_include_flaky_retailer": True})
    assert any(c.key == "atlas" for c in build_mock_connectors(enabled))


async def test_feed_connector_reports_record_count_in_health(settings: Settings):
    connector = FeedConnector(settings, SAMPLE_FEED_CONFIG)
    health = await connector.health_check()
    assert health.healthy is True
    assert "6 records" in (health.message or "")
    await connector.aclose()


async def test_feed_connector_surfaces_http_failures(settings: Settings):
    config = FeedConnectorConfig(
        key="broken_feed",
        display_name="Broken Feed",
        url="https://feeds.example/missing.json",
        format="json",
    )
    connector = FeedConnector(settings, config)

    async def fail(*args, **kwargs):
        raise httpx.ConnectError("no route to host")

    connector._ensure_client().get = fail  # type: ignore[method-assign]
    health = await connector.health_check()
    assert health.healthy is False
    await connector.aclose()


async def test_feed_connector_rejects_malformed_documents(settings: Settings):
    connector = FeedConnector(settings, SAMPLE_FEED_CONFIG)
    with pytest.raises(ConnectorError):
        connector._extract_records("<not-xml")
    await connector.aclose()


# --------------------------------------------------------------------------
# HTML connector: must stay disabled without explicit permission
# --------------------------------------------------------------------------


def _html_connector(settings: Settings, permission: bool) -> HtmlRetailerConnector:
    return HtmlRetailerConnector(
        settings,
        key="permitted_retailer",
        display_name="Permitted Retailer",
        search_url_template="https://retailer.example/search?q={query}",
        permission_granted=permission,
        ships_to=["AU"],
    )


async def test_html_connector_refuses_to_run_when_globally_disabled(settings: Settings):
    connector = _html_connector(settings, permission=True)
    assert connector.settings.enable_html_connectors is False
    with pytest.raises(ConnectorPermissionError):
        await connector.search(parse_query("linen shirt"))


async def test_html_connector_refuses_to_run_without_retailer_permission(settings: Settings):
    enabled = settings.model_copy(update={"enable_html_connectors": True})
    connector = _html_connector(enabled, permission=False)
    with pytest.raises(ConnectorPermissionError):
        await connector.search(parse_query("linen shirt"))


def test_html_connector_is_not_registered_automatically(registry: ConnectorRegistry):
    assert all(not c.requires_permission for c in registry.all())


def test_html_connector_supports_returns_false_when_not_permitted(settings: Settings):
    connector = _html_connector(settings, permission=True)
    assert connector.supports(parse_query("linen shirt")) is False


def test_jsonld_extraction_finds_nested_products():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"ItemList","itemListElement":[
      {"@type":"Product","name":"Linen Shirt","sku":"AB-1234",
       "offers":{"@type":"Offer","price":"119.00","priceCurrency":"AUD",
                 "availability":"https://schema.org/InStock","url":"/p/ab-1234"}}]}
    </script>
    <script type="application/ld+json">not json</script>
    </head></html>
    """
    products = extract_jsonld_products(html)
    assert len(products) == 1
    assert products[0]["name"] == "Linen Shirt"


def test_html_connector_normalises_jsonld(settings: Settings):
    connector = _html_connector(settings, permission=True)
    record = {
        "@type": "Product",
        "name": "Linen Shirt",
        "sku": "AB-1234",
        "brand": {"name": "Example Brand"},
        "image": ["https://img.example/a.jpg"],
        "offers": {
            "price": "119.00",
            "priceCurrency": "AUD",
            "availability": "https://schema.org/OutOfStock",
            "url": "/p/ab-1234",
        },
    }
    product = connector.normalise(
        {"record": record, "base_url": "https://retailer.example/search?q=shirt"}
    )
    assert product is not None
    assert product.brand == "Example Brand"
    assert product.product_url == "https://retailer.example/p/ab-1234"
    assert product.in_stock is False


# --------------------------------------------------------------------------
# Example public API connector
# --------------------------------------------------------------------------


def test_example_public_connector_is_disabled_by_default(settings: Settings):
    assert settings.enable_example_public_connector is False


def test_example_public_connector_normalises_a_record(settings: Settings):
    connector = ExamplePublicApiConnector(settings)
    product = connector.normalise(
        {
            "id": 1,
            "title": "Mens Casual Slim Fit Shirt",
            "price": 15.99,
            "description": "Slim fit cotton shirt",
            "category": "men's clothing",
            "image": "https://img.example/1.jpg",
        }
    )
    assert product is not None
    assert product.currency == "USD"
    assert product.retailer == "example_public"


def test_example_public_connector_discards_records_without_an_id(settings: Settings):
    connector = ExamplePublicApiConnector(settings)
    assert connector.normalise({"title": "No id"}) is None
    assert connector.normalise("not a dict") is None
