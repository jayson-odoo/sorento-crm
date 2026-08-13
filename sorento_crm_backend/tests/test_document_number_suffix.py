"""The document number carries the revision (UAC-portal-submission-revisions section N).

Two functions, one module, so render and parse can never disagree (N7). These are
pure-function tests plus the round trip that is the actual contract: whatever we
render on an outbound surface must resolve back to the stored number on the way in.

The integration half of section N - a suffixed number posted to the external
create endpoints resubmitting the existing rejected row instead of inserting a
duplicate - lives in ``test_external_number_suffix_lookup.py``, against Postgres.

Run: venv/bin/pytest tests/test_document_number_suffix.py -q
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.document_number import (
    display_document_number,
    split_revision_suffix,
    strip_revision_suffix,
    suffix_revision,
)


def _inquiry(number="SI-26-0184", revision_no=0):
    return SimpleNamespace(inquiry_number=number, revision_no=revision_no)


def _request(number="PR-26-0012", revision_no=0):
    return SimpleNamespace(request_number=number, revision_no=revision_no)


# --------------------------------------------------------------------- render


def test_revision_zero_renders_bare():
    """AC N3: revision 0 is the original, and reads as the plain number."""
    assert display_document_number(_inquiry(revision_no=0)) == "SI-26-0184"
    assert display_document_number(_request(revision_no=0)) == "PR-26-0012"
    assert "-R0" not in display_document_number(_inquiry(revision_no=0))


def test_a_missing_revision_column_renders_bare():
    """Complaints and tickets have no revision_no; they must still render."""
    assert display_document_number(SimpleNamespace(complaint_number="CMP-2026-0001")) == (
        "CMP-2026-0001"
    )


@pytest.mark.parametrize("revision_no,expected", [(1, "-R1"), (2, "-R2"), (11, "-R11")])
def test_a_revised_document_reads_at_its_revision(revision_no, expected):
    assert display_document_number(_inquiry(revision_no=revision_no)) == f"SI-26-0184{expected}"


def test_the_number_column_is_picked_per_type():
    assert display_document_number(_request(revision_no=3)) == "PR-26-0012-R3"
    assert (
        display_document_number(_request(revision_no=3), number_attr="request_number")
        == "PR-26-0012-R3"
    )


def test_a_row_with_no_number_renders_empty_so_callers_keep_their_fallback():
    """Every call site is written as ``display_document_number(row) or str(row.id)``."""
    assert display_document_number(_inquiry(number=None, revision_no=2)) == ""
    assert display_document_number(None) == ""


def test_the_caller_may_override_the_revision_it_holds():
    """The revise transaction renders the NEW number before the row is refreshed."""
    assert display_document_number(_inquiry(revision_no=0), revision_no=2) == "SI-26-0184-R2"


def test_a_suffix_is_never_stacked():
    assert suffix_revision("SI-26-0184-R1", 2) == "SI-26-0184-R2"


def test_blank_and_none_render_empty():
    assert suffix_revision(None, 2) == ""
    assert suffix_revision("   ", 2) == ""


@pytest.mark.parametrize("revision_no", [None, 0, -1, "", "not a number"])
def test_a_non_positive_or_unreadable_revision_renders_bare(revision_no):
    assert suffix_revision("SI-26-0184", revision_no) == "SI-26-0184"


# ---------------------------------------------------------------------- strip


def test_strip_returns_the_stored_number():
    assert strip_revision_suffix("SI-26-0184-R2") == "SI-26-0184"
    assert strip_revision_suffix("PR-26-0012-R11") == "PR-26-0012"


def test_strip_leaves_a_bare_number_alone():
    assert strip_revision_suffix("SI-26-0184") == "SI-26-0184"


def test_strip_passes_none_through_so_callers_need_no_pre_test():
    assert strip_revision_suffix(None) is None


def test_strip_only_removes_a_TRAILING_marker():
    """"-R2" mid-string is part of somebody's number, not our suffix."""
    assert strip_revision_suffix("SI-R2-0184") == "SI-R2-0184"


def test_strip_is_case_insensitive_because_humans_retype_these():
    assert strip_revision_suffix("si-26-0184-r2") == "si-26-0184"


def test_split_reports_the_revision_it_removed():
    assert split_revision_suffix("SI-26-0184-R2") == ("SI-26-0184", 2)
    assert split_revision_suffix("SI-26-0184") == ("SI-26-0184", None)


# ----------------------------------------------------------------- round trip


@pytest.mark.parametrize("revision_no", [0, 1, 2, 7, 42])
def test_round_trip_stock_inquiry(revision_no):
    """The contract: anything we render resolves back to the STORED number.

    Both halves live in one module precisely so this can never drift (N7).
    """
    row = _inquiry(revision_no=revision_no)
    assert strip_revision_suffix(display_document_number(row)) == row.inquiry_number


@pytest.mark.parametrize("revision_no", [0, 1, 2, 7, 42])
def test_round_trip_purchase_request(revision_no):
    row = _request(revision_no=revision_no)
    assert strip_revision_suffix(display_document_number(row)) == row.request_number
