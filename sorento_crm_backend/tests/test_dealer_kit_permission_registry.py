"""Dealer Kit permission registry parity (Slice 2, module-access-gates plan).

Asserts that the six ``dealer_kit.*`` slugs seeded by migration 309 are also
declared in ``PERMISSION_REGISTRY``, so that ``sync_permissions`` (the
create_all/CI path) and the migration (the alembic-upgrade path) agree on
which slugs exist.
"""
from app.rbac.permission_registry import PERMISSION_REGISTRY

# The six slugs from migration 309 lines 47-53, in the exact same order and
# with the exact same labels.
_MIGRATION_309_PERMS = [
    ("dealer_kit.page.view", "View catalogue pages"),
    ("dealer_kit.page.edit", "Edit catalogue pages"),
    ("dealer_kit.page.publish", "Publish catalogue pages"),
    ("dealer_kit.library.manage", "Manage Dealer Kit library"),
    ("dealer_kit.brochure.create", "Create brochures"),
    ("dealer_kit.edition.approve", "Approve catalogue editions"),
]


def test_dealer_kit_slugs_registered():
    """Every slug migration 309 seeds must appear in PERMISSION_REGISTRY."""
    registry_slugs = {entry["slug"] for entry in PERMISSION_REGISTRY}
    for slug, _name in _MIGRATION_309_PERMS:
        assert slug in registry_slugs, f"{slug} missing from PERMISSION_REGISTRY"


def test_dealer_kit_slug_names_match_migration():
    """The human-readable name in the registry must match what migration 309 seeds."""
    registry_by_slug = {entry["slug"]: entry["name"] for entry in PERMISSION_REGISTRY}
    for slug, name in _MIGRATION_309_PERMS:
        assert registry_by_slug.get(slug) == name, (
            f"{slug}: registry has {registry_by_slug.get(slug)!r}, migration 309 has {name!r}"
        )
