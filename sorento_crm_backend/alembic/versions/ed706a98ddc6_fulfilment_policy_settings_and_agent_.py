"""Fulfilment policy settings (horizon, cross-group borrow caps) and the agent's ownership
group.

PLAN-demo-followups-19aug-ladder-v2.md workstream C. Two independent additions, one
migration because both feed the same ladder v2 (E) and both are config the planner sets in
one sitting on Supply Chain -> Policies / Master Data -> Sales Agents:

  * ``scm.priority_policy`` gains three settings the ladder (E) will read but this slice does
    NOT wire into scoring: ``buy_all_horizon_days`` (a line due further out than this is
    ``Buy all`` untouched), ``cross_group_borrow_max_qty`` / ``cross_group_borrow_max_pct``
    (a cross-ownership-group borrow is only offered under a small-quantity cap). Columns, not
    another JSONB key, because these are scalars every row has - unlike ``factors``, there is
    no third one coming. Backfilled onto every existing row (there is exactly one active row
    plus history - migration 385), never left NULL for an old row to silently read as "no
    horizon at all".

  * ``sales_agents.location_group`` names which warehouse-suffix group (``BB``, ``HP``, ...)
    an agent's stock lives in, per the captain's ruling that "BRW-BB, MWH-BB, DC1-BB are one
    BB, owned by the BB salespersons". Seeded ``BB`` for the nine names the captain gave,
    matched on ``upper(trim(sales_agent))`` the same way ``sales_agent_service`` normalises a
    document code, so a row already spelled ``sean i``-style still matches. A code the
    captain did not name is left NULL - guessing an ownership group is exactly the mistake
    ``demand_class`` shipped NULL to avoid.

Idempotent: ``add column if not exists`` shape throughout, and the seed is a
``WHERE location_group IS NULL`` UPDATE keyed by the normalised code, so a re-run (or a row
the captain has since edited by hand) is left alone.

Revision ID: ed706a98ddc6
Revises: f3a8c6d9e1b2
"""
from alembic import op
import sqlalchemy as sa

revision = 'ed706a98ddc6'
down_revision = 'f3a8c6d9e1b2'
branch_labels = None
depends_on = None

#: Defaults mirrored in `app/services/scm/priority.py` (`FULFILMENT_SETTINGS_DEFAULTS`) -
#: literals repeated here so the migration stays standalone, same rule as 385.
_BUY_ALL_HORIZON_DAYS = 180
_CROSS_GROUP_BORROW_MAX_QTY = 50
_CROSS_GROUP_BORROW_MAX_PCT = 10

#: The nine names the captain gave for the BB ownership group (PLAN section "captain's ask"
#: item 8), matched case/whitespace-insensitively the way `sales_agent_service.normalize_code`
#: matches a document code.
_BB_AGENT_CODES = (
    "TERA",
    "JEREMY",
    "CINDY LEE",
    "JAY",
    "BRENDON",
    "ERIC NG",
    "JENNIFER",
    "JOHNSON",
    "CASSANDRA",
)


def _columns(insp, table: str, schema: str | None = None) -> set[str]:
    return {c["name"] for c in insp.get_columns(table, schema=schema)}


def _has_table(bind, table: str, schema: str | None = None) -> bool:
    return sa.inspect(bind).has_table(table, schema=schema)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # --- scm.priority_policy: horizon + cross-group borrow caps -----------------
    if _has_table(bind, "priority_policy", schema="scm"):
        present = _columns(insp, "priority_policy", schema="scm")
        if "buy_all_horizon_days" not in present:
            op.add_column(
                "priority_policy",
                sa.Column(
                    "buy_all_horizon_days", sa.Integer(), nullable=False,
                    server_default=sa.text(str(_BUY_ALL_HORIZON_DAYS)),
                ),
                schema="scm",
            )
        if "cross_group_borrow_max_qty" not in present:
            op.add_column(
                "priority_policy",
                sa.Column(
                    "cross_group_borrow_max_qty", sa.Integer(), nullable=False,
                    server_default=sa.text(str(_CROSS_GROUP_BORROW_MAX_QTY)),
                ),
                schema="scm",
            )
        if "cross_group_borrow_max_pct" not in present:
            op.add_column(
                "priority_policy",
                sa.Column(
                    "cross_group_borrow_max_pct", sa.Numeric(6, 2), nullable=False,
                    server_default=sa.text(str(_CROSS_GROUP_BORROW_MAX_PCT)),
                ),
                schema="scm",
            )
        # Backfill belt-and-braces: `server_default` only reaches NEW rows on some drivers'
        # ADD COLUMN paths, and a row inserted by raw SQL between the add and now would read
        # NULL forever without this.
        bind.execute(
            sa.text(
                "UPDATE scm.priority_policy SET buy_all_horizon_days = :h "
                "WHERE buy_all_horizon_days IS NULL"
            ),
            {"h": _BUY_ALL_HORIZON_DAYS},
        )
        bind.execute(
            sa.text(
                "UPDATE scm.priority_policy SET cross_group_borrow_max_qty = :q "
                "WHERE cross_group_borrow_max_qty IS NULL"
            ),
            {"q": _CROSS_GROUP_BORROW_MAX_QTY},
        )
        bind.execute(
            sa.text(
                "UPDATE scm.priority_policy SET cross_group_borrow_max_pct = :p "
                "WHERE cross_group_borrow_max_pct IS NULL"
            ),
            {"p": _CROSS_GROUP_BORROW_MAX_PCT},
        )

    # --- sales_agents.location_group: the BB/HP/... ownership group -------------
    if _has_table(bind, "sales_agents"):
        present = _columns(insp, "sales_agents")
        if "location_group" not in present:
            op.add_column(
                "sales_agents",
                sa.Column("location_group", sa.String(16), nullable=True),
            )
        bind.execute(
            sa.text(
                "UPDATE sales_agents SET location_group = 'BB' "
                "WHERE location_group IS NULL "
                "AND upper(btrim(sales_agent)) = ANY(:codes)"
            ),
            {"codes": list(_BB_AGENT_CODES)},
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if _has_table(bind, "sales_agents"):
        if "location_group" in _columns(insp, "sales_agents"):
            op.drop_column("sales_agents", "location_group")

    if _has_table(bind, "priority_policy", schema="scm"):
        present = _columns(insp, "priority_policy", schema="scm")
        for name in (
            "cross_group_borrow_max_pct",
            "cross_group_borrow_max_qty",
            "buy_all_horizon_days",
        ):
            if name in present:
                op.drop_column("priority_policy", name, schema="scm")
