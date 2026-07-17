"""Postgres-backed TestClient fixtures for the SCM M1 route tests.

The dashboard endpoints read the ``scm`` schema views, which only exist on the
live Postgres DB — so these tests run against the local prod-copy (same source as
the M0 view/golden tests). Every test runs inside a nested SAVEPOINT joined to an
outer transaction: the route's own ``db.commit()`` releases the savepoint (a
restart listener re-opens one), and the whole thing is rolled back on teardown so
nothing (seeded users, created SOs/DOs) ever escapes to the shared DB.
"""
from __future__ import annotations

import os
import re
import uuid

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker


def _pg_url() -> str | None:
    # A live DATABASE_URL env var wins (CI / container). Fall back to the local
    # .env file, which is NOT shipped in the CI Docker image (.dockerignore) — so
    # its absence must never crash collection, only skip the Postgres route tests.
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        env = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        if not os.path.exists(env):
            return None
        with open(env) as fh:
            for line in fh:
                if line.startswith("DATABASE_URL"):
                    raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not raw:
        return None
    return re.sub(r"^postgresql\+\w+", "postgresql", raw)


URL = _pg_url()
requires_pg = pytest.mark.skipif(
    not URL or not URL.startswith("postgresql"),
    reason="SCM M1 route tests require a live Postgres DATABASE_URL",
)


@pytest.fixture()
def scm_app():
    """Yields (app, db, get_current_user, get_current_user_or_api_key).

    Everything the route writes lives in a rolled-back savepoint.
    """
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key

    engine = create_engine(URL)
    connection = engine.connect()
    trans = connection.begin()
    Session = sessionmaker(bind=connection)
    db = Session()
    db.begin_nested()

    @event.listens_for(db, "after_transaction_end")
    def _restart_savepoint(session, transaction):  # noqa: ANN001
        if transaction.nested and not transaction._parent.nested:
            session.begin_nested()

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    try:
        yield app, db, get_current_user, get_current_user_or_api_key
    finally:
        app.dependency_overrides.clear()
        event.remove(db, "after_transaction_end", _restart_savepoint)
        db.close()
        trans.rollback()
        connection.close()
        engine.dispose()


def seed_user(db, role_slug: str | None) -> str:
    """Create a user (rolled back) optionally assigned to an existing role."""
    from app.models.user import User, UserRoleAssignment

    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"scm-{uid}@test.com", name="SCM Test", status="ACTIVE"))
    db.flush()
    if role_slug:
        rid = db.execute(
            text("SELECT id FROM user_roles WHERE slug = :s"), {"s": role_slug}
        ).scalar()
        assert rid, f"role {role_slug} not seeded"
        db.add(UserRoleAssignment(user_id=uid, role_id=rid))
        db.flush()
    return uid


def as_user(app, get_current_user, get_current_user_or_api_key, uid: str) -> None:
    principal = {"id": uid, "email": f"scm-{uid}@test.com"}
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
