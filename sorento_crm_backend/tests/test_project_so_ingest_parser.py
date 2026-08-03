"""Reading an AutoCount sales order export into the canonical document (P8a, stage 1).

The stage 1 transport is a file a CS exports from AutoCount and uploads. Its exact layout
has not been seen yet (recorded as the open risk in `PLAN-project-so-divergence.md`), so
the parser reads by column HEADING with synonyms rather than by position: a column moved
or renamed slightly must not silently shift every quantity one place left.

The round trip our own import file makes is the case that must always work, because that
is the document the CS actually has in front of them.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

import openpyxl
import pytest

from app.services.error_handler import AppException
from app.services.project_so_ingest_parser import parse_document

OUR_IMPORT_FILE = """Provisional Ref,ZZT-PSO-1234
Debtor,SLG CONSTRUCTION SDN BHD
Your Ref No.,PO-778
Our Ref No.,Tuju Residences
Our QT Ref No.,TOWER v2
Terms,*Net 60 days
Doc No.,SO397450

***TOWER***
Item,Description,Reserve Qty,Qty,Delivery Date,UOM,U/Price,Disc.,Total
CB6633,600mm grating,0,600,2026-03-10,UNIT,12.50,,7500.00
AB1200,Wall hung basin,0,40,2026-04-10,SET,300.00,,12000.00

Total,,,,,,,,19500.00
"""


def test_our_own_import_file_round_trips():
    document = parse_document(OUR_IMPORT_FILE.encode("utf-8"), filename="SO397450.csv")

    assert document.doc_no == "SO397450"
    assert document.customer_po_no == "PO-778"
    assert document.area_group == "TOWER"
    assert document.terms == "*Net 60 days"
    assert document.total_amount == Decimal("19500.00")
    assert [line.product_code for line in document.lines] == ["CB6633", "AB1200"]
    assert document.lines[0].qty == Decimal("600")
    assert document.lines[0].unit_price == Decimal("12.50")
    assert document.lines[0].delivery_date == date(2026, 3, 10)
    assert document.lines[1].uom == "SET"


def test_columns_are_read_by_heading_not_by_position():
    body = (
        "Doc No.,SO1\n"
        "Your Ref No.,PO-9\n\n"
        "Delivery Date,U/Price,Item,Qty\n"
        "2026-03-10,12.50,CB6633,600\n"
    )

    document = parse_document(body.encode("utf-8"), filename="x.csv")

    line = document.lines[0]
    assert line.product_code == "CB6633"
    assert line.qty == Decimal("600")
    assert line.unit_price == Decimal("12.50")
    assert line.delivery_date == date(2026, 3, 10)


@pytest.mark.parametrize(
    "heading",
    ["Item", "Item Code", "Stock Code", "Product Code", "ITEM CODE"],
)
def test_the_item_column_is_recognised_however_autocount_labels_it(heading):
    body = f"Doc No.,SO1\nYour Ref No.,PO-9\n\n{heading},Qty,U/Price\nCB6633,600,12.50\n"

    document = parse_document(body.encode("utf-8"), filename="x.csv")

    assert document.lines[0].product_code == "CB6633"


@pytest.mark.parametrize("heading", ["Your Ref No.", "Customer PO", "Cust PO No", "PO No."])
def test_the_customer_po_is_recognised_however_it_is_labelled(heading):
    body = f"Doc No.,SO1\n{heading},PO-778\n\nItem,Qty,U/Price\nCB6633,600,12.50\n"

    assert parse_document(body.encode("utf-8"), filename="x.csv").customer_po_no == "PO-778"


def test_thousands_separators_and_currency_noise_are_read_as_numbers():
    body = (
        "Doc No.,SO1\nYour Ref No.,PO-9\n\n"
        "Item,Qty,U/Price,Total\n"
        'CB6633,"1,810",RM 12.50,"22,625.00"\n'
    )

    line = parse_document(body.encode("utf-8"), filename="x.csv").lines[0]

    assert line.qty == Decimal("1810")
    assert line.unit_price == Decimal("12.50")


@pytest.mark.parametrize(
    "printed,expected",
    [
        ("2026-03-10", date(2026, 3, 10)),
        ("10/03/2026", date(2026, 3, 10)),
        ("10-03-2026", date(2026, 3, 10)),
        ("", None),
    ],
)
def test_the_dates_autocount_prints_are_understood(printed, expected):
    body = (
        "Doc No.,SO1\nYour Ref No.,PO-9\n\n"
        "Item,Qty,U/Price,Delivery Date\n"
        f"CB6633,600,12.50,{printed}\n"
    )

    assert parse_document(body.encode("utf-8"), filename="x.csv").lines[0].delivery_date == expected


def test_a_total_row_is_not_read_as_a_line():
    body = (
        "Doc No.,SO1\nYour Ref No.,PO-9\n\n"
        "Item,Description,Qty,U/Price,Total\n"
        "CB6633,600mm grating,600,12.50,7500.00\n"
        ",Total,,,7500.00\n"
    )

    document = parse_document(body.encode("utf-8"), filename="x.csv")

    assert [line.product_code for line in document.lines] == ["CB6633"]
    assert document.total_amount == Decimal("7500.00")


def test_a_blank_row_between_sections_does_not_end_the_document():
    body = (
        "Doc No.,SO1\nYour Ref No.,PO-9\n\n"
        "Item,Qty,U/Price\n"
        "CB6633,600,12.50\n"
        ",,\n"
        "AB1200,40,300.00\n"
    )

    assert len(parse_document(body.encode("utf-8"), filename="x.csv").lines) == 2


def test_a_file_with_no_recognisable_line_table_is_refused():
    body = "Doc No.,SO1\nYour Ref No.,PO-9\n\nSomething,Else\nfoo,bar\n"

    with pytest.raises(AppException) as exc:
        parse_document(body.encode("utf-8"), filename="x.csv")

    assert exc.value.status_code == 422
    assert "heading" in exc.value.detail["message"].lower()


def test_an_xlsx_export_is_read_the_same_way():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in [
        ["Doc No.", "SO397450"],
        ["Your Ref No.", "PO-778"],
        [],
        ["***TOWER***"],
        ["Item", "Qty", "U/Price", "Delivery Date"],
        ["CB6633", 600, 12.5, date(2026, 3, 10)],
    ]:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)

    document = parse_document(buffer.getvalue(), filename="export.xlsx")

    assert document.doc_no == "SO397450"
    assert document.area_group == "TOWER"
    assert document.lines[0].qty == Decimal("600")
    assert document.lines[0].delivery_date == date(2026, 3, 10)


def test_an_unsupported_file_type_is_refused():
    with pytest.raises(AppException) as exc:
        parse_document(b"%PDF-1.4", filename="scan.pdf")

    assert exc.value.status_code == 422
