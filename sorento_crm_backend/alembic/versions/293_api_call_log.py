"""api_call_log table, retention settings, prune task, view permission

Request telemetry for /api/v1/external/* and MCP-originated calls, written by
middleware so coverage is total by construction. Deliberately NOT an extension of
`integration_log`, which is a work-queue record (retry_count, next_retry_at, a
business_id FK that chat ingest already fakes) rather than telemetry.

Revision ID: 293_api_call_log
Revises: 292_chat_history_admin_perms_and_purge
"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "293_api_call_log"
down_revision = "292_chat_history_admin_perms_and_purge"
branch_labels = None
depends_on = None

_PERMISSIONS = [
    (
        "system_management.api_call_log.view",
        "View API Call Log",
        "View external/MCP API request telemetry (payloads are redacted).",
    ),
]


def upgrade():
    conn = op.get_bind()

    op.create_table(
        "api_call_log",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("endpoint", sa.String(512), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("tool_name", sa.String(128), nullable=True),
        sa.Column("actor", sa.String(128), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False, server_default="success"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("request_payload", sa.Text(), nullable=True),
        sa.Column("response_payload", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_api_call_log_created_at", "api_call_log", ["created_at"])
    op.create_index("ix_api_call_log_source_created_at", "api_call_log", ["source", "created_at"])
    op.create_index("ix_api_call_log_correlation_id", "api_call_log", ["correlation_id"])
    op.create_index("ix_api_call_log_endpoint", "api_call_log", ["endpoint"])

    # Retention. Payloads are the bulk of the bytes and the shortest-lived value;
    # the metadata row stays useful for trend analysis long after the body does.
    present = {c["name"] for c in sa.inspect(conn).get_columns("system_settings")}
    if "api_call_log_payload_retention_days" not in present:
        op.add_column(
            "system_settings",
            sa.Column(
                "api_call_log_payload_retention_days",
                sa.Integer(),
                nullable=False,
                server_default="30",
            ),
        )
    if "api_call_log_row_retention_days" not in present:
        op.add_column(
            "system_settings",
            sa.Column(
                "api_call_log_row_retention_days",
                sa.Integer(),
                nullable=False,
                server_default="180",
            ),
        )

    conn.execute(
        sa.text(
            """
            INSERT INTO scheduled_tasks
                (id, key, name, description, enabled, interval_unit, interval_value, timezone)
            VALUES
                (gen_random_uuid(), 'api_call_log_prune', 'API call log prune',
                 'Daily: NULLs api_call_log payloads past the payload retention window '
                 '(default 30 days) and deletes rows past the row retention window '
                 '(default 180 days). Both configurable in system settings.',
                 true, 'days', 1, 'UTC')
            ON CONFLICT (key) DO NOTHING
            """
        )
    )

    now = datetime.utcnow()
    for slug, name, description in _PERMISSIONS:
        row = conn.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
        ).fetchone()
        if row is None:
            conn.execute(
                sa.text(
                    "INSERT INTO user_permissions (id, slug, name, description, created_at) "
                    "VALUES (:id, :slug, :name, :desc, :now)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "slug": slug,
                    "name": name,
                    "desc": description,
                    "now": now,
                },
            )


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM scheduled_tasks WHERE key = 'api_call_log_prune'"))
    for slug, _name, _desc in _PERMISSIONS:
        conn.execute(sa.text("DELETE FROM user_permissions WHERE slug = :s"), {"s": slug})
    op.drop_column("system_settings", "api_call_log_row_retention_days")
    op.drop_column("system_settings", "api_call_log_payload_retention_days")
    op.drop_index("ix_api_call_log_endpoint", table_name="api_call_log")
    op.drop_index("ix_api_call_log_correlation_id", table_name="api_call_log")
    op.drop_index("ix_api_call_log_source_created_at", table_name="api_call_log")
    op.drop_index("ix_api_call_log_created_at", table_name="api_call_log")
    op.drop_table("api_call_log")
