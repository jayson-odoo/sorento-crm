"""AC-SA301: `branch()` truth table, chatbot-stock-ask-v2-24sep-acceptance-criteria.md
S3. Pure function, no DB - no `tests/_pg_fixture.py` needed."""
from datetime import date

import pytest

from app.services.stock_ask_branch import branch


# (q, x, available, shipment_date, expected) - the UAC table verbatim, rows 1-8.
# Y (the ETA offset) is not an input to branch() - it only affects the "told" date,
# which is composed by the caller from shipment_date + Y, not by this function.
TRUTH_TABLE = [
    pytest.param(250, 200, 1000, date(2026, 10, 12), "too_big", id="row1_too_big"),
    pytest.param(5, 0, 1000, None, "too_big", id="row2_cap_unset_too_big"),
    pytest.param(200, 200, 200, None, "in_stock", id="row3_in_stock_boundary"),
    pytest.param(150, 200, 149, date(2026, 10, 12), "incoming", id="row4_incoming"),
    pytest.param(150, 200, 149, date(2026, 10, 28), "incoming", id="row5_incoming"),
    pytest.param(150, 200, 0, None, "no_incoming", id="row6_no_incoming"),
    pytest.param(150, 200, 0, date(2026, 10, 12), "incoming", id="row7_incoming_y_unset"),
    pytest.param(1, 1, -3, None, "no_incoming", id="row8_so_over_on_hand"),
]


@pytest.mark.parametrize("q,x,available,shipment_date,expected", TRUTH_TABLE)
def test_branch_truth_table(q, x, available, shipment_date, expected):
    assert branch(q, x, available, shipment_date) == expected


def test_q_over_x_wins_even_when_stock_covers_it():
    # X caps what the assistant may answer for at all - a bigger on-hand number
    # never overrides an over-cap quantity (R6 B1 is checked before B2).
    assert branch(q=300, x=200, available=5000, shipment_date=None) == "too_big"


def test_available_exactly_covers_q_is_in_stock_not_too_big():
    assert branch(q=50, x=50, available=50, shipment_date=None) == "in_stock"


def test_q_at_x_boundary_with_shipment_is_incoming_not_too_big():
    assert branch(q=200, x=200, available=0, shipment_date=date(2026, 1, 1)) == "incoming"
