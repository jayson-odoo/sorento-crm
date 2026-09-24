"""stock debt export: generic row_count / sheet_count on user_downloads

PLAN-stock-debt-filters-totals-export-24sep.md, Phase 2 (AC-12b). `generate_stock_debt_
xlsx` stamps these at `mark_ready` so a poll can read "212 rows, 3 sheets" without opening
the workbook - the same reason `516_low_stock_report` added `row_count_low` / `row_count_
all`, but GENERIC rather than low-stock's own two-sheet shape: this export's sheet count
varies with `split` (1, or one per supplier/category/pair), so a fixed pair of named
columns would not fit a THIRD export kind either. `row_count_low` / `row_count_all` are
untouched - they still mean what they meant, and only the low stock task writes them.

Both columns are additive and nullable, so the downgrade is a plain drop and no data is
rewritten either way.

Revision ID: sdbt_0001_download_counts
Revises: oirs_0002_reserve_round2
"""
from alembic import op
import sqlalchemy as sa

revision = "sdbt_0001_download_counts"
down_revision = "oirs_0002_reserve_round2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_downloads", sa.Column("row_count", sa.Integer(), nullable=True))
    op.add_column("user_downloads", sa.Column("sheet_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_downloads", "sheet_count")
    op.drop_column("user_downloads", "row_count")
