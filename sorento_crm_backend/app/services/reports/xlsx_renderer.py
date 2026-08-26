"""ReportResult -> an .xlsx workbook, laid out like the register the client keeps by hand.

SUMMARY first (the pivot), then ONE SHEET PER MONTH of the period, named the way the
client's own file names them (JAN'25 .. DEC'25). A month with no rows still gets its sheet:
a register with eleven tabs reads as a lost month rather than a quiet one.

**Totals are VALUES, never formulas** (AC-D4). The workbook the client keeps uses SUM
formulas; ours writes exactly what the engine computed, so an Excel recalculation cannot
produce a different answer from the screen the user exported.

The renderer knows nothing about months, dates or filters. It is handed a
``engine.WorkbookData`` - a summary and a list of named sheets - and draws it.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.schemas.report import ReportDetailLayout, ReportPivotLayout
from app.services.reports.engine import WorkbookData
from app.services.reports.registry import ReportDefinition

MONEY_FORMAT = "#,##0.00"
# The CRM writes dates dd/mm/yyyy everywhere else, and a text date cannot be sorted,
# filtered or reformatted in Excel - which is most of what a file is opened to do.
DATE_FORMAT = "DD/MM/YYYY"
TICK = "X"

_TITLE_FONT = Font(bold=True, size=14)
_HEADER_FONT = Font(bold=True)
_CENTRE = Alignment(horizontal="center", vertical="center")

# Rows 1-4 are the title block, 5 is blank, so a table's header starts at 6.
_HEADER_ROW = 6


def _title_block(sheet: Worksheet, definition: ReportDefinition, period_label: str) -> None:
    """Whose report this is, what it is, over what period, for which department (AC-D2)."""
    sheet["A1"] = definition.workbook.company_name
    sheet["A1"].font = _TITLE_FONT
    sheet["A2"] = definition.title
    sheet["A2"].font = _HEADER_FONT
    sheet["A3"] = period_label
    sheet["A4"] = definition.workbook.department or ""


def _money(value: Optional[str]) -> Optional[Decimal]:
    return Decimal(value) if value not in (None, "") else None


def _write_money(sheet: Worksheet, row: int, column: int, value: Optional[str]) -> None:
    cell = sheet.cell(row=row, column=column)
    amount = _money(value)
    if amount is None:
        return  # blank, not zero - the client's sheet prints "-" here
    cell.value = amount
    cell.number_format = MONEY_FORMAT


def _write_date(sheet: Worksheet, row: int, column: int, value: Optional[str]) -> None:
    """An ISO date string as a REAL date cell. Anything unparseable stays the text it was."""
    cell = sheet.cell(row=row, column=column)
    try:
        cell.value = date.fromisoformat(str(value)[:10])
    except ValueError:
        cell.value = value
        return
    cell.number_format = DATE_FORMAT


def _autosize(sheet: Worksheet, widths: List[int]) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def _render_summary(
    sheet: Worksheet, definition: ReportDefinition, pivot: ReportPivotLayout, period_label: str
) -> None:
    _title_block(sheet, definition, period_label)

    measures = pivot.measures
    span = max(len(measures), 1)
    header, sub = _HEADER_ROW, _HEADER_ROW + 1

    sheet.cell(row=header, column=1, value=pivot.row_dim.label).font = _HEADER_FONT
    sheet.merge_cells(start_row=header, start_column=1, end_row=sub, end_column=1)

    def _group(column: int, label: str) -> None:
        cell = sheet.cell(row=header, column=column, value=label)
        cell.font = _HEADER_FONT
        cell.alignment = _CENTRE
        if span > 1:
            sheet.merge_cells(
                start_row=header, start_column=column, end_row=header, end_column=column + span - 1
            )
        for offset, measure in enumerate(measures):
            measure_cell = sheet.cell(row=sub, column=column + offset, value=measure.label)
            measure_cell.font = _HEADER_FONT
            measure_cell.alignment = _CENTRE

    column = 2
    for value in pivot.col_dim.values:
        _group(column, (pivot.col_dim.value_labels or {}).get(value, value))
        column += span
    total_column = column
    _group(total_column, "TOTAL")

    row = sub + 1
    for row_value in pivot.row_values:
        sheet.cell(row=row, column=1, value=row_value)
        column = 2
        for col_value in pivot.col_dim.values:
            cell_measures = pivot.cells.get(row_value, {}).get(col_value, {})
            for offset, measure in enumerate(measures):
                _write_money(sheet, row, column + offset, cell_measures.get(measure.key))
            column += span
        for offset, measure in enumerate(measures):
            _write_money(sheet, row, total_column + offset, pivot.row_totals.get(row_value, {}).get(measure.key))
        row += 1

    sheet.cell(row=row, column=1, value="GRAND TOTAL").font = _HEADER_FONT
    column = 2
    for col_value in pivot.col_dim.values:
        for offset, measure in enumerate(measures):
            _write_money(sheet, row, column + offset, pivot.col_totals.get(col_value, {}).get(measure.key))
        column += span
    for offset, measure in enumerate(measures):
        _write_money(sheet, row, total_column + offset, pivot.grand_total.get(measure.key))

    _autosize(sheet, [22] + [14] * (total_column + span - 2))


def _render_detail(
    sheet: Worksheet, definition: ReportDefinition, detail: ReportDetailLayout, period_label: str
) -> None:
    _title_block(sheet, definition, period_label)

    group_row, header_row = _HEADER_ROW, _HEADER_ROW + 1
    positions = {column.key: index for index, column in enumerate(detail.columns, start=1)}

    for column in detail.columns:
        cell = sheet.cell(row=header_row, column=positions[column.key], value=column.label)
        cell.font = _HEADER_FONT
        cell.alignment = _CENTRE

    for group in detail.column_groups:
        members = [positions[key] for key in group.keys if key in positions]
        if not members:
            continue
        first, last = min(members), max(members)
        cell = sheet.cell(row=group_row, column=first, value=group.label)
        cell.font = _HEADER_FONT
        cell.alignment = _CENTRE
        if last > first:
            sheet.merge_cells(
                start_row=group_row, start_column=first, end_row=group_row, end_column=last
            )

    row = header_row + 1
    for record in detail.rows:
        for column in detail.columns:
            index = positions[column.key]
            value = record.get(column.key)
            if column.type == "money":
                _write_money(sheet, row, index, value)
            elif column.type == "date":
                if value is not None:
                    _write_date(sheet, row, index, value)
            elif column.type == "bool":
                if value:
                    sheet.cell(row=row, column=index, value=TICK).alignment = _CENTRE
            elif value is not None:
                sheet.cell(row=row, column=index, value=value)
        row += 1

    # The label opens the row, as the client's own sheets do - unless that cell carries a
    # total, in which case writing the label over it would silently lose the money. It then
    # takes the first cell that holds no total, or a dedicated one past the last column.
    totalled = {c.key for c in detail.columns if c.type == "money" and c.key in detail.totals}
    label_column = next(
        (positions[c.key] for c in detail.columns if c.key not in totalled),
        len(detail.columns) + 1,
    )
    sheet.cell(row=row, column=label_column, value="GRAND TOTAL").font = _HEADER_FONT
    for column in detail.columns:
        if column.key in totalled:
            _write_money(sheet, row, positions[column.key], detail.totals[column.key])

    _autosize(sheet, [max(12, min(40, (c.size or 120) // 8)) for c in detail.columns])


def render_workbook(definition: ReportDefinition, data: WorkbookData) -> bytes:
    """The whole workbook as bytes: SUMMARY, then one sheet per month of the period."""
    workbook = Workbook()
    summary_sheet = workbook.active
    summary_sheet.title = "SUMMARY"
    _render_summary(summary_sheet, definition, data.summary, data.period_label)

    for sheet in data.sheets:
        # Excel refuses a tab name over 31 characters; a month never is, but a report whose
        # period is a custom range still names its sheets through here.
        _render_detail(
            workbook.create_sheet(title=sheet.name[:31]), definition, sheet.detail, sheet.label
        )

    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()
