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

from datetime import date

import pytest

from app.services import project_order_inquiry_import_service as importer
from tests.test_oi_sheet_pairing_repair import _apply
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
        assert result["line_not_found"][0]["reason"] == "no_line_for_item", result


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
