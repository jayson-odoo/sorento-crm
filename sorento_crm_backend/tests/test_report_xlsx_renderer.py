"""The workbook the export writes (AC-D2, AC-D3, AC-D4 - the S2 skeleton).

S2 renders ONE summary sheet plus ONE detail sheet; S4 splits the detail into a sheet per
month and diffs the result against the client's 2025 workbook. What is settled here is the
shape S4 builds on: the title block, header groups as merged cells, and - the one that
matters - **totals written as VALUES**. The workbook the client keeps by hand uses SUM
formulas; ours writes what the engine computed, so Excel cannot disagree with the screen.

Run: pytest tests/test_report_xlsx_renderer.py -q
"""
from __future__ import annotations

from io import BytesIO

import pytest

from tests import _report_fixture as fixture
from tests._pg_fixture import pg_session

SUMMARY = "SUMMARY"
DETAIL = "Orders"


@pytest.fixture
def workbook():
    from openpyxl import load_workbook

    from app.services.reports import engine
    from app.services.reports.xlsx_renderer import render_workbook

    with pg_session() as db:
        fixture.create_table(db)
        definition = fixture.definition()
        result = engine.run(db, definition, definition.default_view["params"], cap=False)
        content = render_workbook(definition, result)

    assert isinstance(content, (bytes, bytearray))
    return load_workbook(BytesIO(content))


def _merged(sheet, anchor: str) -> str:
    """The merged range a top-left cell anchors, as a string, or "" if it is not merged."""
    for cell_range in sheet.merged_cells.ranges:
        if str(cell_range).startswith(f"{anchor}:"):
            return str(cell_range)
    return ""


def test_the_summary_sheet_comes_first(workbook):
    assert workbook.sheetnames == [SUMMARY, DETAIL]


def test_every_sheet_opens_with_the_title_block(workbook):
    """AC-D2: whose report this is, what it is, over what period, for which department."""
    for name, period_label in ((SUMMARY, "Jan'26 to Dec'26"), (DETAIL, "Jan'26 to Dec'26")):
        sheet = workbook[name]
        assert sheet["A1"].value == "ZZT Sdn Bhd"
        assert sheet["A2"].value == "Scratch orders"
        assert sheet["A3"].value == period_label
        assert sheet["A4"].value == "Scratch"


def test_the_summary_merges_each_column_value_over_its_measures(workbook):
    """AC-D3: one merged month header spanning Amount and Fee."""
    sheet = workbook[SUMMARY]
    assert sheet["A6"].value == "Agent"
    assert sheet["B6"].value == "Jan'26"
    assert _merged(sheet, "B6") == "B6:C6"
    assert sheet["B7"].value == "Amount"
    assert sheet["C7"].value == "Fee"


def test_the_summary_carries_a_row_per_row_value(workbook):
    sheet = workbook[SUMMARY]
    assert sheet["A8"].value == "Alice"
    assert sheet["A9"].value == "Bob"
    assert float(sheet["B8"].value) == 1250.25
    assert sheet["B8"].data_type == "n"


def test_a_missing_cell_is_blank_not_zero(workbook):
    """Bob has nothing in January; the workbook prints nothing, as the client's does."""
    sheet = workbook[SUMMARY]
    assert sheet["B9"].value is None


def test_the_grand_total_row_holds_values_not_formulas(workbook):
    """AC-D4. A formula lets Excel recompute a different answer from the screen's."""
    sheet = workbook[SUMMARY]
    total_row = sheet.max_row
    assert sheet.cell(row=total_row, column=1).value == "GRAND TOTAL"
    values = [
        sheet.cell(row=total_row, column=col).value
        for col in range(2, sheet.max_column + 1)
    ]
    assert not any(isinstance(v, str) and v.startswith("=") for v in values)
    assert float(values[-2]) == 1750.24  # the amount grand total, before the fee
    assert float(values[-1]) == 36.51


def test_money_cells_carry_a_thousands_and_two_decimal_format(workbook):
    assert workbook[SUMMARY]["B8"].number_format == "#,##0.00"


def test_the_detail_sheet_lists_the_rows_under_their_headers(workbook):
    sheet = workbook[DETAIL]
    headers = [c.value for c in sheet[7]]
    assert headers[0] == "Order no"
    assert "Amount" in headers
    assert sheet["A8"].value == "Z-001"


def test_the_detail_sheet_merges_the_tick_group_header(workbook):
    """AC-D3: "Delivery year" spans its 2026 and 2027 tick columns."""
    sheet = workbook[DETAIL]
    group_row = [c.value for c in sheet[6]]
    assert "Delivery year" in group_row
    anchor = sheet.cell(row=6, column=group_row.index("Delivery year") + 1)
    assert _merged(sheet, anchor.coordinate)


def test_the_detail_sheet_totals_its_measures_as_values(workbook):
    sheet = workbook[DETAIL]
    total_row = sheet.max_row
    assert sheet.cell(row=total_row, column=1).value == "TOTAL"
    headers = [c.value for c in sheet[7]]
    amount_col = headers.index("Amount") + 1
    cell = sheet.cell(row=total_row, column=amount_col)
    assert float(cell.value) == 1750.24
    assert cell.data_type == "n"


def test_a_tick_reads_as_a_tick_not_as_true(workbook):
    """The client's sheet marks the delivery year with a tick, not the word TRUE."""
    sheet = workbook[DETAIL]
    group_row = [c.value for c in sheet[6]]
    first_tick_col = group_row.index("Delivery year") + 1
    ticks = {sheet.cell(row=row, column=first_tick_col).value for row in range(8, sheet.max_row)}
    assert ticks <= {"X", None}
