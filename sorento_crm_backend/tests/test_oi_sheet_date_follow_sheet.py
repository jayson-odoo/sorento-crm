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
