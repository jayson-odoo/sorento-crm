"""Migration adp_0001 grants `resource.attachments.delete` to `project.customer.service`.

Owner ruling 20 Oct 2026 (ATTACH-DELETE-PERM): single attachment delete now requires the slug,
and project customer service keeps deleting project documents by holding it. The migration's
own ``upgrade()`` / ``downgrade()`` run here against a blank schema inside a transaction that
is rolled back, so nothing depends on what the shared database happens to hold.
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.user import UserPermission, UserRole, UserRolePermission

from ._migration_imports import app_imports
from ._pg_fixture import blank_session

ROLE = "project.customer.service"
SLUG = "resource.attachments.delete"

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "adp_0001_pcs_attach_delete.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_adp_0001", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, step: str) -> None:
    module = _load_migration()
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        getattr(module, step)()


def _permission(db, slug: str) -> str:
    row = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug)
    db.add(row)
    db.flush()
    return row.id


def _role(db, slug: str) -> str:
    row = UserRole(id=str(uuid.uuid4()), slug=slug, name=f"ZZT {slug}", is_trashed=False)
    db.add(row)
    db.flush()
    return row.id


def _links(db, role_id: str, slug: str) -> int:
    return db.execute(
        text(
            "SELECT count(*) FROM user_role_permissions urp "
            "JOIN user_permissions p ON p.id = urp.permission_id "
            "WHERE urp.role_id = :r AND p.slug = :slug"
        ),
        {"r": role_id, "slug": slug},
    ).scalar_one()


@pytest.fixture()
def seeded():
    """A blank schema holding the target role, a bystander role and the permission."""
    with blank_session() as db:
        perm_id = _permission(db, SLUG)
        pcs = _role(db, ROLE)
        bystander = _role(db, f"zzt-{uuid.uuid4().hex[:10]}")
        yield db, {"perm": perm_id, "pcs": pcs, "bystander": bystander}


def test_upgrade_grants_the_role(seeded):
    db, ids = seeded
    _run(db, "upgrade")
    assert _links(db, ids["pcs"], SLUG) == 1


def test_rerun_adds_no_duplicate(seeded):
    db, ids = seeded
    _run(db, "upgrade")
    _run(db, "upgrade")
    assert _links(db, ids["pcs"], SLUG) == 1


def test_existing_link_is_left_alone(seeded):
    db, ids = seeded
    db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=ids["pcs"], permission_id=ids["perm"]))
    db.flush()
    _run(db, "upgrade")
    assert _links(db, ids["pcs"], SLUG) == 1


def test_bystander_gains_nothing(seeded):
    db, ids = seeded
    _run(db, "upgrade")
    assert _links(db, ids["bystander"], SLUG) == 0


def test_downgrade_removes_only_that_link(seeded):
    db, ids = seeded
    other_perm = _permission(db, "resource.attachments.view")
    db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=ids["pcs"], permission_id=other_perm))
    db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=ids["bystander"], permission_id=ids["perm"]))
    db.flush()
    _run(db, "upgrade")
    _run(db, "downgrade")
    assert _links(db, ids["pcs"], SLUG) == 0
    assert _links(db, ids["pcs"], "resource.attachments.view") == 1
    assert _links(db, ids["bystander"], SLUG) == 1


def test_missing_role_or_permission_is_a_no_op():
    with blank_session() as db:
        _run(db, "upgrade")
        _run(db, "downgrade")
        assert db.execute(text("SELECT count(*) FROM user_role_permissions")).scalar_one() == 0


def test_migration_imports_no_application_code():
    assert app_imports(_MIGRATION) == []
