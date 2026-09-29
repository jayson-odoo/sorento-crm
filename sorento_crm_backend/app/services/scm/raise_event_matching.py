"""Shared match window for an `order_inquiry_raises` EVENT against the row it raised.

Extracted out of `order_inquiry_worklist_service.py`'s own `_raise_events_by_row`
(`PLAN-oi-decision-trail-ui.md`, review round 1, B1) so the decision trail's own read
(`decision_trail_service.py`) matches a row to its event with the EXACT same window
rather than a second copy the two could quietly drift apart from.

Rows and their raise event are written in the SAME call
(`ProjectOrderInquiryService._write` alongside `OrderInquiryRaise`'s own writer), so the
match is the event of the SAME inquiry with the smallest `raised_at` inside
`[row.created_at - 1s, row.created_at + 10 min]` - the prod gap measured 1.3 seconds
(SO390524 / OI-2609-0731, 25 Sep 2026). The UPPER bound is what keeps a row that has no
event of its own from latching onto the next reconfirm on the same inquiry (reviewer B1,
round 1: 2,070 sheet-migrated rows read "Reconfirmed by Jayson Foundryx" off an event 1 to
23 hours later). Measured on the 24 Sep prod copy: 10,851 real matches within 1.8s, 85
between 2s and 67s, then nothing until 1h 14m - ten minutes sits in the empty stretch.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

#: The window's own two edges, named so a caller (and a reader of either file) sees the
#: same two numbers rather than a repeated `timedelta(...)` literal.
RAISE_EVENT_BEFORE = timedelta(seconds=1)
RAISE_EVENT_AFTER = timedelta(minutes=10)


def nearest_raise_event(
    born: Optional[datetime],
    candidates: List[Tuple[datetime, str, Optional[str]]],
) -> Optional[Tuple[datetime, str, Optional[str]]]:
    """The first `(raised_at, kind, actor_name)` inside the window around `born`.

    `candidates` is every raise event of the row's own inquiry, already sorted by
    `raised_at` ascending - so "first inside the window" is also "smallest qualifying
    event", which is the rule a row born a beat before its own raise event (never after)
    needs. `None` when `born` is unknown (a row with no birth stamp matches nothing rather
    than everything) or nothing falls inside the window.
    """
    if born is None:
        return None
    return next(
        (
            entry
            for entry in candidates
            if born - RAISE_EVENT_BEFORE <= entry[0] <= born + RAISE_EVENT_AFTER
        ),
        None,
    )
