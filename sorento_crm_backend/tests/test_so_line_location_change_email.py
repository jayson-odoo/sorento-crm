"""SPLIT-SHEET-LOCATION (owner, 7 Nov 2026, Q3): when AutoCount moved an SO line to another
location, the next board Confirm's purchasing email states it, "NEW LOCATION (was <old>)",
at the line's new location. Purchasing decides what to do next: the line's Order Inquiry rows
and their links stay as they are (no cancel at the old location, no fresh order at the new).

Read off the email actually dispatched, through the board's own Confirm route (the one
trigger, FP-EMAIL-ONE-TRIGGER). Every row is seeded here.
"""
from __future__ import annotations

from app.models.project_so import OrderInquiryRow

from .test_oi_saved_line_email import _lines, _order, _post, emails  # noqa: F401
from .test_planning_change_apply_on_board import api, world  # noqa: F401
from .test_planning_changes import _line_payload, _warehouse


def _move(world, project_line, warehouse):
    """AutoCount moves the core SO line (the ESB writes `warehouse_id` in place)."""
    core = _core_line_of(world, project_line)
    core.warehouse_id = warehouse.id
    world.db.commit()


def _core_line_of(world, project_line):
    from app.models.order import SalesOrderLine

    return world.db.get(SalesOrderLine, project_line.core_sales_order_line_id)


def _rows(world, project_line):
    return (
        world.db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == project_line.id)
        .all()
    )


def _sibling(world):
    """Another project location in the same pool (BRW-IB -> BRW-BB on SO429664)."""
    wh = _warehouse(world.db, f"{world.own_wh.warehouse_code}X", segment="project",
                    pool_warehouse_id=world.pool_wh.id)
    world.db.commit()
    return wh


def test_a_buy_line_moved_by_autocount_tells_purchasing_the_new_location(api, emails):
    _client, world = api
    order, line_a, _line_b = _order(api)
    old = world.own_wh.warehouse_code
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])
    rows_before = {(str(r.id), r.state, r.verb, r.qty) for r in _rows(world, line_a)}
    emails.clear()

    new_wh = _sibling(world)
    _move(world, line_a, new_wh)
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])

    assert len(emails) == 1, emails
    assert _lines(emails[0]) == [
        (world.product.product_code, "10", new_wh.warehouse_code, f"NEW LOCATION (was {old})"),
    ], _lines(emails[0])
    # Q3: the Order Inquiry rows stay as they were: no cancel, no fresh order.
    world.db.expire_all()
    assert {(str(r.id), r.state, r.verb, r.qty) for r in _rows(world, line_a)} == rows_before


def test_a_moved_line_that_was_also_cut_says_both(api, emails):
    _client, world = api
    order, line_a, _line_b = _order(api)
    old = world.own_wh.warehouse_code
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])
    emails.clear()

    new_wh = _sibling(world)
    core = _core_line_of(world, line_a)
    core.qty_ordered = 8
    line_a.qty = 8
    world.db.commit()
    _move(world, line_a, new_wh)
    _post(api, order, [_line_payload(line_a.id, buy_qty="8")])

    assert len(emails) == 1, emails
    (line,) = _lines(emails[0])
    assert line[2] == new_wh.warehouse_code, line
    assert line[3].endswith(f"NEW LOCATION (was {old})"), line
    assert "CANCEL 2" in line[3], line


def test_the_email_headline_names_the_location_change(api, emails):
    _client, world = api
    order, line_a, _line_b = _order(api)
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])
    emails.clear()

    _move(world, line_a, _sibling(world))
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])

    assert "NEW LOCATION" in (emails[0].get("headline") or ""), emails[0].get("headline")


def test_a_line_not_moved_and_re_approved_still_sends_nothing(api, emails):
    _client, world = api
    order, line_a, _line_b = _order(api)
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])
    emails.clear()

    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])

    assert emails == [], [_lines(e) for e in emails]



# --------------------------------------------------------------------------- #
# Review split (Confirm dialog step 1): the line's own AutoCount location, as the board
# --------------------------------------------------------------------------- #


def test_review_split_shows_the_lines_autocount_location_not_the_planned_one(api):
    """SO429664: the board reads BRW-BB (core warehouse), the line's `stock_location` still
    says BRW (planned at, or a CS draft's pool code). The sheet reads what the board reads."""
    from app.services.project_line_split_service import LineSplitService

    _client, world = api
    order, line_a, _line_b = _order(api)
    line_a.stock_location = world.pool_wh.warehouse_code
    world.db.commit()

    facts = LineSplitService(world.db).line_facts(order)

    assert facts[str(line_a.id)].location == world.own_wh.warehouse_code
    listed = LineSplitService(world.db).read(order)
    (row,) = [l for l in listed["lines"] if str(l["line_id"]) == str(line_a.id)]
    assert row["location"] == world.own_wh.warehouse_code


def test_review_split_falls_back_to_the_planned_location_when_autocount_names_none(api):
    from app.services.project_line_split_service import LineSplitService

    _client, world = api
    order, line_a, _line_b = _order(api)
    _core_line_of(world, line_a).warehouse_id = None
    line_a.stock_location = world.pool_wh.warehouse_code
    world.db.commit()

    facts = LineSplitService(world.db).line_facts(order)

    assert facts[str(line_a.id)].location == world.pool_wh.warehouse_code


def test_a_moved_line_that_also_grew_orders_the_rise_and_says_the_move(api, emails):
    """Review N1: the moved line skips the rows' own line, so the rise is read off the
    snapshots: ORDER 2 beside the move, at the new location."""
    _client, world = api
    order, line_a, _line_b = _order(api)
    old = world.own_wh.warehouse_code
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])
    emails.clear()

    new_wh = _sibling(world)
    core = _core_line_of(world, line_a)
    core.qty_ordered = 12
    line_a.qty = 12
    world.db.commit()
    _move(world, line_a, new_wh)
    _post(api, order, [_line_payload(line_a.id, buy_qty="12")])

    assert len(emails) == 1, emails
    (line,) = _lines(emails[0])
    assert line[2] == new_wh.warehouse_code, line
    assert "ORDER 2" in line[3], line
    assert line[3].endswith(f"NEW LOCATION (was {old})"), line
