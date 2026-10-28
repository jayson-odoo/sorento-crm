"""FILTER-MULTISELECT PR2: the topic audit's Subject filter takes several values (OR within the
filter). Red first; Postgres only; every test seeds its own taxonomy, facts and sample. Fixtures mirror
tests/chatbot/test_topic_audit_api.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.main  # noqa: F401  registers every model
from app.main import app
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.services.user_service import UserPermissionService

BASE = "/api/v1/system/chatbot/topic-audit"
VIEW = "system.chat_history.view"
ANALYTICS = "chatbot.analytics.view"
UTC = timezone.utc
VERSION = 2
_ACTOR: dict = {"id": None, "name": "ZZT Auditor", "email": "zzt-auditor-multi@zzt.test"}

SUBJECTS = (("inventory", "Stock"), ("order", "Orders"), ("general", "General chat"))
LEAVES = (
    ("inventory.availability", "inventory", "Availability"),
    ("order.status", "order", "Order status"),
    ("general.noise", "general", "Noise"),
)


@pytest.fixture()
def db(session_factory):
    return session_factory()


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in {VIEW, ANALYTICS})
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())


@pytest.fixture()
def client(db, session_factory):
    from app.models.user import User

    _ACTOR["id"] = str(uuid.uuid4())
    seeder = session_factory()
    seeder.add(User(id=_ACTOR["id"], email=_ACTOR["email"], name=_ACTOR["name"], status="ACTIVE"))
    seeder.commit()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def seeded(session_factory, client):
    from app.models.chat_facts import ChatAskFact, ChatTopic

    db = session_factory()
    for order, (code, label) in enumerate(SUBJECTS):
        db.add(ChatTopic(code=code, label=label, definition=label, version=1, sort_order=order))
    db.flush()
    for order, (code, parent, label) in enumerate(LEAVES):
        db.add(ChatTopic(code=code, parent_code=parent, label=label, definition=label, version=VERSION, sort_order=order))
    db.commit()
    leaf = {"inventory": "inventory.availability", "order": "order.status", "general": "general.noise"}
    facts = {}
    for i, subject in enumerate(("inventory", "order", "general", "inventory")):
        fact_id = str(uuid.uuid4())
        db.add(ChatAskFact(
            id=fact_id, source="trace", turn_id=str(uuid.uuid4()), ask_seq=1,
            contact_respond_id=f"ZZT-audit-{fact_id[:8]}", audience="dealer", contact_type="dealer",
            asked_at=datetime(2026, 9, 10, 3, 0, tzinfo=UTC) + timedelta(minutes=i), channel="whatsapp",
            domain=None if subject == "general" else subject, outcome="answered", tools=[],
            topic_code=leaf[subject], taxonomy_version=VERSION, label_confidence=0.9, language="en",
            is_media=False, phantom_dropped=False,
        ))
        facts.setdefault(subject, []).append(fact_id)
    db.commit()
    assert client.post(f"{BASE}/sample", json={"version": VERSION}).status_code == 201
    rows = client.get(BASE, params={"show": "all"}).json()["rows"]
    assert len(rows) == 4
    return rows


def _subjects(client, *pairs):
    resp = client.get(BASE, params=[("show", "all"), *pairs])
    assert resp.status_code == 200, resp.text
    return sorted(r["subject"] for r in resp.json()["rows"])


def test_subject_two_values_are_the_union(client, seeded):
    assert _subjects(client, ("subject", "inventory,general")) == ["general", "inventory", "inventory"]


def test_subject_single_and_repeated(client, seeded):
    assert _subjects(client, ("subject", "order")) == ["order"]
    assert _subjects(client, ("subject", "order"), ("subject", "general")) == ["general", "order"]


def test_no_subject_is_every_row(client, seeded):
    assert len(_subjects(client)) == 4
