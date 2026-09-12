"""Slice B, delta seam (`documentation/plans/scm/PLAN-scm-change-management-one-engine.md`,
UAC AC-B1 to AC-B3, issue #857, scenarios S1 and S11 in
`documentation/plans/scm/mockups/so-change-management-grill-v4.html`). RED before the
coder's slice lands - no implementation exists yet.

Slice C replaces the suggestion vocabulary; these tests assert `proposal_json` /
`composition_json` and the inquiry-row / hold effects AFTER apply, never `row.suggested`
(which stays `replan`/`keep` until Slice C).

Every scenario is on one product, one own location (`BRW`'s own bin, from `_group_sites`),
one pool (`BRW`'s own pool) - the same shape the grill page's scenarios use. Dates:
`NON_IMMEDIATE` (well beyond both `RESERVE_WINDOW_DAYS=60` and `DEFAULT_IMMEDIATE_WINDOW_
DAYS=30`) unless a scenario is explicitly about the immediate window.

Helpers are imported, not copied, from the files the captain's brief points at:
`tests.test_so_supply_confirmation` (`_core_so`/`_core_line`/`_project_so`/`_project_line`/
`_product`/`_warehouse`/`_stock`/`_user`/`_sorento`/`_uid`) and
`tests.scm.test_project_supply_service_ladder` (`_world`/`_group_sites`) - the same
convention `tests/scm/test_ladder_v7_borrow.py` already uses for this exact combination.
The order/line pair is seeded locally (`_seed_order`) rather than via that file's own
`_seed_line`, because `_seed_line`'s `_project_so` call never sets `so_id` - fine for a
pure ladder/proposal test, but `build_batch`'s `order_ids` mapping (SO number -> core SO
id) needs it for the ADDED-kind path, and setting it costs nothing for the matched-line
path this file actually exercises.

Postgres only (`tests/_pg_fixture.py`), every FK seeded here, never a borrowed row.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow
from app.models.project_so import (
    DECISION_ACTIVE,
    INQUIRY_CANCELLED,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiryRow,
    SOSupplyDecision,
)
from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services import planning_change_service
from app.services.project_supply_service import ProjectSupplyService
from app.services.scm.outstanding_diff import DATE_MOVED, QTY_CHANGED, Change, Diff

from tests._pg_fixture import blank_session
from tests.test_so_supply_confirmation import (  # noqa: F401  (helpers, not fixtures)
    _core_line,
    _core_so,
    _product,
    _project_line,
    _project_so,
    _stock,
    _uid,
    _warehouse,
)
from tests.scm.test_project_supply_service_ladder import _group_sites, _world

MARKER = "zzt-deltaseam"

#: Well beyond RESERVE_WINDOW_DAYS (60) and DEFAULT_IMMEDIATE_WINDOW_DAYS (30) - the
#: baseline for every AC-B1/AC-B2 scenario (S1: "line due 4 Sep, not immediate").
NON_IMMEDIATE = date.today() + timedelta(days=100)
#: Inside DEFAULT_IMMEDIATE_WINDOW_DAYS - AC-B3a/b (S11: "advance INTO the immediate
#: window").
IMMEDIATE = date.today() + timedelta(days=10)
#: Advanced from NON_IMMEDIATE but still beyond the 30-day window - AC-B3c.
STILL_OUTSIDE = date.today() + timedelta(days=45)


def _seed_order(db, company_id, project, product, warehouse, *, qty, required_date,
                 so_number=None):
    core_so = _core_so(db, company_id)
    if so_number:
        core_so.so_number = so_number
        db.flush()
    core_line = _core_line(
        db, core_so, product, warehouse, qty_ordered=qty, required_date=required_date,
    )
    order = _project_so(db, project, so_id=core_so.id)
    # `_so_number` (planning_change_service.py) reads `order.autocount_doc_no or
    # order.provisional_ref` - `test_so_supply_confirmation._project_so` sets neither to
    # the CORE so_number, so `_proposal_for`'s board build would otherwise look up a
    # sales order that does not exist (the project order's own provisional_ref) and find
    # nothing. Every other Slice A/B fixture in this lane sets this explicitly
    # (`test_planning_changes.py`'s own `_project_so(..., autocount_doc_no=core_so
    # .so_number)`) - matched here.
    order.autocount_doc_no = core_so.so_number
    line = _project_line(db, order, line_no=1, product=product, core_line=core_line)
    db.commit()
    return order, line, core_so, core_line


def _held_buy_world(db, *, qty="134", required_date=NON_IMMEDIATE):
    """A held Buy, raised ORDER row, on one line - S1's own starting shape."""
    company_id, actor, project, product = _world(db)
    _group, sites = _group_sites(db)
    own, pool = sites["BRW"]
    order, line, core_so, core_line = _seed_order(
        db, company_id, project, product, own, qty=qty, required_date=required_date,
    )
    ProjectSupplyService(db).confirm(
        order,
        ConfirmSupplyBody(lines=[ConfirmLine(
            project_line_id=line.id, buy_qty=qty, buy_reason="ZZT no stock anywhere",
        )]),
        actor_user_id=actor,
    )
    db.commit()
    order_row = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    return {
        "company_id": company_id, "actor": actor, "project": project, "product": product,
        "own": own, "pool": pool, "order": order, "line": line, "core_so": core_so,
        "core_line": core_line, "order_row_id": str(order_row.id),
    }


def _change_and_batch(db, world, *, new_qty=None, new_required_date=None):
    """Mutates the core line the way a book re-upload or a manual edit already would (the
    write happens BEFORE `build_batch` runs - `test_planning_changes.py`'s own
    `test_apply_returns_a_dropped_bystander_in_returned_to_review` docstring is explicit
    about this order of operations), then builds a batch off ONE Change for it."""
    core_so = world["core_so"]
    core_line = world["core_line"]
    old_qty = float(core_line.qty_ordered)
    old_date = core_line.required_date
    item_code = world["product"].product_code
    location = world["own"].warehouse_code

    if new_qty is not None:
        core_line.qty_ordered = Decimal(str(new_qty))
    if new_required_date is not None:
        core_line.required_date = new_required_date
    db.flush()

    kind = QTY_CHANGED if new_required_date is None else DATE_MOVED
    from app.services.scm.outstanding_diff import Line

    before = Line(doc_number=core_so.so_number, item_code=item_code, location=location,
                  qty=old_qty, required_date=old_date, row_ref=str(core_line.id))
    after = Line(
        doc_number=core_so.so_number, item_code=item_code, location=location,
        qty=float(core_line.qty_ordered), required_date=core_line.required_date,
        row_ref=str(core_line.id),
    )
    change = Change(kind, core_so.so_number, item_code, location, before=before, after=after)

    diff = Diff(scope_documents=(core_so.so_number,), changes=[change])
    batch = planning_change_service.build_batch(
        db, diff, applied_line_ids={id(change): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world["actor"], import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    return batch


def _only_row(db, batch: PlanningChangeBatch) -> PlanningChangeRow:
    rows = db.query(PlanningChangeRow).filter_by(batch_id=batch.id).all()
    assert len(rows) == 1, [r.kind for r in rows]
    return rows[0]


def _confirm_and_apply(db, world, batch):
    planning_change_service.set_row_decision(db, str(batch.id), str(_only_row(db, batch).id),
                                              "confirm")
    db.commit()
    result = planning_change_service.apply(db, str(batch.id), world["actor"])
    db.commit()
    return result


def _live_order_rows(db, line_id):
    return (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_id, OrderInquiryRow.verb == IV_ORDER,
                OrderInquiryRow.state != INQUIRY_CANCELLED)
        .all()
    )


def _active_decision(db, order_id):
    return (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order_id,
                SOSupplyDecision.state == DECISION_ACTIVE)
        .one()
    )


# --------------------------------------------------------------------------- #
# AC-B1a: qty up on a held Buy proposes Buy for the WHOLE new quantity
# --------------------------------------------------------------------------- #

def test_qty_up_on_a_held_buy_proposes_buy_for_the_whole_new_quantity():
    with blank_session() as db:
        world = _held_buy_world(db, qty="134")
        batch = _change_and_batch(db, world, new_qty="234")
        assert batch is not None
        row = _only_row(db, batch)
        assert row.kind == "qty_up"
        composition = planning_change_service.composition_from_proposal(row.proposal_json)

    assert composition.get("buy_qty") == "234", composition
    assert composition.get("reserve") == [], composition
    assert composition.get("borrow") == [], composition


# --------------------------------------------------------------------------- #
# AC-B1b: apply of the qty_up row tops up the SAME inquiry row, in place
# --------------------------------------------------------------------------- #

def test_apply_of_a_qty_up_tops_up_the_same_inquiry_row():
    with blank_session() as db:
        world = _held_buy_world(db, qty="134")
        original_row_id = world["order_row_id"]
        batch = _change_and_batch(db, world, new_qty="234")
        assert batch is not None

        result = _confirm_and_apply(db, world, batch)
        assert result["failed_orders"] == [], result["failed_orders"]

        live_rows = _live_order_rows(db, world["line"].id)
        assert len(live_rows) == 1, [str(r.id) for r in live_rows]
        live_row = live_rows[0]
        # Identity, not just quantity - the exact defect this pins (today: cancel + raise).
        assert str(live_row.id) == original_row_id, (
            str(live_row.id), original_row_id,
        )
        assert live_row.qty == Decimal("234")
        assert live_row.previous_qty == Decimal("134")
        assert live_row.note and "Was 134" in live_row.note
        assert live_row.state == "raised"

        decision = _active_decision(db, world["order"].id)
        snapshot = next(
            s for s in decision.line_snapshots if s["project_line_id"] == str(world["line"].id)
        )
        assert Decimal(snapshot["buy_qty"]) == Decimal("234"), snapshot


# --------------------------------------------------------------------------- #
# AC-B1c: qty up never mixes Use own and Buy
# --------------------------------------------------------------------------- #

def test_qty_up_never_mixes_use_own_and_buy():
    with blank_session() as db:
        world = _held_buy_world(db, qty="134")
        _stock(db, world["product"], world["own"], on_hand=100)
        batch = _change_and_batch(db, world, new_qty="234")
        assert batch is not None
        row = _only_row(db, batch)
        composition = planning_change_service.composition_from_proposal(row.proposal_json)

    assert composition.get("buy_qty") == "234", composition
    assert composition.get("reserve") == [], composition


# --------------------------------------------------------------------------- #
# AC-B1d: own stock covering the WHOLE unit reserves it and cancels the Buy row
# --------------------------------------------------------------------------- #

def test_qty_up_with_own_stock_for_the_whole_unit_reserves_it_and_cancels_the_buy_row():
    with blank_session() as db:
        world = _held_buy_world(db, qty="134")
        _stock(db, world["product"], world["own"], on_hand=300)
        batch = _change_and_batch(db, world, new_qty="234")
        assert batch is not None
        row = _only_row(db, batch)
        composition = planning_change_service.composition_from_proposal(row.proposal_json)
        assert composition.get("buy_qty") == "0", composition
        assert sum(Decimal(r["qty"]) for r in composition.get("reserve") or []) == (
            Decimal("234")
        ), composition

        result = _confirm_and_apply(db, world, batch)
        assert result["failed_orders"] == [], result["failed_orders"]

        live_rows = _live_order_rows(db, world["line"].id)
        assert live_rows == [], [str(r.id) for r in live_rows]

        decision = _active_decision(db, world["order"].id)
        snapshot = next(
            s for s in decision.line_snapshots if s["project_line_id"] == str(world["line"].id)
        )
        reserve_qty = sum(
            Decimal(c["qty"]) for c in snapshot["components"] if c["kind"] == "reserve"
        )
        assert reserve_qty == Decimal("234"), snapshot


# --------------------------------------------------------------------------- #
# AC-B2: a later donor holding the WHOLE unit on hand borrows whole, order-back
# --------------------------------------------------------------------------- #

def test_qty_up_with_a_later_donor_holding_the_whole_unit_borrows_whole_and_raises_order_back():
    with blank_session() as db:
        world = _held_buy_world(db, qty="134")
        donor_bin = _warehouse(db, f"ZZT-DONOR-{_uid()[:4]}")
        _stock(db, world["product"], donor_bin, on_hand=234)
        donor_order, donor_line, donor_core_so, donor_core_line = _seed_order(
            db, world["company_id"], world["project"], world["product"], donor_bin,
            qty=234, required_date=NON_IMMEDIATE + timedelta(days=50),
        )
        ProjectSupplyService(db).confirm(
            donor_order,
            ConfirmSupplyBody(lines=[ConfirmLine(
                project_line_id=donor_line.id,
                reserve=[{"warehouse_id": str(donor_bin.id), "qty": "234"}],
            )]),
            actor_user_id=world["actor"],
        )
        db.commit()

        batch = _change_and_batch(db, world, new_qty="234")
        assert batch is not None
        row = _only_row(db, batch)
        composition = planning_change_service.composition_from_proposal(row.proposal_json)
        assert composition.get("borrow"), (
            "expected a Borrow composition off the donor's on-hand stock", composition,
        )
        assert sum(Decimal(b["qty"]) for b in composition.get("borrow") or []) == (
            Decimal("234")
        ), composition
        assert composition.get("buy_qty") == "0", composition

        result = _confirm_and_apply(db, world, batch)
        assert result["failed_orders"] == [], result["failed_orders"]

        live_order_rows = _live_order_rows(db, world["line"].id)
        assert live_order_rows == [], [str(r.id) for r in live_order_rows]

        order_back = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.so_line_id == donor_line.id,
                    OrderInquiryRow.verb == IV_ORDER_BACK,
                    OrderInquiryRow.state != INQUIRY_CANCELLED)
            .one_or_none()
        )
        assert order_back is not None, "expected an ORDER_BACK row on the donor's line"
        assert order_back.qty == Decimal("234")


# --------------------------------------------------------------------------- #
# AC-B3a: advance into the immediate window - pool share up to its allowance,
# the remainder bought
# --------------------------------------------------------------------------- #

def test_advance_into_the_immediate_window_takes_pool_share_up_to_the_allowance_and_buys_the_rest():
    with blank_session() as db:
        world = _held_buy_world(db, qty="134", required_date=NON_IMMEDIATE)
        # Default pool_share_pct (50%): 100 on hand in the pool -> allowance 50.
        _stock(db, world["product"], world["pool"], on_hand=100)

        batch = _change_and_batch(db, world, new_required_date=IMMEDIATE)
        assert batch is not None
        row = _only_row(db, batch)
        assert row.kind == "advanced"
        composition = planning_change_service.composition_from_proposal(row.proposal_json)

        pool_qty = sum(
            Decimal(r["qty"]) for r in (composition.get("reserve") or [])
            if r.get("warehouse_id") == str(world["pool"].id)
        )
        assert pool_qty == Decimal("50"), composition
        assert composition.get("buy_qty") == "84", composition

        result = _confirm_and_apply(db, world, batch)
        assert result["failed_orders"] == [], result["failed_orders"]

        live_rows = _live_order_rows(db, world["line"].id)
        assert len(live_rows) == 1, [str(r.id) for r in live_rows]
        assert live_rows[0].qty == Decimal("84")
        assert live_rows[0].previous_qty == Decimal("134")
        assert live_rows[0].note and "Was 134" in live_rows[0].note


# --------------------------------------------------------------------------- #
# AC-B3b: advance into the immediate window - pool share covers EVERYTHING,
# the Buy row is cancelled
# --------------------------------------------------------------------------- #

def test_advance_into_the_immediate_window_where_pool_share_covers_everything_cancels_the_buy_row():
    with blank_session() as db:
        world = _held_buy_world(db, qty="134", required_date=NON_IMMEDIATE)
        # 300 on hand at 50% -> allowance 150, comfortably covers the whole 134.
        _stock(db, world["product"], world["pool"], on_hand=300)

        batch = _change_and_batch(db, world, new_required_date=IMMEDIATE)
        assert batch is not None
        row = _only_row(db, batch)
        composition = planning_change_service.composition_from_proposal(row.proposal_json)
        assert composition.get("buy_qty") == "0", composition
        pool_qty = sum(Decimal(r["qty"]) for r in (composition.get("reserve") or []))
        assert pool_qty == Decimal("134"), composition

        result = _confirm_and_apply(db, world, batch)
        assert result["failed_orders"] == [], result["failed_orders"]

        original_row = db.get(OrderInquiryRow, world["order_row_id"])
        assert original_row.state == INQUIRY_CANCELLED, original_row.state


# --------------------------------------------------------------------------- #
# AC-B3c: advanced but still outside the immediate window - no partial pool
# share, the Buy row is unchanged
# --------------------------------------------------------------------------- #

def test_advance_that_stays_outside_the_immediate_window_takes_no_partial_pool_share():
    with blank_session() as db:
        world = _held_buy_world(db, qty="134", required_date=NON_IMMEDIATE)
        # Same pool stock AC-B3a uses (allowance 50, well under 134) - immediate, this
        # would take a share; outside the window, R10 says whole or nothing.
        _stock(db, world["product"], world["pool"], on_hand=100)

        batch = _change_and_batch(db, world, new_required_date=STILL_OUTSIDE)
        assert batch is not None
        row = _only_row(db, batch)
        assert row.kind == "advanced"
        composition = planning_change_service.composition_from_proposal(row.proposal_json)
        assert composition.get("buy_qty") == "134", composition
        assert composition.get("reserve") == [], composition

        result = _confirm_and_apply(db, world, batch)
        assert result["failed_orders"] == [], result["failed_orders"]

        live_rows = _live_order_rows(db, world["line"].id)
        assert len(live_rows) == 1, [str(r.id) for r in live_rows]
        assert live_rows[0].qty == Decimal("134")
        # NOT previous_qty is None: the captain's brief called this row "unchanged", but
        # the DATE still moved (NON_IMMEDIATE -> STILL_OUTSIDE) even though the quantity
        # did not, and `_settle_row_in_place`'s own `changed` test is `need != previous_qty
        # OR required_date != previous_date` - a pure date move still stamps `previous_qty`
        # (same value) alongside `previous_date`, exactly S9's own grill wording ("Keep,
        # the inquiry row carries DELAY 'Was 4 Sep'" for a Buy-held line whose QUANTITY
        # never changed). Corrected here rather than left asserting a value this scenario
        # cannot produce.
        assert live_rows[0].previous_qty == Decimal("134")
        assert live_rows[0].note and "Was 134" in live_rows[0].note
