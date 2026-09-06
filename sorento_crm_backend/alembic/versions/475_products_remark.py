"""`products` gains `remark` (AutoCount `Item.Desc2`), stored on its own
column rather than concatenated into `description` (D4, S1).

The xlsx product import keeps concatenating Desc 2 into `description` (its
own established behaviour, unchanged); the ESB masters push stores it here
instead, so the two channels diverge on this one column by decision - see
`ingest-parity-standardisation-acceptance-criteria.md` AC-P1-6/AC-P1-9.

Revision ID: 475_products_remark
Revises: 474_spo_allocations_source_ref
"""
import sqlalchemy as sa
from alembic import op

revision = "475_products_remark"
down_revision = "474_spo_allocations_source_ref"
branch_labels = None
depends_on = None


def apply(bind) -> None:
    bind.execute(sa.text("ALTER TABLE products ADD COLUMN IF NOT EXISTS remark TEXT"))


def revert(bind) -> None:
    bind.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS remark"))


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
