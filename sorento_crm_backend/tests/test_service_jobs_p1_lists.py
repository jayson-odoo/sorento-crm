"""AFTER-SALES-P1 red tests: list sort/filter/search (D1), dispatch board (E2, E3), scope (H3).

Sort keys (the `sort` query value) the coder must accept: job_number, complaint_number, status,
scheduled_from, technician, city, customer. `dir` is asc|desc. Filters: `status` (repeatable or
comma), `technician_id` (same), `date_from` / `date_to` (YYYY-MM-DD, on scheduled_from, MYT).
Search: `query`. Row fields: see tests/_service_jobs_p1_support.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from ._service_jobs_p1_support import (
    ALL_PERMS,
    JOBS,
    VIEW,
    Env,
    api,
    env,  # noqa: F401
    make_complaint,
    make_job,
    make_tech,
)
from ._pg_fixture import unique_code

# rank r in 1..5 -> letter; insertion order is deliberately NOT sorted order
LETTERS = "ghijk"
INSERT_ORDER = [3, 1, 5, 2, 4]


def _seed_five(env):
    tag = unique_code("LS", alpha=True)
    jobs = {}
    base = datetime(2026, 11, 20, 2, 0)
    for r in INSERT_ORDER:
        L = LETTERS[r - 1]
        c = make_complaint(env, "ls", complaint_number=f"{tag}-c{L}")
        tech = make_tech(env, f"{tag} tech {L}")
        status = ["proposed", "confirmed", "on_the_way", "arrived", "completed"][r - 1]
        jobs[r] = make_job(
            env, c, status, technician=tech, scheduled_from=base + timedelta(hours=r),
            job_number=f"SVT-{tag}-{L}", customer_name=f"{tag} cust {L}", site_city=f"{tag} city {L}",
        )
    return tag, jobs


def _ids(resp):
    assert resp.status_code == 200, resp.text
    return [row["id"] for row in resp.json()["data"]]


def _page_through(client, tag, sort, direction, limit=2):
    got = []
    for page in (1, 2, 3):
        got += _ids(client.get(JOBS, params={"query": tag, "sort": sort, "dir": direction, "page": page, "limit": limit}))
    return got


COLUMNS = ["job_number", "complaint_number", "scheduled_from", "technician", "city", "customer"]


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("column", COLUMNS)
def test_d1_every_column_sorts_both_ways_and_the_order_holds_on_page_two(env, column, direction):
    tag, jobs = _seed_five(env)
    ranks = [1, 2, 3, 4, 5] if direction == "asc" else [5, 4, 3, 2, 1]
    expected = [jobs[r].id for r in ranks]
    with api(env) as client:
        assert _page_through(client, tag, column, direction) == expected
        one_page = _ids(client.get(JOBS, params={"query": tag, "sort": column, "dir": direction, "limit": 50}))
        assert one_page == expected


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_d1_status_sorts_consistently_across_pages(env, direction):
    tag, jobs = _seed_five(env)
    with api(env) as client:
        asc = _page_through(client, tag, "status", "asc")
        desc = _page_through(client, tag, "status", "desc")
    assert sorted(asc) == sorted(j.id for j in jobs.values())
    assert asc == list(reversed(desc))


def test_d1_envelope_and_pagination_total(env):
    tag, jobs = _seed_five(env)
    with api(env) as client:
        body = client.get(JOBS, params={"query": tag, "limit": 2}).json()
    assert body["pagination"]["total"] == 5
    assert len(body["data"]) == 2
    row = body["data"][0]
    for field in ("job_number", "complaint_number", "status", "scheduled_from", "technician_name", "city", "customer_name"):
        assert field in row, field


def test_d1_status_filter_is_multi(env):
    tag, jobs = _seed_five(env)
    with api(env) as client:
        both = _ids(client.get(JOBS, params=[("query", tag), ("status", "proposed"), ("status", "arrived")]))
        comma = _ids(client.get(JOBS, params={"query": tag, "status": "proposed,arrived"}))
        one = _ids(client.get(JOBS, params={"query": tag, "status": "confirmed"}))
    assert set(both) == set(comma) == {jobs[1].id, jobs[4].id}
    assert one == [jobs[2].id]


def test_d1_technician_filter_is_multi(env):
    tag, jobs = _seed_five(env)
    t = lambda r: jobs[r].technician_id  # noqa: E731
    with api(env) as client:
        got = _ids(client.get(JOBS, params=[("query", tag), ("technician_id", t(1)), ("technician_id", t(5))]))
        comma = _ids(client.get(JOBS, params={"query": tag, "technician_id": f"{t(1)},{t(5)}"}))
    assert set(got) == set(comma) == {jobs[1].id, jobs[5].id}


def test_d1_scheduled_date_range_filter(env):
    tag, jobs = _seed_five(env)
    # all five sit on 20/11/2026 MYT; shift two onto other days
    jobs[1].scheduled_from = datetime(2026, 11, 18, 2, 0)
    jobs[5].scheduled_from = datetime(2026, 11, 25, 2, 0)
    env.db.flush()
    with api(env) as client:
        mid = set(_ids(client.get(JOBS, params={"query": tag, "date_from": "2026-11-19", "date_to": "2026-11-21"})))
        from_only = set(_ids(client.get(JOBS, params={"query": tag, "date_from": "2026-11-21"})))
    assert mid == {jobs[2].id, jobs[3].id, jobs[4].id}
    assert from_only == {jobs[5].id}


@pytest.mark.parametrize("field", ["job_number", "complaint_number", "customer", "city"])
def test_d1_search_covers_four_fields(env, field):
    tag, jobs = _seed_five(env)
    needle = {
        "job_number": f"SVT-{tag}-h",
        "complaint_number": f"{tag}-ch",
        "customer": f"{tag} cust h",
        "city": f"{tag} city h",
    }[field]
    with api(env) as client:
        assert _ids(client.get(JOBS, params={"query": needle})) == [jobs[2].id]


def test_view_permission_gates_the_list(env):
    with api(env, set()) as client:
        assert client.get(JOBS).status_code == 403
    with api(env, {VIEW}) as client:
        assert client.get(JOBS).status_code == 200


# ------------------------------------------------------------------ E2 / E3 board

MYT = "+08:00"


def _board(client, day):
    r = client.get(f"{JOBS}/board", params={"day": day})
    assert r.status_code == 200, r.text
    return r.json()


def _col(board, name):
    for col in board["columns"]:
        if col["technician_name"] == name:
            return col
    return None


def test_e2_columns_unassigned_first_then_active_technicians_with_a_job_that_day(env):
    tag = unique_code("BD", alpha=True)
    busy, idle, gone = make_tech(env, f"{tag} busy"), make_tech(env, f"{tag} idle"), make_tech(env, f"{tag} gone", active=False)
    c = lambda n: make_complaint(env, "bd", complaint_number=f"{tag}-{n}")  # noqa: E731
    day = datetime(2026, 11, 20)
    late = make_job(env, c(1), "confirmed", technician=busy, scheduled_from=day.replace(hour=6), agreed_by="x")   # 14:00 MYT
    early = make_job(env, c(2), "confirmed", technician=busy, scheduled_from=day.replace(hour=1), agreed_by="x")  # 09:00 MYT
    nobody = make_job(env, c(3), "confirmed", scheduled_from=day.replace(hour=3), agreed_by="x")
    make_job(env, c(4), "confirmed", technician=gone, scheduled_from=day.replace(hour=3), agreed_by="x")
    other_day = make_job(env, c(5), "confirmed", technician=idle, scheduled_from=day + timedelta(days=1, hours=3), agreed_by="x")
    with api(env) as client:
        board = _board(client, "2026-11-20")
    names = [col["technician_name"] for col in board["columns"]]
    assert names[0] == "Unassigned"
    assert f"{tag} busy" in names
    # Fix round 2 (R2-3): a column for EVERY technician with a job that day, archived ones included;
    # only a job with no technician is Unassigned.
    assert f"{tag} idle" not in names and f"{tag} gone" in names
    assert [j["id"] for j in _col(board, f"{tag} busy")["jobs"]] == [early.id, late.id]
    assert [j["id"] for j in _col(board, "Unassigned")["jobs"] if j["id"] == nobody.id] == [nobody.id]
    assert other_day.id not in {j["id"] for col in board["columns"] for j in col["jobs"]}
    assert nobody.id in [j["id"] for j in _col(board, "Unassigned")["jobs"]]
    assert len(_col(board, f"{tag} gone")["jobs"]) == 1


def test_e2_day_is_the_myt_day(env):
    tag = unique_code("BM", alpha=True)
    # 00:30 MYT on 21/11 is 16:30 UTC on 20/11; stored as naive UTC by the app's convention
    j = make_job(env, make_complaint(env, "bm", complaint_number=f"{tag}-1"), "confirmed",
                 scheduled_from=datetime(2026, 11, 20, 16, 30), agreed_by="x")
    with api(env) as client:
        on21 = {x["id"] for c in _board(client, "2026-11-21")["columns"] for x in c["jobs"]}
        on20 = {x["id"] for c in _board(client, "2026-11-20")["columns"] for x in c["jobs"]}
    assert j.id in on21 and j.id not in on20


def test_e3_waiting_is_every_proposed_job_oldest_raised_first_whatever_the_day(env):
    """Fix round 1 (S-1): "Stalled" had no reachable meaning (a Proposed job has no date), so the
    top section is "Waiting for a date": every Proposed job, any day, oldest raised first."""
    tag = unique_code("ST", alpha=True)
    c = lambda n: make_complaint(env, "st", complaint_number=f"{tag}-{n}")  # noqa: E731
    now = datetime.utcnow()
    newer = make_job(env, c(1), "proposed")
    older = make_job(env, c(2), "proposed")
    undated_confirmed = make_job(env, c(5), "confirmed", scheduled_from=now, agreed_by="x")
    newer.created_at = now - timedelta(days=1)
    older.created_at = now - timedelta(days=9)
    env.db.flush()
    with api(env) as client:
        for day in ("2026-11-20", "2031-01-01"):
            waiting = [j["id"] for j in _board(client, day)["waiting"]]
            mine = [i for i in waiting if i in {newer.id, older.id, undated_confirmed.id}]
            assert mine == [older.id, newer.id], (day, mine)


# ------------------------------------------------------------------ visibility

def test_a_job_with_no_related_complaint_lists_and_sorts_with_a_blank_complaint_number(env):
    tag = unique_code("NC", alpha=True)
    job = make_job(env, None, "proposed", customer_name=f"{tag} cust")
    with api(env) as client:
        rows = client.get(JOBS, params={"query": tag, "sort": "complaint_number", "dir": "asc"}).json()["data"]
    assert [r["id"] for r in rows] == [job.id] and rows[0]["complaint_number"] is None


# ------------------------------------------------------------------ round 7 (R7-3): empty values sort last

@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("column,field", [("city", "site_city"), ("customer", "customer_name"), ("complaint_number", None)])
def test_empty_values_sort_last_both_ways(env, column, field, direction):
    tag = unique_code("EM", alpha=True)
    make = lambda n, **kw: make_job(env, kw.pop("complaint", None), "proposed", job_number=f"SVT-{tag}-{n}", **kw)  # noqa: E731
    if column == "complaint_number":
        full = make("a", complaint=make_complaint(env, "em", complaint_number=f"{tag}-zzz"), customer_name=f"{tag} x")
        none = make("b", customer_name=f"{tag} y")
        empty = make("c", customer_name=f"{tag} z")
    else:
        base = {"customer_name": f"{tag} base"}
        mk = lambda n, v: make(n, **{**base, field: v})  # noqa: E731
        full = mk("a", f"{tag} value")
        none = mk("b", None) if field != "customer_name" else mk("b", " ")
        empty = mk("c", "") if field != "customer_name" else mk("c", "   ")
    with api(env) as client:
        rows = client.get(JOBS, params={"query": tag, "sort": column, "dir": direction, "limit": 50}).json()["data"]
    ids = [r["id"] for r in rows]
    assert ids[0] == full.id, (column, direction, ids)
    assert set(ids[1:]) == {none.id, empty.id}
