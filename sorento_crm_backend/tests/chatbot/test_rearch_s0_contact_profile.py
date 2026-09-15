"""S0 - `respond_contacts.chatbot_profile` + `chatbot_recall_enabled` (AC-1503,
PLAN-chatbot-turn-rearch.md).

Column additions to an existing model, not migration-seeded reference DATA, so this
runs on the ordinary blank scratch schema (`Base.metadata.create_all`) like every other
`tests/chatbot/` API test - once the coder adds the columns to `RespondContact`,
`create_all` picks them up for free. Contrast with `test_rearch_s0_domains_seed.py` /
`test_rearch_s0_entity_kinds_seed.py`, which need the real migrated DB because their
rows are seeded inside a migration body.

RIGHT NOW every test here is RED: the columns do not exist on `RespondContact`, and
`RespondContactResponse` / `RespondContactUpdate` do not declare the two fields, so the
API never emits or accepts them (`response_model` silently drops anything undeclared -
LESSONS-LEARNT).
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.main import app
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.services.user_service import UserPermissionService

from tests.chatbot.test_turns_admin_api import db  # noqa: F401 - reuses the blank-schema fixture

BASE = "/api/v1/user-management/contacts"
CONTACT_VIEW = "user_management.contacts.view"

_GRANTS: set[str] = {CONTACT_VIEW}
_ACTOR: dict = {"id": None, "name": "ZZT Contact Profile Tester"}


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    _GRANTS.clear()
    _GRANTS.add(CONTACT_VIEW)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in _GRANTS,
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield
    _GRANTS.clear()


@pytest.fixture()
def client(db):  # noqa: F811 - fixture shadow is the point
    def _override_db():
        try:
            yield db
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


def _seed_contact(db) -> str:
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": f"ZZT-{uuid.uuid4().hex[:8]}", "phone": f"+6000{uuid.uuid4().hex[:7]}", "sv": json.dumps({})},
    )
    db.commit()
    return db.execute(text("SELECT id FROM respond_contacts ORDER BY created_at DESC LIMIT 1")).scalar()


def test_chatbot_profile_column_defaults_to_empty_dict(db):
    contact_id = _seed_contact(db)
    value = db.execute(
        text("SELECT chatbot_profile FROM respond_contacts WHERE id = :i"), {"i": contact_id}
    ).scalar()
    assert value == {}


def test_chatbot_recall_enabled_column_defaults_to_false(db):
    contact_id = _seed_contact(db)
    value = db.execute(
        text("SELECT chatbot_recall_enabled FROM respond_contacts WHERE id = :i"),
        {"i": contact_id},
    ).scalar()
    assert value is False


def test_get_contact_detail_returns_chatbot_profile_and_recall_enabled(db, client):
    contact_id = _seed_contact(db)
    resp = client.get(f"{BASE}/{contact_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "chatbot_profile" in body, body
    assert "chatbot_recall_enabled" in body, body
    assert body["chatbot_profile"] == {}
    assert body["chatbot_recall_enabled"] is False


def test_put_contact_accepts_chatbot_recall_enabled_and_profile(db, client):
    contact_id = _seed_contact(db)
    resp = client.put(
        f"{BASE}/{contact_id}",
        json={
            "chatbot_recall_enabled": True,
            "chatbot_profile": {"tier": "dealer", "language": "en"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chatbot_recall_enabled"] is True
    assert body["chatbot_profile"] == {"tier": "dealer", "language": "en"}

    stored = db.execute(
        text("SELECT chatbot_recall_enabled, chatbot_profile FROM respond_contacts WHERE id = :i"),
        {"i": contact_id},
    ).one()
    assert stored[0] is True
    assert stored[1] == {"tier": "dealer", "language": "en"}
