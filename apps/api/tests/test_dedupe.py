"""Cross-retailer duplicate detection."""

from __future__ import annotations

from decimal import Decimal

from app.models.product import Product
from app.services.dedupe import (
    group_products,
    identity_keys,
    image_fingerprint,
    normalise_brand,
    normalise_title,
)


def product(retailer: str, **overrides) -> Product:
    fields = {
        "product_id": overrides.pop("pid", f"{retailer}-1"),
        "title": "Kessler Relaxed Linen Shirt",
        "brand": "Kessler",
        "retailer": retailer,
        "product_url": f"https://{retailer}.example/p/1",
        "affiliate_url": f"https://{retailer}.example/p/1",
        "image_url": "https://images.example/kessler-linen-shirt-black.jpg",
        "colours": ["black"],
        "price": Decimal("119.00"),
        "in_stock": True,
    }
    fields.update(overrides)
    return Product(**fields)


def test_normalise_brand_strips_punctuation_and_legal_suffixes():
    assert normalise_brand("Cobb & Finch Pty Ltd") == "cobb finch"
    assert normalise_brand("Cobb and Finch") == "cobb and finch"
    assert normalise_brand(None) == ""


def test_normalise_title_removes_brand_colour_and_noise():
    title = normalise_title("Kessler Mens Relaxed Linen Shirt - Black", "Kessler", ["black"])
    assert set(title.split()) == {"relaxed", "linen", "shirt"}


def test_normalise_title_treats_colour_synonyms_as_the_same():
    a = normalise_title("Aldgate Linen Shirt Ecru", "Aldgate", ["ecru"])
    b = normalise_title("Aldgate Linen Shirt Cream", "Aldgate", ["cream"])
    assert a == b


def test_image_fingerprint_ignores_query_strings():
    assert image_fingerprint("https://x.example/a/kessler-shirt.jpg?w=600") == "kesslershirt"
    assert image_fingerprint("https://x.example/img/p.jpg") is None
    assert image_fingerprint(None) is None


def test_identity_keys_include_brand_title_and_image():
    kinds = {kind for kind, _ in identity_keys(product("a"))}
    assert "brand_title" in kinds
    assert "image" in kinds


def test_same_garment_at_three_retailers_becomes_one_group():
    offers = [product("one"), product("two"), product("three")]
    groups = group_products(offers)
    assert len(groups) == 1
    assert groups[0].offer_count == 3
    assert len(groups[0].retailers) == 3


def test_cheapest_in_stock_offer_becomes_the_primary():
    # The $89 offer is out of stock, so neither the primary nor the headline
    # price may come from it.
    groups = group_products(
        [
            product("one", price=Decimal("119")),
            product("two", price=Decimal("99")),
            product("three", price=Decimal("89"), in_stock=False),
        ]
    )
    assert groups[0].primary.retailer == "two"
    assert groups[0].lowest_total_price == 99.0


def test_shipping_is_included_when_choosing_the_cheapest():
    groups = group_products(
        [
            product("one", price=Decimal("99"), shipping_cost=Decimal("25")),
            product("two", price=Decimal("110"), shipping_cost=Decimal("0")),
        ]
    )
    assert groups[0].primary.retailer == "two"


def test_different_colourways_are_not_merged():
    black = product("one")
    cream = product(
        "one",
        pid="one-2",
        colours=["cream"],
        title="Kessler Relaxed Linen Shirt Cream",
        image_url="https://images.example/kessler-linen-shirt-cream.jpg",
    )
    assert len(group_products([black, cream])) == 2


def test_different_garments_are_not_merged():
    shirt = product("one")
    trouser = product(
        "one",
        pid="one-2",
        title="Kessler Wide Leg Trouser",
        image_url="https://images.example/kessler-wide-trouser-black.jpg",
    )
    assert len(group_products([shirt, trouser])) == 2


def test_a_shared_model_identifier_merges_differently_titled_offers():
    a = product("one", title="Relaxed Linen Shirt KSL-LNS-01", brand="Kessler", image_url=None)
    b = product(
        "two",
        title="Kessler Linen Shirt (KSL-LNS-01) Black",
        brand=None,
        image_url=None,
    )
    assert len(group_products([a, b])) == 1


def test_duplicate_listings_from_one_retailer_collapse_to_the_cheaper():
    groups = group_products(
        [
            product("one", pid="one-1", price=Decimal("119")),
            product("one", pid="one-1", price=Decimal("99")),
        ]
    )
    assert groups[0].offer_count == 1
    assert groups[0].primary.price == Decimal("99")


def test_empty_input_produces_no_groups():
    assert group_products([]) == []


def test_group_ids_are_stable_across_runs():
    offers = [product("one"), product("two")]
    assert group_products(offers)[0].group_id == group_products(list(offers))[0].group_id
