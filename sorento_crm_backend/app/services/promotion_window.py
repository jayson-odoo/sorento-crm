"""When a promotion is live, defined once for everyone who asks.

Two modules asked and gave different answers.
``marketing_service._promotion_active_clause`` accepted only a promotion with no
dates at all, or one whose start AND end bracket today, so a promotion with a
start date and a blank end was never active. The Dealer Kit's pricing read a
blank end as unbounded, so the same promotion WAS live there. One commercial
question, two answers, on screens a dealer can hold side by side.

Live data says 26 promotions carry both dates, 3 carry neither, and none carries
a start alone, so the disagreement has never fired. That is the argument for
fixing it now rather than later: it costs nothing today, and after somebody
creates the first open-ended offer it becomes a support ticket nobody can
reproduce.

**The semantics: unbounded on the blank side.** Somebody who fills in a start
and leaves the end empty means "from then until further notice". Reading that as
"never live" is the answer nobody expects, and it is the one the old clause gave.

**Live and expiring are different questions**, and this module keeps them apart
deliberately. A promotion with no end date runs until further notice: it is live,
and there is no day on which it ends, so the expiry automation must never pick it
up. Folding the two ideas into one predicate would start emailing people about
offers that have not ended.

This module holds no imports from the marketing or Dealer Kit services on
purpose, so either can import it without a cycle.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import and_, or_


def is_live(
    is_active: Optional[bool],
    start_date: Optional[date],
    end_date: Optional[date],
    today: date,
) -> bool:
    """Whether a promotion row is live on ``today``.

    The Python half, for a row already in hand. ``live_clause`` is the same rule
    as SQL, and a test asserts the two agree on every shape a row can take.
    """
    # The flag beats any window. It is the control somebody reaches for when a
    # price is wrong, and it has to stop the offer immediately.
    if not is_active:
        return False
    if start_date is not None and start_date > today:
        return False
    if end_date is not None and end_date < today:
        return False
    return True


def live_clause(
    today: date,
    *,
    is_active_col: Any = None,
    start_col: Any = None,
    end_col: Any = None,
):
    """The same rule as a SQLAlchemy clause, for filtering a query.

    Columns are injectable so this can be exercised against literals in a test
    without a promotions table, and so a caller joining an alias can pass it.
    Defaults are the real Promotion columns.
    """
    if is_active_col is None or start_col is None or end_col is None:
        from app.models.marketing import Promotion

        is_active_col = Promotion.is_active if is_active_col is None else is_active_col
        start_col = Promotion.start_date if start_col is None else start_col
        end_col = Promotion.end_date if end_col is None else end_col

    return and_(
        is_active_col.is_(True),
        # A blank bound is unbounded on that side, which is the whole point of
        # this module.
        or_(start_col.is_(None), start_col <= today),
        or_(end_col.is_(None), end_col >= today),
    )


def expires_on_or_before(end_date: Optional[date], horizon: date) -> bool:
    """Whether a promotion ends on or before ``horizon``.

    Deliberately NOT derived from liveness. An offer with no end date never
    expires however live it is, and the expiry automation exists to warn people
    about offers that are ENDING.
    """
    if end_date is None:
        return False
    return end_date <= horizon
