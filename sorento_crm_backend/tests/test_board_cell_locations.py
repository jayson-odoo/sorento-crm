"""The cell's location table lists the whole ladder: own, group, and EVERY site pool.

The captain, on SO415472 (PLAN-scm-cs-planning-uat.md section 0 item 2): "why is BRW the only
pool considered? What about MWH, DC1, WH3?" They WERE considered - `_pool_chain` walks every
active pool - but the table only ever listed a pool a proposal happened to cite, so a pool the
ladder looked at and took nothing from was indistinguishable from one it never opened. A row
reading 0 answers "why not MWH"; a missing row does not.

Three things are proved here (AC-B1 / AC-B2 / the PO qty column of section 3.B):

  * the ORDER and the `where` tag: the line's own location, then the agent's group siblings,
    then every active site pool with THIS line's own pool first;
  * a location with no stock row at all is listed with zeros, never dropped and never "not
    stated" - an absent stock row means zero on the last upload;
  * `po_open_qty`: the open PO balance at that location, netted for the order-inquiry rows
    already placed on those lines, with SPO documents excluded - and it reaches the wire,
    because `response_model` drops what the schema does not declare.

Postgres, blank scratch schema, every FK target seeded here (PRINCIPLES).
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    INQUIRY_PLACED,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
)
from app.models.sales_agent import SalesAgent
from app.schemas.project_board import BoardCell

from ._pg_fixture import blank_session

MARKER = "zzt-board-locations"
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


def _warehouse(db, code: str, *, pool: Warehouse | None = None) -> Warehouse:
    row = Warehouse(
        id=_uid(), warehouse_code=code, warehouse_name=code, is_active=True,
        segment="project", pool_warehouse_id=pool.id if pool else None,
    )
    db.add(row)
    db.flush()
    return row


def _sites(db, codes: list[str], group: str) -> tuple[dict, dict]:
    """One pool per site and one group bin under it, the shape the live book has.

    `BRW` is a warehouse in its own right AND the pool `BRW-BB` draws on, which is exactly
    what `pool_warehouse_id` states - the naming coincidence is not the rule.
    """
    pools = {code: _warehouse(db, code) for code in codes}
    bins = {
        code: _warehouse(db, f"{code}-{group}", pool=pools[code]) for code in codes
    }
    return pools, bins


def _stock(db, product: Product, warehouse: Warehouse, *, on_hand: str):
    db.add(Stock(
        id=_uid(), product_id=product.id, warehouse_id=warehouse.id,
        quantity_on_hand=Decimal(on_hand),
    ))
    db.flush()


def _agent(db, *, group: str | None) -> SalesAgent:
    row = SalesAgent(id=_uid(), sales_agent=f"ZZT{_uid()[:5]}", location_group=group)
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


def _po_line(
    db,
    product: Product,
    warehouse: Warehouse,
    *,
    ordered: str,
    received: str = "0",
    po_number: str | None = None,
    source_system: str | None = None,
) -> PurchaseOrderLine:
    po = PurchaseOrder(
        id=_uid(),
        po_number=po_number or f"ZZT-PO-{_uid()[:8]}",
        issue_date=date(2026, 7, 1),
        status="active",
        source_system=source_system,
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_uid(), purchase_order_id=po.id, product_id=product.id,
        warehouse_id=warehouse.id, qty_ordered=Decimal(ordered),
        qty_received=Decimal(received), line_status="open",
        expected_date=date(2026, 8, 25), source_system=source_system,
    )
    db.add(line)
    db.flush()
    return line


def _place(db, order: SalesOrder, po_line: PurchaseOrderLine, *, qty: str):
    """One order-inquiry row already linked to that PO line, which is what nets it down.

    Read off `order_inquiry_rows.po_line_id`, the only place a placement lives today.
    PLAN section I replaces it with `projects.order_inquiry_links`.
    """
    project = ProjectSalesOrder(
        id=_uid(), so_id=order.id, provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
    )
    db.add(project)
    db.flush()
    inquiry = OrderInquiry(
        id=_uid(), project_sales_order_id=project.id,
        inquiry_no=f"ZZT-OI-{_uid()[:8]}",
    )
    db.add(inquiry)
    db.flush()
    db.add(OrderInquiryRow(
        id=_uid(), order_inquiry_id=inquiry.id, qty=Decimal(qty), verb="ORDER",
        state=INQUIRY_PLACED, po_line_id=po_line.id,
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


def _by_code(cell: dict) -> dict:
    return {entry["location"]: entry for entry in cell["locations"]}


def _tags(cell: dict) -> list[tuple[str, str]]:
    return [(entry["location"], entry["where"]) for entry in cell["locations"]]


# --------------------------------------------------------------------------- #
# AC-B1: own, then the group, then every pool
# --------------------------------------------------------------------------- #


def test_every_active_site_pool_is_listed_after_the_group_own_site_first():
    """A BRW-BB line lists BRW-BB, the four -BB siblings, then all five pools."""
    with blank_session() as db:
        product = _product(db)
        pools, bins = _sites(db, ["BRW", "MWH", "DC1", "WH3", "RSW"], "BB")
        _stock(db, product, bins["BRW"], on_hand="40")
        _stock(db, product, pools["BRW"], on_hand="1716")
        _stock(db, product, pools["MWH"], on_hand="12")
        agent = _agent(db, group="BB")
        order = _order(db, agent=agent)
        _line(db, order, product, bins["BRW"])

        tags = _tags(_cell(db, order, product))

        assert tags[0] == ("BRW-BB", "own")
        # The group's other bins, by code, after the location the order itself named.
        assert sorted(tags[1:5]) == [
            ("DC1-BB", "group"), ("MWH-BB", "group"),
            ("RSW-BB", "group"), ("WH3-BB", "group"),
        ]
        assert {tag[1] for tag in tags[1:5]} == {"group"}
        # Then every pool, this line's own site leading.
        assert tags[5] == ("BRW", "site_pool")
        assert sorted(tags[6:]) == [
            ("DC1", "site_pool"), ("MWH", "site_pool"),
            ("RSW", "site_pool"), ("WH3", "site_pool"),
        ]


def test_a_pool_the_ladder_took_nothing_from_is_still_a_row():
    """"Why not MWH" is answered by the row itself: it was listed, and it held 12."""
    with blank_session() as db:
        product = _product(db)
        pools, bins = _sites(db, ["BRW", "MWH"], "BB")
        _stock(db, product, bins["BRW"], on_hand="40")
        _stock(db, product, pools["MWH"], on_hand="12")
        agent = _agent(db, group="BB")
        order = _order(db, agent=agent)
        _line(db, order, product, bins["BRW"])

        entry = _by_code(_cell(db, order, product))["MWH"]

        assert entry["where"] == "site_pool"
        assert Decimal(entry["qty_on_hand"]) == Decimal("12")
        assert entry["product_id"] == str(product.id)
        assert entry["warehouse_id"] == str(pools["MWH"].id)


# --------------------------------------------------------------------------- #
# AC-B2: no stock row is zero, not an unknown
# --------------------------------------------------------------------------- #


def test_a_location_with_no_stock_row_reads_zero_rather_than_nothing():
    """An absent `stock` row means the last upload counted none there."""
    with blank_session() as db:
        product = _product(db)
        pools, bins = _sites(db, ["BRW", "DC1"], "BB")
        _stock(db, product, bins["BRW"], on_hand="40")
        agent = _agent(db, group="BB")
        order = _order(db, agent=agent)
        _line(db, order, product, bins["BRW"])

        entry = _by_code(_cell(db, order, product))["DC1"]

        assert Decimal(entry["qty_on_hand"]) == Decimal("0")
        assert Decimal(entry["so_qty"]) == Decimal("0")
        assert Decimal(entry["spo_qty"]) == Decimal("0")
        assert Decimal(entry["available_qty"]) == Decimal("0")


def test_a_line_with_no_location_at_all_keeps_its_nulls():
    """The opposite instruction, and it survives: nobody has said where to look, so a zero
    would read as "that location is empty"."""
    with blank_session() as db:
        product = _product(db)
        agent = _agent(db, group="BB")
        order = _order(db, agent=agent)
        db.add(SalesOrderLine(
            id=_uid(), sales_order_id=order.id, product_id=product.id,
            warehouse_id=None, qty_ordered=Decimal("10"), qty_delivered=Decimal("0"),
            required_date=date(2026, 9, 3), line_status="open",
            purchasing_status="not_reviewed",
        ))
        db.flush()

        entry = _by_code(_cell(db, order, product))[None]

        assert entry["qty_on_hand"] is None
        assert entry["available_qty"] is None
        assert entry["po_open_qty"] is None


# --------------------------------------------------------------------------- #
# PO qty (section 3.B, captain 25 Aug)
# --------------------------------------------------------------------------- #


def test_po_open_qty_is_the_open_balance_at_that_location():
    with blank_session() as db:
        product = _product(db)
        _pools, bins = _sites(db, ["BRW"], "BB")
        _stock(db, product, bins["BRW"], on_hand="40")
        _po_line(db, product, bins["BRW"], ordered="500", received="120")
        agent = _agent(db, group="BB")
        order = _order(db, agent=agent)
        _line(db, order, product, bins["BRW"])

        entry = _by_code(_cell(db, order, product))["BRW-BB"]

        assert Decimal(entry["po_open_qty"]) == Decimal("380")


def test_po_open_qty_nets_the_rows_already_placed_on_those_lines():
    with blank_session() as db:
        product = _product(db)
        _pools, bins = _sites(db, ["BRW"], "BB")
        _stock(db, product, bins["BRW"], on_hand="40")
        line = _po_line(db, product, bins["BRW"], ordered="500")
        agent = _agent(db, group="BB")
        order = _order(db, agent=agent)
        _line(db, order, product, bins["BRW"])
        _place(db, order, line, qty="487")

        entry = _by_code(_cell(db, order, product))["BRW-BB"]

        assert Decimal(entry["po_open_qty"]) == Decimal("13")


def test_po_open_qty_excludes_spo_documents():
    """"Those are SPO, not PO" - the captain. An SPO is incoming supply and is already
    counted as `spo_qty`; adding it here would state the same arrival twice."""
    with blank_session() as db:
        product = _product(db)
        _pools, bins = _sites(db, ["BRW"], "BB")
        _stock(db, product, bins["BRW"], on_hand="40")
        _po_line(
            db, product, bins["BRW"], ordered="500",
            po_number=f"SPO-2026/08-{_uid()[:4]}", source_system="scm_spo_history",
        )
        agent = _agent(db, group="BB")
        order = _order(db, agent=agent)
        _line(db, order, product, bins["BRW"])

        entry = _by_code(_cell(db, order, product))["BRW-BB"]

        assert Decimal(entry["po_open_qty"]) == Decimal("0")


def test_po_open_qty_is_counted_at_the_pool_the_po_line_names():
    """The PO says DC1, the demand says BRW-BB: two different rows, and the split
    instruction is the difference between them."""
    with blank_session() as db:
        product = _product(db)
        pools, bins = _sites(db, ["BRW", "DC1"], "BB")
        _stock(db, product, bins["BRW"], on_hand="40")
        _po_line(db, product, pools["DC1"], ordered="500")
        agent = _agent(db, group="BB")
        order = _order(db, agent=agent)
        _line(db, order, product, bins["BRW"])

        by_code = _by_code(_cell(db, order, product))

        assert Decimal(by_code["DC1"]["po_open_qty"]) == Decimal("500")
        assert Decimal(by_code["BRW-BB"]["po_open_qty"]) == Decimal("0")


def test_po_open_qty_reaches_the_wire():
    """`response_model` drops what the schema does not declare, so the field is asserted
    through `BoardCell` rather than only off the service dict."""
    with blank_session() as db:
        product = _product(db)
        _pools, bins = _sites(db, ["BRW"], "BB")
        _stock(db, product, bins["BRW"], on_hand="40")
        _po_line(db, product, bins["BRW"], ordered="500")
        agent = _agent(db, group="BB")
        order = _order(db, agent=agent)
        _line(db, order, product, bins["BRW"])

        cell = BoardCell.model_validate(_cell(db, order, product))
        on_wire = cell.model_dump()["locations"]

        assert {entry["location"] for entry in on_wire} >= {"BRW-BB", "BRW"}
        own = next(entry for entry in on_wire if entry["location"] == "BRW-BB")
        assert own["po_open_qty"] == "500"
        assert own["where"] == "own"
