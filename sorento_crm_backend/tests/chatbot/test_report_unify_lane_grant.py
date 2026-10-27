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
