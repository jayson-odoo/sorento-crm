"""Two rows sharing a document, item and location are DATA, not a spreadsheet accident.

Measured against the captain's real outstanding-SO export: 605 groups share
`(doc, item, location)`. 567 of them differ in quantity, price or remaining figure - SO339706
carries the same item twice at 31 and at 20, which is one order asking for two deliveries and
is exactly what the plan has to see. The other 38 are byte-identical, and the captain's
ruling is "this is totally acceptable in 1 SO".

So the reader's "the same line is stated twice" complaint was wrong on both halves: it fired
on 605 groups of which 567 are unambiguously distinct lines, and it fired on the 38 that are
legitimate. It never blocked anything - the row was always kept - but a report that cries
wolf 605 times is a report the operator stops reading, and these are the same lists that
carry the rows that really did fail.

Identity within a group is positional and lives in `outstanding_diff` (AC-2.2): exact-date
matches pair first, leftovers pair in date order, surplus incoming inserts and surplus
existing closes. That is the single authority, and these tests pin what it means for the two
shapes the captain's file actually contains.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import SO
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import Codes, make_codes, seed_catalogue, workbook

HEADERS = ("S/O NO", "DEBTOR CODE", "ITEM CODE", "QTY", "DELIVERY DATE", "STOCK LOCATION")

DUE = date(2026, 7, 1)


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def seeded(db):
    codes = make_codes()
    seed_catalogue(db, codes)
    return codes


def _file(codes: Codes, *quantities: float) -> bytes:
    """One document, one item, one location, one date - stated once per quantity given."""
    return workbook(
        [(codes.project_so, "300-T012", codes.item_rl, qty, DUE, codes.loc_project)
         for qty in quantities],
        headers=HEADERS,
    )


def _open_lines(db, codes: Codes) -> list[float]:
    return [float(r[0]) for r in db.execute(text("""
        SELECT l.qty_ordered - l.qty_delivered
        FROM sales_order_lines l
        JOIN sales_orders o ON o.id = l.sales_order_id
        WHERE o.so_number = :n AND l.line_status = 'open'
        ORDER BY 1
    """), {"n": codes.project_so}).all()]


def _reported(payload: dict) -> list[str]:
    out: list[str] = []
    for item in (list(payload.get("resolution_issues") or [])
                 + list(payload.get("row_problems") or [])):
        out.append(" ".join(str(v) for v in item.values()))
    return out


def _stated_twice_complaints(payload: dict) -> list[str]:
    return [line for line in _reported(payload) if "stated twice" in line]


# --------------------------------------------------------------------------- #
# 1. the 567: two genuinely different lines (AC-2.1)
# --------------------------------------------------------------------------- #

def test_two_lines_differing_only_in_quantity_both_load_and_nothing_is_complained_about(db, seeded):
    """SO339706's shape: 31 and 20 of one item, same location, same date.

    Losing either half understates what the customer is owed and understates the buy. The old
    reader kept both, but reported the second as a duplicate - so the operator's list of rows
    to look at was 605 entries long on a file with nothing wrong with it.
    """
    out = svc.apply(db, _file(seeded, 31, 20), SO)

    assert out["ok"]
    assert _open_lines(db, seeded) == [20.0, 31.0]
    assert _stated_twice_complaints(out) == []


def test_the_preview_of_a_duplicated_key_promises_what_the_commit_does(db, seeded):
    """Preview and apply build the same diff, so the count the operator confirms has to be
    the count they get. Two rows, two additions, no complaints."""
    preview = svc.preview(db, _file(seeded, 31, 20), SO).to_dict()

    assert preview["counts"]["added"] == 2
    assert _stated_twice_complaints(preview) == []

    applied = svc.apply(db, _file(seeded, 31, 20), SO)
    assert applied["applied"]["added"] == 2


# --------------------------------------------------------------------------- #
# 2. the 38: byte-identical rows (AC-2.4)
# --------------------------------------------------------------------------- #

def test_two_byte_identical_rows_both_load_without_complaint(db, seeded):
    """The captain: "this is totally acceptable in 1 SO".

    Which incoming row pairs with which existing row is arbitrary here and cannot be
    otherwise - the two are indistinguishable in every field - and it is harmless for exactly
    that reason: either assignment leaves the same database state.
    """
    out = svc.apply(db, _file(seeded, 25, 25), SO)

    assert out["ok"]
    assert _open_lines(db, seeded) == [25.0, 25.0]
    assert _stated_twice_complaints(out) == []


# --------------------------------------------------------------------------- #
# 3. re-uploading the same file changes nothing (AC-2.3)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("quantities", [(31, 20), (25, 25)])
def test_re_importing_the_same_file_reads_unchanged(db, seeded, quantities):
    """Idempotency is what makes the removal safe.

    The complaint's stated fear was that the second copy would pair with nothing, be ADDED,
    and double the demand stably enough that no later upload surfaced it. Grouped pairing is
    the answer: on the second run both incoming rows meet the two lines the first run wrote,
    and both read `unchanged`. Asserted for both shapes, because "identical" is the half where
    an implementation that paired by content alone would still have been correct.
    """
    file = _file(seeded, *quantities)
    svc.apply(db, file, SO)

    out = svc.apply(db, file, SO)

    assert out["counts"]["unchanged"] == 2
    assert out["applied"] == {"added": 0, "updated": 0, "closed": 0, "unchanged": 2}
    assert _open_lines(db, seeded) == sorted(float(q) for q in quantities)


def test_dropping_one_of_two_duplicated_lines_closes_exactly_one(db, seeded):
    """The surplus-existing half of the pairing rule, on the shape it is hardest to reason
    about. Two identical lines, one delivered: the file now states one, so one closes and one
    stays open - not both, and not neither."""
    svc.apply(db, _file(seeded, 25, 25), SO)

    out = svc.apply(db, _file(seeded, 25), SO)

    assert out["applied"]["closed"] == 1
    assert _open_lines(db, seeded) == [25.0]
