"""REPORT-SMART-L review blocker: `apply()`'s report-domain read must not undo an engine reroute.

`required_fields.reply_verdict` (engine, after the routing seam) reroutes a short reply under an
open ideation question to `domain_hint "ideate"`, and a reply to a chat report question to
`chat_analytics` (the chat report case is already broken at c925b50327, so no test here). The entry read in `turn/apply.py` (`report_domain`) re-derived the domain from
the report status and turned both back into `order`. Parser fields only; the words are decoration.
"""
from __future__ import annotations

import pytest

from tests.chatbot.test_engine import (  # noqa: F401 - fixtures reused by name
    seeded,
    stub_access,
    stub_parser,
)
from tests.chatbot.test_ideation_required_ask import (
    ASK_REPLY,
    DONE_REPLY,
    IDEATE_PARSE,
    _fake_tool,
    _result,
    _say,
)
from tests.chatbot.test_s3_canned_and_ideate import _seed_completed_lanes

IDEA_REPLIES = [
    ("outstanding order alerts", "outstanding"),
    ("overdue orders alert", "outstanding"),
    ("未交货 订单 提醒", "outstanding"),
    ("amaran order tertunggak", "outstanding"),
    ("pending order digest", "outstanding"),
    ("订单 逾期 通知", "outstanding"),
    ("order tertunggak report", "outstanding"),
    ("late order nudge", "outstanding"),
]


@pytest.mark.parametrize("body, status", IDEA_REPLIES)
def test_a_short_reply_under_the_open_idea_question_is_captured_as_the_idea(
    session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch, body, status
) -> None:
    _seed_completed_lanes(session_factory, system_settings_row)
    stub_access()
    calls = _fake_tool(monkeypatch, [_result("ask_idea", ASK_REPLY), _result("complete", DONE_REPLY)])

    _say(session_factory, stub_parser, IDEATE_PARSE, "want to submit idea", "ZZT-rk-a")
    result = _say(
        session_factory, stub_parser,
        dict(message_type="business_query", intent_hint="check_order", domain_hint="order", order_status=status),
        body, "ZZT-rk-b",
    )
    assert len(calls) == 2, calls  # the reply reached the intake tool, not the order lane
    assert calls[1]["ask_reply"] is True and calls[1]["message_text"] == body, calls[1]
    assert result.reply["text"] == DONE_REPLY, result.reply
