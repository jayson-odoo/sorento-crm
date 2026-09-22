"""S2 - a date move settles the line's buy row(s) in place, no duplicate ADVANCE/DELAY
notice (`PLAN-board-oi-mechanical-22sep.md`, `board-oi-mechanical-22sep-acceptance-
criteria.md`, AC-B2-1..9).

TEST-FIRST: `_stamp_date_move` does not exist yet. Today `_settle_row_in_place`
(`app/services/project_order_inquiry_service.py`) only restates a line's buy row when it
finds EXACTLY ONE still-owed row (`raised`/`partly_linked`/`placed`) and declines
everything else - two still-owed rows, a lone `placed` row with no link, and every
`actioned` row (excluded from its own `live` filter outright). A decline falls through to
the old cancel-and-re-raise path, which leaves the existing rows untouched and raises the
OUTSTANDING remainder as a fresh row, if there is one. Independently,
`planning_change_service._oi_demand_rows` raises an ADVANCE/DELAY notice row for every
`advanced`/`delayed` change UNLESS the line is in `settled_in_place` - membership that only
`_settle_row_in_place` OR the fallback's own outstanding-remainder raise can earn, never a
decline that raises nothing (the `actioned`, fully-linked shape). So a decline today means
BOTH the second notice row still gets raised AND the existing buy row(s) are left with no
date stamp at all - the two bugs AC-B2-4..7 exist to fix.

Every test below drives the REAL planning-change apply path: `set_row_decision(db,
batch_id, row_id, "confirm")` (the row's own frozen suggestion, exactly what the board's
one-press Confirm posts for an unamended row - `_confirm_a_planning_change`,
`app/api/v1/projects/fulfilment_planning.py`) followed by `planning_change_service.apply`.
AC-B2-1/2/3 seed a line that already has exactly ONE live buy row - the branch the plan's
own "what exists" section says is UNCHANGED by this fix - so those three are pinned rather
than red where the fix leaves that branch alone; each says so in its own docstring, and
was run against today's code to confirm which.

Runs on the REAL database (`_real_db_session`, imported from `test_planning_change_apply_
on_board`, rolled back via a savepoint): `scm.committed_v` and the handshake columns live
only in the migrated schema. Every row is seeded here behind the ZZT marker - CI's
database has no data.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ADVANCE,
    IV_DELAY,
    IV_ORDER,
    OrderInquiryRow,
)
from app.services import planning_change_service
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.scm.outstanding_diff import DATE_MOVED

from ..test_order_inquiry_handover_automation import (
    _captured_dispatches,
    _handover_calls,
    _register,
)
from ..test_planning_change_apply_on_board import (
    NOW,
    WAS_1,
    _build,
    _change,
    _confirm,
    _core_line,
    _core_so,
    _line_payload,
    _link,
    _order_row,
    _po_line,
    _project_line,
    _project_so,
    _rows_of,
    _stock,
    _supplier,
    _uid,
    api,
    world,
)

__all__ = ["api", "world"]  # re-exported fixtures; keeps linters from calling them unused


# ---------------------------------------------------------------------------
# shared seeding
# ---------------------------------------------------------------------------


def _notices(db, line_id) -> list:
    return (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == line_id,
            OrderInquiryRow.verb.in_([IV_ADVANCE, IV_DELAY]),
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .all()
    )


def _apply_date_move(world, core, order, core_so, line, *, old_date, new_date, qty):
    """Write the book, build the batch off the diff, accept the frozen suggestion via
    Confirm (the board's own one-press path posts NO composition for an unamended row -
    `_confirm_a_planning_change` only calls `set_row_decision(..., "amend", composition)`
    for a row the PRESS itself named; every other row in the batch is exactly the
    `set_row_decision(..., "confirm")` shape used here), then Apply."""
    core.required_date = new_date
    line.delivery_date = new_date
    world.db.commit()
    changes = [
        _change(
            DATE_MOVED, core, so_number=core_so.so_number,
            old_date=old_date, new_date=new_date, old_qty=qty, new_qty=qty,
        )
    ]
    batch = _build(world, changes, core_so, [str(core.id)])
    assert batch is not None
    out = planning_change_service.get_batch(world.db, str(batch.id))
    row_out = out["orders"][0]["rows"][0]
    planning_change_service.set_row_decision(
        world.db, str(batch.id), row_out["id"], "confirm"
    )
    result = planning_change_service.apply(world.db, str(batch.id), world.actor)
    world.db.commit()
    assert result["failed_orders"] == [], result["failed_orders"]
    return batch, row_out


def _one_row_fixture(api, *, qty="10"):
    """One line, one live ORDER row - the AC-B2-1/2/3 base shape."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered=qty, required_date=WAS_1
    )
    order = _project_so(
        db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()
    assert (
        _confirm(client, order.id, [_line_payload(line.id, buy_qty=qty)]).status_code
        == 200
    )
    row = _order_row(world, line)
    return {
        "client": client, "world": world, "order": order, "core_so": core_so,
        "core": core, "line": line, "row": row,
    }


def _actioned_linked_fixture(api, *, qty_a="10", qty_b="5"):
    """AC-B2-7/AC-B2-9 shape: two `actioned` rows, each with a real link, together
    covering the whole line - `_settle_row_in_place`'s `live` filter excludes `actioned`
    outright, so this declines with ZERO live rows whatever the composition asks for."""
    client, world = api
    db = world.db
    total = str(Decimal(qty_a) + Decimal(qty_b))
    core_so = _core_so(db, world.company_id)
    core = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered=total, required_date=WAS_1
    )
    order = _project_so(
        db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()
    assert (
        _confirm(client, order.id, [_line_payload(line.id, buy_qty=total)]).status_code
        == 200
    )

    supplier = _supplier(world)
    row_a = _order_row(world, line)
    row_a.qty = Decimal(qty_a)
    row_a.state = INQUIRY_ACTIONED
    db.commit()
    _, po_a = _po_line(world, supplier, qty=int(qty_a), expected_date=date(2026, 8, 1))
    _link(world, row_a, po_a, qty=qty_a, document="ACT-A")
    db.commit()

    row_b = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=row_a.order_inquiry_id,
        so_line_id=line.id, item_code=row_a.item_code, qty=Decimal(qty_b),
        delivery_date=row_a.delivery_date, stock_location=row_a.stock_location,
        verb=IV_ORDER, state=INQUIRY_ACTIONED, supply_decision_id=row_a.supply_decision_id,
    )
    db.add(row_b)
    db.commit()
    _, po_b = _po_line(world, supplier, qty=int(qty_b), expected_date=date(2026, 8, 1))
    _link(world, row_b, po_b, qty=qty_b, document="ACT-B")
    db.commit()

    return {
        "client": client, "world": world, "order": order, "core_so": core_so,
        "core": core, "line": line, "row_a": row_a, "row_b": row_b, "total": total,
    }


# ---------------------------------------------------------------------------
# AC-B2-1: one live row, restated in place
# ---------------------------------------------------------------------------


def test_date_move_settles_single_live_row(api):
    """AC-B2-1. Run against today's code and confirmed a PIN, not a red test: the plan's
    own "what exists" section says the single-live-row branch is unchanged, and it is -
    `_settle_row_in_place` already finds exactly one live row here, restates it and
    reports the line as settled, so `_oi_demand_rows` already skips the notice. Kept as a
    regression guard for the branch AC-B2-4..7's fix must leave standing."""
    fixture = _one_row_fixture(api, qty="10")
    world = fixture["world"]
    line = fixture["line"]
    row = fixture["row"]
    row_id = str(row.id)
    row.ack_state = ACK_ACKNOWLEDGED
    row.acknowledged_by = world.actor
    row.acknowledged_at = datetime.utcnow()
    world.db.commit()

    _apply_date_move(
        world, fixture["core"], fixture["order"], fixture["core_so"], line,
        old_date=WAS_1, new_date=NOW, qty="10",
    )

    world.db.expire_all()
    live = [r for r in _rows_of(world, line) if r.state != INQUIRY_CANCELLED]
    assert len(live) == 1, [(r.verb, r.state) for r in live]
    survivor = live[0]
    assert str(survivor.id) == row_id, "settled in place, never recreated"
    assert survivor.delivery_date == NOW
    assert survivor.previous_delivery_date == WAS_1
    assert Decimal(str(survivor.previous_qty)) == Decimal("10")
    assert survivor.changed_at is not None
    assert survivor.note and "10" in survivor.note and WAS_1.isoformat() in survivor.note

    assert _notices(world.db, line.id) == [], (
        "no second row is raised beside the settled buy row"
    )


# ---------------------------------------------------------------------------
# AC-B2-2: the ack transition
# ---------------------------------------------------------------------------


def test_date_move_ack_acknowledged_becomes_changed(api):
    """AC-B2-2a. Pinned for the same reason as AC-B2-1: the single-live-row branch
    already flips an ACKNOWLEDGED row to CHANGED on a genuine settle."""
    fixture = _one_row_fixture(api, qty="10")
    world = fixture["world"]
    row = fixture["row"]
    row.ack_state = ACK_ACKNOWLEDGED
    row.acknowledged_by = world.actor
    row.acknowledged_at = datetime.utcnow()
    world.db.commit()

    _apply_date_move(
        world, fixture["core"], fixture["order"], fixture["core_so"], fixture["line"],
        old_date=WAS_1, new_date=NOW, qty="10",
    )

    world.db.expire_all()
    world.db.refresh(row)
    assert row.ack_state == ACK_CHANGED


def test_date_move_ack_awaiting_stays_awaiting(api):
    """AC-B2-2b. A row born AWAITING (S1, the current board-confirm behaviour) and never
    acknowledged: `_settle_row_in_place`'s ack transition is gated on `ACK_ACKNOWLEDGED`/
    `ACK_CHANGED` and never touches an AWAITING row, so this is ALSO true today for the
    single-live-row branch - a regression pin, not new work."""
    fixture = _one_row_fixture(api, qty="10")
    world = fixture["world"]
    row = fixture["row"]
    assert row.ack_state == ACK_AWAITING

    _apply_date_move(
        world, fixture["core"], fixture["order"], fixture["core_so"], fixture["line"],
        old_date=WAS_1, new_date=NOW, qty="10",
    )

    world.db.expire_all()
    world.db.refresh(row)
    assert row.ack_state == ACK_AWAITING


# ---------------------------------------------------------------------------
# AC-B2-3: PO and SPO links survive
# ---------------------------------------------------------------------------


def test_date_move_keeps_po_and_spo_links(api):
    """AC-B2-3. Pinned for the same reason as AC-B2-1: a same-quantity date move never
    reaches `_settle_row_in_place`'s over-cover branch, so today's code already leaves
    both links exactly as they are."""
    from app.models.procurement import SPOAllocation
    from app.models.project_so import OrderInquiryLink

    fixture = _one_row_fixture(api, qty="15")
    world = fixture["world"]
    row = fixture["row"]
    supplier = _supplier(world)
    _, po_line = _po_line(world, supplier, qty=10, expected_date=date(2026, 8, 1))
    _link(world, row, po_line, qty=10, document="PO-A")

    allocation = SPOAllocation(
        id=_uid(), company_id=world.company_id, spo_number=f"ZZT-SPO-{_uid()[:8]}",
        allocated_quantity=Decimal("5"), quantity_received=Decimal("0"),
        product_id=world.product.id, line_status="open", receipt_status="pending",
        expected_date=date(2026, 8, 1), issue_date=date(2026, 6, 1),
    )
    world.db.add(allocation)
    world.db.flush()
    spo_link = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=row.id,
        spo_allocation_id=allocation.id, document=allocation.spo_number, qty=Decimal("5"),
        linked_by=world.actor, linked_at=datetime.utcnow(),
    )
    world.db.add(spo_link)
    world.db.flush()
    ProjectOrderInquiryService(world.db).refresh_link_state([row])
    world.db.commit()

    _apply_date_move(
        world, fixture["core"], fixture["order"], fixture["core_so"], fixture["line"],
        old_date=WAS_1, new_date=NOW, qty="15",
    )

    world.db.expire_all()
    links = ProjectOrderInquiryService(world.db)._links_of(row.id)
    by_document = {link.document: link for link in links}
    assert set(by_document) == {"PO-A", allocation.spo_number}
    assert Decimal(str(by_document["PO-A"].qty)) == Decimal("10")
    assert Decimal(str(by_document[allocation.spo_number].qty)) == Decimal("5")
    assert by_document["PO-A"].po_line_id == po_line.id
    assert by_document[allocation.spo_number].spo_allocation_id == allocation.id


# ---------------------------------------------------------------------------
# AC-B2-4: a fresh line gets a buy row only, no notice
# ---------------------------------------------------------------------------


def test_fresh_line_gets_buy_row_only_no_notice(api):
    """AC-B2-4. A wholly-reserved line - NO buy row raised, `buy_qty=0` - whose date
    then moves FAR beyond the immediate window: the engine's own frozen suggestion is
    [release reserve, buy for the new date] (measured directly,
    `tests/test_planning_changes.py::test_apply_release_returns_the_whole_line_to_the_
    board_with_no_buy_and_no_oi_change`). `_settle_row_in_place` sees ZERO live rows for
    this line (none exist), declines, and the fallback raises the outstanding 20 as a
    fresh ORDER row with NO "Was <old date>" note - that note only comes from
    `_settle_row_in_place`'s own restatement, which never ran. Meanwhile the line is not
    in `settled_in_place` either (declined, and the fallback's own `settled_in_place.
    append` only fires on a REDIRECT, which this line's plain fresh raise is not), so
    `_oi_demand_rows` raises the ADVANCE/DELAY notice too - the duplicate."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered="20", required_date=WAS_1
    )
    order = _project_so(
        db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()

    assert _confirm(client, order.id, [{
        "project_line_id": str(line.id), "timely_spo_qty": "0",
        "reserve": [{"warehouse_id": world.pool_wh.id, "qty": "20"}],
        "borrow": [], "buy_qty": "0",
    }]).status_code == 200
    assert _notices(db, line.id) == []
    assert (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER,
                OrderInquiryRow.state != INQUIRY_CANCELLED)
        .count() == 0
    ), "fully reserved: no buy row exists before the date move"

    far = date(2027, 3, 10)
    _apply_date_move(
        world, core, order, core_so, line, old_date=WAS_1, new_date=far, qty="20"
    )

    db.expire_all()
    buy_rows = [
        r for r in _rows_of(world, line)
        if r.state != INQUIRY_CANCELLED and r.verb == IV_ORDER
    ]
    assert len(buy_rows) == 1, buy_rows
    fresh = buy_rows[0]
    assert fresh.delivery_date == far
    assert Decimal(str(fresh.qty)) == Decimal("20")
    assert fresh.note and "Was" in fresh.note and WAS_1.isoformat() in fresh.note, (
        fresh.note
    )

    assert _notices(db, line.id) == [], (
        "no ADVANCE/DELAY row beside the fresh buy row this same confirm raised"
    )


# ---------------------------------------------------------------------------
# AC-B2-5: two live rows, both stamped
# ---------------------------------------------------------------------------


def test_two_live_rows_both_stamped_no_notice(api):
    """AC-B2-5. `_settle_row_in_place` declines with two still-owed rows
    (`test_a_line_with_two_still_owed_rows_declines_settle_in_place_and_the_old_path_
    stands` pins today's decline itself) - both rows must stand untouched with no note,
    and a THIRD row would be raised for any outstanding remainder. This is a pure date
    move (same qty), so there is no remainder to raise, and the plan wants both existing
    rows date-stamped in place instead of left bare with a duplicate ADVANCE/DELAY
    notice beside them."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered="20", required_date=WAS_1
    )
    order = _project_so(
        db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()

    assert _confirm(client, order.id, [_line_payload(line.id, buy_qty="20")]).status_code == 200
    supplier = _supplier(world)
    row_a = _order_row(world, line)
    row_a.qty = Decimal("10")
    db.commit()
    _, po_a = _po_line(world, supplier, qty=10, expected_date=date(2026, 8, 1))
    _link(world, row_a, po_a, qty=10, document="ROW-A")
    db.commit()

    row_b = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=row_a.order_inquiry_id,
        so_line_id=line.id, item_code=row_a.item_code, qty=Decimal("10"),
        delivery_date=row_a.delivery_date, stock_location=row_a.stock_location,
        verb=IV_ORDER, state=INQUIRY_RAISED, supply_decision_id=row_a.supply_decision_id,
    )
    db.add(row_b)
    db.commit()
    _, po_b = _po_line(world, supplier, qty=10, expected_date=date(2026, 8, 1))
    _link(world, row_b, po_b, qty=10, document="ROW-B")
    db.commit()

    _apply_date_move(
        world, core, order, core_so, line, old_date=WAS_1, new_date=NOW, qty="20"
    )

    db.expire_all()
    db.refresh(row_a)
    db.refresh(row_b)
    for row, document in ((row_a, "ROW-A"), (row_b, "ROW-B")):
        assert row.delivery_date == NOW, (document, row.delivery_date)
        assert row.previous_delivery_date == WAS_1, document
        assert row.changed_at is not None, document
        assert [
            link.document for link in ProjectOrderInquiryService(db)._links_of(row.id)
        ] == [document]

    assert _notices(db, line.id) == []


# ---------------------------------------------------------------------------
# AC-B2-6: a lone placed row without links
# ---------------------------------------------------------------------------


def test_lone_placed_row_without_links_gets_date_stamp_qty_untouched_no_notice(api):
    """AC-B2-6. The SO349754 WESERP10B shape
    (`test_a_placed_row_with_no_link_declines_settle_and_keeps_its_placed_quantity`):
    a PLACED row with no link row behind it declines settle-in-place outright. Here the
    qty does not move (pure date move), so the netting has no outstanding remainder to
    raise - today that means the row is left completely bare AND a duplicate notice is
    still raised for the line."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered="5", required_date=WAS_1
    )
    order = _project_so(
        db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()
    assert _confirm(client, order.id, [_line_payload(line.id, buy_qty="5")]).status_code == 200

    row = _order_row(world, line)
    row_id = str(row.id)
    row.state = INQUIRY_PLACED
    db.commit()

    _apply_date_move(
        world, core, order, core_so, line, old_date=WAS_1, new_date=NOW, qty="5"
    )

    db.expire_all()
    placed = db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_id).one()
    assert placed.state == INQUIRY_PLACED
    assert Decimal(str(placed.qty)) == Decimal("5"), "qty untouched"
    assert placed.delivery_date == NOW
    assert placed.previous_delivery_date == WAS_1
    assert placed.changed_at is not None

    assert _notices(db, line.id) == []
    fresh = [
        r for r in _rows_of(world, line)
        if str(r.id) != row_id and r.state != INQUIRY_CANCELLED and r.verb == IV_ORDER
    ]
    assert fresh == [], "no fresh ORDER row either - the placed row just gets its date stamped"


# ---------------------------------------------------------------------------
# AC-B2-7: every buy row actioned and fully linked
# ---------------------------------------------------------------------------


def test_actioned_fully_linked_rows_stamped_no_notice_handover_once(api):
    """AC-B2-7. `INQUIRY_ACTIONED` is excluded from `_settle_row_in_place`'s own `live`
    filter outright, so a line whose buy rows are ALL actioned declines with ZERO live
    rows whatever the composition proposes - and since the two rows together already
    cover the whole line, the netting's own outstanding-remainder raise is also zero.
    Today that means the actioned rows are left with no date stamp, the ADVANCE/DELAY
    notice still fires (the line is never in `settled_in_place`), and the handover email
    records it as a fresh `raised` ADVANCE/DELAY, never as the settle it should be."""
    client, world = api
    fixture = _actioned_linked_fixture(api, qty_a="10", qty_b="5")
    world = fixture["world"]
    line = fixture["line"]
    row_a, row_b = fixture["row_a"], fixture["row_b"]

    _apply_date_move(
        world, fixture["core"], fixture["order"], fixture["core_so"], line,
        old_date=WAS_1, new_date=NOW, qty=fixture["total"],
    )

    world.db.expire_all()
    world.db.refresh(row_a)
    world.db.refresh(row_b)
    for row, document in ((row_a, "ACT-A"), (row_b, "ACT-B")):
        assert row.state == INQUIRY_ACTIONED, document
        assert row.delivery_date == NOW, document
        assert row.previous_delivery_date == WAS_1, document
        assert row.changed_at is not None, document
        assert [
            link.document
            for link in ProjectOrderInquiryService(world.db)._links_of(row.id)
        ] == [document]

    assert _notices(world.db, line.id) == []


# ---------------------------------------------------------------------------
# AC-B2-8: no buy row, none raised - pinned
# ---------------------------------------------------------------------------


def test_no_buy_row_and_none_raised_behaviour_pinned(api):
    """AC-B2-8 (pin, per the AC's own wording: "behaviour is unchanged from today; the
    test pins it"). A wholly-reserved line moved only a FEW days - inside the immediate
    window - keeps its reserve exactly as it stood (the engine's own "keep" default for
    an immediate line); no buy row is ever raised. The fix's own scope (AC-B2-1..7) never
    touches this shape, so a notice row is STILL raised for the date move even though
    nothing was ever bought. The fixed code must keep raising it - this pins that."""
    client, world = api
    db = world.db
    near_was = date.today() + timedelta(days=5)
    near_now = date.today() + timedelta(days=10)
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered="20", required_date=near_was
    )
    order = _project_so(
        db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()

    assert _confirm(client, order.id, [{
        "project_line_id": str(line.id), "timely_spo_qty": "0",
        "reserve": [{"warehouse_id": world.pool_wh.id, "qty": "20"}],
        "borrow": [], "buy_qty": "0",
    }]).status_code == 200
    assert (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.state != INQUIRY_CANCELLED)
        .count() == 0
    ), "fully reserved: nothing is raised at all"

    _apply_date_move(
        world, core, order, core_so, line, old_date=near_was, new_date=near_now, qty="20"
    )

    db.expire_all()
    buy_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER,
                OrderInquiryRow.state != INQUIRY_CANCELLED)
        .all()
    )
    assert buy_rows == [], "still no buy row - the reserve covered it, unchanged"

    notices = _notices(db, line.id)
    assert len(notices) == 1, "today's behaviour: a notice IS raised even with no buy row"


# ---------------------------------------------------------------------------
# AC-B2-9: the handover context
# ---------------------------------------------------------------------------


def test_handover_context_lists_date_change_under_changed_not_raised(api, monkeypatch):
    """AC-B2-9. Reuses AC-B2-7's actioned+fully-linked shape, where `_settle_row_in_
    place` declines and no `_record_handover(kind="settled", ...)` call happens at all -
    the line's only handover entry today is the ADVANCE/DELAY notice's own
    `_record_handover(plan_row, kind="raised", was=plan.was)` (`_write`,
    `project_order_inquiry_service.py`), and `derive_for_book_change`'s own `DemandRow`
    never threads a `was`, so that line's `was` field is always blank - the tell that
    distinguishes a fresh "raised" notice from a genuine "changed" settle whose remark
    text ("ADVANCE"/"DELAY") reads identically either way."""
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    fixture = _actioned_linked_fixture(api, qty_a="10", qty_b="5")
    world = fixture["world"]
    calls.clear()  # only the date move's own dispatch matters here

    _apply_date_move(
        world, fixture["core"], fixture["order"], fixture["core_so"], fixture["line"],
        old_date=WAS_1, new_date=NOW, qty=fixture["total"],
    )

    matches = _handover_calls(calls)
    assert matches, "the date move must dispatch a handover"
    lines = matches[-1]["context"]["handover"]["lines"]
    changed_lines = [
        entry for entry in lines
        if entry["remark"] in ("ADVANCE", "DELAY")
        and entry["was"]
        and entry["was"].get("delivery_date")
    ]
    assert len(changed_lines) == 1, lines
    assert changed_lines[0]["was"]["delivery_date"] == WAS_1.strftime("%d/%m/%Y")
    assert changed_lines[0]["delivery_date"] == NOW.strftime("%d/%m/%Y")
