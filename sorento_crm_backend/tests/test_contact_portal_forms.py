"""GET|PUT /api/v1/user-management/contacts/{contact_id}/portal-forms

Contract: PLAN-contact-portal-form-override UAC AC-1 through AC-6.

Only GATED_FORM_TYPES ("price_tag_request" today) is offered by this route -
the four legacy submission kinds are always on the portal landing and never
appear here. `_client` stubs `UserPermissionService.check_user_has_permission`
wholesale (same technique as `tests/test_media_access_contact_route.py`), so
these tests exercise the route's own logic, not the permission service.

Run with: pytest tests/test_contact_portal_forms.py -v
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.access import (
    ContactAccessType,
    RespondContact,
    respond_contact_access_types,
)
from app.models.price_tag import ContactPortalFormOverride
from app.services.portal_form_visibility_service import resolve_visible_form_types
from app.services.user_service import UserPermissionService

from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/user-management/contacts/{contact_id}/portal-forms"


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _seeded_contact(db) -> RespondContact:
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
    )
    db.add(contact)
    db.flush()
    return contact


def _seed_access_type(db, *, portal_form_types: list[str]) -> ContactAccessType:
    row = ContactAccessType(
        code=unique_code("at").lower(),
        name=unique_code("Access Type"),
        portal_form_types=portal_form_types,
    )
    db.add(row)
    db.flush()
    return row


def _assign(db, contact: RespondContact, access_type: ContactAccessType) -> None:
    db.execute(
        respond_contact_access_types.insert().values(
            contact_id=contact.id,
            access_type_code=access_type.code,
        )
    )
    db.flush()


def _client(db, monkeypatch, *, requested_slugs: list[str] | None = None) -> TestClient:
    user = {"id": str(uuid.uuid4())}

    def _db_override():
        yield db

    def _check(self, uid, slug):
        if requested_slugs is not None:
            requested_slugs.append(slug)
        return True

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", _check)
    return TestClient(app)


def test_get_with_no_access_types_and_no_override_is_all_false(monkeypatch):
    with blank_session() as db:
        contact = _seeded_contact(db)
        client = _client(db, monkeypatch)

        response = client.get(BASE.format(contact_id=contact.id))

        assert response.status_code == 200, response.text
        forms = response.json()["forms"]
        assert len(forms) == 1
        row = forms[0]
        assert row["form_type"] == "price_tag_request"
        assert row["inherited"] is False
        assert row["override"] is None
        assert row["effective"] is False


def test_get_reflects_inheritance_from_an_assigned_access_type(monkeypatch):
    with blank_session() as db:
        contact = _seeded_contact(db)
        access_type = _seed_access_type(db, portal_form_types=["price_tag_request"])
        _assign(db, contact, access_type)
        client = _client(db, monkeypatch)

        response = client.get(BASE.format(contact_id=contact.id))

        assert response.status_code == 200, response.text
        row = response.json()["forms"][0]
        assert row["inherited"] is True
        assert row["override"] is None
        assert row["effective"] is True


def test_put_enables_with_no_inheritance_and_resolver_sees_it(monkeypatch):
    with blank_session() as db:
        contact = _seeded_contact(db)
        client = _client(db, monkeypatch)

        response = client.put(
            BASE.format(contact_id=contact.id),
            json={"overrides": [{"form_type": "price_tag_request", "is_enabled": True}]},
        )

        assert response.status_code == 200, response.text
        row = response.json()["forms"][0]
        assert row["override"] is True
        assert row["effective"] is True

        get_response = client.get(BASE.format(contact_id=contact.id))
        assert get_response.json()["forms"][0]["effective"] is True

        assert "price_tag_request" in resolve_visible_form_types(db, contact.id)


def test_put_disables_and_wins_over_inheritance(monkeypatch):
    with blank_session() as db:
        contact = _seeded_contact(db)
        access_type = _seed_access_type(db, portal_form_types=["price_tag_request"])
        _assign(db, contact, access_type)
        client = _client(db, monkeypatch)

        response = client.put(
            BASE.format(contact_id=contact.id),
            json={"overrides": [{"form_type": "price_tag_request", "is_enabled": False}]},
        )

        assert response.status_code == 200, response.text
        row = response.json()["forms"][0]
        assert row["inherited"] is True
        assert row["override"] is False
        assert row["effective"] is False
        assert "price_tag_request" not in resolve_visible_form_types(db, contact.id)


def test_put_null_deletes_the_override_row_back_to_inherit(monkeypatch):
    with blank_session() as db:
        contact = _seeded_contact(db)
        client = _client(db, monkeypatch)

        client.put(
            BASE.format(contact_id=contact.id),
            json={"overrides": [{"form_type": "price_tag_request", "is_enabled": True}]},
        )
        assert (
            db.query(ContactPortalFormOverride)
            .filter(ContactPortalFormOverride.contact_id == contact.id)
            .count()
            == 1
        )

        response = client.put(
            BASE.format(contact_id=contact.id),
            json={"overrides": [{"form_type": "price_tag_request", "is_enabled": None}]},
        )

        assert response.status_code == 200, response.text
        row = response.json()["forms"][0]
        assert row["override"] is None
        assert row["effective"] is False
        assert (
            db.query(ContactPortalFormOverride)
            .filter(ContactPortalFormOverride.contact_id == contact.id)
            .count()
            == 0
        )


def test_put_same_form_type_twice_in_one_request_last_wins(monkeypatch):
    """AC-2/AC-6 review fix: a payload naming price_tag_request twice - once
    enabling it, once clearing it - must not hit the unique constraint (500)
    or leave the outcome dependent on list order. The last entry wins, so
    [true, null] ends with no row at all."""
    with blank_session() as db:
        contact = _seeded_contact(db)
        client = _client(db, monkeypatch)

        response = client.put(
            BASE.format(contact_id=contact.id),
            json={
                "overrides": [
                    {"form_type": "price_tag_request", "is_enabled": True},
                    {"form_type": "price_tag_request", "is_enabled": None},
                ]
            },
        )

        assert response.status_code == 200, response.text
        row = response.json()["forms"][0]
        assert row["override"] is None
        assert row["effective"] is False
        assert (
            db.query(ContactPortalFormOverride)
            .filter(ContactPortalFormOverride.contact_id == contact.id)
            .count()
            == 0
        )


def test_get_and_put_ask_for_the_right_permission_slugs(monkeypatch):
    with blank_session() as db:
        contact = _seeded_contact(db)
        slugs: list[str] = []
        client = _client(db, monkeypatch, requested_slugs=slugs)

        get_response = client.get(BASE.format(contact_id=contact.id))
        assert get_response.status_code == 200, get_response.text
        assert "user_management.contacts.view" in slugs
        assert "user_management.contacts.edit" not in slugs

        slugs.clear()
        put_response = client.put(
            BASE.format(contact_id=contact.id),
            json={"overrides": [{"form_type": "price_tag_request", "is_enabled": True}]},
        )
        assert put_response.status_code == 200, put_response.text
        assert "user_management.contacts.edit" in slugs


def test_put_twice_updates_the_same_row_no_duplicate(monkeypatch):
    with blank_session() as db:
        contact = _seeded_contact(db)
        client = _client(db, monkeypatch)

        client.put(
            BASE.format(contact_id=contact.id),
            json={"overrides": [{"form_type": "price_tag_request", "is_enabled": True}]},
        )
        response = client.put(
            BASE.format(contact_id=contact.id),
            json={"overrides": [{"form_type": "price_tag_request", "is_enabled": False}]},
        )

        assert response.status_code == 200, response.text
        rows = (
            db.query(ContactPortalFormOverride)
            .filter(ContactPortalFormOverride.contact_id == contact.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].is_enabled is False


def test_put_unknown_form_type_is_422(monkeypatch):
    with blank_session() as db:
        contact = _seeded_contact(db)
        client = _client(db, monkeypatch)

        response = client.put(
            BASE.format(contact_id=contact.id),
            json={"overrides": [{"form_type": "not_a_form", "is_enabled": True}]},
        )

        assert response.status_code == 422, response.text
        assert (
            db.query(ContactPortalFormOverride)
            .filter(ContactPortalFormOverride.contact_id == contact.id)
            .count()
            == 0
        )


def test_get_unknown_contact_is_404(monkeypatch):
    with blank_session() as db:
        client = _client(db, monkeypatch)

        response = client.get(BASE.format(contact_id=str(uuid.uuid4())))

        assert response.status_code == 404, response.text


def test_put_unknown_contact_is_404(monkeypatch):
    with blank_session() as db:
        client = _client(db, monkeypatch)

        response = client.put(
            BASE.format(contact_id=str(uuid.uuid4())),
            json={"overrides": [{"form_type": "price_tag_request", "is_enabled": True}]},
        )

        assert response.status_code == 404, response.text
