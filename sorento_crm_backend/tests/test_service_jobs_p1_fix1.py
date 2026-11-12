"""AFTER-SALES-P1 fix round 1 findings that survive the standalone module (owner ruling 12 Nov).

B-1 History for non-admins, S-1 waiting board, S-5 cross-company live job and assign, S-6 numbering
self-seeds, S-7 History shows technician names, S-9 technician guard. The complaint-coupled ones
(re-raise on save, complaint scope, brand scope, site on the complaint) are gone with the coupling.
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
    DISPATCH,
    JOBS,
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


# ------------------------------------------------------------------ S-5

def _company_b(env):
    row = Company(id=str(uuid.uuid4()), name=f"ZZT Co {uuid.uuid4().hex[:6]}", code=unique_code("ZB")[:20])
    env.db.add(row)
    env.db.flush()
    return row.id


def test_s5_a_live_job_in_another_company_blocks_a_second_create(env):
    from app.models.service_jobs import ServiceJob

    c = make_complaint(env, "s5")
    other = _company_b(env)
    env.db.add(ServiceJob(
        id=str(uuid.uuid4()), job_number=f"SVT-{uuid.uuid4().hex[:8]}", complaint_id=c.id,
        customer_name="ZZT other", status_id=status_id(env, "proposed"), company_id=other, created_by=env.actor_id,
    ))
    env.db.flush()
    with api(env) as client:
        r = client.post(JOBS, json={"customer_name": "ZZT x", "complaint_id": c.id})
    assert r.status_code == 409, r.text
    assert "already has a live service job" in r.text


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
    with api(env) as client:
        r = client.post(JOBS, json={"customer_name": "ZZT s6"})
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


