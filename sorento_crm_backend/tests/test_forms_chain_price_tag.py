"""FORMS-REGRESSION: price tag request lifecycle chains over the real routes.

Plan: documentation/plans/forms/PLAN-forms-lifecycle-regression-29oct.md. Harness:
tests/_forms_chain_support.py. Price tag sends go out inside the request
(`price_tag_notify`), so every transition's outbox row lands without a drain.

A price tag request has no form-action undo (no dispatcher key) and only `submit` feeds its
SLA. PRICETAG-SELF-APPROVAL: a portal submit lands at `proof_ready` for the salesperson with no
tracker; only Escalate emits `submit`, and with an active stage it auto-assigns the request to the
stage's assignee and moves it straight to `designing` (D8), so there is no Claim step here. The
chains: draft -> submit -> escalate -> proof -> changes -> proof -> approve -> collection ->
collected; reject (terminal); the salesperson's own revise; void; and the SLA stage's extend,
escalation and overdue sweep.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from tests._forms_chain_support import (
    CONV_SLA,
    ESCALATE,
    EXTEND,
    FORM_SLA,
    PT_BASE,
    SUB,
    contact,
    grant,
    notifications,
    open_tracker,
    outbox,
    sla_chain,
    trackers,
    user,
    world,  # noqa: F401  (fixture)
)

KIND = "price_tag_request"
TABLE = "price_tag_requests"
PROCESS = "dealer_kit.price_tag_requests.process"
VIEW = "dealer_kit.price_tag_requests.view"


def _product(db) -> str:
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    from tests._pg_fixture import unique_code

    category = ProductCategory(id=_uid(), category_code=unique_code("cat"),
                               category_name=unique_code("Category"), class_label="Kitchen Sink")
    brand = Brand(id=_uid(), brand_code=unique_code("br"), brand_name=unique_code("Brand"))
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("uom"), uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(id=_uid(), product_code=unique_code("prod"), product_name=unique_code("Sink"),
                      category_id=category.id, brand_id=brand.id, base_uom_id=uom.id, list_price=899.0)
    db.add(product)
    db.flush()
    return product.id


def _uid():
    import uuid

    return str(uuid.uuid4())


def _setup(w):
    db = w.db
    w.chain = sla_chain(db, KIND, [dict(start_event="submit", resolve_event="voided")])
    w.marketer = user(db, "marketer")
    grant(db, w.marketer, PROCESS, VIEW, ESCALATE)
    for tier in (w.chain.stages[0].tier1, w.chain.stages[0].tier2):
        grant(db, tier, PROCESS, VIEW, EXTEND, ESCALATE)
    w.contact = contact(db, kinds=[KIND], name="pt salesperson")
    w.product = _product(db)
    db.commit()
    return w


def _draft(w):
    res = w.as_contact(w.contact).post(f"{SUB}/{KIND}", json={
        "debtor_name": "ZZT Example Dealer",
        "print_by": "office",
        "needed_by_date": str(date.today() + timedelta(days=7)),
        "lines": [{"line_type": "product", "product_id": w.product}],
    })
    assert res.status_code == 201, res.text
    assert res.json()["portal_draft_at"] is not None
    return res.json()["id"]


def _submitted_self(w):
    """Submitted and waiting for the salesperson himself (proof_ready, nobody assigned)."""
    rid = _draft(w)
    res = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{rid}/submit")
    assert res.status_code == 200, res.text
    return rid


def _submitted(w):
    """Submitted, then escalated: the request is with marketing and the stage is open."""
    rid = _submitted_self(w)
    res = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{rid}/escalate", json={"note": "please redraw"})
    assert res.status_code == 200, res.text
    return rid


def _sends(w, rid):
    rows = outbox(w.db, TABLE, rid)
    assert all(r.status == "success" for r in rows), [(r.status, r.error_message) for r in rows]
    return rows


def _move(w, rid, status, note=None, actor=None):
    body = {"status": status}
    if note is not None:
        body["note"] = note
    return w.as_user(actor or w.marketer).post(f"{PT_BASE}/{rid}/transition", json=body)


def _status(w, rid):
    res = w.as_contact(w.contact).get(f"{SUB}/{KIND}/{rid}")
    assert res.status_code == 200, res.text
    return res.json()["status"]


# ------------------------------------------------------------------ draft, save, submit


def test_draft_save_submit_once_confirms_and_escalate_starts_the_stage(world):
    w = _setup(world)
    rid = _draft(w)
    c = w.as_contact(w.contact)
    saved = c.put(f"{SUB}/{KIND}/{rid}", json={"debtor_name": "ZZT Renamed Dealer"})
    assert saved.status_code == 200, saved.text
    assert c.get(f"{SUB}/{KIND}/{rid}").json()["debtor_name"] == "ZZT Renamed Dealer"
    assert trackers(w.db, KIND, rid) == []
    assert _sends(w, rid) == []

    sub = c.post(f"{SUB}/{KIND}/{rid}/submit")
    assert sub.status_code == 200, sub.text
    assert sub.json()["portal_draft_at"] is None
    # PRICETAG-SELF-APPROVAL: waits for the salesperson, no stage, nobody assigned
    assert sub.json()["status"] == "proof_ready"
    assert sub.json()["assigned_to_id"] is None
    assert trackers(w.db, KIND, rid) == []
    assert len(_sends(w, rid)) == 1  # "we received it"

    again = c.post(f"{SUB}/{KIND}/{rid}/submit")
    assert again.status_code == 409, again.text

    esc = c.post(f"{SUB}/{KIND}/{rid}/escalate", json={"note": "please redraw"})
    assert esc.status_code == 200, esc.text
    tier1 = w.chain.stages[0].tier1
    assert open_tracker(w.db, KIND, rid).assigned_to_id == tier1
    # D8 auto-assign on escalate: straight to designing, owned by the stage's assignee
    assert esc.json()["status"] == "designing"
    assert esc.json()["assigned_to_id"] == tier1
    assert len(trackers(w.db, KIND, rid)) == 1
    assert c.put(f"{SUB}/{KIND}/{rid}", json={"debtor_name": "late edit"}).status_code == 409


# ------------------------------------------------------------------ proof round trip to collection


def test_claim_proof_changes_proof_approve_collect_with_a_send_per_step(world):
    w = _setup(world)
    rid = _submitted(w)
    sends = len(_sends(w, rid))

    assert _status(w, rid) == "designing"
    # already owned by the auto-assign: a claim is refused
    assert w.as_user(w.marketer).post(f"{PT_BASE}/{rid}/claim").status_code == 409

    assert _move(w, rid, "proof_ready").status_code == 200
    assert _status(w, rid) == "proof_ready"
    assert len(_sends(w, rid)) == sends + 1
    sends = len(_sends(w, rid))

    changes = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{rid}/request-changes",
                                           json={"note": "price font too small"})
    assert changes.status_code == 200, changes.text
    assert _status(w, rid) == "changes_requested"

    assert _move(w, rid, "proof_ready").status_code == 200  # straight back, no detour (r9)
    approve = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{rid}/approve")
    assert approve.status_code == 200, approve.text
    assert _status(w, rid) == "approved"

    sends = len(_sends(w, rid))
    assert _move(w, rid, "ready_for_collection").status_code == 200
    assert len(_sends(w, rid)) == sends + 1
    collect = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{rid}/collect")
    assert collect.status_code == 200, collect.text
    assert _status(w, rid) == "collected"

    # terminal: no further move
    assert _move(w, rid, "designing").status_code == 409


# ------------------------------------------------------------------ reject, revise, void


def test_reject_with_a_reason_is_terminal_and_tells_the_contact(world):
    w = _setup(world)
    rid = _submitted(w)
    sends = len(_sends(w, rid))

    rej = _move(w, rid, "rejected", note="product discontinued")
    assert rej.status_code == 200, rej.text
    assert _status(w, rid) == "rejected"
    assert len(_sends(w, rid)) == sends + 1
    assert "product discontinued" in w.sends[-1]["text"]

    assert _move(w, rid, "designing").status_code == 409
    revise = w.as_contact(w.contact).post(f"{SUB}/{KIND}/{rid}/revise", json={
        "reason": "try again", "expected_revision_no": 0, "fields": {},
        "products": [{"product_id": w.product, "quantity": 2}]})
    assert revise.status_code == 422, revise.text


def test_revise_is_the_salesperson_own_and_never_restarts_the_stage(world):
    """PRICETAG-SELF-APPROVAL R4: revise is allowed on his own proof, refused while marketing
    holds the request, counts the revision and opens no stage."""
    w = _setup(world)
    c = w.as_contact(w.contact)
    body = {"reason": "dealer wants five tags", "expected_revision_no": 0,
            "fields": {"debtor_name": "ZZT Example Dealer"},
            "products": [{"product_id": w.product, "quantity": 5}]}

    rid = _submitted(w)  # escalated: with marketing
    early = c.post(f"{SUB}/{KIND}/{rid}/revise", json=body)
    assert early.status_code == 422, early.text
    assert _move(w, rid, "proof_ready").status_code == 200
    assert c.post(f"{SUB}/{KIND}/{rid}/request-changes", json={"note": "wrong dealer"}).status_code == 200
    assert c.post(f"{SUB}/{KIND}/{rid}/revise", json=body).status_code == 422

    own = _submitted_self(w)
    rev = c.post(f"{SUB}/{KIND}/{own}/revise", json=body)
    assert rev.status_code == 200, rev.text
    assert rev.json()["revision_no"] == 1
    assert rev.json()["submission"]["status"] == "proof_ready"
    assert rev.json()["submission"]["assigned_to_id"] is None
    assert trackers(w.db, KIND, own) == []


def test_void_is_terminal(world):
    w = _setup(world)
    rid = _submitted(w)
    res = _move(w, rid, "void")
    assert res.status_code == 200, res.text
    assert _status(w, rid) == "void"
    assert _move(w, rid, "designing").status_code == 409


@pytest.mark.xfail(
    strict=True,
    reason="BUG PT-SLA-CLOSE: a price tag request emits only 'submit' to the form SLA "
    "(portal_price_tag.py submit), so no later move (void, rejected, collected) ever closes "
    "its stage, and the overdue sweep escalates a finished request. The fix lane removes this.",
)
@pytest.mark.parametrize("end", ["void", "rejected"])
def test_a_finished_request_closes_its_sla_stage(world, end):
    w = _setup(world)
    rid = _submitted(w)
    assert _move(w, rid, end, note="closing it").status_code == 200
    assert trackers(w.db, KIND, rid, open_only=True) == []


# ------------------------------------------------------------------ SLA: extend, escalate, sweep


def test_extend_escalate_and_the_overdue_sweep_on_the_price_tag_stage(world, monkeypatch):
    from app.services import form_sla_service as fss

    w = _setup(world)
    rid = _submitted(w)
    stage = open_tracker(w.db, KIND, rid)
    tiers = w.chain.stages[0]

    old_due = stage.due_at_resolution
    ext = w.as_user(tiers.tier1).post(f"{CONV_SLA}/{stage.id}/extend",
                                      json={"days": 1, "reason": "printer down"})
    assert ext.status_code == 200, ext.text
    w.db.refresh(stage)
    assert stage.due_at_resolution > old_due

    monkeypatch.setattr(fss, "_utc_naive_now", lambda: stage.due_at_resolution + timedelta(hours=1))
    assert fss.FormSLAOrchestrator(w.db).scan_overdue_and_escalate()["escalated"] >= 1
    w.db.refresh(stage)
    assert stage.current_tier == 2 and stage.assigned_to_id == tiers.tier2
    assert notifications(w.db, tiers.tier2, event_type="escalated")

    # tier 2 is the top team tier for this agent: a manual escalate is refused
    top = w.as_user(w.marketer).post(f"{FORM_SLA}/{stage.id}/escalate", json={"reason": "more"})
    assert top.status_code == 422, top.text
