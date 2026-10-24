"""Grant resource.attachments.delete to project.customer.service

Single attachment delete (`DELETE /resource-management/attachments/{id}`) now requires
`resource.attachments.delete` (ATTACH-DELETE-PERM). Project customer service deletes project
documents through that route from the Project Documents tab, and the owner ruled on 20 Oct 2026
that the role keeps doing so by holding the slug (full library delete, chosen over a
project-scoped rule).

Data only, additive and idempotent: the link is inserted only when the role and the permission
both exist and the link is missing, so a fresh install without the role, and a database where
the role was already granted by hand, both upgrade cleanly. A trashed role is skipped. Downgrade
removes only that one role-permission pair, including a link that was granted by hand before
this migration ran (it cannot tell the two apart).

Revision ID: adp_0001_pcs_attach_delete
Revises: chs_0001_direct_ingress
"""
import sqlalchemy as sa
from alembic import op

revision = "adp_0001_pcs_attach_delete"
down_revision = "chs_0001_direct_ingress"
branch_labels = None
depends_on = None

_ROLE_SLUG = "project.customer.service"
_PERMISSION_SLUG = "resource.attachments.delete"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
            "SELECT gen_random_uuid()::text, r.id, p.id, now() "
            "FROM user_roles r, user_permissions p "
            "WHERE r.slug = :role AND p.slug = :perm AND r.is_trashed = false "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM user_role_permissions urp "
            "  WHERE urp.role_id = r.id AND urp.permission_id = p.id"
            ")"
        ),
        {"role": _ROLE_SLUG, "perm": _PERMISSION_SLUG},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "DELETE FROM user_role_permissions urp "
            "USING user_roles r, user_permissions p "
            "WHERE urp.role_id = r.id AND urp.permission_id = p.id "
            "AND r.slug = :role AND p.slug = :perm"
        ),
        {"role": _ROLE_SLUG, "perm": _PERMISSION_SLUG},
    )
