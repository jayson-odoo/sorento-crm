"""OI-AUTO-CONFIRM: manual override columns on order inquiry rows + the one-time backfill.

Adds `ack_override` ('confirmed' | 'unconfirmed' | NULL), `ack_override_by`, `ack_override_at`
to `projects.order_inquiry_rows`, then runs `backfill_auto_confirm` once so every live row
reads the state the automatic rule gives it (idempotent). The backfill is NOT reversed on
downgrade: only the three columns are dropped.

Revision ID: oiac_0001_ack_override
Revises: lec_0004_prompt_synonyms
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "oiac_0001_ack_override"
down_revision = "lec_0004_prompt_synonyms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE projects.order_inquiry_rows ADD COLUMN IF NOT EXISTS ack_override VARCHAR(16)"
    )
    op.execute(
        "ALTER TABLE projects.order_inquiry_rows ADD COLUMN IF NOT EXISTS ack_override_by "
        "VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE projects.order_inquiry_rows ADD COLUMN IF NOT EXISTS ack_override_at "
        "TIMESTAMP WITHOUT TIME ZONE"
    )
    from app.services.oi_auto_confirm_backfill import backfill_auto_confirm

    backfill_auto_confirm(op.get_bind())


def downgrade() -> None:
    for column in ("ack_override_at", "ack_override_by", "ack_override"):
        op.execute(f"ALTER TABLE projects.order_inquiry_rows DROP COLUMN IF EXISTS {column}")
