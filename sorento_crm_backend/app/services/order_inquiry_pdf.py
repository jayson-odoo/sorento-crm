"""The Order Inquiry PDF: the OI email's layout, printed (OI-DOWNLOAD, owner 21 Oct 2026,
`documentation/plans/scm/PLAN-oi-download-21oct.md`).

The handover email (`oihr_0008_so_table_on_top` + `oihr_0009_split_rows`) prints the S/O facts
once in a top table (S/O NO, SO DATE, CUSTOMER, PROJECT) and the item lines below it:
LOCATION | ITEM CODE | QTY | [NEW QTY] | DELIVERY | [NEW DATE] | REMARK, the NEW columns only
when some line moved, and a split line's later rows blank in LOCATION / ITEM CODE / QTY /
DELIVERY. This prints the same thing off the rows the OI Excel prints
(`OrderInquiryWorklistService._all_rows`), one block per S/O: an OI is one S/O, so its PDF is
exactly the email's two tables; a filtered list prints one such block per S/O.

Rendered with `pdf_render.render_html` (WeasyPrint), the engine the Purchase Request /
Sponsorship Form PDF uses.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from html import escape
from typing import Any, Dict, List, Sequence

HEADING = "ORDER INQUIRY"


def _date(value: Any) -> str:
    """dd/mm/yyyy, as every date the email prints."""
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    return str(value or "")


def _qty(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value == value.to_integral() else str(value)
    return str(value)


def _continued(row: Dict[str, Any]) -> bool:
    """A split line's row after its first (`_with_splits`' `plan_key` index)."""
    key = row.get("plan_key")
    return bool(key) and key[2] > 0


def _line(row: Dict[str, Any]) -> Dict[str, str]:
    """One item line, as the email prints it. A split line's rows carry the line's QTY /
    DELIVERY on the first row only and their own figures as NEW QTY / NEW DATE."""
    continued = _continued(row)
    return {
        "location": "" if continued else str(row.get("location") or ""),
        "item_code": "" if continued else str(row.get("item_code") or ""),
        "qty": "" if continued else _qty(row.get("qty")),
        "new_qty": _qty(row.get("change_qty")),
        "delivery": "" if continued else _date(row.get("delivery_date")),
        "new_date": _date(row.get("change_date")),
        "remark": str(row.get("split_remark") or ""),
    }


def orders(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """`[{so_number, so_date, customer, project, lines}]`, by S/O no, each S/O's lines in
    the email's order (`_handover_sort_key`): the SO line number ascending, a row naming no
    line last, then item code, with a split line's rows kept together in plan order."""
    by_so: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        so_number = str(row.get("so_number") or "")
        order = by_so.setdefault(
            so_number,
            {
                "so_number": so_number,
                "so_date": _date(row.get("so_date")),
                "customer": str(row.get("customer_name") or ""),
                "project": str(row.get("project_title") or ""),
                "rows": [],
            },
        )
        order["rows"].append(row)
    out = []
    for so_number in sorted(by_so):
        order = by_so[so_number]
        members = sorted(
            order.pop("rows"),
            key=lambda row: (
                row.get("so_line_no") is None,
                row.get("so_line_no") or 0,
                str(row.get("item_code") or ""),
                str(row.get("so_line_id") or ""),
                row["plan_key"][2] if row.get("plan_key") else 0,
            ),
        )
        order["lines"] = [_line(row) for row in members]
        out.append(order)
    return out


def _block(order: Dict[str, Any]) -> str:
    lines = order["lines"]
    new_qty = any(line["new_qty"] for line in lines)
    new_date = any(line["new_date"] for line in lines)
    heads = ["LOCATION", "ITEM CODE", "QTY"]
    heads += ["NEW QTY"] if new_qty else []
    heads += ["DELIVERY"]
    heads += ["NEW DATE"] if new_date else []
    heads += ["REMARK"]

    def cells(line: Dict[str, str]) -> str:
        keys = ["location", "item_code", "qty"]
        keys += ["new_qty"] if new_qty else []
        keys += ["delivery"]
        keys += ["new_date"] if new_date else []
        keys += ["remark"]
        return "".join(f"<td>{escape(line[key])}</td>" for key in keys)

    body = "".join(f"<tr>{cells(line)}</tr>" for line in lines) or (
        f'<tr><td colspan="{len(heads)}" class="empty">No lines.</td></tr>'
    )
    return (
        '<div class="so">'
        '<table class="so-table"><thead><tr>'
        "<th>S/O NO</th><th>SO DATE</th><th>CUSTOMER</th><th>PROJECT</th>"
        "</tr></thead><tbody><tr>"
        f"<td>{escape(order['so_number'])}</td><td>{escape(order['so_date'])}</td>"
        f"<td>{escape(order['customer'])}</td><td>{escape(order['project'])}</td>"
        "</tr></tbody></table>"
        '<table class="lines"><thead><tr>'
        + "".join(f"<th>{head}</th>" for head in heads)
        + f"</tr></thead><tbody>{body}</tbody></table>"
        "</div>"
    )


def build_html(rows: Sequence[Dict[str, Any]]) -> str:
    """The document HTML, without WeasyPrint - what the tests assert on."""
    blocks = "".join(_block(order) for order in orders(rows)) or (
        '<p class="empty">No order inquiry lines.</p>'
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"/>
<style>
  @page {{ size: A4; margin: 14mm 14mm; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #000; font-size: 11px; }}
  h1 {{ font-size: 13px; font-weight: bold; margin: 0 0 12px; }}
  .so {{ margin-bottom: 18px; }}
  table {{ width: 100%; table-layout: fixed; border-collapse: collapse; margin-bottom: 6px; }}
  thead {{ display: table-header-group; }}
  tr {{ page-break-inside: avoid; }}
  th, td {{ border: 1px solid #999; padding: 4px 6px; text-align: left; vertical-align: top;
            font-size: 10px; overflow-wrap: anywhere; word-break: break-word; }}
  th {{ background: #f2f2f2; font-weight: bold; }}
  .empty {{ color: #777; font-style: italic; }}
</style></head><body>
<h1>{HEADING}</h1>
{blocks}
</body></html>"""


def render_pdf(rows: Sequence[Dict[str, Any]]) -> bytes:
    from app.services.pdf_render import render_html

    return render_html(build_html(rows))
