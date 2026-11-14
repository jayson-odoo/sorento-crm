"""UI v2 phase 0: version switch, theme, page-view telemetry

Adds users.ui_version / users.theme_mode, system_settings.ui_v2_enabled / theme, the
ui_page_views table (90-day retention rides the daily `api_call_log_prune` task) and the
`ui.v2.preview` permission, granted to no role. Additive and idempotent.

Revision ID: uiv2_0001_version_theme_views
Revises: srv2_0003_contact_phone_width
"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "uiv2_0001_version_theme_views"
down_revision = "srv2_0003_contact_phone_width"
branch_labels = None
depends_on = None

_SLUG = "ui.v2.preview"


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ui_version VARCHAR(2) NOT NULL DEFAULT 'v1'")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS theme_mode VARCHAR(6) NOT NULL DEFAULT 'system'")
    op.execute("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS ui_v2_enabled BOOLEAN NOT NULL DEFAULT true")
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS theme JSONB NOT NULL "
        """DEFAULT '{"preset": "sorento-blue", "custom_hex": null}'::jsonb"""
    )

    conn = op.get_bind()
    if not sa.inspect(conn).has_table("ui_page_views"):
        op.create_table(
            "ui_page_views",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("route", sa.String(200), nullable=False),
            sa.Column("viewport", sa.String(8), nullable=False),
            sa.Column("ui_version", sa.String(2), nullable=False),
            sa.Column("ms_to_first_data", sa.Integer(), nullable=True),
            sa.Column("viewed_at", sa.DateTime(timezone=False), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ui_page_views_created_at ON ui_page_views (created_at)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ui_page_views_user_created_at ON ui_page_views (user_id, created_at)"
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
                "name": "Preview UI v2",
                "desc": "Switch to the new (v2) interface from the avatar menu.",
                "now": datetime.utcnow(),
            },
        )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = :s)"
        ),
        {"s": _SLUG},
    )
    conn.execute(sa.text("DELETE FROM user_permissions WHERE slug = :s"), {"s": _SLUG})
    op.execute("DROP TABLE IF EXISTS ui_page_views")
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS theme")
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS ui_v2_enabled")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS theme_mode")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS ui_version")
