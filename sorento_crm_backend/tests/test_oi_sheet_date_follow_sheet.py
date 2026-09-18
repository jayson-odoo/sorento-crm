"""The order inquiry sheet's raised row takes the SHEET's own delivery date.

Contract: `documentation/plans/scm/oi-sheet-date-follow-sheet-acceptance-criteria.md`,
AC-1 to AC-7. `PLAN-oi-sheet-date-follow-sheet.md` (18 Sep 2026 owner ruling: "we should
have followed the sheet's date") REVERSES section 7.4 of
`PLAN-scm-oi-sheet-pairing-repair.md`. Measured on prod: SO314593's open AutoCount lines
are 220 @ 01/03/2027 while the sheet said 182 @ 1.9.2026 - 7.4 wrote the LINE's date onto
every migrated row, so the worklist read a delivery purchasing was not working to, and a
re-upload of a corrected sheet did nothing because `_already_raised` skips a line that
already carries a row.

TEST-FIRST: the red state before the fix is the OLD rule (the raised row's `delivery_date`
reads the line's `required_date` over the sheet's) and a missing `DELIVERY_DATE_UPDATED`
repair on re-upload - never an import error.

Postgres only (`tests/_pg_fixture.py`, via `world()`). The world, sheet and apply builders
are IMPORTED from `tests/test_project_order_inquiry_import_migration.py` and
`tests/test_oi_sheet_pairing_repair.py` rather than copied, so the three files cannot
drift about what a seeded world is.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.project_so import IV_ORDER_BACK, OrderInquiryRow
from app.services import import_outcome_codes as oc
from app.services import project_order_inquiry_import_service as importer
from app.services.import_outcome import ImportOutcome

from .test_oi_sheet_pairing_repair import _apply
from .test_project_order_inquiry_import_migration import World, sheet, world


def _migrated_row(w: World, mirror, *, qty: str, delivery_date: date) -> OrderInquiryRow:
    """A row shaped exactly like the ones section 7.4 wrote: raised by an earlier upload,
    on the SALES ORDER LINE's date rather than the sheet's."""
    row = w.board_row(mirror, qty=qty)
    row.delivery_date = delivery_date
    row.note = importer._MIGRATION_STAMP
    w.db.flush()
    return row


def _fresh_row(
    w: World,
    mirror,
    *,
    qty: str,
    delivery_date: date,
    previous_qty: str,
    previous_delivery_date: date,
) -> OrderInquiryRow:
    """The row a later planning change raised beside a migrated one, carrying the Was/Now
    pair a backfill (or `_settle_row_in_place`) stamped from the migrated row's old
    figures - the SO314593/SO314594 shape."""
    row = w.board_row(mirror, qty=qty)
    row.delivery_date = delivery_date
    row.previous_qty = Decimal(previous_qty)
    row.previous_delivery_date = previous_delivery_date
    w.db.flush()
    return row


def test_ac_1_row_takes_the_sheets_own_date_over_the_lines():
    """AC-1. Sheet date 2026-09-01, line required 2027-03-01: the row reports the sheet's."""
    sheet_date = date(2026, 9, 1)
    line_date = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50", required_date=line_date)
        data = sheet([
            (order.so_number, w.product.product_code, 30, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 1, result
        assert w.one_row().delivery_date == sheet_date


def test_ac_2_no_sheet_date_falls_back_to_the_lines_required_date():
    """AC-2. The sheet states none: the line's own required date is what the row reports."""
    line_date = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50", required_date=line_date)
        data = sheet([
            (order.so_number, w.product.product_code, 30, None,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 1, result
        assert w.one_row().delivery_date == line_date


def test_ac_3_order_back_row_takes_the_lines_required_date():
    """AC-3. An ORDER BACK row's date cell carries words, never a date, so the sheet states
    none and the line's own required date stands - unaffected by this reversal."""
    line_date = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50", required_date=line_date)
        data = sheet([
            (order.so_number, w.product.product_code, 30, "ORDER BACK",
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 1, result
        row = w.one_row()
        assert row.verb == IV_ORDER_BACK
        assert row.delivery_date == line_date


def test_ac_4_reupload_repairs_a_migrated_rows_date_and_its_siblings_was_now():
    """AC-4. The SO314593 shape: a migrated row (182 @ 2027-03-01) and a fresh sibling
    raised beside it (220, previous_qty 182 / previous_delivery_date 2027-03-01). The sheet,
    corrected, says 182 @ 2026-09-01. The migrated row's own date moves to the sheet's, the
    sibling's Was/Now pair moves with it, and nothing else changes: no new row, the
    sibling's own qty/delivery_date untouched, one outcome code."""
    old_date = date(2027, 3, 1)
    sheet_date = date(2026, 9, 1)
    sibling_date = date(2027, 6, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=old_date)
        mirror = w.mirror_of(line)
        assert mirror is None, "not adopted yet - seeded fresh for this test"

        # Raise the migrated row through the real importer, so its mirror line exists and
        # its note carries the real migration stamp + a real file name.
        migration_sheet = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])
        first = _apply(w, migration_sheet, file_name="2026-08 order inquiry.xlsx")
        assert first["rows_raised"] == 1, first
        migrated = w.one_row()
        mirror = w.mirror_of(line)

        sibling = _fresh_row(
            w, mirror, qty="220", delivery_date=sibling_date,
            previous_qty="182", previous_delivery_date=old_date,
        )

        outcome_recorder = ImportOutcome(None, persist=False)
        data = sheet([
            (order.so_number, w.product.product_code, 182, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data, outcome=outcome_recorder)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 1, result
        rows = w.rows()
        assert len(rows) == 2, "no new row was raised"

        w.db.refresh(migrated)
        w.db.refresh(sibling)
        assert migrated.delivery_date == sheet_date
        assert sibling.previous_delivery_date == sheet_date
        assert Decimal(str(sibling.qty)) == Decimal("220")
        assert sibling.delivery_date == sibling_date
        seen_codes = {entry["code"] for entry in outcome_recorder.breakdown()["successful"]}
        assert seen_codes == {oc.DELIVERY_DATE_UPDATED}, seen_codes


def test_ac_5_reupload_is_idempotent():
    """AC-5. Running AC-4's upload a second time changes nothing and reports ALREADY_RAISED
    (or unchanged) - the migrated row is already on the sheet's date."""
    old_date = date(2027, 3, 1)
    sheet_date = date(2026, 9, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=old_date)
        migration_sheet = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, migration_sheet, file_name="2026-08 order inquiry.xlsx")
        mirror = w.mirror_of(line)
        sibling = _fresh_row(
            w, mirror, qty="220", delivery_date=date(2027, 6, 1),
            previous_qty="182", previous_delivery_date=old_date,
        )
        data = sheet([
            (order.so_number, w.product.product_code, 182, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        first = _apply(w, data)
        assert first["rows_delivery_date_updated"] == 1, first

        second = _apply(w, data)

        assert second["rows_raised"] == 0, second
        assert second["rows_delivery_date_updated"] == 0, second
        assert second["rows_already_raised"] == 1, second
        migrated = next(
            r for r in w.rows() if r.id != sibling.id
        )
        w.db.refresh(migrated)
        w.db.refresh(sibling)
        assert migrated.delivery_date == sheet_date
        assert sibling.previous_delivery_date == sheet_date


def test_ac_6_non_migrated_row_on_the_line_is_left_alone():
    """AC-6. The only row on the line carries no migration stamp (the board raised it):
    ALREADY_RAISED skip, nothing written."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=date(2027, 3, 1))
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        board = w.board_row(mirror, qty="182")
        board.delivery_date = date(2027, 3, 1)
        w.db.flush()

        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 9, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 0, result
        w.db.refresh(board)
        assert board.delivery_date == date(2027, 3, 1)


def test_ac_7_migrated_row_with_a_different_quantity_is_left_alone():
    """AC-7. A migrated row sits on the line, but its quantity does not match this sheet
    row's - the sheet is restating a DIFFERENT instruction, not this one. ALREADY_RAISED
    skip, nothing written."""
    old_date = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=old_date)
        migration_sheet = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, migration_sheet, file_name="2026-08 order inquiry.xlsx")
        migrated = w.one_row()

        data = sheet([
            (order.so_number, w.product.product_code, 100, date(2026, 9, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 0, result
        w.db.refresh(migrated)
        assert migrated.delivery_date == old_date
