"""SPLIT-SHEET-LOCATION (owner, 6-7 Nov 2026): a change of the AutoCount SO line location
(core warehouse) is detected like a qty / date / item code change.

Owner answers (7 Nov): one row (a location move riding with a qty or date change keeps
today's kind and carries the location in from/to); any location change counts, pool or not.
Plan: `documentation/plans/scm/PLAN-split-sheet-location-06nov.md`.

Pure: the diff, the row kind and its from/to. No database. SO429664-shaped values: the line
was planned at BRW-IB and AutoCount moved it to BRW-BB (same BRW pool).
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services.planning_change_service import (
    _entry_differs_from_older_row,
    _from_to,
    _map_kind,
)
from app.services.scm.outstanding_diff import (
    ADDED,
    CLOSED,
    DATE_MOVED,
    QTY_CHANGED,
    UNCHANGED,
    Line,
    diff_lines,
)

D1 = date(2026, 11, 20)
D2 = date(2026, 12, 4)
LID = "core-line-429664-1"


def _line(location: str, qty: float = 10.0, when: date = D1, line_id=LID) -> Line:
    return Line(doc_number="SO429664", item_code="SRTWT8239-GM", location=location, qty=qty,
                required_date=when, line_id=line_id)


def _one(before: Line, after: Line):
    diff = diff_lines([before], [after])
    assert len(diff.changes) == 1, [c.kind for c in diff.changes]
    return diff.changes[0]


def test_a_location_only_move_on_the_same_line_is_location_changed():
    from app.services.scm.outstanding_diff import LOCATION_CHANGED

    change = _one(_line("BRW-IB"), _line("BRW-BB"))

    assert change.kind == LOCATION_CHANGED
    assert change.location == "BRW-BB"
    assert _map_kind(change) == "location_changed"


def test_the_same_location_is_still_unchanged():
    assert _one(_line("BRW-BB"), _line("BRW-BB")).kind == UNCHANGED


def test_a_location_move_with_a_qty_change_keeps_the_qty_kind():
    change = _one(_line("BRW-IB", qty=10), _line("BRW-BB", qty=8))

    assert change.kind == QTY_CHANGED
    assert _map_kind(change) == "qty_down"


def test_a_location_move_with_a_date_move_keeps_the_date_kind():
    change = _one(_line("BRW-IB", when=D1), _line("BRW-BB", when=D2))

    assert change.kind == DATE_MOVED
    assert _map_kind(change) == "delayed"


def test_lines_without_an_id_still_read_a_move_as_closed_plus_added():
    """The book upload has no line number: location stays part of the group key there."""
    diff = diff_lines([_line("BRW-IB", line_id=None)], [_line("BRW-BB", line_id=None)])

    assert sorted(c.kind for c in diff.changes) == sorted([ADDED, CLOSED])


def test_the_row_carries_the_old_and_new_location_on_a_location_only_move():
    from_, to_ = _from_to(_one(_line("BRW-IB"), _line("BRW-BB")))

    assert from_["location"] == "BRW-IB"
    assert to_["location"] == "BRW-BB"
    # Nothing else moved: qty and date read the same on both sides.
    assert from_["qty"] == to_["qty"] == "10"
    assert from_["required_date"] == to_["required_date"] == D1.isoformat()


def test_the_row_carries_the_location_when_it_rides_on_a_qty_change():
    from_, to_ = _from_to(_one(_line("BRW-IB", qty=10), _line("BRW-BB", qty=8)))

    assert (from_["location"], to_["location"]) == ("BRW-IB", "BRW-BB")
    assert (from_["qty"], to_["qty"]) == ("10", "8")


def test_the_row_carries_no_location_when_it_did_not_move():
    from_, to_ = _from_to(_one(_line("BRW-BB", qty=10), _line("BRW-BB", qty=8)))

    assert from_["location"] is None
    assert to_["location"] is None


def test_a_closed_line_carries_no_location():
    diff = diff_lines([_line("BRW-BB")], [_line("BRW-BB", qty=0)])
    from_, to_ = _from_to(diff.changes[0])

    assert diff.changes[0].kind == CLOSED
    assert to_["location"] is None


def test_a_second_move_differs_from_the_older_pending_row():
    """BRW-IB -> BRW-BB is pending, then AutoCount moves the line again to BRW-IC with
    nothing else changing: the older row must be refreshed, not left saying BRW-BB."""
    older = SimpleNamespace(
        to_json={"required_date": D1.isoformat(), "qty": "10", "status": "open",
                 "item_code": None, "location": "BRW-BB"},
    )

    assert _entry_differs_from_older_row(_one(_line("BRW-BB"), _line("BRW-IC")), older)


def test_an_idempotent_re_push_does_not_differ_from_the_older_row():
    older = SimpleNamespace(
        to_json={"required_date": D1.isoformat(), "qty": "8", "status": "open",
                 "item_code": None, "location": None},
    )

    assert not _entry_differs_from_older_row(
        _one(_line("BRW-BB", qty=10), _line("BRW-BB", qty=8)), older
    )
