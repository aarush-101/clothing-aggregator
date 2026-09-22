"""Persistent application tables.

PostgreSQL stores *application* state only - accounts, saved searches,
favourites, retailer configuration, click events, analytics and connector
health. Product data is deliberately absent: there is no master catalogue, and
retailer results live in Redis with a 24-hour ceiling.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, JSONColumn, created_at_column, uuid_pk


class User(Base):
    """An account.

    Accounts are optional: search works without one. A device can claim an
    anonymous account (``is_anonymous=True``) to save searches and favourites,
    and upgrade it later by setting an email and password hash.
    """

    __tablename__ = "users"

    id: Mapped[str] = uuid_pk()
    email: Mapped[Optional[str]] = mapped_column(String(320), unique=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Only the hash of the bearer token is stored, never the token itself.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    saved_searches: Mapped[List[SavedSearch]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    favourites: Mapped[List[Favourite]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class SavedSearch(Base):
    __tablename__ = "saved_searches"
    __table_args__ = (
        UniqueConstraint("user_id", "intent_fingerprint", name="uq_saved_search_user_intent"),
        Index("ix_saved_searches_user", "user_id"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[Dict[str, Any]] = mapped_column(JSONColumn, nullable=False, default=dict)
    intent_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # Reserved for the price/restock alerts described in the roadmap.
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="saved_searches")


class Favourite(Base):
    __tablename__ = "favourites"
    __table_args__ = (
        UniqueConstraint("user_id", "retailer", "product_id", name="uq_favourite_user_product"),
        Index("ix_favourites_user", "user_id"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    retailer: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    group_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # A snapshot, not a catalogue row: what the shopper saw when they saved it.
    product_snapshot: Mapped[Dict[str, Any]] = mapped_column(
        JSONColumn, nullable=False, default=dict
    )
    price_at_save: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="AUD", nullable=False)
    created_at: Mapped[datetime] = created_at_column()

    user: Mapped[User] = relationship(back_populates="favourites")


class RetailerConfig(Base):
    """Database-backed connector configuration.

    Lets an operator enable, disable or re-point a connector without a deploy.
    Environment variables remain the source of truth at boot; this table is the
    override layer (see ``docs/adding-a-connector.md``).
    """

    __tablename__ = "retailer_configs"

    id: Mapped[str] = uuid_pk()
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(32), nullable=False, default="feed")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True only when the retailer has given written permission (HTML connectors).
    permission_granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    affiliate_network: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    affiliate_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config: Mapped[Dict[str, Any]] = mapped_column(JSONColumn, nullable=False, default=dict)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AffiliateClickEvent(Base):
    __tablename__ = "affiliate_click_events"
    __table_args__ = (
        Index("ix_click_events_created", "created_at"),
        Index("ix_click_events_retailer", "retailer"),
    )

    id: Mapped[str] = uuid_pk()
    search_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    retailer: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    destination_url: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="AUD", nullable=False)
    position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Hashed, never raw - enough to spot abuse, not enough to identify a person.
    client_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = created_at_column()


class SearchAnalytics(Base):
    __tablename__ = "search_analytics"
    __table_args__ = (
        Index("ix_search_analytics_created", "created_at"),
        Index("ix_search_analytics_fingerprint", "intent_fingerprint"),
    )

    id: Mapped[str] = uuid_pk()
    search_id: Mapped[str] = mapped_column(String(64), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    intent_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    intent: Mapped[Dict[str, Any]] = mapped_column(JSONColumn, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    cache_state: Mapped[str] = mapped_column(String(16), nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    group_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class ConnectorHealthRecord(Base):
    __tablename__ = "connector_health_records"
    __table_args__ = (Index("ix_connector_health_key_created", "connector_key", "created_at"),)

    id: Mapped[str] = uuid_pk()
    connector_key: Mapped[str] = mapped_column(String(64), nullable=False)
    connector_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    healthy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    state: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    product_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    attempts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = created_at_column()
