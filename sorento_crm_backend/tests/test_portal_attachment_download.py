"""Portal attachment bytes route (UAC-portal-submission-revisions I2a / I5).

The contact portal has no NextAuth JWT session, so the office
``/resource-management/attachments/{id}/download`` route 401s there. This is the
portal-token-authenticated equivalent, and it is keyed on **attachment_id, not
link_id**: a later revision unlinks attachments the contact removed, and a
link-keyed route would 404 on exactly the historical files revision history
exists to show.

Authorisation walks: token -> the contact owns a submission -> the attachment
is linked to that submission.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves circular-import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.access import RespondContact
from app.models.entity_attachment import EntityAttachmentLink
from app.models.portal import PortalToken
from app.models.procurement import PurchaseRequestHeader, StockInquiry
from app.models.resources import Attachment
from tests._pg_fixture import blank_session

FILE_BYTES = b"portal-attachment-bytes"


class _FakeStorageBackend:
    def download_file(self, key: str) -> bytes:
        return FILE_BYTES


@pytest.fixture
def client(monkeypatch):
    from app.database import get_db
    import app.services.storage_router as storage_router

    with blank_session() as db:
        monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: _FakeStorageBackend())

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app) as c:
                yield c, db
        finally:
            app.dependency_overrides.clear()


def _contact(db: Session, *, name="Contact") -> RespondContact:
    c = RespondContact(
        id=str(uuid.uuid4()), phone_number=f"+6011{uuid.uuid4().hex[:8]}", name=name
    )
    db.add(c)
    db.flush()
    return c


def _token(db: Session, contact: RespondContact, space_id: str) -> PortalToken:
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


def _inquiry(db: Session, contact: RespondContact, space_id: str) -> StockInquiry:
    row = StockInquiry(
        id=str(uuid.uuid4()),
        inquiry_number=f"PORTAL-DL-{uuid.uuid4().hex[:6]}",
        status="pending_purchasing",
        contact_id=contact.id,
        space_id=space_id,
    )
    db.add(row)
    db.commit()
    return row


def _sponsorship_form(
    db: Session, contact: RespondContact, space_id: str
) -> PurchaseRequestHeader:
    row = PurchaseRequestHeader(
        id=str(uuid.uuid4()),
        request_number=f"PORTAL-SF-{uuid.uuid4().hex[:6]}",
        request_type="sponsorship_form",
        status="submitted",
        contact_id=contact.id,
        space_id=space_id,
    )
    db.add(row)
    db.commit()
    return row


def _attachment(db: Session, *, filename="quote.pdf", mime="application/pdf") -> Attachment:
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"https://cdn.test/portal/{uuid.uuid4().hex}/{filename}",
        mime_type=mime,
        file_size_bytes=len(FILE_BYTES),
        uploader_kind="contact",
    )
    db.add(att)
    db.commit()
    return att


def _link(db: Session, att: Attachment, entity_type: str, entity_id: str) -> EntityAttachmentLink:
    link = EntityAttachmentLink(
        entity_type=entity_type, entity_id=str(entity_id), attachment_id=att.id
    )
    db.add(link)
    db.commit()
    return link


def _url(attachment_id: str) -> str:
    return f"/api/v1/public/portal/attachments/{attachment_id}/download"


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


def test_owner_downloads_bytes_of_an_attachment_on_their_own_submission(client):
    c, db = client
    contact = _contact(db)
    token = _token(db, contact, "space-1")
    inquiry = _inquiry(db, contact, "space-1")
    att = _attachment(db)
    _link(db, att, "stock_inquiry", inquiry.id)

    res = c.get(_url(att.id), headers={"X-Portal-Token": token.token})

    assert res.status_code == 200, res.text
    assert res.content == FILE_BYTES
    assert res.headers["content-type"].startswith("application/pdf")
    assert "quote.pdf" in res.headers.get("content-disposition", "")


def test_non_ascii_filename_does_not_break_the_response_header(client):
    """Contact devices produce non-latin-1 filenames; a bare filename="..."
    header would raise at encode time and 500 the download."""
    c, db = client
    contact = _contact(db)
    token = _token(db, contact, "space-1")
    inquiry = _inquiry(db, contact, "space-1")
    att = _attachment(db, filename="报价单 v2.pdf")
    _link(db, att, "stock_inquiry", inquiry.id)

    res = c.get(_url(att.id), headers={"X-Portal-Token": token.token})
    assert res.status_code == 200, res.text
    disposition = res.headers.get("content-disposition", "")
    assert "filename*=UTF-8''" in disposition


def test_token_may_travel_as_a_query_param(client):
    """Mirrors every other portal route (header OR ?token=)."""
    c, db = client
    contact = _contact(db)
    token = _token(db, contact, "space-1")
    inquiry = _inquiry(db, contact, "space-1")
    att = _attachment(db)
    _link(db, att, "stock_inquiry", inquiry.id)

    res = c.get(_url(att.id), params={"token": token.token})
    assert res.status_code == 200, res.text
    assert res.content == FILE_BYTES


def test_sponsorship_form_attachments_resolve_through_the_purchase_request_entity_type(client):
    """Sponsorship form attachments are stored under entity_type=purchase_request."""
    c, db = client
    contact = _contact(db)
    token = _token(db, contact, "space-1")
    form = _sponsorship_form(db, contact, "space-1")
    att = _attachment(db, filename="poster.png", mime="image/png")
    _link(db, att, "purchase_request", form.id)

    res = c.get(_url(att.id), headers={"X-Portal-Token": token.token})
    assert res.status_code == 200, res.text
    assert res.content == FILE_BYTES


# --------------------------------------------------------------------------
# Denials
# --------------------------------------------------------------------------


def test_another_contacts_attachment_is_404(client):
    c, db = client
    owner = _contact(db, name="Owner")
    intruder = _contact(db, name="Intruder")
    intruder_token = _token(db, intruder, "space-1")
    inquiry = _inquiry(db, owner, "space-1")
    att = _attachment(db)
    _link(db, att, "stock_inquiry", inquiry.id)

    res = c.get(_url(att.id), headers={"X-Portal-Token": intruder_token.token})
    assert res.status_code == 404, res.text


def test_same_contact_in_another_space_is_404(client):
    c, db = client
    contact = _contact(db)
    token = _token(db, contact, "space-2")
    inquiry = _inquiry(db, contact, "space-1")
    att = _attachment(db)
    _link(db, att, "stock_inquiry", inquiry.id)

    res = c.get(_url(att.id), headers={"X-Portal-Token": token.token})
    assert res.status_code == 404, res.text


def test_unknown_attachment_is_404(client):
    c, db = client
    contact = _contact(db)
    token = _token(db, contact, "space-1")
    _inquiry(db, contact, "space-1")

    res = c.get(_url(str(uuid.uuid4())), headers={"X-Portal-Token": token.token})
    assert res.status_code == 404, res.text


def test_malformed_attachment_id_is_404_not_500(client):
    c, db = client
    contact = _contact(db)
    token = _token(db, contact, "space-1")

    res = c.get(_url("not-a-uuid"), headers={"X-Portal-Token": token.token})
    assert res.status_code == 404, res.text


def test_attachment_linked_to_nothing_is_404(client):
    """An orphan attachment (no link) belongs to no submission - never readable."""
    c, db = client
    contact = _contact(db)
    token = _token(db, contact, "space-1")
    _inquiry(db, contact, "space-1")
    att = _attachment(db)

    res = c.get(_url(att.id), headers={"X-Portal-Token": token.token})
    assert res.status_code == 404, res.text


def test_attachment_on_a_non_portal_entity_is_404(client):
    """A link on an entity type the portal does not serve grants nothing."""
    c, db = client
    contact = _contact(db)
    token = _token(db, contact, "space-1")
    att = _attachment(db)
    _link(db, att, "product", str(uuid.uuid4()))

    res = c.get(_url(att.id), headers={"X-Portal-Token": token.token})
    assert res.status_code == 404, res.text


def test_download_requires_a_token(client):
    c, db = client
    contact = _contact(db)
    inquiry = _inquiry(db, contact, "space-1")
    att = _attachment(db)
    _link(db, att, "stock_inquiry", inquiry.id)

    res = c.get(_url(att.id))
    assert res.status_code == 401, res.text
