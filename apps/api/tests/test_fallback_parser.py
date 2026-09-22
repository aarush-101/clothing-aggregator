"""The deterministic parser must handle the product's headline queries."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.intent import Gender, SortPreference
from app.services.nlp.fallback_parser import parse_query


def test_relaxed_black_linen_shirt_under_120_ships_to_sydney():
    intent = parse_query("Find me a relaxed black linen shirt under $120 that ships to Sydney")
    assert intent.product_categories == ["shirt"]
    assert intent.colours == ["black"]
    assert intent.materials == ["linen"]
    assert intent.fits == ["relaxed"]
    assert intent.maximum_price == Decimal("120")
    assert intent.destination_city == "Sydney"
    assert intent.destination_country == "AU"
    assert intent.currency == "AUD"
    assert intent.gender is Gender.MEN


def test_cream_oversized_overshirt_size_medium():
    intent = parse_query("Cream oversized overshirt, size medium, under $150 AUD")
    assert intent.product_categories == ["overshirt"]
    assert intent.colours == ["cream"]
    assert intent.fits == ["oversized"]
    assert intent.size == "m"
    assert intent.maximum_price == Decimal("150")
    # The size wording must not leak into the loose keyword list.
    assert "medium" not in intent.additional_keywords


def test_smart_casual_summer_wedding():
    intent = parse_query("Smart casual outfit for a summer wedding under $400")
    assert intent.occasion == "wedding"
    assert "smart casual" in intent.styles
    assert intent.maximum_price == Decimal("400")
    assert "summer" in intent.additional_keywords


def test_similar_to_brand_is_a_style_hint_not_a_brand_filter():
    intent = parse_query("Black wide-leg trousers similar to COS but cheaper")
    assert intent.product_categories == ["trousers"]
    assert intent.fits == ["wide-leg"]
    # Filtering to COS would exclude the cheaper alternatives being asked for.
    assert intent.brands == []
    assert "minimal" in intent.styles
    assert intent.sort_preference is SortPreference.PRICE_LOW_TO_HIGH


def test_brand_preference_and_exclusion():
    intent = parse_query("navy merino jumper from Uniqlo under $150, not Zara")
    assert intent.brands == ["uniqlo"]
    assert intent.excluded_brands == ["zara"]
    assert intent.colours == ["navy"]
    assert intent.materials == ["merino"]
    assert intent.product_categories == ["knitwear"]


@pytest.mark.parametrize(
    "query,minimum,maximum",
    [
        ("shirt between $80 and $150", Decimal("80"), Decimal("150")),
        ("shirt $80-$150", Decimal("80"), Decimal("150")),
        ("shirt under 200", None, Decimal("200")),
        ("shirt over $90", Decimal("90"), None),
        ("shirt around $100", Decimal("80"), Decimal("120")),
        ("shirt up to $1.5k", None, Decimal("1500")),
    ],
)
def test_price_expressions(query, minimum, maximum):
    intent = parse_query(query)
    assert intent.minimum_price == minimum
    assert intent.maximum_price == maximum


@pytest.mark.parametrize(
    "query,expected",
    [
        ("linen shirt in GBP under 90", "GBP"),
        ("linen shirt under £90", "GBP"),
        ("linen shirt under €90", "EUR"),
        ("linen shirt under $90", "AUD"),
        ("linen shirt under 90 USD", "USD"),
    ],
)
def test_currency_detection(query, expected):
    assert parse_query(query).currency == expected


@pytest.mark.parametrize(
    "query,city,country",
    [
        ("shirt shipping to Melbourne", "Melbourne", "AU"),
        ("shirt that ships to London", "London", "GB"),
        ("shirt delivered to Auckland", "Auckland", "NZ"),
        ("just a shirt", "Sydney", "AU"),
    ],
)
def test_destination_defaults_to_sydney(query, city, country):
    intent = parse_query(query)
    assert intent.destination_city == city
    assert intent.destination_country == country


@pytest.mark.parametrize(
    "query,expected",
    [
        ("shirt on sale", SortPreference.BIGGEST_DISCOUNT),
        ("cheapest black tee", SortPreference.PRICE_LOW_TO_HIGH),
        ("new in linen shirts", SortPreference.NEWEST),
        ("black linen shirt", SortPreference.RELEVANCE),
    ],
)
def test_sort_preference(query, expected):
    assert parse_query(query).sort_preference is expected


@pytest.mark.parametrize(
    "query,size",
    [
        ("shirt size medium", "m"),
        ("shirt size XL", "xl"),
        ("trousers 32 waist", "32"),
        ("trousers w34", "34"),
        ("shirt", None),
    ],
)
def test_size_extraction(query, size):
    assert parse_query(query).size == size


def test_gender_override():
    assert parse_query("women's linen shirt").gender is Gender.WOMEN
    assert parse_query("unisex linen shirt").gender is Gender.UNISEX


def test_parser_handles_odd_but_non_empty_input():
    for query in ("???", "$$$", "a", "under $", "..."):
        parse_query(query)  # must not raise


def test_parser_rejects_empty_input():
    # Callers validate first; this keeps the contract explicit rather than
    # surfacing a Pydantic error from deep inside the parser.
    with pytest.raises(ValueError):
        parse_query("   ")
