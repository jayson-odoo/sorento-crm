"""THE Order Inquiry export (OI-EXPORT-SHARED, owner 3 Nov 2026).

Every OI Excel and PDF is written here: the list page's download and its PDF, the async
export tasks, the per-project download, the planning-board OI worksheet and the Excel a
handover email attaches. The owner's three rules, in one place so no surface can drift:

- the first row is the column header (no "ORDER INQUIRY" title row above it);
- the columns are `HEADINGS` unless a caller names its own (the handover's change columns,
  the worksheet's buyer columns);
- rows go by S/O NO, then DELIVERY DATE earliest to latest within each S/O (SO1 all its
  lines by date, then SO2 ...). The date sorted on is the DELIVERY DATE cell the sheet
  prints, so the order a reader sees always matches the column they read.

`in_export_order` is the same rule over any item shape, so an email whose lines are the
attachment's lines (the handover, the reserve email) can put its own table in this order
too: email = preview = attachment.
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, TypeVar

#: The owner's header row, 3 Nov 2026, in this order.
HEADINGS = (
    "SO DATE",
    "S/O NO",
    "ITEM CODE",
    "QTY",
    "DELIVERY DATE",
    "PROJECT/CUSTOMER",
    "LOCATION",
    "REMARK",
)

#: The worksheet tab's name. Never printed as a row.
SHEET_NAME = "ORDER INQUIRY"

#: A record key, not a heading: True on a row that belongs to the row above it (a split
#: line's later rows, which print no DELIVERY DATE of their own) and must stay under it.
CONTINUED = "_continued"

T = TypeVar("T")


def as_date(value: Any) -> Optional[date]:
    """A delivery date in any shape the OI surfaces carry it (a date, a datetime, an ISO
    string, the emails' dd/mm/yyyy), or None when it is blank or unreadable."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def in_export_order(
    items: Sequence[T],
    *,
    so: Callable[[T], Any],
    when: Callable[[T], Any],
    continued: Callable[[T], bool] = lambda _item: False,
) -> List[T]:
    """`items` by S/O, then delivery date earliest first; a blank S/O sorts after every
    real one and a blank date last within its S/O. A `continued` item travels with the
    item before it and the pair sorts on the first one's date. Stable, so items that tie
    keep the order they arrived in."""
    groups: List[List[T]] = []
    for item in items:
        if groups and continued(item):
            groups[-1].append(item)
        else:
            groups.append([item])

    def key(group: List[T]):
        head = group[0]
        number = so(head)
        day = as_date(when(head))
        return (not number, str(number or ""), day is None, day or date.min)

    return [item for group in sorted(groups, key=key) for item in group]


def ordered(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Records (heading -> value) in the export's order."""
    return in_export_order(
        records,
        so=lambda record: record.get("S/O NO"),
        when=lambda record: record.get("DELIVERY DATE"),
        continued=lambda record: bool(record.get(CONTINUED)),
    )


def values(
    records: Sequence[Dict[str, Any]], columns: Sequence[str] = HEADINGS
) -> List[List[Any]]:
    """The table body: one list per record, in the export's order, under `columns`."""
    return [[record.get(heading) for heading in columns] for record in ordered(records)]


def xlsx(records: Sequence[Dict[str, Any]], columns: Sequence[str] = HEADINGS) -> bytes:
    """One sheet: the header row first, then the records in the export's order, in the
    house style. An empty export is still the header row."""
    import openpyxl

    from app.services.order_inquiry_worklist_service import _style_sheet

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = SHEET_NAME
    sheet.append(list(columns))
    for row in values(records, columns):
        sheet.append([_naive(cell) for cell in row])
    _style_sheet(sheet, columns)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def pdf(records: Sequence[Dict[str, Any]], columns: Sequence[str] = HEADINGS) -> bytes:
    """The same table as `xlsx`, printed (owner, 21 Oct: "the pdf needs to be like Excel")."""
    from app.services import order_inquiry_pdf

    return order_inquiry_pdf.render_pdf(columns, values(records, columns))


def _naive(value: Any) -> Any:
    """openpyxl refuses a timezone-aware datetime."""
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value
