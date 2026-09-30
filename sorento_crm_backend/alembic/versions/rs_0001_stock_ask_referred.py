"""REFER-SALESMAN (owner ruling 30 Sep 2026, PLAN-refer-salesman-30sep.md): every reply that
refers a dealer to their salesman is a `stock_asks` row.

Two new branches - `incoming_eta` (a dealer's incoming ETA reply) and `referred` (a miss, a
not-found code, a declined did-you-mean) - and `quantity` nullable, since neither carries the
dealer's quantity. Idempotent: the CHECK is dropped and re-added, the column altered in place.

Revision ID: rs_0001_stock_ask_referred
Revises: lsa_0001_show_all_counts
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "rs_0001_stock_ask_referred"
down_revision = "lsa_0001_show_all_counts"
branch_labels = None
depends_on = None

_OLD = "('too_big', 'in_stock', 'incoming', 'no_incoming')"
_NEW = "('too_big', 'in_stock', 'incoming', 'no_incoming', 'incoming_eta', 'referred')"


def _branch_check(bind, values: str) -> None:
    bind.execute(sa.text("ALTER TABLE stock_asks DROP CONSTRAINT IF EXISTS ck_stock_asks_branch"))
    bind.execute(
        sa.text(f"ALTER TABLE stock_asks ADD CONSTRAINT ck_stock_asks_branch CHECK (branch IN {values})")
    )


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("ALTER TABLE stock_asks ALTER COLUMN quantity DROP NOT NULL"))
    _branch_check(bind, _NEW)


def downgrade() -> None:
    bind = op.get_bind()
    # Rows the new branches wrote cannot satisfy the old shape: take them out first (every
    # stock-branch row carries a quantity, so nothing null is left after this).
    bind.execute(sa.text("DELETE FROM stock_asks WHERE branch IN ('incoming_eta', 'referred')"))
    _branch_check(bind, _OLD)
    bind.execute(sa.text("ALTER TABLE stock_asks ALTER COLUMN quantity SET NOT NULL"))
