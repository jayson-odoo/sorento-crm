"""The Costing page as an Excel file (contract 4.5, AC-CG-09).

Row 1 names the view and the as-of date, row 2 the headers in the page's order, data from row 3.
Numbers are numbers at full precision with a two-place display format; an unknown value is an
empty cell and its reason is in Note.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font

from app.services.costing import basis

HEADERS = [
    "Category", "Code", "Name", "Supplier", "Currency", "Cost", "Rate (per MYR)", "SST",
    "Transport mode", "Transport value", "Landing (RM)", "Cost method", "Mark-up %", "Final (RM)",
    "List price (AutoCount)", "Margin %", "Note",
]
_MONEY = "#,##0.00"
_RATE = "0.0000"
_MODE_LABELS = {"add": "Add", "multiply": "Multiply"}


def format_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _num(value) -> Optional[float]:
    return None if value is None else float(value)


def build_workbook(result: dict) -> bytes:
    party = result["party"]
    view = f"{party['customer_code']} {party['customer_name']}" if party else "Company standard"
    wb = Workbook()
    ws = wb.active
    ws.title = "Costing"
    ws.cell(row=1, column=1, value=f"Costing - {view} - as of {format_date(result['as_of'])}").font = Font(bold=True)
    for i, header in enumerate(HEADERS, start=1):
        ws.cell(row=2, column=i, value=header).font = Font(bold=True)

    for r, row in enumerate(result["rows"], start=3):
        note = "; ".join(basis.reason_text(x) for x in row["reasons"])
        values = [
            (row["category_name"], None),
            (row["product_code"], None),
            (row["product_name"], None),
            (row["supplier_code"], None),
            (row["currency"], None),
            (_num(row["unit_cost"]), _MONEY),
            (_num(row["units_per_base"]), _RATE),
            (_num(row["sst_factor"]), "0.00##"),
            (_MODE_LABELS.get(row["transport_mode"]), None),
            (_num(row["transport_value"]), _MONEY),
            (_num(row["landing"]), _MONEY),
            (basis.METHOD_LABELS.get(row["cost_method"]), None),
            (_num(row["markup_pct"]), _MONEY),
            (_num(row["final"]), _MONEY),
            (_num(row["list_price"]), _MONEY),
            (_num(row["margin_pct"]), _MONEY),
            (note or None, None),
        ]
        for c, (value, fmt) in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            if fmt and value is not None:
                cell.number_format = fmt

    widths = [18, 16, 32, 12, 9, 12, 14, 8, 14, 14, 14, 24, 11, 14, 20, 10, 42]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=2, column=i).column_letter].width = w
    ws.freeze_panes = "A3"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
