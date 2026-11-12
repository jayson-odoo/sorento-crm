"""AFTER-SALES-P1 fix round 1 (reviewer + security-reviewer findings), red first.

B-1 History for non-admins, B-2 raise only on a CHANGED flagged resolution, S-1 waiting board,
S-2 scope fails closed, S-3 assistant scope, S-4 brand scope, S-5 cross-company live job and
assign, S-6 numbering self-seeds, S-7 History shows technician names, S-9 technician guard,
S-12 clearing a Site field, nit: resolutions sort by the flag.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.company import Company
from ._pg_fixture import unique_code
from ._service_jobs_p1_support import (
    ALL_PERMS,
    COMPLAINTS,
    DISPATCH,
    JOBS,
    RESOLUTIONS,
    VIEW,
    api,
    audit_rows,
    env,  # noqa: F401
    live_jobs,
    make_complaint,
    make_job,
    make_tech,
    status_id,
)

AUDIT = "/api/v1/audit/logs/"
CVIEW = "complaint_management.complaints.view"
COWN = "complaint_management.complaints.view_own"


def raise_url(cid):
    return f"{COMPLAINTS}/{cid}/service-jobs"


def _resolution(client, flag=True):
    r = client.post(f"{RESOLUTIONS}/", json={"name": f"ZZT fx {uuid.uuid4().hex[:8]}", "requires_service_job": flag})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ------------------------------------------------------------------ B-1

def test_b1_history_of_a_job_is_readable_with_service_jobs_view(env):
    job = make_job(env, make_complaint(env, "b1"), "proposed")
    audit_rows(env, job.id)
    with api(env, {VIEW, CVIEW}) as client:
        r = client.get(AUDIT, params={"entity_type": "service_jobs", "entity_id": job.id})
    assert r.status_code == 200, r.text


def test_b1_history_of_a_job_is_refused_without_the_permission(env):
    job = make_job(env, make_complaint(env, "b1x"), "proposed")
    with api(env, {CVIEW}) as client:
        r = client.get(AUDIT, params={"entity_type": "service_jobs", "entity_id": job.id})
    assert r.status_code in (403, 404), r.text


# ------------------------------------------------------------------ B-2

def test_b2_resaving_a_complaint_does_not_re_raise_a_cancelled_job(env):
    c = make_complaint(env, "b2")
    with api(env) as client:
        res = _resolution(client)
        assert client.put(f"{COMPLAINTS}/{c.id}", json={"resolution_id": res}).status_code == 200
        (job,) = live_jobs(env, c.id)
        assert client.post(f"{JOBS}/{job.id}/transition", json={"to": "cancelled", "reason": "x"}).status_code == 200
        again = client.put(f"{COMPLAINTS}/{c.id}", json={"resolution_id": res, "site_city": "Ipoh"})
        assert again.status_code == 200, again.text
        assert live_jobs(env, c.id) == []
        other = _resolution(client)
        assert client.put(f"{COMPLAINTS}/{c.id}", json={"resolution_id": other}).status_code == 200
        assert len(live_jobs(env, c.id)) == 1


# ------------------------------------------------------------------ S-1

def test_s1_board_lists_every_proposed_job_as_waiting_oldest_first(env):
    tag = unique_code("WT", alpha=True)
    c = lambda n: make_complaint(env, "wt", complaint_number=f"{tag}-{n}")  # noqa: E731
    now = datetime.utcnow()
    newer = make_job(env, c(1), "proposed")
    older = make_job(env, c(2), "proposed")
    dated = make_job(env, c(3), "proposed", scheduled_from=now + timedelta(days=3))
    confirmed = make_job(env, c(4), "confirmed", scheduled_from=now, agreed_by="x")
    newer.created_at = now - timedelta(days=1)
    older.created_at = now - timedelta(days=9)
    dated.created_at = now - timedelta(days=5)
    env.db.flush()
    mine = {newer.id, older.id, dated.id, confirmed.id}
    with api(env) as client:
        for day in ("2026-11-20", "2031-01-01"):
            body = client.get(f"{JOBS}/board", params={"day": day}).json()
            assert "stalled" not in body
            got = [j["id"] for j in body["waiting"] if j["id"] in mine]
            assert got == [older.id, dated.id, newer.id], (day, got)


# ------------------------------------------------------------------ S-2

def test_s2_no_complaints_access_means_no_rows(env):
    c = make_complaint(env, "s2")
    job = make_job(env, c, "proposed")
    with api(env, {VIEW}) as client:
        assert [r["id"] for r in client.get(JOBS, params={"limit": 200}).json()["data"]] == []
        assert client.get(f"{JOBS}/{job.id}").status_code == 404
        assert client.get(f"{COMPLAINTS}/{c.id}/service-jobs").status_code == 404
        board = client.get(f"{JOBS}/board", params={"day": "2026-11-20"}).json()
        assert all(not col["jobs"] for col in board["columns"]) and board["waiting"] == []


# ------------------------------------------------------------------ S-3

def _assistant(env, perms, contact_id=None):
    from tests.chatbot.agent._seed import seed_user
    from app.services.assistant_registry import query

    uid = seed_user(env.db, contact_pk=contact_id, slugs=perms)
    return lambda: query.run_query(env.db, uid, {"entity": "service_job", "limit": 100})


def test_s3_assistant_service_jobs_need_the_view_slug(env):
    from app.services.assistant_registry import query

    job = make_job(env, make_complaint(env, "s3a"), "proposed")
    ask = _assistant(env, [COWN])
    with pytest.raises(query.QueryRefused):
        ask()
    ask = _assistant(env, [VIEW])
    assert job.id not in {r.get("id") for r in ask()["rows"]}


def test_s3_assistant_view_plus_complaints_own_sees_only_own(env):
    from ._own_scope_support import contact

    mine, theirs = contact(env.db, "AS1"), contact(env.db, "AS2")
    a = make_job(env, make_complaint(env, "s3m", contact_id=mine.id, space_id="z"), "proposed")
    b = make_job(env, make_complaint(env, "s3t", contact_id=theirs.id, space_id="z"), "proposed")
    ids = {r.get("id") for r in _assistant(env, [VIEW, COWN], mine.id)()["rows"]}
    assert a.id in ids and b.id not in ids
    ids_all = {r.get("id") for r in _assistant(env, [VIEW, CVIEW])()["rows"]}
    assert {a.id, b.id} <= ids_all


# ------------------------------------------------------------------ S-4

def test_s4_brand_scoped_context_hides_jobs_without_an_in_scope_complaint(env):
    from app.models.base import set_brand_scope

    c = make_complaint(env, "s4")
    job = make_job(env, c, "proposed")
    with api(env) as client:
        assert job.id in [r["id"] for r in client.get(JOBS, params={"limit": 200}).json()["data"]]
        set_brand_scope(env.db, frozenset({str(uuid.uuid4())}))
        try:
            assert job.id not in [r["id"] for r in client.get(JOBS, params={"limit": 200}).json()["data"]]
            assert client.get(f"{JOBS}/{job.id}").status_code == 404
            assert client.post(raise_url(c.id)).status_code == 404
        finally:
            set_brand_scope(env.db, None)


# ------------------------------------------------------------------ S-5

def _company_b(env):
    row = Company(id=str(uuid.uuid4()), name=f"ZZT Co {uuid.uuid4().hex[:6]}", code=unique_code("ZB")[:20])
    env.db.add(row)
    env.db.flush()
    return row.id


def test_s5_a_live_job_in_another_company_blocks_a_second_raise(env):
    from app.models.service_jobs import ServiceJob

    c = make_complaint(env, "s5")
    other = _company_b(env)
    env.db.add(ServiceJob(
        id=str(uuid.uuid4()), job_number=f"SVT-{uuid.uuid4().hex[:8]}", complaint_id=c.id,
        status_id=status_id(env, "proposed"), company_id=other, created_by=env.actor_id,
    ))
    env.db.flush()
    with api(env) as client:
        r = client.post(raise_url(c.id))
    assert r.status_code == 409, r.text
    assert "another company" in r.text


def test_s5_assign_refuses_a_technician_of_another_company(env):
    from app.models.service_jobs import Technician

    job = make_job(env, make_complaint(env, "s5a"), "proposed")
    other = _company_b(env)
    tech = Technician(id=str(uuid.uuid4()), name=unique_code("T"), employment_type="employee",
                      is_active=True, company_id=other)
    env.db.add(tech)
    env.db.flush()
    with company_scope(env.db, frozenset({str(env.company_id), other})):
        with api(env) as client:
            r = client.post(f"{JOBS}/{job.id}/assign", json={"technician_id": tech.id})
    assert r.status_code == 422, r.text


# ------------------------------------------------------------------ S-6

def test_s6_raise_seeds_a_missing_numbering_rule(env):
    env.db.execute(text("delete from document_numbering_rules where doc_type = 'service_job'"))
    env.db.flush()
    c = make_complaint(env, "s6")
    with api(env) as client:
        r = client.post(raise_url(c.id))
    assert r.status_code == 201, r.text
    assert r.json()["job_number"].startswith("SV")


# ------------------------------------------------------------------ S-7

def test_s7_history_shows_the_technician_name_not_the_id(env):
    job = make_job(env, make_complaint(env, "s7"), "confirmed")
    tech = make_tech(env, "ZZT Test Tech A")
    with api(env) as client:
        assert client.post(f"{JOBS}/{job.id}/assign", json={"technician_id": tech.id}).status_code == 200
        audit_rows(env, job.id)
        rows = client.get(AUDIT, params={"entity_type": "service_jobs", "entity_id": job.id}).json()["data"]
    news = [(r["new_values"] or {}).get("technician_id") for r in rows]
    assert "ZZT Test Tech A" in news, news
    assert tech.id not in news


# ------------------------------------------------------------------ S-9

@pytest.mark.parametrize("frm,to", [("confirmed", "on_the_way"), ("confirmed", "arrived"), ("on_the_way", "arrived")])
def test_s9_arriving_needs_a_technician(env, frm, to):
    job = make_job(env, make_complaint(env, "s9"), frm, scheduled_from=datetime(2026, 11, 20, 2), agreed_by="x")
    with api(env) as client:
        r = client.post(f"{JOBS}/{job.id}/transition", json={"to": to})
    assert r.status_code == 422, r.text
    assert "Assign a technician first." in r.text


# ------------------------------------------------------------------ S-12

def test_s12_a_site_field_can_be_cleared_with_null(env):
    c = make_complaint(env, "s12", site_city="Ipoh")
    with api(env) as client:
        assert client.put(f"{COMPLAINTS}/{c.id}", json={"site_city": None}).status_code == 200
        assert client.get(f"{COMPLAINTS}/{c.id}").json()["site_city"] is None


# ------------------------------------------------------------------ nit

def test_resolutions_sort_by_requires_service_job(env):
    tag = uuid.uuid4().hex[:6]
    with api(env) as client:
        for letter, flag in (("a", False), ("b", True), ("c", False)):
            r = client.post(f"{RESOLUTIONS}/", json={"name": f"ZZT srt {tag} {letter}", "requires_service_job": flag})
            assert r.status_code == 201
        rows = client.get(f"{RESOLUTIONS}/", params={"query": f"ZZT srt {tag}", "sort": "requires_service_job", "dir": "desc"}).json()["data"]
    flags = [r["requires_service_job"] for r in rows]
    assert flags == sorted(flags, reverse=True) and flags[0] is True
