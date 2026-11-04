"""OI-ONE-DELIVERY-DATE: the OI sheet upload writes the SO line date (AC-C1).

TEST-FIRST. The sheet's date still decides which line a row matches; the raised row stores
the matched line's `required_date` as its delivery date and keeps the sheet's own date as
the Was (`previous_delivery_date`) when the two differ. A red is the row still carrying the
sheet's date as its delivery date.

AC-C2 (the upload no longer reports or performs "Dates corrected") is NOT covered: pinning
it needs the repair fixtures of `test_oi_sheet_date_follow_sheet.py`, which the coder rewrites
anyway, and whether the result key is removed or reads 0 is not stated by the UAC.
"""
from __future__ import annotations


from .test_project_order_inquiry_import_migration import D_NOV, D_OCT, sheet, world


def test_sheet_date_differs_from_the_line_row_stores_line_date_and_keeps_sheet_as_was():
    """AC-C1: line due D_OCT, sheet says D_NOV."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50", required_date=D_OCT)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_NOV,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        row = w.one_row()
        assert row.delivery_date == D_OCT
        assert row.previous_delivery_date == D_NOV


def test_sheet_date_equal_to_the_line_leaves_no_was():
    """AC-C1: nothing to keep as Was when the sheet agrees with the line."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50", required_date=D_OCT)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        w.apply(data)

        row = w.one_row()
        assert row.delivery_date == D_OCT
        assert row.previous_delivery_date is None


def test_sheet_row_on_a_line_without_a_date_keeps_the_sheet_date():
    """AC-A11 on import: the line has no date, so the sheet's date is the row's own."""
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50", required_date=None)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_NOV,
             w.warehouse.warehouse_code, ""),
        ])

        w.apply(data)

        row = w.one_row()
        assert row.delivery_date == D_NOV
        assert row.previous_delivery_date is None
