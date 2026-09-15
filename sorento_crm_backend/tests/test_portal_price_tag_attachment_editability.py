"""Round 3 (R3-1): a price tag request's attachment routes must respect the
same gate the header PUT now enforces - a draft, OR while a revision draft
exists for it, refused otherwise. R3-1 reverses S8's ``_require_editable``
(new / changes_requested writable post-submit) back to ``_require_draft``, so
the attachment gate reverses with it: `status=new, portal_draft_at=None` with
NO revision draft in progress must now 409 (S8 had this case succeed), and
only gains attachments back once a revision draft row exists for the request.

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
from tests import _ptag_r9_seed

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


def _seed_revision_config(db: Session, *, enabled: bool = True) -> None:
    from app.models.portal import PortalRevisionConfig
    from app.models.user import SystemSetting

    db.add(
        SystemSetting(id=str(uuid.uuid4()), portal_revisions_enabled=True, portal_max_revisions=2)
    )
    db.add(
        PortalRevisionConfig(
            id=str(uuid.uuid4()),
            source_entity_type="price_tag_request",
            is_enabled=enabled,
            max_revisions=None,
            allowed_statuses=["new", "changes_requested"],
            restart_stage_code=None,
        )
    )
    db.commit()


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

    def test_attachment_routes_refused_at_new_with_no_revision_draft(self, client):
        """R3-1 reverses the S8 case this file used to assert as 200: `status
        new, portal_draft_at=None` with no revision draft in progress is no
        longer editable at all - only a draft (or an in-progress revision
        draft, see the next test) may touch attachments."""
        c, db = client
        contact = _contact(db)
        token = _token(db, contact)

        req = _request(db, contact.id, status="new", portal_draft_at=None)

        upload_res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "price_tag_request", "submission_id": req.id},
            files={"file": ("po2.pdf", io.BytesIO(b"%PDF-1.4 zzt"), "application/pdf")},
            headers={"X-Portal-Token": token.token},
        )
        assert upload_res.status_code == 409, upload_res.text

    def test_attachment_routes_allowed_while_a_revision_draft_exists(self, client):
        """R3-1: a submitted, non-draft request regains attachment writes while
        the contact has an in-progress revision draft for it - the revision
        engine's own draft, not ``portal_draft_at``.

        The gate (``_require_editable``) re-checks the LIVE revision policy
        (gap C fix, 97912eef4), not just the draft row's existence - so the
        policy has to actually allow a revision here: global revisions on,
        and a ``price_tag_request`` config row enabled with ``new`` among its
        allowed statuses (the request's own status), same seeding
        ``test_portal_price_tag_revise.py`` uses.
        """
        from app.models.portal import PortalRevisionConfig, PortalRevisionDraft
        from app.models.user import SystemSetting

        c, db = client
        db.add(SystemSetting(id=str(uuid.uuid4()), portal_revisions_enabled=True, portal_max_revisions=2))
        db.add(
            PortalRevisionConfig(
                id=str(uuid.uuid4()),
                source_entity_type="price_tag_request",
                is_enabled=True,
                max_revisions=None,
                allowed_statuses=["new", "changes_requested"],
                restart_stage_code=None,
            )
        )
        db.commit()
        contact = _contact(db)
        token = _token(db, contact)

        req = _request(db, contact.id, status="new", portal_draft_at=None)
        db.add(
            PortalRevisionDraft(
                id=str(uuid.uuid4()),
                source_entity_type="price_tag_request",
                source_entity_id=req.id,
                contact_id=contact.id,
                base_revision_no=0,
                payload_json={},
            )
        )
        db.commit()

        ok_upload_res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "price_tag_request", "submission_id": req.id},
            files={"file": ("po3.pdf", io.BytesIO(b"%PDF-1.4 zzt"), "application/pdf")},
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


class TestAttachmentGateKeysOffPolicyNotDraftExistence:
    """Review round 3: the gate should key off ``policy.allowed`` for a
    submitted request - a request at a revisable status needs no PARKED
    draft row to accept an attachment, since Send revision itself (no saved
    draft first) is a perfectly normal path. Today ``_require_editable``
    requires ``has_draft AND policy.allowed`` together, so a submitted
    request with the policy enabled but no draft row still 409s."""

    def test_allowed_with_no_draft_row_when_policy_allows(self, client):
        c, db = client
        _seed_revision_config(db, enabled=True)
        contact = _contact(db)
        token = _token(db, contact)
        req = _request(db, contact.id, status="new", portal_draft_at=None)

        upload_res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "price_tag_request", "submission_id": req.id},
            files={"file": ("po.pdf", io.BytesIO(b"%PDF-1.4 zzt"), "application/pdf")},
            headers={"X-Portal-Token": token.token},
        )
        assert upload_res.status_code == 200, upload_res.text

        link_id = upload_res.json()["link_id"]
        delete_res = c.delete(
            f"{_ATTACHMENTS_BASE}/{link_id}",
            headers={"X-Portal-Token": token.token},
        )
        assert delete_res.status_code in (200, 204), delete_res.text

    def test_refused_with_no_draft_row_when_config_disabled(self, client):
        c, db = client
        _seed_revision_config(db, enabled=False)
        contact = _contact(db)
        token = _token(db, contact)
        req = _request(db, contact.id, status="new", portal_draft_at=None)

        upload_res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "price_tag_request", "submission_id": req.id},
            files={"file": ("po.pdf", io.BytesIO(b"%PDF-1.4 zzt"), "application/pdf")},
            headers={"X-Portal-Token": token.token},
        )
        assert upload_res.status_code == 409, upload_res.text

    def test_refused_with_no_draft_row_at_a_status_the_policy_refuses(self, client):
        c, db = client
        _seed_revision_config(db, enabled=True)
        contact = _contact(db)
        token = _token(db, contact)
        req = _request(db, contact.id, status="ready", portal_draft_at=None)

        upload_res = c.post(
            _ATTACHMENTS_BASE,
            data={"kind": "price_tag_request", "submission_id": req.id},
            files={"file": ("po.pdf", io.BytesIO(b"%PDF-1.4 zzt"), "application/pdf")},
            headers={"X-Portal-Token": token.token},
        )
        assert upload_res.status_code == 409, upload_res.text


@pytest.fixture(autouse=True)
def no_respond(monkeypatch):
    """S8: no test run reaches api.respond.io. See `_ptag_r9_seed.block_respond`.

    Every transition here goes through the real notifier, which sends over the
    network unless something stops it - the run log used to carry a live
    ``Window check: Respond.io list_messages failed`` per transition.
    """
    return _ptag_r9_seed.block_respond(monkeypatch)
