"""Every planned row counts: recompute the stored per-run counters and drop
`scm.reorder_recommendation.hidden_by_default` (PLAN-lowstock-show-all.md).

Owner ruling 30 Sep 2026 ("SHOW ALL HIDDEN ITEMS AGAIN") reverses the rule migration 512
stamped into this column (covered + manual reorder level + net above level => off the
buyer's list by default). The code no longer stamps or reads it, so two things remain to
be done in data:

1. `scm.reorder_run.planned_count` and `run_log.recommendation_count` were recomputed by
   512's own backfill WITH the hidden filter, and every run written 10-30 Sep stamped them
   the same way at generation. Nothing recomputes them on an existing run except a
   decision (`decision_service._refresh_run_counts`, `planned_count` only), so the plans
   list's Lines / Products columns would keep the narrowed figures on every older run
   (980 instead of 1,393 on run dd28049a). This recomputes both, once, for every run - the
   same two populations `_summarise` (every rec of the run) and `_refresh_run_counts`
   (DISTINCT product over the decidable rec types) count today, with no filter.
2. The column itself goes. A column nothing writes or reads is the kind of thing that gets
   read again by accident (it still held `true` on 413 rows of one run).

Order matters only for readability: the recount never reads the column. Idempotent: the
recount lands on the same numbers every time and the drop is guarded.

Revision ID: lsa_0001_show_all_counts
Revises: sat_0001_stock_ask_done
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op

revision = "lsa_0001_show_all_counts"
down_revision = "sat_0001_stock_ask_done"
branch_labels = None
depends_on = None

_SCHEMA = "scm"
_TABLE = "reorder_recommendation"
_COLUMN = "hidden_by_default"

#: The rec types `planned_count` counts. MUST stay the same set as
#: `decision_service._PLAN_ROW_DECIDABLE_TYPES` (spelled here, as 512 did, so the migration
#: cannot start failing the day the service module moves).
_DECIDABLE_TYPES = ("buy", "covered", "needs_level", "disposition")


def _has_column() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE, schema=_SCHEMA):
        return False
    return _COLUMN in {col["name"] for col in inspector.get_columns(_TABLE, schema=_SCHEMA)}


def _recount_runs() -> None:
    """`planned_count` = DISTINCT products over the decidable rec types; `run_log.
    recommendation_count` = every rec of the run. `FILTER` on the kinds (not a `WHERE`) so
    a run whose recs are all exceptions still gets an UPDATE row and lands on 0. Runs whose
    `run_log` never carried `recommendation_count` (a failed run) are left alone, as 512
    left them. `decided_count` / `confirmed_count` are untouched."""
    op.execute(sa.text(
        f"""
        UPDATE scm.reorder_run rr
        SET planned_count = sub.planned
        FROM (
            SELECT run_id,
                   count(DISTINCT product_id) FILTER (WHERE rec_type = ANY(:kinds)) AS planned
            FROM {_SCHEMA}.{_TABLE}
            GROUP BY run_id
        ) sub
        WHERE rr.id = sub.run_id
        """
    ).bindparams(kinds=list(_DECIDABLE_TYPES)))
    op.execute(sa.text(
        f"""
        UPDATE scm.reorder_run rr
        SET run_log = jsonb_set(rr.run_log, '{{recommendation_count}}', to_jsonb(sub.cnt))
        FROM (
            SELECT run_id, count(*) AS cnt
            FROM {_SCHEMA}.{_TABLE}
            GROUP BY run_id
        ) sub
        WHERE rr.id = sub.run_id
          AND rr.run_log IS NOT NULL
          AND rr.run_log ? 'recommendation_count'
        """
    ))


def upgrade() -> None:
    _recount_runs()
    if _has_column():
        op.drop_column(_TABLE, _COLUMN, schema=_SCHEMA)


def downgrade() -> None:
    # The column comes back empty (every row false). Re-deriving 512's stamps and its
    # narrowed counters is that migration's business, not this one's: a downgrade here
    # restores the SHAPE the pre-lane code expects, and that code stamps new runs itself.
    if not _has_column():
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.text("false")),
            schema=_SCHEMA,
        )
