"""Configurable alerting percentile for the chat-latency watchdog

p50/p95/p99 were all computed, but `evaluate_breach` alerted on p99 only, hardcoded.
Choosing p95 meant a code change. The percentile is a policy decision, not an
implementation detail, so it moves to settings alongside its target.

Revision ID: 294_chat_latency_percentile
Revises: 293_api_call_log
"""
import sqlalchemy as sa
from alembic import op

revision = "294_chat_latency_percentile"
down_revision = "293_api_call_log"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    present = {c["name"] for c in sa.inspect(conn).get_columns("system_settings")}
    if "chat_latency_percentile" not in present:
        op.add_column(
            "system_settings",
            # Stored as the integer percentile (50/90/95/99) rather than a float
            # quantile, so the column reads the way people say it out loud and
            # cannot carry a nonsense value like 0.995.
            sa.Column(
                "chat_latency_percentile",
                sa.Integer(),
                nullable=False,
                server_default="99",
            ),
        )


def downgrade():
    op.drop_column("system_settings", "chat_latency_percentile")
