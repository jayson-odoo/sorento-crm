"""merge audit_trace_id + transporters_updated_at heads

Two migrations forked from 253 (254_audit_trace_id in parallel with
255 -> 256_transporters_updated_at), creating two alembic heads and breaking
`alembic upgrade head` on deploy. This no-op merge unifies them into one head.

Revision ID: 257_merge_trace_id_transporters
Revises: 254_audit_trace_id, 256_transporters_updated_at
Create Date: 2026-07-03

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "257_merge_trace_id_transporters"
down_revision = ("254_audit_trace_id", "256_transporters_updated_at")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
