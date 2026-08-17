"""One answer to "is this promotion live", for every module that asks.

Two modules asked and disagreed. `marketing_service._promotion_active_clause`
allowed only a promotion with NO dates at all or one whose start AND end bracket
today, so a promotion with a start date and a blank end was never active. The
Dealer Kit's pricing reads a blank end as unbounded, so the same promotion WAS
live there. One commercial question, two answers, on screens a dealer sees side
by side.

Live data says 26 promotions carry both dates, 3 carry neither and ZERO carry a
start alone, so the disagreement has never fired. That is exactly why it gets
fixed now: after somebody creates the first open-ended offer it becomes a
support ticket nobody can reproduce.

The semantics chosen are unbounded on the blank side. A person who fills in a
start and leaves the end empty means "from then until further notice", and
reading that as "never" is the answer nobody expects.

**Live and expiring are different questions.** A promotion with no end date runs
until further notice, so it is live and it can never expire. The expiry
automation must keep ignoring it, and that is asserted here rather than assumed,
because folding the two ideas together would start emailing people about offers
that have not ended.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.promotion_window import is_live, live_clause

TODAY = date(2026, 8, 1)
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)
LAST_WEEK = TODAY - timedelta(days=7)
NEXT_WEEK = TODAY + timedelta(days=7)


class TestTheWindow:
    def test_both_dates_bracketing_today_is_live(self) -> None:
        assert is_live(True, LAST_WEEK, NEXT_WEEK, TODAY) is True

    def test_no_dates_at_all_is_live(self) -> None:
        # An offer with no window is one somebody runs until they turn it off.
        assert is_live(True, None, None, TODAY) is True

    def test_a_start_with_no_end_is_live_once_it_has_started(self) -> None:
        # The case the two modules disagreed on. "From then until further notice"
        # is what a blank end date means to the person who left it blank.
        assert is_live(True, LAST_WEEK, None, TODAY) is True

    def test_a_start_with_no_end_is_not_live_before_it_starts(self) -> None:
        assert is_live(True, TOMORROW, None, TODAY) is False

    def test_an_end_with_no_start_is_live_until_it_ends(self) -> None:
        assert is_live(True, None, NEXT_WEEK, TODAY) is True

    def test_an_end_with_no_start_is_not_live_after_it_ends(self) -> None:
        assert is_live(True, None, YESTERDAY, TODAY) is False

    def test_the_window_includes_its_own_edges(self) -> None:
        # An offer advertised as running to the 31st runs ON the 31st.
        assert is_live(True, TODAY, TODAY, TODAY) is True

    def test_a_past_window_is_not_live(self) -> None:
        assert is_live(True, LAST_WEEK, YESTERDAY, TODAY) is False

    def test_a_future_window_is_not_live(self) -> None:
        assert is_live(True, TOMORROW, NEXT_WEEK, TODAY) is False

    def test_the_active_flag_beats_any_window(self) -> None:
        # Switching a promotion off has to stop it immediately, whatever its
        # dates say. It is the control someone reaches for when a price is wrong.
        assert is_live(False, LAST_WEEK, NEXT_WEEK, TODAY) is False
        assert is_live(False, None, None, TODAY) is False


class TestLiveAndExpiringAreDifferentQuestions:
    def test_an_open_ended_promotion_is_live(self) -> None:
        assert is_live(True, LAST_WEEK, None, TODAY) is True

    def test_an_open_ended_promotion_can_never_expire(self) -> None:
        # It has no end date, so there is no day on which it ends. The expiry
        # automation emails people about offers that are ENDING; an offer with no
        # end must never appear there, however live it is.
        from app.services.promotion_window import expires_on_or_before

        assert expires_on_or_before(None, NEXT_WEEK) is False
        assert expires_on_or_before(None, date(2099, 1, 1)) is False

    def test_a_promotion_with_an_end_expires_when_it_reaches_it(self) -> None:
        from app.services.promotion_window import expires_on_or_before

        assert expires_on_or_before(TOMORROW, NEXT_WEEK) is True
        assert expires_on_or_before(NEXT_WEEK, TOMORROW) is False


class TestTheSqlClauseAgreesWithThePython:
    """The clause and the predicate are two expressions of one rule.

    They are used in different places - one filters a query, one answers about a
    row already in hand - and a codebase where those two drift is one where a
    promotion is listed as live and priced as dead.
    """

    @pytest.mark.parametrize(
        "is_active,start,end",
        [
            (True, LAST_WEEK, NEXT_WEEK),
            (True, None, None),
            (True, LAST_WEEK, None),
            (True, TOMORROW, None),
            (True, None, NEXT_WEEK),
            (True, None, YESTERDAY),
            (True, LAST_WEEK, YESTERDAY),
            (True, TOMORROW, NEXT_WEEK),
            (False, LAST_WEEK, NEXT_WEEK),
        ],
    )
    def test_every_shape_gets_the_same_answer_from_both(
        self, is_active, start, end
    ) -> None:
        from sqlalchemy import Boolean, and_, cast, literal, select

        from tests._pg_fixture import pg_session

        expected = is_live(is_active, start, end, TODAY)

        # Evaluated by Postgres against literals shaped like a promotion row, so
        # the SQL is really executed rather than merely constructed.
        with pg_session() as db:
            clause = live_clause(
                TODAY,
                is_active_col=cast(literal(is_active), Boolean),
                start_col=literal(start, type_=None) if start else literal(None),
                end_col=literal(end, type_=None) if end else literal(None),
            )
            got = db.execute(select(and_(clause))).scalar()

        assert bool(got) is expected
