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
    # Owner change request (9 Nov): LOCATION old, NEW LOCATION new, off `was.location`.
    assert (emails[0]["lines"][0].get("was") or {}).get("location") == old
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


# --------------------------------------------------------------------------- #
# Crew browser pass (7 Nov, SO358013 line 224): the move raises a pending
# `location_changed` row and the board Confirm carries that batch.
# --------------------------------------------------------------------------- #


def _raise_move_row(world, order, project_line, old_code, new_wh):
    """The change row a manual SO edit / AutoCount push raises (real diff, line_id pair)."""
    from app.models.order import SalesOrder
    from app.services import planning_change_service
    from app.services.scm.outstanding_diff import Line, diff_lines

    core = _core_line_of(world, project_line)
    so = world.db.get(SalesOrder, core.sales_order_id)

    def side(code):
        return Line(doc_number=so.so_number, item_code=world.product.product_code,
                    location=code, qty=float(core.qty_ordered),
                    required_date=core.required_date, row_ref=str(core.id),
                    line_id=str(core.id))

    core.warehouse_id = new_wh.id
    diff = diff_lines([side(old_code)], [side(new_wh.warehouse_code)])
    batch = planning_change_service.build_batch(
        world.db, diff,
        applied_line_ids={id(c): str(core.id) for c in diff.changes},
        order_ids={so.so_number: str(so.id)},
        actor=world.actor, import_job_id=None, file_name=None,
    )
    world.db.commit()
    assert batch is not None, "premise: the move raised a change row"
    return batch


def test_the_board_confirm_carrying_the_move_row_tells_new_location(api, emails):
    from .test_planning_change_apply_on_board import _confirm

    client, world = api
    order, line_a, _line_b = _order(api)
    old = world.own_wh.warehouse_code
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])
    emails.clear()

    new_wh = _sibling(world)
    batch = _raise_move_row(world, order, line_a, old, new_wh)
    response = _confirm(client, order.id, [_line_payload(line_a.id, buy_qty="10")],
                        batch_id=str(batch.id))
    assert response.status_code == 200, response.text
    world.db.commit()

    assert len(emails) == 1, emails
    assert _lines(emails[0]) == [
        (world.product.product_code, "10", new_wh.warehouse_code, f"NEW LOCATION (was {old})"),
    ], _lines(emails[0])


def test_the_scm_sales_order_edit_then_board_confirm_tells_new_location(api, emails):
    """Crew browser pass, exactly: SCM Sales Order edit moves the line's location, the board
    shows the change, CS re-decides the same Buy and presses Confirm with the batch."""
    from app.models.order import SalesOrder
    from app.models.planning_change import PlanningChangeRow
    from app.schemas.scm_orders import SalesOrderUpdate
    from app.services.scm.sales_order_service import SalesOrderService

    from .test_planning_change_apply_on_board import _confirm

    client, world = api
    order, line_a, _line_b = _order(api)
    old = world.own_wh.warehouse_code
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])
    emails.clear()

    new_wh = _sibling(world)
    core = _core_line_of(world, line_a)
    so = world.db.get(SalesOrder, core.sales_order_id)
    SalesOrderService(world.db).update(
        so.id,
        SalesOrderUpdate(lines=[
            {
                "id": c.id, "sku": world.product.product_code,
                "qty_ordered": float(c.qty_ordered),
                "required_date": c.required_date.isoformat(),
                "warehouse_code": (
                    new_wh.warehouse_code if c.id == core.id else old
                ),
            }
            for c in (core, _core_line_of(world, _line_b))
        ]),
        user_id=world.actor,
    )
    world.db.commit()
    (row,) = (
        world.db.query(PlanningChangeRow)
        .filter_by(project_line_id=str(line_a.id), applied_state="pending")
        .all()
    )
    assert row.kind == "location_changed", row.kind

    response = _confirm(client, order.id, [_line_payload(line_a.id, buy_qty="10")],
                        batch_id=str(row.batch_id))
    assert response.status_code == 200, response.text
    world.db.commit()

    assert len(emails) == 1, emails
    assert _lines(emails[0]) == [
        (world.product.product_code, "10", new_wh.warehouse_code, f"NEW LOCATION (was {old})"),
    ], _lines(emails[0])


def test_a_first_confirm_of_a_moved_line_with_an_imported_order_says_where_it_was(api, emails):
    """Crew browser pass (SO358013 line 224 CB2828-DIY): the line had no confirmed decision
    yet (the Confirm wrote revision 1), only the raised ORDER row a sheet import left at
    BRW-BB. AutoCount (an SCM edit) moved the line to BRW-IB, CS decided the same Buy 104
    and confirmed: purchasing's order sits at the old location, so the email says the move
    against where their order is. The row keeps its id, state, verb and qty (Q3: no cancel,
    no fresh order); a still-raised row follows the line's location as it already did."""
    from .test_oi_handover_purchasing_focus import _imported_raised_order

    _client, world = api
    order, line = _imported_raised_order(api)
    old = world.own_wh.warehouse_code
    (held,) = _rows(world, line)
    held.stock_location = old
    world.db.commit()
    before = (str(held.id), held.state, held.verb, held.qty)
    emails.clear()

    new_wh = _sibling(world)
    _move(world, line, new_wh)
    _post(api, order, [_line_payload(line.id, buy_qty="10")])

    assert len(emails) == 1, emails
    assert _lines(emails[0]) == [
        (world.product.product_code, "10", new_wh.warehouse_code, f"NEW LOCATION (was {old})"),
    ], _lines(emails[0])
    assert (emails[0]["lines"][0].get("was") or {}).get("location") == old
    world.db.expire_all()
    (after,) = _rows(world, line)
    assert (str(after.id), after.state, after.verb, after.qty) == before


# Review round 2: a first Confirm of a moved line keeps every existing first-Confirm wording
# (CHANGED, take-backs, a mixed decision in full) and adds the move after it, once.


def _imported(api, qtys, *, line_qty, delivery_date=None):
    """An undecided line with raised ORDER rows (a sheet import) at the line's location, then
    AutoCount moves the line to a sibling location. Returns (order, line, old, new_wh)."""
    from decimal import Decimal

    from .test_oi_cancelled_line_used_confirm import _inquiry, _oi_row
    from .test_oi_saved_line_email import _one_line_order

    _client, world = api
    order, line, core = _one_line_order(world, line_qty)
    old = world.own_wh.warehouse_code
    inquiry = _inquiry(world.db, world.company_id, order.id)
    for qty in qtys:
        row = _oi_row(world.db, world.company_id, inquiry.id, line.id,
                      world.product.product_code, qty, delivery_date=delivery_date)
        row.stock_location = old
    core.qty_ordered = Decimal(line_qty)
    line.qty = Decimal(line_qty)
    world.db.commit()
    new_wh = _sibling(world)
    _move(world, line, new_wh)
    return order, line, old, new_wh


def test_first_confirm_two_imported_rows_moved_reads_changed_then_the_move(api, emails):
    _client, world = api
    order, line, old, new_wh = _imported(api, ["10", "3"], line_qty="8")
    emails.clear()

    _post(api, order, [_line_payload(line.id, buy_qty="8")])

    assert len(emails) == 1, emails
    assert [(l["location"], l["remark"]) for l in emails[0]["lines"]] == [
        (new_wh.warehouse_code, f"CHANGED: ORDER 10 & ORDER 3 -> ORDER 8, NEW LOCATION (was {old})"),
    ]
    assert (emails[0]["lines"][0].get("was") or {}).get("location") == old


def test_first_confirm_use_plus_buy_moved_reads_the_mixed_change_then_the_move(api, emails):
    from .test_so_supply_confirmation import _stock

    _client, world = api
    order, line, old, new_wh = _imported(api, ["10"], line_qty="10")
    _stock(world.db, world.product, new_wh, on_hand=50)
    world.db.commit()
    emails.clear()

    _post(api, order, [_line_payload(
        line.id, reserve=[{"warehouse_id": new_wh.id, "qty": "6"}], buy_qty="4",
        amend_reason="Part from stock.",
    )])

    new = new_wh.warehouse_code
    assert len(emails) == 1, emails
    assert [(l["location"], l["remark"]) for l in emails[0]["lines"]] == [
        (new, f"CHANGED: ORDER 10 -> USE {new} 6 & ORDER 4, NEW LOCATION (was {old})"),
    ]


def test_first_confirm_moved_with_nothing_else_to_say_is_the_move_alone(api, emails):
    """Review S2: the imported row already carries the line's date and qty, so no row line is
    queued; the line is told from its snapshot as the move alone, never a fresh ORDER."""
    from .test_oi_saved_line_email import D_A

    _client, world = api
    order, line, old, new_wh = _imported(api, ["10"], line_qty="10", delivery_date=D_A)
    emails.clear()

    _post(api, order, [_line_payload(line.id, buy_qty="10")])

    assert len(emails) == 1, emails
    assert [(l["location"], l["remark"]) for l in emails[0]["lines"]] == [
        (new_wh.warehouse_code, f"NEW LOCATION (was {old})"),
    ]
    assert (emails[0]["lines"][0].get("was") or {}).get("location") == old


def test_first_confirm_with_a_planners_remark_still_says_the_move(api, emails):
    """Review S3: any move counts (Q4), the planner's words included."""
    _client, world = api
    order, line, old, new_wh = _imported(api, ["10"], line_qty="10")
    emails.clear()

    payload = _line_payload(line.id, buy_qty="10")
    payload["remark"] = "Site rushes it."
    _post(api, order, [payload])

    assert len(emails) == 1, emails
    [remark] = [l["remark"] for l in emails[0]["lines"]]
    assert remark == f"Site rushes it., NEW LOCATION (was {old})", remark


def test_review_split_names_the_old_location_and_the_new_one_on_a_moved_line(api):
    """Owner change request (9 Nov): the Confirm preview reads LOCATION the old location and
    NEW LOCATION the new one, off the pending change, as NEW QTY / NEW DATE are."""
    from app.services.project_line_split_service import LineSplitService

    _client, world = api
    order, line_a, line_b = _order(api)
    old = world.own_wh.warehouse_code
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])
    new_wh = _sibling(world)
    _raise_move_row(world, order, line_a, old, new_wh)

    listed = LineSplitService(world.db).read(order)
    by_id = {str(l["line_id"]): l for l in listed["lines"]}
    moved, still = by_id[str(line_a.id)], by_id[str(line_b.id)]
    assert (moved["was_location"], moved["location"]) == (old, new_wh.warehouse_code)
    assert (still["was_location"], still["location"]) == (None, old)
