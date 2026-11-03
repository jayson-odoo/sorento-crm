"""PS-QUOTE-MATRIX output: the PDF HTML and the Excel workbook of an issue with a grid scope.

Written BEFORE the implementation (Phase 2, test-first). Contract section "PDF / Excel" of
``documentation/plans/project-sales/PLAN-ps-quote-matrix-02nov.md``.

World (see ``grid_world`` in ``test_quote_matrix_service.py``): scope UNIT is a grid with headers
TYPE A (1 BH, KITCHEN), TYPE B (2 BH, KITCHEN) and BREAK TANK (no cols), one floor trap row at 45.00
(120 + 120 | 500 + 250) and one sink row at 100.00 (2 in TYPE A / 1 BH). Scope GUARD HOUSE is plain
(5 x 80.00).

    floor trap: TYPE A 240 / 10,800.00, TYPE B 750 / 33,750.00, total qty 990, amount 44,550.00
    sink:       TYPE A 2 / 200.00, total qty 2, amount 200.00
    footer:     leaves 122 120 500 250, TYPE A 242 / 11,000.00, TYPE B 750 / 33,750.00,
                total qty 992, scope total 44,750.00
"""
from __future__ import annotations

import re
from io import BytesIO

from ._pg_fixture import blank_session
from .test_project_proposal_quotation import MARKER, _issue, _price, _setup
from .test_quote_matrix_service import COLUMNS, grid_world, set_grid

from app.services import quotation_columns

# Today's printed column set for a scope with no photo: the one shared definition
# (`quotation_columns`, QUOTE-SIGN-COLUMNS) minus PRODUCT IMAGE.
_TODAY_NO_IMAGE = [
    label for key, label in quotation_columns.COLUMNS if key != quotation_columns.IMAGE
]

UNIT_LABEL = f"{MARKER} Townhouse"
GUARD_LABEL = f"{MARKER} GUARD HOUSE"


# ------------------------------------------------------------------ html helpers


def _strip(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def _scope_block(html: str, label: str) -> str:
    for block in html.split('<div class="scope">')[1:]:
        if label in block.split("</div>")[0]:
            return block
    raise AssertionError(f"no scope block labelled {label!r}")


def _thead_rows(block: str):
    """[[(attrs, text), ...] per header row]"""
    thead = re.search(r"<thead>(.*?)</thead>", block, re.S)
    assert thead, "scope table has no thead"
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", thead.group(1), re.S)
    return [
        [(attrs, _strip(text)) for attrs, text in re.findall(r"<th([^>]*)>(.*?)</th>", row, re.S)]
        for row in rows
    ]


def _tds(block: str, section: str):
    part = re.search(rf"<{section}[^>]*>(.*?)</{section}>", block, re.S)
    assert part, f"scope table has no {section}"
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", part.group(1), re.S)
    return [[_strip(t) for t in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)] for row in rows]


def _html(db, record):
    from app.services import project_quotation_pdf_service as qpdf

    return qpdf.build_issue_html(db, record)


# ------------------------------------------------------------------ PDF


def test_pdf_a_plain_scope_prints_exactly_todays_columns_beside_a_grid_scope():
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        w = grid_world(db)
        block = _scope_block(_html(db, w.record), GUARD_LABEL)
        rows = _thead_rows(block)
        assert len(rows) == 1
        today = list(_TODAY_NO_IMAGE)
        assert [text for _, text in rows[0]] == today
        assert not any("rowspan" in attrs or "colspan" in attrs for attrs, _ in rows[0])
        assert "vert" not in block.split("<tbody")[0]
        footer = _tds(block, "tfoot")
        assert len(footer) == 1
        assert footer[0][0] == "TOTAL" and footer[0][-1] == "400.00"


def test_pdf_a_grid_scope_has_a_two_row_header_with_headers_over_leaves():
    with blank_session() as db:
        w = grid_world(db)
        block = _scope_block(_html(db, w.record), UNIT_LABEL)
        top, bottom = _thead_rows(block)

        spans = {text: attrs for attrs, text in top}
        assert 'colspan="2"' in spans["TYPE A"].replace("'", '"')
        assert 'colspan="2"' in spans["TYPE B"].replace("'", '"')
        # A header with no cols is one column that spans both header rows.
        assert 'rowspan="2"' in spans["BREAK TANK"].replace("'", '"')
        # The leaf labels sit in the second row, in order.
        assert [text for _, text in bottom][:4] == ["1 BH", "KITCHEN", "2 BH", "KITCHEN"]
        # The plain columns are kept and span both rows.
        for name in ("ITEM", "DESCRIPTION", "PRODUCT CODE", "UNIT RATE (RM)"):
            assert 'rowspan="2"' in spans[name].replace("'", '"'), name


def test_pdf_a_grid_scope_has_pair_total_qty_and_grand_total_columns_in_order():
    with blank_session() as db:
        w = grid_world(db)
        top, bottom = _thead_rows(_scope_block(_html(db, w.record), UNIT_LABEL))
        every = [text for _, text in top] + [text for _, text in bottom]
        # TYPE A and TYPE B each get a pair (two headers, two cols each); BREAK TANK does not.
        assert every.count("QTY") == 2
        assert every.count("AMOUNT (RM)") == 2
        assert every.count("TOTAL QTY") == 1
        assert [text for _, text in top][-1] == "GRAND TOTAL"


def test_pdf_a_grid_row_prints_cells_pairs_total_qty_and_grand_total():
    with blank_session() as db:
        w = grid_world(db)
        rows = _tds(_scope_block(_html(db, w.record), UNIT_LABEL), "tbody")
        trap = next(r for r in rows if "45.00" in r)
        for expected in ("120", "500", "250", "240", "10,800.00", "750", "33,750.00", "990", "44,550.00"):
            assert expected in trap, (expected, trap)
        sink = next(r for r in rows if "100.00" in r and "200.00" in r)
        assert "2" in sink and "200.00" in sink


def test_pdf_a_grid_scope_has_footer_rows_total_qty_and_total_rm():
    with blank_session() as db:
        w = grid_world(db)
        footer = _tds(_scope_block(_html(db, w.record), UNIT_LABEL), "tfoot")
        flat = [cell for row in footer for cell in row]
        assert "TOTAL QTY" in flat
        assert "TOTAL (RM)" in flat
        qty_row = next(r for r in footer if "TOTAL QTY" in r)
        for expected in ("122", "120", "500", "250", "242", "750", "992"):
            assert expected in qty_row, (expected, qty_row)
        rm_row = next(r for r in footer if "TOTAL (RM)" in r)
        for expected in ("11,000.00", "33,750.00"):
            assert expected in rm_row, (expected, rm_row)
        assert "44,750.00" in flat  # the scope total row, as today


def _one_grid(db, leaf_count: int):
    company_id, owner, product, project, document, scope = _setup(db)
    line = _price(db, scope, product, owner, "10.00", 1)
    from app.services import project_quotation_service as quotes

    columns = [
        {
            "key": "h1",
            "label": "WIDE",
            "cols": [{"key": f"c{i}", "label": f"R{i}"} for i in range(leaf_count)],
        }
    ]
    set_grid(db, quotes.current_version(db, scope.id), columns, [(line, {"c0": "1.00"})])
    record = _issue(db, document, owner)
    db.flush()
    return record


def test_pdf_leaf_headings_are_vertical_only_when_the_scope_has_more_than_12_leaves():
    with blank_session() as db:
        narrow = _thead_rows(_scope_block(_html(db, _one_grid(db, 12)), UNIT_LABEL))
        assert not any("vert" in attrs for row in narrow for attrs, _ in row)
    with blank_session() as db:
        wide = _thead_rows(_scope_block(_html(db, _one_grid(db, 13)), UNIT_LABEL))
        vertical = [text for row in wide for attrs, text in row if "vert" in attrs]
        assert vertical == [f"R{i}" for i in range(13)]


def test_pdf_a_scope_whose_columns_were_removed_prints_as_a_plain_scope():
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        company_id, owner, product, project, document, scope = _setup(db)
        _price(db, scope, product, owner, "10.00", 3)
        record = _issue(db, document, owner)
        rows = _thead_rows(_scope_block(_html(db, record), UNIT_LABEL))
        assert [text for _, text in rows[0]] == [
            label for key, label in quotation_columns.COLUMNS if key != quotation_columns.IMAGE
        ]
        assert len(rows) == 1


# ------------------------------------------------------------------ Excel


def _workbook(db, record):
    from openpyxl import load_workbook

    from app.services import project_quotation_excel_service as qxl

    buffer = BytesIO()
    qxl.build_issue_workbook(db, record).save(buffer)
    buffer.seek(0)
    return load_workbook(buffer)  # formulas stay as text


def _find(sheet, text, *, min_row=1, column=None):
    for row in sheet.iter_rows(min_row=min_row):
        for cell in row:
            if cell.value == text and (column is None or cell.column == column):
                return cell
    raise AssertionError(f"{text!r} not found on {sheet.title!r}")


def _merged_at(sheet, cell):
    for rng in sheet.merged_cells.ranges:
        if rng.min_row <= cell.row <= rng.max_row and rng.min_col <= cell.column <= rng.max_col:
            return rng
    return None


def test_excel_a_plain_scope_keeps_todays_header_and_has_no_merges():
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        w = grid_world(db)
        book = _workbook(db, w.record)
        sheet = book.worksheets[1]
        item = _find(sheet, "ITEM")
        header = [c.value for c in sheet[item.row] if c.value is not None]
        assert header == _TODAY_NO_IMAGE
        assert not sheet.merged_cells.ranges


def test_excel_a_grid_scope_merges_each_header_over_its_leaves_and_labels_the_leaves():
    with blank_session() as db:
        w = grid_world(db)
        sheet = _workbook(db, w.record).worksheets[0]
        type_a = _find(sheet, "TYPE A")
        type_b = _find(sheet, "TYPE B")
        tank = _find(sheet, "BREAK TANK")
        a_range = _merged_at(sheet, type_a)
        b_range = _merged_at(sheet, type_b)
        assert a_range is not None and (a_range.min_row, a_range.max_row) == (type_a.row, type_a.row)
        assert a_range.max_col - a_range.min_col + 1 == 2
        assert b_range is not None and b_range.max_col - b_range.min_col + 1 == 2
        # A header with no cols spans both header rows in one column.
        t_range = _merged_at(sheet, tank)
        assert t_range is not None
        assert (t_range.min_row, t_range.max_row) == (type_a.row, type_a.row + 1)
        assert t_range.min_col == t_range.max_col
        # Leaf labels sit one row below, under the header's own columns.
        below = [sheet.cell(row=type_a.row + 1, column=c).value for c in range(a_range.min_col, b_range.max_col + 1)]
        assert below == ["1 BH", "KITCHEN", "2 BH", "KITCHEN"]


def test_excel_a_grid_row_holds_numbers_in_cells_and_sum_formulas_in_totals():
    with blank_session() as db:
        w = grid_world(db)
        sheet = _workbook(db, w.record).worksheets[0]
        type_a = _find(sheet, "TYPE A")
        a_range = _merged_at(sheet, type_a)
        first_leaf = a_range.min_col
        trap_row = _find(sheet, 45, min_row=type_a.row + 2).row
        values = [sheet.cell(row=trap_row, column=first_leaf + i).value for i in range(4)]
        assert values == [120, 120, 500, 250]  # numbers, not strings

        total_qty = _find(sheet, "TOTAL QTY", min_row=type_a.row)
        assert total_qty.row in (type_a.row, type_a.row + 1)
        cell = sheet.cell(row=trap_row, column=total_qty.column)
        assert isinstance(cell.value, str) and cell.value.startswith("=") and "SUM(" in cell.value

        # Pair QTY (one per pair header) is a SUM formula over the header's own cells.
        pair_qty_cols = [
            c.column
            for row in sheet.iter_rows(min_row=type_a.row, max_row=type_a.row + 1)
            for c in row
            if c.value == "QTY"
        ]
        assert len(pair_qty_cols) == 2
        for column in pair_qty_cols:
            value = sheet.cell(row=trap_row, column=column).value
            assert isinstance(value, str) and value.startswith("=SUM(")
        pair_amount_cols = [
            c.column
            for row in sheet.iter_rows(min_row=type_a.row, max_row=type_a.row + 1)
            for c in row
            if c.value == "AMOUNT (RM)"
        ]
        assert len(pair_amount_cols) == 2
        for column in pair_amount_cols:
            value = sheet.cell(row=trap_row, column=column).value
            assert isinstance(value, str) and value.startswith("=")

        grand = _find(sheet, "GRAND TOTAL", min_row=type_a.row)
        grand_value = sheet.cell(row=trap_row, column=grand.column).value
        assert isinstance(grand_value, str) and grand_value.startswith("=")


def test_excel_a_grid_scope_has_footer_rows_with_sum_formulas():
    with blank_session() as db:
        w = grid_world(db)
        sheet = _workbook(db, w.record).worksheets[0]
        type_a = _find(sheet, "TYPE A")
        footer_qty = _find(sheet, "TOTAL QTY", min_row=type_a.row + 2)
        footer_rm = _find(sheet, "TOTAL (RM)", min_row=type_a.row + 2)
        a_range = _merged_at(sheet, type_a)
        for cell_row in (footer_qty.row,):
            for offset in range(4):
                value = sheet.cell(row=cell_row, column=a_range.min_col + offset).value
                assert isinstance(value, str) and value.startswith("=SUM("), (offset, value)
        # Per pair AMOUNT footer sits on the TOTAL (RM) row.
        amount_cols = [
            c.column
            for row in sheet.iter_rows(min_row=type_a.row, max_row=type_a.row + 1)
            for c in row
            if c.value == "AMOUNT (RM)"
        ]
        for column in amount_cols:
            value = sheet.cell(row=footer_rm.row, column=column).value
            assert isinstance(value, str) and value.startswith("=")
