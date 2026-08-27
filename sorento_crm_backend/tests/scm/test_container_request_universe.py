"""F1 - the loading plan builds with or without a stock list, and what project need reads off.

`PLAN-scm-fulfilment-feedback.md` section 2 (row 1), AC-A1 / A2 / A3 / A4. Two changes, and
they are both about a screen that used to go blank:

* The row universe was the supplier's stock list ALONE, so a supplier who had not sent one
  produced "No stock list for X yet" and no plan at all - on a screen whose whole job is to
  say what to ask them for. It is now what we buy from them (`product_suppliers`) crossed with
  what customers are owed, plus whatever their stock list or their newest un-converted
  proforma names.
* Project demand on THIS screen is the open project sales-order book, less what CS has
  already placed on a purchase order or an SPO (R15, captain 27 Aug). It read
  `projects.order_inquiry_rows` alone for one day (R1), and on the dev copy 22,238 open
  project SO lines carry no inquiry row at all, so purchasing was shown nothing to ask for.
  The fulfilment board keeps P3 - `demand.py` and `scm.committed_v` are untouched - and only
  the loading plan reads the book for project class.

Postgres, marker-prefixed, every chain seeded here (CI's database is empty).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest

from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import ProductSupplier
from app.models.product import Product
from app.models.project_so import OrderInquiry, OrderInquiryRow, ProjectSalesOrder
from app.models.projects import Project
from app.models.sales_agent import SalesAgent
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


def _project_need(db, w: World, key: str, qty: float, *, required=None) -> SalesOrderLine:
    """Project demand: an open project-class SO line, which is what R15 reads.

    The same book the retail leg reads, told apart by `demand_class` alone - so a project
    requirement is seeded exactly like a retail one and the only difference on the row is the
    column it lands in.
    """
    so = SalesOrder(
        id=_uid(),
        so_number=f"{MARKER}-PSO-{uuid.uuid4().hex[:8]}",
        status="open",
        demand_class="project",
        order_date=date(2026, 1, 1),
    )
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_uid(),
        sales_order_id=so.id,
        product_id=w.product(key).id,
        qty_ordered=qty,
        qty_delivered=0,
        line_status="open",
        purchasing_status="not_reviewed",
        required_date=required,
    )
    db.add(line)
    db.flush()
    return line


def _place(db, w: World, line: SalesOrderLine, qty: float) -> None:
    """CS puts `qty` of a project SO line on a purchase order - the netting R15 subtracts.

    The whole chain, because that is the chain the netting walks: the project mirror of the
    order (`projects.sales_orders` / `projects.sales_order_lines`, reconciled to the core line
    by `core_sales_order_line_id`), the Order Inquiry row CS raised against that mirror line,
    and the `projects.order_inquiry_links` row the placement wrote. A link is what says "this
    requirement is already bought"; anything short of one leaves the line asking to be packed.
    """
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine
    from app.models.project_so import (
        OrderInquiryLink,
        ProjectSalesOrderLine,
    )

    # The company the PRODUCT was stamped with, which is the caller's - not a constant.
    product = db.query(Product).filter(Product.id == line.product_id).one()
    company_id = str(product.company_id)
    core_so = db.query(SalesOrder).filter(SalesOrder.id == line.sales_order_id).one()
    pso = ProjectSalesOrder(
        id=_uid(),
        company_id=company_id,
        project_id=None,
        so_id=core_so.id,
        provisional_ref=f"{MARKER}-PR-{uuid.uuid4().hex[:8]}",
        status="published",
    )
    db.add(pso)
    db.flush()
    psl = ProjectSalesOrderLine(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=pso.id,
        core_sales_order_line_id=line.id,
        line_no=1,
        product_id=line.product_id,
        qty=line.qty_ordered,
    )
    db.add(psl)
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
        so_line_id=psl.id,
        item_code=None,
        qty=line.qty_ordered,
        verb="ORDER",
        state="raised",
    )
    db.add(row)
    db.flush()
    po = PurchaseOrder(
        id=_uid(),
        po_number=f"{MARKER}-PO-{uuid.uuid4().hex[:8]}",
        supplier_id=w.supplier.id,
        issue_date=date(2026, 1, 1),
        status="active",
    )
    db.add(po)
    db.flush()
    po_line = PurchaseOrderLine(
        id=_uid(),
        purchase_order_id=po.id,
        product_id=line.product_id,
        qty_ordered=qty,
        qty_received=0,
        line_status="open",
    )
    db.add(po_line)
    db.flush()
    db.add(
        OrderInquiryLink(
            id=_uid(),
            company_id=company_id,
            row_id=row.id,
            po_line_id=po_line.id,
            document=po.po_number,
            qty=qty,
        )
    )
    db.flush()


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


def _agent(db, w: World, *, code: str, person: str | None) -> SalesAgent:
    """The salesperson on the order: the person when one is named, the code otherwise."""
    product = db.query(Product).filter(Product.id == w.product("A").id).one()
    agent = SalesAgent(
        id=_uid(),
        company_id=str(product.company_id),
        sales_agent=f"{code}-{uuid.uuid4().hex[:6]}" if person else code,
        person_label=person,
    )
    db.add(agent)
    db.flush()
    return agent


def _publish_for_project(db, w: World, line: SalesOrderLine, *, title: str) -> None:
    """The project this core order was published for - the mirror row plus its project.

    Nothing else of `_place`'s chain: this is about the LABEL the lightbox prints, not the
    netting, so an inquiry row and a placement link would only change the quantity.
    """
    product = db.query(Product).filter(Product.id == line.product_id).one()
    company_id = str(product.company_id)
    project = Project(
        id=_uid(),
        company_id=company_id,
        project_code=f"{MARKER}-PJ-{uuid.uuid4().hex[:6]}",
        title=title,
        normalised_title=title.casefold(),
    )
    db.add(project)
    db.flush()
    db.add(
        ProjectSalesOrder(
            id=_uid(),
            company_id=company_id,
            project_id=project.id,
            so_id=line.sales_order_id,
            provisional_ref=f"{MARKER}-PR-{uuid.uuid4().hex[:8]}",
            status="published",
        )
    )
    db.flush()


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
# project demand is the SO book less what CS placed (R15, captain 27 Aug)
# --------------------------------------------------------------------------- #


def test_an_open_project_sales_order_line_is_project_need():
    # R15. The line is the requirement; nothing else has to exist for purchasing to be told
    # about it - which is the whole point, since 22,238 open project lines carry no inquiry
    # row at all.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _project_need(db, w, "A", 25)

        row = _row(_build(db, w), w, "A")

        assert row["project_qty"] == 25
        assert row["retail_qty"] == 0
        assert row["open_so_need"] == 25


def test_a_partly_placed_project_line_counts_only_its_remainder():
    # 30 of the 100 is already on a purchase order, so 70 is what is left to ask for. The
    # netting is per LINE and per link quantity, never per row state.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        line = _project_need(db, w, "A", 100)
        _place(db, w, line, 30)

        row = _row(_build(db, w), w, "A")

        assert row["project_qty"] == 70
        assert row["open_so_need"] == 70


def test_a_fully_placed_project_line_counts_nothing():
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        line = _project_need(db, w, "A", 100)
        _place(db, w, line, 100)

        assert _build(db, w)["rows"] == []


def test_an_inquiry_row_with_no_sales_order_line_is_not_loading_plan_demand():
    # R15's accepted edge: the loading plan reads the BOOK, so a form-only inquiry row (one
    # naming no SO line) is invisible here. None exist on the dev copy; when one does, this
    # test is the record of the decision that has to be revisited.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        core = SalesOrder(
            id=_uid(),
            so_number=f"{MARKER}-PSO-{uuid.uuid4().hex[:8]}",
            status="open",
            demand_class="project",
            order_date=date(2026, 1, 1),
        )
        db.add(core)
        db.flush()
        company_id = str(w.product("A").company_id)
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
        db.add(
            OrderInquiryRow(
                id=_uid(),
                company_id=company_id,
                order_inquiry_id=inquiry.id,
                so_line_id=None,
                item_code=w.product("A").product_code,
                qty=25,
                verb="ORDER",
                state="raised",
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
    # The SAME cutoff, off the SAME column as retail (`sales_order_lines.required_date`): a
    # line due past "Plan until" is not this container's problem.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _project_need(db, w, "A", 25, required=date(2027, 6, 1))
        _project_need(db, w, "A", 10, required=date(2026, 6, 1))

        out = svc.build(
            db, supplier_id=str(w.supplier.id), plan_horizon_date=date(2026, 12, 31)
        )

        row = _row(out, w, "A")
        assert row["project_qty"] == 10
        assert row["earliest_required_date"] == "2026-06-01"


def test_the_project_need_by_date_is_the_earliest_line_the_plan_counts():
    # Quantity and date come off the SAME lines: a requirement already bought must not make
    # the product rank as urgent on a date nobody is still waiting on.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        placed = _project_need(db, w, "A", 7, required=date(2026, 1, 5))
        _place(db, w, placed, 7)
        _project_need(db, w, "A", 10, required=date(2026, 9, 4))

        row = _row(_build(db, w), w, "A")

        assert row["project_qty"] == 10
        assert row["earliest_required_date"] == "2026-09-04"


def test_the_open_so_lines_foot_to_the_whole_need():
    # The invariant `build` states, back where it was before R1: project lines ARE sales-order
    # lines again, so every unit of `open_so_need` has a line behind it - and a placed project
    # line is listed at its remainder, the same figure the column shows.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        _retail_need(db, w, "A", 40)
        line = _project_need(db, w, "A", 100)
        _place(db, w, line, 30)

        out = svc.build(db, supplier_id=str(w.supplier.id), include_lines=True)

        row = _row(out, w, "A")
        listed = sum(ln["qty"] for ln in out["lines"] if ln["product_id"] == row["product_id"])
        assert listed == row["open_so_need"] == 110
        assert {ln["demand_class"] for ln in out["lines"]} == {"retail", "project"}
        assert row["so_count"] == 2


def test_an_open_line_names_its_project_its_agent_and_its_price():
    # AC-B2: the Project / Retail lightbox lists Sales order, Customer, Project, Agent, Price,
    # Qty, Required. The three that were not on the payload are asserted HERE rather than in
    # the dialog's own test, because a field the service stops emitting is invisible to a
    # component test that mocks the payload.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        agent = _agent(db, w, code="ZZAG", person="Wong Mei Ling")
        retail = _retail_need(db, w, "A", 40)
        retail.sales_agent_id = agent.id
        db.query(SalesOrderLine).filter(SalesOrderLine.sales_order_id == retail.id).update(
            {"unit_price": 12.5}
        )
        project_line = _project_need(db, w, "A", 10)
        _publish_for_project(db, w, project_line, title=f"{MARKER} Tropicana Gardens")
        db.flush()

        out = svc.build(db, supplier_id=str(w.supplier.id), include_lines=True)

        by_class = {ln["demand_class"]: ln for ln in out["lines"]}
        assert by_class["retail"]["agent_label"] == "Wong Mei Ling"
        assert by_class["retail"]["unit_price"] == 12.5
        # A retail order is for a customer, not a project - the column is blank, not absent.
        assert by_class["retail"]["project_title"] is None
        assert by_class["project"]["project_title"] == f"{MARKER} Tropicana Gardens"
        # Nothing was said about who sold it or what it costs, and nothing is invented.
        assert by_class["project"]["agent_label"] is None
        assert by_class["project"]["unit_price"] is None


def test_the_agent_falls_back_to_the_code_when_nobody_is_named():
    # `person_label` is the person; `sales_agent` is the AutoCount code every row has. A row
    # carrying only the code says "SLS01", never a dash.
    with pg_session() as db:
        w = World(db)
        _linked(db, w, "A")
        agent = _agent(db, w, code=f"{MARKER}SLS01", person=None)
        so = _retail_need(db, w, "A", 5)
        so.sales_agent_id = agent.id
        db.flush()

        out = svc.build(db, supplier_id=str(w.supplier.id), include_lines=True)

        assert out["lines"][0]["agent_label"] == f"{MARKER}SLS01"


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
