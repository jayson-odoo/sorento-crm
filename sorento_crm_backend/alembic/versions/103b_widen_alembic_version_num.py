"""Widen alembic_version.version_num for long revision IDs (PostgreSQL default is VARCHAR(32)).

Revision ID: 103b_widen_alembic_ver_len
Revises: 103_inbound_shipment_eta
Create Date: 2026-03-19

Without this, revisions longer than 32 chars (e.g. 104_orders_estimated_delivery_label)
fail when Alembic updates the version row.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "103b_widen_alembic_ver_len"
down_revision = "103_inbound_shipment_eta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"))


def downgrade() -> None:
    # Do not shrink: current revision id may exceed 32 chars after 104+.
    pass
