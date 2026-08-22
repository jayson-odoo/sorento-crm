"""The upload diff: what a re-uploaded outstanding-orders extract actually changes.

Pure functions, no database. The cases that matter are not the tidy ones - they are the two
shapes the real AutoCount extract produces:

* one sales order carrying the SAME item at two different delivery dates (SO397450 has
  SRTWC8613-RL twice, 135 due 1 Jul and 72 due 3 Aug), and
* a project slipping, which moves those dates and must read as a MOVE rather than as one
  line closing and an unrelated one opening.

If the second case is got wrong the whole feature is pointless, because "the project moved"
is the change this module exists to react to.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.scm.outstanding_diff import (
    ADDED,
    CLOSED,
    DATE_AND_QTY_CHANGED,
    DATE_MOVED,
    QTY_CHANGED,
    UNCHANGED,
    Line,
    diff_lines,
)

JUL1 = date(2026, 7, 1)
JUL15 = date(2026, 7, 15)
AUG3 = date(2026, 8, 3)
AUG25 = date(2026, 8, 25)


def L(doc="SO397450", item="SRTWC8613-RL", loc="BRW-BB", qty=100.0, when=JUL1, ref=None):
    return Line(doc_number=doc, item_code=item, location=loc, qty=qty,
                required_date=when, row_ref=ref)


def kinds(diff):
    return sorted(c.kind for c in diff.changes)


# --------------------------------------------------------------------------- #
# the two real shapes
# --------------------------------------------------------------------------- #

def test_same_item_twice_on_one_order_stays_two_lines():
    """SO397450 carries SRTWC8613-RL at 135 due 1 Jul and 72 due 3 Aug.

    Keying on (doc, item, location) alone would collapse these into one line and lose a
    delivery date, which silently destroys the demand the whole plan is built on.
    """
    existing = [L(qty=135, when=JUL1), L(qty=72, when=AUG3)]
    incoming = [L(qty=135, when=JUL1), L(qty=72, when=AUG3)]

    diff = diff_lines(existing, incoming)

    assert len(diff.changes) == 2
    assert kinds(diff) == [UNCHANGED, UNCHANGED]
    assert diff.has_material_change is False


def test_a_slipped_project_reads_as_a_move_not_a_close_and_an_add():
    """The case the module exists for. 1 Jul slips to 15 Jul; 3 Aug is untouched.

    Keying on (doc, item, location, date) would report this as one line closed and one line
    added, and the plan would look like a cancellation plus a new order rather than a
    reschedule.
    """
    existing = [L(qty=135, when=JUL1), L(qty=72, when=AUG3)]
    incoming = [L(qty=135, when=JUL15), L(qty=72, when=AUG3)]

    diff = diff_lines(existing, incoming)

    assert kinds(diff) == [DATE_MOVED, UNCHANGED]
    moved = diff.of_kind(DATE_MOVED)[0]
    assert moved.before.required_date == JUL1
    assert moved.after.required_date == JUL15
    assert moved.days_moved == 14
    # The line that did NOT move must not be the one reported as moving.
    assert moved.before.qty == 135


def test_the_unmoved_line_pairs_first_even_when_the_other_moves_past_it():
    """Exact-date matching happens before order-based pairing on purpose.

    Here the 1 Jul line slips all the way to 25 Aug, past the 3 Aug line. Pairing purely by
    sorted order would mis-pair: it would call 3 Aug -> 25 Aug the move and 1 Jul -> 3 Aug a
    second one, reporting two moves where there was one.
    """
    existing = [L(qty=135, when=JUL1), L(qty=72, when=AUG3)]
    incoming = [L(qty=72, when=AUG3), L(qty=135, when=AUG25)]

    diff = diff_lines(existing, incoming)

    assert kinds(diff) == [DATE_MOVED, UNCHANGED]
    moved = diff.of_kind(DATE_MOVED)[0]
    assert (moved.before.required_date, moved.after.required_date) == (JUL1, AUG25)


# --------------------------------------------------------------------------- #
# scope is derived from the file
# --------------------------------------------------------------------------- #

def test_an_order_absent_from_the_file_is_untouched_not_closed():
    """A single-project export must never read as every other project being delivered."""
    existing = [L(doc="SO397450"), L(doc="SO400000", item="OTHER")]
    incoming = [L(doc="SO397450")]

    diff = diff_lines(existing, incoming)

    assert diff.scope_documents == ("SO397450",)
    assert all(c.doc_number == "SO397450" for c in diff.changes)
    assert diff.of_kind(CLOSED) == []


def test_a_line_missing_from_an_in_scope_order_is_closed():
    """Within a document that IS in the file, absence means delivered or cancelled."""
    existing = [L(item="A"), L(item="B")]
    incoming = [L(item="A")]

    diff = diff_lines(existing, incoming)

    closed = diff.of_kind(CLOSED)
    assert len(closed) == 1 and closed[0].item_code == "B"
    assert closed[0].after is None


def test_scope_is_reported_sorted_and_deduplicated():
    diff = diff_lines([], [L(doc="SO2"), L(doc="SO1"), L(doc="SO2", item="X")])
    assert diff.scope_documents == ("SO1", "SO2")


# --------------------------------------------------------------------------- #
# change classification
# --------------------------------------------------------------------------- #

def test_quantity_change_on_the_same_date():
    diff = diff_lines([L(qty=135)], [L(qty=100)])
    c = diff.of_kind(QTY_CHANGED)[0]
    assert c.qty_delta == -35
    # Zero, not None: the line demonstrably did not move. `None` is reserved for a move
    # that cannot be measured because a date is missing, and conflating "did not move" with
    # "unknown" would let the screen show a blank where it should show nothing changed.
    assert c.days_moved == 0


def test_date_and_quantity_can_change_together_and_are_reported_as_one_change():
    """Two separate rows would double-count the line on the confirm screen."""
    diff = diff_lines([L(qty=135, when=JUL1)], [L(qty=100, when=JUL15)])
    assert kinds(diff) == [DATE_AND_QTY_CHANGED]
    c = diff.changes[0]
    assert (c.qty_delta, c.days_moved) == (-35, 14)


def test_a_new_line_on_an_existing_order_is_added():
    diff = diff_lines([L(item="A")], [L(item="A"), L(item="B")])
    assert [c.item_code for c in diff.of_kind(ADDED)] == ["B"]


def test_a_rounding_wobble_is_not_a_change():
    """Extracts round differently between exports; 0.0001 is noise, not a decision."""
    diff = diff_lines([L(qty=100.0)], [L(qty=100.0001)])
    assert kinds(diff) == [UNCHANGED]


def test_a_real_small_quantity_change_is_still_a_change():
    diff = diff_lines([L(qty=100.0)], [L(qty=100.5)])
    assert kinds(diff) == [QTY_CHANGED]


# --------------------------------------------------------------------------- #
# location and determinism
# --------------------------------------------------------------------------- #

def test_the_same_item_at_two_locations_is_two_lines():
    """Location is part of identity: moving a line between bins is not a quantity change."""
    existing = [L(loc="BRW-BB", qty=10), L(loc="BRW-IB", qty=20)]
    incoming = [L(loc="BRW-BB", qty=10), L(loc="BRW-IB", qty=20)]
    assert kinds(diff_lines(existing, incoming)) == [UNCHANGED, UNCHANGED]


def test_row_order_in_the_file_cannot_change_the_result():
    """A planner re-sorting the sheet before uploading must not alter what the diff says."""
    existing = [L(qty=135, when=JUL1), L(qty=72, when=AUG3), L(item="B", qty=5, when=JUL1)]
    forward = [L(qty=135, when=JUL15), L(qty=72, when=AUG3), L(item="B", qty=5, when=JUL1)]

    a = diff_lines(existing, forward)
    b = diff_lines(list(reversed(existing)), list(reversed(forward)))

    def norm(d):
        return sorted((c.kind, c.item_code,
                       c.before.required_date if c.before else None,
                       c.after.required_date if c.after else None) for c in d.changes)

    assert norm(a) == norm(b)


def test_an_undated_line_is_handled_without_comparing_none_to_a_date():
    """Undated demand is real in the extract and must not raise."""
    diff = diff_lines([L(when=None)], [L(when=None)])
    assert kinds(diff) == [UNCHANGED]


def test_an_undated_line_gaining_a_date_is_a_move():
    diff = diff_lines([L(when=None)], [L(when=JUL1)])
    assert kinds(diff) == [DATE_MOVED]
    assert diff.changes[0].days_moved is None  # cannot be measured, must not be invented


# --------------------------------------------------------------------------- #
# an unreadable incoming date (19 Aug 2026 incident) must never read as a move
# --------------------------------------------------------------------------- #

def test_an_unreadable_incoming_date_is_not_a_move():
    """The line already had a real date; the incoming row's date cell failed to parse
    (`date_unreadable`), not merely blank. Reading that as a move would write `None` over
    a date the database already holds - see `outstanding_import_service._write_date`."""
    existing = [L(when=JUL1, qty=135)]
    incoming = [Line(doc_number="SO397450", item_code="SRTWC8613-RL", location="BRW-BB",
                     qty=135, required_date=None, date_unreadable=True)]

    diff = diff_lines(existing, incoming)

    assert kinds(diff) == [UNCHANGED]


def test_an_unreadable_incoming_date_with_a_real_qty_change_is_qty_changed_not_a_move():
    existing = [L(when=JUL1, qty=135)]
    incoming = [Line(doc_number="SO397450", item_code="SRTWC8613-RL", location="BRW-BB",
                     qty=100, required_date=None, date_unreadable=True)]

    diff = diff_lines(existing, incoming)

    assert kinds(diff) == [QTY_CHANGED]
    assert diff.changes[0].qty_delta == -35


# --------------------------------------------------------------------------- #
# summary shape the confirm screen renders
# --------------------------------------------------------------------------- #

def test_counts_cover_every_kind_including_unchanged():
    """"412 unchanged" is load-bearing: a diff showing only changes is indistinguishable
    from a diff that silently failed to read most of the file."""
    existing = [L(item="A", qty=1), L(item="B", qty=2), L(item="C", qty=3)]
    incoming = [L(item="A", qty=1), L(item="B", qty=9), L(item="D", qty=4)]

    counts = diff_lines(existing, incoming).counts

    assert counts[UNCHANGED] == 1
    assert counts[QTY_CHANGED] == 1
    assert counts[CLOSED] == 1
    assert counts[ADDED] == 1
    assert set(counts) >= {ADDED, QTY_CHANGED, DATE_MOVED, DATE_AND_QTY_CHANGED,
                           CLOSED, UNCHANGED}


def test_an_empty_upload_changes_nothing_at_all():
    """An empty file must be a no-op, never "close the whole book"."""
    diff = diff_lines([L(), L(item="B")], [])
    assert diff.scope_documents == ()
    assert diff.changes == []
    assert diff.has_material_change is False


def test_a_first_upload_against_an_empty_system_is_all_added():
    diff = diff_lines([], [L(item="A"), L(item="B")])
    assert kinds(diff) == [ADDED, ADDED]
    assert diff.has_material_change is True
