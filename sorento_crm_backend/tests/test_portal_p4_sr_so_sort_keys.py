"""PORTAL-P4-REQUESTS S4 + S6 red tests: every list column sorts on the server (UAC P4-23 pattern).

Column keys are the grids' own column ids (`SampleRequestsList.tsx`: request_no, submitted_at, status,
delivery_date, customer_name, project_name, delivery_mode, salesperson_name; `SalesOpportunitiesView.tsx`:
opportunity_no, title, customer, agent, stage_label, expected_amount, expected_close_date, source).
An unknown key silently falls back (SR: delivery date; opportunity: created_at), so each case seeds rows whose
requested order is NOT the fallback order and asserts the exact order. A column the grid sorts today
(`enableSorting: false` removed in the same slice for customer / agent / stage_label / source) is checked
for being accepted and stable; one single-valued by construction (one salesperson, one source) cannot be
told from the fallback and is asserted as accepted only.
"""
from __future__ import annotations

import pytest

from tests import _portal_p4_support as s
from tests._portal_p4_sr_so_support import SO_PORTAL, SO_STAFF, SR, SR_PORTAL, scene, world  # noqa: F401

# column -> (value to seed per row i in 0..2, so that ascending order is the order given)
SR_STRICT = {
    "request_no": None,  # creation order == number order
    "delivery_date": lambda i: {"delivery_date": f"2026-12-{10 + i:02d}"},
    "customer_name": lambda i: {"customer_name": f"ZZT {'bcd'[i]}"},
    "project_name": lambda i: {"project_title": f"ZZT {'bcd'[i]} project"},
    "delivery_mode": lambda i: {"delivery_mode": ["driver", "self_collect", "self_deliver"][i]},
    "status": None,
}
SR_ACCEPTED_ONLY = ["submitted_at", "salesperson_name"]


def _sr_rows(w, column):
    ids = []
    for i in range(3):
        over = (SR_STRICT[column](2 - i) if SR_STRICT.get(column) else {})  # created in REVERSE of ascending order
        d = s.ok(w.rep.portal.call("POST", SR_PORTAL, json=w.sr_body(**over)), 201).json()
        if column != "status" or i != 0:
            s.ok(w.rep.portal.call("POST", f"{SR_PORTAL}/{d['id']}/submit"))
        if column == "status" and i == 2:
            s.ok(w.rep.portal.call("POST", f"{SR_PORTAL}/{d['id']}/cancel"))
        ids.append(d["id"])
    return ids


@pytest.mark.parametrize("column", list(SR_STRICT))
def test_p4_sr_list_sorts_on_every_column(world, column):
    w = world
    ids = _sr_rows(w, column)
    asc = [x["id"] for x in s.ok(w.staff(w.rep.actor, "GET", SR, params={"sort": column, "dir": "asc"})).json()["data"]]
    desc = [x["id"] for x in s.ok(w.staff(w.rep.actor, "GET", SR, params={"sort": column, "dir": "desc"})).json()["data"]]
    assert set(asc) == set(desc) == set(ids)
    assert asc == list(reversed(desc)), f"sort={column}: asc and desc gave the same order, the key is ignored"
    if column in {"delivery_date", "customer_name", "project_name", "delivery_mode"}:
        assert asc == list(reversed(ids)), f"sort={column} asc mis-ordered"
    if column == "request_no":
        assert asc == ids


@pytest.mark.parametrize("column", SR_ACCEPTED_ONLY)
def test_p4_sr_list_accepts_the_single_valued_columns(world, column):
    w = world
    ids = _sr_rows(w, "request_no")
    for direction in ("asc", "desc"):
        got = s.ok(w.staff(w.rep.actor, "GET", SR, params={"sort": column, "dir": direction})).json()["data"]
        assert {x["id"] for x in got} == set(ids)


SO_STRICT = {
    "opportunity_no": None,
    "title": lambda i: {"title": f"ZZT {'bcd'[i]}"},
    "customer": lambda i: {"prospect_name": f"ZZT {'bcd'[i]} prospect"},
    "expected_amount": lambda i: {"expected_amount": str(100 * (i + 1))},
    "expected_close_date": lambda i: {"expected_close_date": f"2026-12-{10 + i:02d}"},
}
SO_ACCEPTED_ONLY = ["agent", "stage_label", "source"]


def _so_rows(w, column):
    ids = []
    for i in range(3):
        over = SO_STRICT[column](2 - i) if SO_STRICT.get(column) else {}  # created in REVERSE of ascending order
        ids.append(s.ok(w.rep.portal.call("POST", SO_PORTAL, json=w.so_body(**over)), 201).json()["id"])
    return ids


@pytest.mark.parametrize("column", list(SO_STRICT))
def test_p4_so_list_sorts_on_every_column(world, column):
    w = world
    ids = _so_rows(w, column)
    asc = [x["id"] for x in s.ok(w.staff(w.rep.actor, "GET", SO_STAFF, params={"sort": column, "dir": "asc"})).json()["data"]]
    desc = [x["id"] for x in s.ok(w.staff(w.rep.actor, "GET", SO_STAFF, params={"sort": column, "dir": "desc"})).json()["data"]]
    assert set(asc) == set(desc) == set(ids)
    assert asc == list(reversed(desc)), f"sort={column}: asc and desc gave the same order, the key is ignored"
    if column == "opportunity_no":
        assert asc == ids
    else:
        assert asc == list(reversed(ids)), f"sort={column} asc mis-ordered"


@pytest.mark.parametrize("column", SO_ACCEPTED_ONLY)
def test_p4_so_list_accepts_the_agent_stage_and_source_columns(world, column):
    w = world
    ids = _so_rows(w, "opportunity_no")
    for direction in ("asc", "desc"):
        r = w.staff(w.rep.actor, "GET", SO_STAFF, params={"sort": column, "dir": direction})
        assert r.status_code == 200, r.text
        assert {x["id"] for x in r.json()["data"]} == set(ids)
