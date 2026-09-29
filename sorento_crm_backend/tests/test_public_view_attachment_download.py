"""Public /view attachment bytes route (PR #1256 review, blocking finding 1).

The complaint and stock-inquiry public view pages built preview items from
``file_url`` alone: a signed storage URL (R2/S3/CloudFront) with no CORS headers,
so pdf.js could not read it and the contact saw "This PDF could not be shown
here". This route is the same-origin fix - keyed on the SAME view token the
page itself reads with, same gate shape as the portal's own attachment route
(``tests/test_portal_attachment_download.py``): token -> entity_id -> the
attachment must be linked to that entity, or this 404s exactly like an unknown
attachment id would.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.complaints import Complaint
from app.models.entity_attachment import EntityAttachmentLink
from app.models.procurement import StockInquiry, ViewToken
from app.models.resources import Attachment
from tests._pg_fixture import blank_session

FILE_BYTES = b"public-view-attachment-bytes"


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


def _complaint(db: Session) -> Complaint:
    row = Complaint(id=str(uuid.uuid4()), complaint_number=f"ZZT-{uuid.uuid4().hex[:8]}")
    db.add(row)
    db.commit()
    return row


def _stock_inquiry(db: Session) -> StockInquiry:
    row = StockInquiry(
        id=str(uuid.uuid4()),
        inquiry_number=f"ZZT-{uuid.uuid4().hex[:8]}",
        status="pending_purchasing",
    )
    db.add(row)
    db.commit()
    return row


def _view_token(db: Session, entity_type: str, entity_id: str) -> ViewToken:
    t = ViewToken(
        id=str(uuid.uuid4()),
        entity_type=entity_type,
        entity_id=str(entity_id),
        token=f"tok-{uuid.uuid4().hex}",
    )
    db.add(t)
    db.commit()
    return t


def _attachment(db: Session, *, filename="scan.pdf", mime="application/pdf") -> Attachment:
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"https://cdn.test/view/{uuid.uuid4().hex}/{filename}",
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


def _url(entity: str, attachment_id: str, token: str) -> str:
    return f"/api/v1/public/view/{entity}/attachments/{attachment_id}/download?token={token}"


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


def test_complaint_attachment_downloads_by_view_token(client):
    c, db = client
    complaint = _complaint(db)
    token = _view_token(db, "complaint", complaint.id)
    att = _attachment(db)
    _link(db, att, "complaint", complaint.id)

    res = c.get(_url("complaint", att.id, token.token))

    assert res.status_code == 200, res.text
    assert res.content == FILE_BYTES
    assert res.headers["content-type"].startswith("application/pdf")
    assert "scan.pdf" in res.headers.get("content-disposition", "")


def test_stock_inquiry_attachment_downloads_by_view_token(client):
    c, db = client
    inquiry = _stock_inquiry(db)
    token = _view_token(db, "stock_inquiry", inquiry.id)
    att = _attachment(db)
    _link(db, att, "stock_inquiry", inquiry.id)

    res = c.get(_url("stock-inquiry", att.id, token.token))

    assert res.status_code == 200, res.text
    assert res.content == FILE_BYTES


# --------------------------------------------------------------------------
# Denials
# --------------------------------------------------------------------------


def test_unsupported_entity_is_404(client):
    c, db = client
    res = c.get("/api/v1/public/view/request/attachments/%s/download?token=x" % uuid.uuid4())
    assert res.status_code == 404, res.text


def test_unknown_token_is_404(client):
    c, db = client
    complaint = _complaint(db)
    att = _attachment(db)
    _link(db, att, "complaint", complaint.id)

    res = c.get(_url("complaint", att.id, "no-such-token"))
    assert res.status_code == 404, res.text


def test_token_for_a_different_entity_type_is_404(client):
    """A stock-inquiry token can't be replayed against the complaint path."""
    c, db = client
    inquiry = _stock_inquiry(db)
    token = _view_token(db, "stock_inquiry", inquiry.id)
    att = _attachment(db)
    _link(db, att, "stock_inquiry", inquiry.id)

    res = c.get(_url("complaint", att.id, token.token))
    assert res.status_code == 404, res.text


def test_attachment_not_linked_to_the_tokens_entity_is_404(client):
    """Ownership before existence: a real attachment id on someone else's complaint."""
    c, db = client
    complaint = _complaint(db)
    token = _view_token(db, "complaint", complaint.id)
    other_complaint = _complaint(db)
    att = _attachment(db)
    _link(db, att, "complaint", other_complaint.id)

    res = c.get(_url("complaint", att.id, token.token))
    assert res.status_code == 404, res.text


def test_attachment_linked_to_nothing_is_404(client):
    c, db = client
    complaint = _complaint(db)
    token = _view_token(db, "complaint", complaint.id)
    att = _attachment(db)

    res = c.get(_url("complaint", att.id, token.token))
    assert res.status_code == 404, res.text


def test_download_requires_a_token(client):
    c, db = client
    complaint = _complaint(db)
    att = _attachment(db)
    _link(db, att, "complaint", complaint.id)

    res = c.get(f"/api/v1/public/view/complaint/attachments/{att.id}/download")
    assert res.status_code == 422, res.text
