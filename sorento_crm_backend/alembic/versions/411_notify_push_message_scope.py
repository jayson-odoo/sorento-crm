"""users.notify_push_message_scope - which contacts' messages buzz my phone.

PLAN-message-push slice S1. One column, not a preference table, because there is
exactly one event today; the second event (mentions) is the trigger to migrate this
into `notification_scope_preferences(user_id, event_key, scope)`.

The server default IS the backfill (UAC AC-M27): every row that existed before this
ran comes out `assigned_and_coverage`, which is the behaviour the feature ships with,
so no backfill script exists and none is needed.

The revision id is deliberately short. `alembic_version.version_num` is varchar(32)
on a database alembic created itself, so a longer HEAD cannot be stamped on a fresh
CI database - see tests/test_alembic_revision_ids.py.

Revision ID: 411_notify_push_msg_scope
Revises: 410_trgm_norm_idx
"""
from alembic import op
import sqlalchemy as sa

revision = "411_notify_push_msg_scope"
down_revision = "410_trgm_norm_idx"
branch_labels = None
depends_on = None

_DEFAULT = "assigned_and_coverage"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notify_push_message_scope",
            sa.String(length=24),
            nullable=False,
            server_default=_DEFAULT,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "notify_push_message_scope")
