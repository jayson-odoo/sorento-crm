"""Grant `master_data.spec_registry.{view,edit,add}` to whoever already holds the
matching `master_data.products.*`.

**Measured, not assumed** (UAC M1): all four `master_data.spec_registry.*` permission
rows exist and are granted to **zero roles**, while `master_data.products.view` is
granted to 10 and `.edit` to 9. A permission granted to nobody is indistinguishable
from a broken feature - the whole master spec screen has been admin-only by accident,
and PR 2's add-a-specification picker and add-a-value flow would have shipped 403'd to
every merchandiser the feature exists for.

The routes are relaxed in the same PR so the product page's own reads never depended on
this sweep landing; the sweep is what makes the MASTER screen reachable, and what lets
`PATCH /spec-registry/{key}` accept a registry admin's calibration edit.

`.delete` is deliberately NOT swept. Deleting a key is not the mirror of adding one: a
`user` key with derived values against it takes them with it, and a `seed` key comes
back on the next deploy. It stays where it is until somebody asks for it.

**`integration_*` roles are excluded, and that exclusion is the load-bearing line.**
`integration_n8n`, `integration_sorento_mcp` and `integration_foundryx_esb` are API-key
principals. Granting `spec_registry.add` to the n8n parser would let a machine mint
vocabulary keys - which inverts the one-source-of-truth guarantee this entire milestone
exists to establish. They are read-clients of the vocabulary, never authors of it.

Idempotent both ways: `ON CONFLICT DO NOTHING` on the grants, and the permission rows
are created only when absent (a fresh deploy runs migrations before the app's registry
sync, so they may genuinely not be there yet).

Revision ID: 361_spec_registry_grant_sweep
Revises: 360_merge_container_status_spec
"""
import sqlalchemy as sa
from alembic import op

revision = "361_spec_registry_grant_sweep"
down_revision = "360_merge_container_status_spec"
branch_labels = None
depends_on = None


# (target registry slug, the products slug whose holders get it, name, description)
_SWEEP = (
    (
        "master_data.spec_registry.view",
        "master_data.products.view",
        "View Spec Registry",
        "Permission to view Spec Registry.",
    ),
    (
        "master_data.spec_registry.edit",
        "master_data.products.edit",
        "Edit Spec Registry",
        "Permission to edit Spec Registry.",
    ),
    (
        "master_data.spec_registry.add",
        "master_data.products.add",
        "Add Spec Registry",
        "Permission to add Spec Registry.",
    ),
)

# Matched with LIKE against `user_roles.slug`. API-key principals, never authors.
_EXCLUDED_ROLE_PREFIX = "integration\\_%"


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
                JOIN user_roles r ON r.id = rp.role_id
                CROSS JOIN user_permissions tgt
                WHERE tgt.slug = :target
                  AND r.slug NOT LIKE :excluded
                ON CONFLICT (role_id, permission_id) DO NOTHING
                """
            ),
            {"source": source, "target": target, "excluded": _EXCLUDED_ROLE_PREFIX},
        )


def downgrade() -> None:
    """Take the grants back, leaving the permission rows in place.

    The rows predate this migration - they were measured present and ungranted - so
    deleting them here would remove something this migration did not create.
    """
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM user_role_permissions
            WHERE permission_id IN (
                SELECT id FROM user_permissions WHERE slug = ANY(:slugs)
            )
            """
        ),
        {"slugs": [target for target, _s, _n, _d in _SWEEP]},
    )
