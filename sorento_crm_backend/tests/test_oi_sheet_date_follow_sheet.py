"""The order inquiry sheet's raised row takes the SHEET's own delivery date.

Contract: `documentation/plans/_archive/scm/oi-sheet-date-follow-sheet-acceptance-criteria.md`,
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
    """AC-8 (B1, 19 Sep 2026). The 7.4-era shape: TWO migrated rows on one line, raised
    with no sheet date of their own, so BOTH carry the line's own `required_date` - the
    exact fingerprint 7.4's bug leaves, and the only shape S8 lets a repair touch. A sheet
    that splits them into two DIFFERENT real dates has no per-row identity a bare item/qty
    match can tell the two migrated rows apart by - resolved per LINE instead: pass 2 gives
    each dated sheet row a DIFFERENT one of the two candidates, never both fighting over
    the same first match. An unchanged re-upload of that corrected sheet then writes
    nothing further, since pass 1 now finds an exact match for each.
    """
    from app.services.project_so_adoption_service import ProjectSOAdoptionService

    line_date = date(2027, 3, 1)
    sept, oct_ = date(2026, 9, 1), date(2026, 10, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="500", required_date=line_date)
        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        row_a = _migrated_row(w, mirror, qty="100", delivery_date=line_date)
        row_b = _migrated_row(w, mirror, qty="100", delivery_date=line_date)

        data = sheet([
            (order.so_number, w.product.product_code, 100, sept,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 100, oct_,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data, file_name="2026-09 corrected.xlsx")

        assert result["rows_raised"] == 0, result
        assert result["rows_delivery_date_updated"] == 2, result
        w.db.refresh(row_a)
        w.db.refresh(row_b)
        dates = sorted([row_a.delivery_date, row_b.delivery_date])
        assert dates == [sept, oct_], (
            "both migrated rows should be split across the two dates, one each"
        )

        # Deterministic: the SAME corrected sheet re-applied writes nothing further -
        # pass 1 now finds an exact item/qty/date match for each row.
        again = _apply(w, data, file_name="2026-09 corrected.xlsx")
        assert again["rows_delivery_date_updated"] == 0, again
        w.db.refresh(row_a)
        w.db.refresh(row_b)
        assert sorted([row_a.delivery_date, row_b.delivery_date]) == [sept, oct_]


def test_ac_15_a_row_not_on_the_lines_required_date_is_never_repaired():
    """AC-15 (S8, 19 Sep 2026). The migrated row was raised with a date of the SHEET's own
    (this fix's rule, not 7.4's), so it already differs from the line's `required_date` -
    not 7.4's own mistake, and a later sheet is never a second opinion about it, whatever
    it says."""
    required = date(2027, 3, 1)
    edited_date = date(2026, 12, 25)
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="400", required_date=required)
        migration_sheet = sheet([
            (order.so_number, w.product.product_code, 182, edited_date,
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, migration_sheet, file_name="2026-08 order inquiry.xlsx")
        migrated = w.one_row()
        assert migrated.delivery_date == edited_date
        assert migrated.delivery_date != required

        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 9, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 0, result
        w.db.refresh(migrated)
        assert migrated.delivery_date == edited_date


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


@pytest.mark.parametrize("marker", ["previous_qty", "previous_delivery_date", "changed_at"])
def test_ac_9b_each_b2_marker_alone_blocks_the_repair(marker: str):
    """AC-9 (S7, 19 Sep 2026). Each of the three B2 markers must block the repair ALONE - a
    mutant that drops one of the three filter conditions and keeps the other two would
    otherwise stay green. The migrated row's own `delivery_date` is left AT the line's
    `required_date` here (unlike AC-9's own richer probe), so S8's gate is not what is
    blocking it - only the ONE marker under test is."""
    old_date = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="400", required_date=old_date)
        migration_sheet = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, migration_sheet, file_name="2026-08 order inquiry.xlsx")
        marked = w.one_row()
        if marker == "previous_qty":
            marked.previous_qty = Decimal("150")
        elif marker == "previous_delivery_date":
            marked.previous_delivery_date = old_date
        else:
            marked.changed_at = datetime(2026, 9, 10, 8, 0, 0)
        w.db.flush()

        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 9, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_delivery_date_updated"] == 0, (marker, result)
        assert result["rows_already_raised"] == 1, (marker, result)
        w.db.refresh(marked)
        assert marked.delivery_date == old_date, marker


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
    it is the only quantity match on the line.

    The live row's own `delivery_date` deliberately differs from the line's own
    `required_date` (round 7 review): a live row ON the line's date with no Was of its own
    is EXACTLY shape C's own live-row shape, and this cancelled sibling's quantity (182)
    matches the sheet's - so with the live row ON the line's date this test would exercise
    a genuine shape-C adoption instead of the isolated "a cancelled row is never touched"
    case it means to pin. Off the line's date, neither shape reaches it.
    """
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
        # The live counterpart that makes the LINE already-raised, a different quantity
        # AND a different date - see the docstring above for why the date matters now.
        live = w.board_row(mirror, qty="50")
        live.delivery_date = date(2026, 1, 1)
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


def test_ac_14a_an_unrelated_siblings_was_now_is_byte_for_byte_untouched():
    """AC-14a (B3, 19 Sep 2026). Four siblings on one mirror, one of them the MATCH:

    * `matched` carries the EXACT `(previous_delivery_date, previous_qty)` the redirected
      row produced, AND its own "AutoCount moved ... on <old_date>" provenance line at the
      SAME date the repair moves - the anchor must touch only the "Was ... on" fragment,
      never the provenance line, even though both contain the identical date text (S12a).
    * `same_qty_diff_date` shares the matched sibling's `previous_qty` (182) but a
      DIFFERENT `previous_delivery_date` - untouched (S12b).
    * `same_date_diff_qty` shares the matched sibling's `previous_delivery_date` but a
      DIFFERENT `previous_qty` - untouched (S12c).
    * `unrelated`, an already-PLACED sibling with an entirely different pairing and its own
      "AutoCount moved ... on <date>" line, untouched byte for byte.

    The match is on the EXACT pairing the redirected rows produced, never "any sibling on
    this mirror".
    """
    old_date = date(2027, 3, 1)
    sheet_date = date(2026, 9, 1)
    unrelated_date = date(2026, 5, 1)
    unrelated_note = f"AutoCount moved PO-1 to SO-9 on {unrelated_date.isoformat()}; Was 25 on {unrelated_date.isoformat()}"
    matched_note = (
        f"AutoCount moved PO-2 to SO-10 on {old_date.isoformat()}; "
        f"Was 182 on {old_date.isoformat()}"
    )
    same_qty_diff_date_note = "Was 182 on 2026-04-01"
    same_date_diff_qty_note = f"Was 50 on {old_date.isoformat()}"
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

        matched = _fresh_row(
            w, mirror, qty="220", delivery_date=date(2027, 6, 1),
            previous_qty="182", previous_delivery_date=old_date, note=matched_note,
        )
        same_qty_diff_date = _fresh_row(
            w, mirror, qty="30", delivery_date=date(2026, 7, 1),
            previous_qty="182", previous_delivery_date=date(2026, 4, 1),
            note=same_qty_diff_date_note,
        )
        same_date_diff_qty = _fresh_row(
            w, mirror, qty="40", delivery_date=date(2026, 8, 1),
            previous_qty="50", previous_delivery_date=old_date,
            note=same_date_diff_qty_note,
        )
        unrelated = _fresh_row(
            w, mirror, qty="25", delivery_date=date(2026, 6, 1),
            previous_qty="25", previous_delivery_date=unrelated_date,
            note=unrelated_note,
        )
        unrelated.state = INQUIRY_PLACED
        w.db.flush()

        data = sheet([
            (order.so_number, w.product.product_code, 182, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data, file_name="2026-09 corrected.xlsx")

        assert result["rows_delivery_date_updated"] == 1, result

        w.db.refresh(matched)
        assert matched.previous_delivery_date == sheet_date
        assert matched.note == (
            f"AutoCount moved PO-2 to SO-10 on {old_date.isoformat()}; "
            f"Was 182 on {sheet_date.isoformat()}"
        ), "the AutoCount provenance line must survive verbatim; only the Was fragment moves"

        w.db.refresh(same_qty_diff_date)
        assert same_qty_diff_date.previous_delivery_date == date(2026, 4, 1), (
            "a sibling sharing only the quantity was rewritten"
        )
        assert same_qty_diff_date.note == same_qty_diff_date_note

        w.db.refresh(same_date_diff_qty)
        assert same_date_diff_qty.previous_delivery_date == old_date, (
            "a sibling sharing only the date was rewritten"
        )
        assert same_date_diff_qty.note == same_date_diff_qty_note

        w.db.refresh(unrelated)
        assert unrelated.previous_delivery_date == unrelated_date, (
            "an unrelated sibling's Was/Now was rewritten by a repair on the same mirror"
        )
        assert unrelated.note == unrelated_note, (
            "an unrelated sibling's note (including its AutoCount provenance line) was "
            "falsified by an unanchored note edit"
        )


def test_ac_14b_the_redirected_to_pool_gate_is_not_ignored():
    """AC-14b (B3, 19 Sep 2026). A non-redirected migrated row on the SAME mirror, dated
    EARLIER than the redirected row's own date, must never enter the earliest-date
    computation - only `redirected_to_pool` rows do."""
    old_date = date(2027, 3, 1)
    earlier_date = date(2026, 1, 1)
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

        # A non-redirected migrated row, EARLIER than the redirected one - must be ignored.
        _migrated_row(w, mirror, qty="50", delivery_date=earlier_date, redirected_to_pool=False)

        sibling = _fresh_row(
            w, mirror, qty="220", delivery_date=date(2027, 8, 1),
            previous_qty="182", previous_delivery_date=old_date,
            note=f"Was 182 on {old_date.isoformat()}",
        )

        data = sheet([
            (order.so_number, w.product.product_code, 182, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data, file_name="2026-09 corrected.xlsx")

        assert result["rows_delivery_date_updated"] == 1, result
        w.db.refresh(sibling)
        assert sibling.previous_delivery_date == sheet_date, (
            "the non-redirected, earlier-dated row was counted into the earliest date"
        )


# ---------------------------------------------------------------------------------- #
# S9: _resolve_line_repairs is DB-free and pins the caller's own ordering contract    #
# ---------------------------------------------------------------------------------- #


@dataclass
class _FakeMigratedRow:
    id: str
    item_code: str
    qty: Decimal
    delivery_date: date


@dataclass
class _FakeSheetRow:
    item_code: str
    qty: Decimal
    delivery_date: date


def test_resolve_line_repairs_trusts_the_callers_own_order():
    """S9. `_resolve_line_repairs` takes no database and does not re-derive
    `created_at`/`id` itself - it trusts the ORDER it is handed. Passing the SAME two
    candidates in the opposite order changes which one an ambiguous row claims, which pins
    the contract `_resolve_delivery_date_repairs`'s own `ORDER BY created_at, id` relies on.
    Returns `(repairs, exact_matched)` (N10, round 4 review) - here `exact_matched` is
    always empty, since neither candidate exactly matches the dated row's own date.
    """
    row_a = _FakeMigratedRow(
        id="row-a", item_code="ITEM", qty=Decimal("100"), delivery_date=date(2027, 3, 1)
    )
    row_b = _FakeMigratedRow(
        id="row-b", item_code="ITEM", qty=Decimal("100"), delivery_date=date(2027, 3, 1)
    )
    dated_row = _FakeSheetRow(
        item_code="ITEM", qty=Decimal("100"), delivery_date=date(2026, 9, 1)
    )

    first, first_settled = importer._resolve_line_repairs([(0, dated_row)], [row_a, row_b])
    assert first == {0: "row-a"}
    assert first_settled == set()

    reversed_order, reversed_settled = importer._resolve_line_repairs(
        [(0, dated_row)], [row_b, row_a]
    )
    assert reversed_order == {0: "row-b"}
    assert reversed_settled == set()


def test_resolve_line_repairs_pass_one_settles_exact_matches_first():
    """S9. Pass 1 claims exact item/quantity/date matches as no-ops BEFORE pass 2 ever
    runs, whatever order the candidates were handed in - an unchanged, split-quantity
    re-upload must resolve to NO repairs even when its own migrated rows are scrambled, and
    both rows come back in the SECOND return value (`exact_matched`, N10)."""
    sept, oct_ = date(2026, 9, 1), date(2026, 10, 1)
    row_oct = _FakeMigratedRow(id="row-oct", item_code="ITEM", qty=Decimal("100"), delivery_date=oct_)
    row_sept = _FakeMigratedRow(id="row-sept", item_code="ITEM", qty=Decimal("100"), delivery_date=sept)
    dated_rows = [
        (0, _FakeSheetRow(item_code="ITEM", qty=Decimal("100"), delivery_date=sept)),
        (1, _FakeSheetRow(item_code="ITEM", qty=Decimal("100"), delivery_date=oct_)),
    ]

    # Scrambled: row_oct listed BEFORE row_sept.
    repairs, exact_matched = importer._resolve_line_repairs(dated_rows, [row_oct, row_sept])

    assert repairs == {}, "both rows exactly matched their own migrated row; nothing to repair"
    assert exact_matched == {0, 1}, "both rows should be settled as exact no-op matches"


def test_ac_16_the_eligible_query_orders_by_created_at_then_id():
    """AC-16 (S9, DB). Two migrated rows on one line, same item/qty, whose INSERTION order
    disagrees with their `created_at` - the resolution must still pick the one with the
    EARLIER `created_at` first, proving `_resolve_delivery_date_repairs`'s own `ORDER BY`
    (not `_resolve_line_repairs`, which trusts what it is handed) decides the order.
    """
    from app.services.project_so_adoption_service import ProjectSOAdoptionService

    required = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)

        inserted_first = _migrated_row(w, mirror, qty="100", delivery_date=required)
        inserted_second = _migrated_row(w, mirror, qty="100", delivery_date=required)
        # Force the SECOND-inserted row to carry the EARLIER `created_at`, so insertion
        # order and `created_at` order disagree.
        inserted_first.created_at = datetime(2026, 8, 20, 10, 0, 0)
        inserted_second.created_at = datetime(2026, 8, 10, 9, 0, 0)
        w.db.flush()

        # A single dated sheet row whose date matches NEITHER candidate: pass 2 must pick
        # whichever the ORDER BY hands it first.
        data = sheet([
            (order.so_number, w.product.product_code, 100, date(2026, 9, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_delivery_date_updated"] == 1, result
        w.db.refresh(inserted_first)
        w.db.refresh(inserted_second)
        assert inserted_second.delivery_date == date(2026, 9, 1), (
            "the row with the EARLIER created_at should be repaired first"
        )
        assert inserted_first.delivery_date == required, (
            "the row with the LATER created_at must stay untouched"
        )


def test_ac_18_a_text_date_cell_is_read_and_repaired():
    """AC-18 (round 4, 19 Sep 2026), end to end: `JAN - DEC 2026 ORDERabc.xlsx` stores some
    DELIVERY DATE cells as literal TEXT rather than an Excel date - SO314593's own JUNE
    rows say `1.6.2026` this way, which is why `row.delivery_date` was `None` at the reader
    layer regardless of anything this fix or its reversal did (round 4 root cause).

    Raised (AC-1 shape): a sheet whose cell reads the text `"1.6.2026"` raises a row dated
    2026-06-01. Re-uploaded with a corrected text date (AC-4 shape): the migrated row
    repairs to the new one."""
    text_date = date(2026, 6, 1)
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="50", required_date=text_date)
        migration_sheet = sheet([
            (order.so_number, w.product.product_code, 30, "1.6.2026",
             w.warehouse.warehouse_code, ""),
        ])

        raised = _apply(w, migration_sheet, file_name="2026-08 order inquiry.xlsx")

        assert raised["rows_raised"] == 1, raised
        migrated = w.one_row()
        assert migrated.delivery_date == text_date, "the text date cell was not parsed"

        corrected_sheet = sheet([
            (order.so_number, w.product.product_code, 30, "15.7.2026",
             w.warehouse.warehouse_code, ""),
        ])
        result = _apply(w, corrected_sheet, file_name="2026-09 corrected.xlsx")

        assert result["rows_delivery_date_updated"] == 1, result
        w.db.refresh(migrated)
        assert migrated.delivery_date == date(2026, 7, 15)


def test_ac_19_a_settled_rows_was_date_is_corrected_delivery_date_untouched():
    """AC-19 (Shape B, round 5, 19 Sep 2026 - the SO314593 SRTWCX8605-S-RL-PJ / CB2806A-DIY
    / SRTWB245 shape, found on prod after #1004 deployed). The MIGRATED row itself was
    restated IN PLACE by a planning change: qty 280, delivery_date 2027-03-01 (the book's
    Now, correct), previous_qty 182, previous_delivery_date 2027-03-01 (7.4's mistake, on
    the Was side). The sheet says 182 @ 1.6.2026 - describing the row's WAS state, not a
    fresh instruction. Only the Was date and its note fragment move.

    The note's "Linked to ...; expected ..." clause deliberately carries the SAME old date
    as the "Was ... on" fragment (S15, round 4 review): an unanchored bare-date replace
    would touch both, since the old date string then appears twice - the "expected" clause
    must survive verbatim, only the "Was ..." fragment moves.
    """
    required = date(2027, 3, 1)
    sheet_date = date(2026, 6, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        note = (
            "Migrated from order inquiry sheet JAN - DEC 2026 ORDERabc.xlsx; "
            "Linked to 202603-S0109 (SPO-2026/03-0109), expected 2027-03-01; "
            "auto: autocount linkage; Was 182 on 2027-03-01"
        )
        settled = _settled_row(
            w, mirror, qty="280", delivery_date=required,
            previous_qty="182", previous_delivery_date=required, note=note,
        )

        data = sheet([
            (order.so_number, w.product.product_code, 182, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        preview = importer.preview(w.db, data)
        assert preview["rows_delivery_date_updated"] == 1, preview

        outcome_recorder = ImportOutcome(None, persist=False)
        result = _apply(w, data, outcome=outcome_recorder)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 1, result
        w.db.refresh(settled)
        assert settled.previous_delivery_date == sheet_date, "the Was date did not move"
        assert settled.delivery_date == required, "the Now date must stay untouched"
        assert Decimal(str(settled.qty)) == Decimal("280"), "the Now quantity moved"
        assert Decimal(str(settled.previous_qty)) == Decimal("182"), "previous_qty moved"
        assert settled.note == (
            "Migrated from order inquiry sheet JAN - DEC 2026 ORDERabc.xlsx; "
            "Linked to 202603-S0109 (SPO-2026/03-0109), expected 2027-03-01; "
            "auto: autocount linkage; Was 182 on 2026-06-01"
        ), "only the Was fragment should move; the AutoCount/Linked prose must survive"
        seen_codes = {entry["code"] for entry in outcome_recorder.breakdown()["successful"]}
        assert seen_codes == {oc.DELIVERY_DATE_UPDATED}, seen_codes


def test_ac_20_a_settled_row_not_on_the_lines_date_is_never_repaired():
    """AC-20 (Shape B). A settled row whose `previous_delivery_date` already differs from
    the line's `required_date` does not carry 7.4's mistake any more - never touched,
    whatever the sheet says."""
    required = date(2027, 3, 1)
    already_fixed = date(2026, 1, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        settled = _settled_row(
            w, mirror, qty="280", delivery_date=required,
            previous_qty="182", previous_delivery_date=already_fixed,
            note=f"Migrated from order inquiry sheet x.xlsx; Was 182 on {already_fixed.isoformat()}",
        )

        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 0, result
        w.db.refresh(settled)
        assert settled.previous_delivery_date == already_fixed


def test_ac_21_a_settled_row_with_a_different_was_quantity_is_never_repaired():
    """AC-21 (Shape B). The sheet's quantity does not match the row's Was quantity - a
    different instruction, left alone."""
    required = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        settled = _settled_row(
            w, mirror, qty="280", delivery_date=required,
            previous_qty="182", previous_delivery_date=required,
            note=f"Migrated from order inquiry sheet x.xlsx; Was 182 on {required.isoformat()}",
        )

        data = sheet([
            (order.so_number, w.product.product_code, 100, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 0, result
        w.db.refresh(settled)
        assert settled.previous_delivery_date == required


def test_ac_22_shape_b_reupload_is_idempotent():
    """AC-22 (Shape B). Running AC-19's upload a second time changes nothing: once
    repaired, the settled row's Was date no longer matches the line's `required_date`, so
    the second run finds no candidate at all."""
    required = date(2027, 3, 1)
    sheet_date = date(2026, 6, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        settled = _settled_row(
            w, mirror, qty="280", delivery_date=required,
            previous_qty="182", previous_delivery_date=required,
            note=f"Migrated from order inquiry sheet x.xlsx; Was 182 on {required.isoformat()}",
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
        w.db.refresh(settled)
        assert settled.previous_delivery_date == sheet_date
        assert settled.delivery_date == required


def test_ac_23_shape_a_wins_over_shape_b_deterministically():
    """AC-23 (round 5). A line carrying BOTH an untouched migrated row (shape A) and a
    settled row (shape B) sharing the SAME quantity: with only one sheet row of that
    quantity, shape A is resolved first (exact match, then shape A, then shape B) - the
    untouched row is repaired, the settled row's Was date is left exactly as it was, and
    the one sheet row claims one row only."""
    required = date(2027, 3, 1)
    new_date = date(2026, 6, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)

        untouched = _migrated_row(w, mirror, qty="150", delivery_date=required)
        settled = _settled_row(
            w, mirror, qty="90", delivery_date=required,
            previous_qty="150", previous_delivery_date=required,
            note=f"Migrated from order inquiry sheet x.xlsx; Was 150 on {required.isoformat()}",
        )

        data = sheet([
            (order.so_number, w.product.product_code, 150, new_date,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        assert result["rows_delivery_date_updated"] == 1, result
        w.db.refresh(untouched)
        w.db.refresh(settled)
        assert untouched.delivery_date == new_date, "shape A should have been repaired"
        assert settled.previous_delivery_date == required, (
            "shape B must not also claim the same sheet row"
        )


def test_ac_24_a_settled_row_already_on_the_sheets_date_is_a_no_op_not_a_phantom_repair():
    """AC-24 (S14, round 4 review). A settled row whose `previous_delivery_date` already
    equals the SHEET's own date needs no repair - it must be claimed as a no-op (shape B's
    own pass 1, mirroring shape A's), not repaired and counted. Without this, a sheet row
    whose date equals the row's `previous_delivery_date` (which, by the fingerprint, IS the
    line's `required_date`) was counted and reported `DELIVERY_DATE_UPDATED` on every run
    while nothing ever changed - probe: first run 1, second run 1, preview-again 1."""
    required = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        settled = _settled_row(
            w, mirror, qty="280", delivery_date=required,
            previous_qty="182", previous_delivery_date=required,
            note=f"Migrated from order inquiry sheet x.xlsx; Was 182 on {required.isoformat()}",
        )

        data = sheet([
            (order.so_number, w.product.product_code, 182, required,
             w.warehouse.warehouse_code, ""),
        ])

        preview = importer.preview(w.db, data)
        assert preview["rows_delivery_date_updated"] == 0, preview

        first = _apply(w, data)
        assert first["rows_raised"] == 0, first
        assert first["rows_already_raised"] == 1, first
        assert first["rows_delivery_date_updated"] == 0, first
        w.db.refresh(settled)
        assert settled.previous_delivery_date == required

        second = _apply(w, data)
        assert second["rows_delivery_date_updated"] == 0, second
        w.db.refresh(settled)
        assert settled.previous_delivery_date == required

        preview_again = importer.preview(w.db, data)
        assert preview_again["rows_delivery_date_updated"] == 0, preview_again


def test_ac_25_a_live_row_adopts_the_sheets_was_through_its_cancelled_sibling():
    """AC-25 (Shape C, round 7, 19 Sep 2026 - the REAL SO314593 CB2806A-DIY / SRTWB245
    shape, confirmed by a prod `SELECT`). A reconfirm CANCELLED a migrated row that had
    been settled once before being superseded (qty 220, previous_qty 182,
    previous_delivery_date the line's required_date - its own Was, from that earlier
    settle) and RAISED A FRESH LIVE ROW in its place (qty 220, delivery_date the line's
    required_date, no Was at all, no migration stamp). The sheet says 182 @ 1.6.2026 -
    adopted as the LIVE row's Was through its cancelled sibling's own 182."""
    required = date(2027, 3, 1)
    sheet_date = date(2026, 6, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        cancelled = _cancelled_sibling(
            w, mirror, qty="220", previous_qty="182", previous_delivery_date=required,
        )
        live = _live_row(w, mirror, qty="220", delivery_date=required)

        data = sheet([
            (order.so_number, w.product.product_code, 182, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        preview = importer.preview(w.db, data)
        assert preview["rows_delivery_date_updated"] == 1, preview

        outcome_recorder = ImportOutcome(None, persist=False)
        result = _apply(w, data, outcome=outcome_recorder)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 1, result

        w.db.refresh(live)
        assert Decimal(str(live.previous_qty)) == Decimal("182")
        assert live.previous_delivery_date == sheet_date
        assert live.delivery_date == required, "the live row's Now date must stay untouched"
        assert Decimal(str(live.qty)) == Decimal("220"), "the live row's Now quantity moved"
        assert live.note == f"Was 182 on {sheet_date.isoformat()}"

        w.db.refresh(cancelled)
        assert cancelled.previous_qty == Decimal("182"), "the cancelled sibling was touched"
        assert cancelled.note == "Superseded by revision 2", "the cancelled sibling was touched"

        seen_codes = {entry["code"] for entry in outcome_recorder.breakdown()["successful"]}
        assert seen_codes == {oc.DELIVERY_DATE_UPDATED}, seen_codes


def test_ac_26_a_live_row_with_no_cancelled_sibling_is_left_alone():
    """AC-26 (Shape C), rewritten (S1, round 7 review round 2). A live row with the exact
    shape C shape (no Was, on the line's own date) paired with a cancelled row that LOOKS
    exactly like a migrated sibling - same quantity, same "Superseded by revision 2" note -
    but was never raised by an upload at all, so it carries no `import_job_rows` entry. Not
    a genuine sibling: the live row is left alone, whatever the sheet says."""
    required = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        # Carries the SHEET's own quantity (182), so a false-positive here can only come
        # from mistaking this row for a migrated sibling by quantity/note alone - never
        # from a quantity mismatch (AC-27's own case).
        _cancelled_board_row(w, mirror, qty="182")
        live = _live_row(w, mirror, qty="220", delivery_date=required)

        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 0, result
        w.db.refresh(live)
        assert live.previous_qty is None
        assert live.delivery_date == required


def test_shape_c_sibling_identity_requires_outcome_created():
    """S1 regression (round 7 review round 3). A cancelled row `import_job_rows` DOES
    carry an entry for - but with `outcome = "updated"`, never `"created"` - is not a
    migrated sibling. `apply()` writes an `"updated"` row against an EXISTING row's own id
    every time it repairs one (shape A/B/C's own `outcome.updated(...)` calls); if the
    identity check only tested "does `import_job_rows` carry ANY row for this id" rather
    than `outcome = "created"` specifically, a row a PRIOR repair touched would wrongly
    start qualifying as a migrated sibling too."""
    required = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        sibling = _cancelled_board_row(w, mirror, qty="182")
        _register_migrated(w, sibling, outcome="updated")
        live = _live_row(w, mirror, qty="220", delivery_date=required)

        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 0, result
        w.db.refresh(live)
        assert live.previous_qty is None
        assert live.delivery_date == required


def test_ac_27_a_cancelled_siblings_mismatched_quantity_leaves_the_live_row_alone():
    """AC-27 (Shape C). A cancelled migrated sibling whose OWN `qty` AND `previous_qty`
    both differ from the sheet's quantity carries no identity match - the live row is
    left alone."""
    required = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        _cancelled_sibling(
            w, mirror, qty="220", previous_qty="200", previous_delivery_date=required,
        )
        live = _live_row(w, mirror, qty="220", delivery_date=required)

        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, result
        assert result["rows_delivery_date_updated"] == 0, result
        w.db.refresh(live)
        assert live.previous_qty is None
        assert live.delivery_date == required


def test_ac_28_shape_c_reupload_is_idempotent():
    """AC-28 (Shape C). Running AC-25's upload a second time changes nothing - once
    adopted, the live row's `previous_qty` is no longer `NULL`, so the second run finds
    no candidate at all."""
    required = date(2027, 3, 1)
    sheet_date = date(2026, 6, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        _cancelled_sibling(
            w, mirror, qty="220", previous_qty="182", previous_delivery_date=required,
        )
        live = _live_row(w, mirror, qty="220", delivery_date=required)

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
        w.db.refresh(live)
        assert Decimal(str(live.previous_qty)) == Decimal("182")
        assert live.previous_delivery_date == sheet_date


def test_ac_29_all_three_shapes_on_one_mirror_are_each_claimed_once():
    """AC-29 (round 7). A mirror carrying a shape A row, a shape B row, AND a shape C pair
    (a live row + its cancelled sibling), with three sheet rows each matching exactly one -
    each is claimed once, deterministically, in priority order (exact match, shape A,
    shape B, shape C)."""
    required = date(2027, 3, 1)
    new_date_a = date(2026, 6, 1)
    new_date_b = date(2026, 7, 1)
    new_date_c = date(2026, 8, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="900", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)

        row_a = _migrated_row(w, mirror, qty="100", delivery_date=required)
        row_b = _settled_row(
            w, mirror, qty="90", delivery_date=required,
            previous_qty="150", previous_delivery_date=required,
            note=f"Migrated from order inquiry sheet x.xlsx; Was 150 on {required.isoformat()}",
        )
        _cancelled_sibling(w, mirror, qty="200")
        live_c = _live_row(w, mirror, qty="200", delivery_date=required)

        data = sheet([
            (order.so_number, w.product.product_code, 100, new_date_a,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 150, new_date_b,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 200, new_date_c,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        assert result["rows_delivery_date_updated"] == 3, result

        w.db.refresh(row_a)
        w.db.refresh(row_b)
        w.db.refresh(live_c)

        assert row_a.delivery_date == new_date_a, "shape A row was not repaired"
        assert Decimal(str(row_a.qty)) == Decimal("100")

        assert row_b.previous_delivery_date == new_date_b, "shape B row was not repaired"
        assert Decimal(str(row_b.previous_qty)) == Decimal("150")
        assert Decimal(str(row_b.qty)) == Decimal("90")

        assert Decimal(str(live_c.previous_qty)) == Decimal("200"), "shape C row was not adopted"
        assert live_c.previous_delivery_date == new_date_c
        assert Decimal(str(live_c.qty)) == Decimal("200")
        assert live_c.delivery_date == required


def test_shape_c_pairs_by_sibling_identity_not_file_position():
    """Round 7 review (item 2), tightened round 7 review round 2 (S2) and round 3: asserts
    WHICH live row gets WHICH Was, not merely that both resolve - a bare item-code match on
    `unclaimed_live` is a coin flip whenever more than one candidate shares the item, and a
    test only checking the total count cannot tell a correct pairing from a lucky one.

    Two live rows (own `qty` 220 and 100) and two cancelled siblings of the SAME item, one
    settled once before being superseded (`qty` 220, `previous_qty` 182 - its ORIGINAL
    quantity, created FIRST) and one never settled (`qty` 100, created SECOND). The sheet
    states 100 first, then 182 - the REVERSE of the siblings' own creation order. Pairing
    must follow the MATCHED sibling's own `qty` (prod's own shape: sibling `qty` 220, live
    `qty` 220), never file/creation position: the 100 sheet row is the never-settled
    sibling's own quantity, so it must land on the live row whose `qty` is 100; the 182
    sheet row is the settled sibling's ORIGINAL quantity, so it must land on the live row
    whose `qty` is 220.

    Round 3: `live_220` (the WRONG answer for the FIRST sheet row processed) is created
    SECOND, before `live_100` (the RIGHT one) - reversed - deliberately, with EXPLICIT,
    distinct `created_at` values, so the old item-only-first-match bug picks `live_220`
    every single run rather than winning the id tiebreak by chance: `created_at`'s own
    default is the transaction's `now()`, tied across every row one test writes, so leaving
    it to the default lets `order_by(created_at.asc(), id.asc())` fall back to comparing
    randomly-generated ids - a coin flip the mutant could still pass by luck."""
    required = date(2027, 3, 1)
    sheet_date_100 = date(2026, 6, 1)
    sheet_date_182 = date(2026, 7, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="900", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)

        # Created in THIS order: the 182-original sibling first, the 100 sibling second.
        _cancelled_sibling(
            w, mirror, qty="220", previous_qty="182", previous_delivery_date=required,
        )
        _cancelled_sibling(w, mirror, qty="100")
        # `live_220` is the WRONG target for the sheet's FIRST row (qty 100) - given an
        # EARLIER `created_at` than `live_100`, so an item-only-first-match mutant picks
        # it deterministically, every run, never by an id coin flip.
        live_220 = _live_row(
            w, mirror, qty="220", delivery_date=required,
            created_at=datetime(2026, 1, 1, 0, 0, 0),
        )
        live_100 = _live_row(
            w, mirror, qty="100", delivery_date=required,
            created_at=datetime(2026, 1, 1, 0, 0, 1),
        )

        # Sheet states 100 FIRST, then 182 - the reverse of the siblings' own creation
        # order.
        data = sheet([
            (order.so_number, w.product.product_code, 100, sheet_date_100,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 182, sheet_date_182,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_raised"] == 0, result
        # Both sheet rows have a genuine sibling match (100 and 182 both exist among the
        # siblings) and must both resolve, regardless of file/creation order.
        assert result["rows_delivery_date_updated"] == 2, result

        w.db.refresh(live_220)
        w.db.refresh(live_100)
        assert Decimal(str(live_220.previous_qty)) == Decimal("182"), (
            "the qty-220 live row must adopt the Was through the qty-220 sibling"
        )
        assert live_220.previous_delivery_date == sheet_date_182
        assert Decimal(str(live_100.previous_qty)) == Decimal("100"), (
            "the qty-100 live row must adopt the Was through the qty-100 sibling"
        )
        assert live_100.previous_delivery_date == sheet_date_100


def test_shape_c_note_edit_is_anchored_replacing_not_appending():
    """Round 7 review (item 3), tightened round 7 review round 2 (BLOCKER). If the live
    row's note already carries a "Was ... on ..." fragment (an unusual prior state), the
    shape C write REPLACES that fragment IN PLACE - never appending a second one, and
    never dropping prose that follows it. A `find("Was ")` + prefix-rebuild fix passes a
    naive version of this test but loses everything AFTER the old fragment (a probe's own
    "Linked to ..." / "auto: autocount linkage" tail) - pinned here by putting real prose
    on BOTH sides of the fragment."""
    required = date(2027, 3, 1)
    sheet_date = date(2026, 6, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        _cancelled_sibling(
            w, mirror, qty="220", previous_qty="182", previous_delivery_date=required,
        )
        live = _live_row(w, mirror, qty="220", delivery_date=required)
        live.note = (
            "A stray note; Was 999 on 2020-01-01; Linked to 202603-S0109 (auto); "
            "auto: autocount linkage"
        )
        w.db.flush()

        data = sheet([
            (order.so_number, w.product.product_code, 182, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data)

        w.db.refresh(live)
        assert live.note == (
            "A stray note; Was 182 on 2026-06-01; Linked to 202603-S0109 (auto); "
            "auto: autocount linkage"
        ), (
            "the existing Was fragment must be replaced IN PLACE, with the prose on "
            "both sides of it preserved byte for byte"
        )


def test_shape_c_adoption_at_the_required_date_is_still_idempotent():
    """Round 7 review (item 5). When the sheet's own date happens to equal the line's
    `required_date`, a second run must still be a no-op - the adopted live row is never a
    stamped (migrated) row, so it never re-enters shape A's or shape B's own pool either,
    on top of shape C's own precondition (`previous_qty IS NULL`) no longer holding."""
    required = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        _cancelled_sibling(
            w, mirror, qty="220", previous_qty="182", previous_delivery_date=required,
        )
        live = _live_row(w, mirror, qty="220", delivery_date=required)

        # The sheet's own date happens to equal the line's required_date.
        data = sheet([
            (order.so_number, w.product.product_code, 182, required,
             w.warehouse.warehouse_code, ""),
        ])

        first = _apply(w, data)
        assert first["rows_delivery_date_updated"] == 1, first
        w.db.refresh(live)
        assert live.previous_delivery_date == required

        second = _apply(w, data)

        assert second["rows_delivery_date_updated"] == 0, second
        w.db.refresh(live)
        assert live.previous_delivery_date == required
        assert Decimal(str(live.previous_qty)) == Decimal("182")


def test_shape_c_claims_each_pool_at_most_once():
    """S3 (round 7 review round 2, item a). Two sheet rows share the same item and
    quantity against ONE cancelled sibling and ONE live row: only the FIRST claims the
    adoption; the second stays `ALREADY_RAISED` with no repair - claim-once on both
    pools, not one adoption per matching sheet row."""
    required = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="900", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        _cancelled_sibling(
            w, mirror, qty="220", previous_qty="182", previous_delivery_date=required,
        )
        live = _live_row(w, mirror, qty="220", delivery_date=required)

        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 182, date(2026, 7, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_delivery_date_updated"] == 1, result
        w.db.refresh(live)
        assert Decimal(str(live.previous_qty)) == Decimal("182")
        assert live.previous_delivery_date == date(2026, 6, 1), (
            "the FIRST sheet row must win the only sibling/live pair"
        )


def test_shape_c_never_reclaims_a_row_shape_a_already_repaired():
    """S3 (round 7 review round 2, item b). A single sheet row that could match EITHER
    shape A's own migrated row OR shape C's sibling+live pair is resolved by shape A
    (priority order) and never also handed to shape C - regression guard for
    `_resolve_shape_c_repairs`'s own `if index in already_claimed: continue` skip."""
    required = date(2027, 3, 1)
    new_date = date(2026, 6, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="900", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        row_a = _migrated_row(w, mirror, qty="100", delivery_date=required)
        _cancelled_sibling(
            w, mirror, qty="100", previous_qty="100", previous_delivery_date=required,
        )
        live = _live_row(w, mirror, qty="100", delivery_date=required)

        data = sheet([
            (order.so_number, w.product.product_code, 100, new_date,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_delivery_date_updated"] == 1, result
        w.db.refresh(row_a)
        w.db.refresh(live)
        assert row_a.delivery_date == new_date, "shape A should have claimed this row"
        assert live.previous_qty is None, (
            "shape C must not also claim the same sheet row shape A already repaired"
        )


def test_shape_c_claims_the_live_pool_at_most_once():
    """S3 (round 7 review round 2, item c). Two cancelled siblings share the sheet's own
    quantity, but only ONE live row exists: after the first sheet row claims it, the
    second is left alone rather than reusing the same live row - regression guard for
    `_resolve_shape_c_repairs`'s own `unclaimed_live.remove(live)` call."""
    required = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="900", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        _cancelled_sibling(
            w, mirror, qty="220", previous_qty="182", previous_delivery_date=required,
        )
        _cancelled_sibling(
            w, mirror, qty="220", previous_qty="182", previous_delivery_date=required,
        )
        live = _live_row(w, mirror, qty="220", delivery_date=required)

        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 182, date(2026, 7, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_delivery_date_updated"] == 1, result
        w.db.refresh(live)
        assert Decimal(str(live.previous_qty)) == Decimal("182")
        assert live.previous_delivery_date == date(2026, 6, 1), (
            "the FIRST sheet row must win the only live row"
        )


def test_shape_c_claims_the_sibling_pool_at_most_once():
    """S3 (round 7 review round 2, item c). ONE cancelled sibling but TWO live rows of the
    same item: after the first sheet row claims the sibling, the second sheet row finds no
    sibling left, even though a live row remains unclaimed - regression guard for
    `_resolve_shape_c_repairs`'s own `unclaimed_siblings.remove(sibling)` call."""
    required = date(2027, 3, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="900", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        _cancelled_sibling(
            w, mirror, qty="220", previous_qty="182", previous_delivery_date=required,
        )
        live_1 = _live_row(w, mirror, qty="220", delivery_date=required)
        live_2 = _live_row(w, mirror, qty="220", delivery_date=required)

        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 182, date(2026, 7, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_delivery_date_updated"] == 1, result
        w.db.refresh(live_1)
        w.db.refresh(live_2)
        adopted = [r for r in (live_1, live_2) if r.previous_qty is not None]
        assert len(adopted) == 1, (
            "only ONE live row may adopt a Was through the single cancelled sibling"
        )


def test_shape_c_adopts_even_when_the_lives_own_qty_equals_the_sheet_qty():
    """NIT (round 7 review round 2). A live row whose OWN `qty` happens to equal the
    sheet's own quantity still adopts the Was when the date differs - the equal-quantity
    coincidence is never a reason to skip the adoption."""
    required = date(2027, 3, 1)
    sheet_date = date(2026, 6, 1)
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="400", required_date=required)
        from app.services.project_so_adoption_service import ProjectSOAdoptionService

        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        _cancelled_sibling(
            w, mirror, qty="182", previous_qty="182", previous_delivery_date=required,
        )
        live = _live_row(w, mirror, qty="182", delivery_date=required)

        data = sheet([
            (order.so_number, w.product.product_code, 182, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data)

        assert result["rows_delivery_date_updated"] == 1, result
        w.db.refresh(live)
        assert Decimal(str(live.previous_qty)) == Decimal("182")
        assert live.previous_delivery_date == sheet_date
        assert Decimal(str(live.qty)) == Decimal("182"), (
            "the live row's Now quantity stays untouched, even though it equals the "
            "adopted Was"
        )
