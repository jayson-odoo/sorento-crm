"""What still holds of the OI sheet's delivery date (OI-ONE-DELIVERY-DATE, 3 Nov 2026).

The 18 Sep 2026 rule ("we should have followed the sheet's date") and the three re-upload
repair shapes it grew (A, B, C, fix rounds 1 to 6) are retired: a raised row now takes the SO
LINE's date, with the sheet's date kept as its Was (`test_oi_one_delivery_date_sheet_import.py`),
and a re-upload moves no date. This file keeps the helpers other suites import and the
tests of what the retirement left in force.

Postgres only (`tests/_pg_fixture.py`, via `world()`). The world, sheet and apply builders
are IMPORTED from `tests/test_project_order_inquiry_import_migration.py` and
`tests/test_oi_sheet_pairing_repair.py` rather than copied, so the three files cannot
drift about what a seeded world is.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import pytest

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


def _settled_row(
    w: World,
    mirror,
    *,
    qty: str,
    delivery_date: date,
    previous_qty: str,
    previous_delivery_date: date,
    note: str,
) -> OrderInquiryRow:
    """Shape B, round 5 (19 Sep 2026, prod feedback after #1004 deployed): the MIGRATED row
    itself, restated IN PLACE by a planning change - its Now (`qty`/`delivery_date`) is the
    change's own correct figure, and its Was (`previous_qty`/`previous_delivery_date`) can
    still carry 7.4's mistake. There is no fresh sibling for this shape - the migrated row
    carries both pairs itself. `note` still starts with the migration stamp:
    `_settle_row_in_place` APPENDS to the row's own note rather than replacing it."""
    row = w.board_row(mirror, qty=qty)
    row.delivery_date = delivery_date
    row.previous_qty = Decimal(previous_qty)
    row.previous_delivery_date = previous_delivery_date
    row.note = note
    w.db.flush()
    return row


def _register_migrated(w: World, row: OrderInquiryRow, *, outcome: str = "created") -> None:
    """Stamps `row` into `import_job_rows` the way the importer's own
    `ImportOutcome.success(..., entity_type="order_inquiry_row", entity_id=entry.id)` does
    on every row it raises (S1, round 7 review round 2). Shape C's sibling identity reads
    THIS, never the row's own note - a cancel overwrites the note to "Superseded by
    revision N", so the note can never be trusted once a row is superseded.

    `outcome`, default `"created"`: the identity check is `outcome = 'created'`
    SPECIFICALLY, since only a row's own RAISE writes `entity_type="order_inquiry_row"` -
    an `outcome="updated"` row (round 7 review round 3) is a repair `apply()` records
    against an EXISTING row's own id, never a fresh one, so it must never itself qualify a
    row as a migrated sibling."""
    from app.models.job import ImportJob, ImportJobRow

    job = ImportJob(
        id=str(uuid.uuid4()),
        job_id=f"ZZT-OISD-job-{uuid.uuid4().hex[:8]}",
        job_type="order_inquiry",
        status="finished",
        user_id=w.actor,
    )
    w.db.add(job)
    w.db.flush()
    w.db.add(
        ImportJobRow(
            id=str(uuid.uuid4()),
            import_job_id=job.id,
            row_number=1,
            outcome=outcome,
            code=outcome,
            entity_type="order_inquiry_row",
            entity_id=str(row.id),
        )
    )
    w.db.flush()


def _cancelled_sibling(
    w: World,
    mirror,
    *,
    qty: str,
    previous_qty: str | None = None,
    previous_delivery_date: date | None = None,
    revision: int = 2,
) -> OrderInquiryRow:
    """Shape C's own sibling, round 7 (19 Sep 2026, revised after the real prod SELECT): a
    migrated row a reconfirm CANCELLED, its note overwritten to "Superseded by revision N"
    (`_settle_row_in_place`'s cancel path REPLACES the note, never appends - the migration
    stamp is gone, so this row can never be found by it, only by quantity). Registered in
    `import_job_rows` (`_register_migrated`) exactly as the importer registers every row it
    raises (S1, round 7 review round 2) - THAT is what makes it a genuine migrated sibling,
    not the note or the quantity alone. `previous_qty`/`previous_delivery_date` are set
    only when it was settled once before being superseded (SO314593's own shape); left
    `None` is the "never settled" shape."""
    row = w.board_row(mirror, qty=qty)
    row.state = INQUIRY_CANCELLED
    row.note = f"Superseded by revision {revision}"
    if previous_qty is not None:
        row.previous_qty = Decimal(previous_qty)
    if previous_delivery_date is not None:
        row.previous_delivery_date = previous_delivery_date
    w.db.flush()
    _register_migrated(w, row)
    return row


def _cancelled_board_row(
    w: World, mirror, *, qty: str, revision: int = 2
) -> OrderInquiryRow:
    """S1, round 7 review round 2. A cancelled row that LOOKS exactly like shape C's own
    sibling (same quantity, same "Superseded by revision N" note a cancel leaves) but was
    never raised by an upload at all - a plain cancelled BOARD row. Never registered in
    `import_job_rows`, so it must never be mistaken for a migrated sibling."""
    row = w.board_row(mirror, qty=qty)
    row.state = INQUIRY_CANCELLED
    row.note = f"Superseded by revision {revision}"
    w.db.flush()
    return row


def _live_row(
    w: World,
    mirror,
    *,
    qty: str,
    delivery_date: date,
    created_at: datetime | None = None,
) -> OrderInquiryRow:
    """Shape C's own live row, round 7 (19 Sep 2026): the fresh row a reconfirm RAISED in
    place of a cancelled migrated one - board-raised, no migration stamp, no Was at all.

    `created_at` is an explicit override (review round 3, S2): the column's own default is
    the database's `now()`, which is the SAME value for every row a single test transaction
    writes (Postgres ties `now()` to the transaction, not the statement), so two live rows
    this helper raises in the SAME test carry a TIED `created_at` and the query's
    `order_by(created_at.asc(), id.asc())` falls back to comparing randomly-generated ids -
    a test relying on creation ORDER to be deterministic must set this explicitly."""
    row = w.board_row(mirror, qty=qty)
    row.delivery_date = delivery_date
    if created_at is not None:
        row.created_at = created_at
    w.db.flush()
    return row


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


def test_reupload_moves_no_date_and_reports_no_correction():
    """OI-ONE-DELIVERY-DATE (AC-C2, 3 Nov 2026): the repair of a migrated row's date to the
    sheet's own is retired with the 18 Sep ruling it served. A later sheet that states a
    different date for an already-raised line moves nothing and reports no correction."""
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
        migrated = w.one_row()
        data = sheet([
            (order.so_number, w.product.product_code, 182, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data, file_name="2026-09 corrected.xlsx")

        assert result["rows_raised"] == 0, result
        assert result["rows_delivery_date_updated"] == 0, result
        w.db.refresh(migrated)
        assert migrated.delivery_date == old_date
        assert migrated.previous_delivery_date is None
