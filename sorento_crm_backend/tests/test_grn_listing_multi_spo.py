"""A GRN received against several SPOs imports, and does not poison the file.

The reported failure: GR-001121's "Transfer from" cell held four SPO numbers
("SPO-2026/06-0020, SPO-2026/06-0021, ..."), 71 characters into
`picking_headers.spo_number varchar(50)`:

    (psycopg2.errors.StringDataRightTruncation) value too long for type
    character varying(50)

Two defects, one cell:

1. The column was too narrow. Migration 314 widens it to 255 and the header now
   records EVERY SPO the GRN covers, so the list says "covers these four" instead
   of showing a dash. That column is DISPLAY for this case: matching is scalar and
   stays scalar (`_spo_match_key` and `_normalize_spo_number` compare ONE
   normalized SPO), so a joined value equals no single SPO and cannot false-link.
   The per-line SPO drives allocation matching, and a multi-SPO line stays
   unlinked rather than carrying an unmatchable string.
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
from app.services.procurement_service import _normalize_spo_number, _spo_match_key
from app.tasks.import_tasks import _SPO_NUMBER_MAX_LEN, _run_grn_listing_import_core

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


def test_a_multi_spo_grn_imports_and_records_every_spo(db):
    grn = unique_code("GR")[:50]

    result = _run_grn_listing_import_core(db, _workbook([[grn, "2026-06-25", FOUR_SPOS]]))

    assert result["failed"] == 0, result["errors"]
    assert result["successful"] == 1
    assert _header(db, grn).spo_number == FOUR_SPOS, (
        "the header should say which SPOs the GRN covers, not show a dash"
    )


def test_a_multi_spo_header_matches_no_single_spo(db):
    """The reason the width increase is safe: every consumer compares ONE
    normalized SPO, so a joined value matches nothing rather than the wrong
    allocation."""
    grn = unique_code("GR")[:50]
    _run_grn_listing_import_core(db, _workbook([[grn, "2026-06-25", FOUR_SPOS]]))

    stored = _header(db, grn).spo_number
    assert stored is not None
    for one in FOUR_SPOS.split(", "):
        assert _spo_match_key(stored) != _spo_match_key(one), (
            f"joined header value collided with the single SPO {one}"
        )
        assert _normalize_spo_number(stored) != _normalize_spo_number(one)


def test_a_single_spo_grn_still_stores_it(db):
    grn = unique_code("GR")[:50]

    result = _run_grn_listing_import_core(
        db, _workbook([[grn, "2026-06-25", " SPO-2026/06-0020 "]])
    )

    assert result["failed"] == 0, result["errors"]
    assert _header(db, grn).spo_number == "SPO-2026/06-0020"


def test_every_separator_normalizes_to_one_stored_form(db):
    """AutoCount is not consistent about the separator it exports, and the same
    GRN must not read differently depending on which one it used."""
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
    expected = "SPO-2026/06-0020, SPO-2026/06-0021"
    assert _header(db, semi).spo_number == expected
    assert _header(db, newline).spo_number == expected


def test_a_value_past_the_widened_width_is_skipped_with_a_reason(db):
    """Past 255 even the widened column cannot hold it. Skip the row and say why,
    instead of letting Postgres abort the transaction."""
    grn = unique_code("GR")[:50]
    too_long = "SPO-" + "9" * (_SPO_NUMBER_MAX_LEN + 10)

    result = _run_grn_listing_import_core(db, _workbook([[grn, "2026-06-25", too_long]]))

    assert result["failed"] == 0
    assert result["skipped"] == 1
    assert any(
        f"longer than {_SPO_NUMBER_MAX_LEN}" in d["reason"]
        for d in result["skipped_rows_detail"]
    )
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
