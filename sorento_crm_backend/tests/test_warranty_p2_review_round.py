"""AFTER-SALES-P2 review round, backend red tests.

1. jobs list: with a `warranty_summary` filter the requested sort (job_number, customer, or none = newest first) wins,
   not the summary order. Summary order only applies for sort=warranty_summary.
2. the five admin-only warranty deferred actions re-check admin at COMMIT: parked as admin, role removed before the
   window lapses -> nothing is deleted or archived, outcome is not "committed".
3. parking warranty_term.delete on a term whose policy belongs to another company is refused at park (403/404).
4. a session scoped to two companies cannot create a policy: overlap, duplicate version and a plain create all answer a
   4xx and nothing is written (the default `ambiguous` handling must never silently pick or skip a company).
5. policies list sorts server-side on `term_count` and on `status` (display lifecycle order asc: in_force, scheduled,
   superseded; desc reversed), ties by id.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from contextlib import contextmanager

import pytest

from app.models.base import set_company_scope
from app.models.sla import SlaFormAction

from ._service_jobs_p1_support import api as _api
from ._warranty_p2_support import (
    DISPATCH,
    JOBS,
    POLICIES,
    VIEW,
    WC,
    env,  # noqa: F401
    make_company,
    make_job,
    make_kind,
    make_policy,
    make_product,
    make_term,
)
from .test_warranty_p2_deferred_actions import WARRANTY_KINDS, current, lapse, park, seed

D = date


@contextmanager
def api_all_companies(env, *args, **kwargs):
    with _api(env, *args, **kwargs) as client:
        set_company_scope(env.db, None)
        yield client


# ------------------------------------------------------------------ 1. job list order with the filter


def _covered_jobs(env, n=5):
    from app.models.service_jobs import ServiceJobProduct

    policy, kind, product = make_policy(env), make_kind(env), make_product(env, *WC)
    make_term(env, policy, kind, "Body", lifetime=True)
    tag = f"ZZTORD{uuid.uuid4().hex[:5]}"
    order = [3, 1, 5, 2, 4]  # insertion order is not sorted order
    jobs = {}
    for r in order[:n]:
        job = make_job(
            env,
            job_number=f"{tag}-{r}",
            customer_name=f"{tag} cust {'edcba'[r - 1]}",
            created_at=datetime(2026, 11, 1) + timedelta(hours=r),
        )
        env.db.add(ServiceJobProduct(
            id=str(uuid.uuid4()), service_job_id=job.id, product_id=product.id, kind_id=kind.id,
            purchase_date=D(2020, 3, 15), company_id=env.company_id,
        ))
        jobs[r] = job
    env.db.flush()
    return tag, jobs


def _ids(c, **params):
    r = c.get(JOBS, params={"limit": 50, "warranty_summary": "covered", **params})
    assert r.status_code == 200, r.text
    return [x["id"] for x in r.json()["data"]]


@pytest.mark.parametrize("direction,ranks", [("asc", [1, 2, 3, 4, 5]), ("desc", [5, 4, 3, 2, 1])])
def test_review1_a_summary_filter_keeps_the_requested_job_number_sort(env, direction, ranks):
    tag, jobs = _covered_jobs(env)
    with _api(env) as c:
        assert _ids(c, query=tag, sort="job_number", dir=direction) == [jobs[r].id for r in ranks]


def test_review1_a_summary_filter_keeps_the_customer_sort(env):
    tag, jobs = _covered_jobs(env)
    with _api(env) as c:
        # customer letters run e,d,c,b,a for ranks 1..5, so ascending customer is rank 5 first
        assert _ids(c, query=tag, sort="customer", dir="asc") == [jobs[r].id for r in (5, 4, 3, 2, 1)]


def test_review1_a_summary_filter_with_no_sort_is_newest_first(env):
    tag, jobs = _covered_jobs(env)
    with _api(env) as c:
        assert _ids(c, query=tag) == [jobs[r].id for r in (5, 4, 3, 2, 1)]


# ------------------------------------------------------------------ 2. admin re-checked at commit


@pytest.mark.parametrize("what", WARRANTY_KINDS)
def test_review2_losing_the_admin_role_before_the_window_lapses_stops_the_action(env, what):
    key, etype, rid, done = seed(env, what)
    with api_all_companies(env, {VIEW, DISPATCH}, roles={"admin"}) as c:
        r = park(c, key, etype, rid)
        assert r.status_code == 202, r.text
        action_id = r.json()["id"]
    lapse(env, action_id)
    with api_all_companies(env, {VIEW, DISPATCH}, roles=()) as c:  # same user, role withdrawn
        body = current(c, etype, rid).json()
    assert not done(), "the action ran although the requester was no longer an admin"
    assert body["last_outcome"] is None or body["last_outcome"]["status"] != "committed"


# ------------------------------------------------------------------ 3. term of another company


def test_review3_parking_a_term_delete_on_another_companys_term_is_refused(env):
    from app.models.warranty import WarrantyTerm

    other = make_company(env)
    theirs = make_policy(env, "ZZTTHEIRS", D(2000, 1, 1), None, company_id=other)
    term = make_term(env, theirs, make_kind(env), "Body", months=12)
    with _api(env, {VIEW, DISPATCH}, roles={"admin"}) as c:  # scoped to our company only
        r = park(c, "warranty_term.delete", "warranty_term", term.id)
        assert r.status_code in (403, 404), r.text
    env.db.expire_all()
    assert env.db.query(SlaFormAction).filter(SlaFormAction.source_entity_id == term.id).count() == 0
    assert env.db.get(WarrantyTerm, term.id) is not None


# ------------------------------------------------------------------ 4. two-company scope


def test_review4_a_two_company_scope_never_silently_creates_or_skips_the_overlap_check(env):
    from app.models.warranty import WarrantyPolicy

    other = make_company(env)
    make_policy(env, "ZZTEXIST", D(2024, 1, 1), D(2024, 12, 31))
    with _api(env, roles={"admin"}) as c:
        set_company_scope(env.db, frozenset({env.company_id, other}))
        before = env.db.query(WarrantyPolicy).count()
        overlap = c.post(POLICIES, json={"version": "ZZTNEW1", "effective_from": "2024-06-01", "effective_to": "2024-09-30"})
        dup = c.post(POLICIES, json={"version": "ZZTEXIST", "effective_from": "2030-01-01", "effective_to": "2030-12-31"})
        for r in (overlap, dup):
            assert 400 <= r.status_code < 500, (r.status_code, r.text)
        assert env.db.query(WarrantyPolicy).count() == before
        # last: a refusal raised inside the flush leaves this shared test session unusable afterwards
        plain = c.post(POLICIES, json={"version": "ZZTNEW2", "effective_from": "2035-01-01", "effective_to": "2035-12-31"})
        assert 400 <= plain.status_code < 500, (plain.status_code, plain.text)


# ------------------------------------------------------------------ 5. policies list sorts


def _sort_world(env):
    tag = f"ZZTSRT{uuid.uuid4().hex[:5]}"
    kind = make_kind(env)
    spec = {  # name -> (from, to, terms)
        "a": (D(2001, 1, 1), D(2002, 1, 1), 2),    # superseded
        "b": (D(2000, 1, 1), None, 0),             # in force
        "c": (D(2099, 1, 1), None, 3),             # scheduled
        "d": (D(2003, 1, 1), D(2004, 1, 1), 1),    # superseded
        "e": (D(2005, 1, 1), None, 4),             # in force
    }
    made = {}
    for name, (start, end, n) in spec.items():
        policy = make_policy(env, f"{tag}-{name}", start, end)
        for i in range(n):
            make_term(env, policy, kind, f"P{i}", months=12)
        made[name] = policy
    return tag, made


def _versions(c, tag, **params):
    r = c.get(POLICIES, params={"query": tag, "limit": 50, **params})
    assert r.status_code == 200, r.text
    return [x["version"].split("-")[-1] for x in r.json()["data"]]


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_review5_policies_sort_by_term_count(env, direction):
    tag, _ = _sort_world(env)
    with _api(env, roles={"admin"}) as c:
        # terms: b0 d1 a2 c3 e4
        got = "".join(_versions(c, tag, sort="term_count", dir=direction))
    assert got == ("bdace" if direction == "asc" else "ecadb")


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_review5_policies_sort_by_status_in_display_order(env, direction):
    tag, _ = _sort_world(env)
    with _api(env, roles={"admin"}) as c:
        got = _versions(c, tag, sort="status", dir=direction)
        rank = {"b": 0, "e": 0, "c": 1, "a": 2, "d": 2}  # in_force, scheduled, superseded
        ranks = [rank[v] for v in got]
        assert ranks == sorted(ranks, reverse=direction == "desc")
        paged = []
        for page in (1, 2, 3):
            paged += _versions(c, tag, sort="status", dir=direction, limit=2, page=page)
        assert paged == got
