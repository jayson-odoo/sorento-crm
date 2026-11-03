"""OI-EXPORT-SHARED (owner, 3 Nov 2026): every Order Inquiry Excel/PDF comes from ONE
exporter (`app/services/order_inquiry_export.py`), sorted by S/O then delivery date earliest
to latest within each S/O, and its first row is the column header - no "ORDER INQUIRY"
title row above it.

Covers each surface: the list-page Excel and PDF (`OrderInquiryWorklistService`), the
planning-board worksheet, the per-project Excel (`ProjectOrderInquiryService.export_xlsx`,
tested in `tests/test_project_order_inquiry.py`), the handover attachment (`handover_xlsx`)
and the handover email's own line order, which must match the attachment's.
"""
from __future__ import annotations

import io
from datetime import date

import openpyxl

from app.services import order_inquiry_export
from app.services.order_inquiry_export import HEADINGS

OWNER_HEADER = [
    "SO DATE",
    "S/O NO",
    "ITEM CODE",
    "QTY",
    "DELIVERY DATE",
    "PROJECT/CUSTOMER",
    "LOCATION",
    "REMARK",
]


def _sheet(content: bytes):
    workbook = openpyxl.load_workbook(io.BytesIO(content))
    assert len(workbook.worksheets) == 1, workbook.sheetnames
    return workbook.worksheets[0]


def _header(sheet):
    return [cell.value for cell in sheet[1]]


def _body(sheet):
    return [[cell.value for cell in row] for row in sheet.iter_rows(min_row=2)]


def _day(value):
    return value.date() if hasattr(value, "date") else value


# --------------------------------------------------------------------------- #
# The exporter itself (no database)
# --------------------------------------------------------------------------- #


def test_the_owners_header_is_the_shared_heading_row():
    assert list(HEADINGS) == OWNER_HEADER


def test_rows_go_by_so_then_delivery_date_earliest_first():
    records = [
        {"S/O NO": "SO2", "DELIVERY DATE": date(2026, 11, 1), "ITEM CODE": "B"},
        {"S/O NO": "SO1", "DELIVERY DATE": date(2026, 12, 1), "ITEM CODE": "A"},
        {"S/O NO": "SO1", "DELIVERY DATE": None, "ITEM CODE": "UNDATED"},
        {"S/O NO": "", "DELIVERY DATE": date(2026, 1, 1), "ITEM CODE": "NO-SO"},
        {"S/O NO": "SO1", "DELIVERY DATE": date(2026, 10, 5), "ITEM CODE": "C"},
        {"S/O NO": "SO2", "DELIVERY DATE": date(2026, 10, 1), "ITEM CODE": "D"},
    ]
    got = [r["ITEM CODE"] for r in order_inquiry_export.ordered(records)]
    # SO1's lines by date (undated last), then SO2's, then the row with no S/O.
    assert got == ["C", "A", "UNDATED", "D", "B", "NO-SO"]


def test_emailed_dd_mm_yyyy_dates_sort_as_dates_not_text():
    records = [
        {"S/O NO": "SO1", "DELIVERY DATE": "02/12/2026", "ITEM CODE": "DEC"},
        {"S/O NO": "SO1", "DELIVERY DATE": "15/11/2026", "ITEM CODE": "NOV"},
    ]
    got = [r["ITEM CODE"] for r in order_inquiry_export.ordered(records)]
    assert got == ["NOV", "DEC"]


def test_a_continued_row_stays_under_the_row_it_continues():
    records = [
        {"S/O NO": "SO1", "DELIVERY DATE": date(2026, 12, 1), "ITEM CODE": "SPLIT"},
        {"S/O NO": "SO1", "DELIVERY DATE": None, "ITEM CODE": None, "_continued": True},
        {"S/O NO": "SO1", "DELIVERY DATE": date(2026, 11, 1), "ITEM CODE": "EARLY"},
    ]
    got = [r["ITEM CODE"] for r in order_inquiry_export.ordered(records)]
    assert got == ["EARLY", "SPLIT", None]


def test_the_shared_workbook_starts_with_the_header_row_and_sorts():
    content = order_inquiry_export.xlsx(
        [
            {"S/O NO": "SO2", "DELIVERY DATE": date(2026, 10, 1), "ITEM CODE": "X"},
            {"S/O NO": "SO1", "DELIVERY DATE": date(2026, 10, 2), "ITEM CODE": "Y"},
        ]
    )
    sheet = _sheet(content)
    assert _header(sheet) == OWNER_HEADER
    assert [row[1] for row in _body(sheet)] == ["SO1", "SO2"]


def test_the_pdf_has_no_title_above_the_table():
    from app.services import order_inquiry_pdf

    html = order_inquiry_pdf.build_html(HEADINGS, [])
    assert "ORDER INQUIRY" not in html
    assert "<h1" not in html


# --------------------------------------------------------------------------- #
# The handover attachment and the email it rides on (no database)
# --------------------------------------------------------------------------- #


def _line(so, item, day, **extra):
    return {
        "so_date": "01/10/2026",
        "so_number": so,
        "item_code": item,
        "qty": "1",
        "delivery_date": day,
        "customer": "Cust",
        "project": None,
        "location": "KL",
        "remark": "",
        **extra,
    }


def test_the_handover_attachment_starts_with_the_header_and_sorts_by_so_then_date():
    from app.services.order_inquiry_worklist_service import handover_xlsx

    sheet = _sheet(
        handover_xlsx(
            [
                _line("SO2", "B", "01/10/2026"),
                _line("SO1", "LATE", "20/12/2026"),
                _line("SO1", "EARLY", "05/11/2026"),
            ]
        )
    )
    assert _header(sheet) == OWNER_HEADER
    body = _body(sheet)
    assert [(row[1], row[2]) for row in body] == [
        ("SO1", "EARLY"),
        ("SO1", "LATE"),
        ("SO2", "B"),
    ]


def test_the_handover_email_lines_are_in_the_attachments_order():
    """email = preview = attachment: the email's line table is sorted by the same rule, so
    the attachment written from those lines prints them in the same order."""
    from app.services.order_inquiry_worklist_service import handover_xlsx
    from app.services.project_order_inquiry_service import _build_handover_context

    def item(so, line_no, item_code, day, continued=False):
        return {
            "so_number": so,
            "line_no": line_no,
            "item_code": item_code,
            "pso_id": so,
            "order_inquiry_id": "oi-1",
            "so_line_id": f"{so}-{line_no}",
            "row_id": f"{so}-{line_no}-{item_code}",
            "line": _line(so, item_code, day, continued=continued),
        }

    pending = [
        # Line 1 is due LATER than line 2, so SO-then-line-no and SO-then-date disagree.
        item("SO1", 1, "L1", "20/12/2026"),
        item("SO1", 1, "L1", "25/12/2026", continued=True),
        item("SO1", 2, "L2", "05/11/2026"),
        item("SO0", 9, "Z", "01/01/2027"),
    ]
    context, _source = _build_handover_context(pending)
    lines = context["handover"]["lines"]
    assert [(l["so_number"], l["item_code"], l["delivery_date"]) for l in lines] == [
        ("SO0", "Z", "01/01/2027"),
        ("SO1", "L2", "05/11/2026"),
        ("SO1", "L1", "20/12/2026"),
        ("SO1", "L1", "25/12/2026"),
    ]
    sheet = _sheet(handover_xlsx(lines))
    # The continued row prints no item code of its own (the email's own split layout).
    assert [(row[1], row[2]) for row in _body(sheet)] == [
        ("SO0", "Z"),
        ("SO1", "L2"),
        ("SO1", "L1"),
        ("SO1", None),
    ]


# --------------------------------------------------------------------------- #
# The list page's Excel / PDF and the planning-board worksheet (database)
# --------------------------------------------------------------------------- #

from tests.scm.conftest import requires_pg  # noqa: E402
from tests.scm.test_order_summary_sheet import MARKER, _scope_row  # noqa: E402
from tests.scm.test_summary_order_service import chain, db  # noqa: E402,F401


def _seed(db, product):
    """Two sales orders: SO B (one line, due earliest of all) seeded first, then SO A with a
    December row and an October row, so neither seeding order nor date alone gives the
    S/O-then-date order. S/O A sorts before S/O B."""
    from app.models.project_so import OrderInquiryRow

    so_a, so_b = f"{MARKER}-A-SO", f"{MARKER}-B-SO"
    b = _scope_row(db, product=product, qty=1, delivery=date(2026, 9, 1), so_number=so_b)
    a = _scope_row(db, product=product, qty=2, delivery=date(2026, 12, 1), so_number=so_a)
    # The sheet prints the project SO's AutoCount number (`_SO_NUMBER`).
    a["pso"].autocount_doc_no = so_a
    b["pso"].autocount_doc_no = so_b
    first = a["row"]
    sibling = OrderInquiryRow(
        order_inquiry_id=first.order_inquiry_id, so_line_id=first.so_line_id, qty=3,
        verb=first.verb, state=first.state, ack_state=first.ack_state,
        delivery_date=date(2026, 10, 1), supply_decision_id=None,
    )
    db.add(sibling)
    db.flush()
    return so_a, so_b, [b["row"], first, sibling]


@requires_pg
def test_the_list_export_starts_with_the_header_and_sorts_by_so_then_date(db, chain):
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    so_a, so_b, seeded = _seed(db, chain["product"])
    row_ids = [row.id for row in seeded]

    _filename, content = OrderInquiryWorklistService(db).export_xlsx(row_ids=row_ids)
    sheet = _sheet(content)
    assert _header(sheet) == OWNER_HEADER
    body = _body(sheet)
    assert [(row[1], _day(row[4]), row[3]) for row in body] == [
        (so_a, date(2026, 10, 1), 3.0),
        (so_a, date(2026, 12, 1), 2.0),
        (so_b, date(2026, 9, 1), 1.0),
    ]


@requires_pg
def test_the_list_pdf_prints_the_same_header_and_order(db, chain, monkeypatch):
    from app.services import order_inquiry_pdf
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    printed = {}
    monkeypatch.setattr(
        order_inquiry_pdf,
        "render_pdf",
        lambda columns, values: printed.update(columns=list(columns), values=values) or b"%PDF",
    )
    so_a, so_b, seeded = _seed(db, chain["product"])

    OrderInquiryWorklistService(db).export_pdf(row_ids=[row.id for row in seeded])
    assert printed["columns"] == OWNER_HEADER
    assert [(row[1], row[4]) for row in printed["values"]] == [
        (so_a, date(2026, 10, 1)),
        (so_a, date(2026, 12, 1)),
        (so_b, date(2026, 9, 1)),
    ]


@requires_pg
def test_the_worksheet_starts_with_its_header_and_sorts_by_so_then_date(db, chain):
    from app.services.order_inquiry_worklist_service import (
        WORKSHEET_HEADINGS,
        OrderInquiryWorklistService,
    )

    so_a, so_b, seeded = _seed(db, chain["product"])

    _filename, content = OrderInquiryWorklistService(db).export_xlsx(
        row_ids=[row.id for row in seeded], columns=WORKSHEET_HEADINGS
    )
    sheet = _sheet(content)
    assert _header(sheet) == list(WORKSHEET_HEADINGS)
    assert "TOTAL QTY" not in WORKSHEET_HEADINGS
    so_col = list(WORKSHEET_HEADINGS).index("S/O NO")
    date_col = list(WORKSHEET_HEADINGS).index("DELIVERY DATE")
    assert [(row[so_col], _day(row[date_col])) for row in _body(sheet)] == [
        (so_a, date(2026, 10, 1)),
        (so_a, date(2026, 12, 1)),
        (so_b, date(2026, 9, 1)),
    ]


# --------------------------------------------------------------------------- #
# The reserve email's table follows the OI export's order (no database)
# --------------------------------------------------------------------------- #


def test_the_reserve_email_table_goes_by_so_then_delivery_date():
    from app.services.order_inquiry_reserve_service import merged_context

    def context(inquiry_no, so_number, rows):
        return {
            "reserve": {
                "inquiry_no": inquiry_no,
                "so_number": so_number,
                "so_date": "01/10/2026",
                "customer": "Cust",
                "project_customer": "Cust",
                "oi_link": f"https://crm/oi/{inquiry_no}",
                "link": f"https://crm/oi/{inquiry_no}?reserve=1",
                "rows": [
                    {
                        "item_code": code,
                        "delivery_iso": iso,
                        "delivery_date": iso,
                        "qty": "1",
                        "qty_requested": "1",
                        "status": "Reserved",
                        "status_kind": "reserved",
                    }
                    for code, iso in rows
                ],
                "row_count": len(rows),
                "open_row_count": 0,
            },
            "raiser": None,
        }

    merged = merged_context(
        [
            context("OI-2", "SO2", [("AAA", "2026-09-01")]),
            context("OI-1", "SO1", [("AAA", "2026-12-01"), ("ZZZ", "2026-10-01"), ("MMM", None)]),
        ]
    )
    got = [(line["so_number"], line["item_code"]) for line in merged["reserve"]["lines"]]
    assert got == [("SO1", "ZZZ"), ("SO1", "AAA"), ("SO1", "MMM"), ("SO2", "AAA")]
