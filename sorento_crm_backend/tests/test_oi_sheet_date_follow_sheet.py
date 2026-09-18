"""The order inquiry sheet's raised row takes the SHEET's own delivery date.

Contract: `documentation/plans/scm/oi-sheet-date-follow-sheet-acceptance-criteria.md`,
AC-1 to AC-13. `PLAN-oi-sheet-date-follow-sheet.md` (18 Sep 2026 owner ruling: "we should
have followed the sheet's date") REVERSES section 7.4 of
`PLAN-scm-oi-sheet-pairing-repair.md`. Measured on prod: SO314593's open AutoCount lines
are 220 @ 01/03/2027 while the sheet said 182 @ 1.9.2026 - 7.4 wrote the LINE's date onto
every migrated row, so the worklist read a delivery purchasing was not working to, and a
re-upload of a corrected sheet did nothing because `_already_raised` skips a line that
already carries a row.

TEST-FIRST: the red state before the fix is the OLD rule (the raised row's `delivery_date`
reads the line's `required_date` over the sheet's) and a missing `DELIVERY_DATE_UPDATED`
repair on re-upload - never an import error.

Fix round 1 (19 Sep 2026, Opus review) added AC-8 to AC-13: B1 (repair candidates are
resolved per LINE, not per row - a sheet that splits one line's quantity across several
dated rows has no per-row identity a bare item/qty match can tell apart), B2 (a migrated
row a planning change has since restated keeps the change's own date, never the repair's),
S1 (`preview` forecasts the exact count `apply` writes) and S5 (a sibling's Was/Now moves
with the repair). AC-4/AC-5 were adjusted so their sibling carries a real
`redirected_to_pool` migrated row to recompute FROM, matching S5's own rule instead of the
superseded ad-hoc qty/date match the first round shipped.

Postgres only (`tests/_pg_fixture.py`, via `world()`). The world, sheet and apply builders
are IMPORTED from `tests/test_project_order_inquiry_import_migration.py` and
`tests/test_oi_sheet_pairing_repair.py` rather than copied, so the three files cannot
drift about what a seeded world is.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.models.project_so import INQUIRY_CANCELLED, INQUIRY_PLACED, IV_ORDER_BACK, OrderInquiryRow
from app.services import import_outcome_codes as oc
from app.services import project_order_inquiry_import_service as importer
from app.services.import_outcome import ImportOutcome

from .test_oi_sheet_pairing_repair import _apply
from .test_project_order_inquiry_import_migration import World, sheet, world


def _migrated_row(
    w: World, mirror, *, qty: str, delivery_date: date, redirected_to_pool: bool = False
) -> OrderInquiryRow:
    """A row shaped exactly like the ones section 7.4 wrote: raised by an earlier upload,
    carrying the migration stamp. `redirected_to_pool=True` is the S5 shape - a row a later
    planning change released back to stock, which is what the sibling's Was/Now is read
    off (AC-OH-40..42)."""
    row = w.board_row(mirror, qty=qty)
    row.delivery_date = delivery_date
    row.note = importer._MIGRATION_STAMP
    row.redirected_to_pool = redirected_to_pool
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
    note: str | None = None,
) -> OrderInquiryRow:
    """The row a later planning change raised beside a migrated one, carrying the Was/Now
    pair `_settle_row_in_place` stamped from the redirected rows it replaced - the
    SO314593/SO314594 shape."""
    row = w.board_row(mirror, qty=qty)
    row.delivery_date = delivery_date
    row.previous_qty = Decimal(previous_qty)
    row.previous_delivery_date = previous_delivery_date
    if note is not None:
        row.note = note
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
    """AC-4. The SO314593 shape: a migrated row (182 @ 2027-03-01, released to the pool)
    and a fresh sibling raised beside it (220, previous_qty 182 / previous_delivery_date
    2027-03-01). A LATER, DIFFERENTLY NAMED sheet (N4: the repair is not scoped to the
    uploading file) says 182 @ 2026-09-01. The migrated row's own date moves to the
    sheet's, the sibling's Was/Now pair moves with it, and nothing else changes: no new
    row, the sibling's own qty/delivery_date untouched, one outcome code."""
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
        migrated.redirected_to_pool = True
        mirror = w.mirror_of(line)
        w.db.flush()

        sibling = _fresh_row(
            w, mirror, qty="220", delivery_date=sibling_date,
            previous_qty="182", previous_delivery_date=old_date,
            note=f"Was 182 on {old_date.isoformat()}",
        )

        outcome_recorder = ImportOutcome(None, persist=False)
        data = sheet([
            (order.so_number, w.product.product_code, 182, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        # A DIFFERENT file name than the one that migrated the row (N4).
        result = _apply(w, data, outcome=outcome_recorder, file_name="2026-09 corrected.xlsx")

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 1, result
        rows = w.rows()
        assert len(rows) == 2, "no new row was raised"

        w.db.refresh(migrated)
        w.db.refresh(sibling)
        assert migrated.delivery_date == sheet_date
        assert sibling.previous_delivery_date == sheet_date
        assert Decimal(str(sibling.previous_qty)) == Decimal("182")
        assert Decimal(str(sibling.qty)) == Decimal("220")
        assert sibling.delivery_date == sibling_date
        assert sibling.note == f"Was 182 on {sheet_date.isoformat()}"
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
        migrated = w.one_row()
        migrated.redirected_to_pool = True
        mirror = w.mirror_of(line)
        w.db.flush()
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


def test_ac_8_repairs_are_resolved_per_line_not_per_row():
    """AC-8 (B1, 19 Sep 2026). A sheet that splits one line's quantity into two equal-qty,
    differently dated rows has no per-row identity a bare item/qty match can tell apart -
    resolved per LINE instead: pass 1 settles a row that already carries its own exact
    date as a no-op, pass 2 lets only the row that does NOT already match claim the
    remaining candidate. An unchanged re-upload must therefore write nothing, and a sheet
    that moves only ONE of the two rows must move only its own migrated counterpart -
    deterministically, on a second identical re-upload too.
    """
    sept, oct_, nov = date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="500", required_date=date(2030, 1, 1))
        raise_sheet = sheet([
            (order.so_number, w.product.product_code, 100, sept,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 100, oct_,
             w.warehouse.warehouse_code, ""),
        ])

        raised = _apply(w, raise_sheet, file_name="2026-08 order inquiry.xlsx")
        assert raised["rows_raised"] == 2, raised
        rows = w.rows()
        assert len(rows) == 2
        sept_row = next(r for r in rows if r.delivery_date == sept)
        oct_row = next(r for r in rows if r.delivery_date == oct_)

        # Re-upload of the SAME, unchanged sheet: nothing to repair.
        unchanged = _apply(w, raise_sheet, file_name="2026-08 order inquiry.xlsx")
        assert unchanged["rows_raised"] == 0, unchanged
        assert unchanged["rows_delivery_date_updated"] == 0, unchanged
        w.db.refresh(sept_row)
        w.db.refresh(oct_row)
        assert sept_row.delivery_date == sept
        assert oct_row.delivery_date == oct_

        # Only the October row moves, to November.
        moved_sheet = sheet([
            (order.so_number, w.product.product_code, 100, sept,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 100, nov,
             w.warehouse.warehouse_code, ""),
        ])
        moved = _apply(w, moved_sheet, file_name="2026-09 corrected.xlsx")
        assert moved["rows_raised"] == 0, moved
        assert moved["rows_delivery_date_updated"] == 1, moved
        w.db.refresh(sept_row)
        w.db.refresh(oct_row)
        assert sept_row.delivery_date == sept, "the untouched row moved"
        assert oct_row.delivery_date == nov, "the row the sheet actually moved did not"

        # Deterministic: the SAME move re-applied writes nothing further.
        again = _apply(w, moved_sheet, file_name="2026-09 corrected.xlsx")
        assert again["rows_delivery_date_updated"] == 0, again
        w.db.refresh(sept_row)
        w.db.refresh(oct_row)
        assert sept_row.delivery_date == sept
        assert oct_row.delivery_date == nov


def test_ac_9_a_row_a_planning_change_settled_keeps_the_changes_date():
    """AC-9 (B2, 19 Sep 2026). A migrated row a planning change has since restated
    (`previous_qty`/`previous_delivery_date`/`changed_at` all set, state PLACED, moved to
    November by the change) is purchasing's own work, not the migration's mistake - the
    repair must never revert it. Covers the reviewer's own probe: today the repair
    reverted a placed row's planning change and its own Was/Now read the same date twice.
    """
    old_date = date(2027, 3, 1)
    changed_date = date(2026, 11, 1)
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="400", required_date=old_date)
        migration_sheet = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, migration_sheet, file_name="2026-08 order inquiry.xlsx")
        settled = w.one_row()
        # A planning change restated it: its OWN Was/Now, its own state, unrelated to the
        # sheet's original figures.
        settled.previous_qty = Decimal("150")
        settled.previous_delivery_date = old_date
        settled.changed_at = datetime(2026, 9, 10, 8, 0, 0)
        settled.delivery_date = changed_date
        settled.state = INQUIRY_PLACED
        w.db.flush()

        data = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 0, result
        w.db.refresh(settled)
        assert settled.delivery_date == changed_date, (
            "a planning change's own date was reverted by the repair"
        )
        assert settled.previous_delivery_date == old_date, (
            "the change's own Was/Now was overwritten"
        )


def test_ac_10_an_undated_row_never_writes_null_over_a_migrated_row():
    """AC-10 (S2, 19 Sep 2026). An ORDER BACK re-upload states no date at all - it must
    never claim, and never blank, a migrated row's date."""
    old_date = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="400", required_date=old_date)
        migration_sheet = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, migration_sheet, file_name="2026-08 order inquiry.xlsx")
        migrated = w.one_row()

        data = sheet([
            (order.so_number, w.product.product_code, 182, "ORDER BACK",
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 0, result
        w.db.refresh(migrated)
        assert migrated.delivery_date == old_date, "an undated row wrote NULL over a date"


def test_ac_11_a_cancelled_migrated_row_is_never_repaired():
    """AC-11 (S2, 19 Sep 2026). The line's live row is a different quantity, so the sheet's
    182 matches only a CANCELLED migrated row - which must never be repaired, even though
    it is the only quantity match on the line."""
    old_date = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=old_date)
        migration_sheet = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, migration_sheet, file_name="2026-08 order inquiry.xlsx")
        cancelled = w.one_row()
        cancelled.state = INQUIRY_CANCELLED
        mirror = w.mirror_of(line)
        w.db.flush()
        # The live counterpart that makes the LINE already-raised, a different quantity.
        live = w.board_row(mirror, qty="50")
        live.delivery_date = old_date
        w.db.flush()

        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 9, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 0, result
        w.db.refresh(cancelled)
        assert cancelled.delivery_date == old_date, "a cancelled row was repaired"


def test_ac_12_preview_forecasts_the_exact_repair_count():
    """AC-12 (S1, 19 Sep 2026). `preview` decides the repair read-only in `_plan`, so it
    reports `rows_delivery_date_updated` BEFORE Confirm, and `apply` writes exactly that
    many - never a caller-supplied count the two paths could drift apart on."""
    old_date = date(2027, 3, 1)
    sheet_date = date(2026, 9, 1)
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="400", required_date=old_date)
        migration_sheet = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, migration_sheet, file_name="2026-08 order inquiry.xlsx")

        data = sheet([
            (order.so_number, w.product.product_code, 182, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        preview = importer.preview(w.db, data)
        assert preview["rows_delivery_date_updated"] == 1, preview

        applied = _apply(w, data)
        assert applied["rows_delivery_date_updated"] == preview["rows_delivery_date_updated"]


def test_ac_13_two_released_rows_recompute_the_siblings_was_now():
    """AC-13 (S5, 19 Sep 2026). Two migrated rows released to the pool (100 + 82, both
    2027-03-01) and a sibling whose Was/Now was stamped from them (`previous_qty` 182,
    `previous_delivery_date` 2027-03-01, note prose "Was 182 on 2027-03-01"). The sheet
    corrects the two released rows to DIFFERENT dates (2026-09-01 and 2026-10-01); the
    sibling's `previous_delivery_date` recomputes to the EARLIEST of the two, `previous_qty`
    is untouched, and the note prose is corrected to match."""
    old_date = date(2027, 3, 1)
    sept, oct_ = date(2026, 9, 1), date(2026, 10, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="500", required_date=old_date)
        migration_sheet = sheet([
            (order.so_number, w.product.product_code, 100, old_date,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 82, old_date,
             w.warehouse.warehouse_code, ""),
        ])
        raised = _apply(w, migration_sheet, file_name="2026-08 order inquiry.xlsx")
        assert raised["rows_raised"] == 2, raised
        mirror = w.mirror_of(line)
        for row in w.rows():
            row.redirected_to_pool = True
        w.db.flush()

        sibling = _fresh_row(
            w, mirror, qty="220", delivery_date=date(2027, 8, 1),
            previous_qty="182", previous_delivery_date=old_date,
            note=f"Was 182 on {old_date.isoformat()}",
        )

        data = sheet([
            (order.so_number, w.product.product_code, 100, sept,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 82, oct_,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data, file_name="2026-09 corrected.xlsx")

        assert result["rows_delivery_date_updated"] == 2, result
        w.db.refresh(sibling)
        assert sibling.previous_delivery_date == sept, "not the EARLIEST of the two dates"
        assert Decimal(str(sibling.previous_qty)) == Decimal("182"), "previous_qty moved"
        assert sibling.note == f"Was 182 on {sept.isoformat()}"
