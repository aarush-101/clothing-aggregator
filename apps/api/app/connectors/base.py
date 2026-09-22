"""The retailer connector interface.

Every source of products - a mock retailer, an affiliate feed, a retailer's own
API - implements this interface and returns the same :class:`Product` model, so
nothing downstream needs to know where a garment came from.

See ``docs/adding-a-connector.md`` for a step-by-step guide.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.logging_config import get_logger
from app.models.intent import SearchIntent
from app.models.product import Product, utcnow
from app.services.affiliate import build_affiliate_url

log = get_logger(__name__)


class ConnectorError(RuntimeError):
    """A connector failed in a way the search engine should report, not crash on."""


class ConnectorPermissionError(ConnectorError):
    """A connector was enabled without the authorisation it requires."""


@dataclass
class ConnectorHealth:
    key: str
    name: str
    healthy: bool
    latency_ms: Optional[int] = None
    message: Optional[str] = None
    checked_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "healthy": self.healthy,
            "latency_ms": self.latency_ms,
            "message": self.message,
            "checked_at": self.checked_at.isoformat(),
        }


class RetailerConnector(abc.ABC):
    """Base class for every product source.

    Subclasses must set :attr:`key` and :attr:`display_name`, and implement
    :meth:`search` and :meth:`normalise`.
    """

    #: stable machine key, e.g. "northbound"
    key: str = ""
    #: shopper-facing name, e.g. "Northbound Supply"
    display_name: str = ""
    #: ISO-3166 alpha-2 codes this retailer ships to; empty means worldwide
    ships_to: List[str] = []
    #: currency the retailer prices in
    currency: str = "AUD"
    #: genders this retailer stocks
    genders: List[str] = ["men", "unisex"]
    #: set True for connectors that need written retailer permission (HTML)
    requires_permission: bool = False

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ------------------------------------------------------------------ API
    def supports(self, intent: SearchIntent) -> bool:
        """Should this connector be queried for this intent?

        The default rules are shipping destination, gender and explicit brand
        exclusion. Override to add category or price coverage rules.
        """
        if self.ships_to and intent.destination_country not in self.ships_to:
            return False
        if self.genders and intent.gender.value not in self.genders:
            return False
        if self.key in intent.excluded_brands:
            return False
        return True

    @abc.abstractmethod
    async def search(self, intent: SearchIntent) -> List[Product]:
        """Query the source and return normalised products."""

    @abc.abstractmethod
    def normalise(self, raw_product: Any) -> Optional[Product]:
        """Map one raw record onto :class:`Product`; return None to discard it."""

    async def health_check(self) -> ConnectorHealth:
        """Cheap liveness probe. Override for network-backed connectors."""
        return ConnectorHealth(key=self.key, name=self.display_name, healthy=True)

    async def aclose(self) -> None:
        """Release any long-lived resources (HTTP clients, etc.)."""

    # -------------------------------------------------------------- helpers
    def affiliate_url_for(self, product_url: str, product_id: str) -> str:
        return build_affiliate_url(
            product_url=product_url,
            retailer=self.key,
            product_id=product_id,
            templates=self.settings.affiliate_template_map,
            subid_prefix=self.settings.affiliate_subid_prefix,
        )

    def build_product(self, **fields: Any) -> Optional[Product]:
        """Construct a Product, returning None if the record is unusable.

        Connectors call this instead of ``Product(...)`` so that one bad row in
        a 5,000-row feed never fails the whole connector.
        """
        fields.setdefault("retailer", self.key)
        fields.setdefault("retailer_name", self.display_name)
        fields.setdefault("currency", self.currency)
        fields.setdefault("retrieved_at", utcnow())
        product_url = fields.get("product_url")
        product_id = str(fields.get("product_id") or "")
        if not product_url or not product_id:
            return None
        try:
            fields.setdefault("affiliate_url", self.affiliate_url_for(product_url, product_id))
            return Product(**fields)
        except Exception as exc:
            log.debug(
                "connector.product_discarded",
                retailer=self.key,
                product_id=product_id,
                error=str(exc),
            )
            return None
