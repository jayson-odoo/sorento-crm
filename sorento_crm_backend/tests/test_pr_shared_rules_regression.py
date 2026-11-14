"""OCN-ORDER-CHANGE-NOTICE regression pin: the purchase request moves behave exactly as today.

The OCN lane lifts the PR's rules into shared module functions (plan "Shared once, never
copied": `_refuse_if_voided`, `assert_decidable`, `decision_comments`, `_VOID_BLOCKED_STATUSES`,
the finalize-from set, the already-pending no-op guard, the write sets of send for approval,
reject submitted and the approval decision) and wraps the `pr.*` deferred actions in one
helper. This file pins what those four moves do on main BEFORE the extraction, column by
column, so the extraction cannot change them. It must pass before and after the lane.

Reference chain: tests/test_forms_chain_purchase_request.py (same harness, real routes, real
SLA orchestrator, real RBAC). Postgres only, every row seeded.
"""
from __future__ import annotations

import pytest

from tests._forms_chain_support import (
    PR_BASE,
    SUB,
    contact,
    grant,
    open_tracker,
    sla_chain,
    trackers,
    user,
    world,  # noqa: F401  (fixture)
)

KINDS = ["purchase_request", "sponsorship_form"]
STAFF_SLUGS = (
    "procurement.purchase_requests.view",
    "procurement.purchase_requests.send_for_approval",
    "procurement.purchase_requests.approve",
    "procurement.purchase_requests.process",
    "procurement.purchase_requests.void",
)


def _setup(w, kind):
    db = w.db
    w.chain = sla_chain(db, kind, [
        dict(start_event="submit", resolve_event="send_for_approval,reject_submitted,voided",
             advance_on_event="send_for_approval"),
        dict(start_event="send_for_approval", resolve_event="approved,approval_rejected,voided",
             advance_on_event="approved"),
        dict(start_event="approved", resolve_event="resolved,voided"),
    ])
    w.kind = kind
    w.staff = user(db, f"{kind} staff")
    grant(db, w.staff, *STAFF_SLUGS)
    w.contact = contact(db, name=f"{kind} salesperson")
    db.commit()
    return w


def _submitted(w):
    c = w.as_contact(w.contact)
    res = c.post(f"{SUB}/{w.kind}", json={
        "fields": {"customer_name": "Customer A", "purpose": "showroom stock",
                   "requested_by_contact_id": w.contact},
        "products": [{"item_code": "ABC123-RL", "quantity": 4, "unit_price": 25, "total": 100}],
    })
    assert res.status_code == 200, res.text
    rid = res.json()["id"]
    res = c.post(f"{SUB}/{w.kind}/{rid}/submit")
    assert res.status_code == 200, res.text
    return rid


def _header(w, rid):
    from app.models.procurement import PurchaseRequestHeader

    w.db.expire_all()
    return w.db.query(PurchaseRequestHeader).filter(PurchaseRequestHeader.id == rid).one()


def _post(w, rid, action, json=None):
    return w.as_user(w.staff).post(f"{PR_BASE}/{rid}/{action}", json=json)


# ------------------------------------------------------------------ send for approval


@pytest.mark.parametrize("kind", KINDS)
def test_send_for_approval_writes_pending_and_the_requester_and_is_a_no_op_twice(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    res = _post(w, rid, "set-pending-approval")
    assert res.status_code == 200, res.text
    h = _header(w, rid)
    assert h.approval_status == "pending"
    assert h.status == "submitted"  # the lifecycle status does not move on send for approval
    assert h.requested_approval_by_user_id == w.staff
    assert (h.approved_at, h.approved_by, h.approval_comments) == (None, None, None)
    approval = open_tracker(w.db, kind, rid)
    assert approval.team_set_code == w.chain.stages[1].team_set

    again = _post(w, rid, "set-pending-approval")
    assert again.status_code == 200, again.text
    assert open_tracker(w.db, kind, rid).id == approval.id  # no second approval stage
    assert len(trackers(w.db, kind, rid)) == 2


@pytest.mark.parametrize("kind", KINDS)
def test_send_for_approval_is_refused_after_an_approval_rejection(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    assert _post(w, rid, "set-pending-approval").status_code == 200
    assert _post(w, rid, "approval-decision", {"action": "rejected", "comments": "Over budget"}).status_code == 200
    res = _post(w, rid, "set-pending-approval")
    assert res.status_code == 409, res.text
    assert _header(w, rid).approval_status == "rejected"


# ------------------------------------------------------------------ reject submitted


@pytest.mark.parametrize("kind", KINDS)
def test_reject_submitted_writes_both_statuses_the_reason_and_the_rejecter(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    res = _post(w, rid, "reject-submitted", {"rejection_reason": "Missing PO copy"})
    assert res.status_code == 200, res.text
    h = _header(w, rid)
    assert (h.status, h.approval_status) == ("rejected", "rejected")
    assert h.approval_comments == "Missing PO copy"
    assert h.rejected_by_id == w.staff
    assert h.requested_approval_by_user_id == w.staff
    assert h.approved_at is not None
    assert h.approved_by and h.approved_by != w.staff  # a display name, never the raw id
    assert trackers(w.db, kind, rid, open_only=True) == []


@pytest.mark.parametrize("kind", KINDS)
def test_reject_submitted_needs_a_reason_and_is_refused_once_pending(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    assert _post(w, rid, "reject-submitted", {"rejection_reason": ""}).status_code == 422
    assert _post(w, rid, "set-pending-approval").status_code == 200
    res = _post(w, rid, "reject-submitted", {"rejection_reason": "Too late"})
    assert res.status_code == 409, res.text
    assert _header(w, rid).approval_status == "pending"


# ------------------------------------------------------------------ approval decision


@pytest.mark.parametrize("kind", KINDS)
def test_approve_writes_both_statuses_and_the_stamp_then_refuses_a_second_decision(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    assert _post(w, rid, "set-pending-approval").status_code == 200
    res = _post(w, rid, "approval-decision", {"action": "approved", "comments": "Fine"})
    assert res.status_code == 200, res.text
    h = _header(w, rid)
    assert (h.status, h.approval_status) == ("approved", "approved")
    assert h.approved_at is not None
    assert h.approved_by  # the approver's display name
    assert h.approval_comments == "Fine"
    assert h.rejected_by_id is None
    assert open_tracker(w.db, kind, rid).team_set_code == w.chain.stages[2].team_set

    again = _post(w, rid, "approval-decision", {"action": "rejected", "comments": "Changed my mind"})
    assert again.status_code == 409, again.text
    assert "already been approved" in again.text


@pytest.mark.parametrize("kind", KINDS)
def test_reject_needs_remarks_and_records_the_rejecter(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    assert _post(w, rid, "set-pending-approval").status_code == 200
    blank = _post(w, rid, "approval-decision", {"action": "rejected", "comments": "  "})
    # Today: 400 VALIDATION_ERROR (handle_validation_error), pinned as is.
    assert blank.status_code == 400, blank.text
    assert "Rejection reason is required" in blank.text
    assert _header(w, rid).approval_status == "pending"
    res = _post(w, rid, "approval-decision", {"action": "rejected", "comments": "Over budget"})
    assert res.status_code == 200, res.text
    h = _header(w, rid)
    assert (h.status, h.approval_status) == ("rejected", "rejected")
    assert h.approval_comments == "Over budget"
    assert h.rejected_by_id == w.staff
    assert trackers(w.db, kind, rid, open_only=True) == []


@pytest.mark.parametrize("kind", KINDS)
def test_a_decision_before_send_for_approval_is_refused(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    res = _post(w, rid, "approval-decision", {"action": "approved", "comments": None})
    assert res.status_code == 409, res.text
    assert "Send it for approval first" in res.text
    assert _header(w, rid).status == "submitted"


@pytest.mark.parametrize("kind", KINDS)
def test_an_unknown_decision_action_is_refused(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    assert _post(w, rid, "set-pending-approval").status_code == 200
    res = _post(w, rid, "approval-decision", {"action": "maybe", "comments": None})
    assert res.status_code in (409, 422), res.text
    assert _header(w, rid).approval_status == "pending"


# ------------------------------------------------------------------ process (finalize-from)


@pytest.mark.parametrize("kind", KINDS)
def test_process_only_from_approved(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    early = _post(w, rid, "process", {"note": None})
    # Today: 400 VALIDATION_ERROR naming the current status, pinned as is.
    assert early.status_code == 400, early.text
    assert "must be approved" in early.text
    assert _header(w, rid).status == "submitted"
    assert _post(w, rid, "set-pending-approval").status_code == 200
    assert _post(w, rid, "approval-decision", {"action": "approved"}).status_code == 200
    done = _post(w, rid, "process", {"note": None})
    assert done.status_code == 200, done.text
    assert _header(w, rid).status == "processed_by_cs"
    assert trackers(w.db, kind, rid, open_only=True) == []


# ------------------------------------------------------------------ void


@pytest.mark.parametrize("kind", KINDS)
def test_void_while_pending_writes_the_reason_quad_and_closes_the_approval(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    assert _post(w, rid, "set-pending-approval").status_code == 200
    stage = open_tracker(w.db, kind, rid)
    assert _post(w, rid, "void", {"void_reason": "ab"}).status_code == 422
    res = _post(w, rid, "void", {"void_reason": "Duplicate of another"})
    assert res.status_code == 200, res.text
    h = _header(w, rid)
    assert (h.status, h.approval_status) == ("voided", "voided")
    assert h.void_reason == "Duplicate of another"
    assert h.voided_by == w.staff
    assert h.voided_at is not None
    assert trackers(w.db, kind, rid, open_only=True) == []
    w.db.refresh(stage)
    assert stage.is_resolved is True  # the PR's chain lists 'voided' as a resolve event


@pytest.mark.parametrize("kind", KINDS)
def test_void_before_approval_leaves_no_approval_status(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    assert _post(w, rid, "void", {"void_reason": "Duplicate of another"}).status_code == 200
    h = _header(w, rid)
    assert h.status == "voided"
    assert h.approval_status in (None, "", "draft")


@pytest.mark.parametrize(
    "path",
    [
        ("reject-submitted",),
        ("set-pending-approval", "approval-decision:rejected"),
        ("set-pending-approval", "approval-decision:approved", "process"),
    ],
    ids=["rejected_submitted", "approval_rejected", "processed_by_cs"],
)
@pytest.mark.parametrize("kind", KINDS)
def test_void_is_refused_from_every_closed_state(world, kind, path):
    w = _setup(world, kind)
    rid = _submitted(w)
    for step in path:
        if step == "reject-submitted":
            res = _post(w, rid, step, {"rejection_reason": "Missing PO copy"})
        elif step.startswith("approval-decision"):
            action = step.split(":")[1]
            res = _post(w, rid, "approval-decision", {"action": action, "comments": "Over budget"})
        elif step == "process":
            res = _post(w, rid, step, {"note": None})
        else:
            res = _post(w, rid, step)
        assert res.status_code == 200, (step, res.text)
    before = _header(w, rid).status
    res = _post(w, rid, "void", {"void_reason": "Too late now"})
    assert res.status_code == 409, res.text
    assert _header(w, rid).status == before


@pytest.mark.parametrize("kind", KINDS)
def test_a_voided_request_refuses_every_approval_step_with_the_voided_message(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    assert _post(w, rid, "void", {"void_reason": "Duplicate of another"}).status_code == 200
    for action, body in (
        ("set-pending-approval", None),
        ("reject-submitted", {"rejection_reason": "Incomplete"}),
        ("approval-decision", {"action": "approved", "comments": None}),
    ):
        res = _post(w, rid, action, body)
        assert res.status_code == 409, (action, res.text)
        assert "voided" in res.text.lower(), (action, res.text)
    assert _header(w, rid).status == "voided"


# ------------------------------------------------------------------ the deferred-action surface


def test_the_pr_deferred_actions_stay_registered_for_both_kinds():
    import app.services.form_actions  # noqa: F401  (registers the actions)
    from app.services.form_action_registry import get_action

    for key in ("pr.send_for_approval", "pr.reject_submitted", "pr.approval_decision", "pr.finalize", "pr.void"):
        action = get_action(key)
        assert action is not None, key
        assert {"purchase_request", "sponsorship_form"} <= set(action.entity_types), key
