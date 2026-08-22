"""Promotion types get their own RBAC slugs, granted to whoever already administers promotions.

Promotion-type config is not ordinary marketing data: `show_expired` and its bounds
decide what the WhatsApp bot tells a customer about an ended promotion. Leaving the
write routes on "any logged-in user" meant a normal CRM account could switch `special`
back on and change the answer the bot gives, so the three write routes are gated and
the slugs have to exist before they can be required.

Grants are copied from the holders of `marketing.promotions.edit`: whoever may already
edit a promotion is exactly who administers this vocabulary. A permission granted to
nobody is indistinguishable from a broken feature, which is why the copy matters more
than the insert.

Idempotent raw SQL, safe to re-run.

Revision ID: 362_promotion_type_perms
Revises: 361_promotion_types
"""
import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "362_promotion_type_perms"
down_revision = "361_promotion_types"
branch_labels = None
depends_on = None

_PERMS = (
    ("marketing.promotion_types.view", "View Promotion Types", "Permission to view Promotion Types."),
    ("marketing.promotion_types.add", "Add Promotion Types", "Permission to add Promotion Types."),
    ("marketing.promotion_types.edit", "Edit Promotion Types", "Permission to edit Promotion Types."),
    (
        "marketing.promotion_types.delete",
        "Delete Promotion Types",
        "Permission to delete Promotion Types.",
    ),
)

# Whoever may edit a promotion may administer the types those promotions are classified
# into - the two are the same job done by the same marketing staff.
_GRANT_SOURCE_SLUG = "marketing.promotions.edit"


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
                   AND NOT EXISTS (
                       SELECT 1
                         FROM user_role_permissions existing
                        WHERE existing.role_id = urp.role_id
                          AND existing.permission_id = tgt.id
                   )
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
        bind.execute(
            sa.text("DELETE FROM user_permissions WHERE slug = :slug"),
            {"slug": slug},
        )
