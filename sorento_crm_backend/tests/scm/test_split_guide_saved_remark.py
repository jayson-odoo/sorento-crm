"""OI-SPLIT-GUIDE round 3 (UAC F3): the split read gives every line a saved decision's words.

`LineSplitService.read` gains `saved_remark` per line: the purchasing email's own words for the
line's SAVED draft (`saved_line_remark`, one function), null when the line has no saved draft. A
covered line the read skipped (book-cancelled) is returned when it has a saved draft; one
delivered in full carries its saved words. Every row is seeded here (CI's database has no data).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.project_order_inquiry_service import saved_line_remark
from tests.scm.test_line_splits_api import _url
from tests.scm.test_line_splits_round3 import api, world  # noqa: F401 - fixtures reused
from tests.test_planning_changes import BASE, _core_line, _core_so, _project_line, _project_so

D = date(2026, 11, 20)


class _S:
    pass


def _seed(api):
    """Six lines on one order, nothing confirmed: 10 own reserve, 20 pool reserve + buy, 30 order
    back, 40 no draft, 50 delivered in full, 60 cancelled in the book."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    s = _S()
    s.client, s.world, s.db, s.core_so, s.order = client, world, db, core_so, order
    s.core, s.line = {}, {}
    for no in (10, 20, 30, 40, 50, 60):
        core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10", required_date=D)
        core.line_no = no
        line = _project_line(db, order, line_no=no, product=world.product, core_line=core)
        line.stock_location = world.own_wh.warehouse_code
        s.core[no], s.line[no] = core, line
    db.commit()
    return s


def _save_draft(s, no, decision):
    board = s.client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": s.core_so.so_number, "granularity": "week"},
    )
    assert board.status_code == 200, board.text
    key = next(
        c["key"] for c in board.json()["contributions"] if c.get("project_line_id") == str(s.line[no].id)
    )
    r = s.client.put(f"{BASE}/fulfilment-planning/lines/{key}/draft", json={"decision": decision})
    assert r.status_code == 200, f"premise: the draft of line {no} saves: {r.text}"


def _own(s, qty):
    w = s.world.own_wh
    return {"warehouse_id": str(w.id), "location": w.warehouse_code, "qty": str(qty)}


def _pool(s, qty):
    w = s.world.pool_wh
    return {"warehouse_id": str(w.id), "location": w.warehouse_code, "qty": str(qty), "rung": "pool"}


def _amend(reserve=(), buy="0", **extra):
    return {"verdict": "amended", "reserve": list(reserve), "borrow": [], "buy_qty": str(buy),
            "reason": "Planner choice.", **extra}


def _read(s):
    r = s.client.get(_url(s.order.id))
    assert r.status_code == 200, r.text
    return {x["line_no"]: x for x in r.json()["lines"]}


def _email_words(reserve=(), buy=None, order_back=False, own=None):
    """What the email's own function says for the same decision (one function)."""
    components = [
        {"kind": "reserve", "qty": c["qty"], "rung": c.get("rung"), "source_location": c["location"]}
        for c in reserve
    ]
    if buy:
        components.append({"kind": "buy", "qty": str(buy)})
    return saved_line_remark(
        {"components": components, "order_back": order_back, "location": own}
    )[0]


def test_f3_own_location_reserve_reads_use_and_the_location(api):
    s = _seed(api)
    _save_draft(s, 10, _amend([_own(s, 10)]))
    got = _read(s)[10]
    assert "saved_remark" in got, ("the split read declares saved_remark", sorted(got))
    assert got["saved_remark"] == f"USE {s.world.own_wh.warehouse_code}"
    assert got["saved_remark"] == _email_words([_own(s, 10)])


def test_f3_pool_reserve_and_buy_read_in_the_emails_words(api):
    s = _seed(api)
    _save_draft(s, 20, _amend([_pool(s, 6)], buy=4))
    got = _read(s)[20]
    pool = s.world.pool_wh.warehouse_code
    assert got.get("saved_remark") == f"USE {pool} 6 & ORDER 4", got.get("saved_remark")
    assert got["saved_remark"] == _email_words([_pool(s, 6)], buy=4)


def test_f3_order_back_reads_order_back(api):
    s = _seed(api)
    _save_draft(s, 30, _amend(buy=10, order_back=True))
    got = _read(s)[30]
    assert got.get("saved_remark") == "ORDER BACK", got.get("saved_remark")
    assert got["saved_remark"] == _email_words(buy=10, order_back=True)


def test_f3_a_line_with_no_saved_draft_has_a_null_saved_remark(api):
    s = _seed(api)
    _save_draft(s, 10, _amend([_own(s, 10)]))
    got = _read(s)[40]
    assert "saved_remark" in got, ("the field is on every line", sorted(got))
    assert got["saved_remark"] is None


def test_f3_a_line_delivered_in_full_with_a_saved_draft_is_returned_with_its_words(api):
    s = _seed(api)
    s.core[50].qty_delivered = Decimal("10")
    s.db.commit()
    _save_draft(s, 50, _amend([_own(s, 10)]))
    got = _read(s).get(50)
    assert got is not None, "a covered line delivered in full is on the read"
    assert got.get("saved_remark") == f"USE {s.world.own_wh.warehouse_code}", got.get("saved_remark")


def test_f3_a_book_cancelled_line_with_a_saved_draft_is_returned_with_its_words(api):
    s = _seed(api)
    _save_draft(s, 60, _amend([_own(s, 10)]))
    s.core[60].line_status = "cancelled"
    s.db.commit()
    got = _read(s).get(60)
    assert got is not None, "a covered book-cancelled line is on the read (it is skipped today)"
    assert got.get("saved_remark") == f"USE {s.world.own_wh.warehouse_code}", got.get("saved_remark")
