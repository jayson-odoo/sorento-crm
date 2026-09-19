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


def test_ac_lp_1_exact_month_po_fallback_lands_every_2026_line():
    """AC-LP-1. Clean database, the UAC fixture: six rows raise, one per 2026 line - three
    of them (01-02, 05-04, 06-01) by an exact date match, one (04-01) by the same-month
    pass, two (02-02, 03-02) only by the sheet's own PO - and the 2025-12-01 line, bought
    for but never cited or dated by the sheet, carries none."""
    with world() as w:
        order, lines, pos = _uac_book(w)
        data = _uac_month_and_rollup(_uac_rows(w, order, pos))

        result = w.apply(data)

        assert result["rows_raised"] == 6, result
        assert result["rows_line_not_found"] == 0, result
        _assert_uac_landing(w, lines)


def test_ac_lp_2_exact_date_beats_file_order():
    """AC-LP-2. The two rows that can only be settled by the PO pass (02-02, 03-02) are
    stated in the FIRST tab, well ahead of the tab carrying the exact-date rows they could
    otherwise steal from under a single file-order pass - the landing does not move."""
    with world() as w:
        order, lines, pos = _uac_book(w)
        rows = _uac_rows(w, order, pos)
        data = book(
            FIRST=[rows["02-02"], rows["03-02"]],
            SECOND=[
                rows["01-02"], rows["04-01"], rows["05-04-month"], rows["06-01-month"],
            ],
            ROLLUP=[rows["05-04-rollup"], rows["06-01-rollup"]],
        )

        result = w.apply(data)

        assert result["rows_raised"] == 6, result
        _assert_uac_landing(w, lines)


def test_ac_lp_3_same_month_beats_file_order():
    """AC-LP-3. 02-02 - whose line pick can only be settled in the PO pass - is stated
    ahead of 04-01, whose own same-month pick is 04-02, and still does not take it."""
    with world() as w:
        order, lines, pos = _uac_book(w)
        rows = _uac_rows(w, order, pos)
        data = book(
            FIRST=[rows["02-02"]],
            SECOND=[rows["04-01"]],
            THIRD=[rows["01-02"], rows["03-02"], rows["05-04-month"], rows["06-01-month"]],
            ROLLUP=[rows["05-04-rollup"], rows["06-01-rollup"]],
        )

        result = w.apply(data)

        assert result["rows_raised"] == 6, result
        _assert_uac_landing(w, lines)


# --------------------------------------------------------------------------- #
# AC-LP-4 to AC-LP-6: the same-month tie-break, and the PO pass proper         #
# --------------------------------------------------------------------------- #


def test_ac_lp_4_same_month_two_lines_po_then_nearest_date():
    """AC-LP-4. Two lines fall in the same month as the row: the sheet's own PO decides
    between them - here the FARTHER line's PO is cited, which only a PO-aware tie-break can
    honour - and with neither bought by anything, the nearer date decides instead."""
    with world() as w:
        order = w.order()
        near = _with_ref(
            w, w.line(order, qty_ordered="80", required_date=date(2026, 4, 2)), _ref(),
        )
        far = _with_ref(
            w, w.line(order, qty_ordered="80", required_date=date(2026, 4, 20)), _ref(),
        )
        _po_near, po_line_near = w.po_line(qty_ordered="80")
        _names(w, po_line_near, near.source_ref)
        po_far, po_line_far = w.po_line(qty_ordered="80")
        _names(w, po_line_far, far.source_ref)
        data = sheet([
            (order.so_number, w.product.product_code, 80, date(2026, 4, 1),
             w.warehouse.warehouse_code, po_far.po_number),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(far)
        assert mirror is not None
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "the month pass used date proximity ahead of the sheet's own cited PO"
        )

    with world() as w:
        order = w.order()
        near = w.line(order, qty_ordered="80", required_date=date(2026, 4, 2))
        w.line(order, qty_ordered="80", required_date=date(2026, 4, 20))
        data = sheet([
            (order.so_number, w.product.product_code, 80, date(2026, 4, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(near)
        assert mirror is not None
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "with no PO to tell the two lines apart, the nearer date should have won"
        )

    with world() as w:
        # The row's own date (04-20) sits BEFORE the earlier line and AFTER the later one
        # is impossible with only two candidates, so instead the row sits BETWEEN them,
        # much closer to the later one - "earliest" and "nearest" disagree here, and only
        # "nearest" is the UAC's own rule.
        order = w.order()
        earliest_by_date = _with_ref(
            w, w.line(order, qty_ordered="80", required_date=date(2026, 4, 2)), _ref(),
        )
        nearest_by_proximity = _with_ref(
            w, w.line(order, qty_ordered="80", required_date=date(2026, 4, 25)), _ref(),
        )
        po_a, po_line_a = w.po_line(qty_ordered="80")
        _names(w, po_line_a, earliest_by_date.source_ref)
        po_b, po_line_b = w.po_line(qty_ordered="80")
        _names(w, po_line_b, nearest_by_proximity.source_ref)
        data = sheet([
            (order.so_number, w.product.product_code, 80, date(2026, 4, 20),
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(nearest_by_proximity)
        assert mirror is not None
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "the month pass picked the EARLIEST line rather than the NEAREST one"
        )


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
    """AC-LP-7. Every link AC-LP-1 writes is the book's own (`links_from_autocount`), and a
    row whose sheet PO differs from the book's own PO for the line it landed on links to
    the BOOK's document - the sheet's citation still pairs nothing (R2 kept)."""
    with world() as w:
        order, lines, pos = _uac_book(w)
        data = _uac_month_and_rollup(_uac_rows(w, order, pos))

        result = w.apply(data)

        assert result["rows_raised"] == 6, result
        assert result["links_from_autocount"] == 6, result
        rows_by_date = _rows_by_date(w)
        expected_po = {
            date(2026, 1, 2): pos["oct"],
            date(2026, 4, 1): pos["oct"],
            date(2026, 2, 2): pos["oct"],
            date(2026, 3, 2): pos["oct"],
            date(2026, 5, 4): pos["mar"],
            date(2026, 6, 1): pos["mar"],
        }
        for when, po_number in expected_po.items():
            row = rows_by_date[when][0]
            links = w.links(row)
            assert len(links) == 1, (when, [link.document for link in links])
            assert links[0].document == po_number, (when, links[0].document)

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
    line that fits - in the exact-date pass, in the PO pass - and, when it is the only
    line at all, is still taken rather than refusing the row."""
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

    with world() as w:
        order = w.order()
        lonely = _with_ref(
            w,
            w.line(order, qty_ordered="50", required_date=D_MATCH, line_status="cancelled"),
            _ref(),
        )
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_MATCH,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        assert result["rows_line_not_found"] == 0, result
        mirror = w.mirror_of(lonely)
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "a lone cancelled line still matches - it is where the history is (D1)"
        )


def test_ac_lp_9_order_back_lands_on_the_cited_po_line():
    """AC-LP-9. An ORDER BACK row carries no delivery date, so it takes part in no date
    pass and no month pass - it lands through the PO pass alone, even against a line dated
    EARLIER than the one its own citation names (proving the pick, not a date tie-break,
    decided it)."""
    with world() as w:
        order = w.order()
        cited = _with_ref(
            w, w.line(order, qty_ordered="80", required_date=date(2026, 7, 15)), _ref(),
        )
        earlier_uncited = _with_ref(
            w, w.line(order, qty_ordered="80", required_date=date(2026, 7, 1)), _ref(),
        )
        po_cited, po_line_cited = w.po_line(qty_ordered="80")
        _names(w, po_line_cited, cited.source_ref)
        po_other, po_line_other = w.po_line(qty_ordered="80")
        _names(w, po_line_other, earlier_uncited.source_ref)
        data = sheet([
            (order.so_number, w.product.product_code, 80, "ORDER BACK",
             w.warehouse.warehouse_code, po_cited.po_number),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        row = w.one_row()
        # Existing behaviour, not this lane's: an ORDER BACK row adopts the delivery date
        # of the line it lands on, so this is the CITED line's own required date.
        assert row.delivery_date == date(2026, 7, 15)
        mirror = w.mirror_of(cited)
        assert mirror is not None
        assert str(row.so_line_id) == str(mirror.id), (
            "an ORDER BACK row landed on the earlier-dated line instead of the one its "
            "own citation names"
        )


# --------------------------------------------------------------------------- #
# AC-LP-10: citation lending reaches the line pick                            #
# --------------------------------------------------------------------------- #


def test_ac_lp_10_restatement_lends_its_po_to_the_first_statement():
    """AC-LP-10. A restatement that carries a PO lends it to the first statement when that
    one carries none - and the line pick, which can only be settled by the PO pass here,
    actually reads it. A first statement that already cites its own PO keeps it.

    `line_lent` is dated LATER than `line_other` (2026-10-01 against 2026-08-01)
    deliberately: the fallback's own "earliest date" term would otherwise pick
    `line_lent` on its own, and this criterion would pass whether or not the lending ever
    reached the line pick at all.
    """
    with world() as w:
        order = w.order()
        line_lent = _with_ref(
            w, w.line(order, qty_ordered="70", required_date=date(2026, 10, 1)), _ref(),
        )
        line_other = _with_ref(
            w, w.line(order, qty_ordered="70", required_date=date(2026, 8, 1)), _ref(),
        )
        po_lent, po_line_lent = w.po_line(qty_ordered="70")
        _names(w, po_line_lent, line_lent.source_ref)
        po_other, po_line_other = w.po_line(qty_ordered="70")
        _names(w, po_line_other, line_other.source_ref)
        # The row's own date (Feb) is neither an exact match nor a same-month match for
        # EITHER candidate, so only the PO pass - and therefore only the lent citation -
        # can settle it.
        stated = (
            order.so_number, w.product.product_code, 70, date(2026, 2, 1),
            w.warehouse.warehouse_code, "",
        )
        restated = (
            order.so_number, w.product.product_code, 70, date(2026, 2, 1),
            w.warehouse.warehouse_code, po_lent.po_number,
        )
        outcome = ImportOutcome(None, persist=False)

        result = w.apply(book(MONTH=[stated], ROLLUP=[restated]), outcome=outcome)

        assert result["rows_raised"] == 1, result
        assert outcome.count_of("restates_an_instalment") == 1, outcome.breakdown()
        assert len(w.rows()) == 1, "lending changed the duplicate count"
        mirror = w.mirror_of(line_lent)
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "the restatement's citation never reached the line pick"
        )

    with world() as w:
        order = w.order()
        line_first = _with_ref(
            w, w.line(order, qty_ordered="70", required_date=date(2026, 8, 1)), _ref(),
        )
        line_second = _with_ref(
            w, w.line(order, qty_ordered="70", required_date=date(2026, 10, 1)), _ref(),
        )
        po_first, po_line_first = w.po_line(qty_ordered="70")
        _names(w, po_line_first, line_first.source_ref)
        po_second, po_line_second = w.po_line(qty_ordered="70")
        _names(w, po_line_second, line_second.source_ref)
        stated = (
            order.so_number, w.product.product_code, 70, date(2026, 2, 1),
            w.warehouse.warehouse_code, po_first.po_number,
        )
        restated = (
            order.so_number, w.product.product_code, 70, date(2026, 2, 1),
            w.warehouse.warehouse_code, po_second.po_number,
        )

        result = w.apply(book(MONTH=[stated], ROLLUP=[restated]))

        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(line_first)
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "a first statement that already cited its own PO lost it to the "
            "restatement's citation"
        )


# --------------------------------------------------------------------------- #
# AC-LP-11: re-upload reports the SAME line every time                        #
# --------------------------------------------------------------------------- #


def test_ac_lp_11_reupload_reports_the_same_line_every_time():
    """AC-LP-11. Re-upload of the same file after AC-LP-1: nothing new raises, all six
    dates report `rows_already_raised`, and every one names the SAME line it landed on the
    first time - no two rows ever end up on one line.

    `_assert_uac_landing` is asserted after BOTH applies, not just the counts: the UAC's
    own fixture has a line (2025-12-01) that a wrong line pick lands on instead of one of
    the six named lines, and a wrong pick there still leaves the counts alone (still six
    raised, still zero already-raised the second time) - only the landing map catches it.
    """
    with world() as w:
        order, lines, pos = _uac_book(w)
        data = _uac_month_and_rollup(_uac_rows(w, order, pos))

        first = w.apply(data)
        assert first["rows_raised"] == 6, first
        _assert_uac_landing(w, lines)
        first_landing = {row.delivery_date: str(row.so_line_id) for row in w.rows()}

        second = w.apply(data)

        assert second["rows_raised"] == 0, second
        assert second["rows_already_raised"] == 6, second
        assert len(w.rows()) == 6, "a re-upload raised a second row on some line"
        _assert_uac_landing(w, lines)
        second_landing = {row.delivery_date: str(row.so_line_id) for row in w.rows()}
        assert second_landing == first_landing, (
            "the re-upload reported a different line than the first upload did"
        )


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


def test_ac_lp_12_bumped_row_takes_the_next_free_line():
    """AC-LP-12 (bumped, re-upload = first upload). Line A is already raised; the sheet's
    first row (150) lands there and charges the ledger, leaving only 50 - too little for
    the second row's 100 - so the second row is bumped onto line B, the next free line
    that fits.

    This is exactly the landing a FIRST upload of this sheet would give against a clean
    line A: charging the ledger on an already-raised line (AC-LP-12's own "charge" half)
    is what makes a RE-upload land the rest of its rows the same way the first upload
    would have, rather than silently absorbing every same-item row onto the one already-
    raised line no matter how many the file states.
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

        assert result["rows_already_raised"] == 1, result
        assert result["rows_raised"] == 1, result
        assert result["rows_line_not_found"] == 0, result
        mirror_b = w.mirror_of(line_b)
        assert mirror_b is not None
        bumped = [row for row in w.rows() if Decimal(str(row.qty)) == Decimal("100")]
        assert len(bumped) == 1, [str(row.qty) for row in w.rows()]
        assert str(bumped[0].so_line_id) == str(mirror_b.id), (
            "the bumped row did not land on the next free line"
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


def test_ac_lp_13_preview_and_apply_land_every_row_the_same():
    """AC-LP-13. `preview` forecasts exactly what `apply` commits: a second `preview` after
    the upload reports every one of the six lines as already raised, nothing left over and
    nothing double-counted - which only holds if both runs picked the SAME line for every
    row (the result carries no per-row line id, so this is the strongest check available
    through the public contract alone)."""
    with world() as w:
        order, lines, pos = _uac_book(w)
        data = _uac_month_and_rollup(_uac_rows(w, order, pos))

        before = w.preview(data)
        assert before["rows_raised"] == 6, before
        assert before["rows_already_raised"] == 0, before

        applied = w.apply(data)
        assert applied["rows_raised"] == 6, applied
        _assert_uac_landing(w, lines)

        after = w.preview(data)
        assert after["rows_raised"] == 0, after
        assert after["rows_already_raised"] == 6, after
        assert after["rows_line_not_found"] == 0, after


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


def test_ac_lp_14_sheet_po_outranks_same_month():
    """AC-LP-14 (R4, 19 Sep 2026, prod C-FH14 / SO324265). The 04-01 row cites PO B while
    the only line in its own month books PO A - under the old single month pass that line
    still won it (nothing outranked "same month" for a citation-less tie), stealing it from
    the row that actually cites A and cascading every later row onto the wrong line: 02-02
    finds its A line taken and slides to 05-02, 03-02 finds NOTHING free and falls all the
    way back to the 2025-12-01 line the sheet never cites. Stating the 04-01 row FIRST in
    the file, ahead of the exact-date rows it could otherwise starve, proves the outcome is
    the pass order, not file order (AC-LP-2/3's own point, restated for this defect)."""
    with world() as w:
        order = w.order()
        line_dec = _with_ref(
            w, w.line(order, qty_ordered="130", required_date=date(2025, 12, 1)), _ref(),
        )
        line_jan = _with_ref(
            w, w.line(order, qty_ordered="130", required_date=date(2026, 1, 2)), _ref(),
        )
        line_apr = _with_ref(
            w, w.line(order, qty_ordered="130", required_date=date(2026, 4, 2)), _ref(),
        )
        line_may_2 = _with_ref(
            w, w.line(order, qty_ordered="130", required_date=date(2026, 5, 2)), _ref(),
        )
        line_may_1 = _with_ref(
            w, w.line(order, qty_ordered="130", required_date=date(2026, 5, 1)), _ref(),
        )

        po_x, po_line_x = w.po_line(qty_ordered="130", number=_po_number("202508"))
        _names(w, po_line_x, line_dec.source_ref)

        po_a, po_line_a = w.po_line(qty_ordered="130", number=_po_number("202509"))
        _names(w, po_line_a, line_jan.source_ref)
        _sibling_po_line(w, po_a, qty_ordered="130", from_so_line_ref=line_apr.source_ref)
        _sibling_po_line(w, po_a, qty_ordered="130", from_so_line_ref=line_may_2.source_ref)

        po_b, po_line_b = w.po_line(qty_ordered="130", number=_po_number("202510"))
        _names(w, po_line_b, line_may_1.source_ref)

        p, loc, so = w.product.product_code, w.warehouse.warehouse_code, order.so_number
        # The 04-01 row stated FIRST, ahead of the three exact-date rows it could otherwise
        # starve if the outcome depended on file order rather than the pass order.
        data = sheet([
            (so, p, 130, date(2026, 4, 1), loc, po_b.po_number),
            (so, p, 130, date(2026, 1, 2), loc, po_a.po_number),
            (so, p, 130, date(2026, 2, 2), loc, po_a.po_number),
            (so, p, 130, date(2026, 3, 2), loc, po_a.po_number),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 4, result
        assert result["rows_line_not_found"] == 0, result
        rows_by_date = _rows_by_date(w)
        _assert_lands_on(w, rows_by_date, date(2026, 1, 2), line_jan)
        _assert_lands_on(w, rows_by_date, date(2026, 2, 2), line_apr)
        _assert_lands_on(w, rows_by_date, date(2026, 3, 2), line_may_2)
        _assert_lands_on(w, rows_by_date, date(2026, 4, 1), line_may_1)
        december_mirror = w.mirror_of(line_dec)
        assert december_mirror is None or not any(
            str(row.so_line_id) == str(december_mirror.id) for row in w.rows()
        ), "a row landed on the 2025-12-01 line the sheet never cites"


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


def test_ac_lp_15_lending_goes_to_the_matching_repeat():
    """AC-LP-15 (lending). The month tab's two identical rows are two SEPARATE instructions
    (this criterion's own point) - so when the roll-up restates them with two DIFFERENT
    purchase orders, each lent citation must reach the SAME-POSITION month instruction, not
    either one at random or both landing on the first. Neither line is an exact-date or
    same-month match for the row's own date, so only the PO pass can settle either - proving
    the lending, not a date tie, decided it. A THIRD, decoy line the book also bought for
    stands ready to catch a citation-less instruction via the plain fallback (earliest date
    among bought lines): if either lending went to the wrong position, the row it starved
    would land on the decoy instead of its own line, which the closing assertion catches."""
    with world() as w:
        order = w.order()
        line_x = _with_ref(
            w, w.line(order, qty_ordered="25", required_date=date(2026, 7, 1)), _ref(),
        )
        line_y = _with_ref(
            w, w.line(order, qty_ordered="25", required_date=date(2026, 9, 1)), _ref(),
        )
        decoy = _with_ref(
            w, w.line(order, qty_ordered="25", required_date=date(2026, 1, 1)), _ref(),
        )
        po_x, po_line_x = w.po_line(qty_ordered="25", number=_po_number("202508"))
        _names(w, po_line_x, line_x.source_ref)
        po_y, po_line_y = w.po_line(qty_ordered="25", number=_po_number("202509"))
        _names(w, po_line_y, line_y.source_ref)
        po_decoy, po_line_decoy = w.po_line(qty_ordered="25", number=_po_number("202510"))
        _names(w, po_line_decoy, decoy.source_ref)

        stated = (
            order.so_number, w.product.product_code, 25, date(2026, 2, 1),
            w.warehouse.warehouse_code, "",
        )
        restated_x = (
            order.so_number, w.product.product_code, 25, date(2026, 2, 1),
            w.warehouse.warehouse_code, po_x.po_number,
        )
        restated_y = (
            order.so_number, w.product.product_code, 25, date(2026, 2, 1),
            w.warehouse.warehouse_code, po_y.po_number,
        )
        data = book(MONTH=[stated, stated], ROLLUP=[restated_x, restated_y])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        rows = w.rows()
        assert len(rows) == 2, [str(r.qty) for r in rows]
        mirror_x, mirror_y = w.mirror_of(line_x), w.mirror_of(line_y)
        assert {str(r.so_line_id) for r in rows} == {str(mirror_x.id), str(mirror_y.id)}, (
            "a citation lent to the wrong position starved one instruction, which fell to "
            "the plain fallback and landed on the decoy line instead of its own"
        )


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


def test_ac_lp_16_equal_quantity_line_before_a_bigger_one():
    """AC-LP-16 (R6, prod CB2805A-DIY / SO324265, 19 Sep 2026). Two lines share ONE exact
    date, qty 230 (created FIRST, so it wins today's created-at tie-break) and qty 150; the
    sheet's own 150 row is stated FIRST, ahead of the 230 row. `_rank_for` carries no
    quantity term at all, so today the bigger line takes the 150 row on nothing but that
    tie-break, and the 230 row then finds every line too small or already spent and reads
    `qty_exceeds_ordered` - CB2805A-DIY's own defect (whole order, 18 Sep prod copy: 184
    instructions, only 180 landed)."""
    with world() as w:
        order = w.order()
        line_230 = _born_at(
            w, w.line(order, qty_ordered="230", required_date=date(2026, 1, 2)),
            datetime(2026, 6, 1, 8, 0, 0),
        )
        line_150 = _born_at(
            w, w.line(order, qty_ordered="150", required_date=date(2026, 1, 2)),
            datetime(2026, 6, 1, 9, 0, 0),
        )
        data = sheet([
            (order.so_number, w.product.product_code, 150, date(2026, 1, 2),
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 230, date(2026, 1, 2),
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        assert result["rows_line_not_found"] == 0, result
        rows_by_qty = {Decimal(str(row.qty)): row for row in w.rows()}
        assert len(rows_by_qty) == 2, [str(r.qty) for r in w.rows()]
        assert str(rows_by_qty[Decimal("150")].so_line_id) == str(
            w.mirror_of(line_150).id
        ), "the 150 row did not land on the 150 line"
        assert str(rows_by_qty[Decimal("230")].so_line_id) == str(
            w.mirror_of(line_230).id
        ), "the 230 row did not land on the 230 line"


def test_ac_lp_16_equal_quantity_wins_the_po_pass_too():
    """AC-LP-16 (PO pass). The same defect, reached through pass 3 instead of pass 1: two
    lines share one month-mismatched date and one book PO, so only the citation pass can
    settle either. `_rank_for_po` carries no quantity term either, so the tie-break
    (earliest date, then oldest, then id) alone would hand ONE line to both rows and starve
    the other - the equal-quantity step has to settle it first."""
    with world() as w:
        order = w.order()
        line_230 = _with_ref(
            w,
            _born_at(
                w, w.line(order, qty_ordered="230", required_date=date(2026, 5, 2)),
                datetime(2026, 6, 1, 8, 0, 0),
            ),
            _ref(),
        )
        line_150 = _with_ref(
            w,
            _born_at(
                w, w.line(order, qty_ordered="150", required_date=date(2026, 5, 2)),
                datetime(2026, 6, 1, 9, 0, 0),
            ),
            _ref(),
        )
        po_a, po_line_230 = w.po_line(qty_ordered="230", number=_po_number("202509"))
        _names(w, po_line_230, line_230.source_ref)
        _sibling_po_line(w, po_a, qty_ordered="150", from_so_line_ref=line_150.source_ref)
        data = sheet([
            (order.so_number, w.product.product_code, 150, date(2026, 2, 2),
             w.warehouse.warehouse_code, po_a.po_number),
            (order.so_number, w.product.product_code, 230, date(2026, 2, 2),
             w.warehouse.warehouse_code, po_a.po_number),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        assert result["rows_line_not_found"] == 0, result
        rows_by_qty = {Decimal(str(row.qty)): row for row in w.rows()}
        assert len(rows_by_qty) == 2, [str(r.qty) for r in w.rows()]
        assert str(rows_by_qty[Decimal("150")].so_line_id) == str(
            w.mirror_of(line_150).id
        ), "the 150 row did not land on the 150 line"
        assert str(rows_by_qty[Decimal("230")].so_line_id) == str(
            w.mirror_of(line_230).id
        ), "the 230 row did not land on the 230 line"


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


def test_ac_lp_16_equal_quantity_in_the_fallback():
    """AC-LP-16 (should-fix, review round 2, 19 Sep 2026). The fallback pass runs the SAME
    two-step `_attempt` every other pass does: neither line shares the row's date or month,
    and neither row cites anything, so only pass 5 can ever place either. Pinned here so a
    future change that scopes the equal-quantity step OUT of the fallback specifically has
    somewhere to go red - every other test in this file stays green with it removed from
    pass 5 alone."""
    with world() as w:
        order = w.order()
        line_230 = w.line(order, qty_ordered="230", required_date=date(2026, 3, 1))
        line_150 = w.line(order, qty_ordered="150", required_date=date(2026, 4, 1))
        data = sheet([
            (order.so_number, w.product.product_code, 150, date(2026, 7, 5),
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 230, date(2026, 7, 5),
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        rows_by_qty = {Decimal(str(row.qty)): row for row in w.rows()}
        assert len(rows_by_qty) == 2, [str(r.qty) for r in w.rows()]
        assert str(rows_by_qty[Decimal("150")].so_line_id) == str(
            w.mirror_of(line_150).id
        ), "the 150 row did not land on the 150 line"
        assert str(rows_by_qty[Decimal("230")].so_line_id) == str(
            w.mirror_of(line_230).id
        ), "the 230 row did not land on the 230 line"


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


def test_ac_lp_17_lone_cancelled_line_still_matches():
    """AC-LP-17 (D1 kept). With no live line anywhere in the order, the cancelled line is
    still where the history is: the fallback still takes it rather than refusing the row,
    exactly as before R7."""
    with world() as w:
        order = w.order()
        lonely = w.line(
            order, qty_ordered="25", required_date=date(2026, 3, 2),
            line_status="cancelled",
        )
        data = sheet([
            (order.so_number, w.product.product_code, 25, date(2026, 3, 2),
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        assert result["rows_line_not_found"] == 0, result
        mirror = w.mirror_of(lonely)
        assert str(w.one_row().so_line_id) == str(mirror.id), (
            "a lone cancelled line still matches - it is where the history is (D1)"
        )
