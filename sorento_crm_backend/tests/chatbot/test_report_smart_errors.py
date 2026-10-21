"""REPORT-SMART-1021 step 5: a report failure ends in a clear sentence, never raw text.

Seen in 30 days of dev chat (masked): a raw "INVALID_UUID" sent to a user, a "SEP 2026"
period that broke the run, and a dealer's "what is my sales this month" answered "Could not
run". Probed in the sandbox: a top selling result with no rendered text printed
`[object Object]`, a tool-error string printed verbatim, and a period the parser wrote as
"SEP 2026" printed "Dates: SEP 2026" or "Could not run the sales report right now.".
"""
from __future__ import annotations

import json

import pytest

from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import PRODUCT_CODE, _e, _rank, console  # noqa: F401

PERIOD_Q = "Which period? For example this month, September, 2026, or 1 to 15 Sep."
_RAW = ("[object", "INVALID_UUID", "Error executing tool", "TypeError", "ValueError", "Traceback")


def _clean(text: str) -> None:
    for raw in _RAW:
        assert raw not in text, (raw, text)
    assert text.strip(), "an empty reply"


# ---------------------------------------------------------------- the top selling output


def test_a_top_selling_result_with_no_rendered_text_is_a_sentence() -> None:
    from app.services.chatbot.lanes.business.fetch import _top_selling_output

    out = _top_selling_output({"has_result": False, "items": []}, {})
    _clean(out["response"])


def test_a_tool_error_string_is_never_printed() -> None:
    from app.services.chatbot.lanes.business.fetch import _top_selling_output

    raw = "Error executing tool crm_top_selling_report: " + json.dumps(
        {"code": "INVALID_UUID", "message": "`customer_ids` contains a non-UUID value: 'X'"}
    )
    out = _top_selling_output(raw, {})
    _clean(out["response"])


@pytest.mark.parametrize("tool", ["_outstanding_report_output", "_sales_report_output"])
def test_the_sibling_reports_never_print_a_dict_as_text(tool) -> None:
    from app.services.chatbot.lanes.business import fetch

    out = getattr(fetch, tool)({"has_result": False, "items": []}, {})
    assert "[object" not in (out.get("response") or ""), out


def test_a_top_selling_turn_whose_tool_rendered_nothing_says_a_sentence(console) -> None:
    text, _calls = console.say(
        _rank(order_status="top_selling", group_by=None, top_n=5, rank_by="amount", basis="delivered",
              date_filter_start="2026-09-01", date_filter_end="2026-09-30"),
        "top 5 selling items september by amount delivered",
    )
    _clean(text)


# ---------------------------------------------------------------- a period the parser wrote in words


@pytest.mark.parametrize(
    "status, entities, body",
    [
        ("sales_analysis", [], "total sales SEP 2026"),
        ("sales_report", [_e(PRODUCT_CODE, "product")], f"{PRODUCT_CODE} sales SEP 2026"),
        ("top_selling", [], "top 5 items SEP 2026"),
        ("sales_analysis", [], "jualan Sept 2026"),  # paraphrase
    ],
    ids=["analysis", "sales_report", "top_selling", "paraphrase_ms"],
)
def test_an_unreadable_period_is_asked_never_run_or_echoed(console, status, entities, body) -> None:
    text, calls = console.say(
        _rank(*entities, order_status=status, group_by=None, top_n=5, measure="amount", basis="delivered",
              rank_by="amount", date_filter_start="SEP 2026", date_filter_end="SEP 2026", domain_hint="sales"),
        body,
    )
    _clean(text)
    assert "SEP 2026" not in text and "Could not run" not in text, text
    assert PERIOD_Q in text, text


def test_near_miss_a_readable_period_runs_as_before(console) -> None:
    text, _calls = console.say(
        _rank(_e(PRODUCT_CODE, "product"), order_status="sales_report", group_by=None,
              date_filter_start="2026-09-01", date_filter_end="2026-09-30", domain_hint="sales"),
        f"{PRODUCT_CODE} sales september",
    )
    assert PERIOD_Q not in text, text
