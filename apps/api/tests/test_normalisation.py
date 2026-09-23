"""Normalising untrusted retailer data into the Product model."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.product import Product, sanitise_text, sanitise_url


def make_product(**overrides) -> Product:
    fields = {
        "product_id": "p1",
        "title": "Linen Shirt",
        "retailer": "demo",
        "product_url": "https://shop.example/p/1",
        "affiliate_url": "https://shop.example/p/1",
        "price": Decimal("119.00"),
    }
    fields.update(overrides)
    return Product(**fields)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("<b>Linen</b> Shirt", "Linen Shirt"),
        ("Linen   Shirt\n\n", "Linen Shirt"),
        ("<script>alert(1)</script>Shirt", "alert(1) Shirt"),
        ("", None),
        (None, None),
    ],
)
def test_sanitise_text(raw, expected):
    assert sanitise_text(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "//evil.example/p",
        "ftp://files.example/p",
        "https://shop.example/p 1",
        "",
        None,
    ],
)
def test_unsafe_urls_are_rejected(raw):
    assert sanitise_url(raw) is None


def test_safe_urls_pass_through():
    assert sanitise_url("https://shop.example/p/1?x=2") == "https://shop.example/p/1?x=2"


def test_product_rejects_an_unsafe_product_url():
    with pytest.raises(ValidationError):
        make_product(product_url="javascript:alert(1)")


def test_prices_are_parsed_from_messy_strings():
    product = make_product(price="$1,299.95", original_price="AUD 1,499.00")
    assert product.price == Decimal("1299.95")
    assert product.original_price == Decimal("1499.00")


def test_discount_is_computed_only_when_there_is_one():
    assert make_product(price=100, original_price=200).discount_percent == 50
    assert make_product(price=100, original_price=100).discount_percent is None
    assert make_product(price=100).discount_percent is None


def test_total_price_includes_shipping():
    assert make_product(price=100, shipping_cost=9.95).total_price == 109.95


def test_list_fields_accept_delimited_strings():
    product = make_product(colours="Black / Charcoal", available_sizes="S,M,L")
    assert product.colours == ["black", "charcoal"]
    assert product.available_sizes == ["s", "m", "l"]


def test_naive_datetimes_are_made_timezone_aware():
    product = make_product(source_updated_at=datetime(2026, 9, 1, 12, 0, 0))
    assert product.source_updated_at.tzinfo is timezone.utc


def test_match_score_is_clamped():
    assert make_product(match_score=5.0).match_score == 1.0
    assert make_product(match_score=-1.0).match_score == 0.0


def test_money_serialises_as_numbers():
    payload = make_product(price=Decimal("119.00"), shipping_cost=Decimal("9.95")).model_dump(
        mode="json"
    )
    assert payload["price"] == 119.0
    assert payload["shipping_cost"] == 9.95
