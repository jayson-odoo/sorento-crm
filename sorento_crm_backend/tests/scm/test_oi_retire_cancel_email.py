"""OI-RETIRE-CANCEL-EMAIL: a line AutoCount deleted tells purchasing CANCEL on the planning
change Confirm (`documentation/plans/scm/PLAN-oi-retire-cancel-email-20oct.md`, AC-1 to AC-4).

Owner case (20 Oct 2026): staff deleted an S-trap line in AutoCount and added a P-trap line of
the same quantity. The Confirm email carried ORDER for the P-trap and nothing for the S-trap:
`planning_change_service._retire_inquiry_rows` cancels the deleted line's rows BEFORE the confirm
(so `_retire_uncovered_rows`, which queues the CANCEL handover, never sees them) and queued no
handover line of its own.

Same harness as `tests/test_planning_change_apply_on_board.py`, the dispatch read off
`_captured_dispatches`.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.project_so import INQUIRY_ACTIONED, INQUIRY_CANCELLED, IV_ORDER
from app.services.scm.outstanding_diff import ADDED, CLOSED, Change, Line

from ..test_order_inquiry_handover_automation import (
    _captured_dispatches,
    _handover_calls,
    _register,
)
from ..test_planning_change_apply_on_board import (
    WAS_1,
    _build,
    _change,
    _confirm,
    _core_line,
    _core_so,
    _line_payload,
    _order_row,
    _project_line,
    _project_so,
    _rows_of,
    api,
    world,
)
from ..test_planning_changes import _product

__all__ = ["api", "world"]  # re-exported fixtures


def _swap_fixture(api, *, old_row_state=None):
    """Line 1 (old product) confirmed as Buy 14, its ORDER row raised. Then AutoCount deletes
    line 1 (the pull writes `line_status = cancelled`) and adds line 2 (new product, 14)."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="14",
                        required_date=WAS_1)
    order = _project_so(db, world.project, so_id=core_so.id,
                        autocount_doc_no=core_so.so_number)
    line_1 = _project_line(db, order, line_no=1, product=world.product, core_line=core_1)
    db.commit()
    response = _confirm(client, order.id, [_line_payload(line_1.id, buy_qty="14")])
    assert response.status_code == 200, response.text
    old_row = _order_row(world, line_1)
    if old_row_state is not None:
        old_row.state = old_row_state
    db.commit()

    new_product = _product(db)
    core_1.line_status = "cancelled"
    line_1.qty = Decimal("0")
    core_2 = _core_line(db, core_so, new_product, world.own_wh, qty_ordered="14",
                        required_date=WAS_1)
    line_2 = _project_line(db, order, line_no=2, product=new_product, core_line=core_2)
    db.commit()

    added = Change(
        ADDED, core_so.so_number, new_product.product_code, "ZZT", before=None,
        after=Line(doc_number=core_so.so_number, item_code=new_product.product_code,
                   location="ZZT", qty=14.0, required_date=WAS_1, row_ref=str(core_2.id)),
    )
    changes = [
        _change(CLOSED, core_1, so_number=core_so.so_number, old_date=WAS_1,
                new_date=None, old_qty="14", new_qty="0"),
        added,
    ]
    batch = _build(world, changes, core_so, [str(core_1.id), str(core_2.id)])
    assert batch is not None
    return {
        "client": client, "world": world, "order": order, "batch": batch,
        "line_1": line_1, "line_2": line_2, "old_row": old_row,
        "old_code": old_row.item_code,
    }


def _confirm_with_batch(fixture, monkeypatch):
    _register(fixture["world"])
    calls = _captured_dispatches(monkeypatch)
    response = _confirm(
        fixture["client"], fixture["order"].id,
        [_line_payload(fixture["line_2"].id, buy_qty="14")],
        batch_id=str(fixture["batch"].id),
    )
    assert response.status_code == 200, response.text
    fixture["world"].db.commit()
    handover = _handover_calls(calls)
    assert handover, [c["trigger_type"] for c in calls]
    return handover


def _lines(handover):
    return [entry for call in handover for entry in call["context"]["handover"]["lines"]]


def test_a_deleted_line_and_its_replacement_print_cancel_and_order_in_one_email(api, monkeypatch):
    """AC-1 + AC-2: one email, CANCEL ALL for the deleted line's row (printed once), ORDER for
    the added line."""
    fixture = _swap_fixture(api)
    world = fixture["world"]

    handover = _confirm_with_batch(fixture, monkeypatch)

    assert len(handover) == 1, "both lines ride the one Confirm email"
    lines = _lines(handover)
    old = [e for e in lines if e["item_code"] == fixture["old_code"]]
    assert len(old) == 1, lines
    assert old[0]["remark"] == "CANCEL ALL", old[0]
    assert old[0]["qty"] == "0", old[0]
    new_row = _order_row(world, fixture["line_2"])
    new = [e for e in lines if e["item_code"] == new_row.item_code]
    assert len(new) == 1, lines
    assert new[0]["remark"] == "ORDER", new[0]
    assert new[0]["qty"] == "14", new[0]
    assert all(r.state == INQUIRY_CANCELLED for r in _rows_of(world, fixture["line_1"]))


def test_an_actioned_row_on_the_deleted_line_stays_live_and_still_prints_cancel(api, monkeypatch):
    """AC-3: purchasing's own word keeps the row live, but the email still tells them the line
    is gone so they can act on what they placed."""
    fixture = _swap_fixture(api, old_row_state=INQUIRY_ACTIONED)
    world = fixture["world"]

    handover = _confirm_with_batch(fixture, monkeypatch)

    old = [e for e in _lines(handover) if e["item_code"] == fixture["old_code"]]
    assert len(old) == 1, _lines(handover)
    assert old[0]["remark"] == "CANCEL ALL", old[0]
    world.db.refresh(fixture["old_row"])
    assert fixture["old_row"].state == INQUIRY_ACTIONED
    assert "closed by a planning change batch" in (fixture["old_row"].note or "")


def test_a_row_cancelled_before_the_apply_prints_nothing(api, monkeypatch):
    """AC-4: only rows this apply retires are told."""
    fixture = _swap_fixture(api, old_row_state=INQUIRY_CANCELLED)

    handover = _confirm_with_batch(fixture, monkeypatch)

    assert not [e for e in _lines(handover) if e["item_code"] == fixture["old_code"]]
    assert [e for e in _lines(handover) if e["remark"] == "ORDER"]


def test_the_retired_row_is_an_order_row(api):
    """Guard on the fixture itself: the deleted line's row is the Buy the first Confirm
    raised, so the CANCEL above is about that row and nothing else."""
    fixture = _swap_fixture(api)
    assert fixture["old_row"].verb == IV_ORDER
