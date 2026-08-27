"""The purchase-history channel files a shipping order as an SPO allocation. AC-K1.

`PLAN-scm-cs-planning-uat.md` section K, captain's Q6 ruling: `purchase_orders` stops
receiving SPO documents. The `SPO-` half of the same book now writes one `spo_allocations`
row per line, upserted on `(company, spo_number, spo_line_number)`.

`blank_session`, not the shared database: this asserts that NO `purchase_orders` row with an
`SPO-` number exists after the import, and the shared local database is a prod copy holding
3,983 of them until the captain applies migration 420. On a scratch schema the sentence is
about this test's own book and nothing else. The alias rows the structured reader resolves
its headers through are seeded from migration 358's own `seed()`, because `create_all` never
runs a migration body (the "CI's database has no data" lesson).
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.models.inventory import Warehouse
from app.models.procurement import PurchaseOrder, SPOAllocation, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services import import_outcome_codes as oc
from app.services.import_outcome import ImportOutcome
from app.services.scm import po_history_service as svc

from .._pg_fixture import blank_session
from ._outstanding_workbooks import workbook

MARKER = "ZZTSPOK"

#: The document family this file is about, and one purchase order beside it so the routing
#: is asserted rather than assumed.
SPO_A = "SPO-2026/08-0061"
SPO_B = "SPO-2026/08-0062"
PO_A = "202608-S0099"

HEADERS = ("Doc No", "Doc Date", "Item Code", "Qty", "Location", "Creditor Name",
           "Delivery Date")

#: A stock location the catalogue does not hold. Its raw spelling is what `location_code`
#: exists to keep.
UNHELD = "RESERVE-XX"


def _uid() -> str:
    return str(uuid.uuid4())


def _seed_aliases(db) -> None:
    path = (Path(__file__).resolve().parent.parent.parent / "alembic" / "versions"
            / "358_scm_po_spo_history_aliases.py")
    spec = importlib.util.spec_from_file_location("zzt_migration_358", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.seed(db.connection())


def _catalogue(db):
    uom = UnitOfMeasure(id=_uid(), uom_code=f"{MARKER}{uuid.uuid4().hex[:6]}", uom_name="Set")
    category = ProductCategory(id=_uid(), category_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
                               category_name=f"{MARKER} cat")
    db.add_all([uom, category])
    db.flush()
    products = {}
    for code in (f"{MARKER}-WCY7405", f"{MARKER}-WC7405"):
        row = Product(id=_uid(), product_code=code, product_name=f"{MARKER} {code}",
                      category_id=category.id, base_uom_id=uom.id, list_price=Decimal("10.00"))
        db.add(row)
        products[code] = row
    warehouse = Warehouse(id=_uid(), warehouse_code=f"{MARKER}-BRW-IB",
                          warehouse_name=f"{MARKER} BRW-IB", is_active=True)
    # The structured export names the creditor and never its code, so the supplier has to
    # exist under that NAME for the row to be attributed to anybody. This channel never
    # creates one from a name (`_suppliers_by_name`), so an unseeded book writes rows with
    # no supplier - which is a fact about the file, not a failure.
    supplier = Supplier(id=_uid(), supplier_code=f"{MARKER}{uuid.uuid4().hex[:6]}",
                        supplier_name=f"{MARKER} CREDITOR", is_active=True)
    db.add_all([warehouse, supplier])
    db.flush()
    return products, warehouse


def _book(products, warehouse) -> bytes:
    """Two shipping orders and one purchase order.

    `SPO_A` states the same product twice - two containers on one document, the shape the
    old `(spo, product, warehouse)` unique key forbade - and a third line at a location the
    catalogue does not hold.
    """
    codes = list(products)
    return workbook(
        [
            (SPO_A, date(2026, 8, 12), codes[0], 160, warehouse.warehouse_code,
             f"{MARKER} CREDITOR", date(2026, 9, 1)),
            (SPO_A, date(2026, 8, 12), codes[0], 170, warehouse.warehouse_code,
             f"{MARKER} CREDITOR", date(2026, 9, 1)),
            (SPO_A, date(2026, 8, 12), codes[1], 12, UNHELD,
             f"{MARKER} CREDITOR", date(2026, 9, 1)),
            (SPO_B, date(2026, 8, 13), codes[1], 5, warehouse.warehouse_code,
             f"{MARKER} CREDITOR", date(2026, 9, 8)),
            (PO_A, date(2026, 8, 14), codes[0], 20, warehouse.warehouse_code,
             f"{MARKER} CREDITOR", date(2026, 9, 9)),
        ],
        headers=HEADERS,
        title="PO SPO",
    )


def _rows(db, number: str):
    return (
        db.query(SPOAllocation)
        .filter(SPOAllocation.spo_number == number)
        .order_by(SPOAllocation.spo_line_number)
        .all()
    )


class _Recorder(ImportOutcome):
    """An `ImportOutcome` that remembers which code each source row got."""

    def __init__(self) -> None:
        super().__init__(None, persist=False)
        self.codes: list[str] = []

    def _record(self, *, outcome, code, row=None, **kwargs):  # noqa: ANN001
        self.codes.append(code)
        return super()._record(outcome=outcome, code=code, row=row, **kwargs)


def _world(db):
    _seed_aliases(db)
    products, warehouse = _catalogue(db)
    db.commit()
    return products, warehouse


def test_a_shipping_order_writes_allocations_and_no_purchase_order():
    with blank_session() as db:
        products, warehouse = _world(db)
        svc.apply(db, _book(products, warehouse))
        db.flush()

        assert db.query(PurchaseOrder).filter(
            PurchaseOrder.po_number.like("SPO-%")).count() == 0
        # The purchase order in the same file is untouched by the split.
        assert db.query(PurchaseOrder).filter(PurchaseOrder.po_number == PO_A).count() == 1

        rows = _rows(db, SPO_A)
        assert [row.spo_line_number for row in rows] == [1, 2, 3]
        assert [row.allocated_quantity for row in rows] == [160, 170, 12]
        # Two containers of one product on one document, at one location.
        assert rows[0].product_id == rows[1].product_id
        assert rows[0].warehouse_id == rows[1].warehouse_id == warehouse.id
        assert len(_rows(db, SPO_B)) == 1


def test_history_lands_closed_and_fully_received():
    """This channel's governing rule: history must never read as incoming supply. The rows
    fail both halves of `scm.on_order_v`'s predicate rather than relying on a filter."""
    with blank_session() as db:
        products, warehouse = _world(db)
        svc.apply(db, _book(products, warehouse))
        db.flush()

        for row in _rows(db, SPO_A) + _rows(db, SPO_B):
            assert row.line_status == "closed"
            assert row.receipt_status == "fully_received"
            assert row.quantity_received == row.allocated_quantity
            assert row.source_system == svc.SPO_SOURCE_SYSTEM
            assert row.inbound_shipment_id is None


def test_an_unheld_location_keeps_its_code_and_carries_no_warehouse():
    with blank_session() as db:
        products, warehouse = _world(db)
        svc.apply(db, _book(products, warehouse))
        db.flush()

        unplaced = _rows(db, SPO_A)[2]
        assert unplaced.warehouse_id is None
        assert unplaced.location_code == UNHELD
        placed = _rows(db, SPO_A)[0]
        assert placed.location_code == warehouse.warehouse_code


def test_the_document_date_the_delivery_date_and_the_creditor_reach_the_row():
    with blank_session() as db:
        products, warehouse = _world(db)
        svc.apply(db, _book(products, warehouse))
        db.flush()

        row = _rows(db, SPO_A)[0]
        assert row.issue_date == date(2026, 8, 12)
        # What rung 1 compares against a sales line's required date.
        assert row.expected_date == date(2026, 9, 1)
        assert row.supplier_id is not None


def test_a_second_upload_of_the_same_book_writes_no_second_row():
    with blank_session() as db:
        products, warehouse = _world(db)
        book = _book(products, warehouse)
        first = svc.apply(db, book)
        db.flush()
        second = svc.apply(db, book)
        db.flush()

        assert first["lines_created"] == 5
        assert second["lines_created"] == 0
        assert db.query(SPOAllocation).filter(
            SPOAllocation.spo_number.in_([SPO_A, SPO_B])).count() == 4


def test_a_line_another_feed_owns_is_left_exactly_as_it_was():
    """The live outstanding book and `spo_conversion_service` write the OPEN balances that
    are the module's only incoming supply. A history export that also mentions the document
    must not close them, or a re-upload deletes the supply."""
    with blank_session() as db:
        products, warehouse = _world(db)
        live = SPOAllocation(
            id=_uid(), spo_number=SPO_B, spo_line_number=1,
            product_id=products[f"{MARKER}-WC7405"].id, warehouse_id=warehouse.id,
            allocated_quantity=5, quantity_received=0, receipt_status="pending",
            line_status="open", source_system="scm_upload",
        )
        db.add(live)
        db.commit()

        recorder = _Recorder()
        svc.apply(db, _book(products, warehouse), outcome=recorder)
        db.flush()

        held = _rows(db, SPO_B)[0]
        assert held.line_status == "open"
        assert held.quantity_received == 0
        assert held.source_system == "scm_upload"
        assert oc.DOCUMENT_OWNED_ELSEWHERE in recorder.codes
