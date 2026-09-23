"""Persistent variant catalogue, source schedules and ingestion runs.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op
from app.db.base import JSONColumn

revision = "0002"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "catalogue_sources",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("next_due", sa.Float(), nullable=False),
        sa.Column("lease_until", sa.Float(), nullable=False),
        sa.Column("lease_token", sa.String(64)),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("last_success", sa.Float()),
        sa.Column("last_attempt", sa.Float()),
        sa.Column("error", sa.Text()),
        sa.Column("offer_count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "catalogue_offers",
        sa.Column("source_key", sa.String(64), primary_key=True),
        sa.Column("variant_id", sa.String(255), primary_key=True),
        sa.Column("category", sa.String(160)),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("payload", JSONColumn, nullable=False),
    )
    op.create_index(
        "ix_catalogue_offer_search", "catalogue_offers", ["source_key", "category", "expires_at"]
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("completed_at", sa.Float()),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("offer_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text()),
    )
    op.create_index(
        "ix_ingestion_runs_source_started", "ingestion_runs", ["source_key", "started_at"]
    )


def downgrade():
    op.drop_table("ingestion_runs")
    op.drop_table("catalogue_offers")
    op.drop_table("catalogue_sources")
