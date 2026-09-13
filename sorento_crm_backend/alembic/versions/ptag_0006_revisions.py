"""price_tag_request revisions - revision_no/last_revised_at, config seed

R3-1 of PLAN-portal-price-tag-journey-r8 "Round 3": price_tag_request becomes a
fourth RevisionAdapter (app/services/portal_revision_service.py). Strictly
additive, same shape as portal_rev_0001's seed for the first three types:

1. `revision_no` / `last_revised_at` on `price_tag_requests`.
2. A `portal_revision_configs` row for `price_tag_request`, seeded DISABLED
   (an owner opts in from System Settings, same as `complaint` shipped) with
   allowed statuses `new, changes_requested` - the same two the post-submit
   PUT window used to cover under S8's (now reversed) edit gate.

Revision ID: ptag_0006_revisions
Revises: 514_merge_513_heads
Create Date: 2026-09-13
"""
import json

from alembic import op
import sqlalchemy as sa


revision = "ptag_0006_revisions"
down_revision = "514_merge_513_heads"
branch_labels = None
depends_on = None

_ALLOWED_STATUSES = ("new", "changes_requested")


def upgrade() -> None:
    op.add_column(
        "price_tag_requests",
        sa.Column("revision_no", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "price_tag_requests",
        sa.Column("last_revised_at", sa.DateTime(timezone=False), nullable=True),
    )

    # Idempotent, so a partially-applied run and the shared dev database both
    # re-run cleanly (same guard portal_rev_0001 uses).
    op.execute(
        sa.text(
            "INSERT INTO portal_revision_configs "
            "(id, source_entity_type, is_enabled, max_revisions, allowed_statuses, restart_stage_code) "
            "VALUES (gen_random_uuid(), :t, false, NULL, CAST(:s AS jsonb), NULL) "
            "ON CONFLICT (source_entity_type) DO NOTHING"
        ).bindparams(t="price_tag_request", s=json.dumps(list(_ALLOWED_STATUSES)))
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM portal_revision_configs WHERE source_entity_type = :t"
        ).bindparams(t="price_tag_request")
    )
    op.drop_column("price_tag_requests", "last_revised_at")
    op.drop_column("price_tag_requests", "revision_no")
