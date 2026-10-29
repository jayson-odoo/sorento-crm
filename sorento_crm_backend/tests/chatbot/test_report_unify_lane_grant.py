"""REPORT-UNIFY owner Q6, lane side: the reveal a report ask is read under depends on its basis."""
from __future__ import annotations

import pytest

from app.services.chatbot.lanes.business import report_ask

OUT = "sales_orders.outstanding"
SALES = "sales_orders.sales_report"


@pytest.mark.parametrize("basis", ["outstanding", "pending_delivery", "unpaid"])
def test_an_outstanding_kind_is_read_under_the_outstanding_reveal(basis) -> None:
    assert report_ask.grant_key({"order_status": report_ask.ASK_NAME, "basis": basis}) == OUT


@pytest.mark.parametrize("basis", ["invoiced", "delivered", "ordered", None])
def test_every_other_basis_is_read_under_the_sales_report_reveal(basis) -> None:
    assert report_ask.grant_key({"order_status": report_ask.ASK_NAME, "basis": basis}) == SALES


def test_an_outstanding_ask_whose_kind_is_still_to_be_asked_needs_the_outstanding_reveal() -> None:
    assert report_ask.grant_key({"order_status": report_ask.ASK_NAME, "capability_from": "outstanding"}) == OUT


def test_a_non_report_ask_verdict_keeps_the_sales_report_reveal() -> None:
    assert report_ask.grant_key({"order_status": "sales_report", "basis": "unpaid"}) == SALES


@pytest.mark.parametrize("basis", ["outstanding", "pending_delivery", "unpaid"])
def test_s9_the_refusal_for_an_outstanding_kind_names_the_outstanding_reveal(basis) -> None:
    """S9: same words as the route's `outstanding_not_enabled`."""
    line = report_ask.not_enabled_line({"order_status": report_ask.ASK_NAME, "basis": basis})
    assert line == "Outstanding is not enabled for your account."


@pytest.mark.parametrize("basis", ["invoiced", "delivered", "ordered", None])
def test_s9_the_refusal_for_every_other_basis_names_the_sales_report_reveal(basis) -> None:
    line = report_ask.not_enabled_line({"order_status": report_ask.ASK_NAME, "basis": basis})
    assert line == "Sales report is not enabled for your account."


def test_s9_the_lane_fragment_carries_the_outstanding_line() -> None:
    from app.services.chatbot.lanes import business

    fragment = business._sales_report_not_enabled({"order_status": report_ask.ASK_NAME, "basis": "unpaid"})
    assert "Outstanding is not enabled for your account." in str(fragment)
    assert "Sales report is not enabled" not in str(fragment)
