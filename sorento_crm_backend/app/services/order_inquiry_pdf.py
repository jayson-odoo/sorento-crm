"""The Order Inquiry PDF: the OI Excel sheet, printed (OI-DOWNLOAD,
`documentation/plans/scm/PLAN-oi-download-21oct.md`).

Owner, 21 Oct 2026: "the pdf needs to be like Excel la, just in pdf format, so I expect 1 table
just like the excel only". So this prints exactly what the workbook holds: the ORDER INQUIRY
title, then ONE table whose header is the sheet's header row and whose rows are the sheet's
rows, both handed over by `OrderInquiryWorklistService` from the same `_sheet_values` the
workbook is written from (no second column list). The look is the house style
(`app/services/excel_style.py`: dark header with white bold text, thin borders, wrapped cells,
dd/mm/yyyy dates) on A4 landscape, with the header row repeated on every page.

Rendered with `pdf_render.render_html` (WeasyPrint), the engine the Purchase Request /
Sponsorship Form PDF uses.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from html import escape
from typing import Any, Sequence

from app.services import excel_style


def cell_text(value: Any) -> str:
    """A sheet cell as the workbook shows it: blank for none, dates dd/mm/yyyy, a whole
    quantity without its `.0`."""
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, (float, Decimal)):
        return str(int(value)) if value == int(value) else format(value, "f").rstrip("0").rstrip(".")
    return str(value)


def _widths(columns: Sequence[str]) -> list[float]:
    """Each column's share of the page, in proportion to its width in the workbook."""
    from app.services.order_inquiry_worklist_service import (
        _EXPORT_DEFAULT_WIDTH,
        _EXPORT_WIDTHS,
    )

    raw = [_EXPORT_WIDTHS.get(column, _EXPORT_DEFAULT_WIDTH) for column in columns]
    total = sum(raw) or 1
    return [round(100 * width / total, 2) for width in raw]


def build_html(columns: Sequence[str], values: Sequence[Sequence[Any]]) -> str:
    """The document HTML, without WeasyPrint - what the tests assert on."""
    from app.services.order_inquiry_worklist_service import EXPORT_TITLE
    colgroup = "".join(f'<col style="width:{w}%"/>' for w in _widths(columns))
    head = "".join(f"<th>{escape(str(column))}</th>" for column in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(cell_text(cell))}</td>" for cell in row) + "</tr>"
        for row in values
    )
    fill = "#" + excel_style.HEADER_FILL[2:]
    font = "#" + excel_style.HEADER_FONT_COLOR[2:]
    return f"""<!doctype html><html><head><meta charset="utf-8"/>
<style>
  @page {{ size: A4 landscape; margin: 10mm; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #000; }}
  h1 {{ font-size: 12px; font-weight: bold; margin: 0 0 6px; }}
  table {{ width: 100%; table-layout: fixed; border-collapse: collapse; }}
  thead {{ display: table-header-group; }}
  tr {{ page-break-inside: avoid; }}
  th, td {{ border: 1px solid #000; padding: 2px; text-align: left; vertical-align: top;
            font-size: 7px; white-space: normal; overflow-wrap: break-word; }}
  /* A heading breaks only between words (ACKNOWLEDGED never as ACKNOWLED / GED). */
  th {{ background: {fill}; color: {font}; font-weight: bold; font-size: 6px;
        overflow-wrap: normal; word-break: keep-all; }}
</style></head><body>
<h1>{escape(EXPORT_TITLE)}</h1>
<table><colgroup>{colgroup}</colgroup><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
</body></html>"""


def render_pdf(columns: Sequence[str], values: Sequence[Sequence[Any]]) -> bytes:
    from app.services.pdf_render import render_html

    return render_html(build_html(columns, values))
