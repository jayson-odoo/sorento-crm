"""SCM: split scm.item_classification's ABC letter by demand class (project vs retail).

Captain's rule, 19 Aug 2026: hot-selling is judged by delivered QUANTITY per demand class
(project vs retail), never money - the existing all-demand `abc_class`/`annual_value` (the
reorder engine's inventory-value lens) is untouched. Adds the four project/retail columns.

Revision ID: 389_item_classification_abc_by_demand_class
Revises: 388_drop_osla_company_default
"""
import sqlalchemy as sa
from alembic import op

revision = "389_item_classification_abc_by_demand_class"
down_revision = "388_drop_osla_company_default"
branch_labels = None
depends_on = None

_TABLE = "item_classification"
_SCHEMA = "scm"


def upgrade() -> None:
    # All four nullable: an existing row belongs to a run before this split existed, and
    # NULL means "no demand of that class in the window" (unknown), exactly as a NULL
    # `abc_class` means unknown today. Grain and unique constraint are unchanged.
    for column in (
        sa.Column("abc_class_project", sa.String(1), nullable=True),
        sa.Column("abc_class_retail", sa.String(1), nullable=True),
        sa.Column("annual_qty_project", sa.Numeric(), nullable=True),
        sa.Column("annual_qty_retail", sa.Numeric(), nullable=True),
    ):
        op.add_column(_TABLE, column, schema=_SCHEMA)


def downgrade() -> None:
    for name in (
        "annual_qty_retail",
        "annual_qty_project",
        "abc_class_retail",
        "abc_class_project",
    ):
        op.drop_column(_TABLE, name, schema=_SCHEMA)
