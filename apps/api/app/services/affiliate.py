"""Affiliate / tracked outbound links.

Each retailer can have a deep-link template configured through
``AFFILIATE_TEMPLATES``. Two placeholders are supported:

``{url}``     URL-encoded destination product URL
``{subid}``   our click-tracking sub-id, echoed back by the network in reports

When no template is configured the shopper still goes to the retailer's own
product page - we never fabricate an affiliate link, and we never rewrite a URL
into something the retailer did not publish.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, Optional
from urllib.parse import quote

from app.models.product import sanitise_url

_SUBID_SAFE = re.compile(r"[^A-Za-z0-9_-]")
MAX_SUBID_LENGTH = 64


def build_subid(prefix: str, retailer: str, product_id: str) -> str:
    """Deterministic click-tracking id.

    Deliberately independent of the search that produced it so that cached
    results stay valid; the search id is recorded on the click event instead.
    """
    digest = hashlib.sha1(f"{retailer}:{product_id}".encode()).hexdigest()[:12]
    raw = f"{prefix}-{retailer}-{digest}"
    return _SUBID_SAFE.sub("-", raw)[:MAX_SUBID_LENGTH]


def build_affiliate_url(
    product_url: str,
    retailer: str,
    product_id: str,
    templates: Dict[str, str],
    subid_prefix: str = "ca",
) -> str:
    """Expand the retailer's affiliate template, or return the plain URL."""
    safe_product_url = sanitise_url(product_url)
    if not safe_product_url:
        raise ValueError(f"unsafe product URL for retailer '{retailer}'")

    template = templates.get(retailer)
    if not template:
        return safe_product_url

    subid = build_subid(subid_prefix, retailer, product_id)
    expanded = template.replace("{url}", quote(safe_product_url, safe="")).replace("{subid}", subid)
    safe_affiliate_url = sanitise_url(expanded)
    if not safe_affiliate_url:
        # A broken template must never break the product listing.
        return safe_product_url
    return safe_affiliate_url


def extract_subid(affiliate_url: str) -> Optional[str]:
    match = re.search(r"(?:subid|clickref|sid|u1)=([A-Za-z0-9_-]{1,64})", affiliate_url or "")
    return match.group(1) if match else None
