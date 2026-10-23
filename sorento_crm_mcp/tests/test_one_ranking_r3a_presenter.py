"""REPORT-SMART-L one ranking, round R3a (AC-OR3): the report ask presenter keeps what the top selling
reply gave an item ranking: the WhatsApp split of a long list and the "no sale is not ranked" line.
Fake names only."""
from __future__ import annotations

import re

from sorento_crm_mcp.presenters import WHATSAPP_MESSAGE_MAX_CHARS, _report_ask

PERIOD = {"date_from": "2026-09-01", "date_to": "2026-09-30"}


def _body(rows: int, *, group_by: str = "product", sort: str = "desc", **over):
    body = {
        "status": "ok", "message": None, "basis": "delivered", "basis_label": "delivered sales", "measure": "qty",
        "group_by": group_by, "group_label": group_by.title(), "sort": sort, **PERIOD, "filters": [],
        "rows": [{"rank": i, "name": f"ZZT-ITEM-{i:04d}", "qty": 1000 - i, "amount": float(5000 - i)} for i in range(1, rows + 1)],
        "more": 0, "total_count": rows, "total": {"qty": 99999, "amount": 99999.0},
    }
    body.update(over)
    return body


def test_r3a_1_a_long_item_ranking_is_split_into_whatsapp_sized_parts() -> None:
    text = _report_ask(_body(200))
    assert len(text) > WHATSAPP_MESSAGE_MAX_CHARS, "harness: the ranking must be longer than one message"
    parts = re.split(r"\n\n(?=\(\d+/\d+\)\n)", text)
    assert len(parts) > 1 and parts[0].startswith("(1/"), text[:200]
    assert all(len(p) <= WHATSAPP_MESSAGE_MAX_CHARS for p in parts), [len(p) for p in parts]
    assert "ZZT-ITEM-0001" in parts[0] and "ZZT-ITEM-0200" in parts[-1], "no row is cut"


def test_r3a_1_guard_a_short_item_ranking_is_one_unmarked_message() -> None:
    text = _report_ask(_body(5))
    assert not text.startswith("(1/") and "\n\n(" not in text, text


def test_r3a_1_guard_a_long_customer_ranking_is_not_split_by_this_round() -> None:
    # Only item and category rankings carried the split; a customer or agent reply stays as it is.
    text = _report_ask(_body(5, group_by="customer"))
    assert not text.startswith("(1/"), text


def test_r3a_2_a_bottom_item_ranking_says_items_with_no_sale_are_not_ranked() -> None:
    text = _report_ask(_body(5, sort="asc"))
    assert "with no sale in this period are not ranked." in text, text


def test_r3a_2_a_bottom_category_ranking_says_categories_with_no_sale_are_not_ranked() -> None:
    text = _report_ask(_body(5, group_by="category", sort="asc"))
    assert "Categories with no sale in this period are not ranked." in text, text


def test_r3a_2_guard_a_top_ranking_has_no_such_line() -> None:
    assert "not ranked" not in _report_ask(_body(5)), "top ranking"


def test_r3a_2_guard_a_bottom_agent_ranking_has_no_such_line() -> None:
    assert "not ranked" not in _report_ask(_body(5, group_by="sales_agent", sort="asc"))
