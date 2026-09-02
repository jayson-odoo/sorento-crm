"""merge xco and spec-labels mergepoints

PR #549 and PR #550 each added their own no-op mergepoint over the same two
Sep 2026 alembic heads (457_ptag_line_xco_repair, 457_reorder_replan,
455_spec_registry_value_labels), landing 458_merge_xco_reorder_specs and
460_merge_spec_labels_replan as two separate heads on main. This revision
joins the two mergepoints back into one head. The next real migration,
458_claim_crm_supply on PR #490, chains onto this revision.

Revision ID: 462_merge_xco_spec_labels
Revises: 458_merge_xco_reorder_specs, 460_merge_spec_labels_replan
Create Date: 2026-09-02 22:23:56.299782

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '462_merge_xco_spec_labels'
down_revision = ('458_merge_xco_reorder_specs', '460_merge_spec_labels_replan')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
