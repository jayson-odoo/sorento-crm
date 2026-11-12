"""OCN-ORDER-CHANGE-NOTICE red tests: record, numbering and the purchase request chain.

UAC A1, A2, A4-A7 and B1-B8, B10 (documentation/plans/procurement/
ocn-order-change-notice-acceptance-criteria.md). Two layers:

* the service (`app.services.order_change_notice_service`): each move's state change, the
  columns it writes and the SLA event name it returns (NPA template: the move only flushes
  and returns the event, the router emits it after commit);
* the routes, for what only the emitted event proves: which SLA stage starts, resolves or is
  voided (the forms-chain SLA world, real orchestrator).

Postgres only, every row seeded here (tests/_ocn_support.py).
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.error_handler import AppException

from ._forms_chain_support import SORENTO, open_tracker, settings_row, trackers, world  # noqa: F401
from ._ocn_support import (  # noqa: F401  (fixtures)
    KIND,
    OCN,
    actor,
    approved,
    create,
    get,
    load,
    move,
    number_pattern,
    ocn,
    ok,
    payload,
    pending,
    sla,
    submitted,
    svc,
    uid,
)


def _draft(o, user_id=None, **over):
    s = svc()
    row = s.create_draft(o.db, actor=actor(o, user_id or o.raiser), data=payload(o, http=False, **over))
    o.db.flush()
    return row


def _to(o, row, *steps):
    """Walk `row` through service moves, each by its stage's actor."""
    s = svc()
    for step in steps:
        if step == "submit":
            s.submit(o.db, row, actor=actor(o, o.raiser))
        elif step == "send":
            s.send_for_approval(o.db, row, actor=actor(o, o.sales_admin))
        elif step == "approve":
            s.decide(o.db, row, actor=actor(o, o.manager), action="approved", comments=None)
        elif step == "reject":
            s.decide(o.db, row, actor=actor(o, o.manager), action="rejected", comments="Wrong quantity")
        elif step == "send_back":
            s.reject_submitted(o.db, row, actor=actor(o, o.sales_admin), reason="Add the PO copy")
        elif step == "done":
            s.mark_done(o.db, row, actor=actor(o, o.cs))
        else:  # pragma: no cover - test typo
            raise AssertionError(step)
    o.db.flush()
    return row


def _refused(status: int, fn, *args, **kwargs) -> AppException:
    with pytest.raises(AppException) as exc:
        fn(*args, **kwargs)
    assert exc.value.status_code == status, (exc.value.status_code, exc.value.detail)
    return exc.value


def _message(exc: AppException) -> str:
    return str(getattr(exc, "message", None) or exc.detail)


# ================================================================== A. record and numbering


def test_a1_create_stores_a_draft_by_the_raiser_numbered_from_the_rule(ocn):
    row = _draft(ocn)
    assert row.status == "draft"
    assert row.created_by == ocn.raiser
    assert row.source == "crm"
    assert str(row.company_id) == SORENTO
    assert re.match(number_pattern(), row.ocn_number), row.ocn_number
    assert row.ocn_number.endswith("-0001")
    second = _draft(ocn)
    assert second.ocn_number.endswith("-0002")
    assert (row.revision_no or 0) == 0
    assert row.approval_status in (None, "", "draft")


def test_a1_create_over_http_answers_the_draft_and_its_number(ocn):
    body = create(ocn)
    assert body["status"] == "draft"
    assert body["source"] == "crm"
    assert re.match(number_pattern(), body["ocn_number"]), body["ocn_number"]


def test_a1_next_ocn_number_is_the_one_shared_function(ocn):
    """Plan "Shared once": one module function the delta service and the OCN service use."""
    s = svc()
    first = s.next_ocn_number(ocn.db, SORENTO)
    second = s.next_ocn_number(ocn.db, SORENTO)
    assert re.match(number_pattern(), first) and re.match(number_pattern(), second)
    assert int(second[-4:]) == int(first[-4:]) + 1


def test_a2_two_companies_each_get_their_own_sequence(ocn):
    from ._sample_request_seed import second_company

    other = second_company(ocn.db)
    # Lead ruling m5 (round 4): each company has its own rule row (the migration seeds one per
    # company); a company created here gets its row the same way.
    from ._ocn_support import numbering_rule

    numbering_rule(ocn.db, company_id=SORENTO)
    numbering_rule(ocn.db, company_id=other)
    s = svc()
    x1 = s.next_ocn_number(ocn.db, SORENTO)
    x2 = s.next_ocn_number(ocn.db, SORENTO)
    y1 = s.next_ocn_number(ocn.db, other)
    assert x1.endswith("-0001") and x2.endswith("-0002")
    assert y1.endswith("-0001"), f"company Y drew {y1} from company X's counter"


def test_a2_same_number_allowed_across_companies_refused_twice_in_one(ocn):
    from app.models.project_so import OrderChangeNotice

    from ._sample_request_seed import second_company

    from app.models.base import company_scope

    other = second_company(ocn.db)
    number = f"OCN{date.today().year % 100:02d}-0999"
    with company_scope(ocn.db, None):  # the all-companies principal writes both companies' rows
        ocn.db.add(OrderChangeNotice(id=uid(), company_id=SORENTO, ocn_number=number, status="draft", source="crm"))
        ocn.db.add(OrderChangeNotice(id=uid(), company_id=other, ocn_number=number, status="draft", source="crm"))
        ocn.db.flush()  # two companies, one number: allowed
        nested = ocn.db.begin_nested()
        ocn.db.add(OrderChangeNotice(id=uid(), company_id=SORENTO, ocn_number=number, status="draft", source="crm"))
        with pytest.raises(IntegrityError) as exc:
            ocn.db.flush()
        nested.rollback()
    assert "uq_ocn_number" in str(exc.value)


def test_a4_require_project_on_refuses_submit_without_a_project_naming_the_field(ocn):
    settings_row(ocn.db, order_change_notice_require_project=True)
    row = _draft(ocn, project_id=None)
    exc = _refused(422, svc().submit, ocn.db, row, actor=actor(ocn, ocn.raiser))
    assert "project" in _message(exc).lower()
    assert row.status == "draft"


def test_a4_require_project_on_submits_with_a_project(ocn):
    settings_row(ocn.db, order_change_notice_require_project=True)
    row = _draft(ocn, project_id=ocn.project.id)
    assert svc().submit(ocn.db, row, actor=actor(ocn, ocn.raiser)) == "submit"
    assert row.status == "submitted"


def test_a4_require_project_off_by_default_submits_without_one(ocn):
    from app.models.user import SystemSetting

    assert SystemSetting().order_change_notice_require_project in (False, None)
    settings_row(ocn.db, order_change_notice_require_project=False)
    row = _draft(ocn, project_id=None)
    assert svc().submit(ocn.db, row, actor=actor(ocn, ocn.raiser)) == "submit"
    assert row.status == "submitted"
    assert row.project_id is None


def test_a5_the_response_carries_the_types_risk_level_and_guide_text(ocn):
    body = create(ocn, change_type_id=ocn.types.cancellation.id)
    detail = ok(get(ocn, body["id"]))
    assert detail["change_type_id"] == ocn.types.cancellation.id
    assert detail["change_type_name"] == "Cancellation"
    assert detail["risk_level"].lower() == "highest"
    assert detail["guide_text"] == ocn.types.cancellation.guide_text


def test_a5_an_inactive_change_type_is_refused(ocn):
    res = ocn.as_(ocn.raiser).post(OCN, json=payload(ocn, change_type_id=ocn.types.retired.id))
    assert res.status_code == 422, res.text


def test_a5_an_unknown_change_type_is_refused(ocn):
    res = ocn.as_(ocn.raiser).post(OCN, json=payload(ocn, change_type_id=uid()))
    assert res.status_code == 422, res.text


def test_a5_service_refuses_an_inactive_type_too(ocn):
    _refused(422, svc().create_draft, ocn.db, actor=actor(ocn, ocn.raiser),
             data=payload(ocn, http=False, change_type_id=ocn.types.retired.id))


def test_a6_lines_store_every_column_against_a_catalogue_product(ocn):
    row = _draft(ocn, lines=[
        {"product_id": ocn.p1.id, "qty_before": Decimal("100"), "qty_after": Decimal("60"),
         "date_before": date(2026, 12, 1), "date_after": date(2026, 12, 1),
         "delivered_qty": Decimal("20"), "remark": "Cancel balance"},
        {"product_id": ocn.p2.id, "qty_before": Decimal("50"), "qty_after": Decimal("50"),
         "date_before": date(2026, 12, 1), "date_after": date(2027, 2, 1),
         "delivered_qty": Decimal("0"), "remark": None},
    ])
    from app.models.project_so import OrderChangeNoticeLine

    lines = (
        ocn.db.query(OrderChangeNoticeLine)
        .filter(OrderChangeNoticeLine.ocn_id == row.id)
        .order_by(OrderChangeNoticeLine.position)
        .all()
    )
    assert [str(line.product_id) for line in lines] == [ocn.p1.id, ocn.p2.id]
    first = lines[0]
    assert (first.qty_before, first.qty_after, first.delivered_qty) == (100, 60, 20)
    assert (first.date_before, first.date_after) == (date(2026, 12, 1), date(2026, 12, 1))
    assert first.remark == "Cancel balance"


def test_a6_a_line_without_a_product_is_refused(ocn):
    """No free-text product line anywhere (owner standing rule): an item code alone is refused."""
    res = ocn.as_(ocn.raiser).post(OCN, json=payload(ocn, lines=[
        {"item_code": "ABC123-RL", "qty_before": "1", "qty_after": "2"},
    ]))
    assert res.status_code == 422, res.text


def test_a6_submit_needs_at_least_one_line(ocn):
    row = _draft(ocn, lines=[])
    exc = _refused(422, svc().submit, ocn.db, row, actor=actor(ocn, ocn.raiser))
    assert row.status == "draft"
    assert _message(exc)


def test_a6_quantities_are_never_capped_by_stock(ocn):
    """The products hold no stock at all; a big quantity still saves and submits."""
    row = _draft(ocn, lines=[
        {"product_id": ocn.p1.id, "qty_before": Decimal("5"), "qty_after": Decimal("999999"),
         "date_before": None, "date_after": None, "delivered_qty": Decimal("0"), "remark": None},
    ])
    assert svc().submit(ocn.db, row, actor=actor(ocn, ocn.raiser)) == "submit"


def test_a7_customer_id_and_typed_name_both_kept_po_and_so_are_free_text(ocn):
    row = _draft(ocn, customer_name="Customer A (typed)", customer_po_no="XT04/3871 (R1)",
                 so_no_text="SO-ZZT-0001")
    assert str(row.customer_id) == ocn.customer.id
    assert row.customer_name == "Customer A (typed)"
    assert row.customer_po_no == "XT04/3871 (R1)"
    assert row.so_no_text == "SO-ZZT-0001"
    # Nothing is linked by matching the PO or SO text (no automatic joining by similar names).
    assert row.purchase_order_id is None
    assert row.project_sales_order_id is None
    assert row.project_id is None


# ================================================================== B. lifecycle (service)


def test_b1_submit_moves_draft_to_submitted_and_returns_submit(ocn):
    row = _draft(ocn)
    assert svc().submit(ocn.db, row, actor=actor(ocn, ocn.raiser)) == "submit"
    assert row.status == "submitted"
    assert row.submitted_at is not None


def test_b2_send_for_approval_marks_it_pending_and_names_the_requester(ocn):
    row = _to(ocn, _draft(ocn), "submit")
    assert svc().send_for_approval(ocn.db, row, actor=actor(ocn, ocn.sales_admin)) == "send_for_approval"
    assert row.approval_status == "pending"
    assert row.status in ("submitted", "resubmitted")
    assert row.requested_approval_by_user_id == ocn.sales_admin


def test_b2_send_for_approval_needs_the_edit_permission(ocn):
    row = _to(ocn, _draft(ocn), "submit")
    _refused(403, svc().send_for_approval, ocn.db, row, actor=actor(ocn, ocn.viewer))
    assert row.approval_status in (None, "", "draft")


def test_b3_send_back_rejects_with_the_reason_and_the_raiser_resubmits(ocn):
    s = svc()
    row = _to(ocn, _draft(ocn), "submit")
    assert s.reject_submitted(ocn.db, row, actor=actor(ocn, ocn.sales_admin),
                              reason="Add the PO copy") == "reject_submitted"
    assert (row.status, row.approval_status) == ("rejected", "rejected")
    assert row.approval_comments == "Add the PO copy"
    assert row.rejected_by_id == ocn.sales_admin
    # amend and resubmit
    s.update(ocn.db, row, actor=actor(ocn, ocn.raiser), data={"description": "PO copy attached"})
    assert s.submit(ocn.db, row, actor=actor(ocn, ocn.raiser)) == "submit"
    assert row.status in ("submitted", "resubmitted")
    assert row.approval_status in (None, "", "draft")


def test_b3_send_back_needs_a_reason(ocn):
    row = _to(ocn, _draft(ocn), "submit")
    _refused(422, svc().reject_submitted, ocn.db, row, actor=actor(ocn, ocn.sales_admin), reason="  ")
    assert row.status == "submitted"


def test_b4_approve_stamps_the_approver_and_returns_approved(ocn):
    row = _to(ocn, _draft(ocn), "submit", "send")
    assert svc().decide(ocn.db, row, actor=actor(ocn, ocn.manager), action="approved",
                        comments="Fine") == "approved"
    assert (row.status, row.approval_status) == ("approved", "approved")
    assert row.approver_id == ocn.manager
    assert row.approved_at is not None


def test_b4_approve_needs_the_approve_permission(ocn):
    row = _to(ocn, _draft(ocn), "submit", "send")
    _refused(403, svc().decide, ocn.db, row, actor=actor(ocn, ocn.sales_admin), action="approved", comments=None)
    assert row.approval_status == "pending"


def test_b5_reject_records_the_remarks_and_returns_approval_rejected(ocn):
    row = _to(ocn, _draft(ocn), "submit", "send")
    assert svc().decide(ocn.db, row, actor=actor(ocn, ocn.manager), action="rejected",
                        comments="Wrong quantity") == "approval_rejected"
    assert (row.status, row.approval_status) == ("rejected", "rejected")
    assert row.approval_comments == "Wrong quantity"
    assert row.rejected_by_id == ocn.manager
    # amend and resubmit, as B3
    assert svc().submit(ocn.db, row, actor=actor(ocn, ocn.raiser)) == "submit"
    assert row.status in ("submitted", "resubmitted")


def test_b5_reject_needs_remarks(ocn):
    row = _to(ocn, _draft(ocn), "submit", "send")
    _refused(422, svc().decide, ocn.db, row, actor=actor(ocn, ocn.manager), action="rejected", comments="")
    assert row.approval_status == "pending"


def test_b6_done_moves_approved_to_processed_with_an_optional_cs_comment(ocn):
    s = svc()
    row = _to(ocn, _draft(ocn), "submit", "send", "approve")
    assert s.mark_done(ocn.db, row, actor=actor(ocn, ocn.cs), cs_comment="Keyed into the SO") == "resolved"
    assert row.status == "processed_by_cs"
    assert row.cs_comment == "Keyed into the SO"
    other = _to(ocn, _draft(ocn), "submit", "send", "approve")
    assert s.mark_done(ocn.db, other, actor=actor(ocn, ocn.cs)) == "resolved"
    assert other.cs_comment is None


@pytest.mark.parametrize("steps", [(), ("submit",), ("submit", "send"), ("submit", "send", "approve")],
                         ids=["draft", "submitted", "pending_approval", "approved"])
def test_b7_void_from_every_open_status(ocn, steps):
    row = _to(ocn, _draft(ocn), *steps)
    assert svc().void(ocn.db, row, actor=actor(ocn, ocn.sales_admin), reason="Customer withdrew it") == "voided"
    assert row.status == "voided"
    assert row.void_reason == "Customer withdrew it"
    assert row.voided_by == ocn.sales_admin
    assert row.voided_at is not None
    if steps == ("submit", "send"):
        assert row.approval_status == "voided"  # the open approval closes with the form


def test_b7_void_needs_a_reason(ocn):
    row = _draft(ocn)
    _refused(422, svc().void, ocn.db, row, actor=actor(ocn, ocn.sales_admin), reason="x")
    assert row.status == "draft"


@pytest.mark.parametrize("steps", [("submit", "send_back"), ("submit", "send", "approve", "done")],
                         ids=["rejected", "done"])
def test_b7_void_is_refused_once_closed(ocn, steps):
    row = _to(ocn, _draft(ocn), *steps)
    before = row.status
    _refused(409, svc().void, ocn.db, row, actor=actor(ocn, ocn.sales_admin), reason="Too late now")
    assert row.status == before


def test_b7_a_voided_ocn_cannot_be_voided_again(ocn):
    row = _draft(ocn)
    svc().void(ocn.db, row, actor=actor(ocn, ocn.sales_admin), reason="Duplicate entry")
    _refused(409, svc().void, ocn.db, row, actor=actor(ocn, ocn.sales_admin), reason="Duplicate entry")


def test_b8_an_approved_ocn_is_locked_against_edit(ocn):
    row = _to(ocn, _draft(ocn), "submit", "send", "approve")
    _refused(409, svc().update, ocn.db, row, actor=actor(ocn, ocn.raiser), data={"description": "sneaky"})
    assert row.description != "sneaky"


def test_b8_revise_unlocks_back_to_draft_bumps_the_revision_and_clears_the_stamp(ocn):
    s = svc()
    row = _to(ocn, _draft(ocn), "submit", "send", "approve")
    before = row.revision_no or 0
    # Lead ruling (plan + UAC B8): revise returns the OCN to draft and emits nothing.
    assert s.revise(ocn.db, row, actor=actor(ocn, ocn.sales_admin), reason="Customer changed the dates") is None
    assert row.status == "draft"
    assert row.revision_no == before + 1
    assert row.approval_status in (None, "", "draft")
    assert row.approver_id is None
    assert row.approved_at is None
    # now editable again
    s.update(ocn.db, row, actor=actor(ocn, ocn.raiser), data={"description": "New dates"})
    assert row.description == "New dates"


def test_b8_revise_needs_a_reason_and_an_approved_ocn(ocn):
    s = svc()
    row = _to(ocn, _draft(ocn), "submit", "send", "approve")
    _refused(422, s.revise, ocn.db, row, actor=actor(ocn, ocn.sales_admin), reason="")
    draft = _draft(ocn)
    _refused(409, s.revise, ocn.db, draft, actor=actor(ocn, ocn.sales_admin), reason="Nothing to revise")


# B10: a move from a wrong status is refused 409 and changes nothing.
_WRONG = [
    ("submit", ("submit", "send", "approve"), lambda s, o, r: s.submit(o.db, r, actor=actor(o, o.raiser))),
    ("send_for_approval", (), lambda s, o, r: s.send_for_approval(o.db, r, actor=actor(o, o.sales_admin))),
    ("send_for_approval_twice_after_reject", ("submit", "send", "reject"),
     lambda s, o, r: s.send_for_approval(o.db, r, actor=actor(o, o.sales_admin))),
    ("reject_submitted", ("submit", "send"),
     lambda s, o, r: s.reject_submitted(o.db, r, actor=actor(o, o.sales_admin), reason="Late")),
    ("decide_on_draft", (), lambda s, o, r: s.decide(o.db, r, actor=actor(o, o.manager), action="approved", comments=None)),
    ("decide_twice", ("submit", "send", "approve"),
     lambda s, o, r: s.decide(o.db, r, actor=actor(o, o.manager), action="approved", comments=None)),
    ("done_on_pending", ("submit", "send"), lambda s, o, r: s.mark_done(o.db, r, actor=actor(o, o.cs))),
    ("revise_submitted", ("submit",),
     lambda s, o, r: s.revise(o.db, r, actor=actor(o, o.sales_admin), reason="Not approved yet")),
]


@pytest.mark.parametrize("name,steps,call", _WRONG, ids=[w[0] for w in _WRONG])
def test_b10_a_move_from_a_wrong_status_is_refused_409(ocn, name, steps, call):
    row = _to(ocn, _draft(ocn), *steps)
    before = (row.status, row.approval_status, row.revision_no)
    exc = _refused(409, call, svc(), ocn, row)
    assert _message(exc)
    assert (row.status, row.approval_status, row.revision_no) == before


def test_b10_a_voided_ocn_refuses_every_approval_step(ocn):
    s = svc()
    row = _to(ocn, _draft(ocn), "submit", "send")
    s.void(ocn.db, row, actor=actor(ocn, ocn.sales_admin), reason="Customer withdrew it")
    _refused(409, s.decide, ocn.db, row, actor=actor(ocn, ocn.manager), action="approved", comments=None)
    _refused(409, s.send_for_approval, ocn.db, row, actor=actor(ocn, ocn.sales_admin))
    assert (row.status, row.approval_status) == ("voided", "voided")


# ================================================================== B. lifecycle (SLA stages, routes)


def test_b1_route_submit_starts_the_main_stage(ocn, sla):
    d = create(ocn)
    assert trackers(ocn.db, KIND, d["id"]) == []  # a draft starts nothing
    body = ok(move(ocn, d["id"], "submit", ocn.raiser))
    assert body["status"] == "submitted"
    stage = open_tracker(ocn.db, KIND, d["id"])
    assert stage.team_set_code == "project_sales"
    assert stage.assigned_to_id == sla.main.tier1


def test_b2_route_send_for_approval_resolves_main_and_starts_the_manager_stage(ocn, sla):
    d = submitted(ocn)
    main = open_tracker(ocn.db, KIND, d["id"])
    body = ok(move(ocn, d["id"], "send-for-approval", ocn.sales_admin))
    assert body["approval_status"] == "pending"
    ocn.db.refresh(main)
    assert main.is_resolved is True
    stage = open_tracker(ocn.db, KIND, d["id"])
    assert stage.team_set_code == "project_sales_manager"
    assert stage.assigned_to_id == sla.approval.tier1


def test_b2_the_default_approver_takes_the_approval_stage_when_in_the_team_set(ocn, sla):
    settings_row(ocn.db, order_change_notice_default_approver_user_id=sla.approval.tier2)
    d = pending(ocn)
    stage = open_tracker(ocn.db, KIND, d["id"])
    assert stage.team_set_code == "project_sales_manager"
    assert stage.assigned_to_id == sla.approval.tier2


def test_b2_a_default_approver_outside_the_team_set_is_ignored(ocn, sla):
    settings_row(ocn.db, order_change_notice_default_approver_user_id=ocn.viewer)
    d = pending(ocn)
    assert open_tracker(ocn.db, KIND, d["id"]).assigned_to_id == sla.approval.tier1


def test_b3_route_send_back_resolves_main_and_resubmit_starts_a_fresh_main(ocn, sla):
    d = submitted(ocn)
    first = open_tracker(ocn.db, KIND, d["id"])
    body = ok(move(ocn, d["id"], "reject-submitted", ocn.sales_admin, json={"reason": "Add the PO copy"}))
    assert body["status"] == "rejected"
    assert trackers(ocn.db, KIND, d["id"], open_only=True) == []
    ocn.db.refresh(first)
    assert first.is_resolved is True
    ok(move(ocn, d["id"], "submit", ocn.raiser))
    again = open_tracker(ocn.db, KIND, d["id"])
    assert again.id != first.id and again.team_set_code == "project_sales"


def test_b4_route_approve_resolves_approval_and_starts_customer_service(ocn, sla):
    d = pending(ocn)
    approval = open_tracker(ocn.db, KIND, d["id"])
    body = ok(move(ocn, d["id"], "approval-decision", ocn.manager, json={"action": "approved", "comments": None}))
    assert (body["status"], body["approval_status"]) == ("approved", "approved")
    ocn.db.refresh(approval)
    assert approval.is_resolved is True
    stage = open_tracker(ocn.db, KIND, d["id"])
    assert stage.team_set_code == "customer_service"
    assert stage.assigned_to_id == sla.cs.tier1


def test_b5_route_reject_resolves_approval_and_starts_nothing(ocn, sla):
    d = pending(ocn)
    body = ok(move(ocn, d["id"], "approval-decision", ocn.manager,
                   json={"action": "rejected", "comments": "Wrong quantity"}))
    assert body["status"] == "rejected"
    assert trackers(ocn.db, KIND, d["id"], open_only=True) == []
    assert all(t.is_resolved for t in trackers(ocn.db, KIND, d["id"]))


def test_b6_route_done_resolves_the_customer_service_stage(ocn, sla):
    d = approved(ocn)
    body = ok(move(ocn, d["id"], "done", ocn.cs, json={"cs_comment": "Keyed in"}))
    assert body["status"] == "processed_by_cs"
    assert body["cs_comment"] == "Keyed in"
    assert trackers(ocn.db, KIND, d["id"], open_only=True) == []
    rows = trackers(ocn.db, KIND, d["id"])
    assert [t.team_set_code for t in rows] == ["project_sales", "project_sales_manager", "customer_service"]
    assert all(t.is_resolved for t in rows)


@pytest.mark.parametrize("to", ["submitted", "pending", "approved"])
def test_b7_route_void_voids_the_open_stage_never_resolves_it(ocn, sla, to):
    d = {"submitted": submitted, "pending": pending, "approved": approved}[to](ocn)
    stage = open_tracker(ocn.db, KIND, d["id"])
    body = ok(move(ocn, d["id"], "void", ocn.sales_admin, json={"reason": "Customer withdrew it"}))
    assert body["status"] == "voided"
    assert trackers(ocn.db, KIND, d["id"], open_only=True) == []
    ocn.db.refresh(stage)
    assert stage.voided_at is not None
    assert stage.is_resolved is False


def test_b8_route_edit_of_an_approved_ocn_is_refused(ocn, sla):
    d = approved(ocn)
    res = ocn.as_(ocn.raiser).put(f"{OCN}/{d['id']}", json={"description": "sneaky"})
    assert res.status_code == 409, res.text
    assert load(ocn, d["id"]).description != "sneaky"


def test_b8_route_revise_voids_the_open_stage_and_returns_to_draft(ocn, sla):
    d = approved(ocn)
    cs_stage = open_tracker(ocn.db, KIND, d["id"])
    body = ok(move(ocn, d["id"], "revise", ocn.sales_admin, json={"reason": "Customer changed the dates"}))
    assert body["status"] == "draft"
    assert body["revision_no"] == 1
    assert body["approval_status"] in (None, "", "draft")
    ocn.db.refresh(cs_stage)
    assert cs_stage.voided_at is not None and cs_stage.is_resolved is False


def test_b10_route_wrong_status_is_409_and_emits_nothing(ocn, sla):
    d = create(ocn)
    res = move(ocn, d["id"], "approval-decision", ocn.manager, json={"action": "approved", "comments": None})
    assert res.status_code == 409, res.text
    res = move(ocn, d["id"], "done", ocn.cs, json={"cs_comment": None})
    assert res.status_code == 409, res.text
    assert trackers(ocn.db, KIND, d["id"]) == []
    assert load(ocn, d["id"]).status == "draft"
