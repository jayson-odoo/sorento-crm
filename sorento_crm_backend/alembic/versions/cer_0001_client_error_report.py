"""client_error_report table + view permission (CLIENT-ERROR-REPORT)

Browser crash reports from the root and protected error boundaries. Additive only.
Retention (30 days) rides the existing daily `api_call_log_prune` task, so no new
scheduled task row.

Revision ID: cer_0001_client_error_report
Revises: oiod_0001_backfill
"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "cer_0001_client_error_report"
down_revision = "oiod_0001_backfill"
branch_labels = None
depends_on = None

_SLUG = "system_management.client_error.view"


def upgrade():
    conn = op.get_bind()
    if not sa.inspect(conn).has_table("client_error_report"):
        op.create_table(
            "client_error_report",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("user_id", sa.String(64), nullable=True),
            sa.Column("boundary", sa.String(16), nullable=False),
            sa.Column("error_name", sa.String(128), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("stack", sa.Text(), nullable=True),
            sa.Column("digest", sa.String(64), nullable=True),
            sa.Column("path", sa.String(512), nullable=True),
            sa.Column("build_sha", sa.String(64), nullable=True),
            sa.Column("user_agent", sa.String(512), nullable=True),
            sa.Column("is_chunk_error", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("client_ts", sa.DateTime(timezone=False), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        )
    op.execute("CREATE INDEX IF NOT EXISTS ix_client_error_report_created_at ON client_error_report (created_at)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_client_error_report_user_created_at "
        "ON client_error_report (user_id, created_at)"
    )

    if conn.execute(sa.text("SELECT 1 FROM user_permissions WHERE slug = :s"), {"s": _SLUG}).fetchone() is None:
        conn.execute(
            sa.text(
                "INSERT INTO user_permissions (id, slug, name, description, created_at) "
                "VALUES (:id, :slug, :name, :desc, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "slug": _SLUG,
                "name": "View Client Errors",
                "desc": "View browser crash reports (error, page path, build, browser).",
                "now": datetime.utcnow(),
            },
        )


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM user_permissions WHERE slug = :s"), {"s": _SLUG})
    op.execute("DROP TABLE IF EXISTS client_error_report")
