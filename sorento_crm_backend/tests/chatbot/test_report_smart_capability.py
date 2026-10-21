"""REPORT-SMART-1021 step 2: code picks the report tool from the parser's params.

Owner 15 Oct: "the report engine, it is not very smart and dynamic". The parser names the
report kind (`order_status`) AND the axis (`group_by`); until now the kind alone picked the
tool, so "total sale for all sale agents in September" (kind sales_analysis, axis sales_agent)
was answered "I can't break sales down by sales_agent yet", and "top 10 dealers selling
<product>" (kind top_selling, axis customer) listed the top items overall.

The capability table (`report_ask.CAN_DRAW`): an axis the picked tool cannot draw but
`crm_report_ask` can sends the ask there, its filters, period, count, metric and basis read
the way a sales ranking reads them; whatever is still missing is asked in ONE numbered reply.

Sandbox fixtures mirror the 8 real asks of 30 days of dev chat (masked, crew relay): fake
agents, customers and products from `test_report_ask_lane._seed`. Parser fields only; the
message words are decoration (a paraphrase per example proves it).
"""
from __future__ import annotations

import re
from typing import Any

import pytest

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import (  # noqa: F401 - fixtures + helpers
    CUSTOMER_NAME,
    DIMENSION_REFUSAL,
    PRODUCT_CODE,
    SEP,
    TOPN_Q,
    _e,
    _rank,
    _reply,
    console,
    dealer,
)

YEAR_2026 = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-12-31"}
NINE_MONTHS = {"date_filter_start": "2026-01-01", "date_filter_end": "2026-09-30"}
_NUMBERED = re.compile(r"^\s*([1-9])[.)]", re.M)


def _ask(*entities: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """A sales figure ask the parser read as some report kind, with an axis of its own and
    neither measure nor basis named (overrides fill them)."""
    base: dict[str, Any] = dict(
        domain_hint="sales", top_n=None, rank_direction=None, measure=None, basis=None, rank_by=None, **SEP
    )
    base.update(overrides)
    return _rank(*entities, **base)


def _numbered(text: str) -> list[int]:
    return [int(n) for n in _NUMBERED.findall(text)]


def _no_unsupported_line(text: str) -> None:
    assert "can't break sales down" not in text.lower(), text


# ---------------------------------------------------------------- example 1: by sales agent


@pytest.mark.parametrize(
    "status, body",
    [
        ("sales_analysis", "Total sale for all sale agents on September 2026"),
        ("sales_report", "september sales per salesman"),  # paraphrase, read as a sales report
    ],
    ids=["analysis", "paraphrase_sales_report"],
)
def test_e1_sales_by_every_agent_is_one_question_then_the_whole_breakdown(console, status, body) -> None:
    text, calls = console.say(_ask(order_status=status, group_by="sales_agent"), body)
    assert calls == [], (text, calls)
    _no_unsupported_line(text)
    # A breakdown of all agents is never asked "how many": only the metric and the basis.
    assert TOPN_Q not in text and _numbered(text) == [1, 2], text

    text, calls = console.say(_reply(measure="amount", basis="delivered"), "amount, delivered")
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["group_by"] == "sales_agent" and args["measure"] == "amount" and args["basis"] == "delivered", args
    assert args["top_n"] >= 100, args  # every agent, not a top few
    assert args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args


def test_e1_a_breakdown_naming_its_choices_runs_at_once(console) -> None:
    text, calls = console.say(
        _ask(order_status="sales_analysis", group_by="sales_agent", measure="amount", basis="delivered"),
        "delivered sales amount by agent september",
    )
    assert len(calls) == 1, (text, calls)
    _no_unsupported_line(text)


def test_e1_the_analysis_basis_word_fills_the_basis(console) -> None:
    """The analysis reads its basis off `sales_basis`; a delivered one is the report basis."""
    text, calls = console.say(
        _ask(order_status="sales_analysis", group_by="sales_agent", measure="qty", sales_basis="delivered"),
        "delivered qty per agent september",
    )
    assert len(calls) == 1 and calls[0]["basis"] == "delivered", (text, calls)


# ---------------------------------------------------------------- example 2: by customer


def test_e2_delivered_sales_by_customer_asks_only_the_metric(console) -> None:
    text, calls = console.say(
        _ask(order_status="sales_analysis", group_by="customer", basis="delivered", **NINE_MONTHS),
        "dealer deliver sale 1/1/26-30/9/26 by dealer",
    )
    assert calls == [], (text, calls)
    _no_unsupported_line(text)
    assert "quantity" in text.lower() and _numbered(text) == [], text
    text, calls = console.say(_reply(measure="amount"), "amount")
    assert len(calls) == 1, (text, calls)
    assert calls[0]["group_by"] == "customer" and calls[0]["date_from"] == "2026-01-01", calls
    assert calls[0]["date_to"] == "2026-09-30", calls


def test_e2_paraphrase_a_sales_report_for_one_customer_by_product(console) -> None:
    text, calls = console.say(
        _ask(_e(CUSTOMER_NAME, "customer"), order_status="sales_report", group_by="product",
             measure="qty", basis="delivered", **NINE_MONTHS),
        f"{CUSTOMER_NAME} delivered qty by product jan to sep",
    )
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["group_by"] == "product" and args["customer_ids"] == [console.ids["customer"]], args


# ---------------------------------------------------------------- examples 3 and 4: who sells a product


def test_e3_top_dealers_selling_a_product_rank_customers_for_that_product(console) -> None:
    text, calls = console.say(
        _ask(_e(PRODUCT_CODE, "product"), order_status="top_selling", group_by="customer", top_n=10,
             rank_direction="top", rank_by="amount", basis="delivered", **YEAR_2026),
        f"Top 10 dealer selling {PRODUCT_CODE}",
    )
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["group_by"] == "customer" and args["top_n"] == 10, args
    assert args["product_code"] == PRODUCT_CODE, args  # the product is the filter, never dropped


def test_e3_paraphrase_with_no_metric_asks_it(console) -> None:
    text, calls = console.say(
        _ask(_e(PRODUCT_CODE, "product"), order_status="top_selling", group_by="customer", top_n=10,
             basis="delivered", **YEAR_2026),
        f"which 10 customers buy the most {PRODUCT_CODE}",
    )
    assert calls == [], (text, calls)
    assert "quantity" in text.lower(), text


def test_e4_top_salespeople_for_a_product_by_quantity_delivered(console) -> None:
    text, calls = console.say(
        _ask(_e(PRODUCT_CODE, "product"), order_status="top_selling", group_by="sales_agent", top_n=5,
             rank_direction="top", rank_by="quantity", basis="delivered", **YEAR_2026),
        f"top 销售员 {PRODUCT_CODE} in 2026, top 5, by quantity, delivered",
    )
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["group_by"] == "sales_agent" and args["top_n"] == 5, args
    assert args["measure"] == "qty" and args["basis"] == "delivered", args
    assert args["product_code"] == PRODUCT_CODE, args


def test_e4_paraphrase_malay_wording_same_fields(console) -> None:
    text, calls = console.say(
        _ask(_e(PRODUCT_CODE, "product"), order_status="top_selling", group_by="sales_agent", top_n=5,
             rank_by="quantity", basis="delivered", **YEAR_2026),
        f"5 jurujual teratas untuk {PRODUCT_CODE} 2026 ikut kuantiti",
    )
    assert len(calls) == 1 and calls[0]["group_by"] == "sales_agent", (text, calls)


# ---------------------------------------------------------------- example 6: one agent's products


def test_e6_one_agents_top_products_rank_products_filtered_by_that_agent(console) -> None:
    text, calls = console.say(
        _ask(_e("AGENT A", "sales_agent"), _e("Sorento", "brand"), order_status="sales_ranking", group_by="product",
             top_n=10, rank_direction="top", measure="amount", basis="delivered"),
        "Sale agent AGENT A sorento top 10 product sale on September",
    )
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["group_by"] == "product" and args["sales_agent_ids"] == [console.ids["agent"]], args
    assert args["brand_ids"] == [console.ids["brand"]], args


# ---------------------------------------------------------------- near misses: the table keeps what fits


def test_near_miss_an_analysis_by_month_stays_the_sales_analysis(console) -> None:
    text, calls = console.say(_ask(order_status="sales_analysis", group_by="month"), "sales by month this year")
    assert calls == [], (text, calls)  # crm_sales_analysis ran, not the report ask


def test_near_miss_a_top_selling_ask_with_no_axis_stays_top_selling(console) -> None:
    text, calls = console.say(
        _ask(order_status="top_selling", group_by=None, top_n=10, rank_by="quantity", basis="delivered"),
        "top 10 selling items september",
    )
    assert calls == [], (text, calls)


def test_near_miss_an_axis_no_tool_draws_is_still_said(console) -> None:
    text, calls = console.say(_ask(order_status="sales_analysis", group_by="transporter"), "sales by transporter")
    assert calls == [], (text, calls)
    assert "transporter" in text.lower(), text


def test_dealer_a_staff_axis_through_another_report_kind_is_refused(dealer) -> None:
    text, calls = dealer.say(_ask(order_status="sales_analysis", group_by="sales_agent"), "my sales by agent")
    assert calls == [], (text, calls)
    assert text.strip() == DIMENSION_REFUSAL, text


def test_dealer_a_product_breakdown_of_its_own_sales_runs_on_the_report_ask(dealer) -> None:
    text, calls = dealer.say(
        _ask(order_status="sales_analysis", group_by="product", measure="qty", basis="delivered", top_n=5),
        "my top 5 products by qty delivered september",
    )
    assert len(calls) == 1 and calls[0]["group_by"] == "product", (text, calls)
