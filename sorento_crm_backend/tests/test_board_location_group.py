"""The cell's stock table shows the AGENT'S ownership group, not only the line's warehouse.

The captain, reading a cell whose table held one row: the line names BRW-BB, but BRW-BB is one
of three warehouses belonging to the BB salespeople (BRW-BB / MWH-BB / DC1-BB), and "can I
fulfil this" is a question about the GROUP. A table that shows one of the three answers a
narrower question than the one being asked.

The group is `sales_agents.location_group` (PLAN-demo-followups-19aug-ladder-v2.md section 8),
matched against a warehouse code's own suffix by the ladder's existing rule
(`sales_agent_service.group_of_warehouse_code`) - so "which warehouses are the BB group" has ONE
definition in this codebase rather than a second one written here.

Three refusals, all of them stated rather than silent:

  * the agent holds no group -> the line's own location only, and the cell SAYS so;
  * the order names no agent -> the same, with its own sentence;
  * the line's warehouse is outside the group -> it is still listed. It is where the line
    actually is, and dropping it to show a tidy group would hide the only location that
    matters to that line.

Postgres, blank scratch schema, every FK target seeded here (PRINCIPLES).
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.sales_agent import SalesAgent

from ._pg_fixture import blank_session

MARKER = "zzt-board-group"
TODAY = date(2026, 8, 19)
BUCKET = "2026-08-31"


def _uid() -> str:
    return str(uuid.uuid4())


def _product(db) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(), product_code=f"ZZT-{_uid()[:6]}", product_name=f"{MARKER} basin",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, code: str) -> Warehouse:
    row = Warehouse(
        id=_uid(), warehouse_code=code, warehouse_name=code, is_active=True,
        segment="project",
    )
    db.add(row)
    db.flush()
    return row


def _stock(db, product: Product, warehouse: Warehouse, *, on_hand: str):
    db.add(Stock(
        id=_uid(), product_id=product.id, warehouse_id=warehouse.id,
        quantity_on_hand=Decimal(on_hand),
    ))
    db.flush()


def _agent(db, code: str, *, group: str | None) -> SalesAgent:
    row = SalesAgent(id=_uid(), sales_agent=code, location_group=group)
    db.add(row)
    db.flush()
    return row


def _order(db, *, agent: SalesAgent | None) -> SalesOrder:
    customer = Customer(
        id=_uid(), customer_code=f"ZZT-{_uid()[:8]}", customer_name=f"{MARKER} customer"
    )
    db.add(customer)
    db.flush()
    row = SalesOrder(
        id=_uid(), so_number=f"ZZT-SO-{_uid()[:8]}", customer_id=customer.id,
        sales_agent_id=agent.id if agent else None, order_date=date(2026, 1, 1),
        demand_class="project", status="open",
    )
    db.add(row)
    db.flush()
    return row


def _line(db, order: SalesOrder, product: Product, warehouse: Warehouse, *, qty: str = "10"):
    db.add(SalesOrderLine(
        id=_uid(), sales_order_id=order.id, product_id=product.id,
        warehouse_id=warehouse.id, qty_ordered=Decimal(qty), qty_delivered=Decimal("0"),
        required_date=date(2026, 9, 3), line_status="open",
        purchasing_status="not_reviewed",
    ))
    db.flush()


def _cell(db, order: SalesOrder, product: Product) -> dict:
    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    board = FulfilmentBoardService(db).build(
        [order.so_number], granularity="week", as_of=TODAY
    )
    return next(
        c for c in board["cells"]
        if c["item_code"] == product.product_code and c["bucket_key"] == BUCKET
    )


def _codes(cell: dict) -> list[str]:
    return [entry["location"] for entry in cell["locations"]]


def _by_code(cell: dict) -> dict:
    return {entry["location"]: entry for entry in cell["locations"]}


# --------------------------------------------------------------------------- #
# the group is listed whole
# --------------------------------------------------------------------------- #


def test_every_warehouse_of_the_agents_group_is_listed_not_only_the_lines_own():
    """Three BB warehouses, one line naming one of them: three rows."""
    with blank_session() as db:
        product = _product(db)
        brw = _warehouse(db, "BRW-BB")
        mwh = _warehouse(db, "MWH-BB")
        dc1 = _warehouse(db, "DC1-BB")
        _stock(db, product, brw, on_hand="40")
        _stock(db, product, mwh, on_hand="25")
        agent = _agent(db, f"ZZTB{_uid()[:4]}", group="BB")
        order = _order(db, agent=agent)
        _line(db, order, product, brw)

        cell = _cell(db, order, product)

        assert set(_codes(cell)) == {"BRW-BB", "MWH-BB", "DC1-BB"}
        # The line's own location leads: it is the one the order actually named.
        assert _codes(cell)[0] == "BRW-BB"
        assert cell["location_group"] == "BB"
        assert cell["location_group_note"] is None


def test_a_group_warehouse_with_no_demand_still_reports_what_it_holds():
    """The whole point of listing it: 25 sitting at MWH-BB is the fact that decides whether
    this line has to be bought at all."""
    with blank_session() as db:
        product = _product(db)
        brw = _warehouse(db, "BRW-BB")
        mwh = _warehouse(db, "MWH-BB")
        _stock(db, product, brw, on_hand="40")
        _stock(db, product, mwh, on_hand="25")
        agent = _agent(db, f"ZZTB{_uid()[:4]}", group="BB")
        order = _order(db, agent=agent)
        _line(db, order, product, brw)

        entry = _by_code(_cell(db, order, product))["MWH-BB"]

        assert Decimal(entry["qty_on_hand"]) == Decimal("25")
        # Addressable, so its documents can be opened like any other row's.
        assert entry["product_id"] == str(product.id)
        assert entry["warehouse_id"] == str(mwh.id)
        # No demand of this cell sits there, and the row says 0 rather than claiming some.
        assert Decimal(entry["qty_demand"]) == Decimal("0")


def test_a_group_warehouse_holding_nothing_is_listed_rather_than_dropped():
    """"Nothing at DC1-BB" is an answer; a missing row is not."""
    with blank_session() as db:
        product = _product(db)
        brw = _warehouse(db, "BRW-BB")
        _warehouse(db, "DC1-BB")
        _stock(db, product, brw, on_hand="40")
        agent = _agent(db, f"ZZTB{_uid()[:4]}", group="BB")
        order = _order(db, agent=agent)
        _line(db, order, product, brw)

        assert "DC1-BB" in _codes(_cell(db, order, product))


def test_a_location_outside_the_group_is_kept_because_the_line_is_there():
    """The line names KCH-XX and the agent's group is BB: four rows, not three."""
    with blank_session() as db:
        product = _product(db)
        outside = _warehouse(db, "KCH-XX")
        brw = _warehouse(db, "BRW-BB")
        mwh = _warehouse(db, "MWH-BB")
        _stock(db, product, outside, on_hand="7")
        _stock(db, product, brw, on_hand="40")
        _stock(db, product, mwh, on_hand="25")
        agent = _agent(db, f"ZZTB{_uid()[:4]}", group="BB")
        order = _order(db, agent=agent)
        _line(db, order, product, outside)

        cell = _cell(db, order, product)

        assert set(_codes(cell)) == {"KCH-XX", "BRW-BB", "MWH-BB"}
        assert _codes(cell)[0] == "KCH-XX"


# --------------------------------------------------------------------------- #
# and when there is no group to list
# --------------------------------------------------------------------------- #


def test_an_agent_with_no_group_falls_back_to_the_lines_own_location_and_says_so():
    with blank_session() as db:
        product = _product(db)
        brw = _warehouse(db, "BRW-BB")
        _warehouse(db, "MWH-BB")
        _stock(db, product, brw, on_hand="40")
        agent = _agent(db, f"ZZTN{_uid()[:4]}", group=None)
        order = _order(db, agent=agent)
        _line(db, order, product, brw)

        cell = _cell(db, order, product)

        assert _codes(cell) == ["BRW-BB"]
        assert cell["location_group"] is None
        assert cell["location_group_note"] == f"Agent {agent.sales_agent} has no location group."


def test_an_order_with_no_agent_says_that_instead_of_naming_a_missing_one():
    with blank_session() as db:
        product = _product(db)
        brw = _warehouse(db, "BRW-BB")
        _warehouse(db, "MWH-BB")
        _stock(db, product, brw, on_hand="40")
        order = _order(db, agent=None)
        _line(db, order, product, brw)

        cell = _cell(db, order, product)

        assert _codes(cell) == ["BRW-BB"]
        assert cell["location_group"] is None
        assert cell["location_group_note"] == "No sales agent on the order, so no location group."


def test_a_group_typed_in_lower_case_still_matches_the_warehouse_suffix():
    """`normalize_location_group` is why: the suffix is upper by construction, the typed
    value is whatever the admin typed."""
    with blank_session() as db:
        product = _product(db)
        brw = _warehouse(db, "BRW-BB")
        mwh = _warehouse(db, "MWH-BB")
        _stock(db, product, brw, on_hand="40")
        _stock(db, product, mwh, on_hand="25")
        agent = _agent(db, f"ZZTL{_uid()[:4]}", group="bb")
        order = _order(db, agent=agent)
        _line(db, order, product, brw)

        cell = _cell(db, order, product)

        assert set(_codes(cell)) == {"BRW-BB", "MWH-BB"}
        assert cell["location_group"] == "BB"
