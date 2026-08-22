"""The spec-registry grant sweep - AC-A.13, `PRINCIPLES.md` DoD gate 3.

The migration's `upgrade()` is imported and run inside a rolled-back transaction against
a blank schema, so what is under test is the CODE rather than whatever the local
database happens to hold. CI's database is empty and every role here is seeded by the
test with a `zzt_` marker.

The exclusion is the assertion that matters: an `integration_*` role holding
`master_data.products.add` must NOT come out of this holding `spec_registry.add`.
Granting a machine the right to mint vocabulary keys inverts the one-source-of-truth
guarantee the whole milestone exists to establish, and it would be invisible - the n8n
parser would simply start succeeding at something nobody meant to allow.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from tests._pg_fixture import blank_session

# Loaded by PATH, not by dotted name: `alembic/versions` has no `__init__.py`, so it is
# not an importable package, and the revision id starts with a digit besides.
_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "361_spec_registry_grant_sweep.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "zzt_migration_361", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

_PRODUCT_SLUGS = (
    "master_data.products.view",
    "master_data.products.add",
    "master_data.products.edit",
)
_REGISTRY_SLUGS = (
    "master_data.spec_registry.view",
    "master_data.spec_registry.add",
    "master_data.spec_registry.edit",
    "master_data.spec_registry.delete",
)


def _permission(db, slug: str) -> str:
    from app.models.user import UserPermission

    row = db.query(UserPermission).filter_by(slug=slug).first()
    if row is None:
        row = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
        db.add(row)
        db.flush()
    return row.id


def _role(db, slug: str) -> str:
    from app.models.user import UserRole

    row = UserRole(
        id=str(uuid.uuid4()),
        slug=slug,
        name=slug,
        description="",
        is_protected=False,
        is_default=False,
    )
    db.add(row)
    db.flush()
    return row.id


def _grant(db, role_id: str, slug: str) -> None:
    from app.models.user import UserRolePermission

    db.add(
        UserRolePermission(
            id=str(uuid.uuid4()), role_id=role_id, permission_id=_permission(db, slug)
        )
    )
    db.flush()


def _slugs_for(db, role_id: str) -> set[str]:
    rows = db.execute(
        text(
            """
            SELECT p.slug
            FROM user_role_permissions rp
            JOIN user_permissions p ON p.id = rp.permission_id
            WHERE rp.role_id = :role
            """
        ),
        {"role": role_id},
    ).all()
    return {row[0] for row in rows}


def _run_upgrade(db) -> None:
    """Run the migration body against this session's connection.

    `op.get_bind()` needs a MigrationContext, so one is built over the test's own
    connection - everything it writes is inside the transaction blank_session rolls
    back.
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        module.upgrade()


@pytest.fixture
def db():
    with blank_session() as s:
        for slug in (*_PRODUCT_SLUGS, *_REGISTRY_SLUGS):
            _permission(s, slug)
        yield s


def test_a_product_viewer_gains_the_registry_view(db):
    role = _role(db, "zzt_sweep_viewer")
    _grant(db, role, "master_data.products.view")

    _run_upgrade(db)

    assert "master_data.spec_registry.view" in _slugs_for(db, role)


def test_a_product_editor_gains_the_registry_edit(db):
    role = _role(db, "zzt_sweep_editor")
    _grant(db, role, "master_data.products.edit")

    _run_upgrade(db)

    assert "master_data.spec_registry.edit" in _slugs_for(db, role)


def test_a_product_adder_gains_the_registry_add(db):
    role = _role(db, "zzt_sweep_adder")
    _grant(db, role, "master_data.products.add")

    _run_upgrade(db)

    assert "master_data.spec_registry.add" in _slugs_for(db, role)


def test_each_grant_follows_its_own_source_slug(db):
    """A role that may only READ products must not come out able to EDIT the registry."""
    role = _role(db, "zzt_sweep_readonly")
    _grant(db, role, "master_data.products.view")

    _run_upgrade(db)

    slugs = _slugs_for(db, role)
    assert "master_data.spec_registry.view" in slugs
    assert "master_data.spec_registry.edit" not in slugs
    assert "master_data.spec_registry.add" not in slugs


def test_delete_is_never_granted(db):
    role = _role(db, "zzt_sweep_everything")
    for slug in _PRODUCT_SLUGS:
        _grant(db, role, slug)

    _run_upgrade(db)

    assert "master_data.spec_registry.delete" not in _slugs_for(db, role)


def test_integration_roles_are_excluded(db):
    """An API-key principal minting vocabulary keys inverts the whole milestone."""
    role = _role(db, "integration_n8n")
    for slug in _PRODUCT_SLUGS:
        _grant(db, role, slug)

    _run_upgrade(db)

    assert _slugs_for(db, role) & set(_REGISTRY_SLUGS) == set()


def test_every_integration_role_is_excluded_not_just_n8n(db):
    for slug in ("integration_sorento_mcp", "integration_foundryx_esb"):
        role = _role(db, slug)
        _grant(db, role, "master_data.products.view")

        _run_upgrade(db)

        assert _slugs_for(db, role) & set(_REGISTRY_SLUGS) == set()


def test_a_role_holding_no_product_permission_gains_nothing(db):
    role = _role(db, "zzt_sweep_outsider")

    _run_upgrade(db)

    assert _slugs_for(db, role) == set()


def test_running_it_twice_changes_nothing(db):
    role = _role(db, "zzt_sweep_idempotent")
    _grant(db, role, "master_data.products.view")

    _run_upgrade(db)
    first = _slugs_for(db, role)
    _run_upgrade(db)

    assert _slugs_for(db, role) == first
    # And not as duplicate rows under one slug, which the set above would hide.
    count = db.execute(
        text("SELECT count(*) FROM user_role_permissions WHERE role_id = :role"),
        {"role": role},
    ).scalar()
    assert count == len(first)


def test_downgrade_takes_the_grants_back_and_leaves_the_permissions(db):
    role = _role(db, "zzt_sweep_reversible")
    _grant(db, role, "master_data.products.view")
    _run_upgrade(db)

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        module.downgrade()

    assert "master_data.spec_registry.view" not in _slugs_for(db, role)
    # The rows predate this migration; removing them would delete what it never made.
    remaining = db.execute(
        text("SELECT count(*) FROM user_permissions WHERE slug = :slug"),
        {"slug": "master_data.spec_registry.view"},
    ).scalar()
    assert remaining == 1
