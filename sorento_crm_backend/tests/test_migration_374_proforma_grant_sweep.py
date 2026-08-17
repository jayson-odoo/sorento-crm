"""The proforma-invoice grant sweep - AC-P4.3, `PRINCIPLES.md` DoD gate 3.

A new permission that nobody holds is a feature that silently 403s, so migration 374 sweeps
`scm.proforma_invoice.upload` onto every role that already holds `scm.reorder.run` - whoever
runs the module's uploads today. This pins that sweep against the migration's own code rather
than against whatever grants the local database happens to carry.

Mirrors `test_migration_361_spec_registry_grant_sweep.py` with ONE deliberate difference: it
calls `grant_upload_permission()` rather than `upgrade()`. 374's `upgrade()` also creates
`scm.proforma_invoice` and its line table, and `op.create_table(..., schema="scm")` names the
real schema outright - `blank_session`'s schema translation does not reach it, so running the
whole body here would collide with the tables that already exist rather than test anything.
The grant sweep is the part with a rule in it; the DDL is asserted by every other proforma
suite simply by writing rows.

The exclusion is the assertion that matters: an `integration_*` role is an API-key principal
reading the module, never an operator uploading a supplier's document of record to it.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from tests._pg_fixture import blank_session

# Loaded by PATH, not by dotted name: `alembic/versions` has no `__init__.py`, so it is not
# an importable package, and the revision id starts with a digit besides.
_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "374_scm_proforma_invoice.py"
)

SOURCE_SLUG = "scm.reorder.run"
TARGET_SLUG = "scm.proforma_invoice.upload"


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_374", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _run_sweep(db) -> None:
    """Run the migration's grant sweep on this session's connection.

    Everything it writes is inside the transaction `blank_session` rolls back.
    """
    _migration_module().grant_upload_permission(db.connection())


@pytest.fixture
def db():
    with blank_session() as s:
        _permission(s, SOURCE_SLUG)
        yield s


def test_a_role_that_runs_the_reorder_gains_the_upload(db):
    role = _role(db, "zzt374_operator")
    _grant(db, role, SOURCE_SLUG)

    _run_sweep(db)

    assert TARGET_SLUG in _slugs_for(db, role)


def test_the_permission_itself_is_created_when_absent(db):
    assert (
        db.execute(
            text("SELECT count(*) FROM user_permissions WHERE slug = :s"),
            {"s": TARGET_SLUG},
        ).scalar()
        == 0
    )

    _run_sweep(db)

    assert (
        db.execute(
            text("SELECT count(*) FROM user_permissions WHERE slug = :s"),
            {"s": TARGET_SLUG},
        ).scalar()
        == 1
    )


def test_integration_roles_are_excluded(db):
    """An API-key principal writing supplier documents of record is not what it is for."""
    role = _role(db, "integration_n8n")
    _grant(db, role, SOURCE_SLUG)

    _run_sweep(db)

    assert TARGET_SLUG not in _slugs_for(db, role)


def test_every_integration_role_is_excluded_not_just_n8n(db):
    for slug in ("integration_sorento_mcp", "integration_foundryx_esb"):
        role = _role(db, slug)
        _grant(db, role, SOURCE_SLUG)

        _run_sweep(db)

        assert TARGET_SLUG not in _slugs_for(db, role)


def test_a_role_holding_no_reorder_permission_gains_nothing(db):
    role = _role(db, "zzt374_outsider")

    _run_sweep(db)

    assert _slugs_for(db, role) == set()


def test_running_it_twice_changes_nothing(db):
    role = _role(db, "zzt374_idempotent")
    _grant(db, role, SOURCE_SLUG)

    _run_sweep(db)
    first = _slugs_for(db, role)
    _run_sweep(db)

    assert _slugs_for(db, role) == first
    # And not as duplicate rows under one slug, which the set above would hide.
    count = db.execute(
        text("SELECT count(*) FROM user_role_permissions WHERE role_id = :role"),
        {"role": role},
    ).scalar()
    assert count == len(first)


def test_the_permission_is_also_in_the_registry_so_a_fresh_database_has_it():
    """CI builds a database with `create_all` + a registry sync and never runs a migration
    body, so a permission that exists only in the sweep would not exist there at all."""
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    assert TARGET_SLUG in {entry["slug"] for entry in PERMISSION_REGISTRY}
