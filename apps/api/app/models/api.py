"""Request and response bodies for the HTTP API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.product import sanitise_text, sanitise_url


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Hard ceiling; the configured SEARCH_MAX_QUERY_LENGTH is applied on top.
    query: str = Field(min_length=1, max_length=2000)


class SearchCreatedResponse(BaseModel):
    search_id: str
    query: str
    status: str = "accepted"
    events_url: str
    snapshot_url: str


class ClickRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retailer: str = Field(min_length=1, max_length=64)
    product_id: str = Field(min_length=1, max_length=255)
    destination_url: str = Field(max_length=2048)
    search_id: Optional[str] = Field(default=None, max_length=64)
    subid: Optional[str] = Field(default=None, max_length=64)
    price: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=3)
    position: Optional[int] = Field(default=None, ge=0, le=10000)

    @field_validator("destination_url")
    @classmethod
    def _safe_destination(cls, value: str) -> str:
        url = sanitise_url(value)
        if not url:
            raise ValueError("destination_url must be an http(s) URL")
        return url


class ClickResponse(BaseModel):
    recorded: bool
    click_id: Optional[str] = None
    destination_url: str


class AnonymousSessionResponse(BaseModel):
    user_id: str
    token: str
    is_anonymous: bool = True


class SaveSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    label: Optional[str] = Field(default=None, max_length=160)

    @field_validator("label")
    @classmethod
    def _clean_label(cls, value: Optional[str]) -> Optional[str]:
        return sanitise_text(value, limit=160) if value else None


class FavouriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: Dict[str, Any]
    group_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("product")
    @classmethod
    def _required_fields(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        for field in ("retailer", "product_id", "title"):
            if not value.get(field):
                raise ValueError(f"product.{field} is required")
        return value


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    checks: Dict[str, Any]


class RetailerSummary(BaseModel):
    key: str
    name: str
    type: str
    ships_to: List[str]
    currency: str
    requires_permission: bool
    healthy: Optional[bool] = None
    message: Optional[str] = None
    latency_ms: Optional[int] = None
