"""FORMS-REGRESSION: complaint lifecycle chains over the real routes.

Plan: documentation/plans/forms/PLAN-forms-lifecycle-regression-29oct.md. Harness:
tests/_forms_chain_support.py.

Complaint sends to the contact go through the `respond_io` RQ queue, not the request, so each
decision is followed by `w.drain()`: the worker body runs inline on this test's connection and
writes the outbox row the worker would. Asserting the row (not the enqueue) proves the job's
arguments were good enough for the worker to send.

SLA chain: technical (submit -> approved / rejected, technical_team_response responds),
CS processing (approved -> resolved), `voided` closing each stage.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from tests._forms_chain_support import (
    CX_BASE,
    ESCALATE,
    EXTEND,
    FORM_ACTIONS,
    FORM_SLA,
    CONV_SLA,
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
    settings_row,
    sla_chain,
    trackers,
    user,
    world,  # noqa: F401  (fixture)
)

KIND = "complaint"
TABLE = "complaints"
STAFF_SLUGS = (
    "complaint_management.complaints.view",
    "complaint_management.complaints.approve",
    "complaint_management.complaints.reject",
    "complaint_management.complaints.resolve",
    "complaint_management.complaints.close",
    "complaint_management.complaints.void",
    UNDO,
    ESCALATE,
)


def _setup(w, *, decide_grace=None):
    db = w.db
    w.chain = sla_chain(db, KIND, [
        dict(start_event="submit", respond_event="technical_team_response",
             resolve_event="approved,rejected,voided", advance_on_event="approved",
             grace_seconds=decide_grace),
        dict(start_event="approved", resolve_event="resolved,voided"),
    ])
    w.staff = user(db, "complaint staff")
    grant(db, w.staff, *STAFF_SLUGS)
    for stage in w.chain.stages:
        grant(db, stage.tier1, EXTEND, *STAFF_SLUGS)
        grant(db, stage.tier2, EXTEND, *STAFF_SLUGS)
    w.contact = contact(db, name="complaint salesperson")
    db.commit()
    return w


FIELDS = {
    "customer_name": "ZZT Example Hardware",
    "delivery_order_number": "DO-ZZT-1001",
    "defect_description": "Tiles chipped on arrival",
    "product_code": "ZZT-TILE-1",
    "quantity": 12,
}


def _draft(w):
    res = w.as_contact(w.contact).post(f"{SUB}/{KIND}", json={"fields": FIELDS})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "draft"
    return res.json()["id"]


def _submitted(w):
    cid = _draft(w)
    res = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{cid}/submit")
    assert res.status_code == 200, res.text
    return cid


def _sends(w, cid):
    w.drain()
    rows = outbox(w.db, TABLE, cid)
    assert all(r.status == "success" for r in rows), [(r.status, r.error_message) for r in rows]
    return rows


def _respond(w, cid, text="Replacement tiles will be sent", actor=None):
    res = w.as_user(actor or w.staff).post(f"{CX_BASE}/{cid}/update-and-reply",
                                           json={"technical_team_response": text})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "responded"
    return res


def _portal(w, cid):
    res = w.as_contact(w.contact).get(f"{SUB}/{KIND}/{cid}")
    assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------------ draft, save, submit


def test_draft_save_reopen_submit_starts_the_technical_stage(world):
    w = _setup(world)
    cid = _draft(w)
    c = w.as_contact(w.contact)
    saved = c.put(f"{SUB}/{KIND}/{cid}", json={"fields": {**FIELDS, "quantity": 20}})
    assert saved.status_code == 200, saved.text
    assert _portal(w, cid)["is_draft"] is True
    assert trackers(w.db, KIND, cid) == []

    sub = c.post(f"{SUB}/{KIND}/{cid}/submit")
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "submitted"
    assert sub.json()["document_number"]
    staff_view = w.as_user(w.staff).get(f"{CX_BASE}/{cid}")
    assert staff_view.status_code == 200, staff_view.text
    assert staff_view.json()["status"] == "submitted"

    stage = open_tracker(w.db, KIND, cid)
    assert stage.assigned_to_id == w.chain.stages[0].tier1
    assert notifications(w.db, w.chain.stages[0].tier1, event_type="assigned")
    assert _sends(w, cid) == []


# ------------------------------------------------------------------ respond, reject, resubmit, approve


def test_respond_reject_resubmit_respond_approve_process_with_outbox(world):
    w = _setup(world)
    cid = _submitted(w)
    first = open_tracker(w.db, KIND, cid)
    s = w.as_user(w.staff)

    # approve / reject wait for the technical response
    assert s.post(f"{CX_BASE}/{cid}/approve").status_code == 400  # validation: not decidable here

    _respond(w, cid)
    assert len(_sends(w, cid)) == 1  # the response reaches the contact
    w.db.refresh(first)
    assert first.is_responded is True

    blank = s.post(f"{CX_BASE}/{cid}/reject", json={"rejection_reason": " "})
    assert blank.status_code == 400, blank.text
    assert "rejection_reason is required" in blank.json()["message"]
    assert w.as_user(w.staff).get(f"{CX_BASE}/{cid}").json()["status"] == "responded"
    rej = s.post(f"{CX_BASE}/{cid}/reject", json={"rejection_reason": "photos do not show the defect"})
    assert rej.status_code == 200, rej.text
    assert rej.json()["status"] == "rejected"
    seen = _portal(w, cid)
    assert seen["status"] == "rejected"
    assert seen["rejection_reason"] == "photos do not show the defect"
    assert len(_sends(w, cid)) == 2
    assert "photos do not show the defect" in w.sends[-1]["text"]
    assert trackers(w.db, KIND, cid, open_only=True) == []

    # resubmitted with better evidence: a fresh technical stage
    res = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{cid}/submit",
                                       json={"fields": {**FIELDS, "defect_description": "Chipped, photos attached"}})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "resubmitted"
    again = open_tracker(w.db, KIND, cid)
    assert again.id != first.id
    assert len(_sends(w, cid)) == 2

    _respond(w, cid, "Approved for replacement")
    ok = s.post(f"{CX_BASE}/{cid}/approve")
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved"
    assert open_tracker(w.db, KIND, cid).team_set_code == w.chain.stages[1].team_set
    assert len(_sends(w, cid)) == 4  # response + approval

    done = s.post(f"{CX_BASE}/{cid}/process", json={"note": "replacement delivered"})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "processed_by_cs"
    assert trackers(w.db, KIND, cid, open_only=True) == []
    assert len(_sends(w, cid)) == 5


# ------------------------------------------------------------------ undo and revert


def test_decide_inside_grace_then_cancel_sends_nothing(world):
    w = _setup(world, decide_grace=45)
    cid = _submitted(w)
    _respond(w, cid)
    before = len(_sends(w, cid))
    stage = open_tracker(w.db, KIND, cid)

    parked = w.as_user(w.staff).post(f"{CX_BASE}/{cid}/reject",
                                     json={"rejection_reason": "not our product"})
    assert parked.status_code == 202, parked.text
    action_id = parked.json()["pending_action_id"]

    cancel = w.as_user(w.staff).post(f"{FORM_ACTIONS}/{action_id}/cancel")
    assert cancel.status_code == 200, cancel.text
    assert w.as_user(w.staff).get(f"{CX_BASE}/{cid}").json()["status"] == "responded"
    assert len(_sends(w, cid)) == before
    assert open_tracker(w.db, KIND, cid).id == stage.id


def test_decide_inside_grace_commits_through_the_sweep(world):
    from app.services.form_action_service import FormActionService

    w = _setup(world, decide_grace=45)
    cid = _submitted(w)
    _respond(w, cid)
    before = len(_sends(w, cid))

    parked = w.as_user(w.staff).post(f"{CX_BASE}/{cid}/approve")
    assert parked.status_code == 202, parked.text
    action_id = parked.json()["pending_action_id"]
    assert len(_sends(w, cid)) == before

    make_due(w.db, action_id)
    out = FormActionService(w.db).commit_due()  # the scheduler's form_action_commit task
    assert out["committed"] == 1
    assert form_action(w.db, action_id).status == "committed"
    w.db.expire_all()
    assert w.as_user(w.staff).get(f"{CX_BASE}/{cid}").json()["status"] == "approved"
    assert len(_sends(w, cid)) == before + 1


def test_revert_an_approval_restores_responded_and_sends_a_correction(world):
    w = _setup(world)
    cid = _submitted(w)
    _respond(w, cid)
    technical = open_tracker(w.db, KIND, cid)
    assert w.as_user(w.staff).post(f"{CX_BASE}/{cid}/approve").status_code == 200
    before = len(_sends(w, cid))

    undo = w.as_user(w.staff).post(f"{FORM_ACTIONS}/undo", json={
        "source_entity_type": KIND, "source_entity_id": cid, "reason": "wrong complaint approved"})
    assert undo.status_code == 200, undo.text
    assert w.as_user(w.staff).get(f"{CX_BASE}/{cid}").json()["status"] == "responded"
    assert open_tracker(w.db, KIND, cid).id == technical.id
    assert len(_sends(w, cid)) == before + 1
    assert "changed back" in w.sends[-1]["text"]

    # a user without the undo slug is refused
    nobody = user(w.db, "no undo")
    grant(w.db, nobody, "complaint_management.complaints.view")
    w.db.commit()
    assert w.as_user(w.staff).post(f"{CX_BASE}/{cid}/approve").status_code == 200
    refused = w.as_user(nobody).post(f"{FORM_ACTIONS}/undo", json={
        "source_entity_type": KIND, "source_entity_id": cid, "reason": "x"})
    assert refused.status_code == 403, refused.text


# ------------------------------------------------------------------ extend, escalate, handle


def test_extend_escalate_claim_then_holder_responds(world):
    w = _setup(world)
    settings_row(w.db, handling_lock_enabled_types=KIND)
    cid = _submitted(w)
    tech = open_tracker(w.db, KIND, cid)
    stage = w.chain.stages[0]

    old_due = tech.due_at_resolution
    ext = w.as_user(stage.tier1).post(f"{CONV_SLA}/{tech.id}/extend",
                                      json={"days": 1, "reason": "lab test pending"})
    assert ext.status_code == 200, ext.text
    w.db.refresh(tech)
    assert tech.due_at_resolution > old_due and tech.extension_count == 1

    esc = w.as_user(w.staff).post(f"{FORM_SLA}/{tech.id}/escalate", json={"reason": "VIP customer"})
    assert esc.status_code == 200, esc.text
    assert esc.json()["current_tier"] == 2 and esc.json()["assigned_to_id"] == stage.tier2
    assert notifications(w.db, stage.tier2, event_type="escalated")

    # escalated + lock on: the response is refused until claimed
    blocked = w.as_user(stage.tier2).post(f"{CX_BASE}/{cid}/update-and-reply",
                                          json={"technical_team_response": "on it"})
    assert blocked.status_code == 403, blocked.text
    assert w.as_user(stage.tier2).post(f"{FORM_SLA}/{tech.id}/claim").status_code == 200
    _respond(w, cid, "Handled after escalation", actor=stage.tier2)

    # release, then the next decision needs a fresh claim
    rel = w.as_user(stage.tier2).post(f"{FORM_SLA}/{tech.id}/release")
    assert rel.status_code == 200, rel.text
    assert rel.json()["handled_by_id"] is None
    assert w.as_user(stage.tier2).post(f"{CX_BASE}/{cid}/approve").status_code == 403
    assert w.as_user(stage.tier1).post(f"{FORM_SLA}/{tech.id}/claim").status_code == 200
    ok = w.as_user(stage.tier1).post(f"{CX_BASE}/{cid}/approve")
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved"
    assert {"extend", "escalation", "handling_claimed", "handling_released"} <= set(event_types(w.db, tech.id))


def test_overdue_sweep_escalates_an_unanswered_complaint(world, monkeypatch):
    from app.services import form_sla_service as fss

    w = _setup(world)
    cid = _submitted(w)
    tech = open_tracker(w.db, KIND, cid)
    monkeypatch.setattr(fss, "_utc_naive_now", lambda: tech.due_at + timedelta(minutes=5))
    out = fss.FormSLAOrchestrator(w.db).scan_overdue_and_escalate()
    assert out["escalated"] >= 1
    w.db.refresh(tech)
    assert tech.current_tier == 2 and tech.assigned_to_id == w.chain.stages[0].tier2
    assert "did not" in (tech.escalation_reason or "")


# ------------------------------------------------------------------ void


def test_void_stops_the_sla_and_tells_the_contact(world):
    w = _setup(world)
    cid = _submitted(w)
    _respond(w, cid)
    before = len(_sends(w, cid))
    void = w.as_user(w.staff).post(f"{CX_BASE}/{cid}/void", json={"void_reason": "logged twice"})
    assert void.status_code == 200, void.text
    assert void.json()["status"] == "voided"
    assert trackers(w.db, KIND, cid, open_only=True) == []
    assert len(_sends(w, cid)) == before + 1
    s = w.as_user(w.staff)
    assert s.post(f"{CX_BASE}/{cid}/approve").status_code == 400  # validation: not decidable here
    assert s.post(f"{CX_BASE}/{cid}/void", json={"void_reason": "again please"}).status_code == 409
