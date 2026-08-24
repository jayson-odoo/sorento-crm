"""The one decision a user makes about message pushes: `users.notify_push_message_scope`.

UAC: documentation/plans/notifications/message-push-acceptance-criteria.md
     AC-M25 (the self-service route persists it, 422 on anything outside the four)
     AC-M26 (BOTH manual dict builders return it, or the select renders its default forever)
     AC-M27 (existing rows get `assigned_and_coverage` from the server default, no backfill)

AC-M26 is the whole reason this file exists. `UserResponse` inherits the field from
`UserBase` the moment the schema declares it, so a test that only round-trips the
schema passes while the FE still never sees the value - `get_user` and `get_me` each
build a manual dict and silently drop anything not listed in it.

AC-M27 is asserted by RUNNING the migration over a pre-migration row, not by reading
the live database: CI's database is empty, so "some user exists and reads
assigned_and_coverage" proves nothing there.

Run:
    venv/bin/pytest tests/test_message_push_scope_preference.py -q
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.user import User
from app.services.user_service import UserPermissionService
from tests._pg_fixture import TEST_PREFIX, blank_session

CHANNELS = "/api/v1/notifications/preferences/channels"
USERS = "/api/v1/user-management/users"

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "411_notify_push_message_scope.py"
)

_ACTOR: dict = {"id": None, "name": f"{TEST_PREFIX} Actor"}


@pytest.fixture
def db(monkeypatch):
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    """Every permission granted: this file is about the column, not the gate."""
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: True,
    )
    monkeypatch.setattr(
        UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"}
    )


@pytest.fixture
def client(db):
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _user(db) -> str:
    uid = str(uuid.uuid4())
    db.add(
        User(
            id=uid,
            email=f"{TEST_PREFIX.lower()}-{uid[:8]}@test.invalid",
            name=f"{TEST_PREFIX} Scope User",
            status="ACTIVE",
        )
    )
    db.commit()
    _ACTOR["id"] = uid
    return uid


# --------------------------------------------------------------------------- #
# AC-M25 - the route persists it, and rejects anything else with 422           #
# --------------------------------------------------------------------------- #


def test_default_is_assigned_and_coverage(client, db):
    _user(db)

    body = client.get(CHANNELS).json()

    assert body["notify_push_message_scope"] == "assigned_and_coverage"


@pytest.mark.parametrize(
    "scope", ["assigned_and_coverage", "assigned_only", "all_contacts", "off"]
)
def test_each_allowed_scope_persists(client, db, scope):
    _user(db)

    saved = client.patch(CHANNELS, json={"notify_push_message_scope": scope})

    assert saved.status_code == 200
    assert saved.json()["notify_push_message_scope"] == scope
    assert client.get(CHANNELS).json()["notify_push_message_scope"] == scope


def test_an_unknown_scope_is_rejected_with_422(client, db):
    user_id = _user(db)
    client.patch(CHANNELS, json={"notify_push_message_scope": "all_contacts"})

    rejected = client.patch(CHANNELS, json={"notify_push_message_scope": "everything"})

    assert rejected.status_code == 422
    db.expire_all()
    assert (
        db.query(User).filter(User.id == user_id).one().notify_push_message_scope
        == "all_contacts"
    )


def test_omitting_the_scope_leaves_it_alone(client, db):
    _user(db)
    client.patch(CHANNELS, json={"notify_push_message_scope": "off"})

    client.patch(CHANNELS, json={"notify_whatsapp": True})

    assert client.get(CHANNELS).json()["notify_push_message_scope"] == "off"


# --------------------------------------------------------------------------- #
# AC-M26 - BOTH manual dict builders carry it                                  #
# --------------------------------------------------------------------------- #


def test_get_me_returns_the_saved_scope(client, db):
    _user(db)
    client.patch(CHANNELS, json={"notify_push_message_scope": "all_contacts"})

    me = client.get(f"{USERS}/me")

    assert me.status_code == 200
    assert me.json()["notify_push_message_scope"] == "all_contacts"


def test_get_user_returns_the_saved_scope(client, db):
    user_id = _user(db)
    client.patch(CHANNELS, json={"notify_push_message_scope": "assigned_only"})

    fetched = client.get(f"{USERS}/{user_id}")

    assert fetched.status_code == 200
    assert fetched.json()["notify_push_message_scope"] == "assigned_only"


# --------------------------------------------------------------------------- #
# AC-M27 - the server default IS the backfill                                  #
# --------------------------------------------------------------------------- #


def _load_migration():
    spec = importlib.util.spec_from_file_location("m411", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_pre_migration_user_comes_out_assigned_and_coverage():
    """Run the migration over a row that predates the column - no backfill script."""
    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        # Seeded through the ORM and only THEN rewound to the pre-migration shape:
        # a raw INSERT skips every Python-side model default (`is_trashed` is NOT
        # NULL with no server default) and dies on a constraint that has nothing to
        # do with what is under test.
        legacy_id = str(uuid.uuid4())
        session.add(
            User(
                id=legacy_id,
                email=f"{TEST_PREFIX.lower()}-legacy-{legacy_id[:8]}@test.invalid",
                name=f"{TEST_PREFIX} Legacy",
                status="ACTIVE",
            )
        )
        session.commit()
        session.execute(
            text("ALTER TABLE users DROP COLUMN IF EXISTS notify_push_message_scope")
        )

        module = _load_migration()
        ctx = MigrationContext.configure(session.connection())
        with Operations.context(ctx):
            module.upgrade()

        assert (
            session.execute(
                text(
                    "SELECT notify_push_message_scope FROM users WHERE id = :i"
                ),
                {"i": legacy_id},
            ).scalar()
            == "assigned_and_coverage"
        )
