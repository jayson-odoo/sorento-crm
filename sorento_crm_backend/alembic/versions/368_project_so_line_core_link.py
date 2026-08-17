"""The Project SO line's link to its reconciled core SO line (front planning 6.1).

`projects.sales_orders.so_id` already links the Project SO HEADER to the core
`public.sales_orders` row. The LINE has had no counterpart, so nothing could say which
core line a Project line was promised from - and the atomic confirmation in
PLAN-scm-front-planning.md 3.1 is written against exactly that: "verify that every Project
line has a unique reconciled core SO line", with the balance invariant computed from the
core line's current open quantity.

Nullable, because reconciliation happens later (stage 1B's AutoCount upload fills it) and
an unreconciled line is simply not confirmable. The unique index is PARTIAL for the same
reason: NULL is the normal state until then, and only a reconciled link has to be unique.
One Project line per core line is what stops the same committed quantity being promised
from two places.

**No backfill is possible.** No line-level link exists anywhere today - not on the project
line, not on the core line, not in a join table - so there is nothing to derive an existing
value from. Every existing row starts NULL, and reconciliation is the only writer.

Revision ID: 368_project_so_line_core_link
Revises: 2c859e3161da
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "368_project_so_line_core_link"
down_revision = "2c859e3161da"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sales_order_lines",
        sa.Column("core_sales_order_line_id", UUID(as_uuid=False), nullable=True),
        schema="projects",
    )
    op.create_foreign_key(
        "fk_projects_so_line_core_line",
        "sales_order_lines",
        "sales_order_lines",
        ["core_sales_order_line_id"],
        ["id"],
        source_schema="projects",
        referent_schema="public",
        ondelete="SET NULL",
    )
    op.create_index(
        "uq_projects_so_line_core_line",
        "sales_order_lines",
        ["core_sales_order_line_id"],
        unique=True,
        schema="projects",
        postgresql_where=sa.text("core_sales_order_line_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_projects_so_line_core_line", "sales_order_lines", schema="projects")
    op.drop_constraint(
        "fk_projects_so_line_core_line", "sales_order_lines", schema="projects"
    )
    op.drop_column("sales_order_lines", "core_sales_order_line_id", schema="projects")
