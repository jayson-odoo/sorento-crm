"""A GRN LINE says which SPO it was received against; the header is the fallback.

Until now the only SPO linkage was the GRN header's "Transfer from" cell, so a
GRN received against several SPOs could name only one of them (or, when the cell
held all four, none - a joined value matches no single SPO by design). The
AutoCount GRN DETAIL listing carries the SPO on the line itself, in a column
called "Our PO No.", which is the linkage the business actually keys on.

The resolution order is: the line's own column, then the sheet's repeated header
column, then - in the import loop - the GRN header's stored `spo_number`.
"""
from __future__ import annotations

import pytest

from app.tasks.import_tasks import (
    _grn_import_normalize_header,
    _resolve_line_spo,
)


def _row(**cells) -> dict:
    """Build a parsed row the way the importer does: normalized header -> value."""
    return {_grn_import_normalize_header(k): v for k, v in cells.items()}


def test_the_lines_own_po_column_is_read():
    row = _row(**{"Our PO No.": "SPO-2026/06-0056"})

    assert _resolve_line_spo(row) == "SPO-2026/06-0056"


def test_the_line_beats_the_repeated_header_column():
    """A GRN received against several SPOs: the header cell cannot tell this line
    apart from its siblings, the line's own column can."""
    row = _row(
        **{
            "Transfer From": "SPO-2026/06-0020",
            "Our PO No.": "SPO-2026/06-0056",
        }
    )

    assert _resolve_line_spo(row) == "SPO-2026/06-0056"


def test_a_blank_line_column_falls_through_to_the_header_column():
    """The regression this guards: a present-key lookup stops at the empty line
    column and loses the fallback, leaving every line of the file unlinked."""
    for blank in (None, "", "   "):
        row = _row(**{"Our PO No.": blank, "Transfer From": "SPO-2026/06-0020"})

        assert _resolve_line_spo(row) == "SPO-2026/06-0020", f"blank={blank!r}"


def test_no_spo_column_at_all_resolves_to_none():
    """Then the import loop falls back to the GRN header's stored spo_number."""
    row = _row(**{"Doc No": "GR-2026/07-0148", "Item Code": "ABC", "Qty": 3})

    assert _resolve_line_spo(row) is None


def test_a_multi_spo_line_cell_names_no_single_allocation():
    """Same scalar rule as the header: a joined value would match nothing, so the
    line stays unlinked rather than carrying an unmatchable string."""
    row = _row(**{"Our PO No.": "SPO-2026/06-0020, SPO-2026/06-0021"})

    assert _resolve_line_spo(row) is None


@pytest.mark.parametrize(
    "spelling",
    ["Our PO No.", "Our P.O. No", "OUR PO NUMBER", "our po no", "From Doc. No."],
)
def test_the_column_is_matched_punctuation_and_case_insensitively(spelling):
    row = _row(**{spelling: "SPO-2026/06-0056"})

    assert _resolve_line_spo(row) == "SPO-2026/06-0056"


def test_a_local_po_on_the_line_is_carried_through_verbatim():
    """Local purchases receive against a PO, not an SPO. It is not an SPO match,
    so the line simply gets no allocation - it must not be rewritten or dropped
    on the way in."""
    row = _row(**{"Our PO No.": "PO-2026/03-0037"})

    assert _resolve_line_spo(row) == "PO-2026/03-0037"
