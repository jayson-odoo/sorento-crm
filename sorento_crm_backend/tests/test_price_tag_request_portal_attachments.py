"""Portal PO attachments for price tag requests (PLAN-price-tag-feedback-r2 S1).

``price_tag_request`` is not in ``SUPPORTED_TYPES`` - it has its own dedicated
router (``portal_price_tag.py``), not the generic ``PortalService`` CRUD - so the
shared ``/portal/attachments`` routes need their own kind check and their own
ownership check (against ``PriceTagRequest.contact_id``, not
``PortalService.get_submission``) before they will serve it at all (AC-S1-4).

Fixture pattern for the storage mock: ``test_portal_attachment_attribution_and_lock.py``.
Fixture pattern for seeding a request directly: ``test_portal_price_tag_routes.py``.
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


def _contact(
    db: Session, *, name: str = "ZZT Contact", visible: bool = True
) -> RespondContact:
    """A portal contact. ``visible=True`` (the default - most tests in this
    file are about OWNERSHIP, not visibility) grants price_tag_request access
    the same way a real access-type assignment would; pass ``visible=False``
    for the tests that are specifically about a contact who lacks it."""
    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=name
    )
    db.add(contact)
    db.flush()
    if visible:
        _grant_price_tag_visibility(db, contact.id)
    return contact


def _token(db: Session, contact: RespondContact, *, space_id: str = "zzt-space") -> PortalToken:
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


def _grant_price_tag_visibility(db: Session, contact_id: str) -> None:
    """Access-type grant the portal detail route checks (``_assert_visible`` in
    portal_price_tag.py) before it will answer at all - separate from the
    ownership check this file is mostly about."""
    from app.models.access import ContactAccessType, respond_contact_access_types

    access_type = ContactAccessType(
        code=unique_code("at"),
        name=unique_code("Access Type"),
        portal_form_types=["price_tag_request"],
    )
    db.add(access_type)
    db.flush()
    db.execute(
        respond_contact_access_types.insert().values(
            contact_id=contact_id,
            access_type_code=access_type.code,
        )
    )
    db.commit()


def _request(db: Session, contact_id: str, **fields):
    req = PriceTagRequestService.create_request(
        db,
        contact_id=contact_id,
        company_id=_SORENTO_COMPANY_ID,
        data={"debtor_name": unique_code("ZZT Dealer"), **fields},
    )
    db.commit()
    return req


def _link_attachment(
    db: Session,
    request_id: str,
    *,
    filename: str = "ZZT-po.pdf",
    uploader_kind: str | None = "contact",
    uploaded_by_contact_id: str | None = None,
    uploaded_by: str | None = None,
) -> tuple[str, str]:
    """A pre-existing attachment linked straight to a price_tag_request entity,
    for tests that read the list/detail/download routes without exercising the
    upload route itself. Returns (link_id, attachment_id)."""
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=f"portal/zzt/{uuid.uuid4()}.pdf",
        mime_type="application/pdf",
        uploader_kind=uploader_kind,
        uploaded_by_contact_id=uploaded_by_contact_id,
        uploaded_by=uploaded_by,
    )
    db.add(att)
    db.flush()
    link = EntityAttachmentLink(
        entity_type="price_tag_request", entity_id=request_id, attachment_id=att.id
    )
    db.add(link)
    db.commit()
    return str(link.id), str(att.id)


# ---------------------------------------------------------------------------
# AC-S1-4: upload, ownership 404
# ---------------------------------------------------------------------------


class TestUpload:
    def test_upload_stores_via_entity_attachment_service_and_answers_the_legacy_shape(
        self, client
    ):
        c, db = client
        contact = _contact(db)
        token = _token(db, contact)
        req = _request(db, contact.id)

        res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "price_tag_request", "submission_id": req.id},
            files={"file": ("po.pdf", io.BytesIO(b"%PDF-1.4 zzt"), "application/pdf")},
            headers={"X-Portal-Token": token.token},
        )

        assert res.status_code == 200, res.text
        body = res.json()
        # The legacy kinds' shape (AC-S1-4): every one of these keys, not a
        # partial answer that the FE would have to special-case.
        for key in ("link_id", "attachment_id", "filename", "size", "url", "content_type"):
            assert key in body, f"missing {key!r} in {body!r}"
        assert body["filename"] == "po.pdf"
        assert body["content_type"] == "application/pdf"

        link = (
            db.query(EntityAttachmentLink)
            .filter(EntityAttachmentLink.id == body["link_id"])
            .first()
        )
        assert link is not None
        assert link.entity_type == "price_tag_request"
        assert link.entity_id == req.id

        att = db.query(Attachment).filter(Attachment.id == body["attachment_id"]).first()
        assert att is not None
        assert att.uploader_kind == "contact"
        assert att.uploaded_by_contact_id == contact.id

    def test_upload_with_an_oversized_content_type_does_not_crash(self, client):
        """attachments.mime_type is VARCHAR(100) and the Content-Type header is
        caller-controlled - an oversized value must not 500 (or crash the
        whole upload) on any kind, price_tag_request included."""
        c, db = client
        contact = _contact(db)
        token = _token(db, contact)
        req = _request(db, contact.id)

        oversized_content_type = "application/pdf; name=\"" + ("z" * 200) + ".pdf\""
        assert len(oversized_content_type) > 100

        res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "price_tag_request", "submission_id": req.id},
            files={"file": ("po.pdf", io.BytesIO(b"x"), oversized_content_type)},
            headers={"X-Portal-Token": token.token},
        )

        assert res.status_code == 200, res.text
        stored_content_type = res.json()["content_type"]
        assert stored_content_type is not None
        assert len(stored_content_type) <= 100
        # The type/subtype survives; only the parameters are cut.
        assert stored_content_type.startswith("application/pdf")

    def test_upload_refuses_a_request_the_contact_does_not_own_with_404(self, client):
        """AC-S1-4: not-owned is 404, never 403 - the route must not confirm an
        id the token has no claim on."""
        c, db = client
        owner = _contact(db, name="ZZT Owner")
        stranger = _contact(db, name="ZZT Stranger")
        stranger_token = _token(db, stranger)
        req = _request(db, owner.id)

        res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "price_tag_request", "submission_id": req.id},
            files={"file": ("po.pdf", io.BytesIO(b"x"), "application/pdf")},
            headers={"X-Portal-Token": stranger_token.token},
        )

        assert res.status_code == 404, res.text

    def test_upload_refuses_a_nonexistent_request_with_404(self, client):
        c, db = client
        contact = _contact(db)
        token = _token(db, contact)

        res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "price_tag_request", "submission_id": str(uuid.uuid4())},
            files={"file": ("po.pdf", io.BytesIO(b"x"), "application/pdf")},
            headers={"X-Portal-Token": token.token},
        )

        assert res.status_code == 404, res.text

    def test_upload_refuses_a_malformed_submission_id_with_404_not_500(self, client):
        c, db = client
        contact = _contact(db)
        token = _token(db, contact)

        res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "price_tag_request", "submission_id": "not-a-uuid"},
            files={"file": ("po.pdf", io.BytesIO(b"x"), "application/pdf")},
            headers={"X-Portal-Token": token.token},
        )

        assert res.status_code == 404, res.text

    def test_an_unrelated_kind_is_still_refused(self, client):
        """The widened kind check must not become a blanket bypass - only
        price_tag_request joins SUPPORTED_TYPES for the attachment routes."""
        c, db = client
        contact = _contact(db)
        token = _token(db, contact)

        res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "not_a_real_kind", "submission_id": str(uuid.uuid4())},
            files={"file": ("po.pdf", io.BytesIO(b"x"), "application/pdf")},
            headers={"X-Portal-Token": token.token},
        )

        assert res.status_code == 400, res.text


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class TestList:
    def test_list_answers_with_the_legacy_shape(self, client):
        c, db = client
        contact = _contact(db)
        token = _token(db, contact)
        req = _request(db, contact.id)
        _link_attachment(
            db, req.id, uploader_kind="contact", uploaded_by_contact_id=contact.id
        )

        res = c.get(
            _ATTACHMENTS_BASE,
            params={"kind": "price_tag_request", "submission_id": req.id},
            headers={"X-Portal-Token": token.token},
        )

        assert res.status_code == 200, res.text
        items = res.json()["items"]
        assert len(items) == 1
        assert items[0]["filename"] == "ZZT-po.pdf"
        assert items[0]["content_type"] == "application/pdf"
        assert items[0]["can_unlink"] is True

    def test_list_refuses_a_request_the_contact_does_not_own_with_404(self, client):
        c, db = client
        owner = _contact(db, name="ZZT Owner")
        stranger = _contact(db, name="ZZT Stranger")
        stranger_token = _token(db, stranger)
        req = _request(db, owner.id)

        res = c.get(
            _ATTACHMENTS_BASE,
            params={"kind": "price_tag_request", "submission_id": req.id},
            headers={"X-Portal-Token": stranger_token.token},
        )

        assert res.status_code == 404, res.text


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_own_upload_removes_the_link(self, client):
        c, db = client
        contact = _contact(db)
        token = _token(db, contact)
        req = _request(db, contact.id)
        link_id, _attachment_id = _link_attachment(
            db, req.id, uploader_kind="contact", uploaded_by_contact_id=contact.id
        )

        res = c.delete(
            f"{_ATTACHMENTS_BASE}/{link_id}", headers={"X-Portal-Token": token.token}
        )

        assert res.status_code == 200, res.text
        assert (
            db.query(EntityAttachmentLink).filter(EntityAttachmentLink.id == link_id).first()
            is None
        )

    def test_delete_refuses_a_link_on_someone_elses_request_with_404(self, client):
        c, db = client
        owner = _contact(db, name="ZZT Owner")
        stranger = _contact(db, name="ZZT Stranger")
        stranger_token = _token(db, stranger)
        req = _request(db, owner.id)
        link_id, _attachment_id = _link_attachment(
            db, req.id, uploader_kind="contact", uploaded_by_contact_id=owner.id
        )

        res = c.delete(
            f"{_ATTACHMENTS_BASE}/{link_id}", headers={"X-Portal-Token": stranger_token.token}
        )

        assert res.status_code == 404, res.text
        assert (
            db.query(EntityAttachmentLink).filter(EntityAttachmentLink.id == link_id).first()
            is not None
        )


# ---------------------------------------------------------------------------
# Download bytes (backs the FE's in-place preview + Download button)
# ---------------------------------------------------------------------------


class TestDownload:
    def test_owner_can_read_the_bytes(self, client):
        c, db = client
        contact = _contact(db)
        token = _token(db, contact)
        req = _request(db, contact.id)
        _link_id, attachment_id = _link_attachment(
            db, req.id, uploader_kind="contact", uploaded_by_contact_id=contact.id
        )

        res = c.get(
            f"{_ATTACHMENTS_BASE}/{attachment_id}/download",
            headers={"X-Portal-Token": token.token},
        )

        assert res.status_code == 200, res.text

    def test_a_non_owner_gets_404_not_the_bytes(self, client):
        c, db = client
        owner = _contact(db, name="ZZT Owner")
        stranger = _contact(db, name="ZZT Stranger")
        stranger_token = _token(db, stranger)
        req = _request(db, owner.id)
        _link_id, attachment_id = _link_attachment(
            db, req.id, uploader_kind="contact", uploaded_by_contact_id=owner.id
        )

        res = c.get(
            f"{_ATTACHMENTS_BASE}/{attachment_id}/download",
            headers={"X-Portal-Token": stranger_token.token},
        )

        assert res.status_code == 404, res.text


# ---------------------------------------------------------------------------
# Visibility gate parity with portal_price_tag.py's dedicated CRUD routes:
# revoking a contact's price_tag_request grant has to close the attachment
# routes too, not just the ones portal_price_tag.py itself owns.
# ---------------------------------------------------------------------------


class TestVisibilityGate:
    def test_upload_is_refused_without_the_form_type_grant(self, client):
        c, db = client
        contact = _contact(db, visible=False)
        token = _token(db, contact)
        req = _request(db, contact.id)

        res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "price_tag_request", "submission_id": req.id},
            files={"file": ("po.pdf", io.BytesIO(b"x"), "application/pdf")},
            headers={"X-Portal-Token": token.token},
        )

        assert res.status_code == 403, res.text

    def test_list_is_refused_without_the_form_type_grant(self, client):
        c, db = client
        contact = _contact(db, visible=False)
        token = _token(db, contact)
        req = _request(db, contact.id)

        res = c.get(
            _ATTACHMENTS_BASE,
            params={"kind": "price_tag_request", "submission_id": req.id},
            headers={"X-Portal-Token": token.token},
        )

        assert res.status_code == 403, res.text

    def test_delete_is_refused_without_the_form_type_grant(self, client):
        c, db = client
        contact = _contact(db, visible=False)
        token = _token(db, contact)
        req = _request(db, contact.id)
        link_id, _attachment_id = _link_attachment(
            db, req.id, uploader_kind="contact", uploaded_by_contact_id=contact.id
        )

        res = c.delete(
            f"{_ATTACHMENTS_BASE}/{link_id}", headers={"X-Portal-Token": token.token}
        )

        assert res.status_code == 403, res.text


# ---------------------------------------------------------------------------
# AC-S1-5 (portal half): the detail route answers with real attachments
# ---------------------------------------------------------------------------


class TestPortalDetailCarriesAttachments:
    def test_the_detail_route_lists_uploaded_attachments(self, client):
        c, db = client
        contact = _contact(db)
        token = _token(db, contact)
        req = _request(db, contact.id)
        _link_attachment(
            db, req.id, filename="ZZT-quote.pdf", uploader_kind="contact",
            uploaded_by_contact_id=contact.id,
        )

        res = c.get(
            f"/api/v1/public/portal/submissions/price_tag_request/{req.id}",
            headers={"X-Portal-Token": token.token},
        )

        assert res.status_code == 200, res.text
        attachments = res.json()["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["filename"] == "ZZT-quote.pdf"
        assert attachments[0]["content_type"] == "application/pdf"
        assert "url" in attachments[0]

    def test_a_request_with_no_attachments_still_answers_with_an_empty_list(self, client):
        c, db = client
        contact = _contact(db)
        token = _token(db, contact)
        req = _request(db, contact.id)

        res = c.get(
            f"/api/v1/public/portal/submissions/price_tag_request/{req.id}",
            headers={"X-Portal-Token": token.token},
        )

        assert res.status_code == 200, res.text
        assert res.json()["attachments"] == []
