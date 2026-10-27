"""REPORT-UNIFY phase 3 fix round, R2: an axis the report ask cannot draw is said (with the axes it can), and nothing is
fetched, unless it is the Yearly comparison (axis year, on `crm_sales_analysis`). The default tool pick never sends an
unsettled `crm_report_ask`."""
from __future__ import annotations

import pytest

from app.services.chatbot.lanes.business import report_ask
from tests.chatbot.test_report_unify_routing import (  # noqa: F401  (bot / console are fixtures)
    YEAR,
    _status,
    bot,
    console,
)


@pytest.mark.parametrize("axis", ["week", "day", "quarter", "weather"])
@pytest.mark.parametrize("status", ["sales_report", "sales_analysis", "sales_ranking"])
def test_r2_an_axis_the_report_ask_cannot_draw_is_said_and_nothing_runs(bot, status, axis) -> None:
    text, calls = bot.say(_status(status, group_by=axis, top_n=5, measure="amount", basis="delivered", **YEAR), f"sales by {axis} 2026")
    assert calls == [], calls
    assert "customer, product, brand, category, sales agent, location, channel or month." in text, text


def test_r2_the_yearly_comparison_still_runs_on_the_sales_analysis_tool(bot) -> None:
    text, calls = bot.say(
        _status("sales_analysis", group_by="year", sales_basis="delivered", basis=None, **YEAR), "sales by year"
    )
    assert [n for n, _a in calls] == ["crm_sales_analysis"], (calls, text)
