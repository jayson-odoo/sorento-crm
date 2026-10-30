"""PORTAL-P4-REQUESTS S5 red tests: every New Product Application list column sorts on the server (UAC P4-23).

Column ids are `NewProductApplicationsList.tsx`'s: application_no, status, stock_inquiry_number, customer_name,
first_line, lines_total, lines_done, needed_by, created_at. Server keys today: application_no, status, created_at,
submitted_at, needed_by, customer_name. An unknown key silently falls back to created_at, so each case seeds rows whose
requested order is NOT the fallback order and asserts the exact order. `lines_done` is 0 for every row of a fresh
list (a line is done only once purchasing opens it), so it is asserted as accepted only.
"""
from __future__ import annotations

import pytest

from tests import _portal_p4_support as s
from tests._portal_p4_npa_support import NPA, SUB, create, scene, world  # noqa: F401

# column -> builder of the body for row i (rows are created i = 0, 1, 2; the value sorts DESCENDING in i, so
# ascending order is the reverse of creation order, the opposite of the created_at fallback ascending)
STRICT = {
    "customer_name": lambda w, i, ids: dict(customer_name=f"ZZT {'dcb'[i]} customer"),
    "needed_by": lambda w, i, ids: dict(needed_by=f"2026-12-{20 - i:02d}"),
    "first_line": lambda w, i, ids: dict(lines=[w.line(description=f"ZZT {'dcb'[i]} sink")]),
    "lines_total": lambda w, i, ids: dict(lines=[w.line() for _ in range(3 - i)]),
    "stock_inquiry_number": None,  # built from real inquiries below
}


def _rows(w, column):
    ids = []
    inquiries = []
    if column == "stock_inquiry_number":
        # inquiry numbers ascend in creation order, so the fallback (created_at desc) and asc disagree
        inquiries = [w.inquiry(w.rep, inquiry_number=f"SI26-Z{'cba'[i]}{s.uid()[:3]}") for i in range(3)]
    for i in range(3):
        if column == "stock_inquiry_number":
            over = dict(stock_inquiry_id=inquiries[i].id)
        else:
            over = STRICT[column](w, i, ids)
        ids.append(create(w.rep.portal, w, **over)["id"])
    return ids


@pytest.mark.parametrize("column", list(STRICT))
def test_p4_npa_list_sorts_on_every_column(world, column):
    w = world
    ids = _rows(w, column)

    def order(direction):
        got = s.ok(w.staff(w.rep.actor, "GET", NPA, params={"sort": column, "dir": direction})).json()["items"]
        return [x["id"] for x in got]

    asc, desc = order("asc"), order("desc")
    assert set(asc) == set(desc) == set(ids)
    assert asc != desc, f"sort={column}: asc and desc gave the same order, the key is ignored"
    assert asc == list(reversed(desc))
    # value order, not creation order: the created_at fallback would give ids (asc) / reversed (desc)
    assert asc == list(reversed(ids)), f"sort={column} asc mis-ordered"


def test_p4_npa_list_accepts_lines_done_both_directions(world):
    w = world
    ids = _rows(w, "lines_total")
    for direction in ("asc", "desc"):
        r = w.staff(w.rep.actor, "GET", NPA, params={"sort": "lines_done", "dir": direction})
        assert r.status_code == 200, r.text
        assert {x["id"] for x in r.json()["items"]} == set(ids)
