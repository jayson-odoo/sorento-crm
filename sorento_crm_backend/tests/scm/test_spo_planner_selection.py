"""F7 - the SPO planner CHOOSES: which POs it draws from, and which demand it is for.

TEST-FIRST: the take ordering by document date, `so_coverage`, `po_take_ids`, `so_line_ids`
and the link rows the create writes do not exist at the time this file is written, so every
test here is expected to be red until they land.

Postgres via `pg_session` (rolled back at teardown). The `World` builder from
`test_spo_conversion` is reused rather than copied - this suite is about the same service,
and a second world would be a second set of assumptions about what a shipment looks like.
The PROJECT chain (project -> sales order -> inquiry -> row) is built here, because no other
SPO suite has ever needed one.

Q8: PO takes are ordered by the purchase order's OWN document date (`issue_date`), not by
when a line is due. Q4: the demand walk ticks project by required date, then retail, until
the packed quantity is used up; what no tick claims is free stock at the suggested warehouse.
R1: project demand is an unlinked order-inquiry row, retail is a sales-order book line.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.project_so import (
    INQUIRY_RAISED,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SO_STATUS_DRAFT,
)
from app.models.projects import Project
from app.services.scm import spo_conversion_service as svc
from tests._pg_fixture import pg_session
from tests.scm.test_spo_conversion import MARKER, World, _line, _u


def _project_chain(db, w: World, product_key: str, *, qty: int, delivery: date):
    """A project order-inquiry row asking for `qty` of this product, linked to nothing yet.

    The whole chain, because an inquiry row without one has no product to match against and
    no document number to read: project -> project sales order -> line -> inquiry -> row.
    """
    title = f"{MARKER} project {uuid.uuid4().hex[:6]}"
    project = Project(
        id=_u(),
        title=title,
        # NOT NULL, and normally filled by the service that creates a project - stated here
        # because this suite writes the row directly.
        normalised_title=title.lower(),
        project_code=f"{MARKER}-{uuid.uuid4().hex[:8]}",
    )
    db.add(project)
    db.flush()
    pso = ProjectSalesOrder(
        id=_u(),
        project_id=project.id,
        area_group="TOWER",
        provisional_ref=f"{MARKER}-PSO-{uuid.uuid4().hex[:6]}",
        autocount_doc_no=f"{MARKER}-SI-{uuid.uuid4().hex[:6]}",
        status=SO_STATUS_DRAFT,
        grouping_origin="area",
        published_at=datetime(2026, 1, 2, 9, 0),
    )
    db.add(pso)
    db.flush()
    line = ProjectSalesOrderLine(
        id=_u(),
        project_sales_order_id=pso.id,
        line_no=1,
        product_id=w.product(product_key).id,
        description=f"{MARKER} line",
        qty=Decimal(str(qty)),
        uom="UNIT",
        unit_price=Decimal("10.00"),
        amount=Decimal(str(qty * 10)),
        delivery_date=delivery,
    )
    db.add(line)
    db.flush()
    inquiry = OrderInquiry(
        id=_u(), project_sales_order_id=pso.id, state=INQUIRY_RAISED
    )
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_u(),
        order_inquiry_id=inquiry.id,
        so_line_id=line.id,
        item_code=w.product(product_key).product_code,
        qty=Decimal(str(qty)),
        delivery_date=delivery,
        # ORDER BACK is the only verb an SPO can answer - an ORDER is a new purchase and
        # goes on a purchase order (`_SPO_LINKABLE_VERBS`).
        verb=IV_ORDER_BACK,
        state=INQUIRY_RAISED,
    )
    db.add(row)
    db.flush()
    return row, pso


def _retail_demand(db, w: World, product_key: str, wh, *, qty: int, required: date):
    """One open sales-order book line - the retail half of the tick list (R1)."""
    customer = Customer(
        id=_u(),
        customer_code=f"{MARKER}-C-{uuid.uuid4().hex[:6]}",
        customer_name=f"{MARKER} dealer",
    )
    db.add(customer)
    db.flush()
    so = SalesOrder(
        id=_u(),
        so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:6]}",
        customer_id=customer.id,
        order_date=date(2026, 7, 1),
        status="open",
    )
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=_u(),
        sales_order_id=so.id,
        product_id=w.product(product_key).id,
        warehouse_id=wh.id,
        qty_ordered=qty,
        qty_delivered=0,
        required_date=required,
        line_status="open",
    )
    db.add(line)
    db.flush()
    return line, so


def _coverage(line: dict, kind: str) -> list[dict]:
    return [c for c in line["so_coverage"] if c["kind"] == kind]


# --------------------------------------------------------------------------- #
# AC-G1 - the takes are ordered by the purchase order's own document date (Q8)
# --------------------------------------------------------------------------- #


def test_po_takes_are_ordered_by_the_purchase_orders_own_document_date():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        # The OLDER document is due LATER and sorts LATER by number, so neither the old
        # expected-date ordering nor the document number could produce this answer.
        older = w.po("Z", supplier, [("A", 50, 0)], issue_date=date(2026, 1, 5))
        newer = w.po("A", supplier, [("A", 50, 0)], issue_date=date(2026, 3, 9))
        for po, due in ((older, date(2026, 12, 1)), (newer, date(2026, 6, 1))):
            for pl in po.lines:
                pl.expected_date = due
        db.flush()
        shipment, lines = w.shipment([("A", 80, supplier)])

        out = svc.suggest(db, str(shipment.id))

        takes = _line(out, str(lines[0].id))["po_takes"]
        assert [t["po_date"] for t in takes] == ["2026-01-05", "2026-03-09"]
        assert takes[0]["qty"] == 50
        assert takes[1]["qty"] == 30


# --------------------------------------------------------------------------- #
# AC-G3 - the demand this SPO could be for, project first (Q4, R1)
# --------------------------------------------------------------------------- #


def test_the_coverage_list_walks_project_then_retail_by_need_by_date():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        # Retail needed FIRST by date, project later - the walk still puts project first.
        _retail_demand(db, w, "A", wh, qty=30, required=date(2026, 9, 1))
        _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))

        out = svc.suggest(db, str(shipment.id))

        coverage = _line(out, str(lines[0].id))["so_coverage"]
        assert [c["kind"] for c in coverage] == ["project", "retail"]
        assert coverage[0]["qty"] == 40
        assert coverage[1]["qty"] == 30


def test_the_default_ticks_stop_once_the_packed_quantity_is_used_up():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 50, supplier)])
        _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))
        _retail_demand(db, w, "A", wh, qty=30, required=date(2026, 9, 20))
        _retail_demand(db, w, "A", wh, qty=90, required=date(2026, 10, 2))

        out = svc.suggest(db, str(shipment.id))

        coverage = _line(out, str(lines[0].id))["so_coverage"]
        # 50 packed: the project row's 40 and part of the first retail line, and no further.
        assert [c["default_ticked"] for c in coverage] == [True, True, False]


def test_a_project_row_already_linked_elsewhere_is_offered_only_for_what_is_left():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        other_po = w.po("Z", supplier, [("A", 15, 0)])
        row, _pso = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))
        # 15 of the 40 already sits on another purchase order, so only 25 is still demand
        # this SPO could answer.
        db.add(OrderInquiryLink(
            id=_u(),
            row_id=row.id,
            po_line_id=other_po.lines[0].id,
            document=other_po.po_number,
            qty=Decimal("15"),
        ))
        db.flush()

        out = svc.suggest(db, str(shipment.id))

        project = _coverage(_line(out, str(lines[0].id)), "project")
        assert project and project[0]["qty"] == 25


def test_a_row_whose_verb_is_not_order_back_is_not_offered_at_all():
    """Only an ORDER BACK row can be linked to an SPO - an ORDER is a new purchase and goes
    on a purchase order. Offering it would be offering a tick that cannot be honoured."""
    from app.models.project_so import IV_ORDER

    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        row, _pso = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))
        row.verb = IV_ORDER
        db.flush()

        out = svc.suggest(db, str(shipment.id))

        assert _coverage(_line(out, str(lines[0].id)), "project") == []


# --------------------------------------------------------------------------- #
# AC-G2 / AC-G5 - the ticked takes are the ceiling
# --------------------------------------------------------------------------- #


def _confirm(shipment_line, qty, **extra):
    return {"shipment_line_id": str(shipment_line.id), "qty": qty, "include": True, **extra}


def test_unticking_a_take_lowers_what_the_spo_can_pull():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        po_a = w.po("A", supplier, [("A", 60, 0)], issue_date=date(2026, 1, 5))
        w.po("B", supplier, [("A", 40, 0)], issue_date=date(2026, 3, 9))
        shipment, lines = w.shipment([("A", 100, supplier)])
        keep = str(po_a.lines[0].id) if hasattr(po_a, "lines") else None
        out = svc.suggest(db, str(shipment.id))
        takes = _line(out, str(lines[0].id))["po_takes"]
        keep = takes[1]["po_line_id"]

        created = svc.create(
            db, str(shipment.id),
            [_confirm(lines[0], 100, po_take_ids=[keep])],
        )

        # Only the second PO was ticked, and it covers 40 - so that is the SPO.
        assert created["created_spos"][0]["qty"] == 40


def test_an_empty_take_list_is_not_the_same_as_saying_nothing():
    """`po_take_ids: []` is "draw from none of them", which cannot become an SPO line -
    distinct from the key being ABSENT, which means "every take you re-derive".

    With nothing else on the shipment, that is a confirm with nothing in it, and the
    existing refusal stands rather than a second, softer one being invented for this path.
    """
    from app.services.error_handler import AppException

    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("A", supplier, [("A", 60, 0)])
        shipment, lines = w.shipment([("A", 60, supplier)])

        with pytest.raises(AppException) as exc:
            svc.create(db, str(shipment.id), [_confirm(lines[0], 60, po_take_ids=[])])

        assert exc.value.status_code == 422
        assert exc.value.detail["detail"] == "nothing_selected"


# --------------------------------------------------------------------------- #
# AC-G6 / AC-G7 - the ticked demand is tied to the SPO
# --------------------------------------------------------------------------- #


def test_a_ticked_project_row_is_linked_to_the_spo_allocation_it_will_be_served_by():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        row, _pso = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))

        created = svc.create(
            db, str(shipment.id),
            [_confirm(
                lines[0], 100,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 100}],
                so_line_ids=[f"project:{row.id}"],
            )],
        )

        assert created["demand_links"]
        link_row = (
            db.query(OrderInquiryLink)
            .filter(OrderInquiryLink.row_id == row.id)
            .one()
        )
        assert link_row.spo_allocation_id is not None
        assert float(link_row.qty) == 40
        assert link_row.document == created["created_spos"][0]["po_number"]


def test_the_link_never_claims_more_than_the_row_still_needs():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        row, _pso = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))

        svc.create(
            db, str(shipment.id),
            [_confirm(
                lines[0], 100,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 100}],
                so_line_ids=[f"project:{row.id}"],
            )],
        )

        total = sum(
            float(l.qty)
            for l in db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row.id).all()
        )
        assert total == 40


def test_a_retail_tick_steers_the_split_but_writes_no_link():
    """`projects.order_inquiry_links.row_id` is NOT NULL - the table hangs off an inquiry
    row, and a retail sales-order line has none. The tick still counts: it is what put the
    quantity at that warehouse."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        retail, _so = _retail_demand(db, w, "A", wh, qty=30, required=date(2026, 9, 1))

        created = svc.create(
            db, str(shipment.id),
            [_confirm(
                lines[0], 100,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 100}],
                so_line_ids=[f"retail:{retail.id}"],
            )],
        )

        assert created["allocations"]
        assert created["demand_links"] == []


def test_nothing_ticked_writes_no_link_at_all():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        row, _pso = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))

        created = svc.create(
            db, str(shipment.id),
            [_confirm(
                lines[0], 100,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 100}],
                so_line_ids=[],
            )],
        )

        assert created["demand_links"] == []
        assert (
            db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row.id).count() == 0
        )


def test_the_purchase_order_says_which_spo_took_its_quantity():
    """AC-G7, the PO half: the source PO's own detail lists the SPO that pulled from it."""
    from app.services.scm.purchase_order_service import PurchaseOrderService

    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        po = w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 60, supplier)])

        created = svc.create(
            db, str(shipment.id),
            [_confirm(
                lines[0], 60,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 60}],
            )],
        )
        db.flush()

        blocks = PurchaseOrderService(db)._allocations_for(
            db.query(type(po)).filter(type(po).id == po.id).one()
        )

        spo_rows = [
            p for block in blocks for p in block["placements"] if p.get("kind") == "spo"
        ]
        assert spo_rows, "the PO detail says nothing about the SPO that pulled from it"
        assert spo_rows[0]["spo_number"] == created["created_spos"][0]["po_number"]
        assert spo_rows[0]["qty"] == 60
        assert spo_rows[0]["packing_list"] == shipment.shipment_number


# --------------------------------------------------------------------------- #
# The route carries the ticks (AC-G6)
# --------------------------------------------------------------------------- #


def test_the_route_passes_the_ticks_through_to_the_service(scm_app):
    """The planner sends `po_take_ids` and `so_line_ids` on every line; a schema that
    dropped either would leave the screen's choices on the floor with nothing to say so."""
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    supplier = w.supplier()
    wh = w.warehouse()
    w.po("A", supplier, [("A", 100, 0)])
    shipment, lines = w.shipment([("A", 100, supplier)])
    row, _pso = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))

    client = TestClient(app)
    suggestion = client.get(f"/api/v1/scm/inbound-shipments/{shipment.id}/spo-suggestion")
    assert suggestion.status_code == 200, suggestion.text
    coverage = suggestion.json()["lines"][0]["so_coverage"]
    assert [c["key"] for c in coverage] == [f"project:{row.id}"]
    assert coverage[0]["default_ticked"] is True

    created = client.post(
        f"/api/v1/scm/inbound-shipments/{shipment.id}/spo",
        json={
            "lines": [
                {
                    "shipment_line_id": str(lines[0].id),
                    "qty": 100,
                    "include": True,
                    "location_splits": [{"warehouse_id": str(wh.id), "qty": 100}],
                    "so_line_ids": [f"project:{row.id}"],
                }
            ]
        },
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["demand_links"] and body["demand_links"][0]["qty"] == 40
