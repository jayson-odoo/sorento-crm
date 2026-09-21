"""Phase 3 fix-round reds - blind spots the reviewer found in S3's own-arrival credit
(R7, R2) that the existing S3 test files (`test_board_received_stock_s3_own_arrival.py`,
`test_board_received_stock_s3_confirm_round_trip.py`) do not pin.

`documentation/plans/scm/PLAN-board-received-stock-own-arrival.md` S3, UAC
`board-received-stock-own-arrival-acceptance-criteria.md` AC-S3-1..AC-S3-9 (S3 is
implemented; these are ADDITIONAL reds against seams the review round measured against
live code, not the un-implemented contract).

Every fixture here uses PLENTY of on hand (200) and NO competing 5000-unit order, so the
group net stays POSITIVE throughout - the reviewer's own point: the existing AC-S3-4
double-count guard only bites because its own on-hand figure (50) is smaller than the
lines' combined theoretical credit, so it catches a DIFFERENT, LOCATION-LEVEL over-spend.
The bugs pinned here survive a generous on-hand ledger because they are not about the
physical floor at all - they are about which SIBLING's spare, and which PRODUCT's
receipt, a line is allowed to credit against.

Seams named by the brief (measured directly, not guessed):

- `app/services/project_supply_service.py::own_arrival_credit_for` walks
  EVERY sibling of the sales order (`SalesOrderLine.sales_order_id == core_line.
  sales_order_id`) with no `product_id` filter at all, and does not remember, across
  SEPARATE calls for two different open siblings, how much of one closed sibling's spare
  an EARLIER call already promised - only the per-(product, location) `own_arrival_left`
  ledger (on-hand) is threaded across the walk, and it is far too coarse to catch a
  spare-source over-spend when on hand is abundant (MB2).
- `_po_received_by_so_line_ref` matches purely on
  `PurchaseOrderLine.from_so_line_ref == source_ref` text, with NO product check at all -
  neither tier 1 (this line's own PO) nor, through it, tier 2 (siblings' spare) ever
  verifies the receiving PO line's `product_id` matches the credited line's own product
  (MB3, both tiers).
- `app/services/project_order_inquiry_service.py::_own_arrival_credit_for_row`
  builds its own minimal `_LineFacts` with
  `open_qty=_dec(core_line.qty_ordered)` - NOT net of `qty_delivered`, unlike every other
  caller of `_LineFacts.open_qty` in this codebase (`project_supply_service.py`:
  `qty_ordered - qty_delivered`) - so a partly-delivered line's credit is
  capped by its ORIGINAL order quantity, not what is actually still open (SF1).
- `_redirect_row_if_received`: the `credit >= linked_qty` shortcut
  (`if linked_qty > _ZERO and self._own_arrival_credit_for_row(row) >= linked_qty: return
  None`) exits BEFORE the function ever looks at `open_links` - so a row whose credit
  happens to cover its FULL linked total (received + still-open) never releases the
  still-open document link, even though nothing about that credit was drawn from the open
  PO shipping (SF10).

Postgres only (`tests/_pg_fixture.py`), every FK seeded here, never a borrowed row.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow
from app.models.procurement import PurchaseOrderLine
from app.models.project_so import (
    DECISION_ACTIVE,
    INQUIRY_PLACED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    SOSupplyDecision,
)
from app.services import planning_change_service
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from tests._pg_fixture import blank_session
from tests.test_fulfilment_board import TODAY, _cell, _line, _order, _product, _service
from tests.test_fulfilment_board import _stock as _board_stock
from tests.test_planning_changes import (  # noqa: F401  (api is the fixture)
    api,
    _core_line,
    _core_so,
    _project_line,
    _project_so,
    _stock,
    _uid,
)
from tests.scm._own_arrival_fixture import (
    order_with_lines,
    own_arrival_group,
    own_arrival_warehouse,
    po_line_bought_for,
    spo_allocation_fully_received,
    supplier_and_po,
)
from tests.scm.test_board_received_stock_s3_own_arrival import (  # noqa: F401  (reused, not modified)
    L2_REQUIRED,
    L3_REQUIRED,
)


def _own_arrival_qty(contribution: dict) -> Decimal:
    return sum(
        (
            Decimal(s["qty"])
            for s in contribution["sources"]
            if s.get("source") == "own_arrival"
        ),
        Decimal("0"),
    )


# ============================================================================
# MB2 - tier-2 spare must be spent ONCE across the siblings drawing on it
# ============================================================================


def test_tier2_spare_is_spent_once_across_siblings():
    """MB2: one closed sibling line (ordered 20, its PO received 60 -> spare 40), two
    open lines needing 40 each, 200 on hand, no other order. The group net is POSITIVE
    throughout (200 on hand, nothing competing for it) - AC-S3-4's own guard cannot catch
    this, because its own on-hand figure is deliberately smaller than the two lines'
    combined theoretical credit. Here on hand is generous on purpose: the only thing that
    should cap the TOTAL own-arrival credit across L2 and L3 is L1's actual spare of 40,
    not the location's physical floor.

    Measured against `own_arrival_credit_for` (`project_supply_service.py`):
    the tier-2 `spare` for a given sibling is recomputed FRESH, independently, every time
    a DIFFERENT open line asks for it - nothing decrements "how much of L1's 40-unit
    spare a sibling already took" the way `own_arrival_left` decrements the PHYSICAL
    on-hand ledger. So today L2 draws its own theoretical credit (min(spare 40, its own
    open qty 40) = 40, well inside the 200-unit on-hand ledger) and L3 independently
    computes the SAME 40-unit spare from L1 a second time, drawing another 40 off a
    ledger that still has 160 left - total credited 80, double the real 40-unit spare.
    """
    with blank_session() as db:
        group, product = own_arrival_group(db)
        own = own_arrival_warehouse(db, group)
        _board_stock(db, product, own, on_hand=200)
        mine, (l1, l2, l3) = order_with_lines(
            db, product=product, warehouse=own,
            lines=[
                {
                    "qty": "20", "required_date": date(2026, 8, 10), "source_ref": "MB2-L1",
                    "line_status": "closed", "delivered": "20",
                },
                {"qty": "40", "required_date": L2_REQUIRED, "source_ref": "MB2-L2"},
                {"qty": "40", "required_date": L3_REQUIRED, "source_ref": "MB2-L3"},
            ],
        )
        po1 = supplier_and_po(db, po_number="ZZT-PO-MB2-L1")
        po_line_bought_for(
            db, po1, product, own, from_so_line_ref="MB2-L1", qty_received=60, qty_ordered=20,
        )

        board = _service(db).build([mine.so_number], granularity="week", as_of=TODAY)
        l2_cell = _cell(board, product.product_code, "2026-08-17")
        l3_cell = _cell(board, product.product_code, "2026-08-24")
        l2_reserved = _own_arrival_qty(l2_cell["contributions"][0])
        l3_reserved = _own_arrival_qty(l3_cell["contributions"][0])

        assert l2_reserved + l3_reserved <= Decimal("40"), (
            "L1's spare (60 received - 20 delivered = 40) is the only thing backing "
            "EITHER L2's or L3's tier-2 credit; crediting both independently double-"
            f"spends it: L2 own_arrival={l2_reserved} L3 own_arrival={l3_reserved} "
            f"(200 on hand never binds here, which is the point): "
            f"L2 sources={l2_cell['contributions'][0]['sources']} / "
            f"L3 sources={l3_cell['contributions'][0]['sources']}"
        )


# ============================================================================
# MB3 - own-arrival credit must never cross a product boundary (tier 1 and tier 2)
# ============================================================================


def test_tier2_never_credits_another_product():
    """MB3 (tier 2 half): order with line A (product X, needs 40, no PO of its own) and
    line B (product Y, ordered 20, its PO received 100 -> 80 spare after netting line B's
    own qty_ordered), 200 on hand of BOTH products, no other order. Line A must get NO
    own_arrival credit - line B's spare is a different product's stock.

    `own_arrival_credit_for`'s sibling loop (`project_supply_service.py`)
    filters siblings only by `SalesOrderLine.sales_order_id == core_line.sales_order_id`
    - it never compares `sibling.product_id` to `core_line.product_id` - so today line A
    (product X) reads line B's (product Y) spare as its own tier-2 credit.
    """
    with blank_session() as db:
        group = f"OA{_uid()[:4]}".upper()
        own = own_arrival_warehouse(db, group)
        product_x = _product(db, f"ZZT-X-{_uid()[:8]}")
        product_y = _product(db, f"ZZT-Y-{_uid()[:8]}")
        _board_stock(db, product_x, own, on_hand=200)
        _board_stock(db, product_y, own, on_hand=200)

        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        line_a = _line(
            db, order, product_x, qty="40", required_date=L2_REQUIRED, warehouse=own,
        )
        line_a.source_ref = "MB3-LINEA-TIER2"
        line_b = _line(
            db, order, product_y, qty="20", required_date=L3_REQUIRED, warehouse=own,
        )
        line_b.source_ref = "MB3-LINEB-TIER2"
        db.flush()

        po = supplier_and_po(db, po_number="ZZT-PO-MB3-TIER2")
        po_line_bought_for(
            db, po, product_y, own, from_so_line_ref="MB3-LINEB-TIER2",
            qty_received=100, qty_ordered=20,
        )

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)
        cell = _cell(board, product_x.product_code, "2026-08-17")
        contribution = cell["contributions"][0]

        own_arrival_sources = [
            s for s in contribution["sources"] if s.get("source") == "own_arrival"
        ]
        assert own_arrival_sources == [], (
            "line B's spare is product Y stock (line A is product X, a different "
            f"product in the same order); line A must draw no own_arrival credit off "
            f"it: {contribution['sources']}"
        )


def test_tier1_never_credits_another_product():
    """MB3 (tier 1 half): a PO line of product Y whose `from_so_line_ref` equals line
    A's (product X) own `source_ref` credits nothing - the received units are the WRONG
    product for line A to draw against, even though the text field matches.

    `_po_received_by_so_line_ref` (`project_supply_service.py`) filters
    `PurchaseOrderLine.from_so_line_ref == source_ref` with no join back to the credited
    line's own `product_id` at all - a collision (or a data-entry mistake) on that text
    field is enough to credit a line with a delivery of a completely different item.
    """
    with blank_session() as db:
        group, product_x = own_arrival_group(db)
        own = own_arrival_warehouse(db, group)
        product_y = _product(db, f"ZZT-Y-{_uid()[:8]}")
        _board_stock(db, product_x, own, on_hand=200)
        mine, (line_a,) = order_with_lines(
            db, product=product_x, warehouse=own,
            lines=[{"qty": "40", "required_date": L2_REQUIRED, "source_ref": "MB3-LINEA-TIER1"}],
        )
        po = supplier_and_po(db, po_number="ZZT-PO-MB3-TIER1")
        po_line_bought_for(
            db, po, product_y, own, from_so_line_ref="MB3-LINEA-TIER1",
            qty_received=100, qty_ordered=100,
        )

        board = _service(db).build([mine.so_number], granularity="week", as_of=TODAY)
        cell = _cell(board, product_x.product_code, "2026-08-17")
        contribution = cell["contributions"][0]

        own_arrival_sources = [
            s for s in contribution["sources"] if s.get("source") == "own_arrival"
        ]
        assert own_arrival_sources == [], (
            "the PO line that received 100 is product Y stock; line A is product X - "
            "the text-matching `from_so_line_ref` must not credit a different product's "
            f"receipt: {contribution['sources']}"
        )


# ============================================================================
# SF1 - the path picker's own fact must cap credit by OPEN qty, like the board does
# ============================================================================


def _path_picker_world_partial_delivery(db, world, *, qty_delivered, on_hand):
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered="40",
        qty_delivered=str(qty_delivered), required_date=date(2027, 6, 1),
    )
    core_line.source_ref = f"ZZT-SF1-{_uid()[:8]}"
    db.flush()
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    po = supplier_and_po(db, po_number=f"ZZT-PO-SF1-{_uid()[:8]}")
    po_line_bought_for(
        db, po, world.product, world.own_wh, from_so_line_ref=core_line.source_ref,
        qty_received=40, qty_ordered=40,
    )
    _stock(db, world.product, world.own_wh, on_hand)
    spo = spo_allocation_fully_received(
        db, world.product, world.own_wh, qty=40, from_po_number=po.po_number,
    )
    inquiry = OrderInquiry(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        amendment_id=None, state="raised", raised_by=world.actor,
    )
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=line.id, qty=Decimal("40"), verb=IV_ORDER, state=INQUIRY_PLACED,
        stock_location=world.own_wh.warehouse_code,
    )
    db.add(row)
    db.flush()
    link = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=row.id, spo_allocation_id=spo.id,
        document=spo.spo_number, qty=Decimal("40"),
    )
    db.add(link)
    decision = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state=DECISION_ACTIVE, line_snapshots=[], confirmed_by=world.actor,
    )
    db.add(decision)
    db.commit()
    return row, link, decision, po


def test_path_picker_caps_credit_by_open_qty_like_the_board(api):
    """SF1: line ordered 40, delivered 30 (open 10), row linked 40 to a received SPO
    allocation, its own PO line received 40, on hand 40. The line's own-arrival credit
    must be capped by what it still OWES (open qty 10), not by its original order
    quantity (40) - the same distinction `project_supply_service.py` already makes for
    every OTHER `_LineFacts.open_qty` caller (`qty_ordered - qty_delivered`). Credit (10)
    is short of the linked 40, so `_redirect_row_if_received` must NOT settle in place -
    Path A (redirect, fresh row raised) applies.

    Before the fix, `_own_arrival_credit_for_row` (`project_order_inquiry_service.py`)
    built its own `_LineFacts` with `open_qty=_dec(core_line.qty_ordered)` - the ORIGINAL
    order quantity, never netted against `qty_delivered` - so it read credit as
    min(tier1 40, open_qty 40) capped by on hand 40 = 40, which met the linked 40 and
    wrongly retained the row in place. This test guards the fix (`open_qty` netted
    against `qty_delivered`).
    """
    client, world = api
    db = world.db
    row, link, decision, po = _path_picker_world_partial_delivery(
        db, world, qty_delivered=30, on_hand=40,
    )

    svc = ProjectOrderInquiryService(db)
    result = svc._redirect_row_if_received(row, [link], decision)

    assert result is not None, (
        "line ordered 40, delivered 30: own-arrival credit must be capped at the OPEN "
        "qty (10), short of the row's linked 40 - Path A (redirect to a fresh row) must "
        "still fire, not settle in place off the line's original, already-partly-"
        f"delivered order quantity: {result}"
    )
    db.expire_all()
    fresh = db.get(OrderInquiryRow, row.id)
    assert fresh.redirected_to_pool is True, fresh.redirected_to_pool


# ============================================================================
# SF8 - the allowed half of AC-S3-6: amending only the uncredited remainder is fine
# ============================================================================


def test_ac_s3_6_amending_the_uncredited_remainder_to_buy_is_allowed(api):
    """SF8: guard for the ALLOWED half of AC-S3-6 - a row carrying an own-arrival
    Reserve of 30 plus an ordinary remainder of 10 (the row's total open qty is 40);
    amending ONLY the 10 into Buy (the 30 stays Reserve, at the same warehouse the
    credit named) must be accepted - `set_row_decision` must not raise
    `planning_change_buy_over_own_arrival`.

    `_refuse_buy_over_own_arrival` (`planning_change_service.py`) only refuses
    when the amended composition's Reserve at the credited warehouse drops BELOW the
    credited quantity; here it stays exactly at 30, so this is expected to be GREEN
    today if `_refuse_buy_over_own_arrival` is implemented as documented - kept as a
    guard either way, so a future change that widens the refusal to the whole row (not
    just the credited part) is caught here.
    """
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered="40",
        required_date=date(2027, 6, 1),
    )
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    batch = PlanningChangeBatch(
        id=_uid(), source_kind="so_manual_edit", order_count=1, line_count=1,
    )
    db.add(batch)
    db.flush()
    row = PlanningChangeRow(
        id=_uid(), batch_id=batch.id, project_sales_order_id=order.id, project_line_id=line.id,
        core_line_id=core_line.id, line_no=1, item_code=world.product.product_code,
        kind="qty_up", from_json={}, to_json={"qty": "40"}, facts_json={},
        proposal_json={
            "project_line_id": str(line.id), "qty": "40",
            "qty_proposed_reserve": "30", "qty_proposed_buy": "10",
            "qty_proposed_incoming": "0",
            "sources": [{
                "kind": "reserve", "qty": "30", "location": world.own_wh.warehouse_code,
                "warehouse_id": str(world.own_wh.id), "rung": "group_take",
                "source": "own_arrival", "supply_document": "ZZT-PO-OWNARRSF8",
            }],
        },
        decision=None, applied_state="pending",
    )
    db.add(row)
    db.commit()

    composition = {
        "project_line_id": str(line.id), "timely_spo_qty": "0",
        "reserve": [{"warehouse_id": str(world.own_wh.id), "qty": "30"}],
        "borrow": [],
        "buy_qty": "10", "buy_reason": "ZZT buying only the uncredited remainder",
        "amend_reason": "ZZT SF8 guard - amend the remainder, keep the credit",
    }

    result = planning_change_service.set_row_decision(
        db, str(batch.id), str(row.id), "amend", composition,
    )

    db.expire_all()
    fresh = db.get(PlanningChangeRow, row.id)
    assert fresh.decision == "amend", fresh.decision
    assert fresh.composition_json is not None, "amend must store a composition"
    assert fresh.composition_json.get("buy_qty") == "10", fresh.composition_json
    assert fresh.composition_json.get("reserve") == [
        {"warehouse_id": str(world.own_wh.id), "qty": "30", "location": world.own_wh.warehouse_code},
    ], fresh.composition_json
    assert result is not None


# ============================================================================
# SF10 - REVERSED, second review round (21 Sep): a mixed row keeps BOTH links
# ============================================================================


def test_mixed_row_replan_settles_in_place_and_keeps_both_links(api):
    """AC-S3-12 (owner ruling R2, second review round 21 Sep): a row linked 40 to a
    received SPO allocation AND 30 to a STILL-OPEN purchase-order line (total linked
    70). Its own line's own PO received 70, on hand 70 - own-arrival credit is 70, which
    meets the row's WHOLE linked total (70), so the `credit >= linked_qty` shortcut in
    `_redirect_row_if_received` fires and returns `None` (retain, Path B) - unchanged
    from AC-S3-7's own contract.

    REVERSED from this file's earlier version (SF10, which had the settle release the
    still-open PO link as a side effect): the owner's ruling is that shifting an open PO
    link off a row is PURCHASING's own decision, made at Order Inquiries, not something a
    replan's credit-covered settle makes for them by side effect. A replan that quietly
    frees a purchasing team's still-open PO reservation the moment landed stock happens
    to cover the row is exactly the "released at revision N" surprise AC-S3-8's own
    Path A already reserves for a row that is genuinely NOT covered - Path B (this row)
    must not borrow that mechanism.

    Pinned END STATE, checked directly against the DB: BOTH links survive the settle -
    the RECEIVED link (`received_link`, evidence of history) exactly as before, and the
    OPEN PO link (`open_link`) too, because nothing about the credit that settled this
    row in place was drawn from that still-open PO's own shipping.

    Before this ruling, `_redirect_row_if_received`'s `credit >= linked_qty` branch
    (`app/services/project_order_inquiry_service.py`) released `still_open`
    links via `_remove_links` before returning `None` (the SF10 fix, review round one).
    This test guards the revert: the branch returns `None` without
    touching `open_links` at all, the same early exit this file's docstring originally
    described before SF10 changed it.
    """
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered="70",
        required_date=date(2027, 6, 1),
    )
    core_line.source_ref = f"ZZT-SF10-{_uid()[:8]}"
    db.flush()
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    po1 = supplier_and_po(db, po_number=f"ZZT-PO-SF10-TIER1-{_uid()[:8]}")
    po_line_bought_for(
        db, po1, world.product, world.own_wh, from_so_line_ref=core_line.source_ref,
        qty_received=70, qty_ordered=70,
    )
    _stock(db, world.product, world.own_wh, 70)

    spo = spo_allocation_fully_received(
        db, world.product, world.own_wh, qty=40, from_po_number=po1.po_number,
    )
    po2 = supplier_and_po(db, po_number=f"ZZT-PO-SF10-OPEN-{_uid()[:8]}")
    open_po_line = PurchaseOrderLine(
        id=_uid(), purchase_order_id=po2.id, product_id=world.product.id,
        warehouse_id=world.own_wh.id, qty_ordered=Decimal("30"), qty_received=Decimal("0"),
        line_status="open",
    )
    db.add(open_po_line)
    db.flush()

    inquiry = OrderInquiry(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        amendment_id=None, state="raised", raised_by=world.actor,
    )
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=line.id, qty=Decimal("70"), verb=IV_ORDER, state=INQUIRY_PLACED,
        stock_location=world.own_wh.warehouse_code,
    )
    db.add(row)
    db.flush()
    received_link = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=row.id, spo_allocation_id=spo.id,
        document=spo.spo_number, qty=Decimal("40"),
    )
    open_link = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=row.id, po_line_id=open_po_line.id,
        document=po2.po_number, qty=Decimal("30"),
    )
    db.add_all([received_link, open_link])
    decision = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state=DECISION_ACTIVE, line_snapshots=[], confirmed_by=world.actor,
    )
    db.add(decision)
    db.commit()

    svc = ProjectOrderInquiryService(db)
    result = svc._redirect_row_if_received(row, [received_link, open_link], decision)

    assert result is None, (
        "own-arrival credit (70, capped by 70 on hand) covers the row's WHOLE linked "
        f"total (40 received + 30 open = 70): the >= threshold retains (Path B), not "
        f"redirects: {result}"
    )
    db.expire_all()
    still_received = db.get(OrderInquiryLink, received_link.id)
    assert still_received is not None, (
        "the received link is evidence of history and must survive an in-place settle"
    )
    still_open = db.get(OrderInquiryLink, open_link.id)
    assert still_open is not None, (
        "AC-S3-12 (owner ruling R2): shifting the still-open PO link off this row is "
        "purchasing's own decision at Order Inquiries, not a side effect of a credit-"
        f"covered settle - the link must survive untouched: {still_open}"
    )


# ============================================================================
# B2 (round 3): the netting loop's PARTLY_LINKED branch calls
# `_redirect_row_if_received` for MULTIPLE rows of one line on ONE instance - the
# per-instance `own_arrival_left` ledger must be charged with what each ROW actually
# used to clear itself, never the whole LINE's theoretical credit on the first row asked.
# ============================================================================


def test_path_picker_charges_only_what_each_row_used(api):
    """B2: one line, qty_ordered 70, its own PO received 70 (tier-1 credit, theoretical
    70, capped by on hand 70) - TWO rows on that SAME line, 35 each, each with its OWN
    SPO allocation link fully received (35 each, linked total 70 across the two rows).
    Both rows are genuinely backed by real, physical stock (70 on hand covers both 35s
    with nothing left over) - `_redirect_row_if_received`, evaluated for BOTH rows on
    ONE `ProjectOrderInquiryService` instance (the netting loop's own PARTLY_LINKED
    branch, `project_order_inquiry_service.py`, does exactly this for every row of an
    order in one replan call), must retain BOTH (`None`, Path B) - neither flips
    `redirected_to_pool`.

    RED today: `_own_arrival_credit_for_row` builds its `_LineFacts` off the WHOLE
    line's `open_qty` (70) on every call, and `own_arrival_credit_for` charges the
    shared `own_arrival_left` ledger with the FULL theoretical credit it computes (70),
    never with what the calling row actually needed to clear its own `credit >=
    linked_qty` check (35) - so row 1's own check (`70 >= 35`) drains the ledger to 0 in
    one call, and row 2's own check then reads `credit = min(70, remaining=0) = 0`,
    which is `< 35`, so row 2 is wrongly redirected even though 35 of the SAME 70
    physically on hand is, in truth, still exactly its own.

    Idempotence (same bug, one layer down, pinned in isolation on a fresh product/PO of
    its own so nothing else touches its ledger key): asking the SAME row's own credit
    TWICE in a row, on one instance, must return the SAME answer - re-asking the
    question a row already asked must not draw the ledger down a second time. Today the
    second call returns 0, because `own_arrival_credit_for` charges the ledger
    unconditionally on every call it is given, whether the caller is a fresh row or the
    same one asked again.
    """
    client, world = api
    db = world.db

    core_so = _core_so(db, world.company_id)
    core_line = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered="70",
        required_date=date(2027, 6, 1),
    )
    core_line.source_ref = f"ZZT-B2-{_uid()[:8]}"
    db.flush()
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    po = supplier_and_po(db, po_number=f"ZZT-PO-B2-{_uid()[:8]}")
    po_line_bought_for(
        db, po, world.product, world.own_wh, from_so_line_ref=core_line.source_ref,
        qty_received=70, qty_ordered=70,
    )
    _stock(db, world.product, world.own_wh, 70)

    inquiry = OrderInquiry(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        amendment_id=None, state="raised", raised_by=world.actor,
    )
    db.add(inquiry)
    db.flush()

    row1 = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=line.id, qty=Decimal("35"), verb=IV_ORDER, state=INQUIRY_PLACED,
        stock_location=world.own_wh.warehouse_code,
    )
    row2 = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=line.id, qty=Decimal("35"), verb=IV_ORDER, state=INQUIRY_PLACED,
        stock_location=world.own_wh.warehouse_code,
    )
    db.add_all([row1, row2])
    db.flush()

    spo1 = spo_allocation_fully_received(
        db, world.product, world.own_wh, qty=35, from_po_number=po.po_number,
    )
    spo2 = spo_allocation_fully_received(
        db, world.product, world.own_wh, qty=35, from_po_number=po.po_number,
    )
    link1 = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=row1.id, spo_allocation_id=spo1.id,
        document=spo1.spo_number, qty=Decimal("35"),
    )
    link2 = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=row2.id, spo_allocation_id=spo2.id,
        document=spo2.spo_number, qty=Decimal("35"),
    )
    db.add_all([link1, link2])
    decision = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state=DECISION_ACTIVE, line_snapshots=[], confirmed_by=world.actor,
    )
    db.add(decision)
    db.commit()

    svc = ProjectOrderInquiryService(db)
    result1 = svc._redirect_row_if_received(row1, [link1], decision)
    result2 = svc._redirect_row_if_received(row2, [link2], decision)

    assert result1 is None, (
        "row 1's own 35 is backed by 35 of the 70 physically on hand: it must be "
        f"retained (Path B), not redirected: {result1}"
    )
    db.expire_all()
    fresh1 = db.get(OrderInquiryRow, row1.id)
    assert fresh1.redirected_to_pool is not True, fresh1.redirected_to_pool

    assert result2 is None, (
        "row 2's own 35 is backed by the OTHER 35 of the same 70 physically on hand - "
        "row 1's own check must not charge the shared ledger with the WHOLE line's "
        "theoretical credit (70) when it only needed 35 to clear its own check, or row "
        f"2 reads a falsely-drained ledger and is wrongly redirected: {result2}"
    )
    fresh2 = db.get(OrderInquiryRow, row2.id)
    assert fresh2.redirected_to_pool is not True, fresh2.redirected_to_pool

    # Idempotence, isolated: a fresh product (its own ledger key, untouched by anything
    # above) so re-asking the SAME row's own credit twice measures only whether the
    # method itself is idempotent, not interference from row1/row2's own draws.
    idem_product = _product(db, f"ZZT-B2-IDEM-{_uid()[:8]}")
    idem_core_so = _core_so(db, world.company_id)
    idem_core_line = _core_line(
        db, idem_core_so, idem_product, world.own_wh, qty_ordered="50",
        required_date=date(2027, 6, 2),
    )
    idem_core_line.source_ref = f"ZZT-B2-IDEM-{_uid()[:8]}"
    db.flush()
    idem_order = _project_so(
        db, world.project, so_id=idem_core_so.id, autocount_doc_no=idem_core_so.so_number,
    )
    idem_line = _project_line(
        db, idem_order, line_no=1, product=idem_product, core_line=idem_core_line,
    )
    db.commit()

    idem_po = supplier_and_po(db, po_number=f"ZZT-PO-B2-IDEM-{_uid()[:8]}")
    po_line_bought_for(
        db, idem_po, idem_product, world.own_wh, from_so_line_ref=idem_core_line.source_ref,
        qty_received=50, qty_ordered=50,
    )
    _stock(db, idem_product, world.own_wh, 50)

    idem_inquiry = OrderInquiry(
        id=_uid(), company_id=world.company_id, project_sales_order_id=idem_order.id,
        amendment_id=None, state="raised", raised_by=world.actor,
    )
    db.add(idem_inquiry)
    db.flush()
    idem_row = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=idem_inquiry.id,
        so_line_id=idem_line.id, qty=Decimal("50"), verb=IV_ORDER, state=INQUIRY_PLACED,
        stock_location=world.own_wh.warehouse_code,
    )
    db.add(idem_row)
    db.commit()

    first_credit = svc._own_arrival_credit_for_row(idem_row)
    second_credit = svc._own_arrival_credit_for_row(idem_row)
    assert first_credit == second_credit == Decimal("50"), (
        "asking the same row's own credit twice on one instance must be idempotent - "
        f"first={first_credit} second={second_credit}"
    )


# ============================================================================
# Round-4 fix-round reds - two of the reviewer's own measured probes,
# `_own_arrival_credit_for_row` capping/charging by the wrong number when a row's own
# `qty` and its LINKED total (what `_redirect_row_if_received`'s own `>=` check compares
# the credit against) diverge. AC-S3-13/AC-S3-14
# (`board-received-stock-own-arrival-acceptance-criteria.md`).
#
# `_own_arrival_credit_for_row` (`project_order_inquiry_service.py`) today caps and
# charges the credit at `credit = min(theoretical, max(row.qty, 0))` - `row.qty`, the
# row's OWN quantity - even though `_redirect_row_if_received` compares that same credit
# against `linked_qty` (`sum(link.qty for link in links)`), a DIFFERENT number whenever a
# row's `qty` and its links' combined total diverge. The expected fix is
# `_own_arrival_credit_for_row(row, need)` capping and charging by `need` - the caller's
# own `linked_qty` - not `row.qty`.
# ============================================================================


def test_path_picker_charges_the_linked_need_not_the_rows_own_qty(api):
    """PROBE A (round-4 brief, reviewer-measured): row qty 30, ONE fully-received link of
    40, the line's own PO received 40, 40 on hand. `_redirect_row_if_received` compares
    the row's own-arrival credit against `linked_qty` (here 40, the link's own qty, not
    the row's), so the credit that answers that question must be capped/charged by 40 -
    the line's own PO physically covers all of it (40 received, 40 on hand) - and the row
    must be RETAINED (Path B, `None`).

    RED today: `_own_arrival_credit_for_row` caps/charges the credit at
    `row.qty` (30) instead of the linked total the caller is about to compare it
    against, so `credit = min(theoretical=40, row.qty=30) = 30`, which is `< linked_qty
    (40)` - the row is wrongly redirected (Path A, a fresh row raised) even though
    nothing about its own line's landed stock is short.
    """
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered="40",
        required_date=date(2027, 6, 1),
    )
    core_line.source_ref = f"ZZT-PROBEA-{_uid()[:8]}"
    db.flush()
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    po = supplier_and_po(db, po_number=f"ZZT-PO-PROBEA-{_uid()[:8]}")
    po_line_bought_for(
        db, po, world.product, world.own_wh, from_so_line_ref=core_line.source_ref,
        qty_received=40, qty_ordered=40,
    )
    _stock(db, world.product, world.own_wh, 40)
    spo = spo_allocation_fully_received(
        db, world.product, world.own_wh, qty=40, from_po_number=po.po_number,
    )

    inquiry = OrderInquiry(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        amendment_id=None, state="raised", raised_by=world.actor,
    )
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=line.id, qty=Decimal("30"), verb=IV_ORDER, state=INQUIRY_PLACED,
        stock_location=world.own_wh.warehouse_code,
    )
    db.add(row)
    db.flush()
    link = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=row.id, spo_allocation_id=spo.id,
        document=spo.spo_number, qty=Decimal("40"),
    )
    db.add(link)
    decision = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state=DECISION_ACTIVE, line_snapshots=[], confirmed_by=world.actor,
    )
    db.add(decision)
    db.commit()

    svc = ProjectOrderInquiryService(db)
    result = svc._redirect_row_if_received(row, [link], decision)

    assert result is None, (
        "row qty 30, one fully-received 40-unit link: the line's own PO received 40, 40 "
        "on hand - the credit `_redirect_row_if_received` compares against its own "
        "linked total (40) must be 40, not row.qty (30), so the row is RETAINED "
        f"(Path B), not redirected: {result}"
    )
    db.expire_all()
    fresh = db.get(OrderInquiryRow, row.id)
    assert fresh.redirected_to_pool is not True, fresh.redirected_to_pool


def test_path_picker_charges_each_rows_own_linked_total_across_two_rows(api):
    """PROBE B (round-4 brief, reviewer-measured): one line, its own PO line received 70,
    70 on hand, no other order. TWO rows on that line: row 1 qty 70 but only 10 of it
    LINKED (to a received SPO allocation); row 2 qty 10, fully linked (also received).
    Both must be RETAINED (Path B, `None`) - 10 + 10 = 20 of the 70 physically landed is
    all either row's own linked total ever asks for.

    RED today: row 1's credit is capped/charged at `row.qty` (70), not its own
    `linked_qty` (10) - `_redirect_row_if_received` charges the shared per-instance
    `_own_arrival_left` ledger the full 70 on row 1's OWN check (`70 >= 10` passes
    regardless, so row 1 still reads retained here, but the ledger is drained to 0 doing
    it), leaving row 2's own check (`credit = min(70, remaining=0) = 0`) to read `0 <
    10` and wrongly redirect row 2 even though 10 of the SAME 70 physically on hand is,
    in truth, still exactly its own. Pinned on the LEDGER, read directly off the service
    instance (`svc._own_arrival_left[product_id][warehouse_code]`, the shape
    `_charge_own_arrival_credit`/`_own_arrival_credit_for_row` key it by): after both
    rows are asked, 70 - 10 - 10 = 50 must be left, not 70 - 70 - 0 = 0.
    """
    client, world = api
    db = world.db

    core_so = _core_so(db, world.company_id)
    core_line = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered="70",
        required_date=date(2027, 6, 1),
    )
    core_line.source_ref = f"ZZT-PROBEB-{_uid()[:8]}"
    db.flush()
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    po = supplier_and_po(db, po_number=f"ZZT-PO-PROBEB-{_uid()[:8]}")
    po_line_bought_for(
        db, po, world.product, world.own_wh, from_so_line_ref=core_line.source_ref,
        qty_received=70, qty_ordered=70,
    )
    _stock(db, world.product, world.own_wh, 70)

    inquiry = OrderInquiry(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        amendment_id=None, state="raised", raised_by=world.actor,
    )
    db.add(inquiry)
    db.flush()

    row1 = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=line.id, qty=Decimal("70"), verb=IV_ORDER, state=INQUIRY_PLACED,
        stock_location=world.own_wh.warehouse_code,
    )
    row2 = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=line.id, qty=Decimal("10"), verb=IV_ORDER, state=INQUIRY_PLACED,
        stock_location=world.own_wh.warehouse_code,
    )
    db.add_all([row1, row2])
    db.flush()

    spo1 = spo_allocation_fully_received(
        db, world.product, world.own_wh, qty=10, from_po_number=po.po_number,
    )
    spo2 = spo_allocation_fully_received(
        db, world.product, world.own_wh, qty=10, from_po_number=po.po_number,
    )
    link1 = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=row1.id, spo_allocation_id=spo1.id,
        document=spo1.spo_number, qty=Decimal("10"),
    )
    link2 = OrderInquiryLink(
        id=_uid(), company_id=world.company_id, row_id=row2.id, spo_allocation_id=spo2.id,
        document=spo2.spo_number, qty=Decimal("10"),
    )
    db.add_all([link1, link2])
    decision = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state=DECISION_ACTIVE, line_snapshots=[], confirmed_by=world.actor,
    )
    db.add(decision)
    db.commit()

    svc = ProjectOrderInquiryService(db)
    result1 = svc._redirect_row_if_received(row1, [link1], decision)
    result2 = svc._redirect_row_if_received(row2, [link2], decision)

    assert result1 is None, (
        "row 1's own linked total is 10 (only one of its links is received, though its "
        f"row qty is 70): retained (Path B), not redirected: {result1}"
    )
    db.expire_all()
    fresh1 = db.get(OrderInquiryRow, row1.id)
    assert fresh1.redirected_to_pool is not True, fresh1.redirected_to_pool

    assert result2 is None, (
        "row 2's own linked total is 10 (fully linked, fully received) - row 1's own "
        "check must not charge the shared ledger with row 1's QTY (70) when row 1's own "
        f"linked total only needed 10 to clear its own check: {result2}"
    )
    fresh2 = db.get(OrderInquiryRow, row2.id)
    assert fresh2.redirected_to_pool is not True, fresh2.redirected_to_pool

    ledger_key = str(world.product.id)
    remaining = svc._own_arrival_left.get(ledger_key, {}).get(world.own_wh.warehouse_code)
    assert remaining == Decimal("50"), (
        "each row must charge the shared ledger with only what IT was measured against "
        "(10 each), leaving 70 - 10 - 10 = 50 for anything asked after, not 70 - 70 = 0: "
        f"svc._own_arrival_left={svc._own_arrival_left}"
    )
