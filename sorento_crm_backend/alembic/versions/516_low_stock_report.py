"""low stock report: the chat marker, the worker's delivery claim and the chat wait

PLAN-low-stock-report.md - the lane's ONE migration, landed in S3 (the workbook slice)
rather than in S5 (the chat route) so `generate_low_stock_report` can stamp its row counts
at `mark_ready` there. S5 uses the rest of these columns; nothing else does yet.

* ``scm.reorder_run.requested_via`` - ``chat`` on a run the low stock tool started over
  WhatsApp, NULL on every other run. Drives the "via chat" marker on the plans list.
* ``user_downloads.deliver_to_contact_id`` / ``delivered_at`` - the two halves of the
  hand-off between the chat turn and the worker (AC-44/AC-45). The turn claims delivery for
  the worker by writing the contact; the worker claims the push back by stamping
  ``delivered_at``. Two conditional updates on one row, so exactly one of them fires.
* ``user_downloads.row_count_low`` / ``row_count_all`` - written at ``mark_ready`` so the
  chat route can state "Low: 12 of 340 planned products" without opening the workbook on
  the request thread (AC-36/AC-43).
* ``system_settings.low_stock_sync_wait_seconds`` - how long that route holds the turn open
  before it answers ``pending``. NOT NULL DEFAULT 40 (owner's ruling: a System Setting, not
  a constant), validated 5..90 on PUT the way ``media_sync_wait_seconds`` is.

Every column is additive and nullable (or defaulted), so the downgrade is a plain drop and
no data is rewritten either way.

Revision ID: 516_low_stock_report
Revises: 511_committed_v_line_owed
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "516_low_stock_report"
down_revision = "511_committed_v_line_owed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reorder_run",
        sa.Column("requested_via", sa.String(length=10), nullable=True),
        schema="scm",
    )
    op.add_column(
        "user_downloads",
        sa.Column("deliver_to_contact_id", UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "user_downloads",
        sa.Column("delivered_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column("user_downloads", sa.Column("row_count_low", sa.Integer(), nullable=True))
    op.add_column("user_downloads", sa.Column("row_count_all", sa.Integer(), nullable=True))
    op.add_column(
        "system_settings",
        sa.Column(
            "low_stock_sync_wait_seconds",
            sa.Integer(),
            nullable=False,
            server_default="40",
        ),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "low_stock_sync_wait_seconds")
    op.drop_column("user_downloads", "row_count_all")
    op.drop_column("user_downloads", "row_count_low")
    op.drop_column("user_downloads", "delivered_at")
    op.drop_column("user_downloads", "deliver_to_contact_id")
    op.drop_column("reorder_run", "requested_via", schema="scm")
