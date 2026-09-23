"""Load the checked-in retailer registry; only explicit ingestion entries run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, model_validator

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "data" / "retailers.json"


class IngestionConfig(BaseModel):
    enabled: bool = False
    method: str = "shopify_json"
    collection: str
    currency: str = "AUD"
    refresh_seconds: int = Field(default=21600, ge=3600)
    max_pages: int = Field(default=30, ge=1, le=100)
    # Own-label stores whose Shopify vendor field is a department, not a brand.
    default_brand: Optional[str] = None
    # For catch-all collections that include homewares/books: keep only garments.
    garments_only: bool = False
    # Brand stores often use internal vendor names ("Levi AUS/NZ Production",
    # "CORE"); map them, case-insensitively, to the label shoppers know.
    vendor_brands: Dict[str, str] = Field(default_factory=dict)


class Retailer(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_\-]{2,40}$")
    name: str
    website_url: str
    menswear_url: str
    storefront_market: Optional[str] = None
    website_verification: dict
    data_access: dict
    ingestion: Optional[IngestionConfig] = None

    @model_validator(mode="after")
    def validate_source(self):
        home = urlsplit(self.website_url)
        if home.scheme != "https" or not home.hostname or home.username or home.password:
            raise ValueError("Retailer websites must use public HTTPS URLs")
        if home.port or home.query or home.fragment:
            raise ValueError("Retailer home URL must not include a port, query or fragment")
        if self.ingestion:
            import re

            if self.ingestion.method != "shopify_json":
                raise ValueError("Unsupported ingestion method")
            if not re.fullmatch(r"[a-z0-9-]+", self.ingestion.collection):
                raise ValueError("Invalid collection handle")
            if not re.fullmatch(r"[A-Z]{3}", self.ingestion.currency):
                raise ValueError("Invalid currency")
            if home.path not in {"", "/"}:
                raise ValueError("Shopify collection ingestion requires a root storefront URL")
            if self.ingestion.enabled and self.website_verification.get("status") != "verified":
                raise ValueError("Review the website before enabling ingestion")
        return self

    @property
    def catalogue_url(self) -> str:
        if not self.ingestion:
            raise ValueError("Retailer has no ingestion configuration")
        return (
            f"{self.website_url.rstrip('/')}/collections/{self.ingestion.collection}/products.json"
        )


def load_retailers(path: Path = REGISTRY_PATH) -> List[Retailer]:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported retailer registry version")
    retailers = [Retailer.model_validate(row) for row in payload["retailers"]]
    if len({r.key for r in retailers}) != len(retailers):
        raise ValueError("Duplicate retailer keys")
    enabled_hosts = [
        urlsplit(r.website_url).hostname for r in retailers if r.ingestion and r.ingestion.enabled
    ]
    if len(set(enabled_hosts)) != len(enabled_hosts):
        raise ValueError("Only one ingestion source per host is supported")
    return retailers


def enabled_retailers() -> List[Retailer]:
    return [r for r in load_retailers() if r.ingestion and r.ingestion.enabled]
