"""FORMS-REGRESSION: stock inquiry lifecycle chains over the real routes.

Plan: documentation/plans/forms/PLAN-forms-lifecycle-regression-29oct.md. Harness:
tests/_forms_chain_support.py. Contact sends go through the `respond_io` queue, so `_sends`
drains it first (the worker body runs inline and writes the real outbox row).

SLA chain: project sales (submit -> project_sales_approve / project_sales_reject), purchasing
(project_sales_approve -> purchasing_respond / purchasing_decide), `voided` closing each stage.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from tests._forms_chain_support import (
    CONV_SLA,
    ESCALATE,
    EXTEND,
    FORM_ACTIONS,
    FORM_SLA,
    SI_BASE,
    SUB,
    UNDO,
    contact,
    event_types,
    grant,
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

KIND = "stock_inquiry"
TABLE = "stock_inquiries"
STAFF_SLUGS = (
    "procurement.stock_inquiries.view",
    "procurement.stock_inquiries.project_sales_approve",
    "procurement.stock_inquiries.project_sales_reject",
    "procurement.stock_inquiries.purchasing_reject",
    "procurement.stock_inquiries.reopen",
    "procurement.stock_inquiries.void",
    UNDO,
    ESCALATE,
)
FIELDS = {
    "salesperson": "ZZT Aminah",
    "product_code": "ZZT-TILE-9",
    "item_description": "60x60 matt porcelain",
    "project_customer": "ZZT Example Builders",
    "project_name": "ZZT Example Tower",
    "quantity": "300",
}


def _setup(w, *, approve_grace=None):
    db = w.db
    w.chain = sla_chain(db, KIND, [
        dict(start_event="submit", resolve_event="project_sales_approve,project_sales_reject,voided",
             advance_on_event="project_sales_approve", grace_seconds=approve_grace),
        dict(start_event="project_sales_approve",
             resolve_event="purchasing_respond,purchasing_decide,voided"),
    ])
    w.staff = user(db, "si staff")
    grant(db, w.staff, *STAFF_SLUGS)
    for stage in w.chain.stages:
        grant(db, stage.tier1, EXTEND, *STAFF_SLUGS)
        grant(db, stage.tier2, EXTEND, *STAFF_SLUGS)
    w.contact = contact(db, name="si salesperson")
    db.commit()
    return w


def _draft(w):
    res = w.as_contact(w.contact).post(f"{SUB}/{KIND}", json={"fields": FIELDS})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "draft"
    return res.json()["id"]


def _submitted(w):
    sid = _draft(w)
    res = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{sid}/submit")
    assert res.status_code == 200, res.text
    return sid


def _sends(w, sid):
    w.drain()
    rows = outbox(w.db, TABLE, sid)
    assert all(r.status == "success" for r in rows), [(r.status, r.error_message) for r in rows]
    return rows


def _status(w, sid):
    res = w.as_user(w.staff).get(f"{SI_BASE}/{sid}")
    assert res.status_code == 200, res.text
    return res.json()["status"]


def _approve(w, sid):
    res = w.as_user(w.staff).post(f"{SI_BASE}/{sid}/project-sales-approve")
    assert res.status_code == 200, res.text
    return res


# ------------------------------------------------------------------ draft, save, submit


def test_draft_save_reopen_submit_starts_the_project_sales_stage(world):
    w = _setup(world)
    sid = _draft(w)
    c = w.as_contact(w.contact)
    saved = c.put(f"{SUB}/{KIND}/{sid}", json={"fields": {**FIELDS, "quantity": "320"}})
    assert saved.status_code == 200, saved.text
    detail = c.get(f"{SUB}/{KIND}/{sid}")
    assert detail.status_code == 200 and detail.json()["is_draft"] is True
    assert trackers(w.db, KIND, sid) == []

    sub = c.post(f"{SUB}/{KIND}/{sid}/submit")
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "pending_project_sales"
    assert sub.json()["document_number"]
    stage = open_tracker(w.db, KIND, sid)
    assert stage.assigned_to_id == w.chain.stages[0].tier1
    assert notifications(w.db, w.chain.stages[0].tier1, event_type="assigned")
    assert _sends(w, sid) == []


# ------------------------------------------------------------------ reject, resubmit, approve, respond


def test_reject_resubmit_approve_respond_full_chain_with_outbox(world):
    w = _setup(world)
    sid = _submitted(w)
    first = open_tracker(w.db, KIND, sid)
    s = w.as_user(w.staff)

    assert s.post(f"{SI_BASE}/{sid}/project-sales-reject", json={"reason": ""}).status_code == 400
    rej = s.post(f"{SI_BASE}/{sid}/project-sales-reject", json={"reason": "wrong project code"})
    assert rej.status_code == 200, rej.text
    assert rej.json()["status"] == "rejected"
    portal = w.as_contact(w.contact).get(f"{SUB}/{KIND}/{sid}").json()
    assert portal["status"] == "rejected" and portal["rejection_reason"] == "wrong project code"
    assert len(_sends(w, sid)) == 1
    assert "wrong project code" in w.sends[-1]["text"]
    assert trackers(w.db, KIND, sid, open_only=True) == []

    res = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{sid}/submit",
                                       json={"fields": {**FIELDS, "project_name": "ZZT Example Tower B"}})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "resubmitted"
    again = open_tracker(w.db, KIND, sid)
    assert again.id != first.id and again.team_set_code == w.chain.stages[0].team_set

    _approve(w, sid)
    assert _status(w, sid) == "pending_purchasing"
    purchasing = open_tracker(w.db, KIND, sid)
    assert purchasing.team_set_code == w.chain.stages[1].team_set
    assert len(_sends(w, sid)) == 2

    reply = w.as_user(w.chain.stages[1].tier1).post(
        f"{SI_BASE}/{sid}/update-and-reply", json={"purchasing_response": "300 pcs in stock, 2 weeks"})
    assert reply.status_code == 200, reply.text
    assert reply.json()["status"] == "responded"
    assert len(_sends(w, sid)) == 3
    assert "300 pcs in stock" in w.sends[-1]["text"]
    assert trackers(w.db, KIND, sid, open_only=True) == []


def test_purchasing_reject_then_reopen_restores_the_stage_status_quietly(world):
    w = _setup(world)
    sid = _submitted(w)
    _approve(w, sid)
    before = len(_sends(w, sid))

    rej = w.as_user(w.staff).post(f"{SI_BASE}/{sid}/purchasing-reject", json={"reason": "discontinued"})
    assert rej.status_code == 200, rej.text
    assert rej.json()["status"] == "rejected"
    assert len(_sends(w, sid)) == before + 1

    reopen = w.as_user(w.staff).post(f"{SI_BASE}/{sid}/reopen", json={"reason": "supplier found"})
    assert reopen.status_code == 200, reopen.text
    assert reopen.json()["status"] == "pending_purchasing"  # back to where it was rejected from
    assert len(_sends(w, sid)) == before + 1  # reopen tells nobody


# ------------------------------------------------------------------ revise


def test_revise_after_a_response_restarts_project_sales(world):
    w = _setup(world)
    revision_config(w.db, KIND, allowed_statuses=["pending_project_sales", "pending_purchasing", "responded"])
    sid = _submitted(w)
    _approve(w, sid)
    w.as_user(w.chain.stages[1].tier1).post(f"{SI_BASE}/{sid}/update-and-reply",
                                            json={"purchasing_response": "only 100 pcs"})
    assert _status(w, sid) == "responded"

    rev = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{sid}/revise", json={
        "reason": "customer cut the quantity", "expected_revision_no": 0,
        "fields": {**FIELDS, "quantity": "100"}})
    assert rev.status_code == 200, rev.text
    assert rev.json()["revision_no"] == 1
    assert rev.json()["revision"]["used"] == 1
    assert rev.json()["submission"]["status"] == "pending_project_sales"
    restarted = open_tracker(w.db, KIND, sid)
    assert restarted.team_set_code == w.chain.stages[0].team_set

    blank = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{sid}/revise", json={
        "reason": "   ", "expected_revision_no": 1, "fields": {}})
    assert blank.status_code == 422, blank.text


# ------------------------------------------------------------------ undo and revert


def test_approve_inside_grace_then_cancel_keeps_project_sales(world):
    w = _setup(world, approve_grace=30)
    sid = _submitted(w)
    stage = open_tracker(w.db, KIND, sid)
    parked = w.as_user(w.staff).post(f"{SI_BASE}/{sid}/project-sales-approve")
    assert parked.status_code == 202, parked.text
    cancel = w.as_user(w.staff).post(f"{FORM_ACTIONS}/{parked.json()['pending_action_id']}/cancel")
    assert cancel.status_code == 200, cancel.text
    assert _status(w, sid) == "pending_project_sales"
    assert open_tracker(w.db, KIND, sid).id == stage.id
    assert _sends(w, sid) == []


def test_revert_a_project_sales_approval_reopens_the_stage_and_corrects_the_contact(world):
    w = _setup(world)
    sid = _submitted(w)
    project_sales = open_tracker(w.db, KIND, sid)
    _approve(w, sid)
    before = len(_sends(w, sid))

    undo = w.as_user(w.staff).post(f"{FORM_ACTIONS}/undo", json={
        "source_entity_type": KIND, "source_entity_id": sid, "reason": "approved the wrong inquiry"})
    assert undo.status_code == 200, undo.text
    assert _status(w, sid) == "pending_project_sales"
    assert open_tracker(w.db, KIND, sid).id == project_sales.id
    assert "reopened" in event_types(w.db, project_sales.id)
    assert len(_sends(w, sid)) == before + 1
    assert "changed back" in w.sends[-1]["text"]


# ------------------------------------------------------------------ extend, escalate, handle, sweep


def test_extend_escalate_claim_and_respond_as_the_holder(world):
    w = _setup(world)
    settings_row(w.db, handling_lock_enabled_types=KIND)
    sid = _submitted(w)
    _approve(w, sid)
    stage = w.chain.stages[1]
    purchasing = open_tracker(w.db, KIND, sid)

    old_due = purchasing.due_at_resolution
    assert w.as_user(stage.tier1).post(f"{CONV_SLA}/{purchasing.id}/extend",
                                       json={"days": 3, "reason": "awaiting supplier quote"}).status_code == 200
    w.db.refresh(purchasing)
    assert purchasing.due_at_resolution > old_due

    esc = w.as_user(w.staff).post(f"{FORM_SLA}/{purchasing.id}/escalate", json={"reason": "urgent project"})
    assert esc.status_code == 200, esc.text
    assert esc.json()["current_tier"] == 2
    assert notifications(w.db, stage.tier2, event_type="escalated")

    blocked = w.as_user(stage.tier2).post(f"{SI_BASE}/{sid}/update-and-reply",
                                          json={"purchasing_response": "checking"})
    assert blocked.status_code == 403, blocked.text
    assert w.as_user(stage.tier2).post(f"{FORM_SLA}/{purchasing.id}/claim").status_code == 200
    reply = w.as_user(stage.tier2).post(f"{SI_BASE}/{sid}/update-and-reply",
                                        json={"purchasing_response": "300 pcs, 10 days"})
    assert reply.status_code == 200, reply.text
    assert reply.json()["status"] == "responded"


def test_overdue_sweep_escalates_project_sales(world, monkeypatch):
    from app.services import form_sla_service as fss

    w = _setup(world)
    sid = _submitted(w)
    stage = open_tracker(w.db, KIND, sid)
    monkeypatch.setattr(fss, "_utc_naive_now", lambda: stage.due_at_resolution + timedelta(hours=2))
    assert fss.FormSLAOrchestrator(w.db).scan_overdue_and_escalate()["escalated"] >= 1
    w.db.refresh(stage)
    assert stage.current_tier == 2 and stage.assigned_to_id == w.chain.stages[0].tier2
    assert notifications(w.db, w.chain.stages[0].tier2, event_type="escalated")


# ------------------------------------------------------------------ void


def test_void_stops_the_sla_and_tells_the_contact(world):
    w = _setup(world)
    sid = _submitted(w)
    _approve(w, sid)
    before = len(_sends(w, sid))
    void = w.as_user(w.staff).post(f"{SI_BASE}/{sid}/void", json={"void_reason": "customer cancelled"})
    assert void.status_code == 200, void.text
    assert void.json()["status"] == "voided"
    assert trackers(w.db, KIND, sid, open_only=True) == []
    assert len(_sends(w, sid)) == before + 1
    assert w.as_user(w.staff).post(f"{SI_BASE}/{sid}/void",
                                   json={"void_reason": "again please"}).status_code == 409
    reply = w.as_user(w.staff).post(f"{SI_BASE}/{sid}/update-and-reply",
                                    json={"purchasing_response": "too late"})
    assert reply.status_code == 422, reply.text  # the response gate: voided takes no response
