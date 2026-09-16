"""S5 config routes commit finding (coordinator directive, 16 Sep 2026, "finding 5" -
blocks the owner's hand pass and every S5 save, ordered ahead of everything else this
session).

**Measured on the hand-pass clone**: `app/api/v1/system/chatbot_config.py` has 6
`db.flush()` calls across its six write routes (domains POST/PUT/DELETE, entity-kinds
POST/PUT) and ZERO `db.commit()`. `app/dependencies.py::get_db` never commits either -
it only `yield`s and closes in a `finally`. A save through either surface therefore
rolls back the moment the request's session closes: `PUT /system/chatbot/domains/
db74d044...` on the clone returned 200 twice in a row with the row's own narrowing and
`updated_at` unchanged, because nothing was ever durably written. The SAME shape exists
in `contacts.py`'s `PUT /{id}/chatbot` (the recall toggle today; the new stock-allowed
toggle would inherit the same defect - see `test_rearch_s6_stock_allowed.py`, same
session, whose PUT tests do NOT catch this).

**Why `test_rearch_s5_config_routes.py`'s own route tests did not catch this**: its
`client` fixture's `get_db` override hands the FastAPI request the SAME `pg_db` session
the test itself holds, so a read-back after the PUT sees the flushed-but-uncommitted
row through that one session's own identity map - it looks durable and is not.

**Why this file spies on `.commit()` rather than opening a second session to read
back**: `tests/_pg_fixture.py::pg_session`'s own docstring - "everything runs inside
one outer transaction that is rolled back at teardown, so `begin_nested()` becomes a
real nested savepoint" - means a route's `db.commit()` under this fixture releases a
SAVEPOINT on the SAME connection, not a real cross-connection commit; nothing this
fixture ever does is visible to a genuinely independent second connection regardless of
whether the route commits. A commit-call-count spy is therefore the correct probe for
"did this route try to persist", not a red herring around the fixture's own isolation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.main import app
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.access import McpTool
from app.services.user_service import UserPermissionService

from tests._pg_fixture import pg_session, unique_code
from tests.chatbot.test_rearch_s5_config_routes import _domain_body, _kind_body

VIEW = "system.chat_history.view"
MANAGE = "system.chatbot_config.manage"
DOMAINS_BASE = "/api/v1/system/chatbot/domains"
ENTITY_KINDS_BASE = "/api/v1/system/chatbot/entity-kinds"
CONTACT_CHATBOT_BASE = "/api/v1/user-management/contacts"

_GRANTS: set[str] = set()
_ACTOR: dict = {"id": None, "name": "ZZT Config Commit Tester"}


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    _GRANTS.clear()
    _GRANTS.add(VIEW)
    _GRANTS.add(MANAGE)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in _GRANTS,
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield
    _GRANTS.clear()


@pytest.fixture()
def pg_db():
    with pg_session() as db:
        yield db


@pytest.fixture()
def commit_spy(pg_db, monkeypatch):
    """Wraps the REQUEST session's own `.commit` with a counter, the real method still
    called underneath (so a route that DOES commit still behaves normally under the
    savepoint semantics `pg_session` sets up)."""
    calls = {"n": 0}
    real_commit = pg_db.commit

    def _spy():
        calls["n"] += 1
        return real_commit()

    monkeypatch.setattr(pg_db, "commit", _spy)
    return calls


@pytest.fixture()
def client(pg_db):
    def _override_db():
        try:
            yield pg_db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    _ACTOR["id"] = str(uuid.uuid4())
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def real_tool_name(pg_db) -> str:
    row = pg_db.execute(McpTool.__table__.select().limit(1)).first()
    if row is not None:
        return row.tool_name
    name = unique_code("tool")
    pg_db.add(
        McpTool(
            tool_name=name,
            description="ZZT scratch tool",
            http_path="/api/v1/zzt/scratch",
            http_method="GET",
            is_active=True,
            last_seen_at=datetime.now(timezone.utc),
        )
    )
    pg_db.flush()
    return name


def _seed_domain(pg_db, *, tool: str) -> str:
    resp_body = _domain_body(unique_code("domain"), tool=tool)
    from app.models.chatbot_policy import ChatbotDomain

    row = ChatbotDomain(**resp_body)
    pg_db.add(row)
    pg_db.flush()
    return str(row.id)


def _seed_kind(pg_db) -> str:
    from app.models.chatbot_policy import ChatbotEntityKind

    kind = unique_code("kind")
    values = _kind_body(kind)
    # `label` defaults from `kind` only inside the POST route (chatbot_config.py:326) -
    # seeding the ORM row directly bypasses that, so the NOT NULL column needs it here.
    values["label"] = kind.replace("_", " ").title()
    row = ChatbotEntityKind(**values, sort_order=0)
    pg_db.add(row)
    pg_db.flush()
    return row.kind


def _seed_contact(pg_db) -> str:
    cid = unique_code("contact")
    pg_db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST('{}' AS jsonb))"
        ),
        {"cid": cid, "phone": f"+60{uuid.uuid4().int % 10**9}"},
    )
    pg_db.flush()
    return pg_db.execute(
        text("SELECT id FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": cid}
    ).scalar()


class TestChatbotDomainsRoutesCommit:
    def test_create_domain_commits_exactly_once(self, client, pg_db, commit_spy, real_tool_name) -> None:
        resp = client.post(DOMAINS_BASE, json=_domain_body(unique_code("domain"), tool=real_tool_name))
        assert resp.status_code == 201, resp.text
        assert commit_spy["n"] == 1, (
            f"POST {DOMAINS_BASE} flushed but never committed - commit() called "
            f"{commit_spy['n']} time(s), expected 1. A flush-only write is discarded "
            "the moment the request's session closes (get_db never commits either)."
        )

    def test_update_domain_commits_exactly_once(self, client, pg_db, commit_spy, real_tool_name) -> None:
        domain_id = _seed_domain(pg_db, tool=real_tool_name)
        commit_spy["n"] = 0  # ignore the seed's own writes
        resp = client.put(f"{DOMAINS_BASE}/{domain_id}", json=_domain_body(unique_code("domain"), tool=real_tool_name))
        assert resp.status_code == 200, resp.text
        assert commit_spy["n"] == 1, commit_spy["n"]

    def test_delete_domain_commits_exactly_once(self, client, pg_db, commit_spy, real_tool_name) -> None:
        domain_id = _seed_domain(pg_db, tool=real_tool_name)
        commit_spy["n"] = 0
        resp = client.delete(f"{DOMAINS_BASE}/{domain_id}")
        assert resp.status_code == 204, resp.text
        assert commit_spy["n"] == 1, commit_spy["n"]

    def test_a_failing_create_never_commits(self, client, commit_spy) -> None:
        resp = client.post(
            DOMAINS_BASE, json=_domain_body(unique_code("domain"), tool="zzt-not-a-real-tool-name")
        )
        assert resp.status_code == 422, resp.text
        assert commit_spy["n"] == 0, (
            f"a rejected (422) create must never commit; commit() called {commit_spy['n']} time(s)"
        )


class TestChatbotEntityKindsRoutesCommit:
    def test_create_entity_kind_commits_exactly_once(self, client, pg_db, commit_spy) -> None:
        resp = client.post(ENTITY_KINDS_BASE, json=_kind_body(unique_code("kind")))
        assert resp.status_code == 201, resp.text
        assert commit_spy["n"] == 1, commit_spy["n"]

    def test_update_entity_kind_commits_exactly_once(self, client, pg_db, commit_spy) -> None:
        kind = _seed_kind(pg_db)
        commit_spy["n"] = 0
        resp = client.put(f"{ENTITY_KINDS_BASE}/{kind}", json=_kind_body(kind))
        assert resp.status_code == 200, resp.text
        assert commit_spy["n"] == 1, commit_spy["n"]


class TestContactChatbotRouteCommit:
    def test_put_contact_chatbot_commits_exactly_once(self, client, pg_db, commit_spy) -> None:
        contact_id = _seed_contact(pg_db)
        commit_spy["n"] = 0
        resp = client.put(
            f"{CONTACT_CHATBOT_BASE}/{contact_id}/chatbot",
            json={"chatbot_recall_enabled": True},
        )
        assert resp.status_code == 200, resp.text
        assert commit_spy["n"] == 1, (
            f"PUT {CONTACT_CHATBOT_BASE}/{{id}}/chatbot flushed but never committed - "
            f"commit() called {commit_spy['n']} time(s), expected 1. The new stock-"
            "allowed toggle (test_rearch_s6_stock_allowed.py) inherits this same "
            "defect if it lands on the same route body without a fix here."
        )
