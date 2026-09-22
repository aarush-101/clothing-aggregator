"""SearchIntent normalisation and cache fingerprinting."""

from __future__ import annotations

from decimal import Decimal

from app.models.intent import Gender, SearchIntent, SortPreference


def make(**kwargs) -> SearchIntent:
    kwargs.setdefault("original_query", "black linen shirt")
    return SearchIntent(**kwargs)


def test_lists_are_lowercased_and_deduplicated():
    intent = make(colours=["Black", "black", " BLACK "], materials=["Linen", "linen"])
    assert intent.colours == ["black"]
    assert intent.materials == ["linen"]


def test_inverted_price_bounds_are_corrected():
    intent = make(minimum_price=Decimal("200"), maximum_price=Decimal("100"))
    assert intent.minimum_price == Decimal("100")
    assert intent.maximum_price == Decimal("200")


def test_excluded_brand_wins_over_preferred_brand():
    intent = make(brands=["cos", "arket"], excluded_brands=["cos"])
    assert intent.brands == ["arket"]
    assert intent.excluded_brands == ["cos"]


def test_defaults_are_menswear_australia():
    intent = make()
    assert intent.gender is Gender.MEN
    assert intent.currency == "AUD"
    assert intent.destination_country == "AU"
    assert intent.destination_city == "Sydney"
    assert intent.sort_preference is SortPreference.RELEVANCE


def test_invalid_currency_and_country_fall_back_to_defaults():
    intent = make(currency="dollars", destination_country="Australia!")
    assert intent.currency == "AUD"
    assert intent.destination_country == "AU"


def test_sort_aliases_are_normalised():
    assert make(sort_preference="cheapest").sort_preference is SortPreference.PRICE_LOW_TO_HIGH
    assert make(sort_preference="LATEST").sort_preference is SortPreference.NEWEST
    assert make(sort_preference="nonsense").sort_preference is SortPreference.RELEVANCE


def test_gender_aliases():
    assert make(gender="mens").gender is Gender.MEN
    assert make(gender="Female").gender is Gender.WOMEN


def test_fingerprint_ignores_wording_and_list_order():
    a = make(original_query="relaxed black linen shirt", colours=["black"], materials=["linen"])
    b = make(original_query="linen shirt in black, relaxed", colours=["black"], materials=["linen"])
    assert a.fingerprint() == b.fingerprint()

    c = make(colours=["black", "navy"])
    d = make(colours=["navy", "black"])
    assert c.fingerprint() == d.fingerprint()


def test_fingerprint_changes_with_meaningful_constraints():
    base = make(colours=["black"])
    assert base.fingerprint() != make(colours=["navy"]).fingerprint()
    assert base.fingerprint() != make(colours=["black"], maximum_price=120).fingerprint()
    assert base.fingerprint() != make(colours=["black"], size="m").fingerprint()


def test_fingerprint_is_stable_across_equivalent_price_representations():
    assert (
        make(maximum_price=120).fingerprint() == make(maximum_price=Decimal("120.00")).fingerprint()
    )


def test_all_keywords_deduplicates_across_groups():
    intent = make(
        product_categories=["shirt"],
        styles=["minimal"],
        colours=["black"],
        materials=["linen"],
        additional_keywords=["black", "summer"],
        occasion="wedding",
    )
    keywords = intent.all_keywords()
    assert keywords.count("black") == 1
    assert set(keywords) == {"shirt", "minimal", "black", "linen", "summer", "wedding"}


def test_prices_serialise_as_numbers_for_the_client():
    payload = make(maximum_price=Decimal("120.50")).model_dump(mode="json")
    assert payload["maximum_price"] == 120.5
    assert isinstance(payload["maximum_price"], float)


def test_describe_is_human_readable():
    intent = make(
        colours=["black"],
        fits=["relaxed"],
        materials=["linen"],
        product_categories=["shirt"],
        maximum_price=120,
    )
    assert intent.describe() == "black relaxed linen shirt under AUD 120"
