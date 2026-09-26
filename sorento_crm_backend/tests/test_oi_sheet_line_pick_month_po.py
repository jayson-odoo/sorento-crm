"""The order inquiry sheet's line pick: exact date, then same month, then the sheet's PO.

Contract: `documentation/plans/scm/oi-sheet-line-pick-month-po-acceptance-criteria.md`,
AC-LP-1 to AC-LP-17, with `PLAN-oi-sheet-line-pick-month-po.md` sections 0 to 3 for the
promised behaviour. One test per criterion, named for it; AC-LP-12 gets two (the ledger
charge, and the legitimate split it must not break). AC-LP-14 (R4), AC-LP-15 (R5), AC-LP-16
(R6) and AC-LP-17 (R7) are later small-fix slices, each added after the pick's own tests
below first went green.

TEST-FIRST, written before the four-pass line pick exists (AC-LP-1 to AC-LP-13 below; the
red state for those was TODAY's single-pass `_rank_for` behaviour on `origin/main` - a row
landing on the wrong line, or the ledger NOT charging an already-raised line, review
finding 9, 14 Sep, which this slice reverses on purpose - never an import typo or a fixture
bug). AC-LP-14 and AC-LP-15 are each their own small red-then-green round against the
FIVE-pass pick that resulted; their own docstrings say what was red for them.

The fixture is the UAC's own measured shape, SO324265 / BT012-CR (prod, 19 Sep 2026): one
project-class sales order, one product, seven lines. `_uac_book` seeds the book half
(the lines and the three purchase orders that bought for them); `_uac_rows` seeds the
sheet half (the row tuples `sheet()`/`book()` take, keyed by label). Every purchase order
number is minted in the family the UAC states (`202508-...`, `202510-...`, `202603-...`)
but suffixed unique per test (`_po_number`), so parallel runs never collide on one number
and the sheet's own citation always names the number this run actually created.

Harness reused from the sibling files rather than copied wholesale: `World` / `world()`,
`sheet()` / `book()`, `D_OCT`, `_n`, `_uid` from `test_project_order_inquiry_import_migration`
(the canonical seeded-world file); `_with_ref` / `_names` from the same file (every sibling
test file defines its own copy of `_ref()` rather than importing one, so a test-looking
value can never be special-cased by the importer - this file does too). `_sibling_po_line`
is copied from `test_oi_sheet_pairing_repair.py::_sibling_po_line` (a second line on an
EXISTING purchase order), needed here because several UAC lines share one purchase order.
`World.apply` already takes an `outcome=`, so no local `_apply` wrapper is needed - none of
these criteria need `file_name` (that is the rollback slice's own concern).

Postgres only (`tests/_pg_fixture.py`, reached through `world()`). Every chain is seeded
here - company, uom, category, product, warehouse, sales order, purchase orders - because
CI's database is empty and nothing may be read off an existing row.

**Finding-9 search (asked for by the tester brief, not code touched here):** no existing
test asserts the no-charge-on-an-already-raised-line behaviour with a SECOND row proving
the line's remaining quantity was not reduced. `_match_row`'s own docstring
(`app/services/project_order_inquiry_import_service.py`, "review finding 9, 14 Sep") is the
only place the behaviour is stated. `test_line_with_existing_row_is_skipped` (AC-S1-10,
`test_project_order_inquiry_import_migration.py:804`) and
`test_sheet_reupload_skips_redirected_line` (`test_oi_sheet_pairing_repair.py:2236`) both
seed an already-raised line but send only ONE sheet row at it, so neither one can observe
whether the ledger was charged - they pin `_already_raised`'s own read, not `_match_row`'s
charge decision. AC-LP-12 (`test_ac_lp_12_charge_already_raised_line` below) is the new
test that pins the reversed behaviour; nothing existing needed to change.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrderLine
from app.services.import_outcome import ImportOutcome
from app.services.project_so_adoption_service import ProjectSOAdoptionService

from .test_project_order_inquiry_import_migration import (
    D_OCT,
    World,
    _n,
    _names,
    _uid,
    _with_ref,
    book,
    sheet,
    world,
)

#: A delivery date used by criteria that need one exact match and nothing else notable
#: about it (AC-LP-8's first two scenarios).
D_MATCH = date(2026, 3, 1)


def _ref() -> str:
    """The shape AutoCount writes into `sales_order_lines.source_ref`, minted in the same
    family every sibling file uses, so nothing in the importer can special-case a
    test-looking value."""
    return f"AED_SORENTO:{41576559 + _n()}:{41604391 + _n()}"


def _po_number(prefix: str) -> str:
    """A purchase order number in the family the UAC fixture states (`<prefix>-Snnnn`),
    suffixed unique per test so parallel runs never collide on one number - the sheet's
    own citation always names the exact number this run minted."""
    return f"{prefix}-S{_n():04d}"


def _sibling_po_line(
    w: World, po, *, qty_ordered: str, from_so_line_ref: str, product=None,
) -> PurchaseOrderLine:
    """A SECOND line on an EXISTING purchase order (copied from
    `test_oi_sheet_pairing_repair.py::_sibling_po_line`): `World.po_line` mints a new
    document every call, and the UAC's own book has one purchase order buying for several
    lines."""
    line = PurchaseOrderLine(
        id=_uid(),
        company_id=w.company_id,
        purchase_order_id=po.id,
        product_id=(product or w.product).id,
        warehouse_id=w.warehouse.id,
        qty_ordered=Decimal(qty_ordered),
        qty_received=Decimal("0"),
        expected_date=date(2026, 9, 1),
        line_status="open",
        from_so_line_ref=from_so_line_ref,
    )
    w.db.add(line)
    w.db.flush()
    return line


def _born_at(w: World, line: SalesOrderLine, when: datetime) -> SalesOrderLine:
    """`created_at` written explicitly (copied from
    `test_oi_sheet_pairing_repair.py::_born_at`): it is the LAST tiebreak in the line pick,
    and `server_default=func.now()` gives every line seeded in one transaction the SAME
    timestamp (Postgres freezes `now()` per transaction), so a test that relies on "the
    older line" without saying which is older would be measuring the order the SELECT
    happened to return."""
    line.created_at = when
    w.db.flush()
    return line


# --------------------------------------------------------------------------- #
# the UAC fixture: one order, seven lines, three purchase orders               #
# --------------------------------------------------------------------------- #

#: The book's own seven lines, exactly as SO324265 / BT012-CR measured them (UAC table 1).
#: One product throughout - the line pick is entirely a question of WHICH line, never of
#: item or location.
_UAC_LINE_DATES: tuple[tuple[str, date, int], ...] = (
    ("2025-12-01", date(2025, 12, 1), 200),
    ("2026-01-02", date(2026, 1, 2), 200),
    ("2026-04-02", date(2026, 4, 2), 200),
    ("2026-05-01", date(2026, 5, 1), 200),
    ("2026-05-02", date(2026, 5, 2), 200),
    ("2026-05-04", date(2026, 5, 4), 200),
    ("2026-06-01", date(2026, 6, 1), 222),
)


def _uac_book(w: World) -> tuple[SalesOrder, dict[str, SalesOrderLine], dict[str, str]]:
    """The book half of the fixture (UAC table 1): one sales order, its seven lines, and
    the three purchase orders that bought for them.

    Returns `(order, lines, pos)`: `lines` keyed by the line's own `required_date` in ISO
    form; `pos` keyed `"aug"` / `"oct"` / `"mar"` for the three purchase order numbers
    (`202508-...`, `202510-...`, `202603-...`) - the sheet never cites `"aug"` at all,
    which is the whole of AC-LP-1's "no row on the 2025-12-01 line".
    """
    order = w.order()
    lines = {
        label: _with_ref(w, w.line(order, qty_ordered=str(qty), required_date=when), _ref())
        for label, when, qty in _UAC_LINE_DATES
    }

    po_aug, aug_line = w.po_line(qty_ordered="200", number=_po_number("202508"))
    _names(w, aug_line, lines["2025-12-01"].source_ref)

    po_oct, oct_line_1 = w.po_line(qty_ordered="200", number=_po_number("202510"))
    _names(w, oct_line_1, lines["2026-01-02"].source_ref)
    for label in ("2026-04-02", "2026-05-01", "2026-05-02"):
        _sibling_po_line(
            w, po_oct, qty_ordered="200", from_so_line_ref=lines[label].source_ref,
        )

    po_mar, mar_line_1 = w.po_line(qty_ordered="200", number=_po_number("202603"))
    _names(w, mar_line_1, lines["2026-05-04"].source_ref)
    _sibling_po_line(
        w, po_mar, qty_ordered="222", from_so_line_ref=lines["2026-06-01"].source_ref,
    )

    pos = {"aug": po_aug.po_number, "oct": po_oct.po_number, "mar": po_mar.po_number}
    return order, lines, pos


def _uac_rows(w: World, order: SalesOrder, pos: dict[str, str]) -> dict[str, tuple]:
    """The sheet half of the fixture (UAC table 2): one row tuple per label, in the shape
    `sheet()` / `book()` take.

    05-04 and 06-01 each have TWO tuples - `-month` (the monthly tab, PO cell blank) and
    `-rollup` (the roll-up tab, PO cell stated) - because the UAC states them as a
    restatement of one instruction, not two (AC-LP-10's own scenario is exactly this pair;
    every other criterion that uses this fixture carries both tabs so the citation-lending
    behaviour is exercised even where it does not change the landing).
    """
    p, loc, so = w.product.product_code, w.warehouse.warehouse_code, order.so_number
    return {
        "01-02": (so, p, 200, date(2026, 1, 2), loc, pos["oct"]),
        "02-02": (so, p, 200, date(2026, 2, 2), loc, pos["oct"]),
        "03-02": (so, p, 200, date(2026, 3, 2), loc, pos["oct"]),
        "04-01": (so, p, 200, date(2026, 4, 1), loc, pos["oct"]),
        "05-04-month": (so, p, 200, date(2026, 5, 4), loc, ""),
        "05-04-rollup": (so, p, 200, date(2026, 5, 4), loc, pos["mar"]),
        "06-01-month": (so, p, 222, date(2026, 6, 1), loc, ""),
        "06-01-rollup": (so, p, 222, date(2026, 6, 1), loc, pos["mar"]),
    }


def _uac_month_and_rollup(rows: dict[str, tuple]) -> bytes:
    """The book in the UAC's own tab shape: one MONTH tab in file order, one ROLLUP tab
    restating the two dates it left blank - AC-LP-1's own layout, reused wherever tab order
    is not itself what a criterion is testing."""
    return book(
        MONTH=[
            rows["01-02"], rows["02-02"], rows["03-02"], rows["04-01"],
            rows["05-04-month"], rows["06-01-month"],
        ],
        ROLLUP=[rows["05-04-rollup"], rows["06-01-rollup"]],
    )


def _rows_by_date(w: World) -> dict:
    held: dict = {}
    for row in w.rows():
        held.setdefault(row.delivery_date, []).append(row)
    return held


def _assert_lands_on(w: World, rows_by_date: dict, when: date, core_line: SalesOrderLine):
    landed = rows_by_date.get(when, [])
    assert len(landed) == 1, (when, [str(r.id) for r in landed])
    mirror = w.mirror_of(core_line)
    assert mirror is not None, f"the line required on {when} was never even mirrored"
    assert str(landed[0].so_line_id) == str(mirror.id), (
        f"the {when} row landed on {landed[0].so_line_id}, not the line the UAC names"
    )


def _assert_uac_landing(w: World, lines: dict[str, SalesOrderLine]) -> None:
    """The exact map AC-LP-1 states. Reused by every criterion that only reorders the file
    (AC-LP-2, AC-LP-3, AC-LP-13): the landing must not move."""
    rows_by_date = _rows_by_date(w)
    _assert_lands_on(w, rows_by_date, date(2026, 1, 2), lines["2026-01-02"])
    _assert_lands_on(w, rows_by_date, date(2026, 4, 1), lines["2026-04-02"])
    _assert_lands_on(w, rows_by_date, date(2026, 2, 2), lines["2026-05-01"])
    _assert_lands_on(w, rows_by_date, date(2026, 3, 2), lines["2026-05-02"])
    _assert_lands_on(w, rows_by_date, date(2026, 5, 4), lines["2026-05-04"])
    _assert_lands_on(w, rows_by_date, date(2026, 6, 1), lines["2026-06-01"])
    december_mirror = w.mirror_of(lines["2025-12-01"])
    assert december_mirror is None or not any(
        str(row.so_line_id) == str(december_mirror.id) for row in w.rows()
    ), "a row landed on the 2025-12-01 line the 2026 book never names"


# --------------------------------------------------------------------------- #
# AC-LP-1 to AC-LP-3: the passes, and file order not deciding them            #
# --------------------------------------------------------------------------- #


# test_ac_lp_1_exact_month_po_fallback_lands_every_2026_line (AC-LP-1),
# test_ac_lp_2_exact_date_beats_file_order (AC-LP-2) and
# test_ac_lp_3_same_month_beats_file_order (AC-LP-3) retired under R4,
# PLAN-board-received-stock-own-arrival, 21 Sep 2026: each pinned the UAC fixture's landing
# under the five-pass exact-date/same-month/PO pick, which `_pick_lines_by_date_order`
# replaces with pure positional date-order pairing (candidate lines sorted by
# `required_date`, sheet rows sorted by `delivery_date`, paired one to one) - the very
# defect (S0's own measurement against SO372176) R4 was ruled to fix. Under the new pick the
# UAC fixture's 2025-12-01 line, bought for but never cited or dated close by the sheet, is
# no longer skipped: it is simply the earliest candidate line and takes whichever sheet row
# sorts first, which is exactly the shape AC-S4-1
# (`tests/scm/test_board_received_stock_s4_import_pairing.py`) now pins instead.


# --------------------------------------------------------------------------- #
# AC-LP-4 to AC-LP-6: the same-month tie-break, and the PO pass proper         #
# --------------------------------------------------------------------------- #


# test_ac_lp_4_same_month_two_lines_po_then_nearest_date (AC-LP-4) retired under R4,
# PLAN-board-received-stock-own-arrival, 21 Sep 2026: it pinned the same-month tie-break
# (citation, then nearest date) of the superseded five-pass pick. `_pick_lines_by_date_order`
# pairs candidate lines to sheet rows purely positionally by sort order (required_date /
# delivery_date), so neither a cited PO nor "nearest date" plays any role in which of two
# same-month lines a row lands on any more.


def test_ac_lp_5_sheet_po_pass_hands_out_in_date_order():
    """AC-LP-5. Two rows left after the month pass, both citing the same purchase order,
    stated with the LATER row FIRST in the file: the EARLIER row still takes the EARLIER
    free line - the hand-out is by the row's own date, never by file order."""
    with world() as w:
        order = w.order()
        line_july = _with_ref(
            w, w.line(order, qty_ordered="90", required_date=date(2026, 7, 1)), _ref(),
        )
        line_sept = _with_ref(
            w, w.line(order, qty_ordered="90", required_date=date(2026, 9, 1)), _ref(),
        )
        po, po_line_july = w.po_line(qty_ordered="90")
        _names(w, po_line_july, line_july.source_ref)
        _sibling_po_line(
            w, po, qty_ordered="90", from_so_line_ref=line_sept.source_ref,
        )
        data = sheet([
            (order.so_number, w.product.product_code, 90, date(2026, 4, 1),
             w.warehouse.warehouse_code, po.po_number),
            (order.so_number, w.product.product_code, 90, date(2026, 3, 1),
             w.warehouse.warehouse_code, po.po_number),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        rows_by_date = _rows_by_date(w)
        _assert_lands_on(w, rows_by_date, date(2026, 3, 1), line_july)
        _assert_lands_on(w, rows_by_date, date(2026, 4, 1), line_sept)


def test_ac_lp_6_no_po_or_po_names_no_free_line_falls_to_today_rank():
    """AC-LP-6. A row that cites no PO at all, or whose cited PO names no free line of
    this order, is never refused for it - both fall through to today's unchanged rank
    (bought, open, earliest date, oldest, id)."""
    with world() as w:
        order = w.order()
        bought = _with_ref(
            w, w.line(order, qty_ordered="60", required_date=date(2026, 8, 1)), _ref(),
        )
        w.line(order, qty_ordered="60", required_date=date(2026, 8, 20))
        po, po_line = w.po_line(qty_ordered="60")
        _names(w, po_line, bought.source_ref)
        data = sheet([
            (order.so_number, w.product.product_code, 60, date(2026, 1, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(bought)
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "with nothing cited, the fallback should still prefer the line the book "
            "bought for"
        )

    with world() as w:
        order = w.order()
        bought_other = _with_ref(
            w, w.line(order, qty_ordered="60", required_date=date(2026, 8, 1)), _ref(),
        )
        w.line(order, qty_ordered="60", required_date=date(2026, 8, 20))
        po_other, po_line_other = w.po_line(qty_ordered="60")
        _names(w, po_line_other, bought_other.source_ref)
        # A real PO number, in the family the reader parses, that names no line of THIS
        # order at all - the row cites something, but it answers for nothing here.
        absent_po_number = _po_number("202612")
        data = sheet([
            (order.so_number, w.product.product_code, 60, date(2026, 1, 1),
             w.warehouse.warehouse_code, absent_po_number),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(bought_other)
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "citing a PO that names no free line should still fall to the blanket bought "
            "fallback, not refuse the row"
        )


# --------------------------------------------------------------------------- #
# AC-LP-7: the sheet's PO decides the LINE, never the LINK                    #
# --------------------------------------------------------------------------- #


def test_ac_lp_7_link_follows_the_book_never_the_sheets_po():
    """AC-LP-7. A row whose sheet PO differs from the book's own PO for the line it landed
    on links to the BOOK's document - the sheet's citation still pairs nothing (R2 kept).

    The UAC-fixture half of this test (six rows, per-line expected link) retired under R4,
    PLAN-board-received-stock-own-arrival, 21 Sep 2026: it asserted the landing AC-LP-1
    pinned, which `_pick_lines_by_date_order`'s positional pairing changes (see
    `test_ac_lp_1_exact_month_po_fallback_lands_every_2026_line`'s retirement note above).
    The single-line half below is untouched: it seeds only ONE open line, so the line pick
    picks it however it is reached, and this test's own point - that the LINK still follows
    `plan.bought_rows`, unchanged by R4's date-order pick, never the sheet's own citation -
    is unaffected and still verified here.
    """
    with world() as w:
        order = w.order()
        line = _with_ref(
            w, w.line(order, qty_ordered="40", required_date=D_OCT), _ref(),
        )
        po_book, po_line = w.po_line(qty_ordered="40")
        _names(w, po_line, line.source_ref)
        po_sheet, _unrelated_line = w.po_line(qty_ordered="40")
        data = sheet([
            (order.so_number, w.product.product_code, 40, D_OCT,
             w.warehouse.warehouse_code, po_sheet.po_number),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        links = w.links(w.one_row())
        assert len(links) == 1, [link.document for link in links]
        assert links[0].document == po_book.po_number, (
            "the row linked to the sheet's own citation instead of the book's document"
        )
        assert links[0].document != po_sheet.po_number


# --------------------------------------------------------------------------- #
# AC-LP-8/9: D1 restated for the passes; ORDER BACK skips three of them       #
# --------------------------------------------------------------------------- #


def test_ac_lp_8_cancelled_ranks_last_in_every_pass():
    """AC-LP-8. D1, restated for the five-pass pick: a cancelled line loses to any live
    line that fits - in the exact-date pass, in the PO pass.

    Both scenarios below still hold their OUTCOME (the live line wins) after R4,
    PLAN-board-received-stock-own-arrival, 21 Sep 2026, even though the REASON changed: the
    cancelled line is no longer merely ranked behind a live one, it is excluded from the
    candidate pool entirely (AC-S4-3), so `_pick_lines_by_date_order` never offers it a
    chance to lose in the first place. The third scenario this test used to carry ("a lone
    cancelled line still matches - it is where the history is", D1) asserted the OPPOSITE of
    AC-S4-3 ("a closed or cancelled core line is never paired, even when it is the only qty
    fit") and is retired; that exact shape (a lone cancelled line, nothing else in the
    order) is now covered by
    `tests/scm/test_board_received_stock_s4_import_pairing.py::test_ac_s4_3_closed_or_cancelled_line_never_paired`,
    which asserts the row is refused `no_line_for_item` rather than matched.
    """
    with world() as w:
        order = w.order()
        _with_ref(
            w,
            w.line(order, qty_ordered="50", required_date=D_MATCH, line_status="cancelled"),
            _ref(),
        )
        live = _with_ref(
            w, w.line(order, qty_ordered="50", required_date=D_MATCH), _ref(),
        )
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_MATCH,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(live)
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "the exact-date pass took the cancelled line over the live one"
        )

    with world() as w:
        order = w.order()
        cancelled = _with_ref(
            w,
            w.line(order, qty_ordered="50", required_date=date(2026, 9, 1),
                   line_status="cancelled"),
            _ref(),
        )
        live = _with_ref(
            w, w.line(order, qty_ordered="50", required_date=date(2026, 11, 1)), _ref(),
        )
        po, po_line = w.po_line(qty_ordered="50")
        # Named to BOTH lines - a document naming a cancelled AND a live line is the exact
        # ghost-vs-real shape the pairing repair plan measured (AC-R-10's own premise).
        _names(w, po_line, cancelled.source_ref)
        _sibling_po_line(w, po, qty_ordered="50", from_so_line_ref=live.source_ref)
        data = sheet([
            (order.so_number, w.product.product_code, 30, date(2026, 3, 1),
             w.warehouse.warehouse_code, po.po_number),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(live)
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "the PO pass took the cancelled line over the live one it also names"
        )


# test_ac_lp_9_order_back_lands_on_the_cited_po_line (AC-LP-9) retired under R4,
# PLAN-board-received-stock-own-arrival, 21 Sep 2026: it pinned the PO-citation pass
# deciding which line an undated ORDER BACK row lands on. `_pick_lines_by_date_order` sorts
# undated rows LAST within one order's file-order walk and still pairs purely positionally
# (candidate open lines sorted by `required_date`), so a citation no longer has any say in
# an ORDER BACK row's landing either - it lands on whichever open line the positional walk
# reaches it at.


# --------------------------------------------------------------------------- #
# AC-LP-10: citation lending reaches the line pick                            #
# --------------------------------------------------------------------------- #


# test_ac_lp_10_restatement_lends_its_po_to_the_first_statement (AC-LP-10) retired under
# R4, PLAN-board-received-stock-own-arrival, 21 Sep 2026: it pinned "a restatement's cited
# PO reaches the line pick" (the PO pass), which is unreachable now - the line pick reads
# `required_date`/`delivery_date` only. Its own docstring already flagged the risk this
# retirement realises: with the PO pass gone, its assertions hold or fail purely on the
# fixture's POSITIONAL date order (the earlier-required-date candidate wins either way),
# which would make a kept copy pass for a reason its own text no longer describes.


# --------------------------------------------------------------------------- #
# AC-LP-11: re-upload reports the SAME line every time                        #
# --------------------------------------------------------------------------- #


# test_ac_lp_11_reupload_reports_the_same_line_every_time (AC-LP-11) retired under R4,
# PLAN-board-received-stock-own-arrival, 21 Sep 2026: `_assert_uac_landing` pinned the
# five-pass landing map (see the AC-LP-1/2/3 retirement note above), so this test's re-upload
# comparison would only ever be comparing two runs of the WRONG landing to each other. The
# general property it was proving - re-upload is idempotent, nothing raises twice, no row
# ever moves - is covered instead by AC-S4-4
# (`tests/scm/test_board_received_stock_s4_import_pairing.py::test_ac_s4_4_reupload_of_both_books_restates_in_place_never_drops`),
# under the current date-order pick.


# --------------------------------------------------------------------------- #
# AC-LP-12: the ledger charges an already-raised line, and a legitimate split #
# still lands both of its rows                                                #
# --------------------------------------------------------------------------- #


def test_ac_lp_12_charge_already_raised_line():
    """AC-LP-12 (charge). A row that lands on an already-raised line still spends its
    quantity against this file's own ledger - reversing review finding 9 (14 Sep) on
    purpose (PLAN section 2, "Ledger") - so a second row of the same item cannot land on
    the same line for more than what is left."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="200", required_date=D_OCT)
        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        w.board_row(w.mirror_of(line), qty="5")
        data = sheet([
            (order.so_number, w.product.product_code, 150, D_OCT,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 100, date(2026, 11, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 0, result
        assert result["rows_already_raised"] == 1, (
            "only the first row should have been permitted to land on the "
            f"already-raised line: {result}"
        )
        assert result["rows_line_not_found"] == 1, result
        assert [entry["reason"] for entry in result["line_not_found"]] == [
            "qty_exceeds_ordered"
        ], result


def test_ac_lp_12_bumped_row_becomes_a_second_row_on_the_taken_line():
    """AC-LP-12 (bumped). Line A already carries a row from an earlier import; line B is
    free. The sheet states two rows, both dated Oct: 150 then 100. The 150 row is
    processed first and pairs onto B, the free candidate; the 100 row is then bumped onto
    A - not skipped as `already_raised`, but raised as a genuine SECOND row on A
    (`already_raised` False, an ordinary migration note), because A's own item DID have a
    free candidate (B) before this walk spent it on the earlier row. Nothing is dropped:
    two rows raised, zero already-raised, zero line-not-found; the DB ends up holding the
    old row on A, the new 100 on A, and the 150 on B.

    Re-pinned under R4, PLAN-board-received-stock-own-arrival, 21 Sep 2026: the
    "bumped row" fix round in `_pick_lines_by_date_order`
    (`app/services/project_order_inquiry_import_service.py`, `row_has_free`) closes the
    silent drop this test used to pin as a known regression - a row bumped off a free line
    by an earlier row of the SAME walk is now raised honestly as a second row instead of
    being absorbed into `rows_already_raised` with no report at all.
    """
    with world() as w:
        order = w.order()
        line_a = w.line(order, qty_ordered="200", required_date=D_OCT)
        line_b = w.line(order, qty_ordered="200", required_date=date(2026, 12, 1))
        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        w.board_row(w.mirror_of(line_a), qty="5")
        data = sheet([
            (order.so_number, w.product.product_code, 150, D_OCT,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 100, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        assert result["rows_already_raised"] == 0, result
        assert result["rows_line_not_found"] == 0, result
        mirror_a = w.mirror_of(line_a)
        mirror_b = w.mirror_of(line_b)
        assert mirror_a is not None and mirror_b is not None
        qtys_by_line: dict[str, list[Decimal]] = {}
        for row in w.rows():
            qtys_by_line.setdefault(str(row.so_line_id), []).append(
                Decimal(str(row.qty))
            )
        assert sorted(qtys_by_line.get(str(mirror_a.id), [])) == [
            Decimal("5"), Decimal("100"),
        ], (
            "line A should hold both the old already-raised row and the new bumped "
            f"second row: {qtys_by_line}"
        )
        assert qtys_by_line.get(str(mirror_b.id)) == [Decimal("150")], (
            f"line B should hold only the first, unbumped row: {qtys_by_line}"
        )


def test_ac_lp_12_legitimate_split_still_lands_both_rows():
    """AC-LP-12 (split, AC-S1-2 kept). Two sheet rows that legitimately split ONE line's
    quantity - 120 plus 80 on a 200 line, neither of them already raised - still both
    land on it: the ledger charge above must not turn into a rule that only one row of a
    file may ever reach a line.

    The two quantities must differ (120/80, not 100/100): `_restates`' key is sales order,
    item, quantity, delivery date and location, so two rows identical on all five are a
    RESTATEMENT of one instruction (owner ruling R3, 14 Sep), not a split, and only one of
    them would raise. A split is two rows that differ on one of those five - here, the
    quantity - which is exactly what AC-S1-2 means by "the sheet may split one line".
    """
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="200", required_date=D_OCT)
        data = sheet([
            (order.so_number, w.product.product_code, 120, D_OCT,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 80, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        mirror = w.mirror_of(line)
        rows = w.rows()
        assert {str(row.so_line_id) for row in rows} == {str(mirror.id)}
        assert sorted(Decimal(str(row.qty)) for row in rows) == [
            Decimal("80"), Decimal("120"),
        ]


# --------------------------------------------------------------------------- #
# AC-LP-13: preview and apply agree                                           #
# --------------------------------------------------------------------------- #


# test_ac_lp_13_preview_and_apply_land_every_row_the_same (AC-LP-13) retired under R4,
# PLAN-board-received-stock-own-arrival, 21 Sep 2026: it used `_assert_uac_landing` (the
# five-pass landing) as its "same line every time" check. `preview`/`apply` agreement is
# covered independently under the current date-order pick by AC-S4-2
# (`tests/scm/test_board_received_stock_s4_import_pairing.py::test_ac_s4_2_fifth_row_beyond_last_line_lands_as_second_row_on_it`),
# which calls `importer.preview` then `_apply` on the same data and compares `rows_raised`.


# --------------------------------------------------------------------------- #
# New measured defect (19 Sep 2026): Excel date SERIALS in the delivery cell,  #
# not an AC-LP of the UAC - the importer-level regression the reader defect    #
# causes (see test_oi_sheet_reader_serial_dates.py for the reader itself).     #
# --------------------------------------------------------------------------- #


def test_serial_dated_rows_are_not_restatements():
    """The customer's current `JAN - DEC 2026 ORDERabc.xlsx` leaves DELIVERY DATE in
    General format holding a plain Excel serial (`46024` = 2026-01-02, `46113` =
    2026-04-01), not a date cell. `_as_date` does not parse a serial (measured, 19 Sep
    2026: 15,942 of 16,057 rows read with no delivery date), so both rows here tie on
    `_restates`' key - same SO, item, qty, and a now-identical `delivery_date=None` - and
    the SECOND is read as a restatement of the first: two real deliveries of 200 collapse
    into one raised row instead of two.

    On TWO SEPARATE tabs on purpose (review round 2, 19 Sep 2026): R5 already makes two
    identical rows on the SAME tab two instructions regardless of whether their dates ever
    parse, which would leave this test green even with the serial branch of `_as_date`
    removed. Across tabs, an unparsed serial still ties both rows to the SAME `_restates`
    key (`delivery_date=None` on both), so the SECOND tab's row still reads as a genuine
    cross-tab restatement of the first UNLESS the serial actually parses into two different
    dates - which is the one thing this test is pinning.
    """
    with world() as w:
        order = w.order()
        line_first = w.line(order, qty_ordered="200", required_date=date(2026, 1, 2))
        line_second = w.line(order, qty_ordered="200", required_date=date(2026, 4, 2))
        data = book(
            JAN=[(
                order.so_number, w.product.product_code, 200, 46024,
                w.warehouse.warehouse_code, "",
            )],
            APR=[(
                order.so_number, w.product.product_code, 200, 46113,
                w.warehouse.warehouse_code, "",
            )],
        )

        result = w.apply(data)

        assert result["rows_raised"] == 2, (
            "before the serial-date fix both rows tie on `_restates`' key (same qty, "
            f"delivery date None) and the second reads as a restatement: {result}"
        )
        rows = w.rows()
        assert len(rows) == 2, [str(row.qty) for row in rows]
        mirror_first = w.mirror_of(line_first)
        mirror_second = w.mirror_of(line_second)
        assert mirror_first is not None and mirror_second is not None
        assert {str(row.so_line_id) for row in rows} == {
            str(mirror_first.id), str(mirror_second.id),
        }, "one row per line, not both stacked onto one"


# --------------------------------------------------------------------------- #
# AC-LP-14: the sheet's PO outranks the month when they disagree (R4)         #
# --------------------------------------------------------------------------- #


# test_ac_lp_14_sheet_po_outranks_same_month (AC-LP-14) retired under R4,
# PLAN-board-received-stock-own-arrival, 21 Sep 2026: it pinned the 19 Sep 2026 R4 ruling
# that the sheet's own cited PO outranks a bare same-month tie in the five-pass pick - a
# DIFFERENT, now-superseded R4 from `PLAN-oi-sheet-line-pick-month-po.md`, not the 21 Sep
# ruling this lane implements. The citation/month passes it exercised are unreachable under
# `_pick_lines_by_date_order`'s positional date-order pairing.


# --------------------------------------------------------------------------- #
# AC-LP-15: a restatement is only ever ACROSS tabs (R5)                       #
# --------------------------------------------------------------------------- #


def test_ac_lp_15_identical_rows_inside_one_tab_are_separate_deliveries():
    """AC-LP-15 (R5, 19 Sep 2026, prod CB1178A-SS-NEW / SO324265). Two lines of the same
    order, item and date - two unit types delivered together - and the sheet states the
    delivery TWICE inside the SAME month tab, then twice again on the roll-up: four rows on
    the sheet, but only TWO real instructions (measured book-wide: 517 keys stated more than
    once inside one tab, 650 deliveries dropped as restatements, across 90 sales orders).
    `_restates` must not collapse the two identical rows within ONE tab into one instruction
    - only a LATER tab restates what an earlier tab already said."""
    with world() as w:
        order = w.order()
        line_a = w.line(order, qty_ordered="25", required_date=date(2026, 1, 2))
        line_b = w.line(order, qty_ordered="25", required_date=date(2026, 1, 2))
        row = (
            order.so_number, w.product.product_code, 25, date(2026, 1, 2),
            w.warehouse.warehouse_code, "",
        )
        data = book(MONTH=[row, row], ROLLUP=[row, row])
        outcome = ImportOutcome(None, persist=False)

        result = w.apply(data, outcome=outcome)

        assert result["rows_raised"] == 2, result
        assert outcome.count_of("restates_an_instalment") == 2, outcome.breakdown()
        rows = w.rows()
        assert len(rows) == 2, [str(r.qty) for r in rows]
        mirror_a, mirror_b = w.mirror_of(line_a), w.mirror_of(line_b)
        assert {str(r.so_line_id) for r in rows} == {str(mirror_a.id), str(mirror_b.id)}


def test_ac_lp_15_roll_up_with_fewer_repeats_adds_nothing():
    """AC-LP-15. The roll-up need not repeat every count the month tab does: the month tab
    states the delivery TWICE (two real instructions), the roll-up restates it only ONCE -
    the roll-up's single row restates the FIRST month instruction by position, nothing
    restates the second one again, and both still raise."""
    with world() as w:
        order = w.order()
        line_a = w.line(order, qty_ordered="25", required_date=date(2026, 1, 2))
        line_b = w.line(order, qty_ordered="25", required_date=date(2026, 1, 2))
        row = (
            order.so_number, w.product.product_code, 25, date(2026, 1, 2),
            w.warehouse.warehouse_code, "",
        )
        data = book(MONTH=[row, row], ROLLUP=[row])
        outcome = ImportOutcome(None, persist=False)

        result = w.apply(data, outcome=outcome)

        assert result["rows_raised"] == 2, result
        assert outcome.count_of("restates_an_instalment") == 1, outcome.breakdown()
        rows = w.rows()
        assert len(rows) == 2, [str(r.qty) for r in rows]
        mirror_a, mirror_b = w.mirror_of(line_a), w.mirror_of(line_b)
        assert {str(r.so_line_id) for r in rows} == {str(mirror_a.id), str(mirror_b.id)}


# test_ac_lp_15_lending_goes_to_the_matching_repeat (AC-LP-15, lending) retired under R4,
# PLAN-board-received-stock-own-arrival, 21 Sep 2026: it pinned citation lending reaching
# the SAME-POSITION month instruction through the PO pass, which no longer exists - the line
# pick reads only `required_date` / `delivery_date` now.


def test_single_sheet_variant_never_dedupes_a_repeat():
    """R5 (19 Sep 2026). The single-sheet variant (`Order Inquiry Form.xlsx`, `sheet()`
    here) has no SECOND tab, so there is nothing left to restate anything - two identical
    rows in this one file are two instructions from the first cell onward, exactly as they
    are inside one tab of the monthly book (AC-LP-15's own point, pinned here for the shape
    that has no tab at all to restate ACROSS)."""
    with world() as w:
        order = w.order()
        line_a = w.line(order, qty_ordered="25", required_date=date(2026, 1, 2))
        line_b = w.line(order, qty_ordered="25", required_date=date(2026, 1, 2))
        data = sheet([
            (order.so_number, w.product.product_code, 25, date(2026, 1, 2),
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 25, date(2026, 1, 2),
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        rows = w.rows()
        assert len(rows) == 2, [str(r.qty) for r in rows]
        assert {str(r.so_line_id) for r in rows} == {
            str(w.mirror_of(line_a).id), str(w.mirror_of(line_b).id),
        }


# --------------------------------------------------------------------------- #
# AC-LP-16: an equal-quantity line is tried before a bigger one (R6)          #
# --------------------------------------------------------------------------- #


# test_ac_lp_16_equal_quantity_line_before_a_bigger_one and
# test_ac_lp_16_equal_quantity_wins_the_po_pass_too (AC-LP-16, R6 of the OLDER
# `PLAN-oi-sheet-line-pick-month-po.md`, 19 Sep 2026) retired under R4,
# PLAN-board-received-stock-own-arrival, 21 Sep 2026: both pinned an "equal-quantity"
# tie-break step layered onto the now-fully-retired five-pass pick's exact-date and PO
# passes. `_pick_lines_by_date_order` has no quantity-aware tie-break at all - two
# same-required-date candidate lines are ordered only by `created_at` then `id` - which is
# R4's OWN explicitly simple design (date order alone, per the plan and AC-S4), not a
# regression it forbids: the resulting `qty_exceeds_ordered` refusal, when it happens, is
# reported honestly through `line_not_found`, never a silent drop (see
# `test_ac_lp_12_bumped_row_becomes_a_second_row_on_the_taken_line` above, re-pinned
# 21 Sep 2026, for the sibling shape - a row bumped off a free line - which the same fix
# round now raises honestly instead of dropping). Worth the owner's awareness as a known
# trade-off of the simpler pick, not reported as a defect here.


# --------------------------------------------------------------------------- #
# AC-LP-16 round 2 (review): zero lines, a cancelled ghost, the fallback step #
# --------------------------------------------------------------------------- #


def test_ac_lp_16_zero_lines_reports_no_line_for_item():
    """AC-LP-16 (blocker 1, review round 2, 19 Sep 2026). A plannable order that holds NO
    lines at all (44 such project-class orders on the 18 Sep prod copy - `_lines_of` inner-
    joins `Product`, and a line whose product is gone falls out the same way) must still
    report the row as `no_line_for_item`, not silently drop the reason.

    `if not candidates: continue` used to sit inside `if narrow is not None:`, so the
    fallback's own final, UNNARROWED step always reached `_match_row` even against an empty
    candidate list and got a real reason back. R6's two-step `_attempt` moved that check to
    the loop's own top level, so it also skipped that final step here, leaving
    `match.reason` `None` forever - and `apply` unconditionally calls `raiser.raise_row`,
    which dereferences `match.core_line.id`: AttributeError, the whole upload rolled back,
    where main only ever reported `no_line_for_item`."""
    with world() as w:
        order = w.order()
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 0, result
        assert result["rows_line_not_found"] == 1, result
        assert [entry["reason"] for entry in result["line_not_found"]] == [
            "no_line_for_item"
        ], result["line_not_found"]


def test_ac_lp_16_equal_quantity_never_prefers_a_cancelled_line():
    """AC-LP-16 (blocker 2, review round 2, 19 Sep 2026). The equal-quantity step must not
    offer a CANCELLED line ahead of a bigger LIVE one that also fits: 412 such August-extract
    ghosts share a date with a bigger live sibling on the prod copy. D1 (a cancelled line
    ranks behind any live line that fits, in every pass) has to hold inside the equal step
    too, not just the ordinary one - a lone cancelled line still matches through the SECOND
    step exactly as today (AC-LP-8's third arm, kept green)."""
    with world() as w:
        order = w.order()
        w.line(
            order, qty_ordered="30", required_date=date(2026, 10, 1),
            line_status="cancelled",
        )
        live = w.line(order, qty_ordered="50", required_date=date(2026, 10, 1))
        data = sheet([
            (order.so_number, w.product.product_code, 30, date(2026, 10, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(live)
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "the equal-quantity step offered the cancelled line ahead of the live one"
        )


# test_ac_lp_16_equal_quantity_in_the_fallback (AC-LP-16, should-fix, review round 2,
# 19 Sep 2026) retired under R4, PLAN-board-received-stock-own-arrival, 21 Sep 2026: same
# ground as the two AC-LP-16 tests retired above - it pinned the fallback pass's own
# equal-quantity tie-break, unreachable now that the whole five-pass pick is gone. The
# `qty_exceeds_ordered` a mismatched positional pairing can still produce here is the same
# honestly-reported trade-off noted above, not a silent drop.


# --------------------------------------------------------------------------- #
# AC-LP-17: a cancelled line may only be taken by the fallback pass (R7)      #
# --------------------------------------------------------------------------- #


def test_ac_lp_17_live_line_in_a_later_pass_beats_a_cancelled_exact_date():
    """AC-LP-17 (R7, prod comparison workbook, 19 Sep 2026, SO324265 / CB2807-DIY). A
    cancelled line dated exactly the row's own date used to be the ONLY exact-date
    candidate, so pass 1 handed it the row before a live line elsewhere in the order - one
    the row's own citation names - was ever offered in a later pass. R7: a cancelled line
    may only be taken by the fallback, so pass 1 now finds nothing here and the citation
    pass (pass 3) lands the row on the live line instead."""
    with world() as w:
        order = w.order()
        w.line(
            order, qty_ordered="25", required_date=date(2026, 3, 2),
            line_status="cancelled",
        )
        live = _with_ref(
            w, w.line(order, qty_ordered="25", required_date=date(2026, 5, 2)), _ref(),
        )
        po, po_line = w.po_line(qty_ordered="25")
        _names(w, po_line, live.source_ref)
        data = sheet([
            (order.so_number, w.product.product_code, 25, date(2026, 3, 2),
             w.warehouse.warehouse_code, po.po_number),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(live)
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "the exact-date pass took the cancelled line before the citation pass ever "
            "offered the live one"
        )


def test_ac_lp_17_cancelled_line_never_wins_the_po_passes():
    """AC-LP-17 (R7, guards passes 2 and 3 specifically). A cancelled line in the row's own
    month, named by the row's own citation, sits beside a LIVE line in the SAME month that
    nothing names, on a different day than either the cancelled line or the row itself - so
    only the month-and-PO pass (2) or the PO-alone pass (3) could ever offer the cancelled
    line, and only the month-alone pass (4) can ever offer the live one. Before R7 dropped
    cancelled candidates from those two passes as well as the exact-date and month-alone
    ones, the cancelled line's citation match won it pass 2 outright, since the live line
    cites nothing to tie on there at all - this is exactly the gap a fix that only guards
    passes 1 and 4 would leave open."""
    with world() as w:
        order = w.order()
        cancelled = _with_ref(
            w,
            w.line(
                order, qty_ordered="40", required_date=date(2026, 6, 10),
                line_status="cancelled",
            ),
            _ref(),
        )
        live = w.line(order, qty_ordered="40", required_date=date(2026, 6, 20))
        po, po_line = w.po_line(qty_ordered="40")
        _names(w, po_line, cancelled.source_ref)
        data = sheet([
            (order.so_number, w.product.product_code, 40, date(2026, 6, 1),
             w.warehouse.warehouse_code, po.po_number),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(live)
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "a PO pass (2 or 3) took the cancelled line it cites over the live line "
            "nothing names"
        )


def test_ac_lp_17_no_citation_still_prefers_the_live_line():
    """AC-LP-17 (R7). Same two lines, but the row cites nothing at all: passes 1 to 4 never
    offer the cancelled line (R7) and never offer the live one either (neither its date nor
    its month matches the row's), so the fallback settles it - and there, D1's own rank
    still puts the live line ahead of the cancelled one."""
    with world() as w:
        order = w.order()
        w.line(
            order, qty_ordered="25", required_date=date(2026, 3, 2),
            line_status="cancelled",
        )
        live = w.line(order, qty_ordered="25", required_date=date(2026, 5, 2))
        data = sheet([
            (order.so_number, w.product.product_code, 25, date(2026, 3, 2),
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(live)
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "the fallback took the cancelled line over the live one"
        )


# test_ac_lp_17_lone_cancelled_line_still_matches (AC-LP-17, D1) retired under R4,
# PLAN-board-received-stock-own-arrival, 21 Sep 2026: it asserted the exact opposite of
# AC-S4-3 ("a closed or cancelled core line is never paired, even when it is the only qty
# fit") - D1's "a lone cancelled line still matches" is explicitly overturned. The identical
# shape (a lone cancelled line, nothing else in the order) is covered instead by
# `tests/scm/test_board_received_stock_s4_import_pairing.py::test_ac_s4_3_closed_or_cancelled_line_never_paired[cancelled]`,
# which asserts the row is refused `no_line_for_item`.
