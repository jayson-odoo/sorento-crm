"""sales_order_lines.uom - the never-created column the model now maps.

Revision ID: 395_so_line_uom
Revises: 394_reorder_coverage_until
Create Date: 2026-08-20

Code review finding B1 on PLAN-scm-stack-followups-19aug: commit 9a730b5dc mapped
`SalesOrderLine.uom` (app/models/order.py) so a line could carry a per-line UoM override,
but no migration in the chain ever added the column - same gap 359 closed for
`unit_price` on this same table. A database built from the migrations alone (CI, a fresh
install, a clean restore) has no such column, and every ORM load of `SalesOrderLine`
(list, detail, upsert) 500s with `UndefinedColumn` the moment the mapped attribute is
touched. Guarded the same way as 359: free where the column already exists (every
database restored from the shared local Postgres, which converges via
`Base.metadata.create_all` and has carried it since 9a730b5dc), decisive where it does not.
"""
from alembic import op
import sqlalchemy as sa


revision = "395_so_line_uom"
down_revision = "394_reorder_coverage_until"
branch_labels = None
depends_on = None


def _line_columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("sales_order_lines")}


def upgrade() -> None:
    if "uom" not in _line_columns():
        op.add_column(
            "sales_order_lines",
            sa.Column("uom", sa.String(100), nullable=True),
        )


def downgrade() -> None:
    if "uom" in _line_columns():
        op.drop_column("sales_order_lines", "uom")
