"""Register and grant the two slugs the chatbot media feature needs.

Registering a permission is not enough. Grants are computed at role-provision
time and do NOT reach existing roles automatically, so a new slug with no grant
path silently 403s the very feature it was meant to protect - and the failure
looks like a broken integration or a broken button, not a missing grant. This is
DoD gate item 7 and it is the single most common way a feature like this ships
broken.

Two slugs, granted differently because they answer different questions.

``integration.chatbot_media.process`` - the /external endpoint n8n calls. Granted
to ``admin`` (which is what the shared key resolves to today, so enforcement
cannot regress live n8n traffic at cutover) and to every ``integration_*`` role
seeded by migration 297. It is its own slug rather than a reused one because it
SPENDS extraction budget: an integration allowed to sync contacts is not
automatically allowed to charge a photo read to a dealer's allowance.

``user_management.contacts.edit`` - the operator surface. Contact editing had no
permission at all before this: every contact write on ``contacts.py`` is gated by
``get_current_user`` alone, so today any authenticated user can change one.
Granting the new slug to EVERY existing role therefore reproduces today's reach
exactly rather than quietly narrowing it - the point of naming it is that it can
now be revoked per role, which was previously impossible. It is deliberately not
an admin-only slug: UAC S1-06 is "anyone who can edit a contact can change media
access. No new admin-only role is introduced."

Revision ID: 357_chatbot_media_permissions
Revises: 356_chatbot_media_endpoint
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "357_chatbot_media_permissions"
down_revision = "356_chatbot_media_endpoint"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

MEDIA_SLUG = "integration.chatbot_media.process"
CONTACT_EDIT_SLUG = "user_management.contacts.edit"

_PERMISSIONS = [
    (
        MEDIA_SLUG,
        "Process chatbot media",
        "Submit an inbound WhatsApp photo or voice note for gating, metering and extraction.",
    ),
    (
        CONTACT_EDIT_SLUG,
        "Edit Contacts",
        "Edit a respond contact, including its chatbot media access and monthly limits.",
    ),
]


def _insert_permission(bind, slug: str, name: str, description: str) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": slug, "name": name, "descr": description},
    )


def _grant(bind, slug: str, role_filter: str) -> None:
    bind.execute(
        sa.text(
            f"""
            INSERT INTO user_role_permissions (id, role_id, permission_id)
            SELECT gen_random_uuid()::text, r.id, p.id
            FROM user_roles r
            CROSS JOIN user_permissions p
            WHERE p.slug = :slug
              AND ({role_filter})
              AND NOT EXISTS (
                  SELECT 1 FROM user_role_permissions rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        ),
        {"slug": slug},
    )


def upgrade() -> None:
    bind = op.get_bind()
    for slug, name, description in _PERMISSIONS:
        _insert_permission(bind, slug, name, description)

    # The integration surface: admin plus every integration_* role.
    _grant(bind, MEDIA_SLUG, "r.slug = 'admin' OR r.slug LIKE 'integration\\_%'")
    # The operator surface: everybody, because everybody could already do it.
    _grant(bind, CONTACT_EDIT_SLUG, "TRUE")


def downgrade() -> None:
    bind = op.get_bind()
    slugs = [slug for slug, _name, _descr in _PERMISSIONS]
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = ANY(:slugs))"
        ),
        {"slugs": slugs},
    )
    bind.execute(
        sa.text("DELETE FROM user_permissions WHERE slug = ANY(:slugs)"),
        {"slugs": slugs},
    )
