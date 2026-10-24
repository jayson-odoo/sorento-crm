"""REPORT-SMART-L one ranking, round R3b (AC-OR3): the report ask reply prints the top selling
agent fill-rate note below 95%. Fake names only."""
from __future__ import annotations

import pytest

from sorento_crm_mcp.presenters import _report_ask

NOTE = "Note: only 40% of sales orders in this period carry a sales agent."


def _body(**over):
    body = {
        "status": "ok", "message": None, "basis": "delivered", "basis_label": "delivered sales", "measure": "qty",
        "group_by": "product", "group_label": "Product", "sort": "desc",
        "date_from": "2026-09-01", "date_to": "2026-09-30",
        "filters": [{"key": "sales_agent", "label": "Sales agent", "values": ["ZZT AGENT"]}],
        "rows": [{"rank": 1, "name": "ZZT-ITEM-1", "qty": 30, "amount": 1200.0}],
        "more": 0, "total_count": 1, "total": {"qty": 30, "amount": 1200.0}, "sales_agent_fill_rate": 0.4,
    }
    body.update(over)
    return body


def test_r3b_1_a_low_fill_rate_prints_the_note_under_the_filters() -> None:
    lines = _report_ask(_body()).split("\n")
    assert NOTE in lines, lines
    assert lines.index(NOTE) < next(i for i, ln in enumerate(lines) if ln.startswith("1. ")), lines  # above the rows


@pytest.mark.parametrize("rate", [0.95, 0.97, 1.0, None])
def test_r3b_2_guard_at_or_above_95_percent_or_no_rate_prints_no_note(rate) -> None:
    assert "carry a sales agent" not in _report_ask(_body(sales_agent_fill_rate=rate))


def test_r3b_2_guard_a_body_without_the_key_prints_no_note() -> None:
    body = _body()
    body.pop("sales_agent_fill_rate")
    assert "carry a sales agent" not in _report_ask(body)
