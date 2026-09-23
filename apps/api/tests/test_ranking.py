"""Deterministic ranking, match reasons, hard filters and sorting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.intent import SearchIntent, SortPreference
from app.models.product import Product, ProductGroup
from app.services.ranking import (
    DEFAULT_WEIGHTS,
    filter_products,
    passes_hard_filters,
    rank_groups,
    score_product,
)


def product(**overrides) -> Product:
    fields = {
        "product_id": overrides.pop("pid", "p1"),
        "title": "Kessler Relaxed Linen Shirt",
        "description": "A relaxed black linen shirt.",
        "brand": "Kessler",
        "retailer": overrides.pop("retailer", "demo"),
        "product_url": "https://shop.example/p/1",
        "affiliate_url": "https://shop.example/p/1",
        "category": "shirt",
        "colours": ["black"],
        "materials": ["linen"],
        "available_sizes": ["s", "m", "l"],
        "price": Decimal("119.00"),
        "currency": "AUD",
        "in_stock": True,
        "shipping_destination": "AU",
    }
    fields.update(overrides)
    return Product(**fields)


def intent(**overrides) -> SearchIntent:
    fields = {
        "original_query": "relaxed black linen shirt under $120",
        "product_categories": ["shirt"],
        "colours": ["black"],
        "materials": ["linen"],
        "fits": ["relaxed"],
        "maximum_price": Decimal("120"),
    }
    fields.update(overrides)
    return SearchIntent(**fields)


def group(*products: Product) -> ProductGroup:
    ordered = sorted(products, key=lambda p: (not p.in_stock, p.total_price))
    return ProductGroup(group_id="g", primary=ordered[0], offers=ordered)


def test_a_perfect_match_scores_near_the_top():
    score, _ = score_product(product(), intent())
    assert score > 0.9


def test_a_wrong_colour_scores_lower_than_a_right_one():
    right, _ = score_product(product(), intent())
    wrong, _ = score_product(product(colours=["navy"], description="A navy shirt."), intent())
    assert wrong < right


def test_wrong_category_is_heavily_penalised():
    trousers = product(title="Kessler Wide Trouser", category="trousers", description="trousers")
    assert score_product(trousers, intent())[0] < score_product(product(), intent())[0]


def test_out_of_stock_is_ranked_below_in_stock():
    assert (
        score_product(product(in_stock=False), intent())[0] < score_product(product(), intent())[0]
    )


def test_size_availability_matters_when_a_size_is_requested():
    wanted = intent(size="m")
    has_size, _ = score_product(product(), wanted)
    missing, _ = score_product(product(available_sizes=["xs", "s"]), wanted)
    assert missing < has_size


def test_unspecified_dimensions_do_not_penalise():
    # No size, brand, colour or material requested: a plain shirt should still
    # score well rather than being punished for unmentioned attributes.
    loose = SearchIntent(original_query="shirt", product_categories=["shirt"])
    assert score_product(product(), loose)[0] > 0.7


def test_match_reasons_are_human_readable():
    _, reasons = score_product(product(), intent())
    assert reasons[0] == (
        "Matches your requested shirt, black colour, linen material and relaxed fit."
    )
    assert any("budget" in reason for reason in reasons)


def test_currency_code_is_not_lowercased_in_reasons():
    _, reasons = score_product(product(), intent())
    assert "AUD" in " ".join(reasons)


def test_reasons_mention_a_meaningful_discount():
    _, reasons = score_product(product(original_price=Decimal("199")), intent())
    assert any("% off" in reason for reason in reasons)


def test_reasons_flag_out_of_stock():
    _, reasons = score_product(product(in_stock=False), intent())
    assert "Currently out of stock" in reasons


# --------------------------------------------------------------------------
# Hard filters
# --------------------------------------------------------------------------


def test_items_far_over_budget_are_filtered_out():
    assert passes_hard_filters(product(price=Decimal("400")), intent()) is False


def test_explicit_budget_is_respected_even_when_only_slightly_over():
    assert passes_hard_filters(product(price=Decimal("125")), intent()) is False


def test_excluded_brands_are_filtered_out():
    excluded = intent(excluded_brands=["kessler"])
    assert passes_hard_filters(product(), excluded) is False


def test_filter_products_keeps_only_eligible_items():
    kept = filter_products([product(pid="a"), product(pid="b", price=Decimal("999"))], intent())
    assert [p.product_id for p in kept] == ["a"]


def test_uncomparable_currencies_are_not_silently_excluded():
    # An unknown currency cannot be converted; excluding it would hide results
    # for the wrong reason.
    assert passes_hard_filters(product(price=Decimal("50"), currency="XYZ"), intent()) is True


# --------------------------------------------------------------------------
# Group ranking and sorting
# --------------------------------------------------------------------------


def test_relevance_sort_puts_the_best_match_first():
    good = group(product(pid="good"))
    poor = group(product(pid="poor", colours=["navy"], description="navy", title="Navy Shirt"))
    ranked = rank_groups([poor, good], intent())
    assert ranked[0].primary.product_id == "good"


def test_price_sort_uses_the_cheapest_offer_including_shipping():
    cheap = group(product(pid="cheap", price=Decimal("90"), shipping_cost=Decimal("30")))
    cheaper = group(product(pid="cheaper", price=Decimal("110"), shipping_cost=Decimal("0")))
    ranked = rank_groups([cheap, cheaper], intent(sort_preference=SortPreference.PRICE_LOW_TO_HIGH))
    assert ranked[0].primary.product_id == "cheaper"


def test_discount_sort_prefers_the_biggest_markdown():
    small = group(product(pid="small", price=Decimal("100"), original_price=Decimal("110")))
    large = group(product(pid="large", price=Decimal("100"), original_price=Decimal("200")))
    ranked = rank_groups([small, large], intent(sort_preference=SortPreference.BIGGEST_DISCOUNT))
    assert ranked[0].primary.product_id == "large"


def test_newest_sort_prefers_the_most_recent_update():
    now = datetime.now(timezone.utc)
    old = group(product(pid="old", source_updated_at=now - timedelta(days=30)))
    new = group(product(pid="new", source_updated_at=now))
    ranked = rank_groups([old, new], intent(sort_preference=SortPreference.NEWEST))
    assert ranked[0].primary.product_id == "new"


def test_multi_retailer_groups_explain_the_cheapest_offer():
    multi = group(
        product(pid="a", retailer="one", price=Decimal("119")),
        product(pid="b", retailer="two", price=Decimal("99")),
    )
    ranked = rank_groups([multi], intent())
    assert ranked[0].primary.retailer == "two"
    assert any(
        "Lowest listed price across 2 retailers" in reason for reason in ranked[0].match_reasons
    )


def test_ranking_is_deterministic():
    groups = [group(product(pid=str(i), price=Decimal("100") + i)) for i in range(5)]
    first = [g.primary.product_id for g in rank_groups(list(groups), intent())]
    second = [g.primary.product_id for g in rank_groups(list(groups), intent())]
    assert first == second


def test_limit_truncates_the_result_set():
    groups = [group(product(pid=str(i))) for i in range(10)]
    assert len(rank_groups(groups, intent(), DEFAULT_WEIGHTS, limit=3)) == 3


def test_weights_are_published_for_inspection():
    weights = DEFAULT_WEIGHTS.as_dict()
    assert pytest.approx(sum(weights.values()), abs=1e-9) == 1.0
    assert "keyword_relevance" in weights
