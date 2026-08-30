"""D61: Price Tag Request deploys granted to nobody, and admins switch it on.

Two halves, one contract (AC-M.26, AC-M.27).

The deploy half: ``ptag_0003`` strips ``price_tag_request`` out of every
``contact_access_types.portal_form_types`` array, so a database that already ran
the first version of ``ptag_0001`` lands where a fresh one lands. The SQL is
imported from the migration rather than retyped, so a test cannot pass against a
statement production never runs.

The admin half: ``portal_form_types`` reaches the wire. ``response_model`` drops
what it does not declare, so every assertion here goes through TestClient and
reads the JSON, not the ORM row.

Run with: pytest tests/test_portal_form_grant_admin.py -v
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.access import (
    ContactAccessType,
    RespondContact,
    respond_contact_access_types,
)
from app.services.portal_form_visibility_service import resolve_visible_form_types
from tests._pg_fixture import blank_session, unique_code

_BASE = "/api/v1/user-management/contact-access-types"
_USER = {"id": str(uuid.uuid4()), "email": "d61@example.com"}


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def client(db, monkeypatch):
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.services.user_service import UserPermissionService

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _USER
    # The blank schema carries no role grants. This file is about the field on the
    # wire, not about who may edit an access type, so the grant check is stubbed.
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
    )
    monkeypatch.setattr(
        UserPermissionService,
        "get_user_permission_slugs",
        lambda self, uid: {"user_management.access_agents.view", "user_management.reference_data.view"},
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_type(db, *, portal_form_types: list[str] | None = None) -> ContactAccessType:
    row = ContactAccessType(
        code=unique_code("at").lower(),
        name=unique_code("Access Type"),
        portal_form_types=portal_form_types if portal_form_types is not None else [],
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# AC-M.26 - the deploy half
# ---------------------------------------------------------------------------


def _strip_sql() -> str:
    """The statement ``ptag_0003`` runs, loaded from the migration file itself."""
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "ptag_0003_strip_price_tag_grant.py"
    )
    spec = importlib.util.spec_from_file_location("ptag_0003_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.STRIP_SQL


class TestTheStrip:
    def test_it_removes_price_tag_request_and_leaves_the_rest(self, db):
        row = _seed_type(
            db,
            portal_form_types=["price_tag_request", "stock_inquiry", "complaint"],
        )
        db.execute(text(_strip_sql()))
        db.flush()
        db.refresh(row)
        assert row.portal_form_types == ["stock_inquiry", "complaint"]

    def test_running_it_twice_changes_nothing(self, db):
        row = _seed_type(db, portal_form_types=["price_tag_request", "stock_inquiry"])
        sql = _strip_sql()
        db.execute(text(sql))
        db.flush()
        db.refresh(row)
        after_once = list(row.portal_form_types)

        db.execute(text(sql))
        db.flush()
        db.refresh(row)
        assert list(row.portal_form_types) == after_once == ["stock_inquiry"]

    def test_a_type_that_never_had_it_is_untouched(self, db):
        row = _seed_type(db, portal_form_types=["stock_inquiry", "purchase_request"])
        db.execute(text(_strip_sql()))
        db.flush()
        db.refresh(row)
        assert row.portal_form_types == ["stock_inquiry", "purchase_request"]

    def test_an_empty_array_survives(self, db):
        row = _seed_type(db, portal_form_types=[])
        db.execute(text(_strip_sql()))
        db.flush()
        db.refresh(row)
        assert row.portal_form_types == []


class TestTheResolverAfterTheStrip:
    def test_a_contact_whose_type_lost_the_grant_does_not_see_it(self, db):
        contact = RespondContact(
            id=str(uuid.uuid4()),
            phone_number=f"+60{uuid.uuid4().hex[:9]}",
            name=unique_code("contact"),
        )
        db.add(contact)
        access_type = _seed_type(db, portal_form_types=["stock_inquiry"])
        db.execute(
            respond_contact_access_types.insert().values(
                contact_id=contact.id,
                access_type_code=access_type.code,
            )
        )
        db.flush()

        visible = resolve_visible_form_types(db, contact.id)

        assert "price_tag_request" not in visible
        assert visible == {"stock_inquiry"}


# ---------------------------------------------------------------------------
# AC-M.27 - the admin half, on the wire
# ---------------------------------------------------------------------------


class TestThePortalFormsField:
    def test_the_row_read_carries_portal_form_types(self, client, db):
        row = _seed_type(db, portal_form_types=["stock_inquiry"])

        res = client.get(f"{_BASE}/{row.code}")

        assert res.status_code == 200, res.text
        # response_model drops what it does not declare - so assert the KEY.
        assert res.json()["portal_form_types"] == ["stock_inquiry"]

    def test_the_admin_list_carries_portal_form_types(self, client, db):
        row = _seed_type(db, portal_form_types=["complaint"])

        res = client.get(f"{_BASE}/all")

        assert res.status_code == 200, res.text
        mine = [r for r in res.json() if r["code"] == row.code]
        assert mine and mine[0]["portal_form_types"] == ["complaint"]

    def test_update_writes_the_grant(self, client, db):
        row = _seed_type(db, portal_form_types=["stock_inquiry"])

        res = client.put(
            f"{_BASE}/{row.code}",
            json={"portal_form_types": ["stock_inquiry", "price_tag_request"]},
        )

        assert res.status_code == 200, res.text
        assert res.json()["portal_form_types"] == ["stock_inquiry", "price_tag_request"]
        db.refresh(row)
        assert row.portal_form_types == ["stock_inquiry", "price_tag_request"]

    def test_update_can_take_the_grant_back(self, client, db):
        row = _seed_type(db, portal_form_types=["stock_inquiry", "price_tag_request"])

        res = client.put(f"{_BASE}/{row.code}", json={"portal_form_types": ["stock_inquiry"]})

        assert res.status_code == 200, res.text
        assert res.json()["portal_form_types"] == ["stock_inquiry"]

    def test_an_update_that_omits_the_field_leaves_it_alone(self, client, db):
        row = _seed_type(db, portal_form_types=["price_tag_request"])

        res = client.put(f"{_BASE}/{row.code}", json={"name": "ZZT renamed"})

        assert res.status_code == 200, res.text
        assert res.json()["portal_form_types"] == ["price_tag_request"]

    def test_an_unknown_kind_is_refused(self, client, db):
        row = _seed_type(db, portal_form_types=["stock_inquiry"])

        res = client.put(
            f"{_BASE}/{row.code}",
            json={"portal_form_types": ["stock_inquiry", "not_a_form"]},
        )

        assert res.status_code == 422, res.text
        db.refresh(row)
        assert row.portal_form_types == ["stock_inquiry"]

    def test_create_carries_the_grant(self, client, db):
        code = unique_code("at").lower()

        res = client.post(
            _BASE,
            json={
                "code": code,
                "name": "ZZT Created",
                "portal_form_types": ["price_tag_request"],
            },
        )

        assert res.status_code == 201, res.text
        assert res.json()["portal_form_types"] == ["price_tag_request"]

    def test_create_refuses_an_unknown_kind(self, client, db):
        res = client.post(
            _BASE,
            json={
                "code": unique_code("at").lower(),
                "name": "ZZT Created",
                "portal_form_types": ["nope"],
            },
        )

        assert res.status_code == 422, res.text
