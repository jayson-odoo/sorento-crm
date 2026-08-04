"""Migration 311's grant sweep, exercised rather than assumed.

Splitting a permission is only safe if the sweep is right: every role that can decide
today must keep deciding, or approvers silently lose their Approve/Reject buttons on
deploy. Asserting against the live database would only prove what this environment
happens to hold, so the migration's own ``upgrade()`` runs here against a blank schema
inside a transaction that is rolled back.
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

from ._pg_fixture import blank_session

APPROVE = "procurement.purchase_requests.approve"
TRIAGE = "procurement.purchase_requests.send_for_approval"

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "311_split_pr_approve_permission.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_311", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _permission(db, slug: str) -> str:
    """Seeded through the ORM so the models' defaults fill every NOT NULL column."""
    row = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug)
    db.add(row)
    db.flush()
    return row.id


def _role(db, name: str) -> str:
    row = UserRole(id=str(uuid.uuid4()), slug=f"zzt-{uuid.uuid4().hex[:10]}", name=name, is_trashed=False)
    db.add(row)
    db.flush()
    return row.id


def _grant(db, role_id: str, permission_id: str) -> None:
    db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role_id, permission_id=permission_id))
    db.flush()


def _holds(db, role_id: str, slug: str) -> bool:
    return bool(
        db.execute(
            text(
                "SELECT 1 FROM user_role_permissions urp "
                "JOIN user_permissions p ON p.id = urp.permission_id "
                "WHERE urp.role_id = :r AND p.slug = :slug"
            ),
            {"r": role_id, "slug": slug},
        ).first()
    )


def _run_upgrade(db) -> None:
    module = _load_migration()
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        module.upgrade()


@pytest.fixture()
def seeded():
    """A blank schema holding one approver role, one unrelated role, and the two
    sales-admin role names the migration targets."""
    with blank_session() as db:
        triage_perm = _permission(db, TRIAGE)
        approver = _role(db, f"ZZT Approver {uuid.uuid4().hex[:6]}")
        _grant(db, approver, triage_perm)
        bystander = _role(db, f"ZZT Bystander {uuid.uuid4().hex[:6]}")
        psm = _role(db, "Project Sales Manager")
        psc = _role(db, "Project Sales Coordinator")
        db.flush()
        yield db, {"approver": approver, "bystander": bystander, "psm": psm, "psc": psc}


def test_the_new_permission_is_created(seeded):
    db, _ = seeded
    _run_upgrade(db)
    assert db.execute(
        text("SELECT 1 FROM user_permissions WHERE slug = :s"), {"s": APPROVE}
    ).first(), "the approve permission was not seeded"


def test_todays_approvers_keep_deciding(seeded):
    """The sweep that stops approvers losing their buttons on deploy."""
    db, roles = seeded
    _run_upgrade(db)
    assert _holds(db, roles["approver"], APPROVE)


def test_an_unrelated_role_gains_nothing(seeded):
    db, roles = seeded
    _run_upgrade(db)
    assert not _holds(db, roles["bystander"], APPROVE)
    assert not _holds(db, roles["bystander"], TRIAGE)


def test_sales_admin_roles_gain_triage_but_not_the_decision(seeded):
    """Hasni is Project Sales Manager locally and Project Sales Coordinator in prod, so
    both names are targeted - and neither becomes an approver."""
    db, roles = seeded
    _run_upgrade(db)
    for key in ("psm", "psc"):
        assert _holds(db, roles[key], TRIAGE), f"{key} did not gain triage"
        assert not _holds(db, roles[key], APPROVE), f"{key} wrongly became an approver"


def test_running_twice_changes_nothing(seeded):
    """Re-running must not double-grant - the shared dev database gets migrations
    replayed across worktrees."""
    db, roles = seeded
    _run_upgrade(db)
    _run_upgrade(db)
    count = db.execute(
        text(
            "SELECT count(*) FROM user_role_permissions urp "
            "JOIN user_permissions p ON p.id = urp.permission_id "
            "WHERE urp.role_id = :r AND p.slug = :s"
        ),
        {"r": roles["approver"], "s": APPROVE},
    ).scalar()
    assert count == 1, f"expected one grant, found {count}"
