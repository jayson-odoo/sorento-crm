"""R7 follow-up: own-arrival credit reads what LANDED on the SPO, never what the PO
merely TRANSFERRED.

`documentation/plans/scm/PLAN-r7-landed-reads-spo-received.md`, UAC
`r7-landed-reads-spo-received-acceptance-criteria.md` AC-1..AC-8.

The defect, measured on prod (SO399639 line 58 / core line 2120, C-FHSS18, 24 Sep 2026):
`purchase_order_lines.qty_received` is the AutoCount TRANSFER of a PO line onto a shipping
order, never a physical receipt - every PO in this business is received through an SPO.
What actually landed is `spo_allocations.quantity_received`, resolved off the PO line's own
`source_ref` via `spo_allocations.from_po_line_ref`.

Postgres only (`tests/_pg_fixture.py`), every FK seeded here, never a borrowed row.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.procurement import PurchaseOrderLine
from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services.error_handler import AppException
from app.services.project_supply_service import ProjectSupplyService, _LineFacts

from tests._pg_fixture import blank_session
from tests.scm._own_arrival_fixture import (
    own_arrival_group,
    own_arrival_warehouse,
    order_with_lines,
    po_line_bought_for,
    supplier_and_po,
)
from tests.scm.test_board_received_stock_s3_own_arrival import L2_REQUIRED
from tests.scm.test_project_supply_service_ladder import _world
from tests.test_fulfilment_board import TODAY, _cell, _product, _service
from tests.test_fulfilment_board import _stock as _board_stock
from tests.test_so_supply_confirmation import (  # noqa: F401  (helpers, not fixtures)
    _core_line,
    _core_so,
    _project_line,
    _project_so,
    _stock,
    _uid,
    _warehouse,
)


def test_t1_po_transferred_zero_spo_received_confirm_buy_succeeds():
    """T1 (AC-1, the SO399639 shape): PO line fully TRANSFERRED
    (`qty_received = qty_ordered = 7`), its SPO row `quantity_received = 0`, on hand at
    the line's own bin 1. Nothing has physically landed (R1), so the own-arrival credit
    is 0 and confirming a Buy for the line's whole open quantity (7) succeeds - no
    refusal.
    """
    within_window = date.today() + timedelta(days=10)
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        own = _warehouse(db, f"ZZT-OWN-{_uid()[:4]}")
        _stock(db, product, own, on_hand=1)

        core_so = _core_so(db, company_id)
        core_line = _core_line(
            db, core_so, product, own, qty_ordered="7", required_date=within_window,
        )
        core_line.source_ref = f"ZZT-T1-{_uid()[:8]}"
        db.flush()
        po = supplier_and_po(db, po_number=f"ZZT-PO-T1-{_uid()[:8]}")
        po_line_bought_for(
            db, po, product, own, from_so_line_ref=core_line.source_ref,
            qty_received=7, qty_ordered=7, spo_received=0,
        )

        order = _project_so(db, project, so_id=core_so.id)
        line = _project_line(db, order, line_no=1, product=product, core_line=core_line)
        db.commit()

        result = ProjectSupplyService(db).confirm(
            order,
            ConfirmSupplyBody(
                lines=[ConfirmLine(project_line_id=str(line.id), buy_qty="7")]
            ),
            actor_user_id=actor,
        )
    assert result["exceptions"] == [], result
    assert result["lines_decided"] == 1, result


def test_t2_spo_received_refusal_names_the_spo_number_never_the_po():
    """T2 (AC-2, AC-8): same shape, but the SPO row's own `quantity_received = 7`, on
    hand 7 - the credit is a clean 7. Confirming a Buy for the whole line, with no
    Reserve at the credited bin, is refused, and the message names the SPO number - never
    the PO number (R3).
    """
    within_window = date.today() + timedelta(days=10)
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        own = _warehouse(db, f"ZZT-OWN-{_uid()[:4]}")
        _stock(db, product, own, on_hand=7)

        core_so = _core_so(db, company_id)
        core_line = _core_line(
            db, core_so, product, own, qty_ordered="7", required_date=within_window,
        )
        core_line.source_ref = f"ZZT-T2-{_uid()[:8]}"
        db.flush()
        po = supplier_and_po(db, po_number=f"ZZT-PO-T2-{_uid()[:8]}")
        _po_line, spo = po_line_bought_for(
            db, po, product, own, from_so_line_ref=core_line.source_ref,
            qty_received=7, qty_ordered=7, spo_received=7,
        )
        # Captured as plain strings while `db` is still open - `spo`/`po` are
        # DETACHED once `blank_session()` closes below, and both objects had every
        # attribute expired by the `db.commit()` a few lines down.
        spo_number, po_number = spo.spo_number, po.po_number

        order = _project_so(db, project, so_id=core_so.id)
        line = _project_line(db, order, line_no=1, product=product, core_line=core_line)
        db.commit()

        with pytest.raises(AppException) as refused:
            ProjectSupplyService(db).confirm(
                order,
                ConfirmSupplyBody(
                    lines=[ConfirmLine(project_line_id=str(line.id), buy_qty="7")]
                ),
                actor_user_id=actor,
            )

    assert refused.value.status_code == 409, refused.value.detail
    assert refused.value.detail.get("code") == "planning_change_buy_over_own_arrival", (
        refused.value.detail
    )
    message = refused.value.detail.get("message") or ""
    assert "7" in message and spo_number in message, message
    assert po_number not in message, (
        f"the refusal must name the document goods landed on (the SPO), never the PO: "
        f"message={message!r}"
    )


def test_t3_po_received_with_no_spo_row_contributes_nothing():
    """T3 (AC-3): a PO line with `qty_received = 7` and NO SPO row naming it (its own
    `source_ref`, as `spo_allocations.from_po_line_ref`) contributes 0 to the credit -
    `purchase_order_lines.qty_received` alone is never "landed" (R1). Confirming a Buy
    for the whole line succeeds.
    """
    within_window = date.today() + timedelta(days=10)
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        own = _warehouse(db, f"ZZT-OWN-{_uid()[:4]}")
        _stock(db, product, own, on_hand=7)

        core_so = _core_so(db, company_id)
        core_line = _core_line(
            db, core_so, product, own, qty_ordered="7", required_date=within_window,
        )
        core_line.source_ref = f"ZZT-T3-{_uid()[:8]}"
        db.flush()
        po = supplier_and_po(db, po_number=f"ZZT-PO-T3-{_uid()[:8]}")
        db.add(PurchaseOrderLine(
            id=_uid(), purchase_order_id=po.id, product_id=product.id, warehouse_id=own.id,
            qty_ordered=Decimal("7"), qty_received=Decimal("7"), line_status="closed",
            from_so_line_ref=core_line.source_ref,
        ))
        db.flush()

        order = _project_so(db, project, so_id=core_so.id)
        line = _project_line(db, order, line_no=1, product=product, core_line=core_line)
        db.commit()

        result = ProjectSupplyService(db).confirm(
            order,
            ConfirmSupplyBody(
                lines=[ConfirmLine(project_line_id=str(line.id), buy_qty="7")]
            ),
            actor_user_id=actor,
        )
    assert result["exceptions"] == [], result
    assert result["lines_decided"] == 1, result


def test_t4_tier2_spare_off_spo_received_ignores_sibling_po_decoy():
    """T4 (AC-4): a closed sibling's SPO row received 12 against ordered 10 -> spare 2
    credited to the open line; the sibling's own PO `qty_received` (a decoy, EQUAL to
    `qty_ordered`, the shape a fully-transferred-but-not-yet-landed line actually carries)
    does not change that (R1).

    Fix round B1: the decoy is deliberately EQUAL to `qty_ordered` (10), not larger. A
    revert to reading `PurchaseOrderLine.qty_received` computes spare = 10 - min(10, 10)
    = 0, short of the 2 the open line needs, so it has to Buy 2 - the decoy has to be
    small enough to make the reverted answer WRONG, or this test cannot tell a correct
    fix from a broken one (reviewer, fix round 1: the original 99-unit decoy still left
    89 units of spare after netting, far more than the 2 needed, so both readings passed
    it by coincidence).
    """
    with blank_session() as db:
        group, product = own_arrival_group(db)
        own = own_arrival_warehouse(db, group)
        _board_stock(db, product, own, on_hand=200)
        mine, (l1, l2) = order_with_lines(
            db, product=product, warehouse=own,
            lines=[
                {
                    "qty": "10", "required_date": date(2026, 8, 10), "source_ref": "T4-L1",
                    "line_status": "closed", "delivered": "10",
                },
                {"qty": "2", "required_date": L2_REQUIRED, "source_ref": "T4-L2"},
            ],
        )
        po1 = supplier_and_po(db, po_number="ZZT-PO-T4-L1")
        po_line_bought_for(
            db, po1, product, own, from_so_line_ref="T4-L1",
            qty_received=10, qty_ordered=10, spo_received=12,
        )
        order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "5000", "required_date": date(2026, 4, 1), "source_ref": "T4-OTHER"}],
        )

        board = _service(db).build([mine.so_number], granularity="week", as_of=TODAY)
        cell = _cell(board, product.product_code, "2026-08-17")
        contribution = cell["contributions"][0]

        reserved = sum(
            (
                Decimal(s["qty"]) for s in contribution["sources"]
                if s.get("rung") == "group_take"
            ),
            Decimal("0"),
        )
        assert reserved == Decimal("2"), (
            "L2's whole 2 must come from L1's 2-unit spare (SPO received 12 - ordered "
            "10), not a spare of 0 read off the decoy PO qty_received=10 (== qty_ordered, "
            f"a transfer, never a receipt): {contribution['sources']}"
        )
        buy = sum(
            (Decimal(s["qty"]) for s in contribution["sources"] if s.get("kind") == "buy"),
            Decimal("0"),
        )
        assert buy == Decimal("0"), contribution["sources"]


def test_t5_prefetch_and_single_read_agree():
    """T5 (AC-5): `_prefetch_own_arrival` (the batched read `walk()` uses) and
    `_po_received_by_so_line_ref` (the single read `own_arrival_credit_for` uses) return
    the SAME (qty, document) for the same line.

    Fix round B1: `qty_received` (the PO's own transfer, 40) and `spo_received` (what
    actually landed, 5) are DELIBERATELY split. The fixture used to default
    `spo_received` to `qty_received`, so both reads agreed at 40 whether they read the
    PO's transfer or the SPO's receipt - a revert of the batched read back to
    `PurchaseOrderLine.qty_received` still passed this test (reviewer, fix round 1). The
    board build at the end pins the WALK path itself (`_prefetch_own_arrival`, not only
    the raw dict this test also reads directly) to the same 5-unit figure.
    """
    with blank_session() as db:
        group, product = own_arrival_group(db)
        own = own_arrival_warehouse(db, group)
        _board_stock(db, product, own, on_hand=200)
        mine, (l2,) = order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "20", "required_date": L2_REQUIRED, "source_ref": "T5-L2"}],
        )
        po = supplier_and_po(db, po_number="ZZT-PO-T5")
        _po_line, spo = po_line_bought_for(
            db, po, product, own, from_so_line_ref="T5-L2",
            qty_received=40, qty_ordered=40, spo_received=5,
        )
        spo_number = spo.spo_number

        service = ProjectSupplyService(db)
        single = service._po_received_by_so_line_ref(
            [l2.source_ref], product_id=str(l2.product_id), company_id=l2.company_id,
        )

        fact = _LineFacts(
            unit_core_line_ids=[str(l2.id)], sales_order_id=str(l2.sales_order_id),
            product_id=str(l2.product_id), source_ref=l2.source_ref,
            line_company_id=l2.company_id,
        )
        service._prefetch_own_arrival([(None, fact, None)])
        key = (str(l2.sales_order_id), str(l2.product_id), str(l2.company_id or ""))
        _siblings, batched = service._own_arrival_order_memo[key]

        assert single.get(l2.source_ref) == (Decimal("5"), spo_number), single
        assert batched.get(l2.source_ref) == (Decimal("5"), spo_number), batched
        assert single.get(l2.source_ref) == batched.get(l2.source_ref), (
            f"single read={single} batched read={batched}"
        )

        order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "5000", "required_date": date(2026, 4, 1), "source_ref": "T5-OTHER"}],
        )
        board = _service(db).build([mine.so_number], granularity="week", as_of=TODAY)
        cell = _cell(board, product.product_code, "2026-08-17")
        contribution = cell["contributions"][0]
        own_arrival_qty = sum(
            (
                Decimal(s["qty"]) for s in contribution["sources"]
                if s.get("source") == "own_arrival"
            ),
            Decimal("0"),
        )
        assert own_arrival_qty == Decimal("5"), (
            f"the WALK path (batched read) must credit the SPO's own 5, not the PO's "
            f"40-unit transfer: {contribution['sources']}"
        )


def test_t6_board_batched_path_zero_spo_received_yields_no_own_arrival_candidate():
    """Fix round B1 (guard for the SO399639 shape on the BATCHED read path): T1 only
    pins the single-read/confirm path (`own_arrival_credit_for` -> `_po_received_by_
    so_line_ref`, called fresh with no prefetch). This drives the SAME shape - PO line
    transferred (`qty_received = qty_ordered = 7`), its SPO row `quantity_received = 0`
    - through the BOARD, whose `walk()` reads `_prefetch_own_arrival` instead. A
    competing order at the same location drives the group net negative, the same shape
    AC-S3-1 measures the ladder's correct answer against: the board must draw NO
    own-arrival credit and compose a pure Buy 7, never read the PO's own transfer as
    landed.
    """
    with blank_session() as db:
        group, product = own_arrival_group(db)
        own = own_arrival_warehouse(db, group)
        _board_stock(db, product, own, on_hand=1)
        mine, (l2,) = order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "7", "required_date": L2_REQUIRED, "source_ref": "T6-L2"}],
        )
        po = supplier_and_po(db, po_number="ZZT-PO-T6")
        po_line_bought_for(
            db, po, product, own, from_so_line_ref="T6-L2",
            qty_received=7, qty_ordered=7, spo_received=0,
        )
        order_with_lines(
            db, product=product, warehouse=own,
            lines=[{"qty": "5000", "required_date": date(2026, 4, 1), "source_ref": "T6-OTHER"}],
        )

        board = _service(db).build([mine.so_number], granularity="week", as_of=TODAY)
        cell = _cell(board, product.product_code, "2026-08-17")
        contribution = cell["contributions"][0]

        own_arrival_sources = [
            s for s in contribution["sources"] if s.get("source") == "own_arrival"
        ]
        assert own_arrival_sources == [], (
            "the PO line's own qty_received=7 is a TRANSFER, never a receipt (R1); "
            "nothing has landed on the SPO (quantity_received=0), so the batched read "
            f"must credit nothing: {contribution['sources']}"
        )
        buy = sum(
            (Decimal(s["qty"]) for s in contribution["sources"] if s.get("kind") == "buy"),
            Decimal("0"),
        )
        assert buy == Decimal("7"), contribution["sources"]



def test_s2_cross_product_spo_row_contributes_nothing_in_both_reads():
    """Fix round S2 (AC-6): an SPO row naming this PO line's own `source_ref` as its
    `from_po_line_ref`, but for a DIFFERENT product, contributes 0 - in the single read
    (`_po_received_by_so_line_ref`) AND the batched one (`_prefetch_own_arrival`).

    Two products in the SAME batched call on purpose: `_prefetch_own_arrival`'s outer
    WHERE already narrows to `SPOAllocation.product_id.in_(product_ids)` - the whole
    WALK's product set - so a single-product fixture would pass even without the
    per-row `SPOAllocation.product_id == PurchaseOrderLine.product_id` JOIN condition,
    simply because the wrong product was never in that set to begin with (measured
    directly: the original, single-product version of this test stayed green with the
    join condition removed). Product Y has to be a REAL member of the same batch (its
    own line, `line_y`) for the WHERE alone to stop shielding line X's read.
    """
    from app.models.procurement import SPOAllocation

    from tests.test_fulfilment_board import _line, _order

    with blank_session() as db:
        group, product_x = own_arrival_group(db)
        own = own_arrival_warehouse(db, group)
        product_y = _product(db, f"ZZT-S2P-Y-{_uid()[:8]}")
        order = _order(db, so_number=f"ZZT-SO-S2P-{_uid()[:8]}")
        line_x = _line(db, order, product_x, qty="20", required_date=L2_REQUIRED, warehouse=own)
        line_x.source_ref = "S2P-LX"
        line_y = _line(db, order, product_y, qty="5", required_date=L2_REQUIRED, warehouse=own)
        line_y.source_ref = "S2P-LY"
        db.flush()

        po = supplier_and_po(db, po_number="ZZT-PO-S2P")
        po_line = PurchaseOrderLine(
            id=_uid(), purchase_order_id=po.id, product_id=product_x.id, warehouse_id=own.id,
            qty_ordered=Decimal("40"), qty_received=Decimal("40"), line_status="closed",
            from_so_line_ref="S2P-LX", source_ref=f"AED_SORENTO:9000:{_uid()[:8]}",
        )
        db.add(po_line)
        db.flush()
        # The WRONG-product SPO row: same `from_po_line_ref` as line X's own PO line,
        # but product Y's own id - product Y is a real member of this batch (line_y),
        # so the outer `.in_(product_ids)` WHERE alone cannot exclude it.
        spo = SPOAllocation(
            id=_uid(), spo_number="ZZT-SPO-S2P", spo_line_number=1,
            product_id=product_y.id, warehouse_id=own.id, location_code=own.warehouse_code,
            allocated_quantity=40, quantity_received=40, receipt_status="fully_received",
            line_status="closed", from_po_line_ref=po_line.source_ref,
            from_po_number=po.po_number, company_id=po_line.company_id,
        )
        db.add(spo)
        db.flush()

        service = ProjectSupplyService(db)
        single = service._po_received_by_so_line_ref(
            ["S2P-LX"], product_id=str(product_x.id), company_id=line_x.company_id,
        )
        assert single.get("S2P-LX", (Decimal("0"), None))[0] == Decimal("0"), single

        fact_x = _LineFacts(
            unit_core_line_ids=[str(line_x.id)], sales_order_id=str(line_x.sales_order_id),
            product_id=str(line_x.product_id), source_ref=line_x.source_ref,
            line_company_id=line_x.company_id,
        )
        fact_y = _LineFacts(
            unit_core_line_ids=[str(line_y.id)], sales_order_id=str(line_y.sales_order_id),
            product_id=str(line_y.product_id), source_ref=line_y.source_ref,
            line_company_id=line_y.company_id,
        )
        service._prefetch_own_arrival([(None, fact_x, None), (None, fact_y, None)])
        key_x = (
            str(line_x.sales_order_id), str(line_x.product_id), str(line_x.company_id or ""),
        )
        _siblings, batched = service._own_arrival_order_memo[key_x]
        assert batched.get("S2P-LX", (Decimal("0"), None))[0] == Decimal("0"), batched


def test_s2_cross_company_spo_row_contributes_nothing_in_both_reads():
    """Fix round S2 (AC-6): an SPO row naming this PO line's own `source_ref`, for the
    SAME product, but a DIFFERENT company, contributes 0 - in both reads.

    Read under `company_scope(db, None)` (the "all companies" / system scope) on
    purpose: the test suite's own default single-company scope (`tests/conftest.py`)
    auto-injects a `company_id`-filtered `with_loader_criteria` on EVERY SELECT against
    a `CompanyScopedMixin` table, which would hide the other company's SPO row from the
    query before either read's own logic ever runs - the read would look correct for a
    reason that has nothing to do with the code under test (measured directly: the
    original version of this test, under the default scope, stayed green with the
    join's company condition removed). Under an unscoped read, only the explicit
    `company_id` filters - the single read's own, stated since round 1, and the
    batched read's join condition, added this round - stop the cross-company match.
    """
    from app.models.base import company_scope
    from app.models.procurement import SPOAllocation

    from tests.test_fulfilment_board import _mocha

    with blank_session() as db:
        with company_scope(db, None):
            group, product = own_arrival_group(db)
            own = own_arrival_warehouse(db, group)
            mine, (l2,) = order_with_lines(
                db, product=product, warehouse=own,
                lines=[{"qty": "20", "required_date": L2_REQUIRED, "source_ref": "S2C-L2"}],
            )
            po = supplier_and_po(db, po_number="ZZT-PO-S2C")
            po_line = PurchaseOrderLine(
                id=_uid(), purchase_order_id=po.id, product_id=product.id, warehouse_id=own.id,
                qty_ordered=Decimal("40"), qty_received=Decimal("40"), line_status="closed",
                from_so_line_ref="S2C-L2", source_ref=f"AED_SORENTO:9000:{_uid()[:8]}",
            )
            db.add(po_line)
            db.flush()
            other_company_id = _mocha(db)
            spo = SPOAllocation(
                id=_uid(), spo_number="ZZT-SPO-S2C", spo_line_number=1,
                product_id=product.id, warehouse_id=own.id, location_code=own.warehouse_code,
                allocated_quantity=40, quantity_received=40, receipt_status="fully_received",
                line_status="closed", from_po_line_ref=po_line.source_ref,
                from_po_number=po.po_number, company_id=other_company_id,
            )
            db.add(spo)
            db.flush()

            service = ProjectSupplyService(db)
            single = service._po_received_by_so_line_ref(
                ["S2C-L2"], product_id=str(product.id), company_id=l2.company_id,
            )
            assert single.get("S2C-L2", (Decimal("0"), None))[0] == Decimal("0"), single

            fact = _LineFacts(
                unit_core_line_ids=[str(l2.id)], sales_order_id=str(l2.sales_order_id),
                product_id=str(l2.product_id), source_ref=l2.source_ref,
                line_company_id=l2.company_id,
            )
            service._prefetch_own_arrival([(None, fact, None)])
            key = (str(l2.sales_order_id), str(l2.product_id), str(l2.company_id or ""))
            _siblings, batched = service._own_arrival_order_memo[key]
            assert batched.get("S2C-L2", (Decimal("0"), None))[0] == Decimal("0"), batched
