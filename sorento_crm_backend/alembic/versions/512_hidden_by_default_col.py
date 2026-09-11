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


def downgrade() -> None:
    if _has_column():
        op.drop_column(_TABLE, _COLUMN, schema=_SCHEMA)
