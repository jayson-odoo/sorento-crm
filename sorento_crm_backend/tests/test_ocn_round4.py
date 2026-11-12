"""OCN-ORDER-CHANGE-NOTICE round 4: the review and security fixes, pinned (lead rulings).

- Amendment pick (security H1, review M5/M6/m16/m17): the one linkable predicate, the list's
  `linkable=true`, the author's visibility, an approved pick revised back to draft, one amendment
  per notice.
- Grants (security M3): `.process` is Done; `.edit` alone cannot mark done.
- Reader rule (security M2, review M1): a grant is always needed; Conversation, SLA tab and
  History open for a view_own raiser and an approve-only user.
- Permission before the dispatcher parks a move (security M1, review M2).
- Raiser notices (review M3), the one Submit rule set (m2), linked notices keep their project
  (m1), Pending approval filter (m8), approved projects only, line cap, Malaysia today, hidden
  revision config, numbering seeded per company (m5).

Postgres only, every row seeded (tests/_ocn_support.py, tests/test_ocn_amendment_link.py).
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.error_handler import AppException

from ._forms_chain_support import SORENTO, grant, notifications, open_tracker, user, world  # noqa: F401
from ._ocn_support import (  # noqa: F401  (fixtures)
    APPROVE,
    CREATE,
    EDIT,
    KIND,
    OCN,
    PROCESS,
    PROJECT_PANEL,
    VIEW,
    VIEW_OWN,
    approved,
    create,
    get,
    load,
    move,
    ocn,
    ok,
    payload,
    pending,
    rows_of,
    sla,
    submitted,
    svc,
)
from .test_ocn_amendment_link import _create, _crm_ocn, _publish, _set, build  # noqa: F401

FORM_ACTIONS = "/api/v1/sla-management/form-actions"


# ================================================================== the amendment pick


@pytest.mark.parametrize("status", ["draft", "submitted", "resubmitted", "rejected"])
def test_r4_an_open_notice_not_waiting_on_approval_is_pickable(build, status):
    b = build
    mine = _crm_ocn(b, b.project.id)
    _set(b, mine.id, status=status, approval_status="rejected" if status == "rejected" else None)
    created = _create(b, ocn_id=mine.id)
    assert created["ocn_id"] == mine.id


@pytest.mark.parametrize(
    "cols",
    [
        dict(status="submitted", approval_status="pending"),
        dict(status="voided", approval_status=None),
        dict(status="processed_by_cs", approval_status="approved"),
    ],
    ids=["pending_approval", "voided", "done"],
)
def test_r4_pending_voided_and_done_notices_are_not_pickable(build, cols):
    b = build
    mine = _crm_ocn(b, b.project.id)
    _set(b, mine.id, **cols)
    with pytest.raises(AppException) as exc:
        _create(b, ocn_id=mine.id)
    assert exc.value.status_code == 409


def test_r4_picking_an_approved_notice_revises_it_and_publish_waits_for_a_new_approval(build):
    b = build
    # Round 5 ruling (security L5): reopening an approval is the Revise right.
    grant(b.db, b.owner, EDIT)
    mine = _crm_ocn(b, b.project.id)
    _set(b, mine.id, status="approved", approval_status="approved", approver_id=b.owner, revision_no=0)
    created = _create(b, ocn_id=mine.id)
    b.db.expire_all()
    row = b.db.get(type(mine), mine.id)
    assert row.status == "draft"
    assert row.revision_no == 1
    assert (row.approval_status, row.approver_id, row.approved_at) == (None, None, None)
    assert row.change_table_json["verb_summary"]  # the change is on it, to be approved
    with pytest.raises(AppException) as exc:
        _publish(b, created["amendment_id"])
    assert exc.value.status_code == 409


def test_r4_the_author_must_be_able_to_see_the_picked_notice(build):
    b = build
    mine = _crm_ocn(b, b.project.id)
    stranger = user(b.db, "OCN pick stranger")
    from app.services.project_so_delta_service import ProjectSODeltaService

    with pytest.raises(AppException) as exc:
        ProjectSODeltaService(b.db).create(
            b.orders["TOWER"].id, schedule_version_id=b.r2.id,
            reason="Programme pushed.", actor_user_id=stranger, ocn_id=mine.id,
        )
    assert exc.value.status_code in (403, 404)


def test_r4_one_amendment_per_notice_is_enforced_by_the_database(build):
    from app.models.project_so import SOAmendment

    b = build
    first = _create(b)
    nested = b.db.begin_nested()
    b.db.add(SOAmendment(company_id=b.company_id, project_sales_order_id=b.orders["TOWER"].id,
                         ocn_id=first["ocn_id"], status="proposed"))
    with pytest.raises(IntegrityError):
        b.db.flush()
    nested.rollback()


def test_r4_the_project_list_offers_only_linkable_notices(ocn):
    from app.models.project_so import OrderChangeNotice

    ids = {}
    for name, cols in {
        "draft": dict(),
        "pending": dict(status="submitted", approval_status="pending"),
        "approved": dict(status="approved", approval_status="approved"),
        "voided": dict(status="voided"),
        "done": dict(status="processed_by_cs", approval_status="approved"),
    }.items():
        d = create(ocn, project_id=ocn.project.id)
        row = load(ocn, d["id"])
        for key, value in cols.items():
            setattr(row, key, value)
        ocn.db.commit()
        ids[name] = d["id"]
    url = PROJECT_PANEL.format(project_id=ocn.project.id)
    every = {r["id"] for r in ok(ocn.as_(ocn.viewer).get(url))["data"]}
    linkable = {r["id"] for r in ok(ocn.as_(ocn.viewer).get(url, params={"linkable": "true"}))["data"]}
    assert every == set(ids.values())
    assert linkable == {ids["draft"], ids["approved"]}
    assert OrderChangeNotice  # the model the predicate reads


# ================================================================== grants: Done is .process


def test_r4_done_needs_process_and_edit_alone_is_refused(ocn):
    d = approved(ocn)
    editor = user(ocn.db, "OCN editor only")
    grant(ocn.db, editor, VIEW, EDIT)
    ocn.db.commit()
    assert move(ocn, d["id"], "done", editor, json={"cs_comment": None}).status_code == 403
    assert load(ocn, d["id"]).status == "approved"
    processor = user(ocn.db, "OCN customer service only")
    grant(ocn.db, processor, PROCESS)
    ocn.db.commit()
    assert ok(move(ocn, d["id"], "done", processor, json={"cs_comment": None}))["status"] == "processed_by_cs"


def test_r4_the_migration_grants_process_from_pr_process_not_edit():
    from .test_ocn_migration import _granted, _role, _upgrade
    from ._pg_fixture import blank_session

    with blank_session() as db:
        cs = _role(db, "zzt-pr-cs", "procurement.purchase_requests.process")
        _upgrade(db)
        granted = _granted(db, cs.id)
        assert "procurement.order_change_notices.process" in granted
        assert "procurement.order_change_notices.edit" not in granted


def test_r4_process_is_in_the_registry():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    assert PROCESS in {e["slug"] for e in PERMISSION_REGISTRY}


# ================================================================== the reader rule


def test_r4_being_named_without_a_grant_reads_nothing(ocn):
    named = user(ocn.db, "OCN named, no grant")
    ocn.db.commit()
    d = create(ocn, sales_in_charge_user_id=named)
    assert get(ocn, d["id"], named).status_code == 403


def test_r4_a_raiser_without_create_cannot_edit_or_submit(ocn):
    raiser = user(ocn.db, "OCN raiser, create revoked")
    grant(ocn.db, raiser, VIEW_OWN)  # still sees their own, no longer creates
    # raised while they still held create
    row = svc().create_draft(ocn.db, actor=svc().actor_from_slugs(raiser, (CREATE, VIEW_OWN)),
                             data=payload(ocn, http=False))
    ocn.db.commit()
    d = {"id": row.id}
    assert get(ocn, d["id"], raiser).status_code == 200
    assert ocn.as_(raiser).put(f"{OCN}/{d['id']}", json={"description": "x"}).status_code == 403
    assert move(ocn, d["id"], "submit", raiser).status_code == 403


def _tab_reads(o, ocn_id, user_id):
    c = o.as_(user_id)
    q = {"source_entity_type": KIND, "source_entity_id": ocn_id}
    return {
        "conversation": c.get(f"/api/v1/form-comments/{KIND}/{ocn_id}").status_code,
        "post": c.post(f"/api/v1/form-comments/{KIND}/{ocn_id}", data={"body": "Checked with site"}).status_code,
        "sla": c.get("/api/v1/sla-management/conversation-sla-tracking/by-source", params=q).status_code,
        "history": c.get("/api/v1/audit/logs", params={"entity_type": KIND, "entity_id": ocn_id}).status_code,
    }


def test_r4_a_view_own_raiser_reads_and_posts_on_every_tab(ocn, sla):
    d = create(ocn, user_id=ocn.own, sales_in_charge_user_id=None, cs_in_charge_user_id=None)
    ok(move(ocn, d["id"], "submit", ocn.own))
    assert _tab_reads(ocn, d["id"], ocn.own) == {"conversation": 200, "post": 201, "sla": 200, "history": 200}


def test_r4_an_approve_only_user_reads_every_tab(ocn, sla):
    approver = user(ocn.db, "OCN approve only")
    grant(ocn.db, approver, APPROVE)
    ocn.db.commit()
    d = submitted(ocn)
    reads = _tab_reads(ocn, d["id"], approver)
    assert (reads["conversation"], reads["sla"], reads["history"]) == (200, 200, 200)


def test_r4_a_view_own_user_cannot_read_another_raisers_tabs(ocn, sla):
    d = submitted(ocn, sales_in_charge_user_id=None, cs_in_charge_user_id=None)
    reads = _tab_reads(ocn, d["id"], ocn.own)
    assert reads["conversation"] == 404 and reads["sla"] == 404
    assert reads["history"] == 404


# ================================================================== permission before parking


def test_r4_a_move_without_its_permission_is_refused_before_any_countdown(ocn, sla):
    from app.models.sla import SlaFormAction

    d = pending(ocn)
    other = submitted(ocn)
    sla.approval.config.grace_seconds = 60
    sla.main.config.grace_seconds = 60
    ocn.db.commit()
    res = move(ocn, d["id"], "approval-decision", ocn.viewer, json={"action": "approved", "comments": None})
    assert res.status_code == 403, res.text
    assert move(ocn, other["id"], "send-for-approval", ocn.manager).status_code == 403
    ocn.db.expire_all()
    from app.models.sla import FORM_ACTION_PENDING

    # The earlier immediate moves left committed history rows; nothing may be parked.
    parked = (
        ocn.db.query(SlaFormAction)
        .filter(SlaFormAction.source_entity_type == KIND, SlaFormAction.status == FORM_ACTION_PENDING)
        .count()
    )
    assert parked == 0


# ================================================================== raiser notices


@pytest.mark.parametrize(
    "path,event",
    [("send_back", "reject_submitted"), ("reject", "approval_rejected"), ("approve", "approved"),
     ("done", "resolved"), ("void", "voided")],
)
def test_r4_the_raiser_is_told_in_app(ocn, sla, path, event):
    if path == "send_back":
        d = submitted(ocn)
        ok(move(ocn, d["id"], "reject-submitted", ocn.sales_admin, json={"reason": "Add the PO copy"}))
    elif path == "reject":
        d = pending(ocn)
        ok(move(ocn, d["id"], "approval-decision", ocn.manager, json={"action": "rejected", "comments": "No"}))
    elif path == "approve":
        d = approved(ocn)
    elif path == "done":
        d = approved(ocn)
        ok(move(ocn, d["id"], "done", ocn.cs, json={"cs_comment": None}))
    else:
        d = submitted(ocn)
        ok(move(ocn, d["id"], "void", ocn.sales_admin, json={"reason": "Customer withdrew it"}))
    got = notifications(ocn.db, ocn.raiser, event_type=f"order_change_notice_{event}")
    assert len(got) == 1
    assert "OCN" in got[0].title


# ================================================================== the Submit rule, links, filters


def test_r4_submit_needs_the_customer_po_on_a_crm_notice(ocn):
    d = create(ocn, customer_po_no=None)
    res = move(ocn, d["id"], "submit", ocn.raiser)
    assert res.status_code == 422, res.text
    assert res.json()["details"]["field"] == "customer_po_no"


def test_r4_a_crm_notice_linked_to_an_amendment_keeps_its_project(build):
    from ._sample_request_seed import make_project

    b = build
    mine = _crm_ocn(b, b.project.id)
    _create(b, ocn_id=mine.id)
    elsewhere = make_project(b.db, b.company_id, b.owner, title="ZZT Harbour Depot")
    svc().update(b.db, mine, actor=svc().actor_from_slugs(b.owner, (CREATE, EDIT, VIEW)),
                 data={"project_id": elsewhere.id, "description": "Edited"})
    b.db.flush()
    assert mine.project_id == b.project.id
    assert mine.description == "Edited"


def test_r4_pending_approval_is_a_status_filter_value(ocn):
    plain = submitted(ocn)
    waiting = pending(ocn)
    got = {r["id"] for r in rows_of(ok(ocn.as_(ocn.viewer).get(OCN, params={"status": "pending_approval"})))}
    assert got == {waiting["id"]}
    got = {r["id"] for r in rows_of(ok(ocn.as_(ocn.viewer).get(OCN, params={"status": "submitted"})))}
    assert plain["id"] in got and waiting["id"] not in got


def test_r4_a_project_waiting_for_approval_cannot_be_linked(ocn):
    proj = ocn.other_project
    proj.approval_state = "pending"
    ocn.db.commit()
    res = ocn.as_(ocn.raiser).post(OCN, json=payload(ocn, project_id=proj.id))
    assert res.status_code == 422, res.text


def test_r4_more_than_a_hundred_lines_is_refused(ocn):
    line = payload(ocn)["lines"][0]
    res = ocn.as_(ocn.raiser).post(OCN, json=payload(ocn, lines=[line] * 101))
    assert res.status_code == 422, res.text


def test_r4_the_notice_date_is_the_malaysia_day(ocn):
    from app.services.certificate_service import today_malaysia

    data = payload(ocn, http=False)
    data.pop("ocn_date")  # the server picks the day
    row = svc().create_draft(ocn.db, actor=svc().actor_from_slugs(ocn.raiser, (CREATE, VIEW)), data=data)
    assert row.ocn_date == today_malaysia()


def test_r4_the_revision_config_row_is_not_listed_on_the_portal_settings():
    from app.api.v1.forms.revision_configs import _HIDDEN_CONFIG_TYPES

    assert KIND in _HIDDEN_CONFIG_TYPES


def test_r4_the_migration_seeds_a_numbering_rule_per_company():
    from sqlalchemy import text

    from .test_ocn_migration import _upgrade
    from ._pg_fixture import blank_session
    from ._sample_request_seed import second_company

    with blank_session() as db:
        other = second_company(db)
        _upgrade(db)
        companies = {
            str(c) for (c,) in db.execute(
                text("SELECT company_id FROM document_numbering_rules WHERE doc_type = :k AND company_id IS NOT NULL"),
                {"k": KIND},
            ).all()
        }
        assert other in companies


# ================================================================== attachments (review B2)


@pytest.fixture
def store(monkeypatch, ocn):
    from ._npa_v4_support import install_storage, seed_attachment_type

    seed_attachment_type(ocn.db)
    return install_storage(monkeypatch)


def _library_file(o, store, name="revised-po.pdf"):
    from app.models.resources import Attachment, AttachmentType
    import uuid as _uuid

    atype = o.db.query(AttachmentType).filter(AttachmentType.code == "response_attachment").first()
    key = f"library/{_uuid.uuid4()}-{name}"
    store.files[key] = b"%PDF-1.4 fake"
    row = Attachment(
        id=str(_uuid.uuid4()), attachment_type_id=atype.id, original_filename=name, stored_filename=name,
        file_path=key, file_size_bytes=13, storage_provider="s3", mime_type="application/pdf",
    )
    o.db.add(row)
    o.db.commit()
    return str(row.id)


def test_r4_the_raiser_links_a_file_and_the_detail_lists_it(ocn, store):
    d = create(ocn)
    att = _library_file(ocn, store)
    res = ocn.as_(ocn.raiser).post(f"{OCN}/{d['id']}/attachments", json={"attachment_id": att})
    assert res.status_code in (200, 201), res.text
    files = ok(get(ocn, d["id"]))["attachments"]
    assert [f["attachment_id"] for f in files] == [att]
    assert files[0]["filename"] == "revised-po.pdf" and files[0]["link_id"]


def test_r4_files_are_locked_once_submitted_and_a_viewer_cannot_link(ocn, store):
    d = create(ocn)
    att = _library_file(ocn, store)
    assert ocn.as_(ocn.viewer).post(f"{OCN}/{d['id']}/attachments", json={"attachment_id": att}).status_code == 403
    ok(move(ocn, d["id"], "submit", ocn.raiser))
    res = ocn.as_(ocn.raiser).post(f"{OCN}/{d['id']}/attachments", json={"attachment_id": att})
    assert res.status_code == 409, res.text
    assert ok(get(ocn, d["id"]))["attachments"] == []


def test_r4_unlink_is_a_pending_action_that_drops_only_the_link(ocn, store):
    import app.services.record_actions  # noqa: F401  (registers the action)
    from app.services.form_action_registry import get_action

    assert get_action("order_change_notice_attachment.unlink") is not None
    d = create(ocn)
    att = _library_file(ocn, store)
    res = ocn.as_(ocn.raiser).post(f"{OCN}/{d['id']}/attachments", json={"attachment_id": att})
    assert res.status_code in (200, 201), res.text
    link_id = ok(get(ocn, d["id"]))["attachments"][0]["link_id"]
    svc().unlink_attachment(ocn.db, link_id, ocn.raiser)
    assert ok(get(ocn, d["id"]))["attachments"] == []
