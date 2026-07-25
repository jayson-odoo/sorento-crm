"""Endpoint tests for GET /api/v1/rule-facts?sources=promotion.

Returns the 9 promotion facts with per-type operators and the dynamic
accessLevels options (materialized ContactAccessType catalog). Enforces the
automation.automations.view permission (JWT only, never X-API-Key).

sqlite fixture + dependency overrides (superadmin bypass) for the happy path;
a permission-less user -> 403; no principal -> 401.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app  # noqa: E402

_SUPERADMIN_ID = "130c548f-048f-53b2-97a6-3a54676bea77"
_SUPERADMIN_ROLE = "7c50d6db-8dce-555a-85a2-86cf7756f33f"
_PLAIN_ID = "22222222-2222-5222-a222-222222222222"
_PLAIN_ROLE = "33333333-3333-5333-a333-333333333333"


@pytest.fixture
def make_client(monkeypatch):
    from app.dependencies import get_current_user, get_db
    from app.database import Base
    from app.models.access import ContactAccessType
    from app.models.lookup import LookupBinding
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # ContactAccessType.keywords has a pg `::jsonb` server_default sqlite can't parse.
    for col in ContactAccessType.__table__.columns:
        sd = getattr(col.server_default, "arg", None)
        if sd is not None and "::" in str(sd):
            col.server_default = None

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            UserRole.__table__,
            UserRoleAssignment.__table__,
            UserPermission.__table__,
            UserRolePermission.__table__,
            ContactAccessType.__table__,
            LookupBinding.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    # superadmin (bypasses permission check)
    db.add(UserRole(id=_SUPERADMIN_ROLE, slug="superadmin", name="Superadmin", is_protected=True))
    db.add(User(id=_SUPERADMIN_ID, email="admin@test.com", name="Admin", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_SUPERADMIN_ID, role_id=_SUPERADMIN_ROLE))
    # plain user with a non-privileged role and no automation.view permission
    db.add(UserRole(id=_PLAIN_ROLE, slug="viewer", name="Viewer"))
    db.add(User(id=_PLAIN_ID, email="viewer@test.com", name="Viewer", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_PLAIN_ID, role_id=_PLAIN_ROLE))
    # active + inactive access types
    db.add(ContactAccessType(code="sorento_dealer", name="Sorento Dealer", is_active=True, sort_order=1, keywords=[]))
    db.add(ContactAccessType(code="cabana_office", name="Cabana Office", is_active=True, sort_order=2, keywords=[]))
    db.add(ContactAccessType(code="legacy", name="Legacy", is_active=False, sort_order=3, keywords=[]))
    db.commit()

    def _override_get_db():
        yield db

    def _make(user_id: str | None):
        app.dependency_overrides[get_db] = _override_get_db
        if user_id is not None:
            app.dependency_overrides[get_current_user] = lambda: {"id": user_id}
        return TestClient(app)

    yield _make

    app.dependency_overrides.clear()
    db.close()


def test_rule_facts_happy_path_returns_promotion_facts(make_client):
    client = make_client(_SUPERADMIN_ID)
    res = client.get("/api/v1/rule-facts", params={"sources": "promotion"})
    assert res.status_code == 200, res.text
    items = res.json()
    keys = {i["key"] for i in items}
    expected = {
        "promotion.name",
        "promotion.accessLevels",
        "promotion.isActive",
        "promotion.startDate",
        "promotion.startDate.daysSince",
        "promotion.startDate.daysUntil",
        "promotion.endDate",
        "promotion.endDate.daysSince",
        "promotion.endDate.daysUntil",
    }
    assert expected == keys  # exactly 9 promotion facts

    by_key = {i["key"]: i for i in items}
    # per-type operators
    assert by_key["promotion.name"]["operators"] == ["eq", "neq", "contains", "in", "not_in"]
    assert by_key["promotion.accessLevels"]["operators"] == [
        "contains_any",
        "contains_all",
        "not_contains",
    ]
    assert by_key["promotion.isActive"]["operators"] == ["is_true", "is_false"]

    # dynamic options: only active access types, code->value / name->label
    opts = by_key["promotion.accessLevels"]["options"]
    values = {o["value"] for o in opts}
    assert values == {"sorento_dealer", "cabana_office"}  # inactive excluded
    assert by_key["promotion.name"]["options"] is None


def test_rule_facts_permission_denied_for_plain_user(make_client):
    client = make_client(_PLAIN_ID)
    res = client.get("/api/v1/rule-facts", params={"sources": "promotion"})
    assert res.status_code == 403, res.text


def test_rule_facts_requires_auth(make_client):
    client = make_client(None)  # no get_current_user override -> real dependency
    res = client.get("/api/v1/rule-facts", params={"sources": "promotion"})
    assert res.status_code in (401, 403), res.text
