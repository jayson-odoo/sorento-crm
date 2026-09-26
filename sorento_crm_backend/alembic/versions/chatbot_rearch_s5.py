"""`system_settings.chatbot_memory`, and `system.chatbot_config.manage` granted to the
two administrator roles.

Chatbot turn re-architecture S5 backend (AC-1513, AC-1561).

**Why only `admin` and `superadmin`.** The first draft of this migration derived the
grant from every role already holding `system.chat_history.view`, on the reasoning that
whoever reads a turn is whoever fixes the domain row behind it. Measured on the
production copy, those roles are `admin`, `guest`, `integration_foundryx_esb` and
`integration_n8n` - so a read-only visitor and two machine principals would have been
handed write access to the policy the turn engine routes and narrows on. Reading a turn
and rewriting the engine's policy are not the same privilege. The grant is now the two
administrator roles by slug and nothing else; any other role is an operator decision,
made on the Roles screen.

Idempotent both ways, and a clean no-op on a database with no roles (CI's).

Revision ID: chatbot_rearch_s5
Revises: chatbot_rearch_s4b
"""
import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s5"
down_revision = "chatbot_rearch_s4b"
branch_labels = None
depends_on = None

_TARGET = "system.chatbot_config.manage"
# `user_roles.slug`, not `name`: the slug is what `user_service` keys its own
# administrator bypass on ("superadmin" / "admin"), and a role's display name is
# editable.
_ADMIN_ROLE_SLUGS = ("superadmin", "admin")
# Name and description match `app/rbac/permission_registry.py`'s own row, so the
# create-if-absent branch below cannot drift from what the registry sync would write.
_NAME = "Manage Chatbot Configuration"
_DESCRIPTION = (
    "Create, edit and delete chatbot domains and entity kinds - the policy the turn "
    "engine routes and narrows on."
)

_MEMORY_DEFAULT = (
    '{"recall_default": false, "episode_retention_days": 180, '
    '"profile_fields": ["tier", "language", "default_ledgers"], '
    '"focus_reset_events": ["topic_switch"]}'
)


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        "system_settings",
        sa.Column(
            "chatbot_memory",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=_MEMORY_DEFAULT,
        ),
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": _TARGET, "name": _NAME, "descr": _DESCRIPTION},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, tgt.id, now()
            FROM user_roles r
            CROSS JOIN user_permissions tgt
            WHERE tgt.slug = :target
              AND r.slug = ANY(:role_slugs)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"target": _TARGET, "role_slugs": list(_ADMIN_ROLE_SLUGS)},
    )


def downgrade() -> None:
    """Take back exactly the grants this made, and drop the column it added.

    The permission ROW stays: the registry sync would recreate it on the next boot
    anyway, and deleting it would take a grant somebody may have made by hand with it.
    """
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM user_role_permissions grant_row
            USING user_permissions tgt, user_roles r
            WHERE grant_row.permission_id = tgt.id
              AND grant_row.role_id = r.id
              AND tgt.slug = :target
              AND r.slug = ANY(:role_slugs)
            """
        ),
        {"target": _TARGET, "role_slugs": list(_ADMIN_ROLE_SLUGS)},
    )
    op.drop_column("system_settings", "chatbot_memory")
