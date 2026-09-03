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

import json
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
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


def _project_chain(
    db, w: World, product_key: str, *, qty: int, delivery: date, core_sales_order_line_id=None
):
    """A project order-inquiry row asking for `qty` of this product, linked to nothing yet.

    The whole chain, because an inquiry row without one has no product to match against and
    no document number to read: project -> project sales order -> line -> inquiry -> row.

    `core_sales_order_line_id` wires the mirror (`ProjectSalesOrderLine.core_sales_order_
    line_id`) to an AutoCount book line - unset by default (an inquiry row raised with no
    matching book line, the common case), set by the dedupe test to prove a book line and
    its own inquiry row collapse into one coverage entry.
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
        core_sales_order_line_id=core_sales_order_line_id,
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


def _retail_demand(
    db, w: World, product_key: str, wh, *, qty: int, required: date, demand_class: str | None = None
):
    """One open sales-order book line - the retail half of the tick list (R1).

    `demand_class` defaults to unset (None), the same as an order nobody classified; R3's
    tests pass it explicitly to build a book line whose OWN sales order reads project."""
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
        demand_class=demand_class,
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


# --------------------------------------------------------------------------- #
# Review finding 5 - an SPO take is subtracted ONCE
# --------------------------------------------------------------------------- #


def test_an_spo_take_does_not_come_off_the_line_twice():
    """`create` advances the source line's own `qty_received` by what it pulls, so the take
    is already out of `outstanding`. Counting it as `allocated` too took it off a second
    time and reported a line with 40 still to come as having nothing free."""
    from app.models.procurement import PurchaseOrder as PO
    from app.services.scm.purchase_order_service import PurchaseOrderService

    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        po = w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 60, supplier)])

        svc.create(
            db, str(shipment.id),
            [_confirm(
                lines[0], 60,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 60}],
            )],
        )
        db.flush()

        block = PurchaseOrderService(db)._allocations_for(
            db.query(PO).filter(PO.id == po.id).one()
        )[0]

        assert block["outstanding"] == 40
        assert block["allocated"] == 0
        assert block["free"] == 40
        # And the take is still ON the panel - it is how the buyer learns where the 60 went.
        assert [p["spo_number"] for p in block["placements"] if p["kind"] == "spo"]


# --------------------------------------------------------------------------- #
# Review finding 9 - unticking a take re-runs the cascade, it does not subtract
# --------------------------------------------------------------------------- #


def test_unticking_a_take_lets_the_remaining_po_cover_what_it_can():
    """80 packed, PO A open 50, PO B open 100. The default cascade takes 50 from A and 30
    from B. Unticking A should ask B for all 80 - it has it. Filtering the takes that were
    already cascaded gave 30 instead, and the buyer lost 50 pieces of cover that exist."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("A", supplier, [("A", 50, 0)], issue_date=date(2026, 1, 5))
        w.po("B", supplier, [("A", 100, 0)], issue_date=date(2026, 3, 9))
        shipment, lines = w.shipment([("A", 80, supplier)])
        out = svc.suggest(db, str(shipment.id))
        takes = _line(out, str(lines[0].id))["po_takes"]
        assert [t["qty"] for t in takes] == [50, 30]
        keep_b = takes[1]["po_line_id"]

        created = svc.create(
            db, str(shipment.id), [_confirm(lines[0], 80, po_take_ids=[keep_b])]
        )

        assert created["created_spos"][0]["qty"] == 80


def test_the_take_carries_its_lines_whole_open_balance_so_the_screen_can_do_the_same():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        w.po("A", supplier, [("A", 50, 0)], issue_date=date(2026, 1, 5))
        w.po("B", supplier, [("A", 100, 0)], issue_date=date(2026, 3, 9))
        shipment, lines = w.shipment([("A", 80, supplier)])

        takes = _line(svc.suggest(db, str(shipment.id)), str(lines[0].id))["po_takes"]

        assert [t["qty"] for t in takes] == [50, 30]
        # What each line has open, not what this cascade happened to take from it - the
        # figure the planner needs to re-cascade when a tick changes.
        assert [t["open_qty"] for t in takes] == [50, 100]


# --------------------------------------------------------------------------- #
# Review finding 10 - a retail order is not offered twice
# --------------------------------------------------------------------------- #


def test_a_retail_line_already_covered_by_one_container_is_offered_net_on_the_next():
    """R7 stands - a retail tick writes no link row - but the tick still has to be
    remembered, or the same 30 pieces are promised to SO-A on every container of the month
    and each one is default-ticked at full quantity.

    S5 supersedes the ORIGINAL shape of this test: a fully covered row is no longer dropped
    from the list - it is RETURNED at `qty: 0` (never re-tickable, `test_a_retail_line_fully
    _covered_by_one_container_returns_taken_on_the_next` covers that in full), so the netting
    itself - the SAME 30 pieces are never offered twice - is what this test still stands for.
    """
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 500, 0)])
        retail, _so = _retail_demand(db, w, "A", wh, qty=30, required=date(2026, 9, 1))

        first, first_lines = w.shipment([("A", 100, supplier)])
        svc.create(
            db, str(first.id),
            [_confirm(
                first_lines[0], 100,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 100}],
                so_line_ids=[f"retail:{retail.id}"],
            )],
        )

        second, second_lines = w.shipment([("A", 100, supplier)])
        coverage = _coverage(
            _line(svc.suggest(db, str(second.id)), str(second_lines[0].id)), "retail"
        )

        # The whole 30 went on the first container - nothing left for a SECOND container to
        # claim, so the row reads 0 and untickable, never the 30 again.
        entry = next(c for c in coverage if str(retail.id) in c["key"])
        assert entry["qty"] == 0
        assert entry["default_ticked"] is False


def test_a_partly_covered_retail_line_is_offered_for_the_rest():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 500, 0)])
        retail, _so = _retail_demand(db, w, "A", wh, qty=30, required=date(2026, 9, 1))

        first, first_lines = w.shipment([("A", 10, supplier)])
        svc.create(
            db, str(first.id),
            [_confirm(
                first_lines[0], 10,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 10}],
                so_line_ids=[f"retail:{retail.id}"],
            )],
        )

        second, second_lines = w.shipment([("A", 100, supplier)])
        coverage = _coverage(
            _line(svc.suggest(db, str(second.id)), str(second_lines[0].id)), "retail"
        )

        entry = next(c for c in coverage if str(retail.id) in c["key"])
        assert entry["qty"] == 20


def test_an_untouched_retail_line_is_offered_in_full():
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 500, 0)])
        retail, _so = _retail_demand(db, w, "A", wh, qty=30, required=date(2026, 9, 1))
        shipment, lines = w.shipment([("A", 100, supplier)])

        coverage = _coverage(
            _line(svc.suggest(db, str(shipment.id)), str(lines[0].id)), "retail"
        )

        entry = next(c for c in coverage if str(retail.id) in c["key"])
        assert entry["qty"] == 30


def test_the_walk_stops_dead_once_packed_is_exactly_consumed():
    """Browser pass 2, finding 3: the default ticks are the screen's starting point, and
    every one of them has to be an order this container can actually put something into.
    On the boundary - the first row consuming the packed quantity exactly - nothing after
    it is ticked."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 40, supplier)])
        _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))
        _retail_demand(db, w, "A", wh, qty=30, required=date(2026, 9, 20))

        coverage = _line(svc.suggest(db, str(shipment.id)), str(lines[0].id))["so_coverage"]

        assert [c["default_ticked"] for c in coverage] == [True, False]
        ticked = sum(c["qty"] for c in coverage if c["default_ticked"])
        assert ticked <= 40


# --------------------------------------------------------------------------- #
# Browser pass 3, finding 4 - the SPO row has to survive the response model
# --------------------------------------------------------------------------- #


def test_the_purchase_order_route_still_carries_the_spo_placement(scm_app):
    """The service builds the row; `response_model` decides what reaches the screen.

    `PurchaseOrderPlacement` declared none of the SPO fields, and Pydantic drops what it
    does not declare - silently. So the panel rendered the qty (a field it does declare)
    and printed "-" for the SPO number and the container beside it, which is exactly what
    the browser pass saw on 202511-S0111.
    """
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
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
    db.commit()

    body = TestClient(app).get(f"/api/v1/scm/purchase-orders/{po.id}").json()

    placements = [
        p for block in body["allocations"] for p in block["placements"]
    ]
    spo_rows = [p for p in placements if p.get("kind") == "spo"]
    assert spo_rows, f"no SPO placement survived the response model: {placements}"
    row = spo_rows[0]
    assert row["spo_number"] == created["created_spos"][0]["po_number"]
    assert row["packing_list"] == shipment.shipment_number
    assert row["qty"] == 60
    assert [x["warehouse_code"] for x in row["warehouses"]] == [wh.warehouse_code]
    assert "arrival_date" in row


# --------------------------------------------------------------------------- #
# S5 - occupied by another SPO: shown grey, never tickable (AC-E1..E6)
# --------------------------------------------------------------------------- #


def test_a_retail_line_fully_covered_by_one_container_returns_taken_on_the_next():
    """AC-E1: netting stays the rule (the row is not offered a tick), but S5 makes the
    occupied portion VISIBLE instead of the row simply vanishing."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 500, 0)])
        retail, _so = _retail_demand(db, w, "A", wh, qty=30, required=date(2026, 9, 1))

        first, first_lines = w.shipment([("A", 30, supplier)])
        created = svc.create(
            db, str(first.id),
            [_confirm(
                first_lines[0], 30,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 30}],
                so_line_ids=[f"retail:{retail.id}"],
            )],
        )
        spo_number = created["created_spos"][0]["po_number"]

        second, second_lines = w.shipment([("A", 100, supplier)])
        coverage = _coverage(
            _line(svc.suggest(db, str(second.id)), str(second_lines[0].id)), "retail"
        )

        entry = next(c for c in coverage if str(retail.id) in c["key"])
        assert entry["qty"] == 0
        assert entry["default_ticked"] is False
        assert entry["taken_qty"] == 30
        assert entry["taken_by"] == [spo_number]


def test_a_retail_line_half_covered_returns_the_rest_and_the_taken_half():
    """AC-E2."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 500, 0)])
        retail, _so = _retail_demand(db, w, "A", wh, qty=30, required=date(2026, 9, 1))

        first, first_lines = w.shipment([("A", 15, supplier)])
        created = svc.create(
            db, str(first.id),
            [_confirm(
                first_lines[0], 15,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 15}],
                so_line_ids=[f"retail:{retail.id}"],
            )],
        )
        spo_number = created["created_spos"][0]["po_number"]

        second, second_lines = w.shipment([("A", 100, supplier)])
        coverage = _coverage(
            _line(svc.suggest(db, str(second.id)), str(second_lines[0].id)), "retail"
        )

        entry = next(c for c in coverage if str(retail.id) in c["key"])
        assert entry["qty"] == 15
        assert entry["taken_qty"] == 15
        assert entry["taken_by"] == [spo_number]


def test_a_project_row_linked_elsewhere_carries_taken_by_naming_the_spo():
    """AC-E3."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        first, first_lines = w.shipment([("A", 100, supplier)])
        row, _pso = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))

        created = svc.create(
            db, str(first.id),
            [_confirm(
                first_lines[0], 100,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 100}],
                so_line_ids=[f"project:{row.id}"],
            )],
        )
        spo_number = created["created_spos"][0]["po_number"]

        # A second open PO, or the second shipment's line cannot convert at all and
        # `so_coverage` would come back empty regardless of what the demand side holds.
        w.po("B", supplier, [("A", 100, 0)])
        second, second_lines = w.shipment([("A", 100, supplier)])
        coverage = _coverage(
            _line(svc.suggest(db, str(second.id)), str(second_lines[0].id)), "project"
        )

        entry = next(c for c in coverage if str(row.id) in c["key"])
        assert entry["qty"] == 0
        assert entry["taken_qty"] == 40
        assert entry["taken_by"] == [spo_number]


def test_a_project_row_placed_on_a_plain_po_carries_taken_by_naming_the_po():
    """F3 (review round): `taken_qty` already sums EVERY `OrderInquiryLink` (a PO placement
    counts exactly the same as an SPO one), but `taken_by` only ever named an SPO - a row
    fully placed on a plain PO read `taken_qty: 40, taken_by: []`, "Another SPO" for a row
    no SPO ever touched. `taken_by` must name the document for EVERY link, PO or SPO."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        po = w.po("A", supplier, [("A", 100, 0)])
        po_line = po.lines[0]
        row, _pso = _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))

        db.add(OrderInquiryLink(
            id=_u(), row_id=row.id, po_line_id=str(po_line.id), qty=Decimal("40"),
            document=po.po_number,
        ))
        db.flush()

        second, second_lines = w.shipment([("A", 100, supplier)])
        coverage = _coverage(
            _line(svc.suggest(db, str(second.id)), str(second_lines[0].id)), "project"
        )

        entry = next(c for c in coverage if str(row.id) in c["key"])
        assert entry["qty"] == 0
        assert entry["taken_qty"] == 40
        assert entry["taken_by"] == [po.po_number]


def test_a_po_line_fully_pulled_returns_taken_in_po_takes_on_a_second_shipment():
    """AC-E4: a line with nothing open, whose only reason is a prior SPO pull, is still
    RETURNED (never silently dropped) - `suggested_qty` for the line does not count it.

    SPO-1 is written directly here - the exact state `create` leaves behind on the source
    line and on its own new line's `source_ref` (`test_the_purchase_order_says_which_spo_
    took_its_quantity` covers `create` itself writing it) - rather than through `svc.create`,
    so its own line, marked CLOSED (its whole quantity already pulled, nothing left to
    receive against it), cannot ALSO show up as a second, unrelated OPEN candidate for the
    second shipment's cascade: a live CRM SPO otherwise counts as genuine "ordered" supply to
    the same supplier and product the instant it exists (`po_ordered_v`'s own rule), which
    would otherwise defeat this test's own "the only PO" premise.
    """
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        po_a = w.po("A", supplier, [("A", 100, 0)])
        source_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == po_a.id
        ).one()

        spo_po = PurchaseOrder(
            id=_u(), po_number=f"{MARKER}-SPO1-{uuid.uuid4().hex[:6]}",
            supplier_id=supplier.id, issue_date=date(2026, 8, 1), status="active",
            source_system=svc.SOURCE_SYSTEM,
        )
        db.add(spo_po)
        db.flush()
        db.add(PurchaseOrderLine(
            id=_u(), purchase_order_id=spo_po.id, product_id=w.product("A").id,
            qty_ordered=100, qty_received=100, line_status="closed",
            source_system=svc.SOURCE_SYSTEM,
            source_ref=json.dumps(
                {"pulls": [{"po_line_id": str(source_line.id), "qty": 100}], "so_coverage": []}
            ),
        ))
        source_line.qty_received = 100
        db.flush()

        second, second_lines = w.shipment([("A", 50, supplier)])
        line = _line(svc.suggest(db, str(second.id)), str(second_lines[0].id))

        entry = next(t for t in line["po_takes"] if t["taken_qty"] > 0)
        assert entry["po_line_id"] == str(source_line.id)
        assert entry["qty"] == 0
        assert entry["open_qty"] == 0
        assert entry["taken_qty"] == 100
        assert entry["taken_by"] == [spo_po.po_number]
        assert line["suggested_qty"] == 0
        assert line["cannot_convert"] is True


def test_a_po_line_with_real_open_balance_the_cascade_did_not_reach_stays_a_normal_row():
    """F2 (review round): a taken-only row must be for a line THIS cascade left NOTHING
    open on. PO-A (100 open) is what the 50-packed cascade takes from first; PO-B (200
    ordered, 30 already pulled by an earlier SPO, so 170 open) is a line the cascade simply
    never reached - it still has real open balance, so it must stay a normal, tickable
    candidate rather than a second, greyed `po_takes` row for the same line PO-A already
    covers. Before this fix ANY candidate with `taken_qty > 0` was appended regardless of
    its own open balance, so PO-B (170 open) showed up greyed and untickable."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        po_a = w.po("A", supplier, [("A", 100, 0)], issue_date=date(2026, 1, 5))
        po_b = w.po("B", supplier, [("A", 200, 0)], issue_date=date(2026, 3, 9))
        po_b_line = po_b.lines[0]

        # An earlier SPO already pulled 30 off PO-B's line (`create`'s own advance).
        earlier_spo = PurchaseOrder(
            id=_u(), po_number=f"{MARKER}-SPO0-{uuid.uuid4().hex[:6]}",
            supplier_id=supplier.id, issue_date=date(2026, 2, 1), status="active",
            source_system=svc.SOURCE_SYSTEM,
        )
        db.add(earlier_spo)
        db.flush()
        db.add(PurchaseOrderLine(
            id=_u(), purchase_order_id=earlier_spo.id, product_id=w.product("A").id,
            qty_ordered=30, qty_received=30, line_status="closed",
            source_system=svc.SOURCE_SYSTEM,
            source_ref=json.dumps(
                {"pulls": [{"po_line_id": str(po_b_line.id), "qty": 30}], "so_coverage": []}
            ),
        ))
        po_b_line.qty_received = 30
        db.flush()

        shipment, lines = w.shipment([("A", 50, supplier)])
        line = _line(svc.suggest(db, str(shipment.id)), str(lines[0].id))

        assert len(line["po_takes"]) == 1
        take = line["po_takes"][0]
        assert take["po_line_id"] == str(po_a.lines[0].id)
        assert take["qty"] == 50
        po_b_ids = [t["po_line_id"] for t in line["po_takes"] if t["po_line_id"] == str(po_b_line.id)]
        assert po_b_ids == [], "PO-B has real open balance the cascade did not reach - not a taken-only row"


def test_unwind_returns_the_same_rows_with_taken_qty_zero_and_full_qty():
    """AC-E5: both halves - a retail line covered, and the PO line it was pulled from."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        po_a = w.po("A", supplier, [("A", 100, 0)])
        source_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == po_a.id
        ).one()
        retail, _so = _retail_demand(db, w, "A", wh, qty=30, required=date(2026, 9, 1))

        first, first_lines = w.shipment([("A", 100, supplier)])
        svc.create(
            db, str(first.id),
            [_confirm(
                first_lines[0], 100,
                location_splits=[{"warehouse_id": str(wh.id), "qty": 100}],
                so_line_ids=[f"retail:{retail.id}"],
            )],
        )
        db.refresh(source_line)
        assert float(source_line.qty_received) == 100, "sanity: the pull advanced it"

        svc.unwind(db, str(first.id))

        second, second_lines = w.shipment([("A", 60, supplier)])
        line = _line(svc.suggest(db, str(second.id)), str(second_lines[0].id))

        po_take = next(t for t in line["po_takes"] if t["po_line_id"] == str(source_line.id))
        assert po_take["open_qty"] == 100
        assert po_take["taken_qty"] == 0
        assert po_take["qty"] == 60

        retail_entry = next(
            c for c in _coverage(line, "retail") if str(retail.id) in c["key"]
        )
        assert retail_entry["qty"] == 30
        assert retail_entry["taken_qty"] == 0
        assert retail_entry["taken_by"] == []


def test_the_route_response_carries_taken_qty_and_taken_by(scm_app):
    """AC-E6: `response_model`-free route, but the additive fields still have to survive it -
    asserted through the API, the same discipline
    `test_the_purchase_order_route_still_carries_the_spo_placement` uses for its own field."""
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    supplier = w.supplier()
    w.po("A", supplier, [("A", 100, 0)])
    shipment, lines = w.shipment([("A", 100, supplier)])
    _project_chain(db, w, "A", qty=40, delivery=date(2026, 9, 10))

    client = TestClient(app)
    r = client.get(f"/api/v1/scm/inbound-shipments/{shipment.id}/spo-suggestion")

    assert r.status_code == 200, r.text
    line = r.json()["lines"][0]
    assert line["po_takes"]
    assert "taken_qty" in line["po_takes"][0]
    assert "taken_by" in line["po_takes"][0]
    assert line["so_coverage"]
    assert "taken_qty" in line["so_coverage"][0]
    assert "taken_by" in line["so_coverage"][0]


# --------------------------------------------------------------------------- #
# R3 - Class is the sales order's own class, not where the row came from
# --------------------------------------------------------------------------- #


def test_a_book_line_carries_its_own_sales_orders_demand_class():
    """AC-J1: a book line whose sales order reads project carries `demand_class: 'project'`;
    a plainly-retail one carries `'retail'`; an inquiry row carries `'project'` regardless -
    it has no `sales_orders.demand_class` to read, project demand is what an inquiry row IS."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        project_line, _project_so = _retail_demand(
            db, w, "A", wh, qty=10, required=date(2026, 9, 1), demand_class="project"
        )
        retail_line, _retail_so = _retail_demand(
            db, w, "A", wh, qty=10, required=date(2026, 9, 2), demand_class="retail"
        )
        _project_chain(db, w, "A", qty=10, delivery=date(2026, 9, 3))

        out = svc.suggest(db, str(shipment.id))

        coverage = _line(out, str(lines[0].id))["so_coverage"]
        retail_entries = _coverage(_line(out, str(lines[0].id)), "retail")
        project_book_entry = next(c for c in retail_entries if str(project_line.id) in c["key"])
        retail_book_entry = next(c for c in retail_entries if str(retail_line.id) in c["key"])
        inquiry_entry = next(c for c in coverage if c["kind"] == "project")

        assert project_book_entry["demand_class"] == "project"
        assert retail_book_entry["demand_class"] == "retail"
        assert inquiry_entry["demand_class"] == "project"
        assert inquiry_entry["kind"] == "project"


def test_project_demand_merges_inquiry_rows_and_project_class_book_lines_by_date():
    """AC-J2 (captain's course correction, 3 Sep): project demand is ONE group - order-
    inquiry rows AND book lines whose own sales order is project-class, merged and sorted
    TOGETHER by delivery date, not inquiry rows automatically ahead of every book line
    regardless of date. Retail (or unclassified) demand is still the OTHER group, behind
    every piece of project demand, regardless of its own date."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        # Retail is needed EARLIEST of the three - and still walks LAST: it is not project
        # demand, so date inside the other group cannot pull it ahead.
        retail_line, _retail_so = _retail_demand(
            db, w, "A", wh, qty=10, required=date(2026, 9, 1), demand_class="retail"
        )
        # The project-class book line is needed BEFORE the inquiry row - it now sorts FIRST
        # within the merged project-demand group, which the old "inquiry rows always first"
        # rule could not produce.
        project_line, _project_so = _retail_demand(
            db, w, "A", wh, qty=10, required=date(2026, 9, 5), demand_class="project"
        )
        _project_chain(db, w, "A", qty=10, delivery=date(2026, 9, 10))

        out = svc.suggest(db, str(shipment.id))

        coverage = _line(out, str(lines[0].id))["so_coverage"]
        assert [c["required_date"] for c in coverage] == [
            "2026-09-05",
            "2026-09-10",
            "2026-09-01",
        ]
        assert str(project_line.id) in coverage[0]["key"]
        assert coverage[1]["kind"] == "project"
        assert str(retail_line.id) in coverage[2]["key"]


def test_a_book_line_already_covered_by_its_own_inquiry_row_is_offered_once():
    """Dedupe (course correction): a book line whose project SO line already carries an
    ORDER BACK inquiry row is the SAME piece of demand as that row - `_project_coverage` and
    `_retail_coverage` read two different tables for it (the inquiry row, and the AutoCount
    book line `ProjectSalesOrderLine.core_sales_order_line_id` mirrors) and would otherwise
    both offer it. `_so_coverage` drops the book-line copy, so the operator sees it once, as
    the project entry."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        core_line, _core_so = _retail_demand(
            db, w, "A", wh, qty=40, required=date(2026, 9, 10), demand_class="project"
        )
        _project_chain(
            db, w, "A", qty=40, delivery=date(2026, 9, 10),
            core_sales_order_line_id=core_line.id,
        )

        out = svc.suggest(db, str(shipment.id))

        coverage = _line(out, str(lines[0].id))["so_coverage"]
        assert len(coverage) == 1
        assert coverage[0]["kind"] == "project"
        assert coverage[0]["demand_class"] == "project"


def test_a_book_line_whose_inquiry_row_covers_a_different_line_is_still_offered():
    """The dedupe is scoped to the SAME core line - two unrelated pieces of project demand
    (one book line, one inquiry row for a different line) both survive."""
    with pg_session() as db:
        w = World(db)
        supplier = w.supplier()
        wh = w.warehouse()
        w.po("A", supplier, [("A", 100, 0)])
        shipment, lines = w.shipment([("A", 100, supplier)])
        _retail_demand(
            db, w, "A", wh, qty=15, required=date(2026, 9, 3), demand_class="project"
        )
        _project_chain(db, w, "A", qty=25, delivery=date(2026, 9, 12))

        out = svc.suggest(db, str(shipment.id))

        coverage = _line(out, str(lines[0].id))["so_coverage"]
        assert len(coverage) == 2
        assert {c["kind"] for c in coverage} == {"project", "retail"}
