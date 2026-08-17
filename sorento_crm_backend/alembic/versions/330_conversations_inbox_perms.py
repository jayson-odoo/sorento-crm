"""Conversations inbox permissions + the inbox list index (UAC AC-N1/AC-N2).

Two permissions and one index.

**`sla_management.conversations.view`** is the read gate for the inbox and for
every contact-keyed thread endpoint. Read access there is deliberately NOT
ticket assignment (AC-N2): a reassigned-away previous assignee, a mentioned
colleague and a manager all need to read the thread. Granted to every role that
already holds `sla_management.conversation_sla_tracking.view` - the people who
already see the tickets these conversations belong to.

**`sla_management.conversations.reply`** is the act gate for sending from the
inbox. The ticket drawer's own send route
(`POST .../conversation-sla-tracking/{id}/ticket/send`) carries NO permission
slug today - it is gated by `can_user_act_on_tracking` alone - so there is no
"ticket send/reply-equivalent permission" to copy grants from. Per the S4.9
plan's fallback, `.reply` therefore gets the SAME grant set as `.view`. Recorded
as an as-built note under AC-N2.

**`ix_chat_histories_contact_sent_desc`** serves the inbox list's
"latest message per contact" DISTINCT ON. The existing composite
(`ix_chat_histories_channel_contact_sent_id`) leads on `channel`, which the
inbox does not filter on (an inbox row is the contact, whatever channel they
last used), so that index cannot serve the per-contact aggregate.

Idempotent raw SQL, safe to re-run.

Revision ID: 330_conversations_inbox
Revises: 329_message_snippets
Create Date: 2026-08-15
"""
import sqlalchemy as sa
from alembic import op

# Kept <= 32 chars: alembic_version.version_num is varchar(32).
revision = "330_conversations_inbox"
down_revision = "329_message_snippets"
branch_labels = None
depends_on = None

_PERMS = (
    (
        "sla_management.conversations.view",
        "View Conversations",
        "Read any contact's conversation thread, its notes and its media from the "
        "Conversations inbox (read access is a permission, not ticket assignment).",
    ),
    (
        "sla_management.conversations.reply",
        "Reply in Conversations",
        "Send a WhatsApp reply to a contact from the Conversations inbox. Stamped "
        "onto the sender's own open ticket for that contact when they hold exactly one.",
    ),
)

_GRANT_SOURCE_SLUG = "sla_management.conversation_sla_tracking.view"

_INDEX = "ix_chat_histories_contact_sent_desc"


def upgrade() -> None:
    bind = op.get_bind()

    for slug, name, descr in _PERMS:
        bind.execute(
            sa.text(
                """
                INSERT INTO user_permissions (id, slug, name, description, created_at)
                SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
                WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
                """
            ),
            {"slug": slug, "name": name, "descr": descr},
        )

    for slug, _name, _descr in _PERMS:
        bind.execute(
            sa.text(
                """
                INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
                SELECT gen_random_uuid()::text, urp.role_id, tgt.id, now()
                  FROM user_role_permissions urp
                  JOIN user_permissions src ON src.id = urp.permission_id
                 CROSS JOIN user_permissions tgt
                 WHERE src.slug = :source_slug
                   AND tgt.slug = :slug
                ON CONFLICT DO NOTHING
                """
            ),
            {"source_slug": _GRANT_SOURCE_SLUG, "slug": slug},
        )

    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_INDEX} "
        "ON chat_histories (contact_id, sent_at DESC, id DESC)"
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.execute(f"DROP INDEX IF EXISTS {_INDEX}")

    for slug, _name, _descr in _PERMS:
        bind.execute(
            sa.text(
                """
                DELETE FROM user_role_permissions
                 WHERE permission_id IN (SELECT id FROM user_permissions WHERE slug = :slug)
                """
            ),
            {"slug": slug},
        )
    for slug, _name, _descr in _PERMS:
        bind.execute(
            sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": slug}
        )
