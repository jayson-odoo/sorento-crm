"""scm.loading_plan gains plan_horizon_start (AC-N7, PLAN-scm-loading-plan-lines-feedback-12sep.md)

Revision ID: 513_loading_plan_horizon_start
Revises: 512_integration_ref_company
Create Date: 2026-09-12

The loading plan's "Sales order cut-off" becomes a window, the same From/To shape and the
same reading `scm.reorder_run.plan_horizon_start` (migration 499) already gives the reorder
engine. NULL (every existing row) plans every open SO line regardless of when it was needed,
unchanged from before this column existed.
"""
import sqlalchemy as sa
from alembic import op

revision = "513_loading_plan_horizon_start"
down_revision = "512_integration_ref_company"
branch_labels = None
depends_on = None

_SCHEMA = "scm"
_TABLE = "loading_plan"
_COLUMN = "plan_horizon_start"


def _has_column() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE, schema=_SCHEMA):
        return False
    return _COLUMN in {col["name"] for col in inspector.get_columns(_TABLE, schema=_SCHEMA)}


def upgrade() -> None:
    # Idempotent: the shared local database converges through `create_all`, so the model's
    # column can already be there before this body ever runs (see the backend CLAUDE.md).
    if not _has_column():
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Date(), nullable=True), schema=_SCHEMA)


def downgrade() -> None:
    if _has_column():
        op.drop_column(_TABLE, _COLUMN, schema=_SCHEMA)
