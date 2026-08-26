"""The workbook the export writes (AC-D1 to AC-D4), on the synthetic dataset.

The client's file is SUMMARY plus twelve monthly tables, and so is ours: one tab per month
OF THE PERIOD, empty months included, because a register with eleven tabs reads as a lost
month rather than a quiet one. What is asserted here is the shape; the numbers are diffed
against the client's own workbook in tests/test_report_workbook_2025.py.

Three rules run through it:

- **Totals are VALUES, never formulas** (AC-D4). The workbook the client keeps by hand uses
  SUM formulas; ours writes what the engine computed, so Excel cannot recalculate a
  different answer from the screen the user exported.
- **Every sheet carries the same columns.** The tick-group members are derived once, over
  the whole period, so JAN and FEB cannot come out with different columns.
- **A blank cell is blank, never 0.00.**

Run: pytest tests/test_report_xlsx_renderer.py -q
"""
from __future__ import annotations

from io import BytesIO

import pytest

from tests import _report_fixture as fixture
from tests._pg_fixture import pg_session

SUMMARY = "SUMMARY"
MONTHS = [
    "JAN'26", "FEB'26", "MAR'26", "APR'26", "MAY'26", "JUN'26",
    "JUL'26", "AUG'26", "SEP'26", "OCT'26", "NOV'26", "DEC'26",
]

_GROUP_ROW = 6
_HEADER_ROW = 7
_FIRST_DATA_ROW = 8


@pytest.fixture
def workbook():
    from openpyxl import load_workbook

    from app.services.reports import engine
    from app.services.reports.xlsx_renderer import render_workbook

    with pg_session() as db:
        fixture.create_table(db)
        definition = fixture.definition()
        data = engine.run_workbook(db, definition, definition.default_view["params"])
        content = render_workbook(definition, data)

    assert isinstance(content, (bytes, bytearray))
    return load_workbook(BytesIO(content))


def _merged(sheet, anchor: str) -> str:
    """The merged range a top-left cell anchors, as a string, or "" if it is not merged."""
    for cell_range in sheet.merged_cells.ranges:
        if str(cell_range).startswith(f"{anchor}:"):
            return str(cell_range)
    return ""


def _headers(sheet) -> list:
    return [c.value for c in sheet[_HEADER_ROW]]


def _row_labels(sheet) -> list:
    """The PS-No column of every data row, excluding the GRAND TOTAL line."""
    return [
        sheet.cell(row=row, column=1).value
        for row in range(_FIRST_DATA_ROW, sheet.max_row)
    ]


# --------------------------------------------------------------------------- AC-D1


def test_the_summary_comes_first_then_one_sheet_per_month_of_the_period(workbook):
    """AC-D1. Twelve months in the period, twelve tabs, in calendar order."""
    assert workbook.sheetnames == [SUMMARY] + MONTHS


def test_a_month_with_no_rows_still_gets_its_sheet(workbook):
    """February booked nothing. The client's register still has a February."""
    sheet = workbook["FEB'26"]
    assert sheet["A1"].value == "ZZT Sdn Bhd"
    assert _headers(sheet)[0] == "Order no"
    assert _row_labels(sheet) == []
    assert sheet.cell(row=sheet.max_row, column=1).value == "GRAND TOTAL"


def test_each_monthly_sheet_holds_only_that_months_rows(workbook):
    assert _row_labels(workbook["JAN'26"]) == ["Z-001", "Z-002"]
    assert _row_labels(workbook["MAR'26"]) == ["Z-003", "Z-004"]
    assert _row_labels(workbook["NOV'26"]) == ["Z-005"]


def test_a_row_outside_the_period_reaches_no_sheet(workbook):
    """Z-006 is a 2025 order; the period is 2026."""
    everywhere = [label for name in MONTHS for label in _row_labels(workbook[name])]
    assert "Z-006" not in everywhere


# --------------------------------------------------------------------------- AC-D2


def test_every_sheet_opens_with_the_title_block(workbook):
    """AC-D2: whose report this is, what it is, over what period, for which department."""
    for name in [SUMMARY] + MONTHS:
        sheet = workbook[name]
        assert sheet["A1"].value == "ZZT Sdn Bhd"
        assert sheet["A2"].value == "Scratch orders"
        assert sheet["A4"].value == "Scratch"


def test_the_period_line_is_the_range_on_summary_and_the_month_on_a_monthly_sheet(workbook):
    assert workbook[SUMMARY]["A3"].value == "Jan'26 to Dec'26"
    assert workbook["JAN'26"]["A3"].value == "Jan'26"
    assert workbook["DEC'26"]["A3"].value == "Dec'26"


# --------------------------------------------------------------------------- AC-D3


def test_the_summary_merges_each_column_value_over_its_measures(workbook):
    """AC-D3: one merged month header spanning Amount and Fee."""
    sheet = workbook[SUMMARY]
    assert sheet["A6"].value == "Agent"
    assert sheet["B6"].value == "Jan'26"
    assert _merged(sheet, "B6") == "B6:C6"
    assert sheet["B7"].value == "Amount"
    assert sheet["C7"].value == "Fee"


def test_a_monthly_sheet_merges_the_tick_group_header(workbook):
    """AC-D3: "Delivery year" spans its 2026 and 2027 tick columns."""
    sheet = workbook["JAN'26"]
    group_row = [c.value for c in sheet[_GROUP_ROW]]
    assert "Delivery year" in group_row
    anchor = sheet.cell(row=_GROUP_ROW, column=group_row.index("Delivery year") + 1)
    assert _merged(sheet, anchor.coordinate)


def test_every_monthly_sheet_carries_the_same_columns(workbook):
    """The tick columns come from the whole period, not from one month's rows.

    January holds no 2027 delivery at all. Deriving the members per sheet would give
    January one tick column and March two, and the twelve tables would stop being the
    same table.
    """
    expected = _headers(workbook["JAN'26"])
    assert "2026" in [str(v) for v in expected] and "2027" in [str(v) for v in expected]
    for name in MONTHS:
        assert _headers(workbook[name]) == expected


def test_a_tick_reads_as_a_tick_not_as_true(workbook):
    """The client's sheet marks the delivery year with a tick, not the word TRUE."""
    sheet = workbook["JAN'26"]
    group_row = [c.value for c in sheet[_GROUP_ROW]]
    first_tick_col = group_row.index("Delivery year") + 1
    ticks = {
        sheet.cell(row=row, column=first_tick_col).value
        for row in range(_FIRST_DATA_ROW, sheet.max_row)
    }
    assert ticks <= {"X", None}


# --------------------------------------------------------------------------- AC-D4


def test_the_summary_carries_a_row_per_row_value(workbook):
    sheet = workbook[SUMMARY]
    assert sheet["A8"].value == "Alice"
    assert sheet["A9"].value == "Bob"
    assert float(sheet["B8"].value) == 1250.25
    assert sheet["B8"].data_type == "n"


def test_a_missing_cell_is_blank_not_zero(workbook):
    """Bob has nothing in January; the workbook prints nothing, as the client's does."""
    assert workbook[SUMMARY]["B9"].value is None


def test_the_summary_grand_total_row_holds_values_not_formulas(workbook):
    """AC-D4. A formula lets Excel recompute a different answer from the screen's."""
    sheet = workbook[SUMMARY]
    total_row = sheet.max_row
    assert sheet.cell(row=total_row, column=1).value == "GRAND TOTAL"
    values = [
        sheet.cell(row=total_row, column=col).value for col in range(2, sheet.max_column + 1)
    ]
    assert float(values[-2]) == 1750.24  # the amount grand total, before the fee
    assert float(values[-1]) == 36.51


def test_a_monthly_sheet_totals_its_own_measures(workbook):
    sheet = workbook["JAN'26"]
    total_row = sheet.max_row
    assert sheet.cell(row=total_row, column=1).value == "GRAND TOTAL"
    amount_col = _headers(sheet).index("Amount") + 1
    fee_col = _headers(sheet).index("Fee") + 1
    assert float(sheet.cell(row=total_row, column=amount_col).value) == 1250.25
    assert float(sheet.cell(row=total_row, column=fee_col).value) == 10.50


def test_the_monthly_totals_add_up_to_the_summary_grand_total(workbook):
    monthly = 0.0
    for name in MONTHS:
        sheet = workbook[name]
        amount_col = _headers(sheet).index("Amount") + 1
        value = sheet.cell(row=sheet.max_row, column=amount_col).value
        monthly += float(value) if value is not None else 0.0
    assert round(monthly, 2) == 1750.24


def test_no_cell_anywhere_in_the_workbook_is_a_formula(workbook):
    """AC-D4, across every sheet: nothing Excel could recalculate."""
    for name in workbook.sheetnames:
        for row in workbook[name].iter_rows():
            for cell in row:
                assert not (isinstance(cell.value, str) and cell.value.startswith("="))


def test_money_cells_carry_a_thousands_and_two_decimal_format(workbook):
    assert workbook[SUMMARY]["B8"].number_format == "#,##0.00"
    sheet = workbook["JAN'26"]
    amount_col = _headers(sheet).index("Amount") + 1
    assert sheet.cell(row=_FIRST_DATA_ROW, column=amount_col).number_format == "#,##0.00"


# ------------------------------------------------------------------ AC-C5 / columns


def test_the_workbook_carries_exactly_the_views_columns_in_its_order():
    """AC-C5. What the user sees on screen is what the file holds, in that order."""
    from openpyxl import load_workbook

    from app.schemas.report import ReportViewConfig
    from app.services.reports import engine
    from app.services.reports.xlsx_renderer import render_workbook

    definition = fixture.definition()
    view = ReportViewConfig.model_validate(
        {
            "params": definition.default_view["params"],
            "detail": {"columns": ["amount", "order_no", "agent"], "order": []},
            "pivot": definition.default_view["pivot"],
        }
    )
    with pg_session() as db:
        fixture.create_table(db)
        data = engine.run_workbook(db, definition, definition.default_view["params"], view)
        content = render_workbook(definition, data)

    sheet = load_workbook(BytesIO(content))["JAN'26"]
    assert _headers(sheet) == ["Amount", "Order no", "Agent"]


def test_an_empty_column_list_falls_back_to_the_definitions_default_columns():
    """A twenty-column sheet is unreadable, so a workbook never means the whole catalog.

    The SCREEN asks for the whole catalog and hides client-side, which is what makes
    ticking a column instant (AC-B7). A FILE has no Columns panel, so an unset view means
    the columns the report was designed around.
    """
    from openpyxl import load_workbook

    from app.schemas.report import ReportViewConfig
    from app.services.reports import engine
    from app.services.reports.xlsx_renderer import render_workbook

    definition = fixture.definition()
    definition.default_view["detail"]["columns"] = ["order_no", "amount"]
    view = ReportViewConfig.model_validate(
        {
            "params": definition.default_view["params"],
            "detail": {"columns": [], "order": []},
            "pivot": definition.default_view["pivot"],
        }
    )
    with pg_session() as db:
        fixture.create_table(db)
        data = engine.run_workbook(db, definition, definition.default_view["params"], view)
        content = render_workbook(definition, data)

    sheet = load_workbook(BytesIO(content))["JAN'26"]
    assert _headers(sheet) == ["Order no", "Amount"]
