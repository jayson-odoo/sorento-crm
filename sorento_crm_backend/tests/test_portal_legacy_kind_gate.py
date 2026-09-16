"""Portal gate (D5): a hidden kind 403s FORM_TYPE_NOT_VISIBLE on every legacy
route (AC-G1), on the two attachment routes that derive their kind from the
link row rather than a ``kind`` path/query param (AC-G2), reflected on
``/me`` (AC-G4), and the price-tag regression guard (AC-G5).

D3's base default means every legacy kind is VISIBLE by default, so "hidden"
here means a deliberate ``is_enabled=false`` override on the kind under test.
None of AC-G1's routes need a REAL submission to exist: `_require_form_visible`
(D5) is called from inside `_check_kind` / `_check_revisable_kind` /
`_check_attachment_kind`, evaluated before any ownership/existence lookup, so
the 403 must fire on a submission id that does not exist at all. Today, with
no gate wired in, these calls fall through to the existing ownership/
existence check instead and answer 200 or 404 - never
``code=FORM_TYPE_NOT_VISIBLE`` - which is the red this file exercises.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves circular-import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.database import get_db
from app.models.access import RespondContact
from app.models.complaints import Complaint
from app.models.entity_attachment import EntityAttachmentLink
from app.models.portal import PortalToken
from app.models.price_tag import ContactPortalFormOverride
from app.models.resources import Attachment
from app.services.portal_service import SUPPORTED_TYPES
from tests._pg_fixture import blank_session, unique_code
from tests._portal_grant import link_contact_segment, seed_segment

BASE = "/api/v1/public/portal"


@pytest.fixture
def client(monkeypatch):
    with blank_session() as db:

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app) as c:
                yield c, db
        finally:
            app.dependency_overrides.clear()


def _contact(db) -> RespondContact:
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
    )
    db.add(contact)
    db.flush()
    return contact


def _token(db, contact: RespondContact, space_id: str = "zzt-space") -> PortalToken:
    t = PortalToken(
        id=str(uuid.uuid4()),
        token=f"tok-{uuid.uuid4().hex}",
        contact_id=contact.id,
        space_id=space_id,
        expires_at=datetime.utcnow() + timedelta(days=30),
        verified_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add(t)
    db.commit()
    return t


def _hide(db, contact_id: str, kind: str) -> None:
    db.add(
        ContactPortalFormOverride(
            id=str(uuid.uuid4()),
            contact_id=contact_id,
            form_type=kind,
            is_enabled=False,
        )
    )
    db.flush()


def _headers(token: PortalToken) -> dict:
    return {"X-Portal-Token": token.token}


def _assert_gated(response) -> None:
    assert response.status_code == 403, response.text
    body = response.json()
    assert body.get("code") == "FORM_TYPE_NOT_VISIBLE", body


def _complaint(db, contact: RespondContact, space_id: str) -> Complaint:
    row = Complaint(
        id=str(uuid.uuid4()), contact_id=contact.id, space_id=space_id, status="new"
    )
    db.add(row)
    db.commit()
    return row


def _attachment_and_link(db, entity_type: str, entity_id: str):
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename="zzt.txt",
        stored_filename="zzt.txt",
        file_path=f"https://cdn.test/{uuid.uuid4().hex}.txt",
        mime_type="text/plain",
        file_size_bytes=5,
        uploader_kind="contact",
    )
    db.add(att)
    db.flush()
    link = EntityAttachmentLink(
        id=str(uuid.uuid4()),
        entity_type=entity_type,
        entity_id=str(entity_id),
        attachment_id=att.id,
    )
    db.add(link)
    db.commit()
    return att, link


# ---------------------------------------------------------------------------
# AC-G1 - 13 generic routes x the 4 legacy kinds
# ---------------------------------------------------------------------------


def _route_calls(kind: str, sid: str):
    """(name, callable(client, headers) -> response) for the 13 gated routes."""
    return [
        (
            "list",
            lambda c, h: c.get(f"{BASE}/submissions", params={"type": kind}, headers=h),
        ),
        (
            "create_draft",
            lambda c, h: c.post(
                f"{BASE}/submissions/{kind}", json={"fields": {}}, headers=h
            ),
        ),
        (
            "update_draft",
            lambda c, h: c.put(
                f"{BASE}/submissions/{kind}/{sid}", json={"fields": {}}, headers=h
            ),
        ),
        (
            "delete_draft",
            lambda c, h: c.delete(f"{BASE}/submissions/{kind}/{sid}", headers=h),
        ),
        (
            "submit",
            lambda c, h: c.post(f"{BASE}/submissions/{kind}/{sid}/submit", headers=h),
        ),
        ("detail", lambda c, h: c.get(f"{BASE}/submissions/{kind}/{sid}", headers=h)),
        (
            "list_revisions",
            lambda c, h: c.get(
                f"{BASE}/submissions/{kind}/{sid}/revisions", headers=h
            ),
        ),
        (
            "revise",
            lambda c, h: c.post(
                f"{BASE}/submissions/{kind}/{sid}/revise",
                json={"reason": "ZZT change", "expected_revision_no": 0},
                headers=h,
            ),
        ),
        (
            "save_revision_draft",
            lambda c, h: c.put(
                f"{BASE}/submissions/{kind}/{sid}/revision-draft",
                json={"base_revision_no": 0},
                headers=h,
            ),
        ),
        (
            "discard_revision_draft",
            lambda c, h: c.delete(
                f"{BASE}/submissions/{kind}/{sid}/revision-draft", headers=h
            ),
        ),
        (
            "neighbours",
            lambda c, h: c.get(
                f"{BASE}/submissions/{kind}/{sid}/neighbours", headers=h
            ),
        ),
        (
            "list_attachments",
            lambda c, h: c.get(
                f"{BASE}/attachments",
                params={"kind": kind, "submission_id": sid},
                headers=h,
            ),
        ),
        (
            "upload_attachment",
            lambda c, h: c.post(
                f"{BASE}/attachments",
                data={"kind": kind, "submission_id": sid},
                files={"file": ("zzt.txt", b"hello", "text/plain")},
                headers=h,
            ),
        ),
    ]


ROUTE_NAMES = [name for name, _ in _route_calls("complaint", "x")]


@pytest.mark.parametrize("kind", SUPPORTED_TYPES)
@pytest.mark.parametrize("route_name", ROUTE_NAMES)
def test_hidden_kind_is_403_on_every_legacy_route(client, route_name, kind):
    c, db = client
    contact = _contact(db)
    token = _token(db, contact)
    _hide(db, contact.id, kind)

    sid = str(uuid.uuid4())
    calls = dict(_route_calls(kind, sid))
    response = calls[route_name](c, _headers(token))

    _assert_gated(response)


# ---------------------------------------------------------------------------
# AC-G2 - attachment download / delete derive kind from the link row
# ---------------------------------------------------------------------------


def test_hidden_kind_attachment_download_is_403(client, monkeypatch):
    import app.services.storage_router as storage_router

    c, db = client
    contact = _contact(db)
    token = _token(db, contact)
    complaint = _complaint(db, contact, token.space_id)
    _hide(db, contact.id, "complaint")
    att, _link = _attachment_and_link(db, "complaint", complaint.id)

    class _FakeBackend:
        def download_file(self, key):
            return b"bytes"

    monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: _FakeBackend())

    response = c.get(f"{BASE}/attachments/{att.id}/download", headers=_headers(token))

    _assert_gated(response)


def test_hidden_kind_attachment_delete_is_403(client):
    c, db = client
    contact = _contact(db)
    token = _token(db, contact)
    complaint = _complaint(db, contact, token.space_id)
    _hide(db, contact.id, "complaint")
    _att, link = _attachment_and_link(db, "complaint", complaint.id)

    response = c.delete(f"{BASE}/attachments/{link.id}", headers=_headers(token))

    _assert_gated(response)


def _purchase_request(db, contact, space_id: str, *, request_type: str):
    from app.models.procurement import PurchaseRequestHeader

    row = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_type=request_type,
        contact_id=contact.id,
        space_id=space_id,
        status="new",
    )
    db.add(row)
    db.commit()
    return row


def test_hidden_sponsorship_form_attachment_download_is_403(client, monkeypatch):
    """AC-G2 r4: sponsorship_form attachments live under
    ``entity_type=purchase_request`` (the two kinds share one table) - the
    row-derived gate must resolve the AMBIGUOUS entity_type to the real
    kind and gate on THAT, not on ``purchase_request``."""
    import app.services.storage_router as storage_router

    c, db = client
    contact = _contact(db)
    token = _token(db, contact)
    sponsorship = _purchase_request(db, contact, token.space_id, request_type="sponsorship_form")
    _hide(db, contact.id, "sponsorship_form")
    att, _link = _attachment_and_link(db, "purchase_request", sponsorship.id)

    class _FakeBackend:
        def download_file(self, key):
            return b"bytes"

    monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: _FakeBackend())

    response = c.get(f"{BASE}/attachments/{att.id}/download", headers=_headers(token))

    _assert_gated(response)


def test_hidden_sponsorship_form_attachment_delete_is_403(client):
    c, db = client
    contact = _contact(db)
    token = _token(db, contact)
    sponsorship = _purchase_request(db, contact, token.space_id, request_type="sponsorship_form")
    _hide(db, contact.id, "sponsorship_form")
    _att, link = _attachment_and_link(db, "purchase_request", sponsorship.id)

    response = c.delete(f"{BASE}/attachments/{link.id}", headers=_headers(token))

    _assert_gated(response)


def test_hidden_kind_attachment_in_revision_history_download_is_403(client):
    """AC-G2 r4: an attachment unlinked by a revision (UAC G6, no live
    ``EntityAttachmentLink`` left) is still resolved through
    ``PortalFormRevision.attachments_json`` - the same gate must fire there
    too, not just on the live-link arm."""
    from app.models.portal import PortalFormRevision

    c, db = client
    contact = _contact(db)
    token = _token(db, contact)
    complaint = _complaint(db, contact, token.space_id)
    _hide(db, contact.id, "complaint")

    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename="zzt-history.txt",
        stored_filename="zzt-history.txt",
        file_path=f"https://cdn.test/{uuid.uuid4().hex}.txt",
        mime_type="text/plain",
        file_size_bytes=5,
        uploader_kind="contact",
    )
    db.add(att)
    db.flush()
    db.add(
        PortalFormRevision(
            id=str(uuid.uuid4()),
            source_entity_type="complaint",
            source_entity_id=complaint.id,
            version_no=1,
            revision_no=0,
            kind="original",
            attachments_json=[{"attachment_id": str(att.id)}],
        )
    )
    db.commit()

    response = c.get(f"{BASE}/attachments/{att.id}/download", headers=_headers(token))

    _assert_gated(response)


# ---------------------------------------------------------------------------
# AC-G4 - /me visible_form_types
# ---------------------------------------------------------------------------


def test_me_visible_form_types_covers_all_five(client):
    c, db = client
    contact = _contact(db)
    token = _token(db, contact)
    segment = seed_segment(db, kinds=["price_tag_request"])
    link_contact_segment(db, contact.id, segment.code)
    _hide(db, contact.id, "complaint")

    response = c.get(f"{BASE}/me", headers=_headers(token))

    assert response.status_code == 200, response.text
    visible = set(response.json()["visible_form_types"])
    assert visible == {
        "stock_inquiry",
        "purchase_request",
        "sponsorship_form",
        "price_tag_request",
    }


# ---------------------------------------------------------------------------
# AC-G5 - price tag regression guard
# ---------------------------------------------------------------------------


def test_price_tag_routes_still_403_without_grant(client):
    c, db = client
    contact = _contact(db)
    token = _token(db, contact)
    # A segment that grants NOTHING - proves plain segment membership does not
    # leak price_tag_request (it stays opt-in, D3).
    segment = seed_segment(db, kinds=())
    link_contact_segment(db, contact.id, segment.code)

    response = c.get(f"{BASE}/submissions/price_tag_request", headers=_headers(token))

    _assert_gated(response)
