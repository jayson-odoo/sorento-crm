"""Chat history admin permissions, downloads retention, and the purge task.

Message content is customer PII, so viewing and exporting are separate slugs rather than
folded into a general system-admin grant.

Also seeds `user_downloads_purge`. Nothing has ever deleted download rows or their stored
objects — with `complaint_pdf` as the only producer that went unnoticed, but chat-history
CSV exports are the largest artifacts the system produces, so it now matters. The purge
applies to every download kind, not just the new one.

Revision ID: 292_chat_history_admin_perms_and_purge
Revises: 291_chat_latency_settings_and_tasks
"""
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "292_chat_history_admin_perms_and_purge"
down_revision = "291_chat_latency_settings_and_tasks"
branch_labels = None
depends_on = None


_PERMISSIONS = (
    (
        "system.chat_history.view",
        "View Chat History",
        "View stored WhatsApp/chat messages and round-trip latency. Message content is customer PII.",
    ),
    (
        "system.chat_history.export",
        "Export Chat History",
        "Export chat messages to CSV via My Downloads.",
    ),
)

# No role grants are seeded, and that is deliberate.
#
# `UserPermissionService.check_user_has_permission` short-circuits to True for the
# superadmin and admin roles, so every `system.*` page is reachable by them without an
# explicit grant — `system.respond_outbox.view` and `system.email_outbox.view` both sit
# at zero grants today for exactly this reason. Registering the slugs still matters: it
# makes them assignable to a non-admin role later, and it keeps the registry complete.
#
# Chat history carries raw customer message content, so defaulting it to admin-only is
# the correct posture; broadening it should be a deliberate act in the roles UI.


def upgrade():
    conn = op.get_bind()
    now = datetime.utcnow()

    present = {
        r[0]
        for r in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'system_settings'"
            )
        )
    }
    if "downloads_retention_days" not in present:
        op.add_column(
            "system_settings",
            sa.Column("downloads_retention_days", sa.Integer(), nullable=False, server_default="30"),
        )

    for slug, name, description in _PERMISSIONS:
        row = conn.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
        ).fetchone()
        if row is None:
            perm_id = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    "INSERT INTO user_permissions (id, slug, name, description, created_at) "
                    "VALUES (:id, :slug, :name, :desc, :now)"
                ),
                {"id": perm_id, "slug": slug, "name": name, "desc": description, "now": now},
            )
        else:
            perm_id = row.id


    conn.execute(
        sa.text(
            """
            INSERT INTO scheduled_tasks
                (id, key, name, description, enabled, interval_unit, interval_value, timezone)
            VALUES
                (gen_random_uuid(), 'user_downloads_purge', 'My Downloads purge',
                 'Daily: deletes My Downloads rows and their stored objects past the retention '
                 'window (default 30 days, configurable). Applies to every download kind.',
                 true, 'days', 1, 'UTC')
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM scheduled_tasks WHERE key = 'user_downloads_purge'"))
    for slug, _name, _desc in _PERMISSIONS:
        row = conn.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
        ).fetchone()
        if row is not None:
            conn.execute(
                sa.text("DELETE FROM user_role_permissions WHERE permission_id = :p"),
                {"p": row.id},
            )
            conn.execute(sa.text("DELETE FROM user_permissions WHERE id = :p"), {"p": row.id})
    op.drop_column("system_settings", "downloads_retention_days")
