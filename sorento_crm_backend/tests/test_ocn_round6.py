"""OCN-ORDER-CHANGE-NOTICE round 6 (security review round 3, lead rulings), pinned.

- M4: picking an approved notice for an amendment tells the raiser and the approver only once
  the amendment commits. A failed amendment tells nobody and leaves the notice approved.
- M5: a file uploaded onto a notice (straight onto it, or in its Conversation) belongs to the
  notice's company, so another company's attachment library cannot list, open or link it.

Postgres only, every row seeded.
"""
from __future__ import annotations

import io

import pytest

from app.models.project_so import OrderChangeNotice, SOAmendment
from app.services.error_handler import AppException

from ._forms_chain_support import SORENTO, grant, notifications, user, world  # noqa: F401
from ._ocn_support import (  # noqa: F401  (fixtures)
    EDIT,
    KIND,
    OCN,
    VIEW,
    create,
    ocn,
    sla,
    submitted,
    svc,
)
from .test_ocn_amendment_link import _crm_ocn, _set, build  # noqa: F401

REOPENED = "order_change_notice_reopened"


# ================================================================== M4


def _approved_pick(b):
    grant(b.db, b.owner, EDIT)
    raiser = user(b.db, "OCN r6 raiser")
    approver = user(b.db, "OCN r6 approver")
    grant(b.db, raiser, VIEW)
    grant(b.db, approver, VIEW)
    mine = _crm_ocn(b, b.project.id)
    _set(b, mine.id, status="approved", approval_status="approved", approver_id=approver,
         created_by=raiser, revision_no=0)
    b.db.commit()  # the seed is durable, so the route's own rollback cannot take it
    return mine, raiser, approver


def _route_create(b, ocn_id):
    """The amendment create ROUTE (`POST /sales-orders/{id}/amendments`), its commit and its
    after-commit step included, called in-process."""
    from app.api.v1.projects.sales_orders import create_amendment
    from app.schemas.project_sales_order import AmendmentCreateRequest

    payload = AmendmentCreateRequest(
        schedule_version_id=b.r2.id, reason="Main contractor pushed the programme.", ocn_id=ocn_id,
    )
    return create_amendment(str(b.orders["TOWER"].id), payload, current_user={"id": b.owner}, db=b.db)


def test_r6_a_failed_amendment_leaves_the_notice_approved_and_tells_nobody(build, monkeypatch):
    from app.services.project_so_delta_service import ProjectSODeltaService

    b = build
    mine, raiser, approver = _approved_pick(b)
    real = ProjectSODeltaService._persist_amendment

    def link_then_fail(self, *args, **kwargs):
        real(self, *args, **kwargs)  # the pick has run: notice reset, amendment flushed
        raise AppException(status_code=409, message="Simulated failure after the link.")

    monkeypatch.setattr(ProjectSODeltaService, "_persist_amendment", link_then_fail)
    with pytest.raises(AppException):
        _route_create(b, mine.id)
    b.db.expire_all()
    row = b.db.get(OrderChangeNotice, mine.id)
    assert row.status == "approved"
    assert row.approval_status == "approved"
    assert row.revision_no == 0
    assert b.db.query(SOAmendment).filter(SOAmendment.ocn_id == mine.id).count() == 0
    for who in (raiser, approver):
        assert notifications(b.db, who, event_type=REOPENED) == [], who


def test_r6_a_landed_amendment_tells_the_two_after_its_commit(build, monkeypatch):
    from app.services import order_change_notice_service as ocn_svc

    b = build
    mine, raiser, approver = _approved_pick(b)
    seen: list[bool] = []
    real = ocn_svc._tell

    def tell_and_check(db, row, event, *args, **kwargs):
        if event == "reopened":  # the amendment must already be durable when the notice goes
            seen.append(db.query(SOAmendment).filter(SOAmendment.ocn_id == row.id).count() == 1
                        and not db.new and not db.dirty)
        return real(db, row, event, *args, **kwargs)

    monkeypatch.setattr(ocn_svc, "_tell", tell_and_check)
    body = _route_create(b, mine.id)
    assert body["ocn_id"] == mine.id
    assert seen == [True]
    for who in (raiser, approver):
        got = notifications(b.db, who, event_type=REOPENED)
        assert len(got) == 1, who
        assert "went back for approval" in got[0].title
    assert b.db.get(OrderChangeNotice, mine.id).status == "draft"


def test_r6_the_service_alone_sends_nothing_before_the_commit(build):
    """Below the route, the pick holds its notices until `run_after_commit`."""
    from app.services.project_so_delta_service import ProjectSODeltaService

    b = build
    mine, raiser, approver = _approved_pick(b)
    delta = ProjectSODeltaService(b.db)
    delta.create(b.orders["TOWER"].id, schedule_version_id=b.r2.id,
                 reason="Main contractor pushed the programme.", actor_user_id=b.owner, ocn_id=mine.id)
    assert notifications(b.db, raiser, event_type=REOPENED) == []
    b.db.commit()
    delta.run_after_commit()
    assert len(notifications(b.db, raiser, event_type=REOPENED)) == 1
    assert len(notifications(b.db, approver, event_type=REOPENED)) == 1


# ================================================================== M5


@pytest.fixture
def store(monkeypatch, ocn):
    from ._npa_v4_support import install_storage, seed_attachment_type

    seed_attachment_type(ocn.db)
    ocn.db.commit()
    return install_storage(monkeypatch)


def _attachment(o, attachment_id):
    from app.models.base import company_scope
    from app.models.resources import Attachment

    with company_scope(o.db, None):
        o.db.expire_all()
        return o.db.query(Attachment).filter(Attachment.id == attachment_id).one()


def test_r6_a_file_uploaded_onto_a_notice_carries_its_company(ocn, store):
    d = create(ocn)
    res = ocn.as_(ocn.raiser).post(
        f"{OCN}/{d['id']}/attachments/upload",
        files={"file": ("revised-po.pdf", io.BytesIO(b"%PDF-1.4 revised"), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    assert str(_attachment(ocn, res.json()["attachment_id"]).company_id) == str(SORENTO)


def test_r6_a_file_posted_in_the_notices_conversation_carries_its_company(ocn, store):
    from app.models.entity_attachment import EntityAttachmentLink

    d = submitted(ocn)  # the Conversation opens once the notice is submitted
    posted = ocn.as_(ocn.raiser).post(
        f"/api/v1/form-comments/{KIND}/{d['id']}",
        data={"body": "The revised PO"},
        files={"files": ("revised-po.pdf", io.BytesIO(b"%PDF-1.4 revised"), "application/pdf")},
    )
    assert posted.status_code == 201, posted.text
    comment_id = posted.json()["comment"]["id"]
    link = ocn.db.query(EntityAttachmentLink).filter(EntityAttachmentLink.entity_id == str(comment_id)).one()
    assert str(_attachment(ocn, link.attachment_id).company_id) == str(SORENTO)


def test_r6_a_complaint_style_upload_stays_shared(ocn, store):
    """Other callers of the shared helper keep today's behaviour (no company given)."""
    from app.services.entity_attachment_service import create_response_attachment

    saved = create_response_attachment(
        ocn.db, entity_type="complaint", entity_id="00000000-0000-4000-8000-000000000001",
        contents=b"%PDF-1.4", filename="c.pdf", content_type="application/pdf",
        uploaded_by=ocn.raiser, commit=True, check_quota=False,
    )
    assert _attachment(ocn, saved["attachment_id"]).company_id is None


def test_r6_another_company_cannot_list_open_or_link_a_notice_file(ocn, store):
    from app.main import app
    from app.models.base import company_scope, set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.entity_attachment_service import EntityAttachmentService

    from ._sample_request_seed import second_company

    d = create(ocn)
    res = ocn.as_(ocn.raiser).post(
        f"{OCN}/{d['id']}/attachments/upload",
        files={"file": ("revised-po.pdf", io.BytesIO(b"%PDF-1.4 revised"), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    attachment_id = res.json()["attachment_id"]

    # Same company: the library still finds it (control for the refusals below).
    reader = user(ocn.db, "OCN r6 catalogue reader")
    grant(ocn.db, reader, "resource.attachments.view")
    listed = ocn.as_(reader).get("/api/v1/resource-management/attachments/", params={"attachment_ids": attachment_id, "limit": 200})
    assert listed.status_code == 200, listed.text
    assert attachment_id in {r["id"] for r in listed.json()["data"]}

    other = second_company(ocn.db)
    ocn.db.commit()
    app.dependency_overrides[apply_company_scope] = lambda: set_company_scope(ocn.db, frozenset({other}))
    listed = ocn.as_(reader).get("/api/v1/resource-management/attachments/", params={"attachment_ids": attachment_id, "limit": 200})
    assert listed.status_code == 200, listed.text
    assert attachment_id not in {r["id"] for r in listed.json()["data"]}
    assert ocn.as_(reader).get(f"/api/v1/resource-management/attachments/{attachment_id}/download").status_code == 404
    assert ocn.as_(reader).get(f"/api/v1/resource-management/attachments/{attachment_id}/preview-url").status_code == 404

    with company_scope(ocn.db, frozenset({other})):
        ocn.db.expire_all()
        with pytest.raises(AppException) as exc:
            EntityAttachmentService(ocn.db).link_existing_attachment(
                entity_type="complaint", entity_id="00000000-0000-4000-8000-000000000002",
                attachment_id=attachment_id,
            )
        assert exc.value.status_code == 404
