"""PORTAL-P2-ONLY-THEIRS UAC 8: five `view_own` slugs, one migration, granted to no role."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import text

from app.rbac.permission_registry import PERMISSION_REGISTRY
from app.services import own_scope

from ._pg_fixture import blank_session

SLUGS = {
    own_scope.PROJECTS_VIEW_OWN,
    own_scope.OPPORTUNITIES_VIEW_OWN,
    own_scope.SAMPLE_REQUESTS_VIEW_OWN,
    own_scope.NPA_VIEW_OWN,
    own_scope.CONVERSATIONS_VIEW_OWN,
}


def _migration():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "pp2_0001_view_own_perms.py"
    spec = importlib.util.spec_from_file_location("pp2_0001_view_own_perms", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_registry_and_the_migration_declare_the_same_five_slugs():
    registry = {entry["slug"]: entry for entry in PERMISSION_REGISTRY if entry["slug"] in SLUGS}
    assert set(registry) == SLUGS
    migration = {slug: (name, descr) for slug, name, descr in _migration()._PERMS}
    assert set(migration) == SLUGS
    for slug, (name, descr) in migration.items():
        assert registry[slug]["name"] == name
        assert registry[slug]["description"] == descr


def test_no_role_holds_a_view_own_slug():
    """P2 grants nothing: the slugs exist, no role carries them (P3 grants)."""
    with blank_session() as db:
        held = db.execute(
            text(
                "select count(*) from user_role_permissions urp "
                "join user_permissions p on p.id = urp.permission_id where p.slug = any(:s)"
            ),
            {"s": list(SLUGS)},
        ).scalar()
        assert held == 0
