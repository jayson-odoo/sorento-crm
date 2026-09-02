"""merge spec value labels and reorder replan heads

PR #520 (455_spec_registry_value_labels) and PR #493 (457_reorder_replan) both
chained onto 454_order_inquiry_born_ack and merged the same evening, 2 Sep 2026,
leaving two alembic heads. This is a no-op merge revision that joins them so
the tree has a single head again. The next migration (458_claim_crm_supply on
PR #490) chains onto this revision.

Revision ID: 460_merge_spec_labels_replan
Revises: 455_spec_registry_value_labels, 457_reorder_replan
Create Date: 2026-09-02 20:13:53.449757

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '460_merge_spec_labels_replan'
down_revision = ('455_spec_registry_value_labels', '457_reorder_replan')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
