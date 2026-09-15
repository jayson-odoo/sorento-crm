"""S1 - a confirmed own-location allocation holds only what is STILL OWED.

`PLAN-fulfilment-board-plans-delivered-lines.md` S1, UAC AC-S1-1 to AC-S1-5.

TEST-FIRST: `owed_qty_expr()` and `_hold_query`'s `held_qty` column do not exist when this
file is written. What it pins is the arithmetic, not the spelling: a hold is
`least(alloc.qty, greatest(ordered - delivered, 0))`, zero on a cancelled line, and the
free-stock reader and the stock-debt screen read the SAME figure.

Why it matters. `so_line_allocations.qty` is frozen at confirm. Delivery does not shrink it,
and the book has ALREADY taken those units off `quantity_on_hand` - so a decided line that has
since shipped is subtracted twice, once by the warehouse and once by its own hold. Today that
bites nobody (97 decided lines on the 0907 copy, none with any delivery); the moment the board
plans delivered lines it is routine.

Postgres, blank scratch schema (`tests/_pg_fixture.py`), every FK target seeded here - company,
category, uom, product, warehouse, stock, core SO + line, the mirror record, its line, an
ACTIVE decision and the allocation. Nothing is borrowed off an existing row: CI's database is
empty.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.models.project_so import (
    DECISION_ACTIVE,
    SO_STATUS_ADOPTED,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOLineAllocation,
    SOSupplyDecision,
)

from ._pg_fixture import blank_session

MARKER = "zzt-holds"

#: Far enough out that no reserve-window rule is in play. Nothing here walks the ladder -
#: the allocation is written directly - but the core line still wants a plausible date.
REQUIRED_DATE = date.today() + timedelta(days=60)


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _product(db):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} basin",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db):
    from app.models.inventory import Warehouse

    code = f"ZZTH{_uid()[:8]}"[:20]
    row = Warehouse(
        id=_uid(),
        warehouse_code=code,
        warehouse_name=code,
        location="ZZT",
        is_active=True,
        segment="project",
        fulfilment_planning=True,
    )
    db.add(row)
    db.flush()
    return row


def _stock(db, product, warehouse, *, on_hand, reserved=0):
    from app.models.inventory import Stock

    row = Stock(
        id=_uid(),
        product_id=product.id,
        warehouse_id=warehouse.id,
        quantity_on_hand=Decimal(str(on_hand)),
        quantity_reserved=Decimal(str(reserved)),
    )
    db.add(row)
    db.flush()
    return row


def _decided_line(
    db,
    *,
    ordered: str,
    delivered: str,
    alloc_qty: str,
    line_status: str = "open",
    on_hand: str = "10",
):
    """One confirmed own-location allocation, on a core line with the stated delivery.

    Returns `(product, warehouse, core_line)` - everything an assertion below needs to name a
    pile and a line. The allocation belongs to an ACTIVE revision, which is the only shape
    `_hold_query` counts besides a pre-Stage-1C row with no decision at all.
    """
    from app.models.order import SalesOrder, SalesOrderLine

    company_id = _sorento(db)
    product = _product(db)
    warehouse = _warehouse(db)
    _stock(db, product, warehouse, on_hand=on_hand)

    core_so = SalesOrder(
        id=_uid(),
        company_id=company_id,
        so_number=f"ZZT-SO-{_uid()[:8]}",
        status="open",
        demand_class="project",
        order_date=date.today(),
    )
    db.add(core_so)
    db.flush()
    core_line = SalesOrderLine(
        id=_uid(),
        company_id=company_id,
        sales_order_id=core_so.id,
        product_id=product.id,
        warehouse_id=warehouse.id,
        qty_ordered=Decimal(ordered),
        qty_delivered=Decimal(delivered),
        required_date=REQUIRED_DATE,
        line_status=line_status,
    )
    db.add(core_line)
    db.flush()

    record = ProjectSalesOrder(
        id=_uid(),
        company_id=company_id,
        project_id=None,
        provisional_ref=core_so.so_number,
        autocount_doc_no=core_so.so_number,
        so_id=core_so.id,
        status=SO_STATUS_ADOPTED,
        grouping_origin="area",
    )
    db.add(record)
    db.flush()
    mirror = ProjectSalesOrderLine(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=record.id,
        line_no=1,
        product_id=product.id,
        description=f"{MARKER} mirror",
        qty=Decimal(ordered),
        uom="UNIT",
        unit_price=Decimal("100.00"),
        amount=Decimal("100.00"),
        delivery_date=REQUIRED_DATE,
        core_sales_order_line_id=core_line.id,
    )
    decision = SOSupplyDecision(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=record.id,
        revision_no=1,
        state=DECISION_ACTIVE,
        confirmed_at=datetime.utcnow(),
        line_snapshots=[{"core_line_id": str(core_line.id), "line_no": 1}],
    )
    db.add_all([mirror, decision])
    db.flush()
    db.add(
        SOLineAllocation(
            id=_uid(),
            company_id=company_id,
            so_line_id=mirror.id,
            source_type="own",
            warehouse_id=warehouse.id,
            qty=Decimal(alloc_qty),
            decision_id=decision.id,
            confirmed_at=datetime.utcnow(),
        )
    )
    db.flush()
    return product, warehouse, core_line


def _free(db, product, warehouse) -> Decimal:
    from app.services.project_supply_service import ProjectSupplyService

    free = ProjectSupplyService(db)._free_stock(
        [str(product.id)], exclude_line_ids=None
    )
    return free[(str(product.id), str(warehouse.id))]


# --------------------------------------------------------------------------- #
# AC-S1-1 to AC-S1-3, AC-S1-5 - the cap, through the free-stock arithmetic
# --------------------------------------------------------------------------- #


def test_hold_caps_at_still_owed_on_partial_delivery():
    """AC-S1-1. 3 allocated, 3 ordered, 1 shipped: the hold is 2.

    The shipped unit is already off `quantity_on_hand`. Holding 3 subtracts it a second time,
    which is stock the business has that no screen can see.
    """
    with blank_session() as db:
        product, warehouse, _core = _decided_line(
            db, ordered="3", delivered="1", alloc_qty="3", on_hand="10"
        )

        assert _free(db, product, warehouse) == Decimal("8"), (
            "10 on hand less a hold capped at the 2 still owed"
        )


def test_hold_is_zero_on_fully_delivered_line():
    """AC-S1-2. Nothing is owed, so nothing is held: the whole 10 is free."""
    with blank_session() as db:
        product, warehouse, _core = _decided_line(
            db, ordered="3", delivered="3", alloc_qty="3", on_hand="10"
        )

        assert _free(db, product, warehouse) == Decimal("10")


def test_hold_is_zero_on_cancelled_line_with_unreversed_delivery():
    """AC-S1-3. The book rarely reverses a delivered quantity when it cancels a line, so
    `ordered - delivered` alone does not read zero for one. A cancelled line owes nothing
    whatever those two columns say - the same rule `_open_of` already applies (R2c)."""
    with blank_session() as db:
        product, warehouse, _core = _decided_line(
            db,
            ordered="3",
            delivered="1",
            alloc_qty="3",
            line_status="cancelled",
            on_hand="10",
        )

        assert _free(db, product, warehouse) == Decimal("10")


def test_hold_unchanged_when_nothing_delivered():
    """AC-S1-5. The cap is a NO-OP above the delivered line: 3 allocated on 3 ordered and
    nothing shipped still holds 3, exactly as it does today."""
    with blank_session() as db:
        product, warehouse, _core = _decided_line(
            db, ordered="3", delivered="0", alloc_qty="3", on_hand="10"
        )

        assert _free(db, product, warehouse) == Decimal("7")


# --------------------------------------------------------------------------- #
# AC-S1-4 - one expression, two readers
# --------------------------------------------------------------------------- #


def test_stock_debt_holds_read_the_same_capped_qty():
    """AC-S1-4. The Stock Debt screen lists the holds the free-stock arithmetic nets off.

    It already shares the PREDICATE (`ProjectSupplyService._hold_query`, passed its own
    `entities`); the capped quantity has to travel with it or the screen prints 3 held beside
    a free figure computed from 2, and the arithmetic on screen stops closing.
    """
    from app.services.scm.stock_debt_service import StockDebtService

    with blank_session() as db:
        product, _warehouse, core_line = _decided_line(
            db, ordered="3", delivered="1", alloc_qty="3", on_hand="10"
        )

        holds = StockDebtService(db)._holds([str(product.id)], {str(core_line.id)})

        on_hand_holds = [h for h in holds if h.kind == "on_hand"]
        assert len(on_hand_holds) == 1, holds
        assert on_hand_holds[0].qty == 2.0, (
            "the screen has to list the same figure the free-stock read subtracted"
        )
