"""scm.reorder_recommendation gains hidden_by_default (S3, PLAN-reorder-one-formula.md).

The ONE scope rule (`app.services.scm.plan_scope.hidden_by_default`) used to live only in
Python, re-derived independently by the recommendations serializer, the Decisions tile
count and `list_plan_row_decisions`'s total - three re-derivations that drifted apart per
the owner's 10 Sep measurement (list 415, tile "0 of 950", sheet 950). This column is
stamped ONCE, at run-write time (`reorder_run_service._build_rec`), and every SQL reader
reads it instead of recomputing the rule.

The backfill below is a ONE-OFF SQL twin of the Python rule, for rows a run wrote before
this column existed. The Python rule stays the only RUNTIME source of truth; this SQL
never runs again after this migration.

Revision ID: 512_hidden_by_default_col
Revises: 510_pi_description_en
Create Date: 2026-09-11
"""
import sqlalchemy as sa
from alembic import op

revision = "512_hidden_by_default_col"
down_revision = "510_pi_description_en"
branch_labels = None
depends_on = None

_SCHEMA = "scm"
_TABLE = "reorder_recommendation"
_COLUMN = "hidden_by_default"


def _has_column() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE, schema=_SCHEMA):
        return False
    return _COLUMN in {col["name"] for col in inspector.get_columns(_TABLE, schema=_SCHEMA)}


def _backfill_run_counts() -> None:
    """One-off recompute of `scm.reorder_run.planned_count` and `run_log.recommendation_count`
    against the `hidden_by_default` column just backfilled above (AC-14 gap, PLAN-reorder-
    one-formula.md, coder round 3): the column landed on the recs, but the two stored
    per-run counters that read it (`reorder_run_service`'s write-time stamp, `_summarise`)
    were never recomputed for a run that already existed, so every plan written before this
    migration kept its unscoped numbers - on prod that includes the owner's own 11 Sep 07:30
    run, which still reads 826.

    Same shape `decision_service._refresh_run_counts`'s SQL and `_summarise` use
    (`FILTER (WHERE NOT hidden_by_default)`, DISTINCT product for `planned_count`, row count
    for `recommendation_count`), just run once for every existing run instead of one at a
    time. `FILTER` (not a `WHERE` ahead of the `GROUP BY`) so a run whose recs are ALL
    hidden still gets an UPDATE row and lands on 0, not skipped and left at its old count.
    `decided_count` / `confirmed_count` are untouched - they are not scoped by this column.
    Idempotent: recomputes to the same numbers every run, never increments anything.
    """
    op.execute(sa.text(
        f"""
        UPDATE scm.reorder_run rr
        SET planned_count = sub.planned
        FROM (
            SELECT run_id,
                   count(DISTINCT product_id) FILTER (WHERE NOT {_COLUMN}) AS planned
            FROM {_SCHEMA}.{_TABLE}
            GROUP BY run_id
        ) sub
        WHERE rr.id = sub.run_id
        """
    ))
    op.execute(sa.text(
        f"""
        UPDATE scm.reorder_run rr
        SET run_log = jsonb_set(rr.run_log, '{{recommendation_count}}', to_jsonb(sub.cnt))
        FROM (
            SELECT run_id, count(*) FILTER (WHERE NOT {_COLUMN}) AS cnt
            FROM {_SCHEMA}.{_TABLE}
            GROUP BY run_id
        ) sub
        WHERE rr.id = sub.run_id
          AND rr.run_log IS NOT NULL
          AND rr.run_log ? 'recommendation_count'
        """
    ))


def upgrade() -> None:
    if not _has_column():
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.text("false")),
            schema=_SCHEMA,
        )

    # The SQL twin of `plan_scope.hidden_by_default`: covered, on the manual reorder_level
    # basis, a basis value exists (the row's own level, else the product's master level),
    # net_position is known, and net_position clears it.
    op.execute(sa.text(
        f"""
        UPDATE {_SCHEMA}.{_TABLE}
        SET {_COLUMN} = true
        WHERE rec_type = 'covered'
          AND (inputs ->> 'policy_type') = 'reorder_level'
          AND COALESCE(
                (inputs ->> 'reorder_level')::numeric,
                (inputs ->> 'master_reorder_level')::numeric
              ) IS NOT NULL
          AND net_position IS NOT NULL
          AND net_position > COALESCE(
                (inputs ->> 'reorder_level')::numeric,
                (inputs ->> 'master_reorder_level')::numeric
              )
        """
    ))

    _backfill_run_counts()


def downgrade() -> None:
    if _has_column():
        op.drop_column(_TABLE, _COLUMN, schema=_SCHEMA)
