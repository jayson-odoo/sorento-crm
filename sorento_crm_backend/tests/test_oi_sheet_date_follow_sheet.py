"""RETIRED BY OI-ONE-DELIVERY-DATE (3 Nov 2026): the sheet-date repairs below no longer run; the raised row takes the SO LINE date (see test_oi_one_delivery_date_sheet_import.py). Kept: the helpers other suites import and the tests of what still holds.

The order inquiry sheet's raised row took the SHEET's own delivery date.

Contract: `documentation/plans/scm/oi-sheet-date-follow-sheet-acceptance-criteria.md`,
AC-1 to AC-29 (AC-19 onward carried by `PLAN-oi-sheet-date-settled-rows.md`'s own UAC,
AC-25 onward by `PLAN-oi-sheet-date-adopt-was.md`'s).
`PLAN-oi-sheet-date-follow-sheet.md` (18 Sep 2026 owner ruling: "we should
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

Fix round 2 (19 Sep 2026, Opus review round 2) added AC-14 to AC-16 and the two DB-free
`_resolve_line_repairs` unit tests: B3 (a sibling's Was/Now is only ever touched when its
OWN `(previous_delivery_date, previous_qty)` is EXACTLY the redirected rows' pairing,
captured BEFORE this run's own repairs - never "any sibling on the mirror" - and the note
edit is anchored to the `"Was {qty} on {date}"` fragment, never a bare date substring), S7
(each of B2's three markers blocks the repair alone), S8 (the repair is confined to rows
still on their core line's own `required_date` - 7.4's own fingerprint, and nothing else)
and S9 (the resolver's ordering contract, pinned once DB-free on the pure function and once
against the database). AC-8 was rewritten to the 7.4-legacy shape (two migrated rows
sharing the LINE's date, not two sheet-dated rows) since S8 confines a repair to exactly
that fingerprint.

Fix round 3 (19 Sep 2026, Opus review round 3, READY) closed three fixture-guard mutants on
AC-14a (S12: a matched sibling whose OWN note also carries an "AutoCount moved ... on
<date>" line at the date the repair moves; a near-miss sibling sharing only the matched
sibling's quantity; a near-miss sibling sharing only its date) and moved S8's equality out
of SQL into a plain Python comparison for performance (S13) with no change to the
criterion AC-15 pins.

Round 4 (19 Sep 2026, found running the real book `JAN - DEC 2026 ORDERabc.xlsx` through
the lane stack) added AC-18: SO314593's rows were skipped as already-raised rather than
repaired because `_as_date` (`project_order_inquiry_reader.py`) answered `None` for a
DELIVERY DATE cell written as TEXT - the book stores some as literal strings - so
`row.delivery_date` was `None` at migration (the LINE's date fallback fired regardless of
7.4) and stayed `None` on re-upload (an undated row correctly claims nothing, per AC-10).
The root cause is upstream of this plan's own change and is fixed in the reader, not the
importer; `test_project_order_inquiry_import_reader.py` carries the reader-level reds.

Round 5 (19 Sep 2026, found on prod after #1004 deployed and the owner ran the real book)
added AC-19 to AC-23, a second repair shape. SO314593's SRTWCX8605-S-RL-PJ / CB2806A-DIY /
SRTWB245 rows were skipped as already-raised rather than repaired: the MIGRATED row itself
had been restated IN PLACE by a planning change (no fresh sibling), so its Now
(`qty`/`delivery_date`) is a change's own correct figure, but its Was
(`previous_qty`/`previous_delivery_date`) still carried 7.4's mistake - the sheet's row
describes the row's WAS state, not a fresh instruction, and shape A's own rule (B2's
`previous_*` NULL markers, plus the qty match against the row's CURRENT `qty`) excludes it
by design. Shape B repairs `previous_delivery_date` instead, matching the sheet's quantity
against `previous_qty`, leaving the row's Now, `changed_at` and `ack_state` untouched -
`_resolve_shape_b_repairs`, run only for sheet rows shape A leaves unclaimed.

Round 5's own review (19 Sep 2026, READY with two should-fixes) added AC-24 and adjusted
AC-19: S14, shape B's first cut had no date comparison of its own, so a sheet row already
on the settled row's Was date was counted and reported `DELIVERY_DATE_UPDATED` on every
run while nothing changed - fixed with shape B's own pass-1 no-op claim, mirroring shape
A's. S15, AC-19's note put the old date in only ONE clause, so an unanchored bare-date
replace and the correct anchored one produced the SAME final note and the mutant survived
undetected - fixed by giving the note's "expected ..." clause the SAME old date as its
"Was ..." fragment (AC-14a, shape A's own version of this test from round 3, was checked
against the same gap and found already correct). N10 (optional, taken): `_resolve_line_
repairs` now returns `(repairs, exact_matched)` so `_resolve_shape_b_repairs` reads shape
A's own pass-1 result instead of re-deriving it; its two DB-free unit tests were adjusted
for the tuple.

Round 6 (19 Sep 2026, owner go, prod feedback after #1011 deployed) added AC-25 to AC-29,
a THIRD repair shape. SO314593's CB2806A-DIY (220) and SRTWB245 (280) were skipped as
already-raised: a board Confirm restated each row IN PLACE on 17 Sep 2026 (10:11 and 11:25
MYT), BEFORE #992 deployed and before any Was was ever recorded - so both carry
`changed_at IS NOT NULL` (something restated an acknowledged row) but `previous_qty`/
`previous_delivery_date` are still `NULL`. Verified against
`ProjectOrderInquiryService._settle_row_in_place`, the ONLY writer of `changed_at` in that
service, at both its pre-#992 shape (`git show a3d215ab9:...`, the commit `e91ec3614`/#992
was built on) and its current one: both ALWAYS pair the `changed_at` stamp with
`previous_qty`/`previous_delivery_date` in the SAME write, so `changed_at` alone is a
trustworthy "this row was restated" marker - never "somebody just edited the sheet's
quantity", which never reaches this service at all. Shape C adopts the sheet row as the
Was the settle never got to write - `previous_qty`/`previous_delivery_date` move from
`NULL` to the sheet's own figures, the note's "Was ... on ..." fragment is appended (none
existed to anchor onto before), and the row's Now, `qty`, `state` and `ack_state` stay
untouched. `_resolve_shape_c_repairs`, run only for sheet rows shapes A and B leave
unclaimed - "exact match, shape A, shape B, shape C" is the full priority order.

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
