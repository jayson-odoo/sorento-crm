"""The one house style for an exported workbook: the LOW STOCK REPORT's look.

Owner, 21 Oct 2026 (OI-DOWNLOAD): "our excel format needs to be nicer ... one of the success
ones is the LOW STOCK REPORT - the formatting is quite nice, we should unify this". That look
(itself the paper sheet's, S14 AC-S14.6) is a dark bold white header row, a thin border and
top-aligned wrapped text on every cell, the panes frozen under the header, and explicit
column widths. It used to be spelled out twice - `summary_order_service.write_sheet` and
`low_stock_report_service._write_workbook` - and now lives here for both of them and for the
Order Inquiry workbook.

Style objects only, built fresh per call: openpyxl stores a cell's style by value, so a
caller assigning these to many cells pays one lookup per distinct style, not per cell.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Optional

HEADER_FILL = "FF404040"
HEADER_FONT_COLOR = "FFFFFFFF"
#: dd/mm/yyyy, how every date in the OI email and their own sheets reads.
DATE_FORMAT = "DD/MM/YYYY"


def border():
    from openpyxl.styles import Border, Side

    thin = Side(style="thin")
    return Border(left=thin, right=thin, top=thin, bottom=thin)


def wrap():
    from openpyxl.styles import Alignment

    return Alignment(wrap_text=True, vertical="top")


def header_font():
    from openpyxl.styles import Font

    return Font(bold=True, color=HEADER_FONT_COLOR)


def header_fill():
    from openpyxl.styles import PatternFill

    return PatternFill("solid", fgColor=HEADER_FILL)


def style_table(
    ws,
    *,
    header_row: int = 1,
    widths: Optional[Mapping[str, float]] = None,
    date_columns: Iterable[int] = (),
) -> None:
    """Style a table already written into `ws` (normal, not write-only, mode): every cell
    from `header_row` down gets the border and wrap, the header row the dark fill and white
    bold font, the panes freeze under the header, `widths` (column letter -> width) apply,
    and the 1-based `date_columns` print dd/mm/yyyy."""
    cell_border, cell_wrap = border(), wrap()
    font, fill = header_font(), header_fill()
    dates = set(date_columns)
    for row in ws.iter_rows(min_row=header_row, max_row=ws.max_row):
        for cell in row:
            cell.border = cell_border
            cell.alignment = cell_wrap
            if cell.row == header_row:
                cell.font = font
                cell.fill = fill
            elif cell.column in dates:
                cell.number_format = DATE_FORMAT
    ws.freeze_panes = f"A{header_row + 1}"
    for col, width in (widths or {}).items():
        ws.column_dimensions[col].width = width
