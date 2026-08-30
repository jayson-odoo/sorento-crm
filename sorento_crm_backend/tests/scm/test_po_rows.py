"""`ProjectSupplyService.po_by_location` - open purchase-order supply, dated (S2, AC-S2-4).

The reader the Stock Debt view needs and the ladder's rung 3 will read next (S4): what is ON
ORDER, per location, net of the SPO already cut from it, at the date it would actually land.

Three rulings are pinned here because they are all counter-intuitive from the column names:

* **R29** a PO line's `expected_date` is the SO delivery date the users TYPED it against, not
  an arrival. Arrival is `purchase_orders.issue_date + the supplier's lead time`, and the
  typed date travels as `bought_for` for display only (R30).
* **R11** a PO counts NET of the SPO placed on it, or the same units are promised twice -
  once as on order and once as arriving. The netting is `qty_ordered - qty_received`, because
  BOTH writers of `spo_allocations.po_line_id` advance the source line's `qty_received` by
  what they placed; subtracting the allocation as well deducts it twice. A CRM-created SPO
  document (`spo_conversion_service`, `source_system = crm_spo`) is not an open PO at all -
  it IS the shipping leg, and `incoming_by_location` already carries its arrival.
* **R17** a bin outside fulfilment planning contributes nothing.

Postgres via `tests/_pg_fixture.py::blank_session`, every test seeding its own chain: CI's
database is empty and the local one is a prod copy, so nothing here counts existing rows.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.services.project_supply_service import ProjectSupplyService

from .._pg_fixture import blank_session
from ..test_so_supply_confirmation import (  # noqa: F401  (helpers, not fixtures)
    _product,
    _sorento,
    _uid,
    _warehouse,
)

ISSUE = date(2026, 6, 1)


def _supplier(db, lead_days: int | None = None, product=None):
    from app.models.procurement import ProductSupplier, Supplier

    row = Supplier(
        id=_uid(),
        supplier_code=f"ZZT-SUP-{_uid()[:6]}".upper(),
        supplier_name="ZZT supplier",
        is_active=True,
    )
    db.add(row)
    db.flush()
    if lead_days is not None and product is not None:
        db.add(
            ProductSupplier(
                id=_uid(),
                product_id=product.id,
                supplier_id=row.id,
                standard_lead_time_days=lead_days,
            )
        )
        db.flush()
    return row


def _po_line(
    db,
    product,
    warehouse,
    *,
    qty,
    received="0",
    supplier=None,
    issue_date=ISSUE,
    expected_date=None,
    status="active",
    line_status="open",
):
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    po = PurchaseOrder(
        id=_uid(),
        po_number=f"ZZT-PO-{_uid()[:6]}".upper(),
        supplier_id=supplier.id if supplier is not None else None,
        issue_date=issue_date,
        status=status,
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_uid(),
        purchase_order_id=po.id,
        product_id=product.id,
        warehouse_id=warehouse.id,
        qty_ordered=Decimal(str(qty)),
        qty_received=Decimal(str(received)),
        expected_date=expected_date,
        line_status=line_status,
    )
    db.add(line)
    db.flush()
    return po, line


def _spo_on(db, product, warehouse, po_line, *, qty, arrives=None, received=0, advance=True):
    """Place `qty` of `po_line` on a shipping order, the way the two real writers do it.

    `advance` mirrors what `allocation_suggestion_service.approve` and
    `spo_conversion_service.create` BOTH do beside the allocation row: they add the placed
    quantity to the source line's `qty_received`, so the units leave "on order" in the same
    action that makes them "arriving". Seeding the allocation without it would test a shape
    no writer produces.
    """
    from app.models.procurement import SPOAllocation

    if advance:
        po_line.qty_received = Decimal(str(po_line.qty_received or 0)) + Decimal(str(qty))
    row = SPOAllocation(
        id=_uid(),
        spo_number=f"ZZT-SPO-{_uid()[:6]}",
        spo_line_number=1,
        product_id=product.id,
        warehouse_id=warehouse.id,
        po_line_id=po_line.id,
        allocated_quantity=qty,
        quantity_received=received,
        receipt_status="pending",
        line_status="open",
        expected_date=arrives or date(2026, 9, 15),
    )
    db.add(row)
    db.flush()
    return row


def _rows(db, product, warehouse):
    return ProjectSupplyService(db).po_by_location([str(product.id)], [str(warehouse.id)])


# --------------------------------------------------------------------------- AC-S2-4


def test_arrival_is_issue_plus_the_suppliers_lead_time_and_the_typed_date_is_bought_for():
    """R29 on the SRTWB242 evidence: PO 202605-S0072's line dates are the open SO due dates
    for the product, not arrivals. So the timeline is dated from the issue and the typed
    date is carried beside it, named for what it is."""
    with blank_session() as db:
        _sorento(db)
        product = _product(db)
        warehouse = _warehouse(db, f"ZZTBRW-BB{_uid()[:4]}")
        supplier = _supplier(db, lead_days=45, product=product)
        po, _line = _po_line(
            db,
            product,
            warehouse,
            qty="100",
            supplier=supplier,
            expected_date=date(2026, 10, 15),
        )
        db.commit()

        rows = _rows(db, product, warehouse)[(str(product.id), str(warehouse.id))]
        assert len(rows) == 1
        row = rows[0]
        assert row.po_number == po.po_number
        assert row.qty == Decimal("100")
        assert row.arrival_date == ISSUE + timedelta(days=45)
        assert row.bought_for == date(2026, 10, 15)
        assert row.po_line_no == 1


def test_the_po_is_net_of_the_spo_already_cut_from_it():
    """R11 / AC-S2-4: 100 ordered with 40 placed on a shipping order contributes 60 - the
    other 40 is the SPO's to contribute, at ITS own arrival."""
    with blank_session() as db:
        _sorento(db)
        product = _product(db)
        warehouse = _warehouse(db, f"ZZTBRW-BB{_uid()[:4]}")
        supplier = _supplier(db, lead_days=30, product=product)
        _po, line = _po_line(db, product, warehouse, qty="100", supplier=supplier)
        _spo_on(db, product, warehouse, line, qty=40)
        db.commit()

        rows = _rows(db, product, warehouse)[(str(product.id), str(warehouse.id))]
        assert [row.qty for row in rows] == [Decimal("60")]


def test_an_approved_allocation_is_deducted_once_not_twice():
    """Review scenario (a). `allocation_suggestion_service.approve` does TWO things to one
    quantity: it adds 40 to the source line's `qty_received` ("the quantity moves from
    Ordered to Incoming in ONE action", its own AC-G6 comment) and it writes the
    `spo_allocations` row with `po_line_id` pointing back at the line. Reading the placement
    off BOTH left 100 - 40 - 40 = 20 on order, so a third of the purchase order vanished
    from the timeline the moment a container was allocated against it.
    """
    with blank_session() as db:
        _sorento(db)
        product = _product(db)
        warehouse = _warehouse(db, f"ZZTBRW-BB{_uid()[:4]}")
        supplier = _supplier(db, lead_days=30, product=product)
        _po, line = _po_line(db, product, warehouse, qty="100", supplier=supplier)
        _spo_on(db, product, warehouse, line, qty=40)  # the writer's own pair of writes
        db.commit()

        assert line.qty_received == Decimal("40")
        rows = _rows(db, product, warehouse)[(str(product.id), str(warehouse.id))]
        assert [row.qty for row in rows] == [Decimal("60")]


def test_a_crm_spo_document_is_never_read_as_an_open_purchase_order():
    """Review scenario (b). `spo_conversion_service.create` pulls 50 off an open PO line
    into a CRM SPO: the source line's `qty_received` rises to 50 (nothing left on order) and
    a NEW `purchase_orders` header stamped `crm_spo` carries the 50 with an
    `spo_allocations` row on it. That document is the shipping leg, and
    `incoming_by_location` already contributes it at its own arrival - so reading it here as
    well promises the units twice. Once a GRN receives 30 of the allocation the old
    expression stopped even cancelling: 50 ordered - 0 received - 20 still placed = a
    phantom 30 on order for a document that has already half landed.
    """
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine
    from app.services.scm.spo_conversion_service import SOURCE_SYSTEM

    with blank_session() as db:
        _sorento(db)
        product = _product(db)
        warehouse = _warehouse(db, f"ZZTBRW-BB{_uid()[:4]}")
        supplier = _supplier(db, lead_days=30, product=product)
        _source_po, source_line = _po_line(
            db, product, warehouse, qty="50", supplier=supplier
        )
        # The conversion: the pull advances the source line, and the SPO is its own document.
        source_line.qty_received = Decimal("50")
        spo_po = PurchaseOrder(
            id=_uid(),
            po_number=f"CRM-SPO-{_uid()[:6]}".upper(),
            supplier_id=supplier.id,
            issue_date=ISSUE,
            status="active",
            source_system=SOURCE_SYSTEM,
        )
        db.add(spo_po)
        db.flush()
        spo_line = PurchaseOrderLine(
            id=_uid(),
            purchase_order_id=spo_po.id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            qty_ordered=Decimal("50"),
            qty_received=Decimal("0"),
            line_status="open",
            source_system=SOURCE_SYSTEM,
        )
        db.add(spo_line)
        db.flush()
        # The allocation on the SPO's own line, 30 of it already received by a GRN.
        _spo_on(
            db, product, warehouse, spo_line, qty=50, received=30, advance=False
        )
        db.commit()

        assert _rows(db, product, warehouse) == {}


def test_a_po_line_fully_placed_on_a_shipping_order_contributes_nothing():
    with blank_session() as db:
        _sorento(db)
        product = _product(db)
        warehouse = _warehouse(db, f"ZZTBRW-BB{_uid()[:4]}")
        supplier = _supplier(db, lead_days=30, product=product)
        _po, line = _po_line(db, product, warehouse, qty="100", supplier=supplier)
        _spo_on(db, product, warehouse, line, qty=100)
        db.commit()

        assert _rows(db, product, warehouse) == {}


def test_a_received_or_closed_line_is_not_supply():
    with blank_session() as db:
        _sorento(db)
        product = _product(db)
        warehouse = _warehouse(db, f"ZZTBRW-BB{_uid()[:4]}")
        supplier = _supplier(db, lead_days=30, product=product)
        _po_line(db, product, warehouse, qty="50", received="50", supplier=supplier)
        _po_line(
            db, product, warehouse, qty="50", supplier=supplier, line_status="closed"
        )
        _po_line(db, product, warehouse, qty="50", supplier=supplier, status="draft")
        db.commit()

        assert _rows(db, product, warehouse) == {}


def test_a_bin_outside_fulfilment_planning_is_not_read():
    """R17 through the caller's own span: the Stock Debt service asks for the flagged bins,
    so a PO booked into a bin nobody plans against is simply not in the answer."""
    with blank_session() as db:
        _sorento(db)
        product = _product(db)
        planned = _warehouse(db, f"ZZTBRW-BB{_uid()[:4]}")
        outside = _warehouse(
            db, f"ZZTBRW-HP{_uid()[:4]}", fulfilment_planning=False
        )
        supplier = _supplier(db, lead_days=30, product=product)
        _po_line(db, product, outside, qty="80", supplier=supplier)
        db.commit()

        service = ProjectSupplyService(db)
        span = service.po_by_location([str(product.id)], list(service._planning_warehouses()))
        assert span == {}
        assert planned.fulfilment_planning is True


def test_with_no_lead_time_anywhere_the_default_lead_dates_the_arrival():
    """`DEFAULT_LEAD_TIME_DAYS`, the same fallback the reserve window uses - never a guess
    invented here, and never a NULL date that would silently drop the document."""
    from app.services.scm.front_planning_engine import DEFAULT_LEAD_TIME_DAYS

    with blank_session() as db:
        _sorento(db)
        product = _product(db)
        warehouse = _warehouse(db, f"ZZTBRW-BB{_uid()[:4]}")
        supplier = _supplier(db)  # no product_suppliers row
        _po_line(db, product, warehouse, qty="10", supplier=supplier)
        db.commit()

        rows = _rows(db, product, warehouse)[(str(product.id), str(warehouse.id))]
        assert rows[0].arrival_date == ISSUE + timedelta(days=DEFAULT_LEAD_TIME_DAYS)


def test_a_po_with_no_issue_date_carries_no_arrival():
    """6 open lines on the live book have no issue date. A document that cannot be dated is
    returned WITHOUT one rather than dropped: the assignment refuses to count it, and the
    drill still lists it so somebody can date it."""
    with blank_session() as db:
        _sorento(db)
        product = _product(db)
        warehouse = _warehouse(db, f"ZZTBRW-BB{_uid()[:4]}")
        supplier = _supplier(db, lead_days=30, product=product)
        _po_line(db, product, warehouse, qty="10", supplier=supplier, issue_date=None)
        db.commit()

        rows = _rows(db, product, warehouse)[(str(product.id), str(warehouse.id))]
        assert rows[0].arrival_date is None


def test_two_lines_of_one_po_are_numbered_in_document_order():
    """`purchase_order_lines` carries no line number, so the drill numbers them the way the
    document's own relationship orders them (created_at, id). Without it both rows read
    `PO 202608-S0041` and a buyer cannot tell which one is short."""
    with blank_session() as db:
        _sorento(db)
        product = _product(db)
        warehouse = _warehouse(db, f"ZZTBRW-BB{_uid()[:4]}")
        supplier = _supplier(db, lead_days=30, product=product)
        from app.models.procurement import PurchaseOrderLine

        po, _first = _po_line(db, product, warehouse, qty="10", supplier=supplier)
        second = PurchaseOrderLine(
            id=_uid(),
            purchase_order_id=po.id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            qty_ordered=Decimal("20"),
            qty_received=Decimal("0"),
            line_status="open",
        )
        db.add(second)
        db.commit()

        rows = _rows(db, product, warehouse)[(str(product.id), str(warehouse.id))]
        # 1 and 2, not two 1s. WHICH line is first is the document's own order (both were
        # written in one transaction, so they share `created_at` and the id breaks the tie),
        # and the drill only has to tell them apart.
        assert sorted(row.po_line_no for row in rows) == [1, 2]
        assert sorted(row.qty for row in rows) == [Decimal("10"), Decimal("20")]


def test_the_page_reads_its_lead_times_in_one_batch_not_one_query_per_line(monkeypatch):
    """S2 cost. `_lead_time_days` is the SCALAR path: one round trip per product, memoized
    afterwards. The Stock Debt list asks about a thousand products at once, and a PO line
    that fell back to it before the memo was filled cost ~1,900 extra round trips per
    request on the dev copy. `_po_rows` now fills the memo through `lead_times()` first, so
    the scalar path is not entered at all.
    """
    calls: list[str] = []
    original = ProjectSupplyService._lead_time_days

    def spy(self, product_id):
        calls.append(str(product_id))
        return original(self, product_id)

    with blank_session() as db:
        _sorento(db)
        product = _product(db)
        warehouse = _warehouse(db, f"ZZTBRW-BB{_uid()[:4]}")
        # No `product_suppliers` row, so the join carries no lead and the fallback fires -
        # the exact case that used to reach the scalar reader.
        supplier = _supplier(db)
        _po_line(db, product, warehouse, qty="10", supplier=supplier)
        db.commit()

        monkeypatch.setattr(ProjectSupplyService, "_lead_time_days", spy)
        rows = _rows(db, product, warehouse)[(str(product.id), str(warehouse.id))]

    assert len(rows) == 1
    assert calls == []
