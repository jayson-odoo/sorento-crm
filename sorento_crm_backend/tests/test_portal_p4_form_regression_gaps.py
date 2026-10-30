"""PORTAL-P4-REQUESTS: API-level regression coverage for the empty / partial cells of the form matrix.

Every salesperson call goes through /api/v1/my-requests as the linked salesperson; the staff side
uses the real staff routes. Regression tests of existing behaviour: a red here is a possible bug,
not a spec to weaken.

  B  sales opportunity: foreign / agentless customer, lost without a reason
  E  sample request, new product application, price tag request, sales opportunity: staff moves
     are visible to the salesperson through my-requests
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.order import Customer
from app.models.sales import SalesOpportunity
from app.models.status import Status
from tests import _portal_p4_npa_support as npa
from tests import _portal_p4_pt_support as pt
from tests import _portal_p4_sr_so_support as srso
from tests import _portal_p4_support as s
from tests._portal_p4_npa_support import world as npa_world  # noqa: F401
from tests._portal_p4_pt_support import world as pt_world  # noqa: F401
from tests._portal_p4_sr_so_support import world  # noqa: F401
from tests._portal_p4_support import scene  # noqa: F401

# --------------------------------------------------------------------------- #
# 2. B: sales opportunity                                                     #
# --------------------------------------------------------------------------- #


def _so_count(w) -> int:
    w.sc.db.expire_all()
    return w.sc.db.query(SalesOpportunity).count()


def _stage(w, key) -> str:
    return w.sc.db.query(Status).filter(Status.entity_type == "sales_opportunity", Status.key == key).one().id


@pytest.mark.parametrize("which", ["other_agents_customer", "customer_without_agent"])
def test_gap_so_create_with_a_customer_that_is_not_theirs_is_422_and_adds_no_row(world, which):
    w = world
    if which == "other_agents_customer":
        customer_id = w.other.mine.id
    else:
        loose = Customer(id=s.uid(), company_id=w.company_id, customer_code=f"ZZT-{s.uid()[:6]}", customer_name="ZZT loose")
        w.sc.db.add(loose)
        w.sc.db.commit()
        customer_id = loose.id
    before = _so_count(w)
    resp = w.rep.me.call("POST", srso.SO_PORTAL, json=w.so_body(prospect_name=None, customer_id=customer_id))
    s.not_a_missing_route(resp)
    assert resp.status_code == 422, resp.text
    assert _so_count(w) == before


def test_gap_so_lost_stage_without_a_reason_is_422_and_the_row_is_not_lost(world):
    w = world
    oid = s.ok(w.rep.me.call("POST", srso.SO_PORTAL, json=w.so_body()), 201).json()["id"]
    resp = w.rep.me.call("PATCH", f"{srso.SO_PORTAL}/{oid}", json={"status_id": _stage(w, "lost")})
    s.not_a_missing_route(resp)
    assert resp.status_code == 422, resp.text
    row = srso.so_row(w, oid)
    assert row.outcome != "lost"
    assert s.ok(w.rep.me.call("GET", f"{srso.SO_PORTAL}/{oid}")).json()["stage_key"] == "new"


# --------------------------------------------------------------------------- #
# 3. E: sample request, processing -> customer_confirmed -> delivered         #
# --------------------------------------------------------------------------- #


def test_gap_sample_request_staff_moves_to_delivered_show_in_my_requests(world):
    w = world
    coord = s.make_user(w.sc.db, perms=[srso.SR_VIEW, srso.SR_PROCESS], name="ZZT Coordinator")
    w.sc.db.commit()
    sid = s.ok(w.rep.me.call("POST", srso.SR_PORTAL, json=w.sr_body()), 201).json()["id"]
    s.ok(w.rep.me.call("POST", f"{srso.SR_PORTAL}/{sid}/submit"))
    path = f"{srso.SR}/{sid}/move"

    s.ok(w.staff(coord, "POST", path, json={"to": "processing"}))
    no_date = w.staff(coord, "POST", path, json={"to": "customer_confirmed"})
    assert no_date.status_code == 422, no_date.text
    assert no_date.json()["code"] == "SAMPLE_REQUEST_DATE_REQUIRED"
    s.ok(w.staff(coord, "POST", path, json={"to": "customer_confirmed", "date": (date.today() + timedelta(days=5)).isoformat()}))
    assert w.rep.me.call("GET", f"{srso.SR_PORTAL}/{sid}").json()["status"] == "customer_confirmed"
    s.ok(w.staff(coord, "POST", path, json={"to": "delivered", "date": (date.today() + timedelta(days=9)).isoformat()}))

    got = s.ok(w.rep.me.call("GET", f"{srso.SR_PORTAL}/{sid}")).json()
    assert got["status"] == "delivered"
    listed = s.ok(w.rep.me.call("GET", srso.SR_PORTAL)).json()["data"]
    assert [r["status"] for r in listed if r["id"] == sid] == ["delivered"]


# --------------------------------------------------------------------------- #
# 4. E: new product application, approve + feedback                           #
# --------------------------------------------------------------------------- #


def test_gap_npa_staff_approve_and_feedback_show_in_my_requests(npa_world):
    w = npa_world
    aid = npa.create(w.rep.me, w)["id"]
    s.ok(w.rep.me.call("POST", f"{npa.SUB}/{aid}/submit"))
    assert s.ok(w.rep.me.call("GET", f"{npa.SUB}/{aid}")).json()["status"] == "submitted"
    approver = s.make_user(w.sc.db, perms=[npa.NPA_VIEW, npa.NPA_APPROVE, npa.NPA_OPEN], name="ZZT Approver")
    w.sc.db.commit()

    assert w.staff(approver, "POST", f"{npa.NPA}/{aid}/approve").json()["status"] == "approved"
    fb = w.staff(approver, "PUT", f"{npa.NPA}/{aid}/feedback", json={"lead_time": "ZZT 3 weeks"})
    assert fb.status_code == 200, fb.text

    got = s.ok(w.rep.me.call("GET", f"{npa.SUB}/{aid}")).json()
    assert got["status"] == "approved"
    assert got.get("lead_time") == "ZZT 3 weeks", {k: v for k, v in got.items() if k != "lines"}


# --------------------------------------------------------------------------- #
# 5. E: price tag request, staff reject / customer requests changes           #
# --------------------------------------------------------------------------- #


def test_gap_price_tag_staff_reject_with_a_reason_shows_in_my_requests_and_notifies(pt_world):
    w = pt_world
    rid = pt.submitted(w.rep.me, w)
    pt.to_proof(w, rid)
    sent_before = len(pt.integration_logs(w, rid))
    reason = "ZZT product discontinued"

    s.ok(w.sc.staff_call("POST", f"{pt.STAFF}/{rid}/transition", json={"status": "rejected", "note": reason}))

    got = s.ok(w.rep.me.call("GET", f"{pt.SUB}/{rid}")).json()
    assert got["status"] == "rejected"
    comments = s.ok(w.rep.me.call("GET", f"{pt.SUB}/{rid}/review-comments")).json()
    assert any(reason in (c.get("body") or "") for c in comments), comments
    logs = pt.integration_logs(w, rid)
    assert len(logs) > sent_before, "the contact got no message on reject"
    assert any(reason in str(getattr(l, "payload", "") or getattr(l, "request_payload", "") or l.__dict__) for l in logs)


def test_gap_price_tag_changes_requested_reason_shows_in_my_requests(pt_world):
    w = pt_world
    rid = pt.submitted(w.rep.me, w)
    pt.to_proof(w, rid)
    reason = "ZZT make the price bigger"
    s.ok(w.rep.me.call("POST", f"{pt.SUB}/{rid}/request-changes", json={"note": reason}))
    got = s.ok(w.rep.me.call("GET", f"{pt.SUB}/{rid}")).json()
    assert got["status"] == "changes_requested"
    comments = s.ok(w.rep.me.call("GET", f"{pt.SUB}/{rid}/review-comments")).json()
    assert any(reason in (c.get("body") or "") for c in comments), comments


# --------------------------------------------------------------------------- #
# 6. E: sales opportunity, staff edit visible to the salesperson              #
# --------------------------------------------------------------------------- #


def test_gap_so_staff_edit_shows_in_my_requests_and_a_foreign_agent_gets_404(world):
    w = world
    oid = s.ok(w.rep.me.call("POST", srso.SO_PORTAL, json=w.so_body()), 201).json()["id"]
    staff = s.make_user(w.sc.db, perms=[srso.SO_VIEW, srso.SO_EDIT], name="ZZT SO Staff")
    w.sc.db.commit()
    qualified = _stage(w, "qualified")

    r = w.staff(staff, "PATCH", f"{srso.SO_STAFF}/{oid}", json={"status_id": qualified, "title": "ZZT staff renamed"})
    assert r.status_code == 200, r.text

    got = s.ok(w.rep.me.call("GET", f"{srso.SO_PORTAL}/{oid}")).json()
    assert (got["stage_key"], got["title"]) == ("qualified", "ZZT staff renamed")

    # a salesperson scoped to a different agent (view_own) cannot see or edit it
    for method, kw in (("GET", {}), ("PATCH", {"json": {"title": "ZZT hijack"}})):
        r = w.staff(w.other.actor, method, f"{srso.SO_STAFF}/{oid}", **kw)
        assert r.status_code == 404, (method, r.status_code, r.text)
    assert srso.so_row(w, oid).title == "ZZT staff renamed"
