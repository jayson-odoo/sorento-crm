"""PUT /api/v1/user-management/contacts/{contact_id}/media-access/{modality}

Contract: sorento_crm_frontend .../contacts/[id]/services/contactMediaAccessService.ts
(Phase 1 docblock) + PLAN-chatbot-media-endpoint UAC S1-06:

    "Anyone who can edit a contact can change media access... a user without
    that permission gets 403. No new admin-only role is introduced."

No slug is hardcoded here on purpose. The point of S1-06 is that the route is
gated by *some* permission the existing contact-edit surface already checks
-- not that it is unguarded (any authenticated user), and not that it demands
a brand-new admin-only role. `UserPermissionService.check_user_has_permission`
is monkeypatched wholesale (same technique as
`tests/test_customer_import_route.py::_client`), so the assertion is exactly
"the route asks the permission service, and honours a False", independent of
which slug it names.

AC id covered: S1-06.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.main import app
from app.services.user_service import UserPermissionService

from tests._pg_fixture import blank_session

ENDPOINT = "/api/v1/user-management/contacts/{contact_id}/media-access/{modality}"


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _seeded_contact(db):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+1555{uuid.uuid4().hex[:8]}",
        name="ZZT media-access route contact",
    )
    db.add(contact)
    db.flush()
    return contact


def _client(db, *, permitted: bool, monkeypatch) -> TestClient:
    user = {"id": str(uuid.uuid4())}

    def _db_override():
        yield db

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: permitted,
    )
    return TestClient(app)


def test_a_caller_without_the_permission_is_refused(monkeypatch):
    with blank_session() as db:
        contact = _seeded_contact(db)
        client = _client(db, permitted=False, monkeypatch=monkeypatch)

        response = client.put(
            ENDPOINT.format(contact_id=contact.id, modality="image"),
            json={"is_allowed": True, "monthly_limit": 200, "max_clip_seconds": None},
        )

        assert response.status_code == 403


def test_a_caller_with_the_permission_can_change_media_access(monkeypatch):
    with blank_session() as db:
        contact = _seeded_contact(db)
        client = _client(db, permitted=True, monkeypatch=monkeypatch)

        response = client.put(
            ENDPOINT.format(contact_id=contact.id, modality="image"),
            json={"is_allowed": True, "monthly_limit": 200, "max_clip_seconds": None},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["modality"] == "image"
        assert body["is_allowed"] is True
        assert body["effective_monthly_limit"] == 200


def test_upserts_when_the_contact_has_no_row_yet(monkeypatch):
    """The FE contract's PUT doc: "a PUT against a contact with no row creates
    one" -- exercised here as part of the permitted path since S1-06 requires
    the write to actually succeed, not merely be authorized."""
    with blank_session() as db:
        contact = _seeded_contact(db)
        from app.models.media import ContactMediaLimit

        assert (
            db.query(ContactMediaLimit)
            .filter(ContactMediaLimit.contact_id == contact.id)
            .first()
            is None
        )
        client = _client(db, permitted=True, monkeypatch=monkeypatch)

        response = client.put(
            ENDPOINT.format(contact_id=contact.id, modality="voice"),
            json={"is_allowed": True, "monthly_limit": None, "max_clip_seconds": 90},
        )

        assert response.status_code == 200
        row = (
            db.query(ContactMediaLimit)
            .filter(
                ContactMediaLimit.contact_id == contact.id,
                ContactMediaLimit.modality == "voice",
            )
            .first()
        )
        assert row is not None
        assert row.is_allowed is True
        assert row.max_clip_seconds == 90
