"""Portal form grant moves from contact access types to market segments
(PLAN-portal-forms-market-segment D1/D4, r2/r3).

Schema only - no data statements. D3's base default (every contact sees the
four legacy kinds regardless of segment or override) makes a seed/backfill
unnecessary: nobody loses a form at deploy, and `price_tag_request` stays
opt-in exactly as it is today (the one existing override row survives
untouched).

1. Add `market_segments.portal_form_types` JSONB NOT NULL default `'[]'`.
2. Drop `contact_access_types.portal_form_types` (access types no longer
   carry any portal-form grant).

Both steps are idempotent: a second run, or a legacy create_all database
already missing/carrying one side, converges without error.

Downgrade drops the segment column and restores the access-type column with
the same default - data is not restored (D4).

Revision ID: ptag_0012_seg_forms
Revises: ptag_0011_line_promo
Create Date: 2026-09-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "ptag_0012_seg_forms"
down_revision = "ptag_0011_line_promo"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return inspect(bind).has_table(table)


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "market_segments"):
        if "portal_form_types" not in _columns(bind, "market_segments"):
            op.add_column(
                "market_segments",
                sa.Column(
                    "portal_form_types",
                    postgresql.JSONB(astext_type=sa.Text()),
                    nullable=False,
                    server_default=sa.text("'[]'::jsonb"),
                ),
            )

    if _has_table(bind, "contact_access_types"):
        if "portal_form_types" in _columns(bind, "contact_access_types"):
            op.drop_column("contact_access_types", "portal_form_types")


def downgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "contact_access_types"):
        if "portal_form_types" not in _columns(bind, "contact_access_types"):
            op.add_column(
                "contact_access_types",
                sa.Column(
                    "portal_form_types",
                    postgresql.JSONB(astext_type=sa.Text()),
                    nullable=False,
                    server_default=sa.text("'[]'::jsonb"),
                ),
            )

    if _has_table(bind, "market_segments"):
        if "portal_form_types" in _columns(bind, "market_segments"):
            op.drop_column("market_segments", "portal_form_types")
