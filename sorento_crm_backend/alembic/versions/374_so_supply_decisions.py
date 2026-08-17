"""The atomic Project SO supply decision (front planning 3.1, 6.2, 6.3).

Four things land together because they are one contract:

1. `projects.so_supply_decisions` - one revision per confirmation, one snapshot per line,
   and a PARTIAL UNIQUE index on `(project_sales_order_id) WHERE state = 'active'`. That
   index is the whole concurrency story: two CS sessions confirming the same order race to
   insert, one wins, and the loser's insert fails on the index instead of both of them
   promising the same stock.
2. `projects.so_line_allocations` learns `decision_id`, `reason` and
   `donor_impact_snapshot`, so the components of one confirmation are grouped, a Borrow
   carries the reason CS typed, and the donor's position at that moment survives.
3. `projects.order_inquiry_rows` learns `supply_decision_id`, so purchasing's row is
   traceable to the decision that raised it (AC-D06) and a superseded revision's unplaced
   rows can be found and cancelled.
4. `scm.committed_v` learns the section 4 precedence: the sheet leg
   (`demand_origin = 'scm_order_inquiry'`) counts only while the core SO has NO active
   confirmed decision. Otherwise a sheet-named SO that CS later confirms is counted twice -
   once as the sheet's quantity and once as the confirmed Buy.

**Every object is created only if it is absent.** Stage 2 is being built in parallel off
the same base and its own migration creates `so_supply_decisions` and adds
`order_inquiry_rows.supply_decision_id` too (it READS the table; this slice owns the
confirmation that writes it). Neither branch carries the other's migration and merge order
into `main` is not decided here, so whichever lands second must be a clean no-op for the
shared objects rather than dying on a duplicate. The `so_line_allocations` additions belong
to this lane alone and are guarded the same way for symmetry.

Revision ID: 374_so_supply_decisions
Revises: 373_merge_scm_stage0_1a
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "374_so_supply_decisions"
down_revision = "373_merge_scm_stage0_1a"
branch_labels = None
depends_on = None

_SCHEMA = "projects"
_DECISIONS = "so_supply_decisions"
_ALLOCATIONS = "so_line_allocations"
_INQUIRY_ROWS = "order_inquiry_rows"


# The body of `scm.committed_v` as of this revision. FROZEN here rather than imported from
# `app.services.scm.demand.COMMITTED_V_SQL`, exactly as 340 and 346 freeze theirs: a
# migration replayed a year from now must install the view the way it was when it shipped,
# not the way the constant reads by then. The two are edited together (the constant carries
# the same predicate) and this copy is what the database gets.
_AS_OF_374 = """
CREATE OR REPLACE VIEW scm.committed_v AS
SELECT sol.product_id,
       sol.warehouse_id,
       SUM(GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                    - COALESCE(sol.qty_delivered, 0), 0)) AS committed
FROM sales_order_lines sol
JOIN sales_orders so ON so.id = sol.sales_order_id
WHERE so.status = 'open'
  AND sol.line_status = 'open'
  AND sol.purchasing_status <> 'covered'
  AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
               - COALESCE(sol.qty_delivered, 0), 0) > 0
  -- S13b: project demand comes from the Order Inquiry; the book supplies the rest.
  -- Front planning section 4: and only while CS has not confirmed a supply decision for
  -- it, after which the confirmed Buy residual replaces the sheet quantity.
  AND (so.demand_class IS DISTINCT FROM 'project'
       OR (so.demand_origin = 'scm_order_inquiry'
           AND NOT EXISTS (
               SELECT 1
               FROM projects.sales_orders pso
               JOIN projects.so_supply_decisions d
                 ON d.project_sales_order_id = pso.id
               WHERE pso.so_id = so.id
                 AND d.state = 'active'
           )))
GROUP BY sol.product_id, sol.warehouse_id;
"""

_AS_OF_346 = """
CREATE OR REPLACE VIEW scm.committed_v AS
SELECT sol.product_id,
       sol.warehouse_id,
       SUM(GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                    - COALESCE(sol.qty_delivered, 0), 0)) AS committed
FROM sales_order_lines sol
JOIN sales_orders so ON so.id = sol.sales_order_id
WHERE so.status = 'open'
  AND sol.line_status = 'open'
  AND sol.purchasing_status <> 'covered'
  AND GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
               - COALESCE(sol.qty_delivered, 0), 0) > 0
  -- S13b: project demand comes from the Order Inquiry; the book supplies the rest
  AND (so.demand_class IS DISTINCT FROM 'project'
       OR so.demand_origin = 'scm_order_inquiry')
GROUP BY sol.product_id, sol.warehouse_id;
"""


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name, schema=_SCHEMA)


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return column in {col["name"] for col in _inspector().get_columns(table, schema=_SCHEMA)}


def _has_index(table: str, name: str) -> bool:
    if not _has_table(table):
        return False
    inspector = _inspector()
    names = {idx["name"] for idx in inspector.get_indexes(table, schema=_SCHEMA)}
    names |= {
        con["name"] for con in inspector.get_unique_constraints(table, schema=_SCHEMA)
    }
    return name in names


def upgrade() -> None:
    if not _has_table(_DECISIONS):
        op.create_table(
            _DECISIONS,
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("company_id", UUID(as_uuid=False), nullable=True),
            sa.Column("project_sales_order_id", UUID(as_uuid=False), nullable=False),
            sa.Column("revision_no", sa.Integer(), nullable=False),
            sa.Column(
                "state", sa.String(length=16), nullable=False, server_default="active"
            ),
            sa.Column("source_revision", sa.String(length=120), nullable=True),
            sa.Column("line_snapshots", JSONB(), nullable=False),
            sa.Column("confirmed_by", sa.String(length=100), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("supersedes_id", UUID(as_uuid=False), nullable=True),
            sa.Column("superseded_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("superseded_reason", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["project_sales_order_id"],
                ["projects.sales_orders.id"],
                name="fk_so_supply_decisions_order",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["confirmed_by"],
                ["users.id"],
                name="fk_so_supply_decisions_confirmed_by",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["supersedes_id"],
                [f"{_SCHEMA}.{_DECISIONS}.id"],
                name="fk_so_supply_decisions_supersedes",
                ondelete="SET NULL",
            ),
            sa.UniqueConstraint(
                "project_sales_order_id",
                "revision_no",
                name="uq_so_supply_decisions_revision",
            ),
            schema=_SCHEMA,
        )

    if not _has_index(_DECISIONS, "ix_so_supply_decisions_order"):
        op.create_index(
            "ix_so_supply_decisions_order",
            _DECISIONS,
            ["project_sales_order_id"],
            schema=_SCHEMA,
        )
    if not _has_index(_DECISIONS, "uq_so_supply_decisions_active"):
        # The DB-level singleton. One active revision per Project SO, so a concurrent
        # second confirmation loses on the index rather than committing beside the first.
        op.create_index(
            "uq_so_supply_decisions_active",
            _DECISIONS,
            ["project_sales_order_id"],
            unique=True,
            schema=_SCHEMA,
            postgresql_where=sa.text("state = 'active'"),
        )

    if not _has_column(_ALLOCATIONS, "decision_id"):
        op.add_column(
            _ALLOCATIONS,
            sa.Column("decision_id", UUID(as_uuid=False), nullable=True),
            schema=_SCHEMA,
        )
        op.create_foreign_key(
            "fk_so_line_allocations_decision",
            _ALLOCATIONS,
            _DECISIONS,
            ["decision_id"],
            ["id"],
            source_schema=_SCHEMA,
            referent_schema=_SCHEMA,
            ondelete="SET NULL",
        )
    if not _has_index(_ALLOCATIONS, "ix_so_line_allocations_decision"):
        op.create_index(
            "ix_so_line_allocations_decision",
            _ALLOCATIONS,
            ["decision_id"],
            schema=_SCHEMA,
        )
    if not _has_column(_ALLOCATIONS, "reason"):
        op.add_column(
            _ALLOCATIONS, sa.Column("reason", sa.Text(), nullable=True), schema=_SCHEMA
        )
    if not _has_column(_ALLOCATIONS, "donor_impact_snapshot"):
        op.add_column(
            _ALLOCATIONS,
            sa.Column("donor_impact_snapshot", JSONB(), nullable=True),
            schema=_SCHEMA,
        )

    if not _has_column(_INQUIRY_ROWS, "supply_decision_id"):
        op.add_column(
            _INQUIRY_ROWS,
            sa.Column("supply_decision_id", UUID(as_uuid=False), nullable=True),
            schema=_SCHEMA,
        )
        op.create_foreign_key(
            "fk_order_inquiry_rows_supply_decision",
            _INQUIRY_ROWS,
            _DECISIONS,
            ["supply_decision_id"],
            ["id"],
            source_schema=_SCHEMA,
            referent_schema=_SCHEMA,
            ondelete="SET NULL",
        )
    if not _has_index(_INQUIRY_ROWS, "ix_project_order_inquiry_rows_decision"):
        op.create_index(
            "ix_project_order_inquiry_rows_decision",
            _INQUIRY_ROWS,
            ["supply_decision_id"],
            schema=_SCHEMA,
        )

    op.execute(_AS_OF_374)


def downgrade() -> None:
    """Drop only what upgrade created, checked the same way it checked before creating."""
    op.execute(_AS_OF_346)

    if _has_index(_INQUIRY_ROWS, "ix_project_order_inquiry_rows_decision"):
        op.drop_index(
            "ix_project_order_inquiry_rows_decision", _INQUIRY_ROWS, schema=_SCHEMA
        )
    if _has_column(_INQUIRY_ROWS, "supply_decision_id"):
        op.drop_column(_INQUIRY_ROWS, "supply_decision_id", schema=_SCHEMA)

    if _has_index(_ALLOCATIONS, "ix_so_line_allocations_decision"):
        op.drop_index("ix_so_line_allocations_decision", _ALLOCATIONS, schema=_SCHEMA)
    for column in ("donor_impact_snapshot", "reason", "decision_id"):
        if _has_column(_ALLOCATIONS, column):
            op.drop_column(_ALLOCATIONS, column, schema=_SCHEMA)

    if _has_table(_DECISIONS):
        op.drop_table(_DECISIONS, schema=_SCHEMA)
