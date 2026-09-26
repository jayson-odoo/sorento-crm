"""S4, importer pairing by date order, never drop (D3, R4).

`documentation/plans/scm/PLAN-board-received-stock-own-arrival.md` S4, UAC
`board-received-stock-own-arrival-acceptance-criteria.md` AC-S4-1 to AC-S4-4 (AC-S4-5 is the
manual SO372176 replay, skipped here). RED before the coder's slice lands - written from the
CONTRACT (the plan's R4 ruling + the S0 measurement's conclusion), with no implementation to
look at.

**The contract pinned here** (R4 + S0's conclusion that S4 needs BOTH halves - a ranking
change AND a skip-rule change):

* Candidate lines for one sales order are its OPEN lines only (not `closed`, not
  `cancelled` - AC-S4-3 reverses the "closed lines migrate too" reading D8 gave the OLDER
  five-pass pick, which the plan's R4 explicitly narrows for this new algorithm), sorted by
  `required_date`.
* Sheet rows of one import call, sorted by `delivery_date`, are paired to those candidate
  lines ONE TO ONE IN DATE ORDER: the earliest row to the earliest-dated line still without
  a row of its own, and so on.
* A row beyond the last such line lands on the LAST candidate line as a SECOND row
  (AC-S4-2) - never dropped, never reported as `already_raised` for landing on a line that
  already carries one.
* Across separate imports (a 2026 book, then a 2027 book, the SO372176 shape) the same rule
  holds: a book's own rows still land on whichever open lines do not yet carry a row, in
  date order, and a re-upload of an unchanged book restates its own existing rows in place
  rather than creating a duplicate or being silently dropped (AC-S4-4).

Today's importer (`app/services/project_order_inquiry_import_service.py`) does neither: its
five-pass line pick (`_match_in_passes` :946-1019, `_run_pass` :836-931) ranks a fallback
match by "the line's own EARLIEST required date, whatever the row's own date" (`_rank_for`
:510-580) rather than by closeness to the row's own date, so two sheet rows aimed at two
different lines both collapse onto whichever line is earliest overall; and once a line's
mirror carries ANY row, `_already_raised` (:1021-1078) marks EVERY later match against that
line as already-raised rather than letting date order route a genuinely later delivery onto
the next open line - which is exactly the drop the plan's S0 measurement found on SO372176
(nine sheet rows lost to `already_raised` / `top_up_sum_mismatch` blocks laid down by an
earlier, mis-ranked row of the SAME 20 Sep import session). So every test below is expected
to fail on an assertion about WHICH line a row landed on, or about the row COUNT staying
equal to the sheet's own row count - never on an import error or fixture bug.

**Contract choices this file had to make, where the plan/UAC leave the shape open** (see the
handback report for the full list):

* AC-S4-1's "where the line's date or qty differs from the sheet, `Was {qty} on {date}`"
  clause describes a RESTATEMENT (a re-upload correcting an existing row, the same note
  fragment `_resolve_delivery_date_repairs` / `_settle_row_in_place` already write
  elsewhere in this file's sibling tests). This AC's own fixture is a FIRST-time raise for
  every row (no prior row exists on any of the four lines before either book runs), so the
  clause never triggers here - both rows on both books get the sheet's own date with no
  Was/Now pair, and this test asserts exactly that (a bare migration-stamp note), rather
  than inventing a Was/Now case the AC's own fixture shape does not produce.
* "Raisable" (AC-S4-2's "the import preview counts 5 raisable") is read straight off
  `preview()`'s own `rows_raised` key - `_result` already defines it as
  `sum(1 for match in plan.matches if match.raisable)`, so no new field is needed.
* AC-S4-3's expected `line_not_found` reason is `no_line_for_item`
  (`app/services/import_outcome_codes.py::NO_LINE_FOR_ITEM`): once the closed/cancelled
  line is excluded from the candidate pool before the item filter ever runs, `same_item`
  in `_match_row` is empty and that is the FIRST filter that refuses the row, exactly the
  reason the function already reports for "no line of this order holds this item" today.

Postgres only (`tests/_pg_fixture.py`, via `world()`). Every FK is seeded here through
`World`; nothing is read off an existing row - CI's database is empty.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services import project_order_inquiry_import_service as importer
from app.services.project_so_adoption_service import ProjectSOAdoptionService
from tests.test_oi_sheet_pairing_repair import _apply
from tests.test_oi_sheet_rebuild_from_planning import _decision
from tests.test_project_order_inquiry_import_migration import sheet, world

from ._oi_book_fixture import book_of, open_lines


def test_ac_s4_1_two_books_pair_onto_open_lines_by_date_order():
    """AC-S4-1. Four open lines dated d1 < d2 < d3 < d4; a 2026 book with two rows dated
    between d1 and d2, then a 2027 book with two rows dated near d3 and d4. After BOTH
    imports there are exactly 4 OI rows, on lines 1, 2, 3, 4 IN THAT ORDER (earliest sheet
    row to the earliest line), each carrying the migration stamp naming its own book.
    """
    d1, d2, d3, d4 = date(2026, 1, 1), date(2026, 6, 1), date(2027, 1, 1), date(2027, 6, 1)
    with world() as w:
        order = w.order()
        line1, line2, line3, line4 = open_lines(w, order, [d1, d2, d3, d4])

        book_2026 = book_of(w, order, [(10, date(2026, 2, 1)), (12, date(2026, 4, 1))])
        book_2027 = book_of(w, order, [(14, date(2027, 2, 1)), (16, date(2027, 7, 1))])

        first = _apply(w, book_2026, file_name="2026 order inquiry.xlsx")
        assert first["rows_raised"] == 2, first
        second = _apply(w, book_2027, file_name="2027 order inquiry.xlsx")
        assert second["rows_raised"] == 2, second

        rows = w.rows()
        assert len(rows) == 4, [
            (str(r.so_line_id), r.delivery_date, str(r.qty)) for r in rows
        ]

        expected_mirror_ids = {str(w.mirror_of(line).id) for line in (line1, line2, line3, line4)}
        actual_mirror_ids = {str(r.so_line_id) for r in rows}
        assert actual_mirror_ids == expected_mirror_ids, (
            "every one of the four lines should carry exactly one row",
            expected_mirror_ids, actual_mirror_ids,
        )

        sorted_rows = sorted(rows, key=lambda r: r.delivery_date)
        for row, line in zip(sorted_rows, (line1, line2, line3, line4)):
            assert str(row.so_line_id) == str(w.mirror_of(line).id), (
                "sheet rows must pair onto open lines in DATE ORDER",
                row.delivery_date, line.required_date,
            )
            assert row.note.startswith(importer._MIGRATION_STAMP), row.note


def test_ac_s4_2_fifth_row_beyond_last_line_lands_as_second_row_on_it():
    """AC-S4-2. Five sheet rows, four open lines: the fifth (latest-dated) row lands on
    line 4 - the LAST open line by required date - as a SECOND row; nothing is dropped; the
    import preview counts 5 raisable.
    """
    dates = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)]
    with world() as w:
        order = w.order()
        lines = open_lines(w, order, dates)

        row_dates = [
            date(2026, 1, 10), date(2026, 2, 10), date(2026, 3, 10),
            date(2026, 4, 10), date(2026, 5, 10),
        ]
        data = book_of(w, order, [(10 + i, row_dates[i]) for i in range(5)])

        preview = importer.preview(w.db, data)
        assert preview["rows_raised"] == 5, preview

        result = _apply(w, data, file_name="2026 order inquiry.xlsx")
        assert result["rows_raised"] == 5, result

        rows = w.rows()
        assert len(rows) == 5, [
            (str(r.so_line_id), r.delivery_date, str(r.qty)) for r in rows
        ]

        last_mirror_id = str(w.mirror_of(lines[3]).id)
        on_last_line = [r for r in rows if str(r.so_line_id) == last_mirror_id]
        assert len(on_last_line) == 2, (
            "the fifth (latest) sheet row should land as a SECOND row on the last line",
            [(str(r.so_line_id), r.delivery_date) for r in rows],
        )
        for line in lines[:3]:
            mirror_id = str(w.mirror_of(line).id)
            on_line = [r for r in rows if str(r.so_line_id) == mirror_id]
            assert len(on_line) == 1, (line.required_date, on_line)


@pytest.mark.parametrize("status", ["closed", "cancelled"])
def test_ac_s4_3_closed_or_cancelled_line_never_paired(status: str):
    """AC-S4-3. A closed or cancelled core line is never paired, even when it is the only
    qty fit - R4's explicit narrowing of the older "closed lines migrate too" (D8) reading,
    for this date-order pick alone.

    Reason updated under R9 (21 Sep 2026, PLAN-board-received-stock-own-arrival,
    AC-S4-6): this order has no open line at all, so the row is now refused with its own
    reason `order_fully_delivered`, never the genuine-item-mismatch `no_line_for_item` -
    this test still pins "never paired"; AC-S4-6 (below) pins the reason itself.
    """
    with world() as w:
        order = w.order()
        w.line(
            order,
            qty_ordered="30",
            qty_delivered="30" if status == "closed" else "0",
            required_date=date(2026, 6, 1),
            line_status=status,
        )
        data = book_of(w, order, [(30, date(2026, 6, 1))])

        result = w.apply(data)

        assert result["rows_raised"] == 0, result
        assert w.rows() == [], "a row was raised against a closed/cancelled line"
        assert result["rows_line_not_found"] == 1, result
        assert result["line_not_found"][0]["reason"] == "order_fully_delivered", result


def test_ac_s4_4_reupload_of_both_books_restates_in_place_never_drops():
    """AC-S4-4. Re-uploading the SAME books restates their existing rows in place - no
    duplicate, no skip that loses a row - so the row count for the order stays equal to the
    total sheet row count (4) across every one of the four uploads: book 2026, book 2027,
    then each again.
    """
    d1, d2, d3, d4 = date(2026, 1, 1), date(2026, 6, 1), date(2027, 1, 1), date(2027, 6, 1)
    with world() as w:
        order = w.order()
        open_lines(w, order, [d1, d2, d3, d4])

        book_2026 = book_of(w, order, [(10, date(2026, 2, 1)), (12, date(2026, 4, 1))])
        book_2027 = book_of(w, order, [(14, date(2027, 2, 1)), (16, date(2027, 7, 1))])

        _apply(w, book_2026, file_name="2026 order inquiry.xlsx")
        assert len(w.rows()) == 2, "book 2026 alone should raise its own 2 rows"

        _apply(w, book_2027, file_name="2027 order inquiry.xlsx")
        assert len(w.rows()) == 4, (
            "book 2027's rows must land on the STILL-OPEN lines book 2026 left, "
            "never be dropped as already_raised against a line book 2026 already claimed",
            [(str(r.so_line_id), r.delivery_date) for r in w.rows()],
        )

        again_2026 = _apply(w, book_2026, file_name="2026 order inquiry.xlsx")
        assert again_2026["rows_raised"] == 0, again_2026
        assert len(w.rows()) == 4, "re-uploading book 2026 must not create or drop a row"

        again_2027 = _apply(w, book_2027, file_name="2027 order inquiry.xlsx")
        assert again_2027["rows_raised"] == 0, again_2027
        assert len(w.rows()) == 4, "re-uploading book 2027 must not create or drop a row"


# --------------------------------------------------------------------------- #
# AC-S4-6 (R9, added 21 Sep evening) - a sheet row for a sales order with no  #
# open line at all gets its OWN reason, `order_fully_delivered`, never the    #
# genuine-item-mismatch `no_line_for_item`                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("status", ["closed", "cancelled"])
def test_ac_s4_6_fully_delivered_order_row_is_refused_with_its_own_reason(status: str):
    """AC-S4-6 (R9). A sheet row for a sales order whose only line is closed or
    cancelled - no open line survives at all - is refused with its OWN reason
    `order_fully_delivered`, never `no_line_for_item`: the order is not adopted, no OI row
    is written, and the old D8 history row on the closed line is not written either
    (`w.rows() == []` covers that - nothing at all lands for this sales order).

    RED today: `_pick_lines_by_date_order` filters an order down to its OPEN lines, finds
    none, and calls `_match_row(row, [], ...)` - whose FIRST filter (`same_item`) is empty
    regardless of WHY the candidate list is empty, so it reports `no_line_for_item`
    (`app/services/import_outcome_codes.py::NO_LINE_FOR_ITEM`) today. The literal string
    `"order_fully_delivered"` is asserted directly rather than importing a constant, so this
    test stays red on the STRING even once the coder adds
    `import_outcome_codes.ORDER_FULLY_DELIVERED` to that module.
    """
    with world() as w:
        order = w.order()
        w.line(
            order,
            qty_ordered="30",
            qty_delivered="30" if status == "closed" else "0",
            required_date=date(2026, 6, 1),
            line_status=status,
        )
        data = book_of(w, order, [(30, date(2026, 6, 1))])

        preview = w.preview(data)
        assert preview["rows_raised"] == 0, preview
        assert preview["orders_adopted"] == 0, preview
        assert preview["rows_line_not_found"] == 1, preview
        assert preview["line_not_found"][0]["reason"] == "order_fully_delivered", preview

        result = w.apply(data)
        assert result["rows_raised"] == 0, result
        assert result["orders_adopted"] == 0, result
        assert result["rows_line_not_found"] == 1, result
        assert result["line_not_found"][0]["reason"] == "order_fully_delivered", result
        assert w.rows() == [], "a row was written for an order with no open line at all"


def test_ac_s4_6_mixed_closed_and_cancelled_lines_report_order_fully_delivered():
    """AC-S4-6 (R9). "All closed or cancelled" covers a MIX of the two statuses across an
    order's lines, not only a single-line order of one status - the parametrized test above
    proves each status alone; this proves the order-wide check is "no OPEN line survives",
    not "every line shares one status"."""
    with world() as w:
        order = w.order()
        w.line(
            order, qty_ordered="10", qty_delivered="10",
            required_date=date(2026, 5, 1), line_status="closed",
        )
        w.line(
            order, qty_ordered="20", qty_delivered="0",
            required_date=date(2026, 6, 1), line_status="cancelled",
        )
        data = book_of(w, order, [(15, date(2026, 6, 1))])

        result = w.apply(data)

        assert result["rows_raised"] == 0, result
        assert result["orders_adopted"] == 0, result
        assert result["line_not_found"][0]["reason"] == "order_fully_delivered", result
        assert w.rows() == [], "a row was written for an order with no open line at all"


# --------------------------------------------------------------------------- #
# AC-S4-7 (R10, added 21 Sep) - a sheet row larger than the open line it       #
# pairs to by date order still lands there, capped only by the ORDER's own    #
# total open capacity, never the one line's                                   #
# --------------------------------------------------------------------------- #


def test_ac_s4_7_row_larger_than_its_line_still_pairs_by_date():
    """AC-S4-7 (R10). Open lines d1 (qty 20) < d2 (qty 60), order total 80; sheet rows 70 @
    d1 and 40 @ d2. The 70-row still lands on line 1 - the line the date-order pick would
    otherwise give it - even though 70 exceeds line 1's OWN qty_ordered of 20 (it does not
    exceed the ORDER's total open qty of 80, R10's actual ceiling); the 40-row lands on
    line 2. Nothing is refused as `qty_exceeds_ordered`.

    Note wording pinned: `f"Was 20 on {d1.isoformat()}"` - the UAC's own literal example
    ('note "Was 20 on d1" style qty difference'), reusing the SAME `f"Was {qty} on {date}"`
    fragment this file already writes elsewhere (`_resolve_delivery_date_repairs`,
    `_settle_row_in_place`, grep `"Was "` across this module) rather than inventing a new
    note shape. Here 20 is line 1's own `qty_ordered` and d1 its `required_date` - the
    fragment records the mismatch between what the LINE was booked for and what this row
    actually states (70), not a prior LIVE row's previous state (this is a first-time raise,
    there is no earlier row to restate). The note fires because the row EXCEEDS the line's
    own ordered qty (R10 wording), not merely because it differs from it - a row landing
    short of or equal to the line's own qty carries no such note.

    RED before the fix: `_match_row`'s `fits` filter
    (`app/services/project_order_inquiry_import_service.py:638-643`) required
    `qty_ordered - taken >= qty` PER CANDIDATE LINE. A row of 70 never fit a line of 20, so
    line 1 was filtered out of `same_place` before rank/date order ever got a say; only
    line 2 (capacity 60) remained as a candidate for the 70-row, which also did not fit, so
    `_match_row` reported `qty_exceeds_ordered` for the 70-row and it was dropped - never the
    two-rows-on-two-lines outcome AC-S4-7 pins. `rows_raised == 1` (only the 40-row) and a
    `qty_exceeds_ordered` entry in `line_not_found` was the pre-fix outcome; R10 replaced the
    per-line ceiling with the order-wide one for the line the date pick lands a row on.
    """
    d1, d2 = date(2026, 1, 1), date(2026, 6, 1)
    with world() as w:
        order = w.order()
        line1 = w.line(order, qty_ordered="20", required_date=d1)
        line2 = w.line(order, qty_ordered="60", required_date=d2)

        data = book_of(w, order, [(70, d1), (40, d2)])

        preview = w.preview(data)
        assert preview["rows_raised"] == 2, preview
        assert preview["rows_line_not_found"] == 0, preview
        reasons = [entry.get("reason") for entry in preview["line_not_found"]]
        assert "qty_exceeds_ordered" not in reasons, preview

        result = w.apply(data)
        assert result["rows_raised"] == 2, result
        assert result["rows_line_not_found"] == 0, result

        rows = w.rows()
        assert len(rows) == 2, [
            (str(r.so_line_id), str(r.qty), r.delivery_date) for r in rows
        ]

        mirror1_id = str(w.mirror_of(line1).id)
        mirror2_id = str(w.mirror_of(line2).id)
        row_on_line1 = next((r for r in rows if str(r.so_line_id) == mirror1_id), None)
        row_on_line2 = next((r for r in rows if str(r.so_line_id) == mirror2_id), None)
        assert row_on_line1 is not None, (
            "the 70-row must land on line 1 (date order), even though it exceeds line 1's "
            "own qty_ordered",
            [(str(r.so_line_id), str(r.qty)) for r in rows],
        )
        assert row_on_line2 is not None, (
            "the 40-row must land on line 2",
            [(str(r.so_line_id), str(r.qty)) for r in rows],
        )
        assert row_on_line1.qty == Decimal("70"), row_on_line1.qty
        assert row_on_line2.qty == Decimal("40"), row_on_line2.qty

        expected_fragment = f"Was 20 on {d1.isoformat()}"
        assert expected_fragment in (row_on_line1.note or ""), row_on_line1.note


def test_ac_s4_7_row_larger_than_the_order_total_is_still_refused():
    """AC-S4-7 (R10) boundary guard. A single open line (qty 20) and a single sheet row of
    500 - far larger than the ORDER's own total open capacity, not merely this one line's -
    is still refused `qty_exceeds_ordered`. R10 lets a row exceed the ONE line the date pick
    lands it on (test above); it does not remove the order-wide ceiling.

    Expected GREEN already: today's per-line `fits` gate already refuses this row (the only
    open line cannot hold 500), the same outcome R10's change must preserve at this
    boundary - kept here as the guard the coder's R10 change must not break, not as a red
    pin.
    """
    with world() as w:
        order = w.order()
        w.line(order, qty_ordered="20", required_date=date(2026, 1, 1))

        data = book_of(w, order, [(500, date(2026, 1, 1))])

        preview = w.preview(data)
        assert preview["rows_raised"] == 0, preview
        assert preview["rows_line_not_found"] == 1, preview
        assert preview["line_not_found"][0]["reason"] == "qty_exceeds_ordered", preview

        result = w.apply(data)
        assert result["rows_raised"] == 0, result
        assert result["rows_line_not_found"] == 1, result
        assert result["line_not_found"][0]["reason"] == "qty_exceeds_ordered", result
        assert w.rows() == [], "a row was written despite exceeding the order's own capacity"


# --------------------------------------------------------------------------- #
# Phase 3 fix-round reds (SF6, SF7) - landing-map guards on top of the count-  #
# only assertions above                                                        #
# --------------------------------------------------------------------------- #


def test_ac_s4_4_reupload_keeps_every_row_on_the_same_line():
    """AC-S4-4, landing-map guard (SF6). Re-uploading the SAME books must not only keep the
    row COUNT stable (`test_ac_s4_4_reupload_of_both_books_restates_in_place_never_drops`
    above) - it must land every sheet row on the EXACT SAME line as the first import, never
    silently move one to a different line, and never create a duplicate. Captures
    `{sheet row identity (delivery_date, qty) -> landing so_line_id}` after the first pass of
    both books, re-uploads the identical books, and asserts the map is byte-identical.

    May be GREEN already - today's importer already restates a re-upload's rows in place by
    (so, item, date, qty) key rather than re-picking a line for an unchanged book, so nothing
    here forces a re-pick. Kept as the guard this slice's own contract needs: the coder's R10
    change (qty no longer gates the date-order pick) must not, as a side effect, let a
    re-upload's line pick land an existing row on a DIFFERENT line than before.
    """
    d1, d2, d3, d4 = date(2026, 1, 1), date(2026, 6, 1), date(2027, 1, 1), date(2027, 6, 1)
    with world() as w:
        order = w.order()
        open_lines(w, order, [d1, d2, d3, d4])

        book_2026 = book_of(w, order, [(10, date(2026, 2, 1)), (12, date(2026, 4, 1))])
        book_2027 = book_of(w, order, [(14, date(2027, 2, 1)), (16, date(2027, 7, 1))])

        _apply(w, book_2026, file_name="2026 order inquiry.xlsx")
        _apply(w, book_2027, file_name="2027 order inquiry.xlsx")

        def landing_map():
            return {
                (r.delivery_date, str(r.qty)): str(r.so_line_id)
                for r in w.rows()
            }

        before = landing_map()
        assert len(before) == 4, before

        _apply(w, book_2026, file_name="2026 order inquiry.xlsx")
        _apply(w, book_2027, file_name="2027 order inquiry.xlsx")

        after = landing_map()
        assert after == before, (
            "re-uploading the same books must not move any row to a different line",
            before, after,
        )
        assert len(w.rows()) == 4, "re-upload must not create a duplicate row"


def test_ac_s4_2_preview_and_apply_land_every_row_on_the_same_line():
    """AC-S4-2, preview/apply parity guard (SF7). For the five-rows/four-lines fixture,
    `preview()` and `apply()` must not only AGREE ON COUNTS
    (`test_ac_s4_2_fifth_row_beyond_last_line_lands_as_second_row_on_it` above pins
    `rows_raised == 5` for both) - each individual sheet row's LANDING LINE must be the same
    line in both. Reads `match.core_line` off the internal plan `preview()` itself computes
    (`importer._preview_plan`, the only place a match's landing line is exposed before
    Confirm - `preview()`'s own dict carries no per-row line detail) and compares each
    raisable match's core line against the line the actual applied `OrderInquiryRow` with the
    same (delivery_date, qty) sheet-row identity lands on (via `World.mirror_of`, the only
    way to go from a core line to the mirror id `OrderInquiryRow.so_line_id` addresses).

    May be GREEN already - nothing pins preview and apply computing the plan differently
    today (`_plan` is called once per call, and `apply` calls it the same way `preview` does).
    Kept as the guard against a coder's R10 change accidentally reading the plan twice (once
    for preview, once inside apply) and letting the two diverge, which this module's own
    `_Plan` docstring already promises against ("the counts on the screen before Confirm are
    the counts Confirm produces") - this test extends that promise from counts to WHICH line.
    """
    dates = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)]
    with world() as w:
        order = w.order()
        lines = open_lines(w, order, dates)

        row_dates = [
            date(2026, 1, 10), date(2026, 2, 10), date(2026, 3, 10),
            date(2026, 4, 10), date(2026, 5, 10),
        ]
        data = book_of(w, order, [(10 + i, row_dates[i]) for i in range(5)])

        plan, preview_result = importer._preview_plan(w.db, data)
        assert plan is not None, preview_result
        assert preview_result["rows_raised"] == 5, preview_result

        # Qty is compared as an int (every fixture qty here is a whole number): the sheet
        # row's own Decimal and the DB column's `NUMERIC(*, 4)` scale would otherwise print
        # "10" vs "10.0000" and fail this assertion for a formatting reason that has nothing
        # to do with WHICH line the row landed on.
        preview_landing = {
            (match.row.delivery_date, int(importer._dec(match.row.qty))): str(match.core_line.id)
            for match in plan.matches
            if match.raisable
        }
        assert len(preview_landing) == 5, preview_landing

        result = _apply(w, data, file_name="2026 order inquiry.xlsx")
        assert result["rows_raised"] == 5, result

        actual_landing: dict[tuple, str] = {}
        for line in lines:
            mirror = w.mirror_of(line)
            if mirror is None:
                continue
            for r in w.rows():
                if str(r.so_line_id) == str(mirror.id):
                    actual_landing[(r.delivery_date, int(r.qty))] = str(line.id)

        assert actual_landing == preview_landing, (
            "preview()'s own plan and apply()'s written rows must land every sheet row on "
            "the SAME line",
            preview_landing, actual_landing,
        )


def test_ac_s4_6_open_line_of_another_item_still_reports_no_line_for_item():
    """AC-S4-6 contrast case (R9). An order that DOES have an open line - just not for
    this row's item - is a genuine item mismatch, not `order_fully_delivered`: R9 only
    recarves the "no open line survives AT ALL" case, and this one must keep reading
    `no_line_for_item` after the coder's fix lands. Today's importer already agrees (its
    open-line filter still leaves a non-empty candidate list here, so `_match_row`'s
    `same_item` filter is the one that actually refuses the row), so this assertion is a
    regression guard against the R9 fix over-reaching, not the red half of AC-S4-6.
    """
    with world() as w:
        order = w.order()
        other_product = w.product_row(code=f"{w.product.product_code}-OTHER")
        w.line(
            order, product=other_product, qty_ordered="30",
            required_date=date(2026, 6, 1), line_status="open",
        )
        data = sheet([
            (order.so_number, w.product.product_code, 10, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 0, result
        assert result["rows_line_not_found"] == 1, result
        assert result["line_not_found"][0]["reason"] == "no_line_for_item", result
        assert w.rows() == [], "a row was written despite no line holding this item"


# --------------------------------------------------------------------------- #
# AC-S4-8 (Phase 3 follow-up, 21 Sep) - a re-upload must restate a row the    #
# line's own ACTIVE supply decision settled, not raise a fresh instruction    #
# for it                                                                      #
# --------------------------------------------------------------------------- #


def test_ac_s4_8_reupload_restates_a_row_the_line_decision_settled():
    """AC-S4-8. Plan section "AFTER (fix round, HEAD c6e3c77c1, AC-S4-5)", PASS 2 finding:
    `_apply_settle_recovery` (AC-RB-11, `project_order_inquiry_import_service.py:2807-2833`)
    settles a freshly-raised row's own live qty/date to the mirror's ACTIVE
    `so_supply_decisions` `buy_qty`/`required_date` - the sheet's own literal figures survive
    only in the row's `previous_qty`/`previous_delivery_date` columns and the "Was {qty} on
    {date}" note. `_restated_existing` (`project_order_inquiry_import_service.py:602-633`)
    matches a re-uploaded sheet row against a live row's item + its CURRENT qty + CURRENT
    delivery_date, so a settled row no longer answers to the sheet's own figures on a
    re-upload: R4's "a re-upload restates existing rows in place; row count stays equal to
    the sheet row count" breaks, exactly the PASS 2 measurement on SO372176 (8 rows -> 11
    after a re-upload, three new rows landing on lines the first upload never touched).

    Three open lines, L1 (d1), L2 (d2), L3 (d3) - L3 is never named by the book, kept open
    and untouched, the same shape SO372176's own L10/L11 held (open lines the FIRST upload
    never reached). L1 carries an ACTIVE decision settling it to 30 @ d1+7; L2 and L3 carry
    none. A book with rows 40 @ d1 and 40 @ d2 is imported once: 2 rows, L1's own settled to
    30 @ d1+7 with a "Was 40 on d1" note, L2's raised plain at 40 @ d2; L3 stays empty. The
    SAME book is re-uploaded: the row count must STAY at 2 (no third row on L3 or anywhere
    else), `rows_raised == 0` on the second apply, and L1's row must still be the SAME
    settled row (30 @ d1+7, id unchanged) rather than replaced or duplicated.

    RED today: L1's live row no longer states 40 @ d1 (the sheet's own figures for that row)
    once settle has moved it to 30 @ d1+7, so `_restated_existing` cannot recognise the
    re-uploaded 40 @ d1 row as the same instruction. It falls through into the date-order
    pick (`_pick_lines_by_date_order`) as if it were a brand-new row; L3 is a genuinely FREE
    candidate for this row's own item (`row_has_free` is true, the AC-LP-12 "bumped" branch),
    so the row is raised as a FRESH second instruction rather than silently skipped as
    already-raised, landing 40 @ d1 on L3 - a line the first upload never touched at all,
    taking the total from 2 to 3. Expected to fail on the row count after the second apply
    (3 != 2), not on a fixture or import error.
    """
    d1, d2, d3 = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)
    settled_date = d1 + timedelta(days=7)
    with world() as w:
        order = w.order()
        line1 = w.line(order, qty_ordered="100", required_date=d1)
        line2 = w.line(order, qty_ordered="100", required_date=d2)
        line3 = w.line(order, qty_ordered="100", required_date=d3)

        # The mirror line has to exist before a decision can be seeded against it - adopted
        # directly here (no upload has happened yet), matching how every sibling AC-RB-11
        # fixture in `test_oi_sheet_rebuild_from_planning.py` seeds an active decision.
        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror1 = w.mirror_of(line1)
        _decision(w, mirror1, line1, buy_qty="30", required_date=settled_date)

        data = book_of(w, order, [(40, d1), (40, d2)])

        first = w.apply(data)
        assert first["rows_raised"] == 2, first

        rows = w.rows()
        assert len(rows) == 2, [
            (str(r.so_line_id), str(r.qty), r.delivery_date) for r in rows
        ]

        mirror1_id = str(mirror1.id)
        mirror2_id = str(w.mirror_of(line2).id)
        mirror3_id = str(w.mirror_of(line3).id)
        row_on_line1 = next((r for r in rows if str(r.so_line_id) == mirror1_id), None)
        row_on_line2 = next((r for r in rows if str(r.so_line_id) == mirror2_id), None)
        assert row_on_line1 is not None, (
            "line 1 must carry a row after the first import",
            [(str(r.so_line_id), str(r.qty)) for r in rows],
        )
        assert row_on_line2 is not None, (
            "line 2 must carry a row after the first import",
            [(str(r.so_line_id), str(r.qty)) for r in rows],
        )
        assert not any(str(r.so_line_id) == mirror3_id for r in rows), (
            "line 3 must stay untouched by the first import - the book never names it",
            [(str(r.so_line_id), str(r.qty)) for r in rows],
        )

        # L1's row is SETTLED to the decision's own figures, not the sheet's literal 40 @ d1.
        assert row_on_line1.qty == Decimal("30"), row_on_line1.qty
        assert row_on_line1.delivery_date == settled_date, row_on_line1.delivery_date
        assert row_on_line1.previous_qty == Decimal("40"), row_on_line1.previous_qty
        assert row_on_line1.previous_delivery_date == d1, row_on_line1.previous_delivery_date
        assert f"Was 40 on {d1.isoformat()}" in (row_on_line1.note or ""), row_on_line1.note

        # L2 carries no decision, so its row is raised plain at the sheet's own figures.
        assert row_on_line2.qty == Decimal("40"), row_on_line2.qty
        assert row_on_line2.delivery_date == d2, row_on_line2.delivery_date
        assert row_on_line2.previous_qty is None, row_on_line2.previous_qty

        row_on_line1_id = row_on_line1.id

        second = w.apply(data)
        assert second["rows_raised"] == 0, (
            "a re-upload of the same book must restate the line-1 row IN PLACE, not raise a "
            "fresh instruction for a row the decision already settled",
            second,
        )

        rows_after = w.rows()
        assert len(rows_after) == 2, (
            "re-uploading the same book must not change the OI row count - the settled "
            "row's own qty/date no longer matching the sheet's literal figures must not "
            "make _restated_existing treat the sheet row as a brand-new instruction that "
            "lands on the untouched, genuinely-free line 3",
            [(str(r.so_line_id), str(r.qty), r.delivery_date) for r in rows_after],
        )
        assert not any(str(r.so_line_id) == mirror3_id for r in rows_after), (
            "line 3 must stay untouched by the re-upload too - the sheet's 40 @ d1 row is "
            "restating line 1's already-settled row, not a new instruction",
            [(str(r.so_line_id), str(r.qty), r.delivery_date) for r in rows_after],
        )

        mirror1_rows_after = [r for r in rows_after if str(r.so_line_id) == mirror1_id]
        assert len(mirror1_rows_after) == 1, (
            "line 1 must still carry exactly ONE row after the re-upload",
            [(str(r.id), str(r.qty), r.delivery_date) for r in mirror1_rows_after],
        )
        assert mirror1_rows_after[0].id == row_on_line1_id, (
            "the re-upload must restate the SAME settled row, not replace or duplicate it"
        )
        assert mirror1_rows_after[0].qty == Decimal("30"), mirror1_rows_after[0].qty
        assert mirror1_rows_after[0].delivery_date == settled_date, (
            mirror1_rows_after[0].delivery_date
        )
