"""Adopting an AutoCount sales order into fulfilment planning (plan section 4).

Contract: `documentation/plans/scm/PLAN-fulfilment-planning-from-autocount-so.md` section
4. Two DDL changes and a status value, and NO new table - everything this slice adds lives
in `projects.*`, which is module-owned and purgeable, and `public.sales_orders` /
`public.sales_order_lines` gain no column, index or constraint (AC-FP23, finding G5).

1. `projects.sales_orders.project_id` becomes NULLABLE. An adopted order has no project
   registration and must not invent one: auto-creating a registration per adopted order
   would pollute the pipeline and collide with ADR-0004 registration exclusivity, and
   asking CS to pick one would add a decision per order for a fact the AutoCount document
   does not carry. The FK and its `ON DELETE RESTRICT` are untouched.
2. A partial unique index `uq_projects_so_core_order` on `(so_id) WHERE so_id IS NOT NULL`.
   One core sales order is planned exactly once, which is what makes a doubly-counted
   confirmed leg in `scm.committed_v` impossible rather than merely unlikely (AC-FP10,
   section 8 invariant 4). Created non-concurrently and allowed to fail loudly on a
   duplicate rather than silently deduping: two planning records for one core order is a
   fact somebody has to see, not one a migration should quietly resolve.
3. The `adopted` status value is a MODEL constant (`SO_STATUS_ADOPTED`), not DDL: the
   column is `String(24)` with no database enum, so there is nothing here to alter.

**Chaining, and what a real landing must do differently.** This revision chains onto
`382_merge_loading_plan_stack`, which exists only on the disposable e2e stack branch
`fm/scm-e2e-integration-stack`, because that is the single head this stack has and the
captain runs the migration against the scratch database from it. On a landing to `main`
this revision's `down_revision` is re-pointed at main's own single head, re-checked with
`alembic heads` immediately before merge, and it gains
`depends_on = ("374_so_supply_decisions",)` so it can never run before Stage 1C's
`projects.so_supply_decisions` exists. Never re-parent or renumber an existing revision to
achieve that; only this one moves.

**Backfill: deliberately none.** No column was added to any existing row, and adoption is
lazy by design (plan section 2): the 605 outstanding project-class core orders become
worklist rows without a row being written for them, and each gains its planning record
only when CS presses Start planning. Stated here so a reviewer does not have to guess
whether gate 2 was missed.

**Downgrade refuses rather than deletes.** Restoring `NOT NULL` on `project_id` fails
loudly while any adopted record exists, because the alternative - deleting somebody's
planning records to make a schema change fit - is worse than a failed downgrade. Detach
every adopted order first.

Revision ID: 383_adopted_autocount_planning
Revises: 382_merge_loading_plan_stack
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "383_adopted_autocount_planning"
down_revision = "382_merge_loading_plan_stack"
branch_labels = None
depends_on = None

_SCHEMA = "projects"
_TABLE = "sales_orders"
_INDEX = "uq_projects_so_core_order"


def _column(bind, name: str):
    for column in sa.inspect(bind).get_columns(_TABLE, schema=_SCHEMA):
        if column["name"] == name:
            return column
    return None


def _has_index(bind) -> bool:
    return any(
        index["name"] == _INDEX
        for index in sa.inspect(bind).get_indexes(_TABLE, schema=_SCHEMA)
    )


def upgrade() -> None:
    bind = op.get_bind()

    project_id = _column(bind, "project_id")
    if project_id is not None and not project_id["nullable"]:
        op.alter_column(
            _TABLE,
            "project_id",
            existing_type=UUID(as_uuid=False),
            nullable=True,
            schema=_SCHEMA,
        )

    if not _has_index(bind):
        op.create_index(
            _INDEX,
            _TABLE,
            ["so_id"],
            unique=True,
            schema=_SCHEMA,
            postgresql_where=sa.text("so_id IS NOT NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _has_index(bind):
        op.drop_index(_INDEX, table_name=_TABLE, schema=_SCHEMA)

    project_id = _column(bind, "project_id")
    if project_id is not None and project_id["nullable"]:
        # Loud on purpose: an adopted record has no project by design, so this ALTER
        # fails while one exists. Detaching them is the operator's decision, not this
        # migration's.
        op.alter_column(
            _TABLE,
            "project_id",
            existing_type=UUID(as_uuid=False),
            nullable=False,
            schema=_SCHEMA,
        )
