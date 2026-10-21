"""CHAT-CLOSED-LISTS R6-1: `matches_bare_size` on the spec registry.

A size given alone (no dimension named) matches the keys flagged here (width and length by
data, set in the registry, never in code). Additive and idempotent (`IF NOT EXISTS`) so the
shared dev DB, which converges through `create_all`, can take it in any order.

Revision ID: spec_bare_size_0001
Revises: chs_0001_direct_ingress
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "spec_bare_size_0001"
down_revision = "chs_0001_direct_ingress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE product_spec_registry "
        "ADD COLUMN IF NOT EXISTS matches_bare_size boolean NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE product_spec_registry DROP COLUMN IF EXISTS matches_bare_size")
