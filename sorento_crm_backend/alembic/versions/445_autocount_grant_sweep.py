"""Grant `.delete` on sales agents, SCM sales orders and SCM purchase orders to
whoever already holds the matching `.edit`.

**Measured, not assumed.** On the dev copy of production every one of the six
masters this surface already ingests has IDENTICAL `.edit` and `.delete` holder
lists - for `master_data.products`, `master_data.product_categories`,
`master_data.units_of_measure`, `inventory.warehouses`, `procurement.suppliers`
and `order_management.customers` alike, both slugs are held by exactly admin,
director, integration_foundryx_esb, integration_n8n, integration_sorento_mcp and
that resource's domain roles. Whoever may author a master may retire one; there
is no third audience anywhere on the surface. So sweeping delete onto the edit
holders is not a new policy, it is the shape the surface already has.

The three slugs below are the exception, and they are the three group A4's
deletion endpoint needs:

    master_data.sales_agents.delete   admin                                  (1)
    master_data.sales_agents.edit     admin, integration_foundryx_esb,
                                      integration_n8n                        (3)
    scm.sales_orders.delete           admin                                  (1)
    scm.sales_orders.edit             admin, integration_foundryx_esb,
                                      integration_n8n                        (3)
    scm.purchase_orders.delete        admin                                  (1)
    scm.purchase_orders.edit          admin, integration_foundryx_esb,
                                      integration_n8n                        (3)

`admin` reaches everything anyway because
`UserPermissionService.check_user_has_permission` short-circuits on that role
slug, which is exactly why the gap is invisible to whoever tests as an admin: the
ESB principal holds `.edit`, is told it may push these entities, and is then
refused when it asks Sorento to retire one. A permission granted to nobody but
admin is indistinguishable from an endpoint that does not work.

Derived from the live grants rather than a hand-written role list, so it stays
correct on a database whose roles were customised after provisioning. Idempotent
both ways: the permission rows are created only when absent (a fresh deploy runs
migrations before the app's registry sync, and `scm.sales_orders.*` is not in
`permission_registry` at all - those rows were provisioned outside it), every
insert is SELECT-driven with `ON CONFLICT DO NOTHING`, and a database with no
roles and no grants - CI's - is a clean no-op rather than a failure.

The statements live in `apply()` / `revert()` so a test can run them on a
connection it rolls back. The local Postgres is shared across worktrees and its
`alembic_version` is stamped for another branch, so `alembic upgrade` is not a
way to check this one.

Revision ID: 445_autocount_grant_sweep
Revises: 444_notify_email_on_mention
"""
import sqlalchemy as sa
from alembic import op

revision = "445_autocount_grant_sweep"
down_revision = "444_notify_email_on_mention"
branch_labels = None
depends_on = None


# (target slug, the slug whose holders get it, name, description)
# Names and descriptions match what `_crud(...)` in `app/rbac/permission_registry.py`
# generates, so the create-if-absent branch cannot drift from what the registry sync
# would have written - and, for the two `scm.*` slugs, from the rows already present
# on the live database.
_SWEEP = (
    (
        "master_data.sales_agents.delete",
        "master_data.sales_agents.edit",
        "Delete Sales Agents",
        "Permission to delete Sales Agents.",
    ),
    (
        "scm.sales_orders.delete",
        "scm.sales_orders.edit",
        "Delete SCM Sales Orders",
        "Permission to delete SCM Sales Orders.",
    ),
    (
        "scm.purchase_orders.delete",
        "scm.purchase_orders.edit",
        "Delete SCM Purchase Orders",
        "Permission to delete SCM Purchase Orders.",
    ),
)


def apply(bind) -> None:
    """Create the target slugs if absent, then grant each to its source's holders."""
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


def revert(bind) -> None:
    """Take back exactly the grants `apply` made, leaving the permission rows.

    Mirrored rather than blanket: a target grant is removed only where the role
    also holds the source `.edit` grant, which is the condition that produced it.
    A `.delete` granted by hand to a role with no `.edit` was not written here and
    survives.

    The permission rows themselves stay. Two of the three were measured present
    before this ran, so deleting them would remove something this migration did
    not create.
    """
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


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
