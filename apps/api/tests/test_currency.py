"""Cross-currency comparison used by price filtering and ranking."""

from __future__ import annotations

from decimal import Decimal

from app.services.currency import comparable_amount, convert, supported_currencies


def test_same_currency_is_returned_unchanged():
    assert convert(Decimal("100"), "AUD", "AUD") == Decimal("100")


def test_usd_converts_to_more_aud():
    converted = convert(Decimal("100"), "USD", "AUD")
    assert converted is not None and converted > Decimal("100")


def test_conversion_round_trips_approximately():
    aud = convert(Decimal("100"), "GBP", "AUD")
    back = convert(aud, "AUD", "GBP")
    assert abs(back - Decimal("100")) < Decimal("0.01")


def test_unknown_currency_is_not_comparable():
    assert comparable_amount(Decimal("100"), "XYZ", "AUD") is None


def test_none_amount_is_passed_through():
    assert convert(None, "USD", "AUD") is None


def test_supported_currencies_are_published():
    rates = supported_currencies()
    assert rates["AUD"] == 1.0
    assert "USD" in rates and "GBP" in rates
