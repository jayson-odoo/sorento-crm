"""A receipt date read the American way silently rewrites every warranty verdict.

A real J&Y World Hardware receipt printed `03/08/2026` came back from extraction as
`2026-03-03`. Five months out, in the field the entire warranty engine computes from
(ADR-0010), on a journey whose whole promise to the consumer is that the system reads the
receipt so they do not have to. Nothing on screen looks wrong: it is a plausible date next
to a correct shop name.

The prompt already said "Malaysian receipts print DD/MM/YYYY, so 16/10/2025 is 2025-10-16
and never 2025-04-10". It did not hold, and that is the lesson rather than an argument for
wording it more firmly: the model is good at reading paper and unreliable at calendar
arithmetic. So it transcribes the characters into `purchase_date_printed`, and this
function does the conversion in code that can be tested.

Day-first is a rule here, not a heuristic. These are Malaysian receipts.

Run: venv/bin/python -m pytest tests/test_extract_purchase_date.py -q -p no:randomly
"""
from __future__ import annotations

import pytest

from app.services.ai_extract.extract_service import AIExtractService

derive = AIExtractService._derive_purchase_date


class TestTheReceiptThatBrokeIt:
    def test_the_j_and_y_receipt_reads_as_august(self):
        # The actual failure: 3 August 2026, returned by the model as 2026-03-03.
        assert derive("03/08/2026") == "2026-08-03"

    def test_the_prompts_own_example_still_holds(self):
        assert derive("16/10/2025") == "2025-10-16"


class TestDayFirst:
    @pytest.mark.parametrize(
        "printed,expected",
        [
            ("01/02/2026", "2026-02-01"),  # ambiguous, and day-first settles it
            ("13/08/2026", "2026-08-13"),  # day > 12, unambiguous either way
            ("3-8-2026", "2026-08-03"),  # dashes, unpadded
            ("03.08.2026", "2026-08-03"),  # dots
            ("03 / 08 / 2026", "2026-08-03"),  # spaced by a sloppy OCR
        ],
    )
    def test_separators_and_padding_do_not_change_the_reading(self, printed, expected):
        assert derive(printed) == expected

    def test_a_two_digit_year_is_this_century(self):
        assert derive("03/08/26") == "2026-08-03"

    def test_an_impossible_day_first_reading_swaps(self):
        """`13` cannot be a month, so month-first is the only reading that exists.

        Deliberately narrow: the swap fires only when day-first is IMPOSSIBLE, never when
        it is merely surprising. Widening it to "looks American" would put the guessing
        back in.
        """
        assert derive("08/13/2026") == "2026-08-13"


class TestWhatItRefusesToInvent:
    def test_an_iso_date_is_trusted_as_written(self):
        assert derive("2026-08-03") == "2026-08-03"

    @pytest.mark.parametrize("printed", ["31/02/2026", "00/08/2026", "45/45/2026"])
    def test_an_impossible_date_is_nothing_rather_than_a_guess(self, printed):
        """Blank is a question CS asks. A repaired date is a warranty verdict nobody typed."""
        assert derive(printed) is None

    @pytest.mark.parametrize("printed", [None, "", "   ", "garbage", "N/A", "2026"])
    def test_unreadable_input_is_nothing(self, printed):
        assert derive(printed) is None

    def test_a_partial_date_is_not_completed(self):
        # "08/2026" has no day. Inventing the 1st would date a warranty from a day the
        # receipt does not name.
        assert derive("08/2026") is None
