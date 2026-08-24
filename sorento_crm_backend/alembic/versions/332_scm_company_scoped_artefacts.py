"""SCM: a plan belongs to a company.

Planning in Sorento must be based on Sorento's warehouses, products and orders, and Mocha may
own warehouses too. The isolation filter runs on ORM execution only, and no `scm.*` table
carried a `company_id` at all, so a run enumerated every company's positions. It was inert only
because Mocha owned 0 warehouses - a property of the data, not of the code.

Company is a property of the LOCATION, and most SCM rows name one, so those are filtered through
the joined `warehouses` rather than carrying a copy of the fact (a second copy is free to
disagree with the first). This migration stamps the rows that are NOT facts about a location:

  * `reorder_run`           - a company's plan. Also the only way the RQ worker can recover a
                                scope: the work-horse receives a run id and nothing else, and an
                                UNSET scope FAILS CLOSED, so a worker relying on ambient scope
                                would silently produce zero recommendations.
  * `reorder_recommendation` - `warehouse_id` is NULL on a network-scope run, so the company
                                cannot be derived at all.
  * `order_summary_row`     - one row per product NETWORK wide; no location to derive from.
  * `recommendation_override` - a person's decision, not a position.
  * `purchasing_budget`     - a company's cash.
  * `scm_analytics_run`, `market_research_run` - runs, same argument as `reorder_run`.

Deliberately NOT stamped, and each for a reason:

  * `demand_stat`, `item_classification` and the five views are keyed by warehouse and/or
    product and derive their company from the join.
  * `supplier_performance` derives from `suppliers.company_id`, which already exists.
  * `market_research_topic` / `market_signal` are facts about the world. A tile price trend in
    Guangdong is not owned by a company.
  * The policy tables are a separate slice (shared-with-override, nullable column).

Every existing row is backfilled to Sorento, which is correct rather than convenient: every
warehouse in the database today belongs to Sorento, so every position, run and recommendation
derived from one is Sorento's.

Nullable, not NOT NULL. A row written with no active scope would otherwise fail the insert
outright, and there are paths (a cron tick, a script) where that is a real possibility; the
read-side predicate treats NULL as "belongs to no company" and hides it, which is the safe
direction. Tightening to NOT NULL is a later migration once the write paths are proven.

Revision ID: 332_scm_company_scoped_artefacts
Revises: 331_scm_order_summary_keyed_status
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "332_scm_company_scoped_artefacts"
down_revision = "331_scm_order_summary_keyed_status"
branch_labels = None
depends_on = None

# The fixed Sorento company row (mirrors migration 302 / `_seed_default_company`).
_SORENTO = "00000000-0000-0000-0000-000000000001"

_TABLES = (
    "reorder_run",
    "reorder_recommendation",
    "order_summary_row",
    "recommendation_override",
    "purchasing_budget",
    "scm_analytics_run",
    "market_research_run",
)


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table, schema="scm")


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table, schema="scm")}


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        if not _has_table(bind, table):
            continue
        if "company_id" in _columns(bind, table):
            continue
        op.add_column(
            table,
            sa.Column(
                "company_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("companies.id", ondelete="RESTRICT"),
                nullable=True,
            ),
            schema="scm",
        )
        # RESTRICT rather than CASCADE: deleting a company must not silently delete its
        # planning history, which is what a past decision is reviewed against.
        op.create_index(
            f"ix_scm_{table}_company_id", table, ["company_id"], schema="scm"
        )
        # Backfill. Only where the company row actually exists, so a database that has not
        # run the company seed is left alone rather than failing on the FK.
        op.execute(
            sa.text(
                f"""
                UPDATE scm.{table}
                   SET company_id = :co
                 WHERE company_id IS NULL
                   AND EXISTS (SELECT 1 FROM companies WHERE id = :co)
                """
            ).bindparams(co=_SORENTO)
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        if not _has_table(bind, table):
            continue
        if "company_id" not in _columns(bind, table):
            continue
        op.drop_index(f"ix_scm_{table}_company_id", table_name=table, schema="scm")
        op.drop_column(table, "company_id", schema="scm")
