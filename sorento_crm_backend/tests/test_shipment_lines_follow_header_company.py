"""A shipment line belongs to the company of the container it hangs off.

Production report, packing list TGHU6295708: the `inbound_shipments` header was
Mocha's, its SPO allocations and its approved GRN were Mocha's, but the two
`inbound_shipment_lines` rows said Sorento (`DEFAULT_COMPANY_ID`). The container
had been fully received and still read `in_transit` / `allocated` / received 0.

Two halves, and both are needed:

* the lines got the wrong company because the insert auto-stamp
  (`company_scope._stamp_company_id`) reads the SESSION scope, not the header. An
  n8n re-upload that carries no company identity runs under scope `None`, finds
  the Mocha header, and stamps every replacement line with the incumbent company;
* the wrong company then made the lines INVISIBLE to the code that maintains
  them. `refresh_shipment_line_statuses` queried `InboundShipmentLine` directly,
  so under the Mocha scope it saw zero lines and returned early, and
  `list_shipments` counted zero lines so it never flipped the header to
  `fully_received`.

The scope filter is deliberately not applied to relationship loads, so the header
could always still SEE its lines - which is why the detail page showed them while
every maintenance path behaved as though the container had none.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PickingHeader,
    PickingLine,
    SPOAllocation,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.schemas.procurement import InboundShipmentCreate, InboundShipmentLineCreate
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.procurement_service import InboundShipmentService

from ._pg_fixture import blank_session, unique_code

MOCHA_ID = "00000000-0000-0000-0000-000000000002"
SHIPPED = 328
SPO_NUMBER = "SPO-2026/07-0012"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        session.add(Company(id=MOCHA_ID, name="Mocha", code=unique_code("MCH")[:20]))
        session.flush()
        yield session


def _product(db) -> str:
    category_id, uom_id = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(ProductCategory(id=category_id, category_code=unique_code("C")[:50], category_name="C"))
    db.add(UnitOfMeasure(id=uom_id, uom_code=unique_code("U")[:20], uom_name="Each"))
    db.flush()
    product_id = str(uuid.uuid4())
    code = unique_code("P")[:50]
    db.add(
        Product(
            id=product_id, product_code=code, product_name=code,
            category_id=category_id, base_uom_id=uom_id, list_price=10, is_active=True,
        )
    )
    db.flush()
    return product_id


def _mocha_container(
    db,
    *,
    line_company_id: str,
    line_status: str = "allocated",
    quantity_received: int = 0,
) -> dict:
    """A Mocha container whose whole SPO -> GRN chain is Mocha's, and one line
    whose ``company_id`` the caller chooses - that split IS the defect.
    """
    set_company_scope(db, frozenset({MOCHA_ID}))
    product_id = _product(db)

    warehouse_id = str(uuid.uuid4())
    db.add(
        Warehouse(
            id=warehouse_id,
            warehouse_code=unique_code("WH")[:50],
            warehouse_name="Mocha WH",
        )
    )

    shipment_id = str(uuid.uuid4())
    db.add(
        InboundShipment(
            id=shipment_id,
            shipment_number=unique_code("SHP")[:50],
            shipping_container_number=unique_code("TGHU")[:100],
            shipment_date=date(2026, 6, 1),
            shipment_status="in_transit",
        )
    )
    db.flush()

    line_id = str(uuid.uuid4())
    line = InboundShipmentLine(
        id=line_id,
        shipment_id=shipment_id,
        product_id=product_id,
        quantity_shipped=SHIPPED,
        cartons_count=1,
        spo_allocated_quantity=SHIPPED,
        quantity_received=quantity_received,
        line_status=line_status,
    )
    # Set BEFORE add: `_stamp_company_id` skips a row that already names a company,
    # so this is exactly the row the n8n re-upload wrote.
    line.company_id = line_company_id
    db.add(line)

    allocation_id = str(uuid.uuid4())
    db.add(
        SPOAllocation(
            id=allocation_id,
            spo_number=SPO_NUMBER,
            inbound_shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            allocated_quantity=SHIPPED,
            quantity_received=SHIPPED,
        )
    )

    picking_header_id = str(uuid.uuid4())
    db.add(
        PickingHeader(
            id=picking_header_id,
            picking_number=unique_code("GR")[:50],
            picking_type="goods_received",
            picking_date=date(2026, 7, 1),
            picking_status="approved",
            inspection_status="pending",
            spo_number=SPO_NUMBER,
        )
    )
    db.flush()
    db.add(
        PickingLine(
            id=str(uuid.uuid4()),
            picking_header_id=picking_header_id,
            spo_allocation_id=allocation_id,
            product_id=product_id,
            quantity_expected=SHIPPED,
            quantity_picked=SHIPPED,
            destination_warehouse_id=warehouse_id,
        )
    )
    db.commit()
    return {
        "shipment_id": shipment_id,
        "line_id": line_id,
        "product_id": product_id,
        "allocation_id": allocation_id,
    }


def _read_all_companies(db, model, row_id):
    """Read a row with the scope stood down, so an assertion about a row's company
    is not itself filtered by that company."""
    db.expire_all()
    set_company_scope(db, None)
    return db.query(model).filter(model.id == row_id).one()


def test_refresh_heals_a_line_stamped_with_another_company(db):
    """The production case: the header is Mocha, the line says Sorento, and the
    GRN received everything. Refreshing under Mocha must find the line through its
    header, put it back in the header's company, and report the receipt."""
    seeded = _mocha_container(db, line_company_id=DEFAULT_COMPANY_ID)

    set_company_scope(db, frozenset({MOCHA_ID}))
    InboundShipmentService(db).refresh_shipment_line_statuses(seeded["shipment_id"])

    line = _read_all_companies(db, InboundShipmentLine, seeded["line_id"])
    assert line.company_id == MOCHA_ID
    assert line.line_status == "received"
    assert line.quantity_received == SHIPPED

    header = _read_all_companies(db, InboundShipment, seeded["shipment_id"])
    assert header.shipment_status == "fully_received"


def test_list_counts_lines_of_another_company_for_their_header(db):
    """The listing counts a container's lines THROUGH the container, so a line
    still carrying another company is counted for its own header rather than
    leaving the container looking empty and permanently in transit."""
    seeded = _mocha_container(db, line_company_id=DEFAULT_COMPANY_ID)
    service = InboundShipmentService(db)

    set_company_scope(db, frozenset({MOCHA_ID}))
    service.refresh_shipment_line_statuses(seeded["shipment_id"])

    # The next n8n re-upload re-splits the line off its header again. The listing
    # must not depend on the heal having run.
    line = _read_all_companies(db, InboundShipmentLine, seeded["line_id"])
    line.company_id = DEFAULT_COMPANY_ID
    db.commit()

    set_company_scope(db, frozenset({MOCHA_ID}))
    result = service.list_shipments()

    headers = [s for s in result["data"] if str(s.id) == seeded["shipment_id"]]
    assert len(headers) == 1, "the Mocha header itself must still be listed"
    assert headers[0].lines_count == 1
    assert headers[0].shipment_status == "fully_received"


def test_revised_lines_take_the_header_company_under_an_all_companies_scope(db):
    """The n8n re-upload path. A company-less caller (scope ``None``) rewrites a
    Mocha container's lines; the replacements belong to Mocha, not to whichever
    company the auto-stamp falls back to."""
    set_company_scope(db, frozenset({MOCHA_ID}))
    product_id = _product(db)
    service = InboundShipmentService(db)
    payload = InboundShipmentCreate(
        shipment_number=unique_code("SHP")[:50],
        shipping_container_number=unique_code("TGHU")[:100],
        shipment_date=date(2026, 6, 1),
        shipment_lines=[
            InboundShipmentLineCreate(product_id=product_id, quantity_shipped=SHIPPED)
        ],
    )
    shipment = service.create_shipment(payload)
    shipment_id = str(shipment.id)

    set_company_scope(db, None)
    revised_product_id = _product(db)
    service.create_shipment(
        InboundShipmentCreate(
            shipment_number=payload.shipment_number,
            shipping_container_number=payload.shipping_container_number,
            shipment_date=date(2026, 6, 1),
            shipment_lines=[
                InboundShipmentLineCreate(product_id=revised_product_id, quantity_shipped=12)
            ],
        )
    )

    db.expire_all()
    set_company_scope(db, None)
    lines = (
        db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == shipment_id)
        .all()
    )
    assert lines, "the revision must leave the container with lines"
    assert {line.company_id for line in lines} == {MOCHA_ID}


def test_a_line_never_outruns_its_header_on_create(db):
    """The plain create path, for the regression guard: line company == header
    company, always, not merely whenever the two happen to be stamped alike."""
    set_company_scope(db, frozenset({MOCHA_ID}))
    product_id = _product(db)
    shipment = InboundShipmentService(db).create_shipment(
        InboundShipmentCreate(
            shipment_number=unique_code("SHP")[:50],
            shipment_date=date(2026, 6, 1),
            shipment_lines=[
                InboundShipmentLineCreate(product_id=product_id, quantity_shipped=SHIPPED)
            ],
        )
    )
    shipment_id, header_company_id = str(shipment.id), shipment.company_id
    assert header_company_id == MOCHA_ID

    db.expire_all()
    set_company_scope(db, None)
    lines = (
        db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == shipment_id)
        .all()
    )
    assert lines
    assert {line.company_id for line in lines} == {header_company_id}
