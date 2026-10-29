"""FORMS-REGRESSION: purchase request and sponsorship form lifecycle chains over the real routes.

Plan: documentation/plans/forms/PLAN-forms-lifecycle-regression-29oct.md. Harness and what it
stubs: tests/_forms_chain_support.py (only the Respond.io network send; the outbox row is the
app's own).

PR and SF share the router and the service (`header.request_type` picks the SLA type and the
Respond use case), so every chain runs for both kinds. The SLA chain mirrors the shipped shape:
review (submit -> send_for_approval / reject_submitted), approval (send_for_approval ->
approved / approval_rejected), processing (approved -> resolved), `voided` closing each stage.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from tests._forms_chain_support import (
    ESCALATE,
    EXTEND,
    FORM_ACTIONS,
    FORM_SLA,
    CONV_SLA,
    PR_BASE,
    SUB,
    UNDO,
    contact,
    event_types,
    form_action,
    grant,
    make_due,
    notifications,
    open_tracker,
    outbox,
    revision_config,
    settings_row,
    sla_chain,
    trackers,
    user,
    world,  # noqa: F401  (fixture)
)

KINDS = ["purchase_request", "sponsorship_form"]
TABLE = "purchase_requests"
STAFF_SLUGS = (
    "procurement.purchase_requests.view",
    "procurement.purchase_requests.send_for_approval",
    "procurement.purchase_requests.approve",
    "procurement.purchase_requests.process",
    "procurement.purchase_requests.close",
    "procurement.purchase_requests.void",
    UNDO,
    ESCALATE,
)


def _setup(w, kind, *, approval_grace=None):
    db = w.db
    w.chain = sla_chain(db, kind, [
        dict(start_event="submit", resolve_event="send_for_approval,reject_submitted,voided",
             advance_on_event="send_for_approval"),
        dict(start_event="send_for_approval", resolve_event="approved,approval_rejected,voided",
             advance_on_event="approved", grace_seconds=approval_grace),
        dict(start_event="approved", resolve_event="resolved,voided"),
    ])
    w.kind = kind
    w.staff = user(db, f"{kind} staff")
    grant(db, w.staff, *STAFF_SLUGS)
    for stage in w.chain.stages:
        grant(db, stage.tier1, EXTEND, *STAFF_SLUGS)
        grant(db, stage.tier2, EXTEND, *STAFF_SLUGS)
    w.contact = contact(db, name=f"{kind} salesperson")
    db.commit()
    return w


def _draft(w):
    c = w.as_contact(w.contact)
    res = c.post(f"{SUB}/{w.kind}", json={
        "fields": {"customer_name": "ZZT Example Trading", "purpose": "showroom stock"},
        "products": [{"item_code": "ZZT-TILE-1", "quantity": 4, "unit_price": 25, "total": 100}],
    })
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "draft"
    return res.json()["id"]


def _submitted(w):
    rid = _draft(w)
    res = w.as_contact(w.contact).post(f"{SUB}/{w.kind}/{rid}/submit")
    assert res.status_code == 200, res.text
    return rid


def _portal(w, rid):
    res = w.as_contact(w.contact).get(f"{SUB}/{w.kind}/{rid}")
    assert res.status_code == 200, res.text
    return res.json()


def _sends(w, rid):
    """Outbox rows for this form: every one written by the app as a delivered send."""
    rows = outbox(w.db, TABLE, rid)
    assert all(r.status == "success" for r in rows), [(r.status, r.error_message) for r in rows]
    return rows


def _last_text(w):
    assert w.sends, "no Respond send was made"
    return w.sends[-1]["text"]


def _to_pending_approval(w, rid):
    res = w.as_user(w.staff).post(f"{PR_BASE}/{rid}/set-pending-approval")
    assert res.status_code == 200, res.text
    return res


# ------------------------------------------------------------------ draft, save, submit


@pytest.mark.parametrize("kind", KINDS)
def test_draft_save_reopen_submit_starts_the_review_stage(world, kind):
    w = _setup(world, kind)
    rid = _draft(w)
    c = w.as_contact(w.contact)

    saved = c.put(f"{SUB}/{kind}/{rid}", json={"fields": {"customer_name": "ZZT Saved Name",
                                                         "purpose": "showroom stock"}})
    assert saved.status_code == 200, saved.text
    reopened = _portal(w, rid)
    assert reopened["status"] == "draft" and reopened["is_draft"] is True
    assert reopened["customer_name"] == "ZZT Saved Name"
    assert trackers(w.db, kind, rid) == []  # a draft starts no SLA

    sub = c.post(f"{SUB}/{kind}/{rid}/submit")
    assert sub.status_code == 200, sub.text
    body = sub.json()
    assert body["status"] == "submitted"
    assert body["document_number"]
    assert body["is_editable"] is False

    stage = open_tracker(w.db, kind, rid)
    assert stage.team_set_code == w.chain.stages[0].team_set
    assert stage.assigned_to_id == w.chain.stages[0].tier1
    assert notifications(w.db, w.chain.stages[0].tier1, event_type="assigned")
    assert _sends(w, rid) == []  # submitting tells the contact nothing

    # a submitted form is no longer a draft: neither PUT nor DELETE reaches it
    assert c.put(f"{SUB}/{kind}/{rid}", json={"fields": {"purpose": "x"}}).status_code == 400
    assert c.delete(f"{SUB}/{kind}/{rid}").status_code == 400


# ------------------------------------------------------------------ reject, resubmit, approve


@pytest.mark.parametrize("kind", KINDS)
def test_reject_resubmit_approve_process_full_chain_with_outbox(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    review = open_tracker(w.db, kind, rid)
    s = w.as_user(w.staff)

    # reject at submitted
    rej = s.post(f"{PR_BASE}/{rid}/reject-submitted", json={"rejection_reason": "missing PO copy"})
    assert rej.status_code == 200, rej.text
    seen = _portal(w, rid)
    assert seen["status"] == "rejected"
    assert seen["rejection_reason"] == "missing PO copy"
    rows = _sends(w, rid)
    assert len(rows) == 1
    assert "rejected" in _last_text(w) and "missing PO copy" in _last_text(w)
    assert w.sends[-1]["use_case"] == kind
    assert trackers(w.db, kind, rid, open_only=True) == []
    w.db.refresh(review)
    assert review.is_resolved is True

    # the contact resubmits: Resubmitted, a fresh review stage
    res = w.as_contact(w.contact).post(f"{SUB}/{kind}/{rid}/submit")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "resubmitted"
    assert res.json()["rejection_reason"] is None
    again = open_tracker(w.db, kind, rid)
    assert again.id != review.id and again.team_set_code == w.chain.stages[0].team_set
    assert len(_sends(w, rid)) == 1  # resubmitting tells nobody on the outbox

    # send for approval: the approval stage opens, the contact hears "pending approval"
    _to_pending_approval(w, rid)
    approval = open_tracker(w.db, kind, rid)
    assert approval.team_set_code == w.chain.stages[1].team_set
    assert len(_sends(w, rid)) == 2

    # approve: processing stage opens, contact told
    ok = s.post(f"{PR_BASE}/{rid}/approval-decision", json={"action": "approved", "comments": None})
    assert ok.status_code == 200, ok.text
    assert ok.json()["approval_status"] == "approved"
    processing = open_tracker(w.db, kind, rid)
    assert processing.team_set_code == w.chain.stages[2].team_set
    assert len(_sends(w, rid)) == 3
    assert "approved" in _last_text(w).lower()

    # process: every stage closed, contact told once more
    done = s.post(f"{PR_BASE}/{rid}/process", json={"note": None})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "processed_by_cs"
    assert trackers(w.db, kind, rid, open_only=True) == []
    assert len(_sends(w, rid)) == 4
    assert len(trackers(w.db, kind, rid)) == 4  # review, review again, approval, processing


@pytest.mark.parametrize("kind", KINDS)
def test_approval_rejected_shows_rejected_and_resubmit_restarts_review(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    _to_pending_approval(w, rid)
    sends_before = len(_sends(w, rid))

    no = w.as_user(w.staff).post(f"{PR_BASE}/{rid}/approval-decision",
                                 json={"action": "rejected", "comments": "over budget"})
    assert no.status_code == 200, no.text
    seen = _portal(w, rid)
    assert seen["status"] == "rejected"  # the portal reads approval_status
    assert len(_sends(w, rid)) == sends_before + 1
    assert "over budget" in _last_text(w)
    assert trackers(w.db, kind, rid, open_only=True) == []

    # comments are mandatory on a rejection, and a decided form cannot be decided again
    assert w.as_user(w.staff).post(f"{PR_BASE}/{rid}/approval-decision",
                                   json={"action": "approved"}).status_code == 409

    res = w.as_contact(w.contact).post(f"{SUB}/{kind}/{rid}/submit")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "resubmitted"
    assert res.json()["approval_status"] is None
    assert open_tracker(w.db, kind, rid).team_set_code == w.chain.stages[0].team_set


# ------------------------------------------------------------------ revise


@pytest.mark.parametrize("kind", KINDS)
def test_revise_restarts_review_counts_down_and_refuses_at_the_cap(world, kind):
    w = _setup(world, kind)
    revision_config(w.db, kind, allowed_statuses=["submitted", "approved"], max_revisions=1)
    rid = _submitted(w)
    first = open_tracker(w.db, kind, rid)
    c = w.as_contact(w.contact)

    before = _portal(w, rid)["revision"]
    assert before["enabled"] is True and before["remaining"] == 1

    rev = c.post(f"{SUB}/{kind}/{rid}/revise", json={
        "reason": "customer doubled the order", "expected_revision_no": 0,
        "fields": {"customer_name": "ZZT Example Trading", "purpose": "showroom stock"},
        "products": [{"item_code": "ZZT-TILE-1", "quantity": 8, "unit_price": 25, "total": 200}],
    })
    assert rev.status_code == 200, rev.text
    assert rev.json()["revision_no"] == 1
    assert rev.json()["revision"]["remaining"] == 0
    assert rev.json()["submission"]["status"] == "submitted"

    w.db.refresh(first)
    assert first.voided_at is not None  # the old review stage is voided, not resolved
    restarted = open_tracker(w.db, kind, rid)
    assert restarted.id != first.id and restarted.team_set_code == w.chain.stages[0].team_set

    stale = c.post(f"{SUB}/{kind}/{rid}/revise", json={
        "reason": "again", "expected_revision_no": 0, "fields": {}})
    assert stale.status_code == 409, stale.text  # stale revision number
    capped = c.post(f"{SUB}/{kind}/{rid}/revise", json={
        "reason": "again", "expected_revision_no": 1, "fields": {}})
    assert capped.status_code == 422, capped.text
    assert "used all" in capped.json()["message"]

    history = c.get(f"{SUB}/{kind}/{rid}/revisions")
    assert history.status_code == 200, history.text
    assert len(history.json()["items"]) == 2  # the original and revision 1


# ------------------------------------------------------------------ undo (cancel in grace)


@pytest.mark.parametrize("kind", KINDS)
def test_approve_inside_grace_then_cancel_changes_nothing_and_sends_nothing(world, kind):
    w = _setup(world, kind, approval_grace=60)
    rid = _submitted(w)
    _to_pending_approval(w, rid)
    approval = open_tracker(w.db, kind, rid)
    sends_before = len(_sends(w, rid))

    parked = w.as_user(w.staff).post(f"{PR_BASE}/{rid}/approval-decision",
                                     json={"action": "approved", "comments": None})
    assert parked.status_code == 202, parked.text
    assert parked.json()["deferred"] is True
    assert parked.json()["window_seconds"] == 60
    action_id = parked.json()["pending_action_id"]

    current = w.as_user(w.staff).get(f"{FORM_ACTIONS}/current",
                                     params={"source_entity_type": kind, "source_entity_id": rid})
    assert current.status_code == 200, current.text
    assert current.json()["pending"]["id"] == action_id
    assert current.json()["pending"]["can_cancel"] is True

    # someone else cannot withdraw it
    other = w.chain.stages[0].tier1
    assert w.as_user(other).post(f"{FORM_ACTIONS}/{action_id}/cancel").status_code == 409

    cancel = w.as_user(w.staff).post(f"{FORM_ACTIONS}/{action_id}/cancel")
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelled"
    assert form_action(w.db, action_id).status == "cancelled"

    detail = w.as_user(w.staff).get(f"{PR_BASE}/{rid}")
    assert detail.json()["approval_status"] == "pending"
    assert len(_sends(w, rid)) == sends_before  # nothing reached the contact
    assert open_tracker(w.db, kind, rid).id == approval.id  # the stage never moved

    # a cancelled action cannot be cancelled again
    assert w.as_user(w.staff).post(f"{FORM_ACTIONS}/{action_id}/cancel").status_code == 409


@pytest.mark.parametrize("kind", KINDS)
def test_approve_inside_grace_commits_when_the_window_lapses(world, kind):
    w = _setup(world, kind, approval_grace=60)
    rid = _submitted(w)
    _to_pending_approval(w, rid)
    sends_before = len(_sends(w, rid))

    parked = w.as_user(w.staff).post(f"{PR_BASE}/{rid}/approval-decision",
                                     json={"action": "approved", "comments": None})
    assert parked.status_code == 202, parked.text
    action_id = parked.json()["pending_action_id"]
    assert len(_sends(w, rid)) == sends_before  # nothing sent while parked

    make_due(w.db, action_id)
    # the lazy commit on read, the same path the banner polls
    current = w.as_user(w.staff).get(f"{FORM_ACTIONS}/current",
                                     params={"source_entity_type": kind, "source_entity_id": rid})
    assert current.status_code == 200, current.text
    assert current.json()["pending"] is None
    assert form_action(w.db, action_id).status == "committed"

    detail = w.as_user(w.staff).get(f"{PR_BASE}/{rid}").json()
    assert detail["approval_status"] == "approved"
    assert len(_sends(w, rid)) == sends_before + 1
    assert open_tracker(w.db, kind, rid).team_set_code == w.chain.stages[2].team_set


# ------------------------------------------------------------------ revert (undo after commit)


@pytest.mark.parametrize("kind", KINDS)
def test_revert_after_commit_restores_the_form_and_sends_a_correction(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    _to_pending_approval(w, rid)
    approval = open_tracker(w.db, kind, rid)
    ok = w.as_user(w.staff).post(f"{PR_BASE}/{rid}/approval-decision",
                                 json={"action": "approved", "comments": None})
    assert ok.status_code == 200, ok.text  # grace 0: immediate, still undoable
    processing = open_tracker(w.db, kind, rid)
    sends_before = len(_sends(w, rid))

    q = {"source_entity_type": kind, "source_entity_id": rid}
    elig = w.as_user(w.staff).get(f"{FORM_ACTIONS}/eligibility", params=q)
    assert elig.status_code == 200, elig.text
    assert elig.json()["can_undo"] is True and elig.json()["tells_contact"] is True

    # the reason is mandatory
    assert w.as_user(w.staff).post(f"{FORM_ACTIONS}/undo", json={**q, "reason": ""}).status_code == 422

    undo = w.as_user(w.staff).post(f"{FORM_ACTIONS}/undo", json={**q, "reason": "approved the wrong one"})
    assert undo.status_code == 200, undo.text
    assert undo.json()["status"] == "undone"

    detail = w.as_user(w.staff).get(f"{PR_BASE}/{rid}").json()
    assert detail["approval_status"] == "pending"
    assert open_tracker(w.db, kind, rid).id == approval.id  # the approval stage is reopened
    w.db.refresh(processing)
    assert processing.voided_at is not None or processing.is_resolved is True
    assert "reopened" in event_types(w.db, approval.id)

    rows = _sends(w, rid)
    assert len(rows) == sends_before + 1
    assert "changed back" in _last_text(w) and "approved the wrong one" in _last_text(w)

    # nothing left to undo
    again = w.as_user(w.staff).post(f"{FORM_ACTIONS}/undo", json={**q, "reason": "again"})
    assert again.status_code == 409, again.text


# ------------------------------------------------------------------ SLA extension


@pytest.mark.parametrize("kind", KINDS)
def test_extend_moves_the_due_date_logs_it_and_survives_an_undo(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    _to_pending_approval(w, rid)
    approval = open_tracker(w.db, kind, rid)
    assignee = approval.assigned_to_id
    old_due = approval.due_at_resolution

    # only the assignee may extend
    other = w.as_user(w.staff).post(f"{CONV_SLA}/{approval.id}/extend",
                                    json={"days": 2, "reason": "waiting on supplier"})
    assert other.status_code == 403, other.text

    ext = w.as_user(assignee).post(f"{CONV_SLA}/{approval.id}/extend",
                                   json={"days": 2, "reason": "waiting on supplier"})
    assert ext.status_code == 200, ext.text
    w.db.refresh(approval)
    assert approval.due_at_resolution > old_due + timedelta(days=1)
    assert approval.extension_count == 1
    assert "extend" in event_types(w.db, approval.id)
    extended_due = approval.due_at_resolution

    # approve, then undo: the reopened stage keeps the extension
    assert w.as_user(w.staff).post(f"{PR_BASE}/{rid}/approval-decision",
                                   json={"action": "approved"}).status_code == 200
    undo = w.as_user(w.staff).post(f"{FORM_ACTIONS}/undo", json={
        "source_entity_type": kind, "source_entity_id": rid, "reason": "too early"})
    assert undo.status_code == 200, undo.text
    w.db.refresh(approval)
    assert approval.is_resolved is False
    assert approval.due_at_resolution == extended_due
    assert approval.extension_count == 1


# ------------------------------------------------------------------ escalation and handling


@pytest.mark.parametrize("kind", KINDS)
def test_manual_escalate_then_claim_lock_and_take_over_before_approving(world, kind):
    w = _setup(world, kind)
    settings_row(w.db, handling_lock_enabled_types=kind)
    rid = _submitted(w)
    _to_pending_approval(w, rid)
    stage = w.chain.stages[1]
    approval = open_tracker(w.db, kind, rid)

    blank = w.as_user(w.staff).post(f"{FORM_SLA}/{approval.id}/escalate", json={"reason": "  "})
    assert blank.status_code == 422, blank.text
    esc = w.as_user(w.staff).post(f"{FORM_SLA}/{approval.id}/escalate",
                                  json={"reason": "customer chasing"})
    assert esc.status_code == 200, esc.text
    assert esc.json()["current_tier"] == 2
    assert esc.json()["assigned_to_id"] == stage.tier2
    assert esc.json()["escalation_reason"]
    assert notifications(w.db, stage.tier2, event_type="escalated")
    assert "escalation" in event_types(w.db, approval.id)

    # escalated + lock on: nobody acts until someone claims it
    blocked = w.as_user(stage.tier2).post(f"{PR_BASE}/{rid}/approval-decision",
                                          json={"action": "approved"})
    assert blocked.status_code == 403, blocked.text
    assert "Claim" in blocked.text

    claim = w.as_user(stage.tier2).post(f"{FORM_SLA}/{approval.id}/claim")
    assert claim.status_code == 200, claim.text
    assert claim.json()["handled_by_id"] == stage.tier2
    assert w.as_user(stage.tier1).post(f"{FORM_SLA}/{approval.id}/claim").status_code == 409
    held = w.as_user(stage.tier1).post(f"{PR_BASE}/{rid}/approval-decision", json={"action": "approved"})
    assert held.status_code == 403, held.text  # "being handled by"

    # a wrong expected holder is refused, the right one takes over
    wrong = w.as_user(stage.tier1).post(f"{FORM_SLA}/{approval.id}/take-over",
                                        json={"expected_handler_id": stage.tier1})
    assert wrong.status_code == 409, wrong.text
    took = w.as_user(stage.tier1).post(f"{FORM_SLA}/{approval.id}/take-over",
                                       json={"expected_handler_id": stage.tier2})
    assert took.status_code == 200, took.text
    assert took.json()["handled_by_id"] == stage.tier1

    ok = w.as_user(stage.tier1).post(f"{PR_BASE}/{rid}/approval-decision", json={"action": "approved"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["approval_status"] == "approved"


@pytest.mark.parametrize("kind", KINDS)
def test_overdue_sweep_escalates_the_stage_and_tells_the_next_tier(world, kind, monkeypatch):
    from app.services import form_sla_service as fss

    w = _setup(world, kind)
    rid = _submitted(w)
    review = open_tracker(w.db, kind, rid)
    stage = w.chain.stages[0]

    # not overdue yet: the sweep leaves it alone
    fss.FormSLAOrchestrator(w.db).scan_overdue_and_escalate()
    w.db.refresh(review)
    assert review.current_tier == 1

    later = review.due_at_resolution + timedelta(hours=1)
    monkeypatch.setattr(fss, "_utc_naive_now", lambda: later)
    result = fss.FormSLAOrchestrator(w.db).scan_overdue_and_escalate()
    assert result["escalated"] >= 1
    w.db.refresh(review)
    assert review.current_tier == 2
    assert review.assigned_to_id == stage.tier2
    assert review.escalated_at is not None
    assert notifications(w.db, stage.tier2, event_type="escalated")

    seen = w.as_user(w.staff).get(FORM_SLA, params={"source_entity_type": kind, "source_entity_id": rid})
    assert seen.status_code == 200, seen.text
    assert seen.json()["data"][0]["current_tier"] == 2


# ------------------------------------------------------------------ void


@pytest.mark.parametrize("kind", KINDS)
def test_void_stops_the_sla_tells_the_contact_and_locks_the_form(world, kind):
    w = _setup(world, kind)
    rid = _submitted(w)
    _to_pending_approval(w, rid)
    sends_before = len(_sends(w, rid))

    short = w.as_user(w.staff).post(f"{PR_BASE}/{rid}/void", json={"void_reason": "x"})
    assert short.status_code == 422, short.text
    void = w.as_user(w.staff).post(f"{PR_BASE}/{rid}/void", json={"void_reason": "duplicate of another"})
    assert void.status_code == 200, void.text
    assert void.json()["status"] == "voided"

    assert trackers(w.db, kind, rid, open_only=True) == []
    assert len(_sends(w, rid)) == sends_before + 1
    assert _portal(w, rid)["status"] == "voided"

    # terminal: no second void, no undo of the earlier send-for-approval
    s = w.as_user(w.staff)
    assert s.post(f"{PR_BASE}/{rid}/void", json={"void_reason": "again please"}).status_code == 409
    undo = s.post(f"{FORM_ACTIONS}/undo", json={"source_entity_type": kind, "source_entity_id": rid,
                                               "reason": "bring it back"})
    assert undo.status_code == 409, undo.text


@pytest.mark.parametrize("kind", KINDS)
def test_a_voided_form_pending_approval_cannot_be_approved(world, kind):
    """Void is terminal and irreversible (PLAN-form-void D3/D6). A form voided while it waits
    for approval keeps approval_status 'pending', and decide_approval only checks that
    column (procurement_service.py decide_approval), so the approve must still be refused."""
    w = _setup(world, kind)
    rid = _submitted(w)
    _to_pending_approval(w, rid)
    s = w.as_user(w.staff)
    assert s.post(f"{PR_BASE}/{rid}/void", json={"void_reason": "duplicate of another"}).status_code == 200

    res = s.post(f"{PR_BASE}/{rid}/approval-decision", json={"action": "approved"})
    detail = s.get(f"{PR_BASE}/{rid}").json()
    assert detail["status"] == "voided", f"voided form came back as {detail['status']!r}"
    assert res.status_code == 409, res.text
