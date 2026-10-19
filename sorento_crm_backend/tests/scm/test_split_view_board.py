"""OI-SPLIT-VIEW section A (UAC A1 to A7): saved split edits are confirmed from the board.

Red until the build: `split_plan_edited` does not exist, `BoardContribution.split_edited` is not
on the wire, and Confirm / Simulate confirm ignore a split-edited line the body does not name.
The owner's SO417636 seed and the confirm helpers are #1749's (`test_line_splits_round3`); every
row is seeded here (CI's database has no data).

`test_a6_*` pins behaviour that already holds today (AC-G19 Save guard) and is green now.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tests.scm.test_line_splits_api import _put, _sp
from tests.test_planning_changes import BASE
from tests.scm.test_line_splits_round3 import (  # noqa: F401 - fixtures reused
    D_167,
    D_167_EDIT,
    D_36,
    D_480_NEW,
    D_608,
    OWNER_CASE,
    _confirm,
    _d,
    _edit_480,
    _excel_rows,
    _line_payload,
    _new_line_plan_applied,
    _on,
    _reconfirm,
    _rows_with_links,
    _save,
    _seed,
    _sent_since,
    _worklist,
    api,
    emails,
    world,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _board_flag(s, no):
    """`split_edited` of line `no` on the board payload (the key must be there)."""
    r = s.client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": s.core_so.so_number, "granularity": "week"},
    )
    assert r.status_code == 200, r.text
    found = [c for c in r.json()["contributions"] if c.get("project_line_id") == _on(s, no)]
    assert found, (f"premise: line {no} is on the board", r.json()["contributions"])
    assert "split_edited" in found[0], ("BoardContribution.split_edited is on the wire", sorted(found[0]))
    return found[0]["split_edited"]


def _unsplit_confirmed_608(s, emails):
    """A line that is confirmed and has no splits: 608 after the owner's batch Confirm."""
    from tests.scm.test_line_splits_round3 import _confirm_batch

    _confirm_batch(s, emails)


def _confirm_empty(s, lines=None):
    r = _confirm(s.client, s.order.id, lines if lines is not None else [])
    assert r.status_code == 200, ("Confirm with no lines of its own is accepted", r.status_code, r.text)
    s.db.commit()
    s.db.expire_all()
    return r


def _snapshot(s):
    from app.models.project_so import OrderInquiryRow, SOSupplyDecision

    s.db.expire_all()
    rows = s.db.query(OrderInquiryRow).filter(
        OrderInquiryRow.so_line_id.in_([str(s.line[no].id) for no in OWNER_CASE])
    ).count()
    decisions = s.db.query(SOSupplyDecision).filter(
        SOSupplyDecision.project_sales_order_id == str(s.order.id)
    ).count()
    return rows, decisions


# ---------------------------------------------------------------------------
# A1: the one function
# ---------------------------------------------------------------------------


def _split(qty, when, on, *, cancel=False):
    return SimpleNamespace(
        base_qty=Decimal("417"), base_date=date(2026, 10, 20), qty=Decimal(qty),
        delivery_date=None if cancel else when, sits_on_line_id=on, is_cancel=cancel, remark="",
    )


def _plan_of(splits):
    from app.services.project_order_inquiry_service import split_plan_key

    return split_plan_key(splits)


def test_a1_split_plan_edited_is_false_when_the_saved_plan_is_the_applied_one():
    from app.services.project_line_split_service import split_plan_edited

    saved = [_split(14, D_480_NEW, "L"), _split(236, D_608, None)]
    assert split_plan_edited(saved, _plan_of(saved)) is False


def test_a1_split_plan_edited_ignores_a_remark():
    from app.services.project_line_split_service import split_plan_edited

    saved = [_split(14, D_480_NEW, "L"), _split(236, D_608, None)]
    applied = _plan_of(saved)
    saved[1].remark = "SITE HOLD"
    assert split_plan_edited(saved, applied) is False


def test_a1_split_plan_edited_ignores_the_order_of_the_splits():
    from app.services.project_line_split_service import split_plan_edited

    saved = [_split(14, D_480_NEW, "L"), _split(236, D_608, None)]
    assert split_plan_edited(list(reversed(saved)), _plan_of(saved)) is False


def test_a1_split_plan_edited_is_true_when_a_date_or_a_qty_differs():
    from app.services.project_line_split_service import split_plan_edited

    saved = [_split(14, D_480_NEW, "L"), _split(236, D_608, None)]
    applied = _plan_of(saved)
    assert split_plan_edited([saved[0], _split(236, D_167_EDIT, None)], applied) is True
    assert split_plan_edited([saved[0], _split(200, D_608, None)], applied) is True


def test_a1_split_plan_edited_is_true_when_nothing_was_applied_yet_and_false_with_no_splits():
    from app.services.project_line_split_service import split_plan_edited

    saved = [_split(14, D_480_NEW, "L")]
    assert split_plan_edited(saved, None) is True
    assert split_plan_edited(saved, []) is True
    assert split_plan_edited([], None) is False
    assert split_plan_edited([], ["417@2026-10-20"]) is False


# ---------------------------------------------------------------------------
# A2: the board flag
# ---------------------------------------------------------------------------


def test_a2_the_applied_new_line_plan_is_not_split_edited(api, emails):
    s, _po = _new_line_plan_applied(api, emails)
    assert _board_flag(s, 480) is False


def test_a2_a_date_edit_of_167_marks_the_line(api, emails):
    s, _po = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", ""), (167, D_167_EDIT, "new", "")])
    assert _board_flag(s, 480) is True


def test_a2_a_remark_only_edit_does_not_mark_the_line(api, emails):
    s, _po = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", "SITE HOLD"), (167, D_167, "new", "")])
    assert _board_flag(s, 480) is False


def test_a2_editing_167_back_to_its_applied_date_clears_the_mark(api, emails):
    s, _po = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", ""), (167, D_167_EDIT, "new", "")])
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", ""), (167, D_167, "new", "")])
    assert _board_flag(s, 480) is False


def test_a2_a_first_split_on_a_confirmed_unsplit_line_marks_it(api, emails):
    s = _seed(api)
    _unsplit_confirmed_608(s, emails)
    _save(s, {608: [(600, D_608, 608, ""), (32, date(2026, 12, 20), "new", "")]})
    assert _board_flag(s, 608) is True


def test_a2_a_line_delivered_in_full_is_never_marked(api, emails):
    from decimal import Decimal as D

    s, _po = _new_line_plan_applied(api, emails)
    assert _board_flag(s, 480) is False, "premise: the key is on the wire"
    core = s.core[752]
    core.qty_delivered = core.qty_ordered
    s.db.commit()
    r = s.client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": s.core_so.so_number, "granularity": "week"},
    )
    assert r.status_code == 200, r.text
    for c in r.json()["contributions"]:
        if c.get("project_line_id") == _on(s, 752):
            assert c.get("split_edited") is False, c


# ---------------------------------------------------------------------------
# A4: Confirm acts on every split-edited line of the order
# ---------------------------------------------------------------------------


def test_a4_confirm_with_no_lines_applies_the_167_edit(api, emails):
    s, po_line = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", ""), (167, D_167_EDIT, "new", "")])
    start = len(emails)
    _confirm_empty(s)

    got = _rows_with_links(s, po_line)
    assert got == {
        (_d("14"), D_480_NEW): _d("14"), (_d("236"), D_608): _d("236"),
        (_d("167"), D_167_EDIT): _d("167"),
    }, ("the 167 row moves to its new date with its link", got)
    sent = _sent_since(emails, start)
    moved = [ln for ln in sent if ln["qty"] == "167"]
    assert len(moved) == 1 and moved[0]["delivery_date"] == "20/12/2029", sent
    assert str(moved[0]["remark"]).startswith("DELAY"), moved[0]["remark"]
    assert [ln["qty"] for ln in sent if ln["qty"] in ("14", "236")] == [], ("only the 167 is told", sent)
    xl = _excel_rows(s)
    assert [r for r in xl if r[2] == _d("167") and r[3] == D_167_EDIT], ("Excel 167 moved", xl)


def test_a4_confirm_naming_only_other_lines_still_applies_the_167_edit(api, emails):
    s, po_line = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", ""), (167, D_167_EDIT, "new", "")])
    start = len(emails)
    _confirm_empty(s, [_line_payload(s.line[752].id, buy_qty="649")])
    assert (_d("167"), D_167_EDIT) in _rows_with_links(s, po_line), _rows_with_links(s, po_line)
    assert len([ln for ln in _sent_since(emails, start) if ln["qty"] == "167"]) == 1


def test_a4_after_the_confirm_the_flag_is_false_and_a_second_confirm_writes_nothing(api, emails):
    s, po_line = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", ""), (167, D_167_EDIT, "new", "")])
    _confirm_empty(s)
    assert _board_flag(s, 480) is False, "the new decision's stamp equals the saved plan"
    before = (_snapshot(s), sorted(_worklist(s, s.line[480]), key=str))
    start = len(emails)
    r = _confirm(s.client, s.order.id, [])
    assert r.status_code in (200, 400, 409, 422), r.text
    s.db.commit()
    s.db.expire_all()
    assert _sent_since(emails, start) == []
    assert (_snapshot(s), sorted(_worklist(s, s.line[480]), key=str)) == before


def test_a4_a_qty_edit_writes_rows_200_and_36_each_linked_and_no_cancel(api, emails):
    from app.models.project_so import IV_CANCEL_BALANCE, OrderInquiryRow

    s, po_line = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (200, D_608, "new", ""), (36, D_36, "new", ""),
                  (167, D_167, "new", "")])
    start = len(emails)
    _confirm_empty(s)
    assert _rows_with_links(s, po_line) == {
        (_d("14"), D_480_NEW): _d("14"), (_d("200"), D_608): _d("200"),
        (_d("36"), D_36): _d("36"), (_d("167"), D_167): _d("167"),
    }, _rows_with_links(s, po_line)
    sent = [(ln["qty"], ln["delivery_date"]) for ln in _sent_since(emails, start)]
    assert ("200", "20/11/2026") in sent and ("36", "20/01/2030") in sent, sent
    assert not [ln for ln in _sent_since(emails, start) if "CANCEL" in str(ln["remark"])]
    xl = _excel_rows(s)
    assert [r for r in xl if r[2] == _d("200")] and [r for r in xl if r[2] == _d("36")], xl
    assert not [r for r in xl if r[2] == _d("236")], xl
    assert not s.db.query(OrderInquiryRow).filter(
        OrderInquiryRow.so_line_id == s.line[480].id, OrderInquiryRow.verb == IV_CANCEL_BALANCE
    ).count()


def test_a4_confirm_all_applies_the_edit_of_an_order_that_names_no_line(api, emails):
    s, po_line = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", ""), (167, D_167_EDIT, "new", "")])
    r = s.client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={"orders": [{"pso_id": str(s.order.id), "lines": []}]},
    )
    assert r.status_code == 200, r.text
    result = r.json()["results"][0]
    assert result["ok"] is True, result
    s.db.commit()
    s.db.expire_all()
    assert (_d("167"), D_167_EDIT) in _rows_with_links(s, po_line), _rows_with_links(s, po_line)


# ---------------------------------------------------------------------------
# A5: Simulate confirm
# ---------------------------------------------------------------------------


def test_a5_simulate_confirm_with_no_lines_reports_the_change_and_writes_nothing(api, emails, monkeypatch):
    from tests.test_fulfilment_simulate_confirm import _as_role

    _as_role(monkeypatch, "admin")
    s, po_line = _new_line_plan_applied(api, emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", ""), (167, D_167_EDIT, "new", "")])
    before = (_snapshot(s), sorted(_worklist(s, s.line[480]), key=str))
    start = len(emails)
    r = s.client.post(
        f"{BASE}/fulfilment-planning/simulate-confirm",
        json={"orders": [{"pso_id": str(s.order.id), "lines": []}]},
    )
    assert r.status_code == 200, r.text
    result = r.json()["results"][0]
    assert result["ok"] is True, result
    rows = result.get("inquiry_rows") or []
    assert [x for x in rows if Decimal(str(x["qty"])) == 167 and x["delivery_date"] == D_167_EDIT.isoformat()], (
        "the simulation reports the 167 moving to 20/12/2029", rows)
    s.db.expire_all()
    assert (_snapshot(s), sorted(_worklist(s, s.line[480]), key=str)) == before
    assert _sent_since(emails, start) == []


# ---------------------------------------------------------------------------
# A6: the Save guard (pins today's behaviour, green now)
# ---------------------------------------------------------------------------


def test_a6_moving_a_confirmed_split_onto_another_line_is_still_refused(api, emails):
    """AC-G19 stays deferred: the Save answers 422 and stores nothing."""
    from tests.scm.test_line_splits_round3 import _confirm_batch

    s = _seed(api)
    _save(s, {480: [(14, D_480_NEW, 480, ""), (236, D_608, 608, ""), (167, D_167, 608, "")]})
    _confirm_batch(s, emails)
    r = _put(s, [{"line_id": _on(s, 480), "splits": [
        _sp(14, D_480_NEW, on=_on(s, 480)), _sp(236, D_608, on=_on(s, 752)),
        _sp(167, D_167, on=_on(s, 608))]}])
    assert r.status_code == 422, (r.status_code, r.text)
    assert "a confirmed split cannot move to another line" in r.text


# ---------------------------------------------------------------------------
# Review round 1, A9: a line with a pending AutoCount change goes the AutoCount way
# ---------------------------------------------------------------------------

D_32 = date(2026, 12, 20)
D_32_EDIT = date(2027, 1, 20)


def _pending_growth_608(api, emails):
    """608 with an applied plan 600 + 32, AutoCount 632 -> 700 pending, the 32's date edited."""
    from app.services.scm.outstanding_diff import QTY_CHANGED
    from tests.scm.test_line_splits_round3 import _build, _change

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


def test_r1a_a9_the_batch_confirm_emails_what_main_emails_600_remain_and_68_order(api, emails):
    s = _pending_growth_608(api, emails)
    start = len(emails)
    r = _confirm(s.client, s.order.id, [_line_payload(s.line[608].id, buy_qty="700")],
                 batch_id=str(s.batch.id))
    assert r.status_code == 200, r.text
    s.db.commit()
    s.db.expire_all()
    sent = [(ln["qty"], str(ln["remark"])) for ln in _sent_since(emails, start)]
    assert [x for x in sent if x[0] == "600" and "REMAIN" in x[1]], ("600 REMAIN", sent)
    assert [x for x in sent if x[0] == "68" and "ORDER 68" in x[1]], ("68 ORDER 68", sent)


def test_r1b_a9_a_confirm_naming_only_line_752_answers_200_despite_the_pending_608(api, emails):
    s = _pending_growth_608(api, emails)
    r = _confirm(s.client, s.order.id, [_line_payload(s.line[752].id, buy_qty="649")])
    assert r.status_code == 200, (r.status_code, r.text)


def test_r1c_a9_a_line_with_a_pending_autocount_change_is_not_split_edited(api, emails):
    s = _pending_growth_608(api, emails)
    assert _board_flag(s, 608) is False


# ---------------------------------------------------------------------------
# Review round 2, A11: a held-back line stays held back
# ---------------------------------------------------------------------------


def _split_edited_608(api, emails):
    """608 plan 600 + 32 applied, 100 delivered, then edited to 500 + 32 (so the flag is on)."""
    s, _po = _new_line_plan_applied(api, emails)
    _save(s, {608: [(600, D_608, 608, ""), (32, D_32, "new", "")]})
    _reconfirm(s)
    s.core[608].qty_delivered = Decimal("100")
    s.db.commit()
    r = _put(s, [{"line_id": _on(s, 608), "splits": [
        _sp(500, D_608, on=_on(s, 608)), _sp(32, D_32, on=None)]}])
    assert r.status_code == 200, ("premise: the edit saves", r.text)
    assert _board_flag(s, 608) is True, "premise: 608 is split-edited"
    return s


def _line_nos(s, rows):
    names = {str(s.line[n].id): n for n in OWNER_CASE}
    return [names.get(x.get("project_line_id")) for x in rows or []]


def _rows_of(s, no):
    from app.models.project_so import OrderInquiryRow

    s.db.expire_all()
    return sorted(
        (str(r.id), r.verb, str(r.qty), r.delivery_date)
        for r in s.db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == s.line[no].id).all()
    )


def test_r2_a11_a_named_split_edited_line_the_server_refuses_is_held_back_only(api, emails):
    s = _split_edited_608(api, emails)
    before = _rows_of(s, 608)
    start = len(emails)
    r = _confirm(s.client, s.order.id, [_line_payload(s.line[608].id, buy_qty="532"),
                                        _line_payload(s.line[752].id, buy_qty="649")])
    assert r.status_code == 200, (r.status_code, r.text)
    body = r.json()
    held = [h.get("line_no") for h in body.get("lines_held_back") or []]
    assert 608 in held, ("608 is held back", body.get("lines_held_back"))
    assert 608 not in _line_nos(s, body.get("lines_confirmed")), ("608 is not confirmed", body["lines_confirmed"])
    s.db.commit()
    assert _rows_of(s, 608) == before, "no OI row change for the held-back line"
    assert [ln for ln in _sent_since(emails, start) if ln["qty"] in ("500", "532", "32")] == [], (
        "no email for the held-back line", _sent_since(emails, start))


def test_r2_a11_an_unnamed_split_edited_line_that_fails_the_check_never_makes_the_confirm_422(api, emails):
    s = _split_edited_608(api, emails)
    # The server re-posts the active decision's Buy (632) for the unnamed line, and the check
    # reads the plan quantity (qty_ordered). Make it 640 with no AutoCount batch, so the Buy
    # no longer adds up and the line is not A9-pending.
    s.core[608].qty_ordered, s.line[608].qty = Decimal("640"), Decimal("640")
    s.db.commit()
    before = _rows_of(s, 608)
    r = _confirm(s.client, s.order.id, [_line_payload(s.line[752].id, buy_qty="649")])
    assert r.status_code == 200, ("the other line confirms", r.status_code, r.text)
    body = r.json()
    assert 752 in _line_nos(s, body.get("lines_confirmed")), body.get("lines_confirmed")
    assert 608 in [h.get("line_no") for h in body.get("lines_held_back") or []], body.get("lines_held_back")
    assert 608 not in _line_nos(s, body.get("lines_confirmed"))
    s.db.commit()
    assert _rows_of(s, 608) == before
