"""FORMS-REGRESSION: sample request lifecycle chains over the real routes.

Plan: documentation/plans/forms/PLAN-forms-lifecycle-regression-29oct.md. Harness:
tests/_forms_chain_support.py.

A sample request has no reject, revise, undo or SLA (its service emits no form event), and
nothing reaches the contact on any move, so the chains pin exactly that: draft -> save ->
submit -> processing -> customer_confirmed -> delivered, the cancel rules, and an empty outbox
throughout.
"""
from __future__ import annotations

from tests._forms_chain_support import (
    SORENTO,
    SR_BASE,
    SUB,
    contact,
    grant,
    outbox,
    trackers,
    user,
    world,  # noqa: F401  (fixture)
)
from tests._sample_request_seed import full_payload, seed_catalogue

KIND = "sample_request"
TABLE = "sample_requests"
PROCESS = ("projects.sample_requests.view", "projects.sample_requests.process")


def _setup(w):
    from app.services import project_seed_service

    db = w.db
    project_seed_service.run(db, company_id=SORENTO)  # the sample_request status graph
    w.cat = seed_catalogue(db)
    w.coord = user(db, "sample coordinator")
    grant(db, w.coord, *PROCESS)
    w.contact = contact(db, kinds=[KIND], name="sr salesperson")
    db.commit()
    return w


def _submitted(w):
    c = w.as_contact(w.contact)
    created = c.post(f"{SUB}/{KIND}", json=full_payload(product_id=w.cat.plain.id))
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "draft"
    rid = created.json()["id"]
    saved = c.put(f"{SUB}/{KIND}/{rid}", json=full_payload(product_id=w.cat.plain.id,
                                                           ship_to_name="ZZT site gate 2"))
    assert saved.status_code == 200, saved.text
    assert c.get(f"{SUB}/{KIND}/{rid}").json()["ship_to_name"] == "ZZT site gate 2"
    sub = c.post(f"{SUB}/{KIND}/{rid}/submit")
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "submitted" and sub.json()["submitted_at"]
    return rid


def _move(w, rid, to, **extra):
    return w.as_user(w.coord).post(f"{SR_BASE}/{rid}/move", json={"to": to, **extra})


def test_draft_save_submit_process_confirm_deliver_tells_nobody(world):
    w = _setup(world)
    rid = _submitted(w)
    c = w.as_contact(w.contact)
    assert c.put(f"{SUB}/{KIND}/{rid}", json={"ship_to_name": "late"}).status_code == 409

    assert _move(w, rid, "processing").status_code == 200
    no_date = _move(w, rid, "customer_confirmed")
    assert no_date.status_code == 422, no_date.text
    assert no_date.json()["code"] == "SAMPLE_REQUEST_DATE_REQUIRED"
    assert _move(w, rid, "customer_confirmed", date="2026-11-20").status_code == 200
    done = _move(w, rid, "delivered", date="2026-11-25")
    assert done.status_code == 200, done.text
    assert c.get(f"{SUB}/{KIND}/{rid}").json()["status"] == "delivered"

    assert trackers(w.db, KIND, rid) == []
    assert outbox(w.db, TABLE, rid) == []
    assert w.sends == []


def test_the_owner_cancels_a_submitted_request_but_not_a_processing_one(world):
    w = _setup(world)
    rid = _submitted(w)
    cancel = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{rid}/cancel")
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelled"

    rid2 = _submitted(w)
    assert _move(w, rid2, "processing").status_code == 200
    late = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{rid2}/cancel")
    assert late.status_code == 409, late.text
    # the office can, with a reason
    no_reason = _move(w, rid2, "cancelled")
    assert no_reason.status_code == 422 and no_reason.json()["code"] == "SAMPLE_REQUEST_REASON_REQUIRED"
    assert _move(w, rid2, "cancelled", reason="customer no longer needs it").status_code == 200
    assert outbox(w.db, TABLE, rid2) == [] and w.sends == []
