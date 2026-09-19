"""The order inquiry sheet's line pick: exact date, then same month, then the sheet's PO.

Contract: `documentation/plans/scm/oi-sheet-line-pick-month-po-acceptance-criteria.md`,
AC-LP-1 to AC-LP-13, with `PLAN-oi-sheet-line-pick-month-po.md` sections 0 to 3 for the
promised behaviour. One test per criterion, named for it; AC-LP-12 gets two (the ledger
charge, and the legitimate split it must not break).

TEST-FIRST, written before the four-pass line pick exists. The red state is therefore
TODAY's single-pass `_rank_for` behaviour on `origin/main` - a row landing on the wrong
line, or the ledger NOT charging an already-raised line (review finding 9, 14 Sep, which
this slice reverses on purpose) - never an import typo or a fixture bug.

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

from datetime import date
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
# AC-LP-1 to AC-LP-3: the four passes, and file order not deciding them        #
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
# AC-LP-8, AC-LP-9: D1 restated for the four passes; ORDER BACK skips two of them #
# --------------------------------------------------------------------------- #


def test_ac_lp_8_cancelled_ranks_last_in_every_pass():
    """AC-LP-8. D1, restated for the four-pass pick: a cancelled line loses to any live
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
        assert row.delivery_date is None, "an ORDER BACK row should carry no delivery date"
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
    actually reads it. A first statement that already cites its own PO keeps it."""
    with world() as w:
        order = w.order()
        line_lent = _with_ref(
            w, w.line(order, qty_ordered="70", required_date=date(2026, 8, 1)), _ref(),
        )
        line_other = _with_ref(
            w, w.line(order, qty_ordered="70", required_date=date(2026, 10, 1)), _ref(),
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
    first time - no two rows ever end up on one line."""
    with world() as w:
        order, lines, pos = _uac_book(w)
        data = _uac_month_and_rollup(_uac_rows(w, order, pos))

        first = w.apply(data)
        assert first["rows_raised"] == 6, first
        first_landing = {row.delivery_date: str(row.so_line_id) for row in w.rows()}

        second = w.apply(data)

        assert second["rows_raised"] == 0, second
        assert second["rows_already_raised"] == 6, second
        assert len(w.rows()) == 6, "a re-upload raised a second row on some line"
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


def test_ac_lp_12_legitimate_split_still_lands_both_rows():
    """AC-LP-12 (split, AC-S1-2 kept). Two sheet rows that legitimately split ONE line's
    quantity - 100 plus 100 on a 200 line, neither of them already raised - still both
    land on it: the ledger charge above must not turn into a rule that only one row of a
    file may ever reach a line."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="200", required_date=D_OCT)
        data = sheet([
            (order.so_number, w.product.product_code, 100, D_OCT,
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 100, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        mirror = w.mirror_of(line)
        rows = w.rows()
        assert {str(row.so_line_id) for row in rows} == {str(mirror.id)}
        assert sorted(Decimal(str(row.qty)) for row in rows) == [
            Decimal("100"), Decimal("100"),
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
