"""Grant `inventory.stock.{view,edit,delete}` to the AutoCount ESB role
(ingest-stock-balances-2-5 D9).

`stock_balances` becomes a push entity on `/external/ingest` (contract 2.5):
the ESB now upserts `stock.quantity_on_hand` directly, and its role needs the
same view/edit/delete grant on the Stock screen's own slugs any other write
path through the ESB already gets (`511_brands_esb_grant.py` is the exact
precedent - same idempotent shape, same reasoning: the integration roles were
seeded once as a copy of Admin's grants, and Admin bypasses every permission
check, so a gap here is invisible until the ESB's first real push is refused).

Idempotent both ways: the permission rows are created only when absent (a
database built by alembic alone, never booted, so `sync_permissions` never
ran), the grant insert is SELECT-driven with `ON CONFLICT (role_id,
permission_id) DO NOTHING`, and a database with no `integration_foundryx_esb`
role (CI) is a clean no-op.

**Downgrade removes exactly these three grants for this role** (D9) - unlike
`511_brands_esb_grant.py`'s no-op downgrade, `inventory.stock.*` did not
pre-date this migration the way the brands slugs might have (the Admin copy
predates brands entirely), so there is nothing older to protect by leaving it
alone.

Revision ID: sb1_stock_balances_grant
Revises: oisl_0001_suggested_links
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op

revision = "sb1_stock_balances_grant"
down_revision = "oisl_0001_suggested_links"
branch_labels = None
depends_on = None

_ESB_ROLE_SLUG = "integration_foundryx_esb"

# (slug, name, description) - names/descriptions match what `_crud(...)` in
# `app/rbac/permission_registry.py` would generate, so the create-if-absent
# branch cannot drift from what the registry sync would have written.
_GRANTS = (
    ("inventory.stock.view", "View Stock", "Permission to view Stock."),
    ("inventory.stock.edit", "Edit Stock", "Permission to edit Stock."),
    ("inventory.stock.delete", "Delete Stock", "Permission to delete Stock."),
)


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
    """Create the three slugs if absent, then grant them to the ESB role."""
    for slug, name, description in _GRANTS:
        _create_if_absent(bind, slug, name, description)

    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, p.id, now()
            FROM user_roles r
            CROSS JOIN user_permissions p
            WHERE r.slug = :role_slug AND p.slug = ANY(:slugs)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"role_slug": _ESB_ROLE_SLUG, "slugs": [slug for slug, _, _ in _GRANTS]},
    )


def revert(bind) -> None:
    """Removes exactly these three grants for the ESB role (D9) - the
    permission rows themselves are left alone, only the role's grant of them."""
    bind.execute(
        sa.text(
            """
            DELETE FROM user_role_permissions rp
            USING user_roles r, user_permissions p
            WHERE rp.role_id = r.id
              AND rp.permission_id = p.id
              AND r.slug = :role_slug
              AND p.slug = ANY(:slugs)
            """
        ),
        {"role_slug": _ESB_ROLE_SLUG, "slugs": [slug for slug, _, _ in _GRANTS]},
    )


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
