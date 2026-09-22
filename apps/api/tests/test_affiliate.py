"""Affiliate link construction and click sub-ids."""

from __future__ import annotations

import pytest

from app.services.affiliate import build_affiliate_url, build_subid, extract_subid

AWIN = "https://www.awin1.com/cread.php?awinmid=1234&awinaffid=999&clickref={subid}&ued={url}"


def test_without_a_template_the_shopper_goes_to_the_retailer():
    url = build_affiliate_url(
        "https://shop.example/p/1", "shop", "p1", templates={}, subid_prefix="ca"
    )
    assert url == "https://shop.example/p/1"


def test_a_configured_template_is_expanded():
    url = build_affiliate_url(
        "https://shop.example/p/1?colour=black",
        "shop",
        "p1",
        templates={"shop": AWIN},
        subid_prefix="ca",
    )
    assert url.startswith("https://www.awin1.com/cread.php")
    assert "https%3A%2F%2Fshop.example%2Fp%2F1%3Fcolour%3Dblack" in url
    assert "clickref=ca-shop-" in url


def test_a_template_for_another_retailer_is_not_applied():
    url = build_affiliate_url("https://shop.example/p/1", "other", "p1", templates={"shop": AWIN})
    assert url == "https://shop.example/p/1"


def test_a_broken_template_falls_back_to_the_plain_url():
    url = build_affiliate_url(
        "https://shop.example/p/1", "shop", "p1", templates={"shop": "not-a-url {url}"}
    )
    assert url == "https://shop.example/p/1"


def test_an_unsafe_product_url_is_refused():
    with pytest.raises(ValueError):
        build_affiliate_url("javascript:alert(1)", "shop", "p1", templates={})


def test_subids_are_stable_and_unique_per_product():
    first = build_subid("ca", "shop", "p1")
    assert first == build_subid("ca", "shop", "p1")
    assert first != build_subid("ca", "shop", "p2")
    assert first != build_subid("ca", "other", "p1")


def test_subids_are_url_safe_and_bounded():
    subid = build_subid("ca", "shop with spaces", "p/1?x=2")
    assert subid.replace("-", "").isalnum()
    assert len(subid) <= 64


def test_subid_can_be_read_back_from_a_network_url():
    url = build_affiliate_url("https://shop.example/p/1", "shop", "p1", templates={"shop": AWIN})
    assert extract_subid(url) == build_subid("ca", "shop", "p1")
