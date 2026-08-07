"""A GRN received against several SPOs imports, and does not poison the file.

The reported failure: GR-001121's "Transfer from" cell held four SPO numbers
("SPO-2026/06-0020, SPO-2026/06-0021, ..."), 71 characters into
`picking_headers.spo_number varchar(50)`:

    (psycopg2.errors.StringDataRightTruncation) value too long for type
    character varying(50)

Two defects, one cell:

1. `spo_number` is SCALAR - every consumer normalizes it as ONE SPO
   (`_spo_match_key`, `procurement_service._spo_group_key`). Widening the column
   would have traded a loud error for a silent one: the joined blob matches no
   allocation and no packing list. A multi-SPO GRN has no single owner, so the
   header stays NULL and the per-line SPO carries the truth.
2. `upsert_grn_header_for_import` commits per row, and the import loop caught the
   exception without rolling back - so every LATER row died with "transaction has
   been rolled back due to a previous exception". One bad cell failed the whole
   file and the job report blamed rows that were fine.
"""
from __future__ import annotations

import uuid
from io import BytesIO

import openpyxl
import pytest

from app.models.base import set_company_scope
from app.models.procurement import PickingHeader
from app.tasks.import_tasks import _run_grn_listing_import_core

from ._pg_fixture import blank_session, unique_code

HEADERS = ["Doc Number", "Date", "Transfer From"]
FOUR_SPOS = (
    "SPO-2026/06-0020, SPO-2026/06-0021, SPO-2026/06-0022, SPO-2026/06-0023"
)


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, None)
        yield session


def _workbook(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _header(db, picking_number: str) -> PickingHeader:
    return (
        db.query(PickingHeader)
        .filter(PickingHeader.picking_number == picking_number)
        .one()
    )


def test_a_multi_spo_grn_imports_with_a_null_header_spo(db):
    grn = unique_code("GR")[:50]

    result = _run_grn_listing_import_core(db, _workbook([[grn, "2026-06-25", FOUR_SPOS]]))

    assert result["failed"] == 0, result["errors"]
    assert result["successful"] == 1
    assert _header(db, grn).spo_number is None, (
        "a GRN received against 4 SPOs has no single owner; the scalar column must "
        "stay NULL rather than hold a blob no consumer can match"
    )


def test_a_single_spo_grn_still_stores_it(db):
    grn = unique_code("GR")[:50]

    result = _run_grn_listing_import_core(
        db, _workbook([[grn, "2026-06-25", " SPO-2026/06-0020 "]])
    )

    assert result["failed"] == 0, result["errors"]
    assert _header(db, grn).spo_number == "SPO-2026/06-0020"


def test_semicolon_and_newline_separated_cells_are_split_too(db):
    """AutoCount is not consistent about the separator it exports."""
    semi, newline = unique_code("GR")[:50], unique_code("GR")[:50]

    result = _run_grn_listing_import_core(
        db,
        _workbook(
            [
                [semi, "2026-06-25", "SPO-2026/06-0020;SPO-2026/06-0021"],
                [newline, "2026-06-25", "SPO-2026/06-0020\nSPO-2026/06-0021"],
            ]
        ),
    )

    assert result["failed"] == 0, result["errors"]
    assert _header(db, semi).spo_number is None
    assert _header(db, newline).spo_number is None


def test_an_over_length_single_spo_is_skipped_with_a_reason(db):
    """Not a multi-SPO cell - one absurd value. Skip the row and say why, instead
    of letting Postgres abort the transaction."""
    grn = unique_code("GR")[:50]
    too_long = "SPO-" + "9" * 60

    result = _run_grn_listing_import_core(db, _workbook([[grn, "2026-06-25", too_long]]))

    assert result["failed"] == 0
    assert result["skipped"] == 1
    assert any("longer than 50" in d["reason"] for d in result["skipped_rows_detail"])
    assert (
        db.query(PickingHeader).filter(PickingHeader.picking_number == grn).first()
        is None
    )


def test_one_failing_row_does_not_fail_the_rest_of_the_file(db):
    """The cascade: a per-row commit loop must rollback on failure, or every later
    row reports someone else's exception."""
    before, after = unique_code("GR")[:50], unique_code("GR")[:50]
    # A picking_number over the column width fails inside the upsert itself, which
    # is the shape the original truncation took: an aborted transaction mid-loop.
    poison = "GR-" + "8" * 80

    result = _run_grn_listing_import_core(
        db,
        _workbook(
            [
                [before, "2026-06-25", "SPO-2026/06-0020"],
                [poison, "2026-06-25", "SPO-2026/06-0021"],
                [after, "2026-06-25", "SPO-2026/06-0022"],
            ]
        ),
    )

    assert result["failed"] == 1, f"expected only the poison row to fail: {result['errors']}"
    assert result["successful"] == 2
    assert _header(db, before).spo_number == "SPO-2026/06-0020"
    assert _header(db, after).spo_number == "SPO-2026/06-0022", (
        "the row AFTER the failure was lost — the session was never rolled back"
    )
    assert not any(
        "previous exception" in e for e in result["errors"]
    ), f"cascade leaked into the report: {result['errors']}"
