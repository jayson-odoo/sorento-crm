"""Merge of main d8395cb8 into chatbot memory lane A: PR #1247's round 8 and round 9
user-block lines (the open task lines, the `Open question: {...}` object, the "Recent
exchanges" pairs) reach the parser through `turn/context.py::assemble` at EVERY level.

Before the merge the engine built the parser block with `context.assemble`, which knew
none of those three, while main's `parser.build_user_block` printed all three - so the
merged engine would have silently dropped main's round 8/9 context for every contact.

Pure Python, no database.
"""
from __future__ import annotations

import json

from app.services.chatbot.head import parser
from app.services.chatbot.turn import context

OPEN_QUESTION = {
    "kind": "quantities",
    "items": [{"position": 1, "code": "SRTWB1455", "qty": None}],
    "owed": ["quantity"],
}
PREVIOUS = "How many units of SRTWB1455 do you need?"
RECENT = [
    ("stock SRTWB1455", "SRTWB1455 is in stock at BRW."),
    ("and in kuching?", PREVIOUS),
]
TASK_LINES = ["Open task: stock check SRTWB1455, quantity still needed."]


def _layers(level: str, **overrides) -> context.ContextLayers:
    kwargs = dict(
        level=level,
        profile_facts=[{"key": "customer", "value": "Chin Chun Trading"}],
        summaries=["Thu 25 Sep: stock SRTWB1455 (answered)."],
        earlier_messages=[
            {"created_at": "Thu 10:00", "text": "hello"},
            {"created_at": "Thu 10:02", "text": "stock SRTWB1455"},
        ],
        previous_response=PREVIOUS,
        current_subject="domain inventory; product SRTWB1455",
        pending_kind=None,
        pending_options=None,
        settings_profile_line=None,
        current_message="10",
        reply_to=None,
        media_line=None,
        task_lines=TASK_LINES,
        open_question_line=parser.open_question_line(OPEN_QUESTION),
        recent_exchanges=RECENT,
    )
    kwargs.update(overrides)
    return context.ContextLayers(**kwargs)


class TestOffLevelIsMainsBlock:
    def test_off_level_equals_mains_build_user_block_with_round_9_lines(self) -> None:
        main_block = parser.build_user_block(
            previous_response=PREVIOUS,
            latest_user_message="10",
            pending_kind="quantity",
            pending_options=None,
            profile_block="Profile: tier gold",
            focus=None,
            open_question=OPEN_QUESTION,
            recent_exchanges=RECENT,
        )
        text, _report = context.assemble(
            _layers(
                "off",
                current_subject=None,
                task_lines=parser.open_task_lines(None, OPEN_QUESTION),
                pending_kind="quantity",
                settings_profile_line="Profile: tier gold",
            )
        )
        assert text == main_block, (text, main_block)
        assert "Open question: " in text
        assert "Recent exchanges, oldest first:" in text


class TestEveryMemoryLevelKeepsRound9Context:
    def test_full_level_carries_task_lines_open_question_and_exchanges(self) -> None:
        text, _report = context.assemble(_layers("full"))
        assert TASK_LINES[0] in text
        assert "Open question: " + json.dumps(OPEN_QUESTION, separators=(",", ":")) in text
        assert "Recent exchanges, oldest first:\nUser: stock SRTWB1455\n" in text
        # The newest reply IS the Previous response line, not paid for twice.
        assert "Assistant: (the Previous response)" in text
        assert f"Previous response: {PREVIOUS}" in text

    def test_conversation_level_carries_them_too(self) -> None:
        text, _report = context.assemble(_layers("conversation"))
        assert TASK_LINES[0] in text
        assert "Open question: " in text
        assert "Recent exchanges, oldest first:" in text

    def test_open_question_sits_in_l2_before_the_current_message(self) -> None:
        text, report = context.assemble(_layers("full"))
        assert text.index("Current subject:") < text.index("Open question: ")
        assert text.index("Open question: ") < text.index("Current user message: 10")
        l2 = next(row for row in report["layers"] if row["layer"] == "L2")
        assert l2["est_tokens"] >= context.est_tokens(parser.open_question_line(OPEN_QUESTION))

    def test_an_earlier_message_the_exchanges_already_print_is_not_repeated(self) -> None:
        text, _report = context.assemble(_layers("full"))
        assert "User: stock SRTWB1455" in text
        assert "you: hello" in text
        assert "you: stock SRTWB1455" not in text


class TestL3BudgetDropsTheOlderLayerFirst:
    def test_earlier_messages_go_before_any_exchange_and_the_newest_exchange_stays(self) -> None:
        long_reply = "x" * 480
        recent = [
            ("first ask", long_reply),
            ("second ask", long_reply),
            ("third ask", PREVIOUS),
        ]
        earlier = [{"created_at": "Thu 09:00", "text": "y" * 190} for _ in range(3)]
        text, report = context.assemble(
            _layers("full", recent_exchanges=recent, earlier_messages=earlier)
        )
        l3 = next(row for row in report["layers"] if row["layer"] == "L3")
        assert l3["dropped"] is True
        assert "Earlier in this conversation" not in text
        assert "User: third ask" in text
        assert l3["est_tokens"] <= context.CAPS["L3"]
