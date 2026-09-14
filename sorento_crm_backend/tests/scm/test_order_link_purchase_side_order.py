"""`_purchase_side` answers with the OLDEST line of a document, not an arbitrary one.

Contract: `documentation/plans/scm/scm-oi-sheet-pairing-repair-acceptance-criteria.md`,
AC-R-25 (reviewer round, 15 Sep 2026).

`order_link_service._purchase_side` is how a cited document number becomes a target: one
purchase order line, or one shipping order allocation, per `(number, item code)`. A purchase
order can state the same item on several lines - two deliveries of the same product, or
five lines raised for five different sales order lines - and the read that feeds `by_key`
used to carry no ORDER BY at all, so which line answered was whatever Postgres returned
first. The order inquiry sheet import then paired the same file differently on its preview
and on its apply, which is a screen saying one thing before Confirm and another after it.

The seed is deliberately inserted out of order - middle, oldest, newest - so a read that
loses the ordering answers with the row it was handed first and this test says so.

Postgres only, through `tests/_pg_fixture.py`'s blank schema (the `world()` helper the order
inquiry migration tests seed with), because CI's database is empty and every FK target -
company, uom, category, product, warehouse, supplier, purchase order - has to be seeded here.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.models.procurement import PurchaseOrderLine
from app.services.scm import order_link_service
from tests.test_project_order_inquiry_import_migration import World, _uid, world


def _line(w: World, po, *, created_at: datetime) -> PurchaseOrderLine:
    """One more line of the SAME purchase order, for the same item, born when it says."""
    row = PurchaseOrderLine(
        id=_uid(),
        company_id=w.company_id,
        purchase_order_id=po.id,
        product_id=w.product.id,
        warehouse_id=w.warehouse.id,
        qty_ordered=Decimal("10"),
        qty_received=Decimal("0"),
        expected_date=date(2026, 9, 1),
        line_status="open",
        created_at=created_at,
    )
    w.db.add(row)
    w.db.flush()
    return row


def test_ac_r_25_purchase_side_answers_with_the_oldest_line():
    """AC-R-25. Three lines of one purchase order, one item: the oldest answers, on both
    `by_key` and `by_number`.

    `created_at` is stated on every line, because a whole AutoCount ingest shares one
    timestamp - Postgres freezes `now()` for the transaction that wrote it - so a test that
    left it to the default would be asserting nothing about the order at all.
    """
    with world() as w:
        po, middle = w.po_line(qty_ordered="10")
        middle.created_at = datetime(2026, 6, 2, 9, 0, 0)
        w.db.flush()
        oldest = _line(w, po, created_at=datetime(2026, 6, 1, 9, 0, 0))
        newest = _line(w, po, created_at=datetime(2026, 6, 3, 9, 0, 0))

        by_key, by_number = order_link_service._purchase_side(w.db, {po.po_number})

        assert by_key[(po.po_number, w.product.product_code)] == (
            order_link_service._PO_SIDE, str(oldest.id),
        ), "the cited document resolved onto a line that is not its oldest"
        assert by_number[po.po_number] == (
            order_link_service._PO_SIDE, str(oldest.id),
        )
        assert str(middle.id) != str(oldest.id) != str(newest.id)
