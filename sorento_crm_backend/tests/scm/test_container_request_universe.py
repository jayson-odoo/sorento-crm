"""F1 - the loading plan builds with or without a stock list, and project need is the OI.

`PLAN-scm-fulfilment-feedback.md` section 2 (row 1), AC-A1 / A2 / A3 / A4. Two changes, and
they are both about a screen that used to go blank:

* The row universe was the supplier's stock list ALONE, so a supplier who had not sent one
  produced "No stock list for X yet" and no plan at all - on a screen whose whole job is to
  say what to ask them for. It is now what we buy from them (`product_suppliers`) crossed with
  what customers are owed, plus whatever their stock list or their newest un-converted
  proforma names.
* Project demand no longer comes from the sales-order book. P3 (captain, 26 Aug) put it in
  ONE place - `projects.order_inquiry_rows` - and `demand.PLAN_DEMAND_ORDER_SQL` excludes
  project class from the book outright, so a plan that read the book for it counted zero.
  This file seeds the Order Inquiry, which is where the number actually lives.

Postgres, marker-prefixed, every chain seeded here (CI's database is empty).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest

from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import ProductSupplier
from app.models.project_so import OrderInquiry, OrderInquiryRow, ProjectSalesOrder
from app.models.scm import ProformaInvoice, ProformaInvoiceLine, ProformaInvoiceShipmentLink
from app.services.scm import container_request_service as svc
from tests._pg_fixture import pg_session
from tests.scm.test_loading_plan import World

MARKER = "ZZCU"


def _uid() -> str:
    return str(uuid.uuid4())


def _linked(db, w: World, key: str) -> None:
    """We buy this product from this supplier. The universe's first leg."""
    db.add(
        ProductSupplier(
            id=_uid(),
            product_id=w.product(key).id,
            supplier_id=w.supplier.id,
            standard_lead_time_days=30,
        )
    )
    db.flush()


def _retail_need(db, w: World, key: str, qty: float, *, required=None) -> SalesOrder:
    """Retail demand: the sales-order book, which is what it still speaks for (P3)."""
    so = SalesOrder(
        id=_uid(),
        so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
        status="open",
        demand_class="retail",
        order_date=date(2026, 1, 1),
    )
    db.add(so)
    db.flush()
    db.add(
        SalesOrderLine(
            id=_uid(),
            sales_order_id=so.id,
            product_id=w.product(key).id,
            qty_ordered=qty,
            qty_delivered=0,
            line_status="open",
            purchasing_status="not_reviewed",
            required_date=required,
        )
    )
    db.flush()
    return so


def _project_need(db, w: World, key: str, qty: float, *, delivery=None) -> OrderInquiryRow:
    """Project demand: an un-linked ORDER row the CS form raised - `committed_v`'s FORM leg.

    The lightest of the two project legs to seed (no supply decision, no mirror line), and
    the one that proves the point: the quantity is read off the Order Inquiry, never off a
    project-class sales order.
    """
    # The FORM leg joins `products` on (product_code, company_id), so every row of this chain
    # has to carry the company the PRODUCT was stamped with - which is the caller's company,
    # not a constant. Hard-coding Sorento here made the leg join nothing under `scm_app`,
    # whose fixture user belongs to a company of its own.
    company_id = str(w.product(key).company_id)
    core = SalesOrder(
        id=_uid(),
        so_number=f"{MARKER}-PSO-{uuid.uuid4().hex[:8]}",
        status="open",
        demand_class="project",
        order_date=date(2026, 1, 1),
    )
    db.add(core)
    db.flush()
    pso = ProjectSalesOrder(
        id=_uid(),
        company_id=company_id,
        project_id=None,
        so_id=core.id,
        provisional_ref=f"{MARKER}-PR-{uuid.uuid4().hex[:8]}",
        status="published",
    )
    db.add(pso)
    db.flush()
    inquiry = OrderInquiry(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=pso.id,
        inquiry_no=f"{MARKER}{uuid.uuid4().hex[:8]}"[:20],
        state="raised",
    )
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_uid(),
        company_id=company_id,
        order_inquiry_id=inquiry.id,
        so_line_id=None,
        item_code=w.product(key).product_code,
        qty=qty,
        delivery_date=delivery,
        verb="ORDER",
        state="raised",
    )
    db.add(row)
    db.flush()
    return row


def _proforma(
    db,
    w: World,
    lines: list[tuple[str, float]],
    *,
    invoice_date: date | None = date(2026, 7, 31),
    status: str = "current",
    converted: bool = False,
    cbm_per_unit: float | None = None,
) -> ProformaInvoice:
    pi = ProformaInvoice(
        id=_uid(),
        supplier_id=w.supplier.id,
        pi_number=f"{MARKER}-PI-{uuid.uuid4().hex[:8]}",
        invoice_date=invoice_date,
        currency="CNY",
        line_count=len(lines),
        status=status,
    )
    db.add(pi)
    db.flush()
    for i, (key, qty) in enumerate(lines, start=1):
        db.add(
            ProformaInvoiceLine(
                id=_uid(),
                invoice_id=pi.id,
                line_no=i,
                item_code=w.product(key).product_code,
                product_id=w.product(key).id,
                qty=qty,
                cbm_per_unit=cbm_per_unit,
            )
        )
    db.flush()
    if converted:
        from app.models.procurement import InboundShipment

        shipment = InboundShipment(
            id=_uid(),
            shipment_number=f"{MARKER}-PL-{uuid.uuid4().hex[:8]}",
            supplier_id=w.supplier.id,
            shipment_date=date(2026, 8, 1),
            shipment_status="draft",
        )
        db.add(shipment)
        db.flush()
        first = (
            db.query(ProformaInvoiceLine)
            .filter(ProformaInvoiceLine.invoice_id == pi.id)
            .first()
        )
        db.add(
            ProformaInvoiceShipmentLink(
                id=_uid(),
                proforma_invoice_id=pi.id,
                proforma_invoice_line_id=first.id,
                inbound_shipment_id=shipment.id,
                inbound_shipment_line_id=None,
            )
        )
        db.flush()
    return pi


def _row(result: dict, w: World, key: str) -> dict:
    code = w.product(key).product_code
    return next(r for r in result["rows"] if r["item_code"] == code)


def _build(db, w: World) -> dict:
    return svc.build(db, supplier_id=str(w.supplier.id))


# --------------------------------------------------------------------------- #
# A1 / A4 - the universe
# --------------------------------------------------------------------------- #


def test_with_no_stock_list_and_no_proforma_a_linked_product_with_need_is_still_a_row():
    # AC-A1. The screen used to answer "no stock list yet" and show nothing - on the screen
    # whose whole job is to say what to ask this supplier for.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _retail_need(db, w, "A", 40)

        out = _build(db, w)

        assert out["stock_list_as_of"] is None
        row = _row(out, w, "A")
        assert row["open_so_need"] == 40
        assert row["has_demand"] is True
        assert row["rank"] == 1
        assert row["holding_source"] == "none"
        assert row["holding_qty"] is None


def test_a_linked_product_with_no_need_and_nothing_held_is_not_a_row():
    # The universe is what to ASK for, not the whole catalogue: a product with no demand and
    # nothing at the supplier names nothing worth a line on a container request.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")

        assert _build(db, w)["rows"] == []


def test_a_product_with_need_that_this_supplier_does_not_make_is_not_a_row():
    # The link is what makes it theirs to pack. Without it the plan would ask a tap factory
    # for a toilet seat.
    with pg_session() as db:
        w = World(db)
        _retail_need(db, w, "A", 40)

        assert _build(db, w)["rows"] == []


def test_a_held_product_with_no_need_is_an_unranked_row(scm_app=None):
    # AC-A4. Nothing the supplier holds vanishes from the one table Ms Tee reads.
    with pg_session() as db:
        w = World(db)
        w.stock("A", packed=12, unfinished=0)

        row = _row(_build(db, w), w, "A")

        assert row["has_demand"] is False
        assert row["rank"] is None
        assert row["suggested_qty"] == 0


# --------------------------------------------------------------------------- #
# A2 / A3 - what "they hold" reads
# --------------------------------------------------------------------------- #


def test_the_newest_unconverted_proforma_stands_in_for_a_missing_stock_list():
    # AC-A2 (Q2). Their pre-loading list is a statement about what they can pack, which is
    # the same question the stock list answers.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _retail_need(db, w, "A", 40)
        _proforma(db, w, [("A", 300)], invoice_date=date(2026, 7, 31))

        out = _build(db, w)

        row = _row(out, w, "A")
        assert row["holding_source"] == "proforma"
        assert row["holding_qty"] == 300
        assert row["holding_as_of"] == "2026-07-31"
        assert out["sources"]["proforma_as_of"] == "2026-07-31"


def test_the_newest_proforma_wins_and_ties_break_deterministically():
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _retail_need(db, w, "A", 40)
        _proforma(db, w, [("A", 100)], invoice_date=date(2026, 6, 1))
        _proforma(db, w, [("A", 300)], invoice_date=date(2026, 7, 31))

        assert _row(_build(db, w), w, "A")["holding_qty"] == 300


def test_a_converted_proforma_does_not_stand_in():
    # It has already become a packing list; what it said they could pack is spent.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _retail_need(db, w, "A", 40)
        _proforma(db, w, [("A", 300)], converted=True)

        assert _row(_build(db, w), w, "A")["holding_source"] == "none"


def test_a_superseded_revision_does_not_stand_in():
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _retail_need(db, w, "A", 40)
        _proforma(db, w, [("A", 300)], status="superseded")

        assert _row(_build(db, w), w, "A")["holding_source"] == "none"


def test_a_stock_list_wins_and_the_proforma_is_not_consulted():
    # AC-A3. The stock list is what they hold TODAY; a proforma is what they promised for
    # one container, and reading both would answer one question twice.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _retail_need(db, w, "A", 40)
        w.stock("A", packed=12, unfinished=5)
        _proforma(db, w, [("A", 300)])

        out = _build(db, w)

        row = _row(out, w, "A")
        assert row["holding_source"] == "stock_list"
        assert row["holding_qty"] == 12
        assert row["qty_packed"] == 12
        assert row["qty_unfinished"] == 5
        assert out["sources"]["proforma_as_of"] is None


def test_a_proforma_line_with_no_open_need_is_an_unranked_row():
    # AC-A4, the proforma half.
    with pg_session() as db:
        w = World(db)
        _proforma(db, w, [("A", 300)])

        row = _row(_build(db, w), w, "A")

        assert row["has_demand"] is False
        assert row["holding_source"] == "proforma"
        assert row["holding_qty"] == 300


# --------------------------------------------------------------------------- #
# project demand is the Order Inquiry (P3, captain 26 Aug)
# --------------------------------------------------------------------------- #


def test_project_need_is_read_off_the_order_inquiry():
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _project_need(db, w, "A", 25)

        row = _row(_build(db, w), w, "A")

        assert row["project_qty"] == 25
        assert row["retail_qty"] == 0
        assert row["open_so_need"] == 25


def test_a_project_class_sales_order_line_is_not_project_demand():
    # P3's whole point: the book speaks for retail alone. A project-class line becomes demand
    # when CS raises an Order Inquiry row for it, and this line has none.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        so = SalesOrder(
            id=_uid(),
            so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
            status="open",
            demand_class="project",
            order_date=date(2026, 1, 1),
        )
        db.add(so)
        db.flush()
        db.add(
            SalesOrderLine(
                id=_uid(),
                sales_order_id=so.id,
                product_id=w.product("A").id,
                qty_ordered=99,
                qty_delivered=0,
                line_status="open",
                purchasing_status="not_reviewed",
            )
        )
        db.flush()

        assert _build(db, w)["rows"] == []


def test_project_and_retail_need_add_up_on_one_row():
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _retail_need(db, w, "A", 40)
        _project_need(db, w, "A", 25)

        row = _row(_build(db, w), w, "A")

        assert row["project_qty"] == 25
        assert row["retail_qty"] == 40
        assert row["open_so_need"] == 65


def test_the_horizon_narrows_project_need_the_same_way_it_narrows_retail():
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _project_need(db, w, "A", 25, delivery=date(2027, 6, 1))
        _project_need(db, w, "A", 10, delivery=date(2026, 6, 1))

        out = svc.build(
            db, supplier_id=str(w.supplier.id), plan_horizon_date=date(2026, 12, 31)
        )

        assert _row(out, w, "A")["project_qty"] == 10


def test_the_open_so_lines_foot_to_the_retail_half_of_the_need():
    # The invariant `build` states, corrected for P3: the flat lines are the sales-order
    # book, and the book is retail. Project need has no book line to list.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _retail_need(db, w, "A", 40)
        _project_need(db, w, "A", 25)

        out = svc.build(db, supplier_id=str(w.supplier.id), include_lines=True)

        row = _row(out, w, "A")
        listed = sum(ln["qty"] for ln in out["lines"] if ln["product_id"] == row["product_id"])
        assert listed == row["retail_qty"] == 40


def _fully_linked(db, w: World, row: OrderInquiryRow) -> None:
    """Place the whole of an inquiry row on a purchase-order line.

    A row netted to nothing by its links is no longer demand - `committed_v` states it as
    `oir.qty > COALESCE(linked, 0)` - so neither its quantity NOR its date may reach the plan.
    """
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine
    from app.models.project_so import OrderInquiryLink

    po = PurchaseOrder(
        id=_uid(),
        po_number=f"{MARKER}-PO-{uuid.uuid4().hex[:8]}",
        supplier_id=w.supplier.id,
        issue_date=date(2026, 1, 1),
        status="active",
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_uid(),
        purchase_order_id=po.id,
        product_id=w.product("A").id,
        qty_ordered=row.qty,
        qty_received=0,
        line_status="open",
    )
    db.add(line)
    db.flush()
    db.add(
        OrderInquiryLink(
            id=_uid(),
            company_id=row.company_id,
            row_id=row.id,
            po_line_id=line.id,
            document=po.po_number,
            qty=row.qty,
        )
    )
    db.flush()


def test_a_row_with_packed_zero_but_unfinished_stock_is_still_a_row():
    # The base rule, restored: "held" is packed OR unfinished. A supplier holding 500 unfired
    # bodies and nothing packed is the case the production ask exists for, and it used to
    # vanish from the grid, the xlsx and the supplier's own page.
    with pg_session() as db:
        w = World(db)
        w.stock("A", packed=0, unfinished=500)

        row = _row(_build(db, w), w, "A")

        assert row["has_demand"] is False
        assert row["qty_unfinished"] == 500
        assert row["holding_source"] == "stock_list"


def test_a_fully_linked_inquiry_row_gives_the_plan_neither_quantity_nor_date():
    # The date and the quantity must come off the SAME rows. A row already placed on a
    # purchase order is not demand, and dating the plan from it would rank a product as
    # urgent on the strength of need somebody has already bought.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        placed = _project_need(db, w, "A", 7, delivery=date(2026, 1, 5))
        _fully_linked(db, w, placed)
        _project_need(db, w, "A", 10)

        row = _row(_build(db, w), w, "A")

        assert row["project_qty"] == 10
        assert row["earliest_required_date"] is None


def test_a_dated_inquiry_row_past_the_horizon_dates_nothing_either():
    # Same rule through the other predicate the quantity leg applies.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _project_need(db, w, "A", 25, delivery=date(2027, 6, 1))
        _project_need(db, w, "A", 10)

        out = svc.build(
            db, supplier_id=str(w.supplier.id), plan_horizon_date=date(2026, 12, 31)
        )

        row = _row(out, w, "A")
        assert row["project_qty"] == 10
        assert row["earliest_required_date"] is None
