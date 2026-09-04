"""`scm.shipping_orders.*` + `integration.contract.read` (S0, PLAN-autocount-document-ingest-v2).

Two new slugs group A3's next slices need before any route can guard on them:

* `scm.shipping_orders.{view,add,edit,delete}` for the shipping-order entity slice S3
  ingests (D8's contract lists it today; the entity itself lands later). Same shape as
  the `scm.sales_orders.*` / `scm.purchase_orders.*` pair migration 445 already created,
  and swept the same way: a role holding `scm.purchase_orders.X` also ends up holding
  `scm.shipping_orders.X`, because a shipping order is the same category of document as
  a purchase order on this surface and there is no audience that may push one but not
  the other.
* `integration.contract.read` (D8) for `GET /external/contract`. Swept onto every role
  holding `scm.sales_orders.edit` - the same three roles (admin, integration_foundryx_esb,
  integration_n8n) that already push sales orders through the ESB are exactly the roles
  that need to ask Sorento what version it accepts before pushing one.

Idempotent both ways, same idiom as migration 445: `_create_if_absent` before every sweep,
every grant insert `ON CONFLICT DO NOTHING`. `revert` removes only the grants this
migration made (mirrored on the source slug), leaving the permission rows - a
`scm.shipping_orders.delete` granted by hand to a role without `.edit` was not written
here and survives.

Revision ID: 472_ingest_v2_permissions
Revises: 471_merge_tag_size_spo_numbering
"""
import sqlalchemy as sa
from alembic import op

revision = "472_ingest_v2_permissions"
down_revision = "471_merge_tag_size_spo_numbering"
branch_labels = None
depends_on = None


# Spelled the way `_crud(...)` in `app/rbac/permission_registry.py` spells them, so the
# create-if-absent branch cannot drift from what a registry sync would have written.
_SHIPPING_ORDERS_ACTIONS = ("view", "add", "edit", "delete")
_SHIPPING_ORDERS_PERMISSIONS = tuple(
    (
        f"scm.shipping_orders.{action}",
        f"{action.capitalize()} SCM Shipping Orders",
        f"Permission to {action} SCM Shipping Orders.",
    )
    for action in _SHIPPING_ORDERS_ACTIONS
)

_CONTRACT_READ = (
    "integration.contract.read",
    "Read ingest contract",
    "Read the AutoCount ESB ingest contract version and supported entity list.",
)

# (target slug, the slug whose holders get it)
_SWEEP = tuple(
    (f"scm.shipping_orders.{action}", f"scm.purchase_orders.{action}")
    for action in _SHIPPING_ORDERS_ACTIONS
) + ((_CONTRACT_READ[0], "scm.sales_orders.edit"),)


def _create_if_absent(bind, slug: str, name: str, description: str) -> None:
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


def apply(bind) -> None:
    """Create the slugs if absent, then grant each target to its source's holders."""
    for slug, name, description in _SHIPPING_ORDERS_PERMISSIONS:
        _create_if_absent(bind, slug, name, description)
    _create_if_absent(bind, *_CONTRACT_READ)

    for target, source in _SWEEP:
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
    """Take back exactly the grants `apply` made, leaving the permission rows."""
    for target, source in _SWEEP:
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
