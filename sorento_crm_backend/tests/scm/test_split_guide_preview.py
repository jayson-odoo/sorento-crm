"""OI-SPLIT-GUIDE (UAC C3, C4): the Confirm dry run lists EVERY row the press changes, and says
which ones come from an AutoCount change nobody saved.

Setup (all seeded here, CI's database has no data): an order with line 10 and line 20, both
confirmed as Buy (rows raised under revision 1). Then AutoCount moves line 10 (qty and/or date,
or cancels it in the book) and the planner presses Confirm naming only line 20.

T-BE1: the dry run lists line 10's retired row (raised under the OLDER revision).
T-BE2: each row carries `state` (UAC C2); `autocount_change` is retired (UAC F9).
T-BE3 (pin): the real press writes the same OrderInquiryRow states with or without this lane.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow
from tests.scm.test_line_splits_round3 import api, world  # noqa: F401 - fixtures reused
from tests.test_planning_change_apply_on_board import _confirm
from tests.test_planning_changes import (
    BASE,
    _core_line,
    _core_so,
    _line_payload,
    _project_line,
    _project_so,
)

D_OLD = date(2026, 11, 20)
D_NEW = date(2026, 12, 18)


class _S:
    pass


def _two_line_order(api):
    """Lines 10 (qty 100) and 20 (qty 50) confirmed as Buy under revision 1."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    s = _S()
    s.client, s.world, s.db, s.core_so, s.order = client, world, db, core_so, order
    s.core, s.line = {}, {}
    for no, qty in ((10, 100), (20, 50)):
        core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=str(qty),
                          required_date=D_OLD)
        core.line_no = no
        line = _project_line(db, order, line_no=no, product=world.product, core_line=core)
        line.stock_location = world.own_wh.warehouse_code
        s.core[no], s.line[no] = core, line
    db.commit()
    r = _confirm(client, order.id, [
        _line_payload(s.line[10].id, buy_qty="100"),
        _line_payload(s.line[20].id, buy_qty="50"),
    ])
    assert r.status_code == 200, f"premise: the first Confirm saves: {r.text}"
    db.commit()
    db.expire_all()
    return s


def _drift(s, how):
    core, line = s.core[10], s.line[10]
    if how in ("qty", "qty_date"):
        core.qty_ordered, line.qty = Decimal("120"), Decimal("120")
    if how in ("date", "qty_date"):
        core.required_date, line.delivery_date = D_NEW, D_NEW
    if how == "cancelled":
        core.line_status = "cancelled"
    s.db.commit()
    s.db.expire_all()


def _press(s, *, preview, named=(20,)):
    return s.client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={
            "preview": preview,
            "orders": [{
                "pso_id": str(s.order.id),
                "lines": [_line_payload(s.line[no].id, buy_qty=str(s.core[no].qty_ordered))
                          for no in named],
            }],
        },
    )


def _press_body(s, body_extra, *, named=(), preview=True):
    entry = {
        "pso_id": str(s.order.id),
        "lines": [_line_payload(s.line[no].id, buy_qty=str(s.core[no].qty_ordered)) for no in named],
    }
    entry.update(body_extra)
    return s.client.post(
        f"{BASE}/fulfilment-planning/confirm-all", json={"preview": preview, "orders": [entry]}
    )


def _result(r):
    assert r.status_code == 200, r.text
    result = r.json()["results"][0]
    assert result["ok"] is True, result
    return result


def _rows_of(result, line_no):
    return [x for x in result["inquiry_rows"] if x["line_no"] == line_no]


def _written(s):
    """The FULL set of OrderInquiryRow the order holds, by line number (ids differ between
    orders): verb, state, qty, date, note."""
    s.db.expire_all()
    no_of = {str(s.line[no].id): no for no in s.line}
    return sorted(
        (no_of[str(r.so_line_id)], r.verb, r.state, str(r.qty), str(r.delivery_date), r.note or "")
        for r in s.db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id.in_(list(no_of)))
    )


# ---------------------------------------------------------------------------
# T-BE1 (UAC C3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("how", ["qty", "date", "qty_date", "cancelled"])
def test_be1_the_dry_run_lists_the_retired_row_of_an_unnamed_line_autocount_moved(api, how):
    s = _two_line_order(api)
    _drift(s, how)
    result = _result(_press(s, preview=True))
    rows = _rows_of(result, 10)
    assert rows, (
        "UAC C3: the retired row of line 10 (raised under the older revision) is listed",
        result["inquiry_rows"],
    )
    assert [x.get("state") for x in rows] == ["cancelled"] * len(rows), (
        "each preview row carries the state it has after the press (INQUIRY_CANCELLED)", rows,
    )


def test_be1_the_real_press_does_retire_that_row_pin(api):
    """Premise of T-BE1: the press really cancels line 10's raised row (green today)."""
    s = _two_line_order(api)
    _drift(s, "qty")
    _result(_press(s, preview=False))
    s.db.commit()
    s.db.expire_all()
    row = s.db.query(OrderInquiryRow).filter(
        OrderInquiryRow.so_line_id == s.line[10].id
    ).one()
    assert row.state == INQUIRY_CANCELLED, row.state


# ---------------------------------------------------------------------------
# T-BE2 (UAC C4)
# ---------------------------------------------------------------------------


def test_be2_a_saved_split_edit_row_reads_raised(api):
    """A split edit is added server-side (`_with_split_edits`): its new row reads `raised` and
    the old one it replaces is listed too."""
    from tests.scm.test_line_splits_api import _put, _sp

    s = _two_line_order(api)
    r = _put(s, [{"line_id": str(s.line[20].id), "splits": [
        _sp(30, D_OLD, on=str(s.line[20].id)),
        _sp(20, D_NEW, on=None),
    ]}])
    assert r.status_code == 200, f"premise: the split saves ({r.status_code}) {r.text}"
    result = _result(_press(s, preview=True, named=()))
    rows = _rows_of(result, 20)
    new = [x for x in rows if x["is_new"]]
    assert new, ("premise: the split edit raises a new row", rows)
    assert all(x.get("state") == "raised" for x in new), ("a row this press raised reads raised", new)


# ---------------------------------------------------------------------------
# T-BE3 pin (no behaviour change)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("how", ["qty", "date", "cancelled"])
def test_be3_the_real_press_writes_the_same_rows_with_or_without_a_dry_run_before_it(api, how):
    """Two identical orders: one is previewed and then pressed, the other only pressed. The full
    set of rows (every line, verb, state, qty, date, note) is the same, so the dry run and this
    lane's preview fix change nothing the real press writes."""
    plain = _two_line_order(api)
    previewed = _two_line_order(api)
    for s in (plain, previewed):
        _drift(s, how)
    _result(_press(previewed, preview=True))
    dry_state = _written(previewed)
    _result(_press(plain, preview=False))
    _result(_press(previewed, preview=False))
    for s in (plain, previewed):
        s.db.commit()
    after = _written(previewed)
    assert after == _written(plain), (after, _written(plain))
    assert dry_state != after, "the real press moved rows the dry run left alone"
    line10 = [x for x in after if x[0] == 10]
    assert line10 and all(x[2] == INQUIRY_CANCELLED for x in line10), line10
    assert {x[0] for x in after} == {10, 20}


# ---------------------------------------------------------------------------
# C2a: the line number a person reads is AutoCount's, not the planning address
# ---------------------------------------------------------------------------


def test_c2a_preview_rows_carry_the_core_line_number_as_so_line_no(api):
    """Mirror (planning) line 560 sits on core (AutoCount) line 480: the row keeps `line_no`
    560 and says `so_line_no` 480. Transfers are not covered here: raising one needs seeded
    stock, and rows share the one builder rule."""
    s = _two_line_order(api)
    s.line[10].line_no, s.core[10].line_no = 560, 480
    s.db.commit()
    s.db.expire_all()
    _drift(s, "qty")
    result = _result(_press(s, preview=True))
    rows = _rows_of(result, 560)
    assert rows, ("premise: line 10's retired row is listed under its planning line_no", result["inquiry_rows"])
    assert all(x.get("so_line_no") == 480 for x in rows), rows


def test_c2a_a_row_of_a_line_without_a_core_line_falls_back_to_the_mirror_number(api):
    s = _two_line_order(api)
    s.line[10].line_no = 560
    s.line[10].core_sales_order_line_id = None
    s.db.commit()
    s.db.expire_all()
    result = _result(_press_body(s, {}, named=(20,)))
    rows = _rows_of(result, 560)
    assert rows, ("premise: line 10's row is listed under its planning line_no", result["inquiry_rows"])
    assert all(x.get("so_line_no") == 560 for x in rows), rows
