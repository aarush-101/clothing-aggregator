"""Initial application schema.

Accounts, saved searches, favourites, retailer configuration, affiliate click
events, search analytics and connector health. Deliberately no product table:
this service does not maintain a master catalogue.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.base import GUID, JSONColumn

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=True, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "saved_searches",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "user_id",
            GUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=160), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("intent", JSONColumn, nullable=False),
        sa.Column("intent_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "intent_fingerprint", name="uq_saved_search_user_intent"),
    )
    op.create_index("ix_saved_searches_user", "saved_searches", ["user_id"])

    op.create_table(
        "favourites",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "user_id",
            GUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retailer", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=255), nullable=False),
        sa.Column("group_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("product_snapshot", JSONColumn, nullable=False),
        sa.Column("price_at_save", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="AUD"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "retailer", "product_id", name="uq_favourite_user_product"),
    )
    op.create_index("ix_favourites_user", "favourites", ["user_id"])

    op.create_table(
        "retailer_configs",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("connector_type", sa.String(length=32), nullable=False, server_default="feed"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("permission_granted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("affiliate_network", sa.String(length=64), nullable=True),
        sa.Column("affiliate_template", sa.Text(), nullable=True),
        sa.Column("config", JSONColumn, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "affiliate_click_events",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("search_id", sa.String(length=64), nullable=True),
        sa.Column(
            "user_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("retailer", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=255), nullable=False),
        sa.Column("subid", sa.String(length=64), nullable=True),
        sa.Column("destination_url", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="AUD"),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("client_fingerprint", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_click_events_created", "affiliate_click_events", ["created_at"])
    op.create_index("ix_click_events_retailer", "affiliate_click_events", ["retailer"])

    op.create_table(
        "search_analytics",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("search_id", sa.String(length=64), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("intent_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("intent", JSONColumn, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("cache_state", sa.String(length=16), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("group_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_search_analytics_created", "search_analytics", ["created_at"])
    op.create_index(
        "ix_search_analytics_fingerprint", "search_analytics", ["intent_fingerprint"]
    )

    op.create_table(
        "connector_health_records",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("connector_key", sa.String(length=64), nullable=False),
        sa.Column("connector_name", sa.String(length=160), nullable=True),
        sa.Column("healthy", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("product_count", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_connector_health_key_created",
        "connector_health_records",
        ["connector_key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_connector_health_key_created", table_name="connector_health_records")
    op.drop_table("connector_health_records")
    op.drop_index("ix_search_analytics_fingerprint", table_name="search_analytics")
    op.drop_index("ix_search_analytics_created", table_name="search_analytics")
    op.drop_table("search_analytics")
    op.drop_index("ix_click_events_retailer", table_name="affiliate_click_events")
    op.drop_index("ix_click_events_created", table_name="affiliate_click_events")
    op.drop_table("affiliate_click_events")
    op.drop_table("retailer_configs")
    op.drop_index("ix_favourites_user", table_name="favourites")
    op.drop_table("favourites")
    op.drop_index("ix_saved_searches_user", table_name="saved_searches")
    op.drop_table("saved_searches")
    op.drop_table("users")
