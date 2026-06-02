"""Index conversation_sla_tracking on (source_entity_type, source_entity_id).

Revision ID: 214_sla_tracking_source_entity_index
Revises: 213_complaints_quantity
Create Date: 2026-05-25

get_tracking_by_source_entity filters on this pair on every stock-inquiry /
complaint reply; without the index it is a sequential scan on a growing table.
"""
from alembic import op


revision = "214_sla_tracking_source_entity_index"
down_revision = "213_complaints_quantity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: the index may already exist from a prior partial run that
    # failed before alembic stamped this revision.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conversation_sla_tracking_source_entity "
        "ON conversation_sla_tracking (source_entity_type, source_entity_id)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_conversation_sla_tracking_source_entity"
    )
