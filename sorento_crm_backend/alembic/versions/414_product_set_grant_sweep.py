"""Grant `master_data.product_sets.{view,add,edit,delete}` to whoever already holds
the matching `master_data.products.*`.

**Measured, not assumed.** All four `master_data.product_sets.*` rows exist in
`user_permissions` (the registry sync put them there) and are granted to **zero**
roles. `admin` and `superadmin` reach the screens anyway because
`UserPermissionService.check_user_has_permission` short-circuits on those two role
slugs, which is exactly why the gap survived a browser-verified build: the person
who verified it was an admin. Every other provisioned role is locked out of a
finished feature. A permission granted to nobody is indistinguishable from a broken
feature.

**Why products is the source.** A product set is a code that names products. Whoever
may see a product may see the sets that product belongs to, and whoever may author a
product may author the grouping of them; there is no third audience to invent. So the
grant is derived from the live `master_data.products.*` grants rather than from a
hand-written role list, which also means it stays correct on a database whose roles
were customised after provisioning.

As measured on the dev copy of production, that source mapping is:

    products.view   -> admin, director, integration_foundryx_esb, integration_n8n,
                       integration_sorento_mcp, marketing_manager,
                       purchasing_executive, purchasing_manager,
                       warehouse_executive, warehouse_manager   (10)
    products.add / .edit / .delete
                    -> the same ten MINUS warehouse_executive    (9)

so a warehouse executive can read a set and cannot author one, which is the shape
products already carries and the shape sets should carry.

**`integration_*` roles are included here, unlike `361_spec_registry_grant_sweep`.**
That migration excluded them because granting `spec_registry.add` to the n8n parser
would let a machine mint search vocabulary, inverting the one-source-of-truth
guarantee of that milestone. No such inversion exists here: n8n already holds
`products.add`/`.edit`/`.delete`, the external link and promotion paths resolve set
codes on its behalf, and a set is a grouping of rows it may already write. The
exclusion was a justified exception there, not a house style to copy.

Idempotent both ways. The grants use `ON CONFLICT DO NOTHING`, the permission rows
are created only when absent (a fresh deploy runs migrations before the app's
registry sync, so they may genuinely not be there yet), and every statement is a
`SELECT`-driven insert, so a database with no roles and no grants - CI's - is a clean
no-op rather than a failure.

Revision ID: 414_product_set_grant_sweep
Revises: 413_product_set_proposals
"""
import sqlalchemy as sa
from alembic import op

revision = "414_product_set_grant_sweep"
down_revision = "413_product_set_proposals"
branch_labels = None
depends_on = None


# (target product-set slug, the products slug whose holders get it, name, description)
# Name and description match `_crud("master_data", "product_sets", "Product Sets")` in
# `app/rbac/permission_registry.py`, so the create-if-absent branch cannot drift from
# what the registry sync would have written.
_SWEEP = (
    (
        "master_data.product_sets.view",
        "master_data.products.view",
        "View Product Sets",
        "Permission to view Product Sets.",
    ),
    (
        "master_data.product_sets.add",
        "master_data.products.add",
        "Add Product Sets",
        "Permission to add Product Sets.",
    ),
    (
        "master_data.product_sets.edit",
        "master_data.products.edit",
        "Edit Product Sets",
        "Permission to edit Product Sets.",
    ),
    (
        "master_data.product_sets.delete",
        "master_data.products.delete",
        "Delete Product Sets",
        "Permission to delete Product Sets.",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()

    for target, _source, name, description in _SWEEP:
        bind.execute(
            sa.text(
                """
                INSERT INTO user_permissions (id, slug, name, description, created_at)
                SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
                WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
                """
            ),
            {"slug": target, "name": name, "descr": description},
        )

    for target, source, _name, _descr in _SWEEP:
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
            {"source": source, "target": target},
        )


def downgrade() -> None:
    """Take back exactly the grants this migration made, leaving the permission rows.

    Mirrored rather than blanket: a target grant is removed only where the role also
    holds the source `products.*` grant, which is the condition that produced it. A
    `product_sets.view` granted by hand to a role with no `products.view` was not
    written here and survives the downgrade.

    The permission rows themselves stay. They were measured present before this ran,
    so deleting them would remove something this migration did not create.
    """
    bind = op.get_bind()

    for target, source, _name, _descr in _SWEEP:
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
            {"source": source, "target": target},
        )
