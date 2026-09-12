"""Review round 2 (r8): a price tag request's attachment routes must respect
the same editability gate the header PUT already enforces
(``portal_price_tag._require_editable``) - not ownership alone.

Today neither ``POST /public/portal/attachments`` nor
``DELETE /public/portal/attachments/{link_id}`` check the request's status at
all for ``kind=price_tag_request`` (``_require_own_price_tag_request`` is an
ownership check only), so uploading or deleting a file on a locked request
(e.g. ``approved``) succeeds where it should 409.

Fixture pattern: ``tests/test_price_tag_request_portal_attachments.py``.
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves the circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.access import RespondContact
from app.models.entity_attachment import EntityAttachmentLink
from app.models.portal import PortalToken
from app.models.resources import Attachment, AttachmentType
from app.services.portal_service import PORTAL_ATTACHMENT_TYPE_CODE
from app.services.price_tag_request_service import PriceTagRequestService
from tests._pg_fixture import blank_session, unique_code

_SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"
_ATTACHMENTS_BASE = "/api/v1/public/portal/attachments"


class _FakeStorageBackend:
    def upload_file(self, *args, **kwargs):
        key = args[1] if len(args) > 1 else kwargs.get("file_path")
        return key, f"https://cdn.test/{key}"

    def download_file(self, key: str) -> bytes:
        return b"zzt-file-bytes"


@pytest.fixture
def client(monkeypatch):
    from app.database import get_db
    import app.services.storage_router as storage_router

    with blank_session() as db:
        db.add(
            AttachmentType(
                id=str(uuid.uuid4()),
                code=PORTAL_ATTACHMENT_TYPE_CODE,
                type_name="Portal Submission",
                allowed_extensions="jpg,jpeg,png,pdf",
                max_file_size_mb=10,
            )
        )
        db.commit()

        fake_backend = _FakeStorageBackend()
        monkeypatch.setattr(storage_router, "default_provider", lambda: "s3")
        monkeypatch.setattr(storage_router, "get_backend", lambda provider: fake_backend)
        monkeypatch.setattr(
            storage_router, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}"
        )

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app) as c:
                yield c, db
        finally:
            app.dependency_overrides.clear()


def _contact(db: Session) -> RespondContact:
    from app.models.access import ContactAccessType, respond_contact_access_types

    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number=f"+60{uuid.uuid4().hex[:9]}", name="ZZT Contact"
    )
    db.add(contact)
    db.flush()
    access_type = ContactAccessType(
        code=unique_code("at"),
        name=unique_code("Access Type"),
        portal_form_types=["price_tag_request"],
    )
    db.add(access_type)
    db.flush()
    db.execute(
        respond_contact_access_types.insert().values(
            contact_id=contact.id,
            access_type_code=access_type.code,
        )
    )
    db.commit()
    return contact


def _token(db: Session, contact: RespondContact) -> PortalToken:
    t = PortalToken(
        id=str(uuid.uuid4()),
        token=f"tok-{uuid.uuid4().hex}",
        contact_id=contact.id,
        space_id="zzt-space",
        expires_at=datetime.utcnow() + timedelta(days=30),
        verified_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add(t)
    db.commit()
    return t


def _request(
    db: Session, contact_id: str, *, status: str = "new", portal_draft_at=None
):
    """A price tag request seeded straight to the given status/draft state -
    same shortcut ``tests/test_portal_price_tag_edit.py::_force_status`` uses,
    inlined here since this file needs no other helper from that suite."""
    req = PriceTagRequestService.create_request(
        db,
        contact_id=contact_id,
        company_id=_SORENTO_COMPANY_ID,
        data={"debtor_name": unique_code("ZZT Dealer")},
    )
    req.status = status
    req.portal_draft_at = portal_draft_at
    db.commit()
    return req


class TestAttachmentRoutesRefuseWhenNotEditable:
    def test_attachment_upload_and_delete_refused_when_not_editable(self, client):
        c, db = client
        contact = _contact(db)
        token = _token(db, contact)

        # Locked: approved, not a draft - _require_editable would refuse a PUT here.
        locked_req = _request(db, contact.id, status="approved", portal_draft_at=None)

        upload_res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "price_tag_request", "submission_id": locked_req.id},
            files={"file": ("po.pdf", io.BytesIO(b"%PDF-1.4 zzt"), "application/pdf")},
            headers={"X-Portal-Token": token.token},
        )
        assert upload_res.status_code == 409, upload_res.text

        # A pre-existing link on the same locked request, for the delete half.
        att = Attachment(
            id=str(uuid.uuid4()),
            original_filename="ZZT-existing.pdf",
            stored_filename="ZZT-existing.pdf",
            file_path=f"portal/zzt/{uuid.uuid4()}.pdf",
            mime_type="application/pdf",
            uploader_kind="contact",
            uploaded_by_contact_id=contact.id,
        )
        db.add(att)
        db.flush()
        link = EntityAttachmentLink(
            entity_type="price_tag_request", entity_id=locked_req.id, attachment_id=att.id
        )
        db.add(link)
        db.commit()

        delete_res = c.delete(
            f"{_ATTACHMENTS_BASE}/{link.id}",
            headers={"X-Portal-Token": token.token},
        )
        assert delete_res.status_code == 409, delete_res.text

        # Editable: status new, portal_draft_at cleared (post-submit edit
        # window) - the same calls must still succeed here.
        editable_req = _request(db, contact.id, status="new", portal_draft_at=None)

        ok_upload_res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "price_tag_request", "submission_id": editable_req.id},
            files={"file": ("po2.pdf", io.BytesIO(b"%PDF-1.4 zzt"), "application/pdf")},
            headers={"X-Portal-Token": token.token},
        )
        assert ok_upload_res.status_code == 200, ok_upload_res.text

        ok_link_id = ok_upload_res.json()["link_id"]
        ok_delete_res = c.delete(
            f"{_ATTACHMENTS_BASE}/{ok_link_id}",
            headers={"X-Portal-Token": token.token},
        )
        # The generic attachment DELETE answers 200, not 204 (see
        # test_price_tag_request_portal_attachments.py::
        # test_delete_own_upload_removes_the_link).
        assert ok_delete_res.status_code == 200, ok_delete_res.text
