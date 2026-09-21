"""S3, own-arrival credit and the path picker (R7, R2, R6).

`documentation/plans/scm/PLAN-board-received-stock-own-arrival.md` S3, UAC
`board-received-stock-own-arrival-acceptance-criteria.md` AC-S3-1 to AC-S3-9. RED before the
coder's slice lands - no implementation to look at, testing the CONTRACT.

CONTRACT CHOICES this file pins (the plan names the seams; it leaves the exact wire shape
of "the composition carries `source: own_arrival`" open, since neither the `Component`
dataclass (`scm/front_planning_engine.py`) nor `_serialize_component`
(`project_supply_service.py`) nor the board's own `_source()`
(`project_fulfilment_board_service.py`) carries a `source` key today):

- The BOARD's own per-line source dict (`FulfilmentBoardService._source`, what
  `cell["contributions"][i]["sources"]` carries on the wire) gains a NEW `source` key,
  `"own_arrival"` on a credit-born Reserve, `None`/absent otherwise. This key does not
  collide with anything that dict already carries.
- `PlanningChangeRow.proposal_json["sources"]` entries (the `BoardContribution`-shaped
  proposal `_serialize_component` in `project_supply_service.py` produces) gain the SAME
  `source` key, plus the existing `supply_document` field carries the PO number (the same
  field every other document-referencing component already uses - no new key invented for
  it).
- AC-S3-1 through AC-S3-5 and AC-S3-9 are exercised through `FulfilmentBoardService.build`
  against CORE `sales_orders`/`sales_order_lines` (no `ProjectSalesOrder` wrapper needed -
  the same convention `tests/test_fulfilment_board.py`'s own `_group_world` uses, and the
  layer the plan's own seam - `scm/front_planning_engine.py::_draw_group` via
  `project_supply_service.py::use_candidates_for` - actually sits at).
- AC-S3-6 through AC-S3-8 need the PROJECT layer (`ProjectSalesOrder`/
  `ProjectSalesOrderLine`/`OrderInquiryRow`/`PlanningChangeRow`), the same convention
  `tests/test_planning_changes.py`'s `api` fixture uses; `_redirect_row_if_received` is
  called directly (a legitimate, already-private seam the plan names by file and symbol).
- AC-S3-9 is read at the SAME layer AC-S2-2 already exercises (`_placed_links` +
  `compose_suggestion`), driven end-to-end off a real `OrderInquiryLink` to a received SPO
  allocation this time, rather than repeating a board-level fixture only to re-prove S2's
  own contract a second time.

Postgres only (`tests/_pg_fixture.py`), every FK seeded here, never a borrowed row.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.project_so import (
    DECISION_ACTIVE,
    INQUIRY_PLACED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    SOSupplyDecision,
)
from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow
from app.services import planning_change_service
from app.services.error_handler import AppException
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from tests._pg_fixture import blank_session
from tests.test_fulfilment_board import TODAY, _cell, _service, _stock as _board_stock
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

L2_REQUIRED = date(2026, 8, 20)
L3_REQUIRED = date(2026, 8, 27)


def _reserve_sources(contribution: dict) -> list:
    return [s for s in contribution["sources"] if s.get("rung") == "group_take"]


def _buy_qty(contribution: dict) -> Decimal:
    return sum(
        (Decimal(s["qty"]) for s in contribution["sources"] if s.get("kind") == "buy"),
        Decimal("0"),
    )


def _own_step(contribution: dict) -> dict:
    return next(s for s in contribution["trail"] if s["kind"] == "own")


def test_ac_s3_1_own_arrival_credit_draws_first_as_a_reserve_despite_a_negative_group_net():
    """AC-S3-1: "Ladder for L2 (needs 20; 40 received on its own PO line; group net
    negative because of the other order): step "Can we use our locations?" answers yes
    with `took = 20`, the component is `RESERVE` on `RUNG_GROUP_TAKE` with `source =
    own_arrival`, and the trail `why` names the PO ("20 landed for this line on PO ...")."

    Measured directly first (the un-implemented state): with a huge competing order at the
    same location, the group nets far below zero and step 1 answers "no", took "0" - own
    PO line 40 received is not credited anywhere, so the LINE buys instead, the exact
    defect SO372176 hit on prod.
    """
    with blank_session() as db:
        group, product = own_arrival_group(db)
        own = own_arrival_warehouse(db, group)
        _board_stock(db, product, own, on_hand=20)
        mine, (l2,) = order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "20", "required_date": L2_REQUIRED, "source_ref": "L2"}],
        )
        po = supplier_and_po(db, po_number="ZZT-PO-OWNARR")
        po_line_bought_for(
            db, po, product, own, from_so_line_ref="L2", qty_received=40, qty_ordered=40,
        )
        order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "5000", "required_date": date(2026, 4, 1), "source_ref": "OTHER"}],
        )

        board = _service(db).build([mine.so_number], granularity="week", as_of=TODAY)
        cell = _cell(board, product.product_code, "2026-08-17")
        contribution = cell["contributions"][0]

        own_step = _own_step(contribution)
        assert own_step["answer"] == "yes", own_step
        assert own_step["took"] == "20", own_step
        assert "20 landed for this line on PO" in own_step["why"], own_step["why"]
        assert po.po_number in own_step["why"], own_step["why"]

        reserves = _reserve_sources(contribution)
        assert reserves and reserves[0]["kind"] == "reserve", contribution["sources"]
        assert reserves[0].get("source") == "own_arrival", reserves[0]


def test_ac_s3_2_tier_2_spare_from_a_siblings_own_po_line_completes_the_reserve():
    """AC-S3-2: "Tier 2: L3 needs 50, its own PO line received 40, L2's PO line has 20
    spare (40 received, L2 needs 20): L3's composition is Reserve 50 (40 own + 10 from the
    order's spare), Buy 0."
    """
    with blank_session() as db:
        group, product = own_arrival_group(db)
        own = own_arrival_warehouse(db, group)
        _board_stock(db, product, own, on_hand=100)
        mine, (l2, l3) = order_with_lines(
            db, product=product, warehouse=own,
            lines=[
                {"qty": "20", "required_date": L2_REQUIRED, "source_ref": "L2"},
                {"qty": "50", "required_date": L3_REQUIRED, "source_ref": "L3"},
            ],
        )
        po2 = supplier_and_po(db, po_number="ZZT-PO-L2")
        po_line_bought_for(
            db, po2, product, own, from_so_line_ref="L2", qty_received=40, qty_ordered=40,
        )
        po3 = supplier_and_po(db, po_number="ZZT-PO-L3")
        po_line_bought_for(
            db, po3, product, own, from_so_line_ref="L3", qty_received=40, qty_ordered=40,
        )
        order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "5000", "required_date": date(2026, 4, 1), "source_ref": "OTHER"}],
        )

        board = _service(db).build([mine.so_number], granularity="week", as_of=TODAY)
        cell = _cell(board, product.product_code, "2026-08-24")
        contribution = cell["contributions"][0]

        reserved = sum((Decimal(s["qty"]) for s in _reserve_sources(contribution)), Decimal("0"))
        assert reserved == Decimal("50"), contribution["sources"]
        assert _buy_qty(contribution) == Decimal("0"), contribution["sources"]


def test_ac_s3_3_the_credit_is_capped_by_on_hand_at_the_location():
    """AC-S3-3: "The credit is capped by on hand: on hand at the location 30, own PO line
    received 40, line needs 40: Reserve 30, remainder follows today's ladder (Buy 10 or
    pool)."
    """
    with blank_session() as db:
        group, product = own_arrival_group(db)
        own = own_arrival_warehouse(db, group)
        _board_stock(db, product, own, on_hand=30)
        mine, (l2,) = order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "40", "required_date": L2_REQUIRED, "source_ref": "L2"}],
        )
        po = supplier_and_po(db, po_number="ZZT-PO-CAP")
        po_line_bought_for(
            db, po, product, own, from_so_line_ref="L2", qty_received=40, qty_ordered=40,
        )
        order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "5000", "required_date": date(2026, 4, 1), "source_ref": "OTHER"}],
        )

        board = _service(db).build([mine.so_number], granularity="week", as_of=TODAY)
        cell = _cell(board, product.product_code, "2026-08-17")
        contribution = cell["contributions"][0]

        reserved = sum((Decimal(s["qty"]) for s in _reserve_sources(contribution)), Decimal("0"))
        assert reserved == Decimal("30"), contribution["sources"]
        assert _buy_qty(contribution) == Decimal("10"), contribution["sources"]


def test_ac_s3_4_credit_is_never_double_counted_against_the_shared_on_hand_ledger():
    """AC-S3-4: "Credit is never double counted: after L2 takes 20 and L3 takes 50, the
    location's free figure offered to the other order is reduced by 70."

    Simplified to what is directly observable off ONE board build without a second HTTP
    round trip (the plan's own `_own_pool_floor` ledger is internal): on hand is 50, less
    than the two lines' COMBINED theoretical credit (20 + 60 = 80), so a walk that fails to
    carry L2's 20 already drawn into L3's own cap would let L3 draw up to 40 (its own PO's
    tier-1 share alone) rather than the 30 actually left (50 - 20). Pinned as an exact sum:
    Reserve(L2) + Reserve(L3) == 50 (on hand), never more.
    """
    with blank_session() as db:
        group, product = own_arrival_group(db)
        own = own_arrival_warehouse(db, group)
        _board_stock(db, product, own, on_hand=50)
        mine, (l2, l3) = order_with_lines(
            db, product=product, warehouse=own,
            lines=[
                {"qty": "20", "required_date": L2_REQUIRED, "source_ref": "L2"},
                {"qty": "50", "required_date": L3_REQUIRED, "source_ref": "L3"},
            ],
        )
        po2 = supplier_and_po(db, po_number="ZZT-PO-L2B")
        po_line_bought_for(
            db, po2, product, own, from_so_line_ref="L2", qty_received=40, qty_ordered=40,
        )
        po3 = supplier_and_po(db, po_number="ZZT-PO-L3B")
        po_line_bought_for(
            db, po3, product, own, from_so_line_ref="L3", qty_received=40, qty_ordered=40,
        )
        order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "5000", "required_date": date(2026, 4, 1), "source_ref": "OTHER"}],
        )

        board = _service(db).build([mine.so_number], granularity="week", as_of=TODAY)
        l2_cell = _cell(board, product.product_code, "2026-08-17")
        l3_cell = _cell(board, product.product_code, "2026-08-24")
        l2_reserved = sum(
            (Decimal(s["qty"]) for s in _reserve_sources(l2_cell["contributions"][0])), Decimal("0"),
        )
        l3_reserved = sum(
            (Decimal(s["qty"]) for s in _reserve_sources(l3_cell["contributions"][0])), Decimal("0"),
        )
        assert l2_reserved + l3_reserved == Decimal("50"), (l2_reserved, l3_reserved)
        assert l3_reserved == Decimal("30"), (
            "L3's own tier-1 40 must already be capped by what L2's own credit left of the "
            f"shared 50 on hand (30), not read the location as if L2 took nothing: {l3_reserved}"
        )


def test_ac_s3_5_a_closed_lines_spare_is_net_of_its_own_qty_ordered():
    """AC-S3-5: "Delivered lines do not count: a closed line's PO receipt is net of that
    line's `qty_ordered` before it becomes tier-2 spare (L1: 39 received, 9 delivered ->
    30 spare)."
    """
    with blank_session() as db:
        group, product = own_arrival_group(db)
        own = own_arrival_warehouse(db, group)
        _board_stock(db, product, own, on_hand=30)
        mine, (l1, l2) = order_with_lines(
            db, product=product, warehouse=own,
            lines=[
                {
                    "qty": "9", "required_date": date(2026, 8, 10), "source_ref": "L1",
                    "line_status": "closed", "delivered": "9",
                },
                {"qty": "20", "required_date": L2_REQUIRED, "source_ref": "L2"},
            ],
        )
        po1 = supplier_and_po(db, po_number="ZZT-PO-L1SPARE")
        po_line_bought_for(
            db, po1, product, own, from_so_line_ref="L1", qty_received=39, qty_ordered=39,
        )
        order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "5000", "required_date": date(2026, 4, 1), "source_ref": "OTHER"}],
        )

        board = _service(db).build([mine.so_number], granularity="week", as_of=TODAY)
        cell = _cell(board, product.product_code, "2026-08-17")
        contribution = cell["contributions"][0]

        reserved = sum((Decimal(s["qty"]) for s in _reserve_sources(contribution)), Decimal("0"))
        assert reserved == Decimal("20"), (
            "L2's whole 20 must come from L1's 30-unit spare (39 received - 9 already "
            f"delivered), not read 0: {contribution['sources']}"
        )
        assert _buy_qty(contribution) == Decimal("0"), contribution["sources"]


def test_ac_s3_6_amend_refuses_a_buy_over_an_own_arrival_reserve(api):
    """AC-S3-6: "`set_row_decision` / amend that turns an own-arrival Reserve into a Buy
    is refused with `planning_change_buy_over_own_arrival` and a message naming N and the
    PO; amending the remainder ... to Buy is allowed."

    `row.proposal_json` is hand-built rather than driven through a live ladder walk (the
    contract choices at the top of this file name the exact shape): a single `reserve`
    source tagged `source: own_arrival`, `supply_document` naming the PO. The amend tries
    to convert the whole 20 to a Buy.
    """
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20",
                            required_date=date(2027, 6, 1))
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
        kind="qty_up", from_json={}, to_json={"qty": "20"}, facts_json={},
        proposal_json={
            "project_line_id": str(line.id), "qty": "20",
            "qty_proposed_reserve": "20", "qty_proposed_buy": "0",
            "qty_proposed_incoming": "0",
            "sources": [{
                "kind": "reserve", "qty": "20", "location": world.own_wh.warehouse_code,
                "warehouse_id": str(world.own_wh.id), "rung": "group_take",
                "source": "own_arrival", "supply_document": "ZZT-PO-OWNARR6",
            }],
        },
        decision=None, applied_state="pending",
    )
    db.add(row)
    db.commit()

    composition = {
        "project_line_id": str(line.id), "timely_spo_qty": "0", "reserve": [], "borrow": [],
        "buy_qty": "20", "buy_reason": "ZZT trying to buy over own-arrival stock",
        "amend_reason": "ZZT testing the refusal",
    }
    try:
        planning_change_service.set_row_decision(db, str(batch.id), str(row.id), "amend", composition)
    except AppException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        assert detail.get("code") == "planning_change_buy_over_own_arrival", detail
        message = str(detail.get("message"))
        assert "20" in message, message
        assert "ZZT-PO-OWNARR6" in message, message
    else:
        assert False, "expected planning_change_buy_over_own_arrival"


def _path_picker_world(db, world, *, on_hand):
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                            required_date=date(2027, 6, 1))
    core_line.source_ref = f"ZZT-PATHPICK-{_uid()[:8]}"
    db.flush()
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    po = supplier_and_po(db, po_number=f"ZZT-PO-PATHPICK-{_uid()[:8]}")
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


def test_ac_s3_7_path_b_settles_in_place_when_own_arrival_credit_covers_the_link(api):
    """AC-S3-7: "Path B: a replanned row linked 40 to a received SPO allocation, own
    landed 40 on hand: the row is settled in place, link kept, note gains "Was {qty} on
    {date}", `redirected_to_pool` stays false, no fresh row is raised."

    `_redirect_row_if_received` (`project_order_inquiry_service.py`, the S2 decline rule
    of `PLAN-oi-replan-received-links.md`) is called directly - it is the function the
    plan names as the seam, and the ONLY part of "settle in place" this AC actually asks a
    NEW check of (the Was/Now note itself is `_settle_row_in_place`'s own continuation once
    this returns `None`, already covered by that existing, unrelated mechanism).
    """
    client, world = api
    db = world.db
    row, link, decision, po = _path_picker_world(db, world, on_hand=40)

    svc = ProjectOrderInquiryService(db)
    result = svc._redirect_row_if_received(row, [link], decision)

    assert result is None, (
        "own-arrival credit (40, capped by 40 on hand) covers the linked 40: settle in "
        f"place, never redirect: {result}"
    )
    db.expire_all()
    fresh = db.get(OrderInquiryRow, row.id)
    assert fresh.redirected_to_pool is False, fresh.redirected_to_pool


def test_ac_s3_8_path_a_still_redirects_when_on_hand_falls_short_of_the_link(api):
    """AC-S3-8: "Path A: same row, on hand at the location 10: today's behaviour,
    `redirected_to_pool` true, fresh row raised, note carries "released at revision N"."

    Named "today's behaviour" in the UAC itself - this is the boundary partner of
    AC-S3-7, pinning the side of R2's rule that does NOT change, so a coder's fix that
    settles EVERY received link in place (ignoring the on-hand cap) is caught here rather
    than only being under-tested.
    """
    client, world = api
    db = world.db
    row, link, decision, po = _path_picker_world(db, world, on_hand=10)

    svc = ProjectOrderInquiryService(db)
    result = svc._redirect_row_if_received(row, [link], decision)

    assert result is not None, (
        "own-arrival credit capped by 10 on hand cannot cover the linked 40: today's "
        "redirect-to-pool path must still fire"
    )
    db.expire_all()
    fresh = db.get(OrderInquiryRow, row.id)
    assert fresh.redirected_to_pool is True, fresh.redirected_to_pool
    assert fresh.note and f"released at revision {decision.revision_no}" in fresh.note, fresh.note


def test_ac_s3_9_the_board_reads_received_for_a_settled_row_and_never_a_reallocate(api):
    """AC-S3-9: "The board reads Received for a Path B row (line summary carries the
    received link qty) and never shows a Reallocate sentence for it."

    End to end off a REAL `OrderInquiryLink` to a received SPO allocation (unlike
    AC-S2-2's pure-function unit test): `_placed_links` reads the link back as
    `received_qty`, and `compose_suggestion`, fed that fact for a line still wanting the
    same 40, composes a `keep` naming "Received" - never a `reallocate`.
    """
    client, world = api
    db = world.db
    row, link, decision, po = _path_picker_world(db, world, on_hand=40)

    placed = planning_change_service._placed_links(db, str(row.so_line_id))
    assert placed.get("received_qty") == "40", placed
    assert placed.get("po_qty") == "0", placed

    facts = {
        "placed": placed,
        "reallocate_to": "pool",
        "new_date": date(2027, 6, 1).isoformat(),
        "immediate": False,
    }
    proposal = {"sources": [{"kind": "buy", "qty": "0"}], "qty_proposed_buy": "0"}
    suggestion = planning_change_service.compose_suggestion("delayed", None, proposal, facts)

    components = suggestion["components"]
    assert not any(c["action"] == "reallocate" for c in components), components
    keep = next((c for c in components if c["action"] == "keep"), None)
    assert keep is not None, components
    assert keep["label"] == f"Received {link.document} 40", keep
