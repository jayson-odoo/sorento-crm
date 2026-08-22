"""Composer message snippets + their permissions (UAC AC-L4).

Canned replies an admin manages in the CRM and staff insert from the ticket
composer behind a "/" picker. Workspace-global in v1: no per-user and no
per-company column, because a snippet is shared team wording.

Two details worth reading before editing:

**The shortcut is unique case-insensitively, and only when set.** A partial
functional unique index rather than a plain UNIQUE column, so any number of
snippets may carry no shortcut at all while "/stock" can never resolve to two
different bodies.

**sync_permissions creates slugs but never grants them.** The registry sync at
startup will create the ``sla_management.message_snippets.*`` rows, but a
permission granted to nobody is indistinguishable from a broken feature, so the
grants are copied here from the existing conversation-SLA-tracking holders -
the same people who work the tickets these snippets are typed into.

Idempotent raw SQL, safe to re-run.

Revision ID: 329_message_snippets
Revises: 328_ticket_comments
Create Date: 2026-08-15
"""
import sqlalchemy as sa
from alembic import op

# Kept <= 32 chars: alembic_version.version_num is varchar(32).
revision = "329_message_snippets"
down_revision = "328_ticket_comments"
branch_labels = None
depends_on = None

TABLE = "message_snippets"

_PERMS = (
    (
        "sla_management.message_snippets.view",
        "View Message Snippets",
        "Permission to view Message Snippets.",
    ),
    (
        "sla_management.message_snippets.add",
        "Add Message Snippets",
        "Permission to add Message Snippets.",
    ),
    (
        "sla_management.message_snippets.edit",
        "Edit Message Snippets",
        "Permission to edit Message Snippets.",
    ),
    (
        "sla_management.message_snippets.delete",
        "Delete Message Snippets",
        "Permission to delete Message Snippets.",
    ),
)

# Whoever may already see the conversation SLA tickets gets the snippets that are
# typed into them. The composer picker itself reads the `.view` slug.
_GRANT_SOURCE_SLUG = "sla_management.conversation_sla_tracking.view"


def upgrade() -> None:
    bind = op.get_bind()

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS message_snippets (
            id         uuid PRIMARY KEY,
            name       varchar(150) NOT NULL,
            shortcut   varchar(60),
            body       text NOT NULL,
            is_active  boolean NOT NULL DEFAULT true,
            created_by varchar,
            created_at timestamp NOT NULL DEFAULT now(),
            updated_at timestamp
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_message_snippets_is_active "
        "ON message_snippets (is_active)"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_message_snippets_shortcut
            ON message_snippets (lower(shortcut))
            WHERE shortcut IS NOT NULL
        """
    )

    # ---- permissions -----------------------------------------------------
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


def downgrade() -> None:
    bind = op.get_bind()

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

    op.execute("DROP INDEX IF EXISTS uq_message_snippets_shortcut")
    op.execute("DROP INDEX IF EXISTS ix_message_snippets_is_active")
    op.execute("DROP TABLE IF EXISTS message_snippets")
