"""SO-LOCATION-GAP (owner, 9 Nov 2026, prod SO429664 SRTWT8239-GM): a line confirmed at BRW,
then moved by AutoCount to BRW-BB BEFORE location changes were detected (#2221), then given a
date change. The email's REMARK said "DELAY, NEW LOCATION (was BRW)" (it compares confirmed
snapshots), but the change row carried no location (it compares the two sides of one AutoCount
push, and the move was in an earlier one): the "What changed" lightbox showed only the date and
the Review split showed no NEW LOCATION.

Rule (brief, 9 Nov): when a line gets a change and its location now differs from the location of
its last confirmed decision (else where its live ORDER rows sit), the move is part of that change,
exactly as if it had been detected. A line with no change of its own is not flagged (owner Q1,
7 Nov: no backfill).

Plan: `documentation/plans/scm/PLAN-so-location-gap-09nov.md`.
"""
from __future__ import annotations

import io
from datetime import timedelta

import pytest

from app.models.planning_change import PlanningChangeRow

from .test_oi_saved_line_email import _lines, _order, _post, emails  # noqa: F401
from .test_planning_change_apply_on_board import _confirm, api, world  # noqa: F401
from .test_planning_changes import _line_payload
from .test_so_line_location_change_email import _core_line_of, _move, _rows, _sibling


def _date_change(world, project_line, before_code, after_code, days=7):
    """One AutoCount push (real diff, line_id pair) moving the line's date `days` later. The
    line sits at `before_code` in the push's before side and `after_code` in its after side:
    equal when the move came in an EARLIER push (the owner's case), different when this push
    carries the move itself (a detected move)."""
    from app.models.order import SalesOrder
    from app.services import planning_change_service
    from app.services.scm.outstanding_diff import Line, diff_lines

    core = _core_line_of(world, project_line)
    so = world.db.get(SalesOrder, core.sales_order_id)
    old_date = core.required_date
    new_date = old_date + timedelta(days=days)

    def side(code, when):
        return Line(doc_number=so.so_number, item_code=world.product.product_code,
                    location=code, qty=float(core.qty_ordered), required_date=when,
                    row_ref=str(core.id), line_id=str(core.id))

    core.required_date = new_date
    diff = diff_lines([side(before_code, old_date)], [side(after_code, new_date)])
    batch = planning_change_service.build_batch(
        world.db, diff,
        applied_line_ids={id(c): str(core.id) for c in diff.changes},
        order_ids={so.so_number: str(so.id)},
        actor=world.actor, import_job_id=None, file_name=None,
    )
    world.db.commit()
    assert batch is not None, "premise: the date change raised a change row"
    return batch


def _pending(world, project_line):
    return (
        world.db.query(PlanningChangeRow)
        .filter_by(project_line_id=str(project_line.id), applied_state="pending")
        .all()
    )


def _split(world, order):
    from app.services.project_line_split_service import LineSplitService

    listed = LineSplitService(world.db).read(order)
    return {
        str(l["line_id"]): (l["was_location"], l["location"]) for l in listed["lines"]
    }


@pytest.mark.parametrize(
    "detected",
    [
        pytest.param(False, id="moved_before_detection"),
        # Control: the same push carries the move (#2221 detects it). Both must read alike.
        pytest.param(True, id="moved_in_the_same_push"),
    ],
)
def test_a_move_rides_on_the_next_change_like_a_detected_one(api, emails, detected):
    """UAC G1-G4, the owner's exact sequence: Buy confirmed at the old location (ORDER raised
    there), moved, then a later date change; then the board Confirm with that batch."""
    from app.services import planning_change_service
    from app.services.order_inquiry_worklist_service import handover_xlsx

    client, world = api
    order, line_a, _line_b = _order(api)
    old = world.own_wh.warehouse_code
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])
    (raised,) = _rows(world, line_a)
    assert raised.stock_location == old, "premise: the ORDER sits at the old location"
    emails.clear()

    new_wh = _sibling(world)
    new = new_wh.warehouse_code
    if detected:
        _core_line_of(world, line_a).warehouse_id = new_wh.id
        batch = _date_change(world, line_a, old, new)
    else:
        _move(world, line_a, new_wh)  # an earlier push, never turned into a change row
        batch = _date_change(world, line_a, new, new)

    # G1: the change row (and so the lightbox, off the wire) carries Location was / now,
    # beside the date; the kind stays the date kind (owner Q2, 7 Nov: one row).
    (row,) = _pending(world, line_a)
    assert row.kind not in ("location_changed",), row.kind
    wire = planning_change_service.row_out(world.db, row)
    assert (wire["from"].get("location"), wire["to"].get("location")) == (old, new), (
        wire["from"], wire["to"],
    )
    assert wire["from"].get("required_date") != wire["to"].get("required_date")

    # G2: Review split LOCATION old, NEW LOCATION new.
    assert _split(world, order)[str(line_a.id)] == (old, new)

    # G3: the email line at the new location says the date word and the move; its table and
    # Excel print LOCATION old, NEW LOCATION new.
    response = _confirm(client, order.id, [_line_payload(line_a.id, buy_qty="10")],
                        batch_id=str(batch.id))
    assert response.status_code == 200, response.text
    world.db.commit()
    assert len(emails) == 1, emails
    ((item_code, qty, location, remark),) = _lines(emails[0])
    assert (item_code, qty, location) == (world.product.product_code, "10", new)
    assert remark == f"DELAY, NEW LOCATION (was {old})", remark
    assert (emails[0]["lines"][0].get("was") or {}).get("location") == old

    import openpyxl

    sheet = openpyxl.load_workbook(io.BytesIO(handover_xlsx(emails[0]["lines"]))).active
    header = [cell.value for cell in sheet[1]]
    values = dict(zip(header, [cell.value for cell in sheet[2]]))
    assert (values.get("LOCATION"), values.get("NEW LOCATION")) == (old, new), values

    # G4: the ORDER row ends the Confirm as it does for a detected move: same row, same verb
    # and qty, following the line to its new location.
    world.db.expire_all()
    (after,) = _rows(world, line_a)
    assert (str(after.id), after.verb, after.qty) == (str(raised.id), raised.verb, raised.qty)
    assert after.stock_location == new, after.stock_location


def test_a_line_moved_before_detection_with_no_change_of_its_own_is_not_flagged(api):
    """UAC G5 (owner Q1, 7 Nov: no backfill): line B moved the same way, but only line A's
    date changed. B gets no change row and the Review split shows no move for it."""
    _client, world = api
    order, line_a, line_b = _order(api)
    _post(api, order, [
        _line_payload(line_a.id, buy_qty="10"), _line_payload(line_b.id, buy_qty="6"),
    ])
    new_wh = _sibling(world)
    new = new_wh.warehouse_code
    _move(world, line_a, new_wh)
    _move(world, line_b, new_wh)

    _date_change(world, line_a, new, new)

    assert _pending(world, line_b) == []
    assert _split(world, order)[str(line_b.id)] == (None, new)


def test_a_line_that_did_not_move_carries_no_location_on_its_change(api):
    """Guard: a plain date change on a line still where it was confirmed reads no move."""
    _client, world = api
    order, line_a, _line_b = _order(api)
    old = world.own_wh.warehouse_code
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])

    _date_change(world, line_a, old, old)

    (row,) = _pending(world, line_a)
    assert (row.from_json.get("location"), row.to_json.get("location")) == (None, None)
    assert _split(world, order)[str(line_a.id)] == (None, old)


def test_a_line_with_no_decision_reads_the_move_from_where_its_order_sits(api):
    """UAC G6: no confirmed decision yet, only the raised ORDER a sheet import left at the old
    location (the email's own first-Confirm reference, `held_order_locations`). Moved before
    detection, then a date change: the row carries the move."""
    from .test_oi_handover_purchasing_focus import _imported_raised_order

    _client, world = api
    order, line = _imported_raised_order(api)
    old = world.own_wh.warehouse_code
    (held,) = _rows(world, line)
    held.stock_location = old
    world.db.commit()
    new_wh = _sibling(world)
    new = new_wh.warehouse_code
    _move(world, line, new_wh)

    _date_change(world, line, new, new)

    (row,) = _pending(world, line)
    assert (row.from_json.get("location"), row.to_json.get("location")) == (old, new), (
        row.from_json, row.to_json,
    )
    assert _split(world, order)[str(line.id)] == (old, new)
