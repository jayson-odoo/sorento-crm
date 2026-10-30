"""PORTAL-P4-REQUESTS S7 red tests: every Price Tag Request list column sorts on the server, for everyone (UAC P4-23).

`PriceTagRequestsList.tsx` today sets `enableSorting: false` on contact_name, line_count, assigned_to_name and
data_changed_tag_count, and `PriceTagRequestService.SORTABLE_COLUMNS` lacks them, so an unknown key falls back
to created_at desc. Each case seeds three rows whose requested order is NOT the fallback order and asserts the
exact order, ascending and descending.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.services.price_tag_request_service import PriceTagRequestService
from tests import _portal_p4_support as s
from tests import _ptag_r9_seed
from tests._portal_p4_pt_support import PT_VIEW, STAFF, scene, world  # noqa: F401


def _rows(w, **per_row):
    """Three submitted staff-visible rows, CREATED in the order a, b, c with created_at one minute apart (so the
    fallback order, created_at desc, is c, b, a and never the ascending order asked for), returned as [a, b, c]."""
    made = []
    for i, tag in enumerate("abc"):
        contact = per_row["contact"](tag) if "contact" in per_row else w.rep.contact
        n_lines = per_row["lines"](tag) if "lines" in per_row else 1
        req = PriceTagRequestService.create_request(
            w.sc.db, contact_id=contact.id, company_id=w.company_id,
            data={"debtor_name": f"ZZT d{tag}", "print_by": "office", "lines": [
                {"line_type": "product", "product_id": _ptag_r9_seed.seed_product(w.sc.db).id} for _ in range(n_lines)]},
        )
        req.portal_draft_at = None
        req.created_at = datetime(2026, 1, 1, 8, i)
        if "assignee" in per_row:
            req.assigned_to_id = per_row["assignee"](tag).id
        if "changed" in per_row:
            req.data_changed_tag_count = per_row["changed"](tag)
            req.data_checked_at = datetime.utcnow()
        made.append((tag, req.id))
    w.sc.db.commit()
    return [rid for _tag, rid in sorted(made)]


def _listing(w, column, direction):
    staff = s.make_user(w.sc.db, perms=[PT_VIEW], name="ZZT Sorter")
    body = s.ok(w.staff(staff, "GET", STAFF, params={"sort": column, "dir": direction, "limit": 200})).json()
    return body["data"]


def _check(w, column, ordered):
    asc = [r["id"] for r in _listing(w, column, "asc") if r["id"] in ordered]
    desc = [r["id"] for r in _listing(w, column, "desc") if r["id"] in ordered]
    assert asc == ordered, f"sort={column} asc mis-ordered (falls back to created_at desc?)"
    assert desc == list(reversed(ordered)), f"sort={column} desc mis-ordered"


def test_p4_pt_list_sorts_on_contact_name(world):
    w = world
    mk = lambda tag: s._contact(w.sc.db, f"ZZT Sales {tag}", w.sc.workspace)  # noqa: E731
    _check(w, "contact_name", _rows(w, contact=mk))


def test_p4_pt_list_sorts_on_line_count(world):
    w = world
    sizes = {"a": 1, "b": 2, "c": 3}
    _check(w, "line_count", _rows(w, lines=lambda tag: sizes[tag]))


def test_p4_pt_list_sorts_on_assigned_to_name(world):
    w = world
    people = {t: s.make_user(w.sc.db, name=f"ZZT Assignee {t}").user for t in "abc"}
    _check(w, "assigned_to_name", _rows(w, assignee=lambda tag: people[tag]))


def test_p4_pt_list_sorts_on_data_changed_tag_count(world):
    w = world
    counts = {"a": 1, "b": 2, "c": 3}
    _check(w, "data_changed_tag_count", _rows(w, changed=lambda tag: counts[tag]))


@pytest.mark.parametrize("column", ["doc_number", "debtor_name", "status", "needed_by_date", "created_at"])
def test_p4_pt_list_keeps_sorting_the_existing_columns(world, column):
    w = world
    _rows(w)
    asc = [r["id"] for r in _listing(w, column, "asc")]
    desc = [r["id"] for r in _listing(w, column, "desc")]
    assert len(asc) >= 3 and set(asc) == set(desc)
