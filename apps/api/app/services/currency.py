"""Currency handling for cross-retailer price comparison.

An aggregator that mixes retailers inevitably mixes currencies, and comparing a
USD price against an AUD budget without converting is simply wrong. The rates
below are static approximations so the MVP has no hard dependency on an FX
provider - see ``docs/limitations.md``; swap :func:`convert` for a cached live
rate source before this touches real money.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, Optional

# Indicative mid-market rates, expressed as "1 unit of X = N AUD".
_TO_AUD: Dict[str, Decimal] = {
    "AUD": Decimal("1.00"),
    "NZD": Decimal("0.92"),
    "USD": Decimal("1.52"),
    "GBP": Decimal("1.94"),
    "EUR": Decimal("1.64"),
    "CAD": Decimal("1.11"),
    "SGD": Decimal("1.13"),
    "JPY": Decimal("0.0102"),
    "DKK": Decimal("0.22"),
    "SEK": Decimal("0.15"),
    "NOK": Decimal("0.14"),
    "CHF": Decimal("1.74"),
}

RATES_ARE_STATIC = True


def supported_currencies() -> Dict[str, float]:
    return {code: float(rate) for code, rate in _TO_AUD.items()}


def convert(amount: Optional[Decimal], from_currency: str, to_currency: str) -> Optional[Decimal]:
    """Convert ``amount`` between currencies; None when a rate is unknown."""
    if amount is None:
        return None
    source = (from_currency or "").upper()
    target = (to_currency or "").upper()
    if source == target:
        return amount
    source_rate = _TO_AUD.get(source)
    target_rate = _TO_AUD.get(target)
    if source_rate is None or target_rate is None or target_rate == 0:
        return None
    return (Decimal(amount) * source_rate) / target_rate


def comparable_amount(
    amount: Optional[Decimal], from_currency: str, to_currency: str
) -> Optional[Decimal]:
    """Best-effort conversion used by price filtering and ranking.

    Returns None when the currencies are not comparable, and callers then skip
    the price constraint rather than silently applying a wrong one.
    """
    return convert(amount, from_currency, to_currency)
