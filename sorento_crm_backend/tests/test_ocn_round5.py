"""OCN-ORDER-CHANGE-NOTICE round 5 (review / security round 2, lead rulings), pinned.

- N1: a raiser notice per move, never swallowed within one revision.
- N3: a file uploaded straight onto the notice, by whoever may edit it; refused for a viewer,
  another company's notice, a bad type or an oversized file.
- N4 / L5: picking an approved notice needs the Revise right; reopening it writes a History line
  and tells the raiser and the approver.
- N6: a view_own raiser edits and deletes their own comment and gets the thread's mail.

Postgres only, every row seeded.
"""
from __future__ import annotations

import io

import pytest

from app.services.error_handler import AppException

from ._forms_chain_support import SORENTO, grant, notifications, user, world  # noqa: F401
from ._ocn_support import (  # noqa: F401  (fixtures)
    EDIT,
    KIND,
    OCN,
    VIEW,
    create,
    get,
    load,
    move,
    ocn,
    ok,
    payload,
    sla,
    submitted,
    svc,
)
from .test_ocn_amendment_link import _create, _crm_ocn, _set, build  # noqa: F401

COMMENTS = f"/api/v1/form-comments/{KIND}"


# ================================================================== N1


def test_r5_two_send_backs_in_one_revision_are_two_notices(ocn, sla):
    d = submitted(ocn)
    ok(move(ocn, d["id"], "reject-submitted", ocn.sales_admin, json={"reason": "Add the PO copy"}))
    ok(move(ocn, d["id"], "submit", ocn.raiser))
    ok(move(ocn, d["id"], "reject-submitted", ocn.sales_admin, json={"reason": "Still no PO copy"}))
    assert load(ocn, d["id"]).revision_no == 0  # same revision throughout
    got = notifications(ocn.db, ocn.raiser, event_type="order_change_notice_reject_submitted")
    assert len(got) == 2
    assert {"Add the PO copy" in n.body for n in got} == {True, False}


# ================================================================== N3 upload


@pytest.fixture
def store(monkeypatch, ocn):
    from ._npa_v4_support import install_storage, seed_attachment_type

    seed_attachment_type(ocn.db)
    ocn.db.commit()
    return install_storage(monkeypatch)


def _upload(o, ocn_id, user_id, name="revised-po.pdf", data=b"%PDF-1.4 revised", mime="application/pdf"):
    return o.as_(user_id).post(
        f"{OCN}/{ocn_id}/attachments/upload", files={"file": (name, io.BytesIO(data), mime)}
    )


def test_r5_the_raiser_uploads_the_revised_po_onto_the_notice(ocn, store):
    d = create(ocn)
    res = _upload(ocn, d["id"], ocn.raiser)
    assert res.status_code == 201, res.text
    files = ok(get(ocn, d["id"]))["attachments"]
    assert [f["filename"] for f in files] == ["revised-po.pdf"]
    assert any(key.startswith(f"order_change_notices/{d['id']}/") for key in store.files)


def test_r5_an_editor_uploads_too(ocn, store):
    d = create(ocn)
    assert _upload(ocn, d["id"], ocn.sales_admin).status_code == 201


def test_r5_a_view_only_user_cannot_upload(ocn, store):
    d = create(ocn)
    assert _upload(ocn, d["id"], ocn.viewer).status_code == 403
    assert ok(get(ocn, d["id"]))["attachments"] == []


def test_r5_another_companys_notice_is_not_found(ocn, store):
    from .test_ocn_routes import _other_company_ocn

    row = _other_company_ocn(ocn)
    assert _upload(ocn, row.id, ocn.sales_admin).status_code == 404


def test_r5_a_submitted_notice_takes_no_upload(ocn, store):
    d = submitted(ocn)
    assert _upload(ocn, d["id"], ocn.raiser).status_code == 409


def test_r5_a_file_type_the_type_does_not_allow_is_refused(ocn, store):
    d = create(ocn)
    res = _upload(ocn, d["id"], ocn.raiser, name="run.exe", data=b"MZ", mime="application/octet-stream")
    assert res.status_code in (400, 422), res.text
    assert ok(get(ocn, d["id"]))["attachments"] == []


def test_r5_an_oversized_file_is_refused(ocn, store):
    from app.models.resources import AttachmentType

    kind = ocn.db.query(AttachmentType).filter(AttachmentType.code == "response_attachment").one()
    kind.max_file_size_mb = 1
    ocn.db.commit()
    d = create(ocn)
    res = _upload(ocn, d["id"], ocn.raiser, data=b"%PDF" + b"x" * (1024 * 1024 + 10))
    assert res.status_code in (400, 422), res.text
    assert ok(get(ocn, d["id"]))["attachments"] == []


# ================================================================== N4 / L5


def _approved_crm_ocn(b, raiser, approver):
    mine = _crm_ocn(b, b.project.id)
    _set(b, mine.id, status="approved", approval_status="approved", approver_id=approver,
         created_by=raiser, revision_no=0)
    return mine


def test_r5_picking_an_approved_notice_needs_the_revise_right(build):
    b = build
    raiser = user(b.db, "OCN pick raiser")
    approver = user(b.db, "OCN pick approver")
    mine = _approved_crm_ocn(b, raiser, approver)
    with pytest.raises(AppException) as exc:  # the author holds only .view
        _create(b, ocn_id=mine.id)
    assert exc.value.status_code == 403
    assert "approved" in exc.value.message
    b.db.expire_all()
    assert b.db.get(type(mine), mine.id).status == "approved"


def test_r5_reopening_writes_history_and_tells_the_raiser_and_the_approver(build):
    from app.models.audit import AuditLog
    from app.services import order_change_notice_service as ocn_svc

    b = build
    grant(b.db, b.owner, EDIT)
    raiser = user(b.db, "OCN pick raiser")
    approver = user(b.db, "OCN pick approver")
    grant(b.db, raiser, VIEW)
    grant(b.db, approver, VIEW)
    mine = _approved_crm_ocn(b, raiser, approver)
    _create(b, ocn_id=mine.id)
    b.db.expire_all()
    assert b.db.get(type(mine), mine.id).status == "draft"
    lines = b.db.query(AuditLog).filter(AuditLog.entity_type == KIND, AuditLog.entity_id == str(mine.id)).all()
    assert any(r.description == ocn_svc.REOPENED_REASON for r in lines)
    for who in (raiser, approver):
        got = notifications(b.db, who, event_type="order_change_notice_reopened")
        assert len(got) == 1, who
        assert "went back for approval" in got[0].title


def test_r5_the_refusals_name_each_case(build):
    b = build
    waiting = _crm_ocn(b, b.project.id)
    _set(b, waiting.id, status="submitted", approval_status="pending")
    with pytest.raises(AppException) as exc:
        _create(b, ocn_id=waiting.id)
    assert "waiting for approval" in exc.value.message
    first = _create(b)
    with pytest.raises(AppException) as exc:
        _create(b, ocn_id=first["ocn_id"])
    assert "already linked" in exc.value.message


# ================================================================== N6 comments


def test_r5_a_view_own_raiser_edits_and_deletes_their_own_comment(ocn):
    from app.services.form_comment_service import FormCommentService

    d = create(ocn, user_id=ocn.own, sales_in_charge_user_id=None, cs_in_charge_user_id=None)
    ok(move(ocn, d["id"], "submit", ocn.own))
    posted = ocn.as_(ocn.own).post(f"{COMMENTS}/{d['id']}", data={"body": "Checked with site"})
    assert posted.status_code == 201, posted.text
    comment_id = posted.json()["comment"]["id"]
    edited = ocn.as_(ocn.own).patch(f"{COMMENTS}/{d['id']}/comments/{comment_id}", json={"body": "Site confirmed"})
    assert edited.status_code == 200, edited.text
    FormCommentService(ocn.db).assert_staff_may_delete(comment_id, ocn.own)  # no refusal


def test_r5_the_view_own_raiser_gets_the_threads_mail(ocn):
    from app.models.notification import Notification
    from app.models.user import User

    d = create(ocn, user_id=ocn.own, sales_in_charge_user_id=None, cs_in_charge_user_id=None)
    ok(move(ocn, d["id"], "submit", ocn.own))
    posted = ocn.as_(ocn.sales_admin).post(f"{COMMENTS}/{d['id']}", data={"body": "Need the revised PO"})
    assert posted.status_code == 201, posted.text
    ocn.db.expire_all()
    mail = (
        ocn.db.query(Notification)
        .filter(Notification.type == "form_comment_notification", Notification.source_entity_id == d["id"])
        .all()
    )
    raiser_email = ocn.db.query(User).filter(User.id == ocn.own).one().email
    assert mail and raiser_email in mail[0].data["recipient_emails"]
    sender_email = ocn.db.query(User).filter(User.id == ocn.sales_admin).one().email
    assert sender_email not in mail[0].data["recipient_emails"]
