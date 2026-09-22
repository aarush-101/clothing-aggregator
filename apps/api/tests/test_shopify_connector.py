"""Shopify storefront connector.

Fixtures mirror the real shapes observed on Todd Snyder, Universal Store and
Assembly Label. No network: the suite must stay hermetic.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import Settings
from app.connectors.base import ConnectorSkipped
from app.connectors.shopify import (
    ShopifyConnector,
    ShopifyStore,
    build_shopify_connectors,
    cold_fetch_budget,
    load_stores,
    new_cold_fetch_budget,
)
from app.models.intent import Gender, SearchIntent

STORE = ShopifyStore(
    key="demo_store",
    name="Demo Store",
    domain="demo-store.example",
    currency="AUD",
    country="AU",
)


def product(**overrides):
    base = {
        "id": 123456,
        "title": "Relaxed Linen Shirt",
        "handle": "relaxed-linen-shirt-black",
        "body_html": "<p>A relaxed shirt in 100% <b>linen</b>.</p><ul><li>Camp collar</li></ul>",
        "vendor": "Demo Brand",
        "product_type": "Shirts",
        "tags": ["Mens", "SS26", "linen"],
        "updated_at": "2026-09-20T10:00:00+10:00",
        "options": [
            {"name": "Size", "position": 1, "values": ["S", "M", "L", "XL"]},
            {"name": "Color", "position": 2, "values": ["Black"]},
        ],
        "images": [{"src": "https://cdn.shopify.com/s/files/demo/linen-shirt.jpg?v=1"}],
        "variants": [
            {
                "option1": "S",
                "option2": "Black",
                "price": "189.00",
                "compare_at_price": "229.00",
                "available": False,
                "sku": "A-S",
            },
            {
                "option1": "M",
                "option2": "Black",
                "price": "179.00",
                "compare_at_price": "229.00",
                "available": True,
                "sku": "A-M",
            },
            {
                "option1": "L",
                "option2": "Black",
                "price": "179.00",
                "compare_at_price": "229.00",
                "available": True,
                "sku": "A-L",
            },
        ],
    }
    base.update(overrides)
    return base


@pytest.fixture
def connector(settings: Settings) -> ShopifyConnector:
    return ShopifyConnector(settings, STORE)


def intent(**overrides) -> SearchIntent:
    fields = {"original_query": "black linen shirt"}
    fields.update(overrides)
    return SearchIntent(**fields)


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------


def test_normalises_a_product(connector: ShopifyConnector):
    result = connector.normalise(product())
    assert result is not None
    assert result.title == "Relaxed Linen Shirt"
    assert result.brand == "Demo Brand"
    assert result.retailer == "demo_store"
    assert result.currency == "AUD"
    assert result.category == "shirt"
    assert result.colours == ["black"]
    assert "linen" in result.materials


def test_links_to_the_real_product_page(connector: ShopifyConnector):
    result = connector.normalise(product())
    assert result.product_url == "https://demo-store.example/products/relaxed-linen-shirt-black"


def test_uses_the_cheapest_purchasable_variant(connector: ShopifyConnector):
    result = connector.normalise(product())
    # The $189 small is sold out, so the $179 medium sets the price.
    assert result.price == Decimal("179.00")
    assert result.original_price == Decimal("229.00")
    assert result.discount_percent == 22


def test_only_lists_sizes_that_can_be_bought(connector: ShopifyConnector):
    result = connector.normalise(product())
    assert result.available_sizes == ["m", "l"]


def test_marks_a_fully_sold_out_product_out_of_stock(connector: ShopifyConnector):
    sold_out = product(variants=[{"option1": "M", "price": "179.00", "available": False}])
    result = connector.normalise(sold_out)
    assert result.in_stock is False


def test_ignores_a_compare_at_price_that_is_not_a_discount(connector: ShopifyConnector):
    full_price = product(
        variants=[
            {"option1": "M", "price": "398.00", "compare_at_price": "398.00", "available": True}
        ]
    )
    result = connector.normalise(full_price)
    assert result.discount_percent is None


def test_reads_colour_from_the_title_when_there_is_no_colour_option(
    connector: ShopifyConnector,
):
    # Universal Store lists colour only in the title.
    no_option = product(
        title="Rusty Big Ticket Hooded Fleece Navy",
        options=[{"name": "Size", "values": ["S", "M"]}],
    )
    result = connector.normalise(no_option)
    assert result.colours == ["navy"]


def test_strips_html_from_the_description(connector: ShopifyConnector):
    result = connector.normalise(product())
    assert "<" not in (result.description or "")
    assert "linen" in (result.description or "").lower()


def test_discards_records_without_a_handle_or_variants(connector: ShopifyConnector):
    assert connector.normalise(product(handle=None)) is None
    assert connector.normalise(product(variants=[])) is None
    assert connector.normalise("not a dict") is None


# --------------------------------------------------------------------------
# Department filtering
# --------------------------------------------------------------------------


def test_excludes_womenswear_from_a_mens_search(connector: ShopifyConnector):
    womens = product(
        title="Re-Worn Womens Boyfriend Jean", product_type="Womens Jeans", tags=["reworn-womens"]
    )
    assert connector._filter_ok(womens, intent()) is False


def test_keeps_a_mens_item_that_also_carries_a_womens_tag(connector: ShopifyConnector):
    both = product(title="Mens Linen Shirt", tags=["Mens", "Womens"])
    assert connector._filter_ok(both, intent()) is True


def test_excludes_kidswear_and_gift_cards(connector: ShopifyConnector):
    assert connector._filter_ok(product(title="Kids Linen Shirt"), intent()) is False
    assert connector._filter_ok(product(title="Gift Card"), intent()) is False


def test_womens_search_excludes_menswear(connector: ShopifyConnector):
    assert connector._filter_ok(product(), intent(gender=Gender.WOMEN)) is False


# --------------------------------------------------------------------------
# Cold-fetch budget
# --------------------------------------------------------------------------


async def test_a_cold_store_is_skipped_once_the_budget_is_spent(connector: ShopifyConnector):
    cold_fetch_budget.set(new_cold_fetch_budget(0))
    with pytest.raises(ConnectorSkipped):
        await connector.search(intent())


def test_the_budget_is_shared_and_decrements(settings: Settings):
    budget = new_cold_fetch_budget(2)
    cold_fetch_budget.set(budget)
    from app.connectors.shopify import _claim_cold_fetch

    assert _claim_cold_fetch() is True
    assert _claim_cold_fetch() is True
    assert _claim_cold_fetch() is False
    assert budget == [0]


# --------------------------------------------------------------------------
# Store registry
# --------------------------------------------------------------------------


def test_the_bundled_store_list_is_well_formed():
    stores = load_stores()
    assert len(stores) > 50
    keys = [store.key for store in stores]
    assert len(keys) == len(set(keys)), "store keys must be unique"
    for store in stores:
        assert store.domain and "/" not in store.domain
        assert len(store.currency) == 3
        assert store.product_url("some-handle").startswith(f"https://{store.domain}/products/")


def test_shopify_connectors_are_off_by_default(settings: Settings):
    # Every verified storefront currently returns a Cloudflare bot challenge,
    # so the connector must not be enabled without a deliberate decision.
    assert settings.enable_shopify_connectors is False
    assert build_shopify_connectors(settings, None) == []


def test_connectors_are_built_when_explicitly_enabled(settings: Settings):
    enabled = settings.model_copy(update={"enable_shopify_connectors": True})
    connectors = build_shopify_connectors(enabled, None, [STORE])
    assert [c.key for c in connectors] == ["demo_store"]
