"""Filter columns on catalogue offers; offers are re-imported, not converted.

Offers are a cache of retailer inventory that expires within 48 hours, so the
table is rebuilt empty and every source is made due for an immediate import.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op
from app.db.base import JSONColumn

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _offers_table(extra):
    op.create_table(
        "catalogue_offers",
        sa.Column("source_key", sa.String(64), primary_key=True),
        sa.Column("variant_id", sa.String(255), primary_key=True),
        sa.Column("category", sa.String(160)),
        sa.Column("expires_at", sa.Float(), nullable=False),
        *extra,
        sa.Column("payload", JSONColumn, nullable=False),
    )
    op.create_index(
        "ix_catalogue_offer_search", "catalogue_offers", ["source_key", "category", "expires_at"]
    )


def _reset_sources():
    op.execute("UPDATE catalogue_sources SET next_due = 0, offer_count = 0")


def upgrade():
    op.drop_table("catalogue_offers")
    _offers_table(
        [
            sa.Column("price", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False),
            sa.Column("in_stock", sa.Boolean()),
            sa.Column("size", sa.String(40)),
            sa.Column("brand", sa.String(160)),
            sa.Column("search_text", sa.Text(), nullable=False),
        ]
    )
    op.create_index("ix_catalogue_offer_price", "catalogue_offers", ["price"])
    op.create_index("ix_catalogue_offer_brand", "catalogue_offers", ["brand"])
    _reset_sources()


def downgrade():
    op.drop_table("catalogue_offers")
    _offers_table([])
    _reset_sources()
