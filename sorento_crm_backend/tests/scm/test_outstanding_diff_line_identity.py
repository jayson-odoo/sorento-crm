"""Slice A, AC-A5a (`documentation/plans/scm/PLAN-scm-change-management-one-engine.md`):
`outstanding_diff.Line` gains an optional `line_id`, and `diff_lines` pairs a before/after
sharing the SAME `line_id` FIRST, ahead of today's (doc, item, location) + date-order
fallback - so a product swap on the SAME line reads as one `product_changed` row rather than
a `closed` plus an unrelated `added`.

Pure functions, no database - same style as `test_outstanding_diff.py`, which this file sits
beside rather than edits: every existing case there (lines with no `line_id`) must keep
pairing exactly as it does today, unaffected by this new identity path.
"""
from __future__ import annotations

from datetime import date

from app.services.scm.outstanding_diff import ADDED, CLOSED, Line, diff_lines

JUL1 = date(2026, 7, 1)


def kinds(diff):
    return sorted(c.kind for c in diff.changes)


# --------------------------------------------------------------------------- #
# a product swap on the SAME line_id is one PRODUCT_CHANGED change, not a
# closed + added pair
# --------------------------------------------------------------------------- #

def test_diff_lines_pairs_by_line_id_and_reads_a_product_swap_as_one_change():
    """Today `Line` has no `line_id` field at all - constructing one with it raises
    `TypeError: unexpected keyword argument 'line_id'`, the expected red until the coder
    adds it."""
    lid = "core-line-1"
    existing = [Line(doc_number="SO1", item_code="A", location="BRW-BB", qty=10.0,
                     required_date=JUL1, line_id=lid)]
    incoming = [Line(doc_number="SO1", item_code="B", location="BRW-BB", qty=10.0,
                     required_date=JUL1, line_id=lid)]

    diff = diff_lines(existing, incoming)

    assert len(diff.changes) == 1, [c.kind for c in diff.changes]
    change = diff.changes[0]
    from app.services.scm.outstanding_diff import PRODUCT_CHANGED

    assert change.kind == PRODUCT_CHANGED
    assert change.before.item_code == "A"
    assert change.after.item_code == "B"


# --------------------------------------------------------------------------- #
# line_id identity beats the (doc, item, location) + date-order fallback: two
# DIFFERENT line_ids that happen to share item/location/qty/date must NOT be
# read as one unchanged pair - each must classify independently
# --------------------------------------------------------------------------- #

def test_a_line_id_pair_with_no_match_on_either_side_closes_the_old_and_adds_the_new():
    """Without line_id awareness these two rows share (doc, item, location) and an
    identical date/qty, so today's pass-2 date-order pairing zips them into ONE
    `unchanged` change - silently losing the fact that a SPECIFIC line left the book and a
    DIFFERENT one arrived. Once line_id is honoured, `gone` (no matching incoming line_id)
    must close and `new` (no matching existing line_id) must add - two changes, not one."""
    existing = [Line(doc_number="SO1", item_code="A", location="BRW-BB", qty=10.0,
                     required_date=JUL1, line_id="gone")]
    incoming = [Line(doc_number="SO1", item_code="A", location="BRW-BB", qty=10.0,
                     required_date=JUL1, line_id="new")]

    diff = diff_lines(existing, incoming)

    assert kinds(diff) == sorted([CLOSED, ADDED]), [c.kind for c in diff.changes]
    closed = diff.of_kind(CLOSED)[0]
    added = diff.of_kind(ADDED)[0]
    assert closed.before.line_id == "gone"
    assert added.after.line_id == "new"


# --------------------------------------------------------------------------- #
# after qty 0 on a line_id-matched pair still closes, even though the item
# code also differs - settlement outranks a product swap
# --------------------------------------------------------------------------- #

def test_a_line_id_pair_settling_to_zero_closes_even_with_a_different_item_code():
    lid = "core-line-2"
    existing = [Line(doc_number="SO1", item_code="A", location="BRW-BB", qty=10.0,
                     required_date=JUL1, line_id=lid)]
    incoming = [Line(doc_number="SO1", item_code="B", location="BRW-BB", qty=0.0,
                     required_date=JUL1, line_id=lid)]

    diff = diff_lines(existing, incoming)

    assert kinds(diff) == [CLOSED], [c.kind for c in diff.changes]
