"""AC-D5: the exported workbook against the client's own 2025 register, cell for cell.

This is the whole point of slice S5's fixture. The client keeps `SPONSORSHIP REPORT
JAN-Dec'25.xlsx` by hand; its twelve GRAND TOTAL cells and its SUMMARY C28 / C29 are numbers
they already trust. So: load those 214 forms into a blank schema through the loader itself,
run the report over 2025, render the export, and compare our GRAND TOTALs to theirs.

The rows are loaded HERE, into the test's own scratch schema, never read from the developer
copy that `scripts/dev/load_sponsorship_2025_fixture.py --apply` writes to. CI has no data
and the local database is a copy of production; a test that leaned on either would pass for
the wrong reason today and fail for no reason tomorrow.

Run: pytest tests/test_report_workbook_2025.py -q
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from tests._pg_fixture import blank_session

WORKBOOK = Path(__file__).resolve().parent / "fixtures" / "sponsorship_2025.xlsx"

SUMMARY = "SUMMARY"
MONTHS = [
    "JAN'25", "FEB'25", "MAR'25", "APR'25", "MAY'25", "JUN'25",
    "JUL'25", "AUG'25", "SEP'25", "OCT'25", "NOV'25", "DEC'25",
]

#: The client's own SUMMARY sheet, cells C28 and C29.
CLIENT_YEAR_PROJECT_VALUE = 257076027.91
CLIENT_YEAR_SAMPLE_PRICE = 518605.38

_HEADER_ROW = 7
_FIRST_DATA_ROW = 8

_PARAMS = {
    "date_basis": "approved_at",
    "period": {"kind": "year", "year": 2025},
    "sales_agent": [],
    "status": ["approved", "processed_by_cs"],
}


@pytest.fixture(scope="module")
def sheets():
    """The client's workbook as plain dicts, read by the loader's own parser."""
    from scripts.dev.load_sponsorship_2025_fixture import parse_workbook

    return parse_workbook(WORKBOOK)


@pytest.fixture(scope="module")
def exported(sheets):
    """The 214 fixture forms, the report over 2025, and the workbook it exports."""
    from openpyxl import load_workbook

    from app.services.company_scope import set_company_scope
    from app.services.reports import engine
    from app.services.reports.definitions.sponsorship import REPORT
    from app.services.reports.xlsx_renderer import render_workbook
    from scripts.dev.load_sponsorship_2025_fixture import load

    with blank_session() as db:
        set_company_scope(db, None)
        result = load(db, sheets)
        assert result["inserted"] == 214, result

        data = engine.run_workbook(db, REPORT, _PARAMS)
        content = render_workbook(REPORT, data)

    return load_workbook(BytesIO(content))


def _headers(sheet) -> list:
    return [c.value for c in sheet[_HEADER_ROW]]


def _grand_total(sheet, label: str) -> float:
    """The GRAND TOTAL row's cell under a named column, as a float."""
    column = _headers(sheet).index(label) + 1
    value = sheet.cell(row=sheet.max_row, column=column).value
    return 0.0 if value is None else round(float(value), 2)


def _money(value) -> float:
    return 0.0 if value is None else round(float(value), 2)


# ------------------------------------------------------------------ shape (AC-D1/D2)


def test_the_export_is_summary_then_the_twelve_months_of_2025(exported):
    assert exported.sheetnames == [SUMMARY] + MONTHS


def test_every_sheet_opens_with_the_clients_title_block(exported):
    """AC-D2, with the values settled in S3: company Sorento, department PROJECT SALES."""
    for name in [SUMMARY] + MONTHS:
        sheet = exported[name]
        assert sheet["A1"].value == "Sorento"
        assert sheet["A2"].value == "Sponsorship report"
        assert sheet["A4"].value == "PROJECT SALES"
    assert exported[SUMMARY]["A3"].value == "Jan'25 to Dec'25"
    assert exported["JAN'25"]["A3"].value == "Jan'25"
    assert exported["DEC'25"]["A3"].value == "Dec'25"


def test_a_monthly_sheet_carries_the_reports_default_columns(exported):
    """The client's seven columns. The Expected-year group has no member in 2025.

    H..K is empty on all 214 rows of the client's workbook, so there is no delivery year
    to tick and the group renders no columns at all. That is a fact about the data, not a
    missing feature (PLAN, S5 contract points).
    """
    assert _headers(exported["JAN'25"]) == [
        "PS No",
        "Sales agent",
        "Customer",
        "Project title",
        "Sponsor project",
        "Project value",
        "Sample price",
    ]
    assert "Expected year of delivery" not in [c.value for c in exported["JAN'25"][6]]


def test_each_sheet_holds_the_same_number_of_rows_the_client_typed(exported, sheets):
    for sheet, name in zip(sheets, MONTHS):
        rendered = exported[name]
        rows = rendered.max_row - _FIRST_DATA_ROW  # the GRAND TOTAL line is the last row
        assert rows == len(sheet["rows"]), name


# ------------------------------------------------------------------ numbers (AC-D5)


def test_each_monthly_grand_total_equals_the_clients_sheet(exported, sheets):
    """The twelve numbers the client checks the register against, to the cent."""
    for sheet, name in zip(sheets, MONTHS):
        rendered = exported[name]
        assert _grand_total(rendered, "Project value") == _money(
            sheet["sheet_total_project_value"]
        ), name
        assert _grand_total(rendered, "Sample price") == _money(
            sheet["sheet_total_sample_price"]
        ), name


def test_the_summary_grand_total_equals_the_clients_c28_and_c29(exported):
    sheet = exported[SUMMARY]
    total_row = sheet.max_row
    assert sheet.cell(row=total_row, column=1).value == "GRAND TOTAL"
    # The last group of the header is TOTAL, and its two measures are the year totals.
    project_value = sheet.cell(row=total_row, column=sheet.max_column - 1).value
    sample_price = sheet.cell(row=total_row, column=sheet.max_column).value
    assert round(float(project_value), 2) == CLIENT_YEAR_PROJECT_VALUE
    assert round(float(sample_price), 2) == CLIENT_YEAR_SAMPLE_PRICE


def test_the_monthly_totals_add_up_to_the_year(exported):
    project_value = sum(_grand_total(exported[name], "Project value") for name in MONTHS)
    sample_price = sum(_grand_total(exported[name], "Sample price") for name in MONTHS)
    assert round(project_value, 2) == CLIENT_YEAR_PROJECT_VALUE
    assert round(sample_price, 2) == CLIENT_YEAR_SAMPLE_PRICE


def test_the_summary_column_headers_are_the_twelve_months(exported):
    sheet = exported[SUMMARY]
    labels = [sheet.cell(row=6, column=col).value for col in range(2, sheet.max_column + 1)]
    named = [label for label in labels if label]
    assert named == [
        "Jan'25", "Feb'25", "Mar'25", "Apr'25", "May'25", "Jun'25",
        "Jul'25", "Aug'25", "Sep'25", "Oct'25", "Nov'25", "Dec'25", "TOTAL",
    ]


def test_no_cell_anywhere_is_a_formula(exported):
    """AC-D4. The client's own sheet is SUM formulas; ours is what the engine computed."""
    for name in exported.sheetnames:
        for row in exported[name].iter_rows():
            for cell in row:
                assert not (isinstance(cell.value, str) and cell.value.startswith("="))
