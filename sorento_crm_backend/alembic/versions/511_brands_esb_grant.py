"""Grant `master_data.brands.{view,edit,delete}` to the AutoCount ESB role
(autocount-brands-ingest D6).

`brands` becomes a first-class ingest entity (contract 2.3) alongside the six
other masters the ESB already pushes, each of which the ESB's role already
holds view/edit/delete on. Whether that role's grants happen to include the
new brand slugs is unknown - the integration roles were seeded once as a copy
of Admin's grants (`integration_seed.py`), and Admin bypasses every permission
check, so a gap here is invisible to anyone testing as an admin and would
surface as the ESB being told brands are supported and then refused on the
first push.

Idempotent both ways, same shape as `445_autocount_grant_sweep.py`: permission
rows are created only when absent (a database built by alembic alone, never
booted, so `sync_permissions` never ran), the grant insert is SELECT-driven
with `ON CONFLICT (role_id, permission_id) DO NOTHING`, and a database with no
`integration_foundryx_esb` role (CI) is a clean no-op.

**Downgrade is a no-op.** The grants may pre-date this migration (the Admin
copy), and stripping them could take away access the ESB already had before
this ever ran. Only the ESB role is touched - the one caller of this surface;
admin bypasses everything else.

The statements live in `apply()`/`revert()`, driven directly in tests on a
connection that rolls back - the local Postgres is shared across worktrees and
its `alembic_version` is stamped for another branch, so `alembic upgrade` is
not a way to check this one.

Revision ID: 511_brands_esb_grant
Revises: 512_hidden_by_default_col
Create Date: 2026-09-12
"""
import sqlalchemy as sa
from alembic import op

revision = "511_brands_esb_grant"
down_revision = "512_hidden_by_default_col"
branch_labels = None
depends_on = None

_ESB_ROLE_SLUG = "integration_foundryx_esb"

# (slug, name, description) - names/descriptions match what `_crud(...)` in
# `app/rbac/permission_registry.py` would generate, so the create-if-absent
# branch cannot drift from what the registry sync would have written.
_GRANTS = (
    ("master_data.brands.view", "View Brands", "Permission to view Brands."),
    ("master_data.brands.edit", "Edit Brands", "Permission to edit Brands."),
    ("master_data.brands.delete", "Delete Brands", "Permission to delete Brands."),
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
    """No-op (D6) - see the module docstring for why."""


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
