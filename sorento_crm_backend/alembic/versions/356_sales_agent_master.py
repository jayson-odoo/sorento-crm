"""The salesperson master gains the columns the SCM order import needs, and orders link to it.

`sales_agents` is a table with two lives. It was created by the AutoCount ingest branch
(migration `303_autocount_slice2_masters`, unmerged) as a read-only mirror of AutoCount's
SalesAgent, and it exists on the shared dev database for that reason with no definition in
main at all. This revision does NOT take it over: the five original columns are reproduced
byte-identically, so whichever chain reaches a database first, both describe one table.

What it adds is four annotation columns - exactly the kind the mirror's re-sync contract
already promises to leave alone:

* `person_label` groups `SEAN I` / `SEAN III` / `SEAN IV` under one human for reporting. The
  captain's file carries 38 codes decomposing to 16 people. Metadata, never identity:
  merging the codes would merge three books of demand that can legitimately differ.
* `demand_class` is what the fulfilment policy weighs when a document says nothing else
  (UAC AC-3). It ships NULL on every row and stays NULL until the captain fills it in: the
  I/III/IV suffix maps to neither company nor market segment anywhere in this database, so
  its meaning is not derivable and guessing it would silently mis-prioritise real orders.
* `company_id` NULL means a SHARED master row, visible to every company. The captain's own
  files show the same agents selling for both, so partitioning the master would duplicate
  each agent and split one person's demand class in two. This is the `container_size` shape
  (a NULL row is everyone's), and it is why `SalesAgent` is deliberately not a
  `CompanyScopedMixin` - the mixin's auto-filter would hide every NULL-company row, which
  here is the entire master.

Adding that column is not enough on its own to make it MEAN anything, which is why the
AutoCount original's plain unique on `sales_agent` is REPLACED here by a unique index on
`(coalesce(company_id, nil-uuid), sales_agent)`. With the plain unique in place a tenant
could never hold its own `SEAN III` beside the shared one, so the documented future - the
`company_id IS NULL OR company_id = <scope>` read in `sales_agent_service` - was
unimplementable without a migration first. It is expressible now: a tenant row and a shared
row with the same code can coexist, and two shared rows with the same code still cannot,
because NULL coalesces to the nil uuid rather than being treated as distinct. Same shape and
same reason as `scm.container_size` (migration 336) and `scm.reorder_level` (344).
* `source` separates a row an admin (or the AutoCount mirror) made from one an upload
  invented on meeting an unknown code. Without it the Test result cannot honestly say "new
  agent, unclassified" (AC-6.4) and the import would be inventing master data nobody knows
  to look at.

No agent codes are seeded. They arrive through the import, which is the only place that
knows them.

`sales_orders.sales_agent_id` is the other half: the order records who sold it, nullable
because no export is obliged to carry an agent and every existing row predates the column.
`ON DELETE SET NULL` - removing a salesperson must not remove their orders.

Idempotent in both directions (create-if-absent, add-column-if-absent, replace-the-unique-
if-it-is-still-the-plain-one), because this table may already exist from the other branch,
and because a create_all database (CI) builds it from the model and then stamps alembic
without ever running this body. The three shapes this has to land on:

* an AutoCount-shaped table that already holds rows: columns are added, and the plain
  `uq_sales_agents_sales_agent` constraint is dropped and replaced by the scoped index;
* a database that has never seen the table: it is created here, with the scoped index and
  no plain unique at all;
* a create_all database (CI): the model carries the same index in `__table_args__`, so the
  shape is already right and this body never runs.

Revision ID: 356_sales_agent_master
Revises: 885010d94677
"""
import sqlalchemy as sa
from alembic import op

from app.services.scm.demand_class import check_constraint_sql

revision = "356_sales_agent_master"
down_revision = "885010d94677"
branch_labels = None
depends_on = None

_UUID = sa.dialects.postgresql.UUID
_TS = dict(server_default=sa.func.now(), nullable=False)

_CHECK_NAME = "ck_sales_agents_demand_class"

#: The AutoCount original's global unique, and this revision's company-scoped replacement.
_PLAIN_UNIQUE = "uq_sales_agents_sales_agent"
_SCOPED_UNIQUE = "uq_sales_agents_company_sales_agent"

#: NULL company means "shared", and Postgres treats NULLs as distinct - so without the
#: coalesce two shared rows could hold the same code, which is the duplicate the unique
#: exists to stop. Same constant as `app/models/scm.py` and `app/models/sales_agent.py`.
_NIL_COMPANY = "00000000-0000-0000-0000-000000000000"

#: The four added columns, in the order the model declares them.
_ADDED = (
    lambda: sa.Column("person_label", sa.String(100), nullable=True),
    lambda: sa.Column("demand_class", sa.String(32), nullable=True),
    lambda: sa.Column("company_id", _UUID(as_uuid=False),
                      sa.ForeignKey("companies.id"), nullable=True),
    # server_default rather than a backfill UPDATE: every row that predates this column was
    # put there by hand or by the mirror, which is exactly what `manual` means, so the
    # default IS the correct historical value.
    lambda: sa.Column("source", sa.String(20), nullable=False,
                      server_default=sa.text("'manual'")),
)


def _columns(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def _scoped_unique() -> None:
    """Create the company-scoped unique index, if this database has not got it yet."""
    if not any(i["name"] == _SCOPED_UNIQUE
               for i in sa.inspect(op.get_bind()).get_indexes("sales_agents")):
        op.create_index(
            _SCOPED_UNIQUE,
            "sales_agents",
            [sa.text(f"coalesce(company_id, '{_NIL_COMPANY}'::uuid)"), "sales_agent"],
            unique=True,
        )


def _drop_plain_unique() -> None:
    """Remove whatever global unique on `sales_agent` alone this database happens to carry.

    By SHAPE, not by name. The AutoCount branch created it as the named constraint
    `uq_sales_agents_sales_agent`; a create_all database built from the model before this
    revision got Postgres's own `sales_agents_sales_agent_key` from `unique=True`. Both mean
    the same wrong thing - one code, ever, across every company - and dropping only the one we
    happened to name would leave the other silently enforcing it while the scoped index sat
    beside it looking correct. Absent on a re-run, which is what makes this idempotent.
    """
    insp = sa.inspect(op.get_bind())
    for uq in insp.get_unique_constraints("sales_agents"):
        if list(uq.get("column_names") or []) == ["sales_agent"]:
            op.drop_constraint(uq["name"], "sales_agents", type_="unique")
    for ix in sa.inspect(op.get_bind()).get_indexes("sales_agents"):
        if ix.get("unique") and list(ix.get("column_names") or []) == ["sales_agent"]:
            op.drop_index(ix["name"], table_name="sales_agents")


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "sales_agents" not in tables:
        # The five original columns are copied verbatim from the AutoCount branch's
        # `303_autocount_slice2_masters`. Do not "improve" them here: a difference is a
        # database where the two branches disagree about one table.
        op.create_table(
            "sales_agents",
            sa.Column("id", _UUID(as_uuid=False), primary_key=True),
            sa.Column("sales_agent", sa.String(100), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("internal_note", sa.Text(), nullable=True),
            sa.Column("follow_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            *[factory() for factory in _ADDED],
            sa.Column("created_at", sa.DateTime(timezone=False), **_TS),
            sa.Column("updated_at", sa.DateTime(timezone=False), **_TS),
        )
        # NO plain unique on the fresh table: it is created in the shape this revision
        # settles on, not created wrong and then corrected.
        _scoped_unique()
    else:
        present = _columns(insp, "sales_agents")
        for factory in _ADDED:
            column = factory()
            if column.name not in present:
                op.add_column("sales_agents", column)
        # Only now can the unique be scoped: the column it scopes to has just arrived. Drop
        # first, then create - the replacement is not additive, and leaving the global one in
        # place would make `company_id` a column that exists and changes nothing.
        _drop_plain_unique()
        _scoped_unique()

    # The closed vocabulary, added separately so it lands on a pre-existing table too. Built
    # from `demand_class.DEMAND_CLASSES` so the constraint and the model's own
    # `CheckConstraint` cannot drift into disagreeing about which words are allowed.
    if not any(c["name"] == _CHECK_NAME
               for c in sa.inspect(conn).get_check_constraints("sales_agents")):
        op.create_check_constraint(_CHECK_NAME, "sales_agents", check_constraint_sql())

    if "sales_agent_id" not in _columns(sa.inspect(conn), "sales_orders"):
        op.add_column(
            "sales_orders",
            sa.Column("sales_agent_id", _UUID(as_uuid=False), nullable=True),
        )
        op.create_foreign_key(
            "fk_sales_orders_sales_agent_id", "sales_orders", "sales_agents",
            ["sales_agent_id"], ["id"], ondelete="SET NULL",
        )
        op.create_index(
            "ix_sales_orders_sales_agent_id", "sales_orders", ["sales_agent_id"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if "sales_agent_id" in _columns(insp, "sales_orders"):
        op.drop_index("ix_sales_orders_sales_agent_id", table_name="sales_orders")
        op.drop_constraint("fk_sales_orders_sales_agent_id", "sales_orders",
                           type_="foreignkey")
        op.drop_column("sales_orders", "sales_agent_id")

    # The table itself is NOT dropped: it predates this revision on the databases that have
    # it, and dropping it here would delete the other branch's mirror.
    if any(c["name"] == _CHECK_NAME
           for c in insp.get_check_constraints("sales_agents")):
        op.drop_constraint(_CHECK_NAME, "sales_agents", type_="check")

    # The scoped index has to go before `company_id` does, and the AutoCount original's global
    # unique has to come back, or a downgraded database would hold NO uniqueness on the agent
    # code at all and the next upload would start duplicating the master. Loud by design if
    # two companies already hold the same code: that data cannot exist under the old shape,
    # and silently dropping one of the rows to make the constraint fit would lose a
    # classification the client entered.
    if any(i["name"] == _SCOPED_UNIQUE for i in insp.get_indexes("sales_agents")):
        op.drop_index(_SCOPED_UNIQUE, table_name="sales_agents")
    if not any(list(uq.get("column_names") or []) == ["sales_agent"]
               for uq in insp.get_unique_constraints("sales_agents")):
        op.create_unique_constraint(_PLAIN_UNIQUE, "sales_agents", ["sales_agent"])

    present = _columns(insp, "sales_agents")
    for factory in reversed(_ADDED):
        name = factory().name
        if name in present:
            op.drop_column("sales_agents", name)
