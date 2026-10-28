"""unpaid_0001: the chatbot integration's act-as user gets a dedicated role holding only
`finance.billing_documents.view`, so `basis=unpaid` on the chatbot report ask (which needs the slug on the act-as user)
keeps working. Additive and idempotent; downgrade removes the assignment and the role.

Postgres only (`tests/_pg_fixture.py`)."""

from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.user import User
from tests._migration_imports import app_imports
from tests._pg_fixture import blank_session

SLUG = "finance.billing_documents.view"
ROLE_SLUG = "chatbot_integration_unpaid_read"
_MIGRATION = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions" / "unpaid_0001_chatbot_ar_role.py"


def _load():
    spec = importlib.util.spec_from_file_location("migration_unpaid_0001", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, fn: str) -> None:
    module = _load()
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        getattr(module, fn)()


def _user(db, label: str) -> str:
    row = User(id=str(uuid.uuid4()), email=f"zzt-{label}-{uuid.uuid4().hex[:8]}@integrations.local", name=f"ZZT {label}", is_integration=True)
    db.add(row)
    db.flush()
    return row.id


def _integration(db, name: str, act_as: str | None) -> None:
    db.execute(
        text("INSERT INTO integrations (id, name, type, act_as_user_id) VALUES (:i, :n, 'automation', :u)"),
        {"i": str(uuid.uuid4()), "n": name, "u": act_as},
    )


def _holders(db) -> set[str]:
    rows = db.execute(
        text(
            "SELECT a.user_id FROM user_role_assignments a "
            "JOIN user_role_permissions rp ON rp.role_id = a.role_id "
            "JOIN user_permissions p ON p.id = rp.permission_id WHERE p.slug = :s"
        ),
        {"s": SLUG},
    ).all()
    return {r[0] for r in rows}


@pytest.fixture()
def seeded():
    with blank_session() as db:
        db.execute(text("DELETE FROM integrations"))
        n8n = _user(db, "n8n")
        mcp = _user(db, "mcp")
        other = _user(db, "other")
        _integration(db, "n8n", n8n)
        _integration(db, "sorento-mcp", mcp)
        _integration(db, "foundryx-esb", other)
        db.flush()
        yield db, n8n, mcp, other


def test_the_chatbot_act_as_users_hold_the_slug_after_upgrade_and_nobody_else_gained_it(seeded):
    db, n8n, mcp, other = seeded
    before = _holders(db)
    _run(db, "upgrade")
    assert _holders(db) - before == {n8n, mcp}
    assert other not in _holders(db)


def test_the_role_holds_only_the_one_slug(seeded):
    db, *_ = seeded
    _run(db, "upgrade")
    slugs = {
        r[0]
        for r in db.execute(
            text(
                "SELECT p.slug FROM user_roles r JOIN user_role_permissions rp ON rp.role_id = r.id "
                "JOIN user_permissions p ON p.id = rp.permission_id WHERE r.slug = :s"
            ),
            {"s": ROLE_SLUG},
        )
    }
    assert slugs == {SLUG}


def test_upgrade_twice_changes_nothing(seeded):
    db, *_ = seeded
    _run(db, "upgrade")
    counts = lambda: (  # noqa: E731
        db.execute(text("SELECT count(*) FROM user_roles WHERE slug = :s"), {"s": ROLE_SLUG}).scalar(),
        db.execute(text("SELECT count(*) FROM user_permissions WHERE slug = :s"), {"s": SLUG}).scalar(),
        len(_holders(db)),
        db.execute(text("SELECT count(*) FROM user_role_assignments")).scalar(),
    )
    first = counts()
    _run(db, "upgrade")
    assert counts() == first


def test_no_integration_or_no_act_as_user_is_a_no_op():
    with blank_session() as db:
        db.execute(text("DELETE FROM integrations"))
        _integration(db, "n8n", None)
        db.flush()
        before = db.execute(text("SELECT count(*) FROM user_role_assignments")).scalar()
        _run(db, "upgrade")
        assert db.execute(text("SELECT count(*) FROM user_role_assignments")).scalar() == before


def test_downgrade_removes_the_assignment_and_the_role(seeded):
    db, n8n, mcp, other = seeded
    before = _holders(db)
    _run(db, "upgrade")
    _run(db, "downgrade")
    assert _holders(db) == before
    assert db.execute(text("SELECT count(*) FROM user_roles WHERE slug = :s"), {"s": ROLE_SLUG}).scalar() == 0


def test_migration_imports_no_application_code():
    assert app_imports(_MIGRATION) == []
