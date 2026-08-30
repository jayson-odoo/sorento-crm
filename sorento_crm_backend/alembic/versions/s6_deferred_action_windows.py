"""The two grace windows a deferred record action waits out (D16, S6-04).

`system_settings.deferred_delete_seconds` (10) and `deferred_action_seconds` (5): how
long a parked delete, and anything reversible, counts down before the server applies it.
They are columns rather than constants so the windows are tuned in System Settings >
General without a deploy - which is the whole of D16.

NOT NULL with the defaults as server_default, so the existing singleton row is
backfilled by the DDL itself and no separate data migration is needed.

Chained onto `445_signin_background`, which the S5 branch this one sits on carries.
That file is not in this worktree yet - it arrives when S5's commits land underneath -
so `alembic upgrade` cannot resolve the chain here, and the tests do not need it to
(they build the schema from the models via `tests/_pg_fixture.py`). Re-check
`alembic heads` against the default branch immediately before merging, or the graph
forks into two heads.

Revision ID: s6_deferred_action_windows
Revises: 445_signin_background
"""
from alembic import op
import sqlalchemy as sa


revision = "s6_deferred_action_windows"
down_revision = "445_signin_background"
branch_labels = None
depends_on = None

TABLE = "system_settings"
COLUMNS = (
    ("deferred_delete_seconds", "10"),
    ("deferred_action_seconds", "5"),
)


def upgrade() -> None:
    for name, default in COLUMNS:
        op.add_column(
            TABLE,
            sa.Column(name, sa.Integer(), nullable=False, server_default=default),
        )


def downgrade() -> None:
    for name, _default in COLUMNS:
        op.drop_column(TABLE, name)
