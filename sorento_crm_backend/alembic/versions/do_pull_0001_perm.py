"""Permission for the Delivery Orders pull from AutoCount (PLAN-autocount-do-pull-crm-30sep.md).

`order_management.orders.autocount_pull` is swept onto every role that already holds the
sibling `order_management.orders.import` permission (P13, the same owner ruling
`522_autocount_pull_perms` applied to products and stock: the new capability is "another way
to bring in the same book", so whoever could already import it may now pull it instead),
integration roles excluded (an integration credential has no browser to click Pull from).
`admin` is granted explicitly too, so the row exists even where `admin` was never directly
granted `.import` by name.

Revision ID: do_pull_0001_perm
Revises: ac_grn_do_0001_ingest
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "do_pull_0001_perm"
down_revision = "ac_grn_do_0001_ingest"
branch_labels = None
depends_on = None

_PERMISSIONS = [
    (
        "order_management.orders.autocount_pull",
        "Pull Delivery Orders from AutoCount",
        "Permission to pull a delivery orders snapshot from AutoCount and review/confirm it.",
    ),
]
#: (new slug, sibling slug already granted to the roles that should get it too).
_SWEEP = [
    ("order_management.orders.autocount_pull", "order_management.orders.import"),
]
_GRANT_ROLE_SLUGS = ("admin",)
_EXCLUDED_ROLE_PREFIX = "integration\\_%"


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


def _sweep(bind, target: str, source: str) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, rp.role_id, tgt.id, now()
            FROM user_role_permissions rp
            JOIN user_permissions src ON src.id = rp.permission_id AND src.slug = :source
            JOIN user_roles r ON r.id = rp.role_id
            CROSS JOIN user_permissions tgt
            WHERE tgt.slug = :target
              AND r.slug NOT LIKE :excluded
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"source": source, "target": target, "excluded": _EXCLUDED_ROLE_PREFIX},
    )


def _grant_to_roles(bind, slug: str, role_slugs: tuple[str, ...]) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, p.id, now()
            FROM user_roles r
            CROSS JOIN user_permissions p
            WHERE p.slug = :slug AND r.slug = ANY(:roles)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"slug": slug, "roles": list(role_slugs)},
    )


def upgrade() -> None:
    bind = op.get_bind()
    for slug, name, description in _PERMISSIONS:
        _insert_permission(bind, slug, name, description)
    for target, source in _SWEEP:
        _sweep(bind, target, source)
    for slug, _name, _descr in _PERMISSIONS:
        _grant_to_roles(bind, slug, _GRANT_ROLE_SLUGS)


def downgrade() -> None:
    bind = op.get_bind()
    slugs = [slug for slug, _, _ in _PERMISSIONS]
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = ANY(:slugs))"
        ),
        {"slugs": slugs},
    )
    bind.execute(
        sa.text("DELETE FROM user_permissions WHERE slug = ANY(:slugs)"), {"slugs": slugs}
    )
