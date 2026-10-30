"""AGENTIC-P3 slice 7 (PLAN-agentic-p3-writes-30oct.md, "Slice 7"): purchase-request approve / reject
through the grace window. Red tests, written before the tools exist.

The world is the forms regression world (`tests/_forms_chain_support.py`): real routes, the real SLA chain,
the real form-action dispatcher and the handling lock, on the blank Postgres schema. The agent contact and
its linked user are added to that world. The agent's own calls are in process (`writes.propose_step`,
`actions.store_proposal`, `actions.confirm`), as in the earlier slices.

Assumed names (the plan fixes the tool names and the rules, not every argument):
- `crm_purchase_requests_list {query?, approval_status?, request_type?, limit?}` (default pending only);
  `crm_purchase_request_get {request_id}` or `{number}`.
- `crm_purchase_request_decide {request_id, decision: "approve" | "reject", reason?}`.
- `crm_purchase_request_decision_cancel {request_id}`.
- A step whose decision was deferred ends with status `parked`, `pending_action_id` and `commit_at`;
  `ActionOutcome.steps[].status` shows `parked`. Change line: field `Approval`, before `Pending`, after
  `Approved` (or `Rejected`), with ` (commits at HH:MM)` appended while parked.
- Proposal summary: `<request number> (<customer name>): approve (notifies the requester)` /
  `... reject: "<reason>" (notifies the requester)`.
- A list / get row carries the request number as `request_number`.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import timedelta

import pytest

from app.models.base import company_scope
from app.models.procurement import PurchaseRequestHeader
from app.models.sla import SlaFormAction
from app.models.user import User
from tests._forms_chain_support import (
    FORM_ACTIONS,
    PR_BASE,
    grant,
    make_due,
    open_tracker,
    outbox,
    settings_row,
    user,
    world,  # noqa: F401  (fixture)
)
from tests.chatbot.agent._seed import seed_contact
from tests.chatbot.agent.test_agent_writes import action_row, answer_, revoke, round_of, tc
from tests.chatbot.agent.test_agent_writes_round1 import go
from tests.chatbot.agent.test_agent_writes_round2 import console_confirm, propose, read, refused, store
from tests.chatbot.agent.test_agent_writes_round2 import grant as grant_more
from tests.test_forms_chain_purchase_request import KINDS, TABLE, _setup, _submitted, _to_pending_approval  # noqa: F401

KIND = "purchase_request"
LIST = "crm_purchase_requests_list"
GET = "crm_purchase_request_get"
DECIDE = "crm_purchase_request_decide"
CANCEL = "crm_purchase_request_decision_cancel"
APPROVE = "procurement.purchase_requests.approve"
VIEW = "procurement.purchase_requests.view"
VIEW_OWN = "procurement.purchase_requests.view_own"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
NOTIFIES = "(notifies the requester)"


# ------------------------------------------------------------------ the scene


def scene(world, *, grace=None, slugs=(APPROVE, VIEW)):
    """A purchase request waiting for approval, and an agent contact whose linked user holds `slugs`."""
    w = _setup(world, KIND, approval_grace=grace)
    w.rid = _submitted(w)
    _to_pending_approval(w, w.rid)
    contact = seed_contact(w.db)
    linked = user(w.db, "agent linked user")
    grant(w.db, linked, *slugs)
    w.db.query(User).filter(User.id == linked).one().respond_contact_id = contact["pk"]
    w.db.commit()
    w.respond_id, w.user_id, w.agent_contact = contact["respond_id"], linked, contact
    return w


def operator(w, *slugs) -> str:
    uid_ = user(w.db, "console operator")
    grant(w.db, uid_, *slugs)
    w.db.commit()
    return uid_


def header(w, rid=None) -> PurchaseRequestHeader:
    w.db.expire_all()
    with company_scope(w.db, None):
        return w.db.query(PurchaseRequestHeader).filter(PurchaseRequestHeader.id == (rid or w.rid)).one()


def number(w) -> str:
    n = header(w).request_number
    assert n, "the seeded request has no request number"
    return n


def decide_args(w, decision="approve", **extra):
    return {"request_id": w.rid, "decision": decision, **extra}


def seen(w, *more):
    return {w.rid, *more}


def chat_confirm(w, action):
    from app.services.chatbot.agent import actions

    return actions.confirm(w.db, w.respond_id, str(action.id), via="chat", turn_id=str(uuid.uuid4()))


def sends(w):
    return len(outbox(w.db, TABLE, w.rid))


def dump(value) -> str:
    return json.dumps(value, default=str)


# ------------------------------------------------------------------ registry


def test_the_registry_holds_the_two_reads_and_the_two_writes_on_the_approve_slug():
    from app.services.chatbot.agent import writes

    assert {LIST, GET} <= set(writes.USER_READS)
    assert {DECIDE, CANCEL} <= set(writes.WRITES)
    assert writes.WRITES[DECIDE].user_permission == APPROVE and writes.WRITES[DECIDE].record_key == "request_id"
    assert writes.WRITES[CANCEL].user_permission == APPROVE


# ------------------------------------------------------------------ reads as the user


def test_the_list_shows_the_requests_waiting_for_approval_to_a_user_who_may_see_them(world):
    w = scene(world)
    n = number(w)

    out, ids = read(w.db, w, None, LIST, {})

    assert out.status == "ok" and n in dump(out.data)
    assert w.rid.lower() in ids
    assert not UUID_RE.search(dump(out.data).replace(w.rid, ""))  # ids only as the tool's own result ids


def test_the_list_respects_the_users_own_scope(world):
    w = scene(world, slugs=(APPROVE, VIEW))
    narrow = scene(world, slugs=(APPROVE, VIEW_OWN))  # sees only requests its own contact submitted

    wide_out, _ = read(w.db, w, None, LIST, {})
    narrow_out, narrow_ids = read(narrow.db, narrow, None, LIST, {})

    assert number(w) in dump(wide_out.data)  # control: a view holder sees it
    assert narrow_out.status == "ok"
    assert number(narrow) not in dump(narrow_out.data) and narrow.rid.lower() not in narrow_ids


def test_get_answers_by_request_number_and_by_id_and_hides_what_the_user_may_not_see(world):
    w = scene(world)
    narrow = scene(world, slugs=(APPROVE, VIEW_OWN))
    n = number(w)

    by_number, _ = read(w.db, w, None, GET, {"number": n})
    by_id, ids = read(w.db, w, None, GET, {"request_id": w.rid})
    hidden, _ = read(narrow.db, narrow, None, GET, {"request_id": narrow.rid})

    assert by_number.status == "ok" and n in dump(by_number.data)
    assert by_id.status == "ok" and n in dump(by_id.data) and w.rid.lower() in ids
    assert hidden.status in ("denied", "invalid", "error")


def test_the_reads_are_not_offered_without_the_approve_slug(world):
    from app.services.chatbot.agent import writes

    w = scene(world, slugs=(VIEW,))
    out, _ = read(w.db, w, None, LIST, {})

    assert out.status == "denied"
    with_slug = scene(world)
    ctx_names = {r.name for r in writes.permitted_user_reads(with_slug.db, _ctx(with_slug))}
    assert {LIST, GET} <= ctx_names


def _ctx(w):
    from app.services.chatbot.agent.access import build_context

    return build_context(w.db, w.respond_id)


# ------------------------------------------------------------------ approve: proposal, confirm, commit


def test_approve_proposal_states_the_notification_and_writes_nothing(world):
    from app.services.chatbot.agent import writes

    w = scene(world)
    before = sends(w)

    res, step = propose(w.db, w, None, DECIDE, decide_args(w), w.rid)

    assert res.status == "proposed" and step is not None
    s = step["summary"]
    assert s.startswith(f"{number(w)} (") and ": approve" in s and s.endswith(NOTIFIES)
    assert not UUID_RE.search(s)
    assert header(w).approval_status == "pending" and sends(w) == before
    assert writes.WRITES[DECIDE].record_key == "request_id"


def test_confirming_an_approval_commits_it_and_the_service_notifies_the_requester(world):
    w = scene(world)
    action = store(w.db, w, None, [(DECIDE, decide_args(w))], {w.rid})
    before = sends(w)

    outcome = chat_confirm(w, action)
    w.drain()

    assert outcome.status == "executed" and [s["status"] for s in outcome.steps] == ["done"]
    assert header(w).approval_status == "approved"
    assert sends(w) == before + 1  # the requester was told, by the service's own send
    change = next(c for c in outcome.steps[0]["changes"] if str(c["field"]).lower() == "approval")
    assert (change["before"], change["after"]) == ("Pending", "Approved")
    assert number(w) in change["record"] and not UUID_RE.search(dump(outcome.steps[0]["changes"]))
    assert "commits at" not in change["after"]


# ------------------------------------------------------------------ reject


def test_reject_needs_a_reason_and_then_rejects_with_it(world):
    w = scene(world)

    bare, none = propose(w.db, w, None, DECIDE, decide_args(w, "reject"), w.rid)
    blank, none2 = propose(w.db, w, None, DECIDE, decide_args(w, "reject", reason="   "), w.rid)
    ok, step = propose(w.db, w, None, DECIDE, decide_args(w, "reject", reason="price too high"), w.rid)

    assert bare.status == "invalid" and none is None and "Give a reason to reject." in bare.message
    assert blank.status == "invalid" and none2 is None
    assert ok.status == "proposed"
    assert 'reject: "price too high"' in step["summary"] and step["summary"].endswith(NOTIFIES)
    action = store(w.db, w, None, [(DECIDE, decide_args(w, "reject", reason="price too high"))], {w.rid})
    before = sends(w)

    outcome = chat_confirm(w, action)
    w.drain()

    assert outcome.status == "executed"
    assert header(w).approval_status == "rejected"
    assert sends(w) == before + 1
    change = next(c for c in outcome.steps[0]["changes"] if str(c["field"]).lower() == "approval")
    assert (change["before"], change["after"]) == ("Pending", "Rejected")


# ------------------------------------------------------------------ not pending, handling lock


def test_a_request_that_is_not_waiting_for_approval_is_invalid(world):
    w = scene(world)
    control, _ = propose(w.db, w, None, DECIDE, decide_args(w), w.rid)
    done = w.as_user(w.staff).post(f"{PR_BASE}/{w.rid}/approval-decision", json={"action": "approved"})
    assert done.status_code == 200, done.text

    res, step = propose(w.db, w, None, DECIDE, decide_args(w), w.rid)

    assert control.status == "proposed"
    assert res.status == "invalid" and step is None
    assert "This request is not waiting for approval (it is approved)." in res.message


def test_a_handling_lock_held_by_someone_else_denies_the_proposal(world):
    w = scene(world)
    settings_row(w.db, handling_lock_enabled_types=KIND)
    control, _ = propose(w.db, w, None, DECIDE, decide_args(w), w.rid)  # not escalated yet: no lock
    stage = w.chain.stages[1]
    tracker = open_tracker(w.db, KIND, w.rid)
    assert w.as_user(w.staff).post(f"/api/v1/sla-management/form-sla-tracking/{tracker.id}/escalate",
                                   json={"reason": "customer chasing"}).status_code == 200
    assert w.as_user(stage.tier2).post(f"/api/v1/sla-management/form-sla-tracking/{tracker.id}/claim").status_code == 200

    res, step = propose(w.db, w, None, DECIDE, decide_args(w), w.rid)

    assert control.status == "proposed"
    assert res.status == "denied" and step is None
    assert "being handled by" in res.message


# ------------------------------------------------------------------ R9: the console operator's reach


def test_a_narrow_console_operator_cannot_propose_a_decision_the_wider_one_can(world):
    w = scene(world)
    wide = operator(w, APPROVE, VIEW)
    narrow = operator(w, APPROVE, VIEW_OWN)

    ok, step = propose(w.db, w, wide, DECIDE, decide_args(w), w.rid)
    no, none = propose(w.db, w, narrow, DECIDE, decide_args(w), w.rid)

    assert ok.status == "proposed" and step is not None
    assert refused(no, none)


def test_the_list_for_a_narrow_operator_leaves_out_what_only_the_linked_user_may_see(world):
    w = scene(world)
    wide = operator(w, APPROVE, VIEW)
    narrow = operator(w, APPROVE, VIEW_OWN)

    wide_out, _ = read(w.db, w, wide, LIST, {})
    narrow_out, ids = read(w.db, w, narrow, LIST, {})

    assert number(w) in dump(wide_out.data)
    assert narrow_out.status in ("ok", "denied")
    assert number(w) not in dump(narrow_out.data) and w.rid.lower() not in ids


@pytest.mark.parametrize("narrowed, expected", [(True, "rejected"), (False, "executed")])
def test_confirm_rechecks_the_operators_reach(world, narrowed, expected):
    w = scene(world)
    op = operator(w, APPROVE, VIEW)
    action = store(w.db, w, op, [(DECIDE, decide_args(w))], {w.rid})
    if narrowed:
        revoke(w.db, op, VIEW)
        grant_more(w.db, op, VIEW_OWN)

    outcome = console_confirm(w.db, w, action, op)

    assert outcome.status == expected
    assert (header(w).approval_status == "approved") is (not narrowed)


# ------------------------------------------------------------------ the grace window


def test_with_a_grace_window_the_decision_is_parked_not_committed(world):
    w = scene(world, grace=60)
    action = store(w.db, w, None, [(DECIDE, decide_args(w))], {w.rid})
    before = sends(w)

    outcome = chat_confirm(w, action)

    step = outcome.steps[0]
    assert step["status"] == "parked"
    assert header(w).approval_status == "pending" and sends(w) == before  # nothing committed or sent
    stored = action_row(w.db, action.id).steps[0]
    assert stored["pending_action_id"] and stored["commit_at"]
    parked = w.db.query(SlaFormAction).filter(SlaFormAction.id == stored["pending_action_id"]).one()
    assert parked.status == "pending" and parked.action_key == "pr.approval_decision"
    assert "commits at" in outcome.reply_text
    change = next(c for c in step["changes"] if str(c["field"]).lower() == "approval")
    assert change["before"] == "Pending" and change["after"].startswith("Approved (commits at ")
    assert not UUID_RE.search(dump(step["changes"]))


def test_the_parked_decision_commits_when_its_window_lapses(world):
    w = scene(world, grace=60)
    action = store(w.db, w, None, [(DECIDE, decide_args(w))], {w.rid})
    chat_confirm(w, action)
    pending_id = action_row(w.db, action.id).steps[0]["pending_action_id"]
    before = sends(w)

    make_due(w.db, pending_id)
    current = w.as_user(w.staff).get(f"{FORM_ACTIONS}/current", params={"source_entity_type": KIND, "source_entity_id": w.rid})

    assert current.status_code == 200 and current.json()["pending"] is None
    assert header(w).approval_status == "approved" and sends(w) == before + 1  # as the screen's own commit


def test_the_cancel_tool_proposes_and_confirming_it_withdraws_the_parked_decision(world):
    w = scene(world, grace=60)
    decide = store(w.db, w, None, [(DECIDE, decide_args(w))], {w.rid})
    chat_confirm(w, decide)
    pending_id = action_row(w.db, decide.id).steps[0]["pending_action_id"]
    before = sends(w)

    res, step = propose(w.db, w, None, CANCEL, {"request_id": w.rid}, w.rid)
    action = store(w.db, w, None, [(CANCEL, {"request_id": w.rid})], {w.rid})
    outcome = chat_confirm(w, action)

    assert res.status == "proposed" and number(w) in step["summary"] and "cancel" in step["summary"].lower()
    assert not UUID_RE.search(step["summary"])
    assert outcome.status == "executed" and [s["status"] for s in outcome.steps] == ["done"]
    w.db.expire_all()
    assert w.db.query(SlaFormAction).filter(SlaFormAction.id == pending_id).one().status == "cancelled"
    assert header(w).approval_status == "pending" and sends(w) == before  # nothing was sent


def test_cancel_with_nothing_parked_is_refused_and_a_control_shows_the_tool_works_when_something_is(world):
    w = scene(world, grace=60)

    nothing, none = propose(w.db, w, None, CANCEL, {"request_id": w.rid}, w.rid)
    decide = store(w.db, w, None, [(DECIDE, decide_args(w))], {w.rid})
    chat_confirm(w, decide)
    something, step = propose(w.db, w, None, CANCEL, {"request_id": w.rid}, w.rid)

    assert something.status == "proposed" and step is not None  # control
    assert refused(nothing, none)


def test_only_the_requester_or_an_admin_can_withdraw_a_parked_decision(world):
    w = scene(world, grace=60)
    other = scene(world, grace=None)  # a second agent contact and linked user in the same world
    decide = store(w.db, w, None, [(DECIDE, decide_args(w))], {w.rid})
    chat_confirm(w, decide)
    pending_id = action_row(w.db, decide.id).steps[0]["pending_action_id"]
    other.rid = w.rid  # the second agent user acts on the first one's parked decision

    res, step = propose(w.db, other, None, CANCEL, {"request_id": w.rid}, w.rid)
    if step is not None:  # the gate may sit at execution rather than at proposal
        action = store(w.db, other, None, [(CANCEL, {"request_id": w.rid})], {w.rid})
        from app.services.chatbot.agent import actions

        outcome = actions.confirm(w.db, other.respond_id, str(action.id), via="chat", turn_id=str(uuid.uuid4()))
        assert outcome.steps[0]["status"] == "failed"
    w.db.expire_all()
    assert w.db.query(SlaFormAction).filter(SlaFormAction.id == pending_id).one().status == "pending"
    own, own_step = propose(w.db, w, None, CANCEL, {"request_id": w.rid}, w.rid)
    assert own.status == "proposed"  # control: the requester may


# ------------------------------------------------------------------ re-check at confirm


@pytest.mark.parametrize("how", ["decided elsewhere", "edited"])
def test_a_request_changed_since_the_proposal_is_rejected_and_nothing_is_written(world, how):
    w = scene(world)
    action = store(w.db, w, None, [(DECIDE, decide_args(w))], {w.rid})
    control = scene(world)
    ok = store(control.db, control, None, [(DECIDE, decide_args(control))], {control.rid})
    if how == "decided elsewhere":
        assert w.as_user(w.staff).post(f"{PR_BASE}/{w.rid}/approval-decision", json={"action": "rejected", "comments": "no"}).status_code == 200
    else:
        with company_scope(w.db, None):
            row = w.db.query(PurchaseRequestHeader).filter(PurchaseRequestHeader.id == w.rid).one()
            row.updated_at = row.updated_at + timedelta(seconds=5)
            w.db.commit()
    before = sends(w)

    fine = chat_confirm(control, ok)
    outcome = chat_confirm(w, action)

    assert fine.status == "executed"  # control: untouched, it goes through
    assert outcome.status == "rejected"
    assert "changed" in (outcome.steps[0]["error"] or "").lower() or "not waiting" in (outcome.steps[0]["error"] or "").lower()
    assert all(not s.get("changes") for s in outcome.steps)
    assert header(w).approval_status != "approved" and sends(w) == before


# ------------------------------------------------------------------ one turn


def test_a_turn_lists_the_waiting_requests_then_proposes_a_decision_and_commits_nothing(world):
    w = scene(world)
    script = [
        round_of(tc(LIST, {}, "l1")),
        round_of(tc(DECIDE, decide_args(w), "d1")),
        answer_("I have prepared the approval."),
    ]
    before = sends(w)

    result, _ = go(w.db, w, script, text_="approve the waiting purchase request")

    assert result.pending_action is not None
    assert number(w) in result.reply_text and NOTIFIES in result.reply_text
    assert header(w).approval_status == "pending" and sends(w) == before
