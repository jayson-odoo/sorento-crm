"""Slice S3b, cost capture (UAC Group C3). RED first: written before the code.

Contract these tests pin, in the order the acceptance criteria state it:

* **AC-C3.1** Ordered cost is `purchase_order_lines.unit_cost` with its currency.
  Already exists; used here only as the other half of the comparison.
* **AC-C3.2** Incoming cost is captured from the packing list at the moment an SPO
  allocation is written, and stamped on the inbound shipment line. The packing-list
  line IS `inbound_shipment_lines`, so the cost is taken from the line itself; the
  missing half is the **currency**, which the table does not have a column for.
  Where the line carries a cost but no currency, the currency resolves through
  `SPOAllocation.po_line_id` to the ordered line's currency, and where there is no
  such source it stays NULL. A currency invented for a cost is worse than an absent
  one, because it silently changes what the variance means.
* **AC-C3.3** Ordered cost is never overwritten by incoming cost, and the variance
  between the two is a first-class output that is DERIVED, never stored.
* **AC-C3.4** Both figures are ex-works in the supplier's currency, which is why a
  variance across two different currencies is not a number at all.

Two new pieces of implementation are named by these tests, because nothing in the
codebase provides them yet:

1. `inbound_shipment_lines.currency` (model column + migration), mirroring
   `purchase_order_lines.currency` as `String(3)` so the two can be compared.
2. `app.services.scm.cost_capture_service.cost_variance(...)`, a pure function over
   the two (cost, currency) pairs returning
   `{"variance", "currency", "comparable", "reason"}`, with
   `variance = incoming - ordered` so a positive number means the supplier repriced
   upward after we committed.

Substrate: Postgres, blank schema, every FK target seeded under the `ZZS3B` marker
prefix. Nothing is borrowed from an existing row, because CI's database is empty.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect as sa_inspect

from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.schemas.procurement import SPOAllocationCreate
from app.services.procurement_service import SPOAllocationService
from tests._pg_fixture import blank_session

MARKER = "ZZS3B"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _product(db) -> str:
    """A product with its real category and UOM parents. Postgres enforces both."""
    tag = _suffix()
    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=f"{MARKER}-CAT-{tag}",
        category_name=f"{MARKER} category {tag}",
    )
    uom = UnitOfMeasure(
        id=str(uuid.uuid4()), uom_code=f"{MARKER}-U{tag[:4]}", uom_name="Each"
    )
    db.add_all([category, uom])
    db.flush()

    pid = str(uuid.uuid4())
    db.add(
        Product(
            id=pid,
            product_code=f"{MARKER}-SKU-{tag}",
            product_name=f"{MARKER} product {tag}",
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=0,
            is_active=True,
        )
    )
    db.flush()
    return pid


def _warehouse(db) -> str:
    tag = _suffix()
    wid = str(uuid.uuid4())
    db.add(
        Warehouse(
            id=wid,
            warehouse_code=f"{MARKER}-WH-{tag}",
            warehouse_name=f"{MARKER} warehouse {tag}",
        )
    )
    db.flush()
    return wid


def _shipment_with_line(db, product_id: str, *, quantity: int = 10, **line_kwargs):
    """A packing list (one shipment, one line). `line_kwargs` carries the cost."""
    tag = _suffix()
    sid = str(uuid.uuid4())
    db.add(
        InboundShipment(
            id=sid,
            shipment_number=f"{MARKER}-SH-{tag}",
            shipping_container_number=f"{MARKER}-CONT-{tag}",
            shipment_date=date(2026, 1, 1),
            shipment_status="in_transit",
        )
    )
    db.flush()

    line_id = str(uuid.uuid4())
    db.add(
        InboundShipmentLine(
            id=line_id,
            shipment_id=sid,
            product_id=product_id,
            quantity_shipped=quantity,
            cartons_count=1,
            **line_kwargs,
        )
    )
    db.flush()
    return sid, line_id


def _po_line(db, product_id: str, warehouse_id: str, *, unit_cost, currency) -> str:
    """The ordered side of the comparison: one PO carrying one line (AC-C3.1)."""
    tag = _suffix()
    po_id = str(uuid.uuid4())
    db.add(
        PurchaseOrder(
            id=po_id,
            po_number=f"{MARKER}-PO-{tag}",
            issue_date=date(2026, 1, 1),
            status="active",
            currency=currency,
        )
    )
    db.flush()

    line_id = str(uuid.uuid4())
    db.add(
        PurchaseOrderLine(
            id=line_id,
            purchase_order_id=po_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            qty_ordered=Decimal("10"),
            qty_received=Decimal("0"),
            unit_cost=unit_cost,
            currency=currency,
            line_status="open",
        )
    )
    db.flush()
    return line_id


def _payload(*, shipment_id, warehouse_id, product_id, po_line_id=None, quantity=10):
    """The allocation as the SPO import / allocation screen submits it.

    `po_line_id` is passed deliberately even though `SPOAllocationCreate` does not
    declare it yet: pydantic ignores unknown keys, so today the allocation is written
    with no PO link and the currency resolution has nothing to read. The dedicated
    schema test below is what names that gap explicitly.
    """
    return SPOAllocationCreate(
        spo_number=f"{MARKER}-SPO-{_suffix()}",
        inbound_shipment_id=shipment_id,
        warehouse_id=warehouse_id,
        product_id=product_id,
        po_line_id=po_line_id,
        allocated_quantity=quantity,
        receipt_status="pending",
        quantity_received=0,
        quantity_rejected=0,
    )


def _reload_line(db, line_id: str) -> InboundShipmentLine:
    db.expire_all()
    return db.query(InboundShipmentLine).filter(InboundShipmentLine.id == line_id).one()


def _require_currency_column() -> None:
    """State the prerequisite before seeding a line that carries a currency.

    Without this, seeding raises `TypeError: 'currency' is an invalid keyword
    argument` from inside a helper, which reads like a broken fixture. The missing
    column is the finding, so say it where it is missed.
    """
    assert "currency" in InboundShipmentLine.__table__.columns, (
        "prerequisite: inbound_shipment_lines.currency does not exist yet, so an "
        "incoming cost cannot be recorded in any currency (AC-C3.2)"
    )


# ---------------------------------------------------------------------------
# AC-C3.2 - the currency column itself
# ---------------------------------------------------------------------------


def test_ac_c3_2_inbound_shipment_line_model_declares_currency():
    """AC-C3.2: the table has no currency column, so a currency migration is in scope.

    Pinned on the model first because everything else in this file reads
    `line.currency`. `String(3)` mirrors `purchase_order_lines.currency`, which is
    what makes the ordered and incoming figures comparable at all (AC-C3.4).
    """
    column = InboundShipmentLine.__table__.columns.get("currency")
    assert column is not None, (
        "inbound_shipment_lines has no currency column, so an incoming cost of 12.50 "
        "carries no unit and cannot be compared with the ordered cost"
    )
    assert getattr(column.type, "length", None) == 3, (
        "currency must be a 3-character code like purchase_order_lines.currency"
    )
    assert column.nullable is True, (
        "a line whose cost has no known currency must be allowed to say so"
    )


def test_ac_c3_2_currency_column_exists_in_the_migrated_database():
    """AC-C3.2: the column must reach a real database, not just the ORM metadata.

    Read from the configured engine, which is a migrated Postgres. A model column
    with no migration behind it is invisible to production.
    """
    from app.database import engine

    columns = {c["name"] for c in sa_inspect(engine).get_columns("inbound_shipment_lines")}
    assert "currency" in columns, (
        f"no currency column on the migrated inbound_shipment_lines: {sorted(columns)}"
    )


def test_ac_c3_2_currency_round_trips_on_a_shipment_line(db):
    """AC-C3.2: a currency written on a packing-list line is read back unchanged."""
    _require_currency_column()
    product_id = _product(db)
    _, line_id = _shipment_with_line(
        db, product_id, unit_cost=Decimal("12.50"), currency="USD"
    )
    db.commit()

    line = _reload_line(db, line_id)
    assert line.unit_cost == Decimal("12.50")
    assert line.currency == "USD"


def test_ac_c3_2_allocation_create_accepts_the_po_line_link(db):
    """AC-C3.2: the currency resolves through `SPOAllocation.po_line_id`.

    The column exists on the model; the create schema does not carry it, so the
    allocation write has no way to record which ordered line it draws down and the
    currency lookup has no starting point. Named as its own failure so the
    behaviour tests below are not diagnosed as a resolution bug.
    """
    assert "po_line_id" in SPOAllocationCreate.model_fields, (
        "SPOAllocationCreate drops po_line_id, so an allocation is written with no "
        "link to the ordered line and its currency"
    )

    product_id = _product(db)
    warehouse_id = _warehouse(db)
    shipment_id, _ = _shipment_with_line(db, product_id, unit_cost=Decimal("12.50"))
    po_line_id = _po_line(
        db, product_id, warehouse_id, unit_cost=Decimal("10.00"), currency="USD"
    )
    db.commit()

    allocation = SPOAllocationService(db).create_allocation(
        _payload(
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            po_line_id=po_line_id,
        ),
        created_by=None,
    )
    assert allocation.po_line_id == po_line_id


# ---------------------------------------------------------------------------
# AC-C3.2 - stamping the incoming cost when the allocation is written
# ---------------------------------------------------------------------------


def test_ac_c3_2_allocation_stamps_incoming_cost_and_resolves_currency_from_po_line(db):
    """AC-C3.2: cost captured at the moment the allocation is written.

    The packing-list line carries 12.50 with no currency. The linked ordered line
    says USD, so that is the unit the incoming figure is in.
    """
    product_id = _product(db)
    warehouse_id = _warehouse(db)
    shipment_id, line_id = _shipment_with_line(
        db, product_id, unit_cost=Decimal("12.50")
    )
    po_line_id = _po_line(
        db, product_id, warehouse_id, unit_cost=Decimal("10.00"), currency="USD"
    )
    db.commit()

    SPOAllocationService(db).create_allocation(
        _payload(
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            po_line_id=po_line_id,
        ),
        created_by=None,
    )

    line = _reload_line(db, line_id)
    assert line.unit_cost == Decimal("12.50"), "the packing-list cost is the incoming cost"
    assert line.currency == "USD", (
        "currency must resolve from the linked ordered line when the packing list "
        "does not state one"
    )


def test_ac_c3_2_currency_stays_null_when_the_po_line_has_none(db):
    """AC-C3.2: no source for the currency means NULL, never a guess.

    The ordered line exists but states no currency. Filling in a house default here
    would silently assert that ordered and incoming are in the same unit, which is
    exactly what makes the variance meaningful, so it must not be invented.
    """
    product_id = _product(db)
    warehouse_id = _warehouse(db)
    shipment_id, line_id = _shipment_with_line(
        db, product_id, unit_cost=Decimal("9.99")
    )
    po_line_id = _po_line(
        db, product_id, warehouse_id, unit_cost=Decimal("9.00"), currency=None
    )
    db.commit()

    SPOAllocationService(db).create_allocation(
        _payload(
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            po_line_id=po_line_id,
        ),
        created_by=None,
    )

    line = _reload_line(db, line_id)
    assert line.unit_cost == Decimal("9.99")
    assert line.currency is None, (
        "no currency is knowable here, and a guessed one changes what the variance means"
    )


def test_ac_c3_2_no_cost_on_the_line_leaves_both_null_and_is_reported(db, caplog):
    """AC-C3.2: an uncosted packing-list line stays uncosted, and says so.

    This is the common case today: `unit_cost` is populated in 0 of 1,015 rows. A
    zero would read as free goods and would flow straight into the variance as a
    100% saving, so the absence must be preserved and surfaced.
    """
    product_id = _product(db)
    warehouse_id = _warehouse(db)
    shipment_id, line_id = _shipment_with_line(db, product_id)  # no unit_cost
    po_line_id = _po_line(
        db, product_id, warehouse_id, unit_cost=Decimal("10.00"), currency="USD"
    )
    db.commit()

    with caplog.at_level(logging.WARNING):
        SPOAllocationService(db).create_allocation(
            _payload(
                shipment_id=shipment_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
                po_line_id=po_line_id,
            ),
            created_by=None,
        )

    line = _reload_line(db, line_id)
    assert line.unit_cost is None, "an absent cost is not zero; zero reads as free goods"
    assert line.currency is None, "a currency with no cost to carry is noise"
    assert any(
        record.levelno >= logging.WARNING and "cost" in record.getMessage().lower()
        for record in caplog.records
    ), "an allocation written against an uncosted packing-list line must be reported"


def test_ac_c3_2_allocation_without_a_po_line_still_stamps_the_cost(db):
    """AC-C3.2: 860 legacy allocations have no PO, and stock can arrive against none.

    The packing-list cost is still the incoming cost. There is simply no ordered
    cost to compare it against, which is a reportable state, not an error.
    """
    product_id = _product(db)
    warehouse_id = _warehouse(db)
    shipment_id, line_id = _shipment_with_line(
        db, product_id, unit_cost=Decimal("7.25")
    )
    db.commit()

    allocation = SPOAllocationService(db).create_allocation(
        _payload(
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            po_line_id=None,
        ),
        created_by=None,
    )
    assert allocation.id is not None, "an allocation with no PO must not be skipped"

    line = _reload_line(db, line_id)
    assert line.unit_cost == Decimal("7.25")
    assert line.currency is None

    from app.services.scm.cost_capture_service import cost_variance

    result = cost_variance(
        ordered_cost=None,
        ordered_currency=None,
        incoming_cost=line.unit_cost,
        incoming_currency=line.currency,
    )
    assert result["variance"] is None
    assert result["comparable"] is False
    assert result["reason"], "the absence of an ordered cost must be stated, not blank"


# ---------------------------------------------------------------------------
# AC-C3.3 - ordered cost is never overwritten, and the variance is derived
# ---------------------------------------------------------------------------


def test_ac_c3_3_ordered_cost_is_never_overwritten_by_incoming_cost(db):
    """AC-C3.3: the ordered figure is evidence and must survive the allocation write.

    Incoming (12.50) sits above ordered (10.00): the supplier repriced after we
    committed. Overwriting the ordered figure erases the only proof of that.

    The stamp is asserted first, deliberately. "Nothing overwrote the ordered cost"
    is trivially true of an operation that writes nothing, so without proving the
    incoming cost actually landed, this test would pass today while guaranteeing
    nothing.
    """
    product_id = _product(db)
    warehouse_id = _warehouse(db)
    shipment_id, line_id = _shipment_with_line(db, product_id, unit_cost=Decimal("12.50"))
    po_line_id = _po_line(
        db, product_id, warehouse_id, unit_cost=Decimal("10.00"), currency="USD"
    )
    db.commit()

    before = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.id == po_line_id).one()
    ordered_cost_before = str(before.unit_cost)
    ordered_currency_before = before.currency
    updated_at_before = before.updated_at

    SPOAllocationService(db).create_allocation(
        _payload(
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            po_line_id=po_line_id,
        ),
        created_by=None,
    )

    stamped = _reload_line(db, line_id)
    assert stamped.unit_cost == Decimal("12.50")
    assert stamped.currency == "USD", (
        "the incoming cost must have been stamped, or the guarantee below is empty"
    )

    after = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.id == po_line_id).one()
    assert str(after.unit_cost) == ordered_cost_before == "10.00"
    assert after.currency == ordered_currency_before == "USD"
    assert after.updated_at == updated_at_before, (
        "the ordered line was written to at all, which it must not be"
    )


def test_ac_c3_3_variance_is_derived_from_the_two_columns_not_stored(db):
    """AC-C3.3: the variance is a first-class output and it is computed, not persisted.

    Two halves, both required. It has to be the right number, read from the two
    cost columns; and there must be no third column holding it, because a stored
    variance goes stale the moment either side is corrected.
    """
    _require_currency_column()
    product_id = _product(db)
    warehouse_id = _warehouse(db)
    _, line_id = _shipment_with_line(
        db, product_id, unit_cost=Decimal("12.50"), currency="USD"
    )
    po_line_id = _po_line(
        db, product_id, warehouse_id, unit_cost=Decimal("10.00"), currency="USD"
    )
    db.commit()

    line = _reload_line(db, line_id)
    po_line = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.id == po_line_id).one()

    from app.services.scm.cost_capture_service import cost_variance

    result = cost_variance(
        ordered_cost=po_line.unit_cost,
        ordered_currency=po_line.currency,
        incoming_cost=line.unit_cost,
        incoming_currency=line.currency,
    )
    assert result["comparable"] is True
    assert result["currency"] == "USD"
    assert Decimal(str(result["variance"])) == Decimal("2.50"), (
        "variance is incoming minus ordered, so a supplier who repriced upward "
        "shows a positive number"
    )

    # Derived, so correcting either side changes it with no write anywhere.
    line.unit_cost = Decimal("9.00")
    db.flush()
    recomputed = cost_variance(
        ordered_cost=po_line.unit_cost,
        ordered_currency=po_line.currency,
        incoming_cost=line.unit_cost,
        incoming_currency=line.currency,
    )
    assert Decimal(str(recomputed["variance"])) == Decimal("-1.00")

    stored = {
        (table, column.name)
        for table, model in (
            ("inbound_shipment_lines", InboundShipmentLine),
            ("purchase_order_lines", PurchaseOrderLine),
            ("spo_allocations", SPOAllocation),
        )
        for column in model.__table__.columns
        if "variance" in column.name.lower()
    }
    assert not stored, f"the variance is persisted in {sorted(stored)}; it must be derived"


def test_ac_c3_3_variance_across_two_currencies_is_not_a_number(db):
    """AC-C3.3 with AC-C3.4: ordered in USD, incoming in CNY.

    Subtracting these produces a figure that means nothing. The honest output is
    that the comparison is not computable, with the reason stated, rather than a
    number obtained by ignoring the units.
    """
    _require_currency_column()
    product_id = _product(db)
    warehouse_id = _warehouse(db)
    _, line_id = _shipment_with_line(
        db, product_id, unit_cost=Decimal("70.00"), currency="CNY"
    )
    po_line_id = _po_line(
        db, product_id, warehouse_id, unit_cost=Decimal("10.00"), currency="USD"
    )
    db.commit()

    line = _reload_line(db, line_id)
    po_line = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.id == po_line_id).one()

    from app.services.scm.cost_capture_service import cost_variance

    result = cost_variance(
        ordered_cost=po_line.unit_cost,
        ordered_currency=po_line.currency,
        incoming_cost=line.unit_cost,
        incoming_currency=line.currency,
    )
    assert result["comparable"] is False
    assert result["variance"] is None, (
        "60.00 here would be an invented saving produced by ignoring USD against CNY"
    )
    assert "curren" in str(result["reason"]).lower(), (
        "the reason must name the currency mismatch so the reader knows why"
    )


# ---------------------------------------------------------------------------
# Guard - existing behaviour the cost stamp must not displace
# ---------------------------------------------------------------------------


def test_guard_allocation_write_still_refreshes_shipment_line_statuses(db):
    """Green before and after: the cost stamp is additive.

    Writing an allocation still rolls the allocated quantity and the line status
    onto the packing-list line, through
    `InboundShipmentService.refresh_shipment_line_statuses`.
    """
    product_id = _product(db)
    warehouse_id = _warehouse(db)
    shipment_id, line_id = _shipment_with_line(db, product_id, quantity=10)
    db.commit()

    assert _reload_line(db, line_id).line_status == "in_transit"

    SPOAllocationService(db).create_allocation(
        _payload(
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            quantity=10,
        ),
        created_by=None,
    )

    line = _reload_line(db, line_id)
    assert line.spo_allocated_quantity == 10
    assert line.quantity_received == 0
    assert line.line_status == "allocated"
