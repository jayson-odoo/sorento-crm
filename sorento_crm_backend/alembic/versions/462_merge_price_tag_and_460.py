"""merge the price-tag chain (458) with the spec-labels/replan merge (460)

PR #549 (price tag rounds 2+3, tip 458_merge_xco_reorder_specs) and PR #550
(460_merge_spec_labels_replan) merged within minutes of each other on 2 Sep
2026. 458 already joined 457_reorder_replan and 455_spec_registry_value_labels;
460 joined the same two independently, so main was left with two heads and the
deploy's single-head gate went red. No-op merge revision joining them.

Revision ID: 462_merge_price_tag_and_460
Revises: 458_merge_xco_reorder_specs, 460_merge_spec_labels_replan
Create Date: 2026-09-02 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '462_merge_price_tag_and_460'
down_revision = ('458_merge_xco_reorder_specs', '460_merge_spec_labels_replan')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
