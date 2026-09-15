"""`system_settings.chatbot_memory`, and `system.chatbot_config.manage` swept onto the
roles that already read the chatbot's turns.

Chatbot turn re-architecture S5 backend (AC-1513, AC-1561).

**Why the sweep, and why from `chat_history.view`.** A permission granted to nobody is
indistinguishable from a broken feature: `admin` and `superadmin` short-circuit
`check_user_has_permission`, so the person who verifies the screens never notices that
every other provisioned role is locked out of it. The source grant is
`system.chat_history.view` because that is already "may look inside the chatbot" - the
operator who reads why a turn answered wrongly is the operator who fixes the domain row
that made it answer wrongly. It is deliberately NOT derived from a hand-written role
list, so it stays correct on a database whose roles were customised after provisioning.

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
_SOURCE = "system.chat_history.view"
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
            SELECT gen_random_uuid()::text, rp.role_id, tgt.id, now()
            FROM user_role_permissions rp
            JOIN user_permissions src ON src.id = rp.permission_id AND src.slug = :source
            CROSS JOIN user_permissions tgt
            WHERE tgt.slug = :target
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"source": _SOURCE, "target": _TARGET},
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
            USING user_permissions tgt
            WHERE grant_row.permission_id = tgt.id
              AND tgt.slug = :target
              AND EXISTS (
                  SELECT 1
                  FROM user_role_permissions src_rp
                  JOIN user_permissions src
                    ON src.id = src_rp.permission_id AND src.slug = :source
                  WHERE src_rp.role_id = grant_row.role_id
              )
            """
        ),
        {"source": _SOURCE, "target": _TARGET},
    )
    op.drop_column("system_settings", "chatbot_memory")
