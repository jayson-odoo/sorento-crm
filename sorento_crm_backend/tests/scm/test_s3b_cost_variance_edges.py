"""Slice S3b, the parts of cost capture the contract suite does not pin.

`test_s3b_cost_capture.py` is the contract for UAC Group C3. It leaves four things
unstated that the implementation had to decide, and a decision nothing tests is a
decision that gets reversed by accident:

1. **A cost with only one currency known** is not comparable either. The contract pins
   the two-different-currencies case; this pins the case where one side states no unit
   at all, which is the common one in production (the packing list carries no currency
   and the PO line may carry none either). Assuming the unknown side matches the known
   one is the same act as inventing a currency.
2. **A currency the packing list DID state is never overwritten** by the ordered line's.
   The resolution through `po_line_id` is a fallback for an absent unit, not a correction
   of a stated one.
3. **`upsert_allocation` captures on the paths that write** (created, updated) and not on
   the path that does not (unchanged). There is no moment of allocation to capture at
   when nothing was written, and that path also cannot bring a new PO link, since upsert
   only ever writes `allocated_quantity`.
4. **The migration chain stays single-headed.** A forked head is discovered at deploy,
   not at test time, unless something asserts it.

Substrate: Postgres, blank schema, `ZZS3E`-prefixed rows, nothing borrowed.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PurchaseOrder,
    PurchaseOrderLine,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.schemas.procurement import SPOAllocationCreate
from app.services.procurement_service import SPOAllocationService
from app.services.scm.cost_capture_service import cost_variance
from tests._pg_fixture import blank_session

MARKER = "ZZS3E"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _product(db) -> str:
    tag = _suffix()
    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=f"{MARKER}-CAT-{tag}",
        category_name=f"{MARKER} category {tag}",
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"{MARKER}-U{tag[:4]}", uom_name="Each")
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


def _payload(*, spo_number, shipment_id, warehouse_id, product_id, po_line_id=None, quantity=10):
    return SPOAllocationCreate(
        spo_number=spo_number,
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


# ---------------------------------------------------------------------------
# cost_variance - the branches the contract suite does not reach
# ---------------------------------------------------------------------------


def test_variance_needs_both_currencies_not_just_one():
    """One stated unit and one absent one is not a comparison.

    This is the production shape today: the ordered line says USD, the packing-list line
    says nothing. Treating the silent side as "presumably USD too" is the same invention
    the NULL currency exists to avoid, so it is refused rather than assumed.
    """
    result = cost_variance(
        ordered_cost=Decimal("10.00"),
        ordered_currency="USD",
        incoming_cost=Decimal("12.50"),
        incoming_currency=None,
    )
    assert result["comparable"] is False
    assert result["variance"] is None
    assert "curren" in str(result["reason"]).lower()


def test_variance_with_neither_currency_known_is_still_refused():
    """Two unlabelled numbers subtract arithmetically and mean nothing."""
    result = cost_variance(
        ordered_cost=Decimal("10.00"),
        ordered_currency=None,
        incoming_cost=Decimal("12.50"),
        incoming_currency=None,
    )
    assert result["comparable"] is False
    assert result["variance"] is None


def test_variance_without_an_incoming_cost_is_not_zero():
    """The common case today: 0 of 1,015 lines carry a cost.

    Reporting 0.00 here would show every uncosted shipment as a 100% saving against its
    purchase order.
    """
    result = cost_variance(
        ordered_cost=Decimal("10.00"),
        ordered_currency="USD",
        incoming_cost=None,
        incoming_currency=None,
    )
    assert result["comparable"] is False
    assert result["variance"] is None
    assert "incoming" in str(result["reason"]).lower()
    assert result["currency"] == "USD", "the one known unit is still worth reporting"


def test_variance_with_neither_cost_says_so():
    result = cost_variance(
        ordered_cost=None, ordered_currency=None, incoming_cost=None, incoming_currency=None
    )
    assert result["comparable"] is False
    assert result["variance"] is None
    assert result["reason"]


def test_currency_comparison_ignores_case_and_padding():
    """`usd ` and `USD` are one currency, not two.

    The codes arrive from an import and from a PO screen, so they are not guaranteed to
    match byte for byte. A false mismatch would suppress a real variance.
    """
    result = cost_variance(
        ordered_cost=Decimal("10.00"),
        ordered_currency=" usd ",
        incoming_cost=Decimal("12.50"),
        incoming_currency="USD",
    )
    assert result["comparable"] is True
    assert result["currency"] == "USD"
    assert result["variance"] == Decimal("2.50")


def test_blank_currency_is_absence_not_a_currency():
    """An empty string is what a cleared form field sends; it states no unit."""
    result = cost_variance(
        ordered_cost=Decimal("10.00"),
        ordered_currency="USD",
        incoming_cost=Decimal("12.50"),
        incoming_currency="   ",
    )
    assert result["comparable"] is False


def test_variance_of_a_float_cost_is_exact():
    """A float cost is converted via str, so 0.1 + 0.2 arithmetic never reaches money."""
    result = cost_variance(
        ordered_cost=10.10, ordered_currency="USD", incoming_cost=10.30, incoming_currency="USD"
    )
    assert result["variance"] == Decimal("0.20")


# ---------------------------------------------------------------------------
# The stamp - decisions the contract suite leaves open
# ---------------------------------------------------------------------------


def test_a_currency_stated_by_the_packing_list_is_not_overwritten(db):
    """Resolution through the PO line is a fallback, not a correction.

    The packing list says CNY and the purchase order says USD. That disagreement is a
    finding about the shipment; silently rewriting the packing list to agree with the PO
    would erase it and produce a variance of zero out of two different currencies.
    """
    product_id = _product(db)
    warehouse_id = _warehouse(db)
    shipment_id, line_id = _shipment_with_line(
        db, product_id, unit_cost=Decimal("70.00"), currency="CNY"
    )
    po_line_id = _po_line(
        db, product_id, warehouse_id, unit_cost=Decimal("10.00"), currency="USD"
    )
    db.commit()

    SPOAllocationService(db).create_allocation(
        _payload(
            spo_number=f"{MARKER}-SPO-{_suffix()}",
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            po_line_id=po_line_id,
        ),
        created_by=None,
    )

    line = _reload_line(db, line_id)
    assert line.currency == "CNY"
    assert line.unit_cost == Decimal("70.00")


def test_a_stated_cny_survives_an_allocation_against_a_myr_po_line(db):
    """AC-P5.3 (proforma/packing-list price capture): the specific pair the gap named.

    Same mechanism as the CNY-vs-USD case above, pinned again for the exact pairing the
    proforma-invoice slice's acceptance criteria calls out - a Malaysian PO denominated in
    MYR must never overwrite a currency the packing list itself stated in CNY.
    """
    product_id = _product(db)
    warehouse_id = _warehouse(db)
    shipment_id, line_id = _shipment_with_line(
        db, product_id, unit_cost=Decimal("70.00"), currency="CNY"
    )
    po_line_id = _po_line(
        db, product_id, warehouse_id, unit_cost=Decimal("55.00"), currency="MYR"
    )
    db.commit()

    SPOAllocationService(db).create_allocation(
        _payload(
            spo_number=f"{MARKER}-SPO-{_suffix()}",
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            po_line_id=po_line_id,
        ),
        created_by=None,
    )

    line = _reload_line(db, line_id)
    assert line.currency == "CNY"
    assert line.unit_cost == Decimal("70.00")


def test_an_allocation_for_a_product_not_on_the_packing_list_does_not_fail(db):
    """The allocated product need not appear on the shipment's lines.

    There is then no packing-list line to stamp. That is a real state, and the allocation
    must still be written rather than the write failing on a missing row.
    """
    product_id = _product(db)
    other_product_id = _product(db)
    warehouse_id = _warehouse(db)
    shipment_id, line_id = _shipment_with_line(db, other_product_id, unit_cost=Decimal("5.00"))
    db.commit()

    allocation = SPOAllocationService(db).create_allocation(
        _payload(
            spo_number=f"{MARKER}-SPO-{_suffix()}",
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
        ),
        created_by=None,
    )
    assert allocation.id is not None
    assert _reload_line(db, line_id).currency is None, "the other product's line is untouched"


def test_upsert_captures_on_create_and_on_update_but_not_on_unchanged(db):
    """The capture follows the write, and `unchanged` writes nothing.

    Created and updated both allocate, so both capture. `unchanged` returns before any
    write: there is no moment of allocation to capture at, and it cannot bring a new PO
    link either, since upsert only ever writes `allocated_quantity`.
    """
    service = SPOAllocationService(db)
    product_id = _product(db)
    warehouse_id = _warehouse(db)
    shipment_id, line_id = _shipment_with_line(db, product_id, quantity=20, unit_cost=Decimal("12.50"))
    po_line_id = _po_line(
        db, product_id, warehouse_id, unit_cost=Decimal("10.00"), currency="USD"
    )
    db.commit()

    spo_number = f"{MARKER}-SPO-{_suffix()}"

    # Created: no PO link, so the currency has no source and correctly stays NULL.
    action, _ = service.upsert_allocation(
        _payload(
            spo_number=spo_number,
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            quantity=10,
        ),
        created_by=None,
    )
    assert action == "created"
    assert _reload_line(db, line_id).currency is None

    # Unchanged: same quantity. Nothing is written, so nothing is captured, even though
    # this payload does carry a PO line.
    action, _ = service.upsert_allocation(
        _payload(
            spo_number=spo_number,
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            po_line_id=po_line_id,
            quantity=10,
        ),
        created_by=None,
    )
    assert action == "unchanged"
    assert _reload_line(db, line_id).currency is None

    # Updated: the row is written, so the capture runs. The link it resolves through is
    # the one on the stored allocation, which upsert deliberately never rewrites -- so a
    # currency still has no source here, and the capture stays honest about that.
    allocation = service.get_allocation(spo_number)
    allocation.po_line_id = po_line_id
    db.commit()

    action, _ = service.upsert_allocation(
        _payload(
            spo_number=spo_number,
            shipment_id=shipment_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            po_line_id=po_line_id,
            quantity=15,
        ),
        created_by=None,
    )
    assert action == "updated"
    assert _reload_line(db, line_id).currency == "USD"


# ---------------------------------------------------------------------------
# The migration chain
# ---------------------------------------------------------------------------


def test_the_currency_migration_chains_onto_a_single_head():
    """One head, and 328 sits directly on 327.

    A second head is not visible in any test failure -- it surfaces at deploy, where
    `alembic upgrade head` refuses to pick between them.
    """
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[2]
    script = ScriptDirectory.from_config(Config(str(root / "alembic.ini")))

    assert len(script.get_heads()) == 1, f"forked migration heads: {script.get_heads()}"

    revision = script.get_revision("328_scm_shipment_line_currency")
    assert revision.down_revision == "327_scm_coverage_config"
