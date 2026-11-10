"""combo part labels and parts line (COMBO-SETTINGS-UX)

Additive and nullable: `product_combo_parts.label`, `product_combos.main_label` and
`product_combos.parts_line`.

Revision ID: combo_0001_part_labels
Revises: pfc_0001_line_is_section
"""
from alembic import op
import sqlalchemy as sa

revision = "combo_0001_part_labels"
down_revision = "pfc_0001_line_is_section"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("product_combo_parts", sa.Column("label", sa.String(length=100), nullable=True))
    op.add_column("product_combos", sa.Column("main_label", sa.String(length=100), nullable=True))
    op.add_column("product_combos", sa.Column("parts_line", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("product_combos", "parts_line")
    op.drop_column("product_combos", "main_label")
    op.drop_column("product_combo_parts", "label")
