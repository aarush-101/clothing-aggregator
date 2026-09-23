"""Data access for accounts, favourites, clicks and analytics.

These application-state repositories degrade gracefully when the database is
not configured. The current demo search can run without Postgres; the planned
product-index repository will require it (see docs/product-index.md).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select

from app.db.session import Database
from app.db.tables import (
    AffiliateClickEvent,
    ConnectorHealthRecord,
    Favourite,
    SavedSearch,
    SearchAnalytics,
    User,
)
from app.logging_config import get_logger
from app.services.search_engine import SearchAnalyticsSink

log = get_logger(__name__)

TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def fingerprint_client(*parts: Optional[str]) -> str:
    """One-way fingerprint of request metadata, for abuse detection only."""
    joined = "|".join(part or "" for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:64]


class AccountRepository:
    def __init__(self, database: Optional[Database]) -> None:
        self._db = database

    @property
    def available(self) -> bool:
        return self._db is not None

    # ------------------------------------------------------------- accounts
    async def create_anonymous_user(self) -> Optional[Dict[str, Any]]:
        if self._db is None:
            return None
        token = secrets.token_urlsafe(TOKEN_BYTES)
        async with self._db.session() as session:
            user = User(is_anonymous=True, token_hash=hash_token(token))
            session.add(user)
            await session.flush()
            return {"user_id": user.id, "token": token, "is_anonymous": True}

    async def get_user_by_token(self, token: str) -> Optional[User]:
        if self._db is None or not token:
            return None
        async with self._db.session() as session:
            result = await session.execute(select(User).where(User.token_hash == hash_token(token)))
            user = result.scalar_one_or_none()
            if user is not None:
                user.last_seen_at = datetime.now(timezone.utc)
            return user

    # -------------------------------------------------------- saved searches
    async def save_search(
        self,
        user_id: str,
        query: str,
        intent: Dict[str, Any],
        fingerprint: str,
        label: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if self._db is None:
            return None
        async with self._db.session() as session:
            existing = await session.execute(
                select(SavedSearch).where(
                    SavedSearch.user_id == user_id,
                    SavedSearch.intent_fingerprint == fingerprint,
                )
            )
            record = existing.scalar_one_or_none()
            if record is None:
                record = SavedSearch(
                    user_id=user_id,
                    query=query,
                    intent=intent,
                    intent_fingerprint=fingerprint,
                    label=label,
                )
                session.add(record)
            else:
                record.query = query
                record.intent = intent
                record.last_run_at = datetime.now(timezone.utc)
            await session.flush()
            return _saved_search_dict(record)

    async def list_saved_searches(self, user_id: str) -> List[Dict[str, Any]]:
        if self._db is None:
            return []
        async with self._db.session() as session:
            result = await session.execute(
                select(SavedSearch)
                .where(SavedSearch.user_id == user_id)
                .order_by(SavedSearch.created_at.desc())
                .limit(100)
            )
            return [_saved_search_dict(row) for row in result.scalars().all()]

    async def delete_saved_search(self, user_id: str, saved_search_id: str) -> bool:
        if self._db is None:
            return False
        async with self._db.session() as session:
            result = await session.execute(
                delete(SavedSearch).where(
                    SavedSearch.user_id == user_id, SavedSearch.id == saved_search_id
                )
            )
            return bool(result.rowcount)

    # ------------------------------------------------------------ favourites
    async def add_favourite(
        self, user_id: str, product: Dict[str, Any], group_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        if self._db is None:
            return None
        async with self._db.session() as session:
            existing = await session.execute(
                select(Favourite).where(
                    Favourite.user_id == user_id,
                    Favourite.retailer == product["retailer"],
                    Favourite.product_id == product["product_id"],
                )
            )
            record = existing.scalar_one_or_none()
            if record is None:
                record = Favourite(
                    user_id=user_id,
                    retailer=product["retailer"],
                    product_id=product["product_id"],
                    group_id=group_id,
                    title=product.get("title") or "Saved item",
                    product_snapshot=product,
                    price_at_save=product.get("price"),
                    currency=product.get("currency") or "AUD",
                )
                session.add(record)
                await session.flush()
            return _favourite_dict(record)

    async def list_favourites(self, user_id: str) -> List[Dict[str, Any]]:
        if self._db is None:
            return []
        async with self._db.session() as session:
            result = await session.execute(
                select(Favourite)
                .where(Favourite.user_id == user_id)
                .order_by(Favourite.created_at.desc())
                .limit(200)
            )
            return [_favourite_dict(row) for row in result.scalars().all()]

    async def remove_favourite(self, user_id: str, retailer: str, product_id: str) -> bool:
        if self._db is None:
            return False
        async with self._db.session() as session:
            result = await session.execute(
                delete(Favourite).where(
                    Favourite.user_id == user_id,
                    Favourite.retailer == retailer,
                    Favourite.product_id == product_id,
                )
            )
            return bool(result.rowcount)

    # ---------------------------------------------------------------- clicks
    async def record_click(self, payload: Dict[str, Any]) -> Optional[str]:
        if self._db is None:
            return None
        async with self._db.session() as session:
            event = AffiliateClickEvent(**payload)
            session.add(event)
            await session.flush()
            return event.id


class DatabaseAnalyticsSink(SearchAnalyticsSink):
    """Persists search analytics and connector health when a database exists."""

    def __init__(self, database: Optional[Database]) -> None:
        self._db = database

    async def record_search(self, payload: Dict[str, Any]) -> None:
        if self._db is None:
            return
        query = payload.get("query", "")
        async with self._db.session() as session:
            session.add(
                SearchAnalytics(
                    search_id=payload["search_id"],
                    query=query[:2000],
                    query_hash=hashlib.sha256(query.lower().encode("utf-8")).hexdigest()[:64],
                    intent_fingerprint=payload.get("intent_fingerprint", ""),
                    intent=payload.get("intent", {}),
                    status=payload.get("status", "completed"),
                    cache_state=payload.get("cache_state", "miss"),
                    result_count=payload.get("result_count", 0),
                    group_count=payload.get("group_count", 0),
                    duration_ms=payload.get("duration_ms", 0),
                )
            )

    async def record_connector_result(self, payload: Dict[str, Any]) -> None:
        if self._db is None:
            return
        async with self._db.session() as session:
            session.add(
                ConnectorHealthRecord(
                    connector_key=payload["connector_key"],
                    connector_name=payload.get("connector_name"),
                    healthy=bool(payload.get("healthy")),
                    state=payload.get("state"),
                    latency_ms=payload.get("duration_ms"),
                    product_count=payload.get("product_count"),
                    attempts=payload.get("attempts"),
                    error=(payload.get("error") or None),
                )
            )


def _saved_search_dict(record: SavedSearch) -> Dict[str, Any]:
    return {
        "id": record.id,
        "label": record.label,
        "query": record.query,
        "intent": record.intent,
        "intent_fingerprint": record.intent_fingerprint,
        "alerts_enabled": record.alerts_enabled,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "last_run_at": record.last_run_at.isoformat() if record.last_run_at else None,
    }


def _favourite_dict(record: Favourite) -> Dict[str, Any]:
    return {
        "id": record.id,
        "retailer": record.retailer,
        "product_id": record.product_id,
        "group_id": record.group_id,
        "title": record.title,
        "product": record.product_snapshot,
        "price_at_save": float(record.price_at_save) if record.price_at_save else None,
        "currency": record.currency,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
