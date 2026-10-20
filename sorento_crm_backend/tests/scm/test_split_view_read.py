"""OI-SPLIT-VIEW section B (UAC B2 to B5, B7): `split_view` on every read of a split line.

One serializer feeds four reads and they must agree: the OI header-lines rows
(`ProjectOrderInquiryService.serialize_rows`, `OrderInquiryRowOut.split_view`), the OI worklist
list (GET /order-inquiries), the SCM sales order (GET /scm/sales-orders/{id}, per line) and the
split sheet read (GET /project-sales/sales-orders/{pso}/line-splits, `LineSplitLineOut`).

Red until the build: no read carries `split_view` yet. The owner's SO417636 seed is #1749's
(`test_line_splits_round3`); 480 is the 480-like line and 752 the 752-like one.
"""
from __future__ import annotations

from datetime import date

import pytest

from tests.scm.test_line_splits_api import _put, _sp, _url
from tests.test_planning_changes import BASE
from tests.scm.test_line_splits_round3 import (  # noqa: F401 - fixtures reused
    D_167,
    D_167_EDIT,
    D_480_NEW,
    D_608,
    D_752_NEW,
    OWNER_CASE,
    _build,
    _change,
    _confirm_batch,
    _edit_480,
    _line_payload,
    _new_line_plan_applied,
    _on,
    _save,
    _seed,
    _today_candidates,
    api,
    emails,
    world,
)

D_480 = date(2026, 10, 20)
D_752 = date(2026, 12, 20)

#: 480: 14 own + 236 and 167 on New line; 752: 37 own + 467 on New line (extra 145).
PLAN_480_752 = {
    480: [(14, D_480_NEW, 480, ""), (236, D_608, "new", ""), (167, D_167, "new", "")],
    752: [(37, D_608, 752, ""), (467, D_752_NEW, "new", "")],
}


# ---------------------------------------------------------------------------
# the four reads
# ---------------------------------------------------------------------------


def _any_row(s, no):
    from app.models.project_so import OrderInquiryRow

    row = (
        s.db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == s.line[no].id)
        .order_by(OrderInquiryRow.created_at.asc())
        .first()
    )
    assert row is not None, f"premise: line {no} has an OI row"
    return row


def _views(s, no):
    """`split_view` of line `no` as each of the four reads carries it (the key must exist)."""
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    s.db.expire_all()
    row = _any_row(s, no)
    out = {}

    serial = ProjectOrderInquiryService(s.db).serialize_rows([row])[0]
    assert "split_view" in serial, ("OrderInquiryRowOut.split_view", sorted(serial))
    out["oi_rows"] = serial["split_view"]

    listed = s.client.get(f"{BASE}/order-inquiries", params={"query": s.core_so.so_number})
    assert listed.status_code == 200, listed.text
    got = {r["id"]: r for r in listed.json()["data"]}[str(row.id)]
    assert "split_view" in got, ("the worklist row carries split_view", sorted(got))
    out["worklist"] = got["split_view"]

    so = s.client.get(f"/api/v1/scm/sales-orders/{s.core_so.id}")
    assert so.status_code == 200, so.text
    line = {ln["id"]: ln for ln in so.json()["lines"]}[str(s.core[no].id)]
    assert "split_view" in line, ("SalesOrderLine.split_view", sorted(line))
    out["scm_so"] = line["split_view"]

    sheet = s.client.get(_url(s.order.id))
    assert sheet.status_code == 200, sheet.text
    mine = {ln["line_id"]: ln for ln in sheet.json()["lines"]}[_on(s, no)]
    assert "split_view" in mine, ("LineSplitLineOut.split_view", sorted(mine))
    out["line_splits"] = mine["split_view"]
    return out


def _one(views):
    """The four reads are the same value; return it."""
    first = views["oi_rows"]
    for name, value in views.items():
        assert value == first, (f"{name} differs from oi_rows", value, first)
    return first


def _row_tuple(r):
    return (r["qty"], r["delivery_date"], r["change"], r["sits_on"], r["sits_on_line_no"])


def _confirmed_world(api, emails):
    s = _seed(api)
    _save(s, PLAN_480_752)
    _confirm_batch(s, emails)
    return s


# ---------------------------------------------------------------------------
# B2 / B3 / B5: values and one source
# ---------------------------------------------------------------------------


def test_b2_the_480_like_line_reads_its_rows_in_seq_order_the_same_on_every_read(api, emails):
    s = _confirmed_world(api, emails)
    view = _one(_views(s, 480))
    assert [_row_tuple(r) for r in view["rows"]] == [
        ("14", "2026-09-20", "ADVANCE", "own", 480),
        ("236", "2026-11-20", "DELAY", "new", None),
        ("167", "2029-11-20", "DELAY", "new", None),
    ], view["rows"]
    assert (view["base_qty"], view["base_date"]) == ("417", "2026-10-20")
    assert (view["now_qty"], view["now_date"]) == ("14", "2026-09-20")
    assert view["total_qty"] == "417"
    for r in view["rows"]:
        assert set(r) >= {"qty", "delivery_date", "change", "sits_on", "sits_on_line_no", "remark",
                          "is_cancel", "changed", "was_qty", "was_date"}, sorted(r)
        assert r["is_cancel"] is False and r["changed"] is False
        assert r["was_qty"] is None and r["was_date"] is None


def test_b2_the_752_like_line_ends_with_the_autocount_extra_row(api, emails):
    s = _confirmed_world(api, emails)
    view = _one(_views(s, 752))
    assert [_row_tuple(r) for r in view["rows"]] == [
        ("37", "2026-11-20", "ADVANCE", "own", 752),
        ("467", "2027-01-02", "DELAY", "new", None),
        ("145", "2027-01-02", "ORDER 145", "extra", 752),
    ], view["rows"]
    assert (view["base_qty"], view["base_date"]) == ("504", "2026-12-20")
    assert (view["now_qty"], view["now_date"]) == ("649", "2027-01-02")
    assert view["total_qty"] == "649"


def test_b2_an_unsplit_line_has_a_null_split_view_on_every_read(api, emails):
    s = _confirmed_world(api, emails)
    views = _views(s, 608)
    assert views == {k: None for k in ("oi_rows", "worklist", "scm_so", "line_splits")}, views


def test_b6_a_split_sitting_on_another_line_is_listed_on_its_own_line_only(api, emails):
    """Q4 (a): 480's 236 sits on 608; it reads `line 608` in 480's rows and 608 (unsplit)
    shows nothing."""
    s = _seed(api)
    _save(s, {480: [(14, D_480_NEW, 480, ""), (236, D_608, 608, ""), (167, D_167, 608, "")]})
    _confirm_batch(s, emails)
    view = _one(_views(s, 480))
    assert [_row_tuple(r) for r in view["rows"]] == [
        ("14", "2026-09-20", "ADVANCE", "own", 480),
        ("236", "2026-11-20", "DELAY", "line", 608),
        ("167", "2029-11-20", "DELAY", "line", 608),
    ], view["rows"]
    assert set(_views(s, 608).values()) == {None}


# ---------------------------------------------------------------------------
# B3: status
# ---------------------------------------------------------------------------


def test_b3_a_confirmed_plan_reads_confirmed_with_its_revision_and_date(api, emails):
    s = _confirmed_world(api, emails)
    view = _one(_views(s, 480))
    assert view["status"] == "confirmed", view["status"]
    assert view["revision_no"] == 2, "the batch Confirm is the order's second decision"
    assert view["confirmed_on"] in _today_candidates(), view["confirmed_on"]


def test_b3_an_edit_after_the_confirm_reads_saved_not_confirmed(api, emails):
    s, _po = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", ""), (167, D_167_EDIT, "new", "")])
    view = _one(_views(s, 480))
    assert view["status"] == "saved", view["status"]


def test_b3_a_remark_only_edit_stays_confirmed(api, emails):
    s, _po = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", "SITE HOLD"), (167, D_167, "new", "")])
    view = _one(_views(s, 480))
    assert view["status"] == "confirmed", view["status"]
    assert [r["remark"] for r in view["rows"]] == ["", "SITE HOLD", ""]


def test_b3_a_newer_autocount_change_reads_autocount_changed(api, emails):
    from decimal import Decimal

    from app.services.scm.outstanding_diff import QTY_CHANGED

    s, _po = _new_line_plan_applied(api, emails)
    core = s.core[480]
    core.qty_ordered, s.line[480].qty = Decimal("20"), Decimal("20")
    s.db.commit()
    batch = _build(s.world, [_change(QTY_CHANGED, core, so_number=s.core_so.so_number,
                                     old_date=D_480_NEW, new_date=D_480_NEW, old_qty="14",
                                     new_qty="20")], s.core_so, [str(core.id)])
    assert batch is not None, "premise: the AutoCount change is pending"
    view = _one(_views(s, 480))
    assert view["status"] == "autocount_changed", view["status"]


# ---------------------------------------------------------------------------
# B4: what changed, only when exact
# ---------------------------------------------------------------------------


def test_b4_a_one_row_edit_marks_that_row_and_names_what_it_was(api, emails):
    s, _po = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", ""), (167, D_167_EDIT, "new", "")])
    view = _one(_views(s, 480))
    changed = [r for r in view["rows"] if r["changed"]]
    assert [(r["qty"], r["delivery_date"]) for r in changed] == [("167", "2029-12-20")], view["rows"]
    assert changed[0]["was_date"] == "2029-11-20", changed[0]
    assert changed[0]["was_qty"] is None, "only the value that differs is told"
    assert all(r["was_qty"] is None and r["was_date"] is None for r in view["rows"] if not r["changed"])


def test_b4_a_two_row_edit_marks_the_new_rows_and_never_guesses_a_was(api, emails):
    from datetime import date as _d

    s, _po = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (200, D_608, "new", ""), (36, _d(2030, 1, 20), "new", ""),
                  (167, D_167, "new", "")])
    view = _one(_views(s, 480))
    assert view["status"] == "saved"
    assert sorted((r["qty"], r["changed"]) for r in view["rows"]) == [
        ("14", False), ("167", False), ("200", True), ("36", True)], view["rows"]
    assert all(r["was_qty"] is None and r["was_date"] is None for r in view["rows"]), view["rows"]


def test_b4_nothing_is_marked_on_a_confirmed_plan(api, emails):
    s, _po = _new_line_plan_applied(api, emails)
    view = _one(_views(s, 480))
    assert view["status"] == "confirmed"
    assert not [r for r in view["rows"] if r["changed"]], view["rows"]


# ---------------------------------------------------------------------------
# Review round 1: B3 partly-from-stock line, B7 access
# ---------------------------------------------------------------------------


def test_r2_b3_a_line_partly_from_stock_reads_confirmed_right_after_its_confirm(api, emails):
    from tests.test_so_supply_confirmation import _stock
    from tests.scm.test_line_splits_round3 import _new_line_plan

    _client, world_ = api
    _stock(world_.db, world_.product, world_.pool_wh, on_hand=50)
    world_.db.commit()
    s = _seed(api)
    _save(s, _new_line_plan())
    from tests.test_planning_change_apply_on_board import _confirm
    r = _confirm(s.client, s.order.id, [
        _line_payload(s.line[480].id, reserve=[{"warehouse_id": s.world.pool_wh.id, "qty": "4"}],
                      buy_qty="10", amend_reason="Part from the pool."),
        _line_payload(s.line[608].id, buy_qty="632"),
        _line_payload(s.line[752].id, buy_qty="649"),
    ], batch_id=str(s.batch.id))
    assert r.status_code == 200, r.text
    s.db.commit()
    s.db.expire_all()
    sheet = s.client.get(_url(s.order.id)).json()
    view = {ln["line_id"]: ln for ln in sheet["lines"]}[_on(s, 480)].get("split_view")
    assert view is not None, "split_view is on the sheet read"
    assert view["status"] == "confirmed", view["status"]
    assert not [r for r in view["rows"] if r["changed"]], view["rows"]


def test_b7_a_user_of_another_company_cannot_read_the_sales_order_or_its_split_view(api, emails):
    """Pin (may pass today): the SCM SO read of a foreign company's order answers 404."""
    from app.models.base import company_scope

    s = _seed(api)
    _save(s, PLAN_480_752)
    other = "00000000-0000-0000-0000-00000000dead"
    with company_scope(s.db, frozenset({other})):
        r = s.client.get(f"/api/v1/scm/sales-orders/{s.core_so.id}")
    assert r.status_code == 404, (r.status_code, r.text[:200])


# ---------------------------------------------------------------------------
# Review round 2, B3: the pending-line ruling and the precedence
# ---------------------------------------------------------------------------

D_32 = date(2026, 12, 20)
D_32_EDIT = date(2027, 1, 20)


def _pending_growth_608(api, emails):
    """608 with an applied plan 600 + 32, AutoCount 632 -> 700 pending, the 32's date edited."""
    from decimal import Decimal

    from app.services.scm.outstanding_diff import QTY_CHANGED
    from tests.scm.test_line_splits_round3 import _reconfirm

    s, _po = _new_line_plan_applied(api, emails)
    _save(s, {608: [(600, D_608, 608, ""), (32, D_32, "new", "")]})
    _reconfirm(s)
    core = s.core[608]
    core.qty_ordered, s.line[608].qty = Decimal("700"), Decimal("700")
    s.db.commit()
    s.batch = _build(s.world, [_change(QTY_CHANGED, core, so_number=s.core_so.so_number,
                                       old_date=D_608, new_date=D_608, old_qty="632",
                                       new_qty="700")], s.core_so, [str(core.id)])
    assert s.batch is not None, "premise: the AutoCount change is pending"
    r = _put(s, [{"line_id": _on(s, 608), "splits": [
        _sp(600, D_608, on=_on(s, 608)), _sp(32, D_32_EDIT, on=None)]}])
    assert r.status_code == 200, ("premise: the edit saves", r.text)
    return s


def test_r2_b3_a_pending_autocount_line_with_an_edited_32_reads_saved_and_marks_the_row(api, emails):
    s = _pending_growth_608(api, emails)
    view = _one(_views(s, 608))
    assert view["status"] == "saved", ("lead ruling: saved, not confirmed", view["status"])
    changed = [r for r in view["rows"] if r["changed"]]
    assert [(r["qty"], r["delivery_date"]) for r in changed] == [("32", "2027-01-20")], view["rows"]
    assert changed[0]["was_date"] == "2026-12-20", changed[0]
    assert changed[0]["was_qty"] is None


def test_r2_b3_the_board_flag_of_that_line_stays_false(api, emails):
    from tests.scm.test_split_view_board import _board_flag

    s = _pending_growth_608(api, emails)
    assert _board_flag(s, 608) is False, "A9: the board counts the line once, for its AutoCount change"


def test_r2_b3_a_stale_plan_reads_autocount_changed_even_when_it_is_edited(api, emails):
    from decimal import Decimal

    from app.services.scm.outstanding_diff import QTY_CHANGED

    s, _po = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", ""), (167, D_167_EDIT, "new", "")])
    core = s.core[480]
    core.qty_ordered, s.line[480].qty = Decimal("20"), Decimal("20")
    s.db.commit()
    batch = _build(s.world, [_change(QTY_CHANGED, core, so_number=s.core_so.so_number,
                                     old_date=D_480_NEW, new_date=D_480_NEW, old_qty="14",
                                     new_qty="20")], s.core_so, [str(core.id)])
    assert batch is not None, "premise: the AutoCount change is pending"
    view = _one(_views(s, 480))
    assert view["status"] == "autocount_changed", ("precedence: AutoCount changed first", view["status"])


# ---------------------------------------------------------------------------
# Review round 4, E5: the SCM sales order carries the split sheet's payload
# ---------------------------------------------------------------------------


def test_r4_e5_the_sales_order_read_carries_line_splits_equal_to_the_sheet_read(api, emails):
    s = _confirmed_world(api, emails)
    so = s.client.get(f"/api/v1/scm/sales-orders/{s.core_so.id}")
    assert so.status_code == 200, so.text
    sheet = s.client.get(_url(s.order.id))
    assert sheet.status_code == 200, sheet.text
    body = so.json()
    assert "line_splits" in body, ("SalesOrder.line_splits is on the wire", sorted(body))
    got = body["line_splits"]
    assert got is not None, "the order has splits, so the payload is there"
    assert set(got) == set(sheet.json()), (sorted(got), sorted(sheet.json()))
    assert got == sheet.json()
    assert {"pso_id", "so_number", "lines"} <= set(got)
    split_lines = [ln for ln in got["lines"] if ln["splits"]]
    assert sorted(ln["line_no"] for ln in split_lines) == [480, 752]


def test_r4_e5_an_order_without_splits_has_no_line_splits(api, emails):
    s = _seed(api)
    so = s.client.get(f"/api/v1/scm/sales-orders/{s.core_so.id}")
    assert so.status_code == 200, so.text
    body = so.json()
    assert body.get("line_splits") is None, "null or absent when nothing is split (pins today)"
