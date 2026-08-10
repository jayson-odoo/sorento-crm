"""Is this demand sustaining or dying off? The pure arithmetic.

> "Just give me a judgment that whether this demand is going to sustain or is going to die
>  off. So I can decide should I order more or should I order just enough or should I
>  order less."

The judgment is a comparison of our own order history, two ways at once (user decision
2026-08-10): the recent window against the window immediately before it - the comparison
that LEADS - and against the same window last year, which sits beside it and is named
absent when the history is shorter than a year.

Pure by design, like `coverage_timeline` and `cover_service`: the resolver half
(`trajectory_service`) reads the tables and feeds this, so the verdicts stay golden-
testable with no database in the picture.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

#: Below this, two windows differ by noise, not by a trend worth telling a buyer about.
#: Returned in every payload so the screen states the rule it applied.
MOVEMENT_THRESHOLD_PCT = 20.0

#: Default windows when no policy configures them. Retail is stable, so a quarter reads it;
#: project is erratic, so it takes a year to mean anything. Both live on
#: `scm.reorder_policy` and these are only the values for a policy that has not said.
DEFAULT_RETAIL_MONTHS = 3
DEFAULT_PROJECT_MONTHS = 12


class Trajectory(NamedTuple):
    """The verdict and the two comparisons behind it."""

    #: rising | holding | falling | quiet | no_history
    verdict: str
    recent_qty: float
    previous_qty: float
    #: Percent change vs the window immediately before. None when the previous window is
    #: zero - a percentage off nothing is undefined, though the direction is still real.
    change_pct: Optional[float]
    #: Percent change vs the same window last year. None when the book is younger.
    year_ago_qty: Optional[float]
    year_change_pct: Optional[float]
    movement_threshold_pct: float = MOVEMENT_THRESHOLD_PCT


def _pct(new: float, old: float) -> Optional[float]:
    if old == 0:
        return None
    return round((new - old) / abs(old) * 100.0, 2)


def assess_trajectory(
    *, recent: float, previous: float, year_ago: Optional[float]
) -> Trajectory:
    """Turn two (or three) window totals into a verdict.

    Order of the rules:

    * nothing anywhere -> ``no_history``. Not "quiet": quiet means it STOPPED, and a
      product that never sold has no heyday to have stopped from.
    * activity before, nothing now -> ``quiet``. The strongest die-off signal there is.
    * a move past the threshold -> ``rising`` / ``falling``.
    * otherwise ``holding``.
    """
    change = _pct(recent, previous)
    year_change = (
        _pct(recent, year_ago) if year_ago is not None and year_ago > 0
        else None
    )

    if recent == 0 and previous == 0:
        verdict = "no_history"
    elif recent == 0:
        verdict = "quiet"
    elif previous == 0:
        # Started from nothing: direction is real even though the percentage is not.
        verdict = "rising"
    elif change is not None and change >= MOVEMENT_THRESHOLD_PCT:
        verdict = "rising"
    elif change is not None and change <= -MOVEMENT_THRESHOLD_PCT:
        verdict = "falling"
    else:
        verdict = "holding"

    return Trajectory(
        verdict=verdict,
        recent_qty=recent,
        previous_qty=previous,
        change_pct=change,
        year_ago_qty=year_ago,
        year_change_pct=year_change,
    )
