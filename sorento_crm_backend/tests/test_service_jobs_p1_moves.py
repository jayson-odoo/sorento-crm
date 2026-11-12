"""AFTER-SALES-P1 red tests: confirm, assign, transitions, audit (UAC C1-C6)."""
from __future__ import annotations

import itertools
import uuid
from datetime import datetime

import pytest

from ._service_jobs_p1_support import (
    DISPATCH,
    JOBS,
    VIEW,
    api,
    audit_rows,
    env,  # noqa: F401
    make_complaint,
    make_job,
    make_tech,
    reload_job,
    status_id,
)

STATUSES = ["proposed", "confirmed", "on_the_way", "arrived", "completed", "verified", "cancelled"]
ALLOWED = {
    ("confirmed", "on_the_way"),
    ("on_the_way", "arrived"),
    ("confirmed", "arrived"),
    ("arrived", "completed"),
    ("completed", "verified"),
    ("confirmed", "proposed"),
    ("on_the_way", "proposed"),
    ("arrived", "proposed"),
    ("proposed", "cancelled"),
    ("confirmed", "cancelled"),
    ("completed", "arrived"),
}
NEEDS_REASON = {"proposed", "cancelled"}
FROM = "2026-11-20T10:00:00+08:00"
TO = "2026-11-20T12:00:00+08:00"


def _key(env, job):
    from app.models.status import Status

    return env.db.query(Status.key).filter(Status.id == reload_job(env, job.id).status_id).scalar()


def _confirmed(env, tech=None):
    c = make_complaint(env, "mv")
    return make_job(
        env, c, "confirmed", technician=tech,
        scheduled_from=datetime(2026, 11, 20, 2, 0), agreed_by="Ms Lim",
    )


# ------------------------------------------------------------------ C1

def test_c1_confirm_moves_proposed_to_confirmed(env):
    job = make_job(env, make_complaint(env, "c1"), "proposed")
    with api(env) as client:
        r = client.post(
            f"{JOBS}/{job.id}/confirm",
            json={"scheduled_from": FROM, "scheduled_to": TO, "customer_agreed_by": "Ms Lim"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "confirmed"
    assert body["customer_agreed_by"] == "Ms Lim"
    assert _key(env, job) == "confirmed"


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"customer_agreed_by": "Ms Lim"}, "scheduled_from"),
        ({"scheduled_from": FROM}, "customer_agreed_by"),
        ({"scheduled_from": FROM, "customer_agreed_by": "   "}, "customer_agreed_by"),
        ({"scheduled_from": FROM, "customer_agreed_by": ""}, "customer_agreed_by"),
    ],
)
def test_c1_confirm_refuses_missing_date_or_agreed_by_naming_the_field(env, payload, field):
    job = make_job(env, make_complaint(env, "c1b"), "proposed")
    with api(env) as client:
        r = client.post(f"{JOBS}/{job.id}/confirm", json=payload)
    assert r.status_code == 422, r.text
    assert field in r.text
    assert _key(env, job) == "proposed"


def test_c1_scheduled_to_before_from_is_refused(env):
    job = make_job(env, make_complaint(env, "c1c"), "proposed")
    with api(env) as client:
        r = client.post(
            f"{JOBS}/{job.id}/confirm",
            json={"scheduled_from": TO, "scheduled_to": FROM, "customer_agreed_by": "Ms Lim"},
        )
    assert r.status_code == 422, r.text
    assert _key(env, job) == "proposed"


def test_c1_confirm_only_from_proposed(env):
    job = _confirmed(env)
    with api(env) as client:
        r = client.post(f"{JOBS}/{job.id}/confirm", json={"scheduled_from": FROM, "customer_agreed_by": "X"})
    assert r.status_code == 409, r.text


# ------------------------------------------------------------------ C2

@pytest.mark.parametrize("key", ["proposed", "confirmed"])
def test_c2_assign_sets_the_technician(env, key):
    tech = make_tech(env)
    job = make_job(env, make_complaint(env, "c2"), key)
    with api(env) as client:
        r = client.post(f"{JOBS}/{job.id}/assign", json={"technician_id": tech.id})
    assert r.status_code == 200, r.text
    assert r.json()["technician_id"] == tech.id
    assert r.json()["technician_name"] == tech.name
    assert reload_job(env, job.id).technician_id == tech.id


def test_c2_inactive_technician_is_refused_with_422(env):
    tech = make_tech(env, active=False)
    job = make_job(env, make_complaint(env, "c2b"), "confirmed")
    with api(env) as client:
        r = client.post(f"{JOBS}/{job.id}/assign", json={"technician_id": tech.id})
    assert r.status_code == 422, r.text
    assert reload_job(env, job.id).technician_id is None


def test_c2_reassign_replaces_and_history_shows_old_to_new(env):
    t1, t2 = make_tech(env), make_tech(env)
    job = make_job(env, make_complaint(env, "c2c"), "confirmed", technician=t1)
    with api(env) as client:
        r = client.post(f"{JOBS}/{job.id}/assign", json={"technician_id": t2.id})
    assert r.status_code == 200, r.text
    rows = audit_rows(env, job.id)
    changes = [x for x in rows if (x.old_values or {}).get("technician_id") == t1.id
               and (x.new_values or {}).get("technician_id") == t2.id]
    assert changes, [(x.action, x.old_values, x.new_values) for x in rows]


@pytest.mark.parametrize("key", ["on_the_way", "arrived", "completed", "verified", "cancelled"])
def test_c2_assign_outside_proposed_or_confirmed_is_refused(env, key):
    tech = make_tech(env)
    job = make_job(env, make_complaint(env, "c2d"), key)
    with api(env) as client:
        r = client.post(f"{JOBS}/{job.id}/assign", json={"technician_id": tech.id})
    assert r.status_code in (409, 422), r.text
    assert reload_job(env, job.id).technician_id is None


# ------------------------------------------------------------------ C3

@pytest.mark.parametrize("frm,to", list(itertools.product(STATUSES, STATUSES)))
def test_c3_only_the_graphs_moves_are_allowed(env, frm, to):
    if to == "confirmed":
        pytest.skip("confirm has its own route (C1); see the next test")
    job = make_job(
        env, make_complaint(env, "c3"), frm,
        scheduled_from=datetime(2026, 11, 20, 2, 0), agreed_by="Ms Lim",
    )
    body = {"to": to}
    if to in NEEDS_REASON:
        body["reason"] = "Customer rejected the visit"
    with api(env) as client:
        r = client.post(f"{JOBS}/{job.id}/transition", json=body)
    if (frm, to) in ALLOWED:
        assert r.status_code == 200, r.text
        assert _key(env, job) == to
    else:
        assert r.status_code == 409, f"{frm}->{to}: {r.status_code} {r.text}"
        assert _key(env, job) == frm


@pytest.mark.parametrize("frm", STATUSES)
def test_c3_transition_route_never_confirms(env, frm):
    job = make_job(env, make_complaint(env, "c3c"), frm)
    with api(env) as client:
        r = client.post(f"{JOBS}/{job.id}/transition", json={"to": "confirmed"})
    assert r.status_code in (409, 422), r.text
    assert _key(env, job) == frm


def test_c3_unknown_target_is_422(env):
    job = _confirmed(env)
    with api(env) as client:
        assert client.post(f"{JOBS}/{job.id}/transition", json={"to": "teleported"}).status_code == 422


# ------------------------------------------------------------------ C4

@pytest.mark.parametrize(
    "frm,to,column",
    [("confirmed", "arrived", "arrived_at"), ("arrived", "completed", "completed_at"), ("completed", "verified", "verified_at")],
)
def test_c4_stamps(env, frm, to, column):
    job = make_job(env, make_complaint(env, "c4"), frm, scheduled_from=datetime(2026, 11, 20, 2, 0), agreed_by="Ms Lim")
    assert getattr(job, column) is None
    with api(env) as client:
        assert client.post(f"{JOBS}/{job.id}/transition", json={"to": to}).status_code == 200
    assert getattr(reload_job(env, job.id), column) is not None


def test_c4_back_to_proposed_clears_schedule_and_agreed_by_but_keeps_technician(env):
    tech = make_tech(env)
    job = _confirmed(env, tech)
    with api(env) as client:
        r = client.post(f"{JOBS}/{job.id}/transition", json={"to": "proposed", "reason": "Customer rejected the visit"})
    assert r.status_code == 200, r.text
    row = reload_job(env, job.id)
    assert row.scheduled_from is None and row.scheduled_to is None
    assert row.customer_agreed_by is None
    assert row.technician_id == tech.id


@pytest.mark.parametrize("frm,to", [("confirmed", "proposed"), ("on_the_way", "proposed"), ("arrived", "proposed"), ("proposed", "cancelled"), ("confirmed", "cancelled")])
@pytest.mark.parametrize("reason", [None, "", "   "])
def test_c4_reason_required_for_proposed_and_cancel(env, frm, to, reason):
    job = make_job(env, make_complaint(env, "c4r"), frm, scheduled_from=datetime(2026, 11, 20, 2, 0), agreed_by="Ms Lim")
    body = {"to": to}
    if reason is not None:
        body["reason"] = reason
    with api(env) as client:
        r = client.post(f"{JOBS}/{job.id}/transition", json=body)
    assert r.status_code == 422, r.text
    assert "reason" in r.text
    assert _key(env, job) == frm


def test_c4_cancel_stores_the_reason(env):
    job = make_job(env, make_complaint(env, "c4s"), "proposed")
    with api(env) as client:
        assert client.post(f"{JOBS}/{job.id}/transition", json={"to": "cancelled", "reason": "Duplicate"}).status_code == 200
    assert reload_job(env, job.id).cancel_reason == "Duplicate"


# ------------------------------------------------------------------ C5

@pytest.mark.parametrize("perms", [{VIEW}, set()])
def test_c5_every_move_needs_dispatch(env, perms):
    tech = make_tech(env)
    job = _confirmed(env)
    with api(env, perms) as client:
        assert client.post(f"{JOBS}/{job.id}/confirm", json={"scheduled_from": FROM, "customer_agreed_by": "X"}).status_code == 403
        assert client.post(f"{JOBS}/{job.id}/assign", json={"technician_id": tech.id}).status_code == 403
        assert client.post(f"{JOBS}/{job.id}/transition", json={"to": "arrived"}).status_code == 403
    assert _key(env, job) == "confirmed"


def test_c5_dispatch_alone_without_view_still_moves(env):
    job = _confirmed(env)
    with api(env, {DISPATCH}) as client:
        assert client.post(f"{JOBS}/{job.id}/transition", json={"to": "arrived"}).status_code == 200


# ------------------------------------------------------------------ C6

def test_c6_create_confirm_assign_and_move_each_write_an_audit_row_on_the_job(env):
    c = make_complaint(env, "c6")
    tech = make_tech(env)
    with api(env) as client:
        job_id = client.post(f"/api/v1/complaints-management/complaints/{c.id}/service-jobs").json()["id"]
        n_created = len(audit_rows(env, job_id))
        assert n_created >= 1
        assert audit_rows(env, job_id)[0].action == "CREATE"

        client.post(f"{JOBS}/{job_id}/confirm", json={"scheduled_from": FROM, "customer_agreed_by": "Ms Lim"})
        n_confirm = len(audit_rows(env, job_id))
        assert n_confirm > n_created
        assert any((x.new_values or {}).get("customer_agreed_by") == "Ms Lim" for x in audit_rows(env, job_id))

        client.post(f"{JOBS}/{job_id}/assign", json={"technician_id": tech.id})
        n_assign = len(audit_rows(env, job_id))
        assert n_assign > n_confirm

        client.post(f"{JOBS}/{job_id}/transition", json={"to": "arrived"})
        rows = audit_rows(env, job_id)
        assert len(rows) > n_assign
        moved = [x for x in rows if (x.new_values or {}).get("status_id") == status_id(env, "arrived")]
        assert moved and moved[-1].old_values.get("status_id") == status_id(env, "confirmed")
        assert all(x.user_id == env.actor_id for x in rows)
