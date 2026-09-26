"""Portal form grant moves from contact access types to market segments
(PLAN-portal-forms-market-segment D1/D4, r4 expand-only).

Expand only - no data statements, no column drop. D4 r4 (security review):
blue/green deploy runs `alembic upgrade head` in the NEW container while the
OLD image still serves traffic and still selects
`contact_access_types.portal_form_types` (old resolver + every ORM load of
`ContactAccessType`), so dropping it here 500s the portal and the Respond.io
ingest path for the whole swap window. This migration therefore only ADDS
`market_segments.portal_form_types` - the model stops mapping the
access-type column now (unmapped column, still physically present), and the
column drop lands as its own migration next release (issue #965).

D3's base default (every contact sees the four legacy kinds regardless of
segment or override) makes a seed/backfill unnecessary: nobody loses a form
at deploy, and `price_tag_request` stays opt-in exactly as it is today (the
one existing override row survives untouched).

Idempotent: a second run, or a legacy create_all database already carrying
the column, converges without error.

Downgrade drops the segment column only - it never touched the access-type
column, so there is nothing to restore there.

Revision ID: ptag_0012_seg_forms
Revises: ptag_0012_data_change_cache
Create Date: 2026-09-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "ptag_0012_seg_forms"
down_revision = "ptag_0012_data_change_cache"
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


def downgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "market_segments"):
        if "portal_form_types" in _columns(bind, "market_segments"):
            op.drop_column("market_segments", "portal_form_types")
