"""AC-1020: while a question is open, exactly three things can happen to it.

A casual or low-signal message leaves it open; a message carrying a domain or an entity
that does NOT answer it clears it with a trace line and is handled as a new ask; a newer
question replaces it. It never answers silently. `dialogue/clearing.py::apply` is the
function that decides the first two; the third is the caller (a lane) asking a fresh
question with `dialogue/open_question.py::ask` once clearing has made room for it.

RED: `app.services.chatbot.dialogue.clearing` does not exist yet.
"""
from __future__ import annotations


def _open_question(kind: str = "product_pick") -> dict:
    return {
        "kind": kind,
        "options": [{"idx": 1, "label": "ZZT product", "code": "ZZT-1", "domain": "inventory"}],
        "expects": "pick",
        "asked_at_turn": 3,
        "asked_at": None,
        "payload": {},
    }


def _casual_parse() -> dict:
    return {
        "message_type": "casual",
        "asks": [],
        "answers_open_question": {"resolved": False, "picks": [], "yes_no": None, "free_text": None},
        "anaphora": False,
        "topic_reset": False,
    }


def _new_ask_parse() -> dict:
    """A message that names a domain/entity but does not answer the open question."""
    return {
        "message_type": "business_query",
        "asks": [
            {
                "domain": "inventory",
                "entities": [
                    {
                        "raw": "ZZT-NEW",
                        "hint": "product",
                        "canonical_code": "ZZT-NEW",
                        "current_message": True,
                        "confident": True,
                    }
                ],
            }
        ],
        "answers_open_question": {"resolved": False, "picks": [], "yes_no": None, "free_text": None},
        "anaphora": False,
        "topic_reset": False,
    }


class TestOpenQuestionSurvivesOrClears:
    def test_a_casual_message_leaves_it_open(self) -> None:
        from app.services.chatbot.dialogue import clearing

        session = {"focus": {}, "open_question": _open_question()}
        new_session, trace_lines = clearing.apply(
            session, _casual_parse(), conversation_closed=False
        )
        assert new_session["open_question"] == _open_question()
        assert trace_lines == []

    def test_a_new_ask_that_does_not_answer_clears_it_with_a_trace_line(self) -> None:
        from app.services.chatbot.dialogue import clearing

        session = {"focus": {}, "open_question": _open_question()}
        new_session, trace_lines = clearing.apply(
            session, _new_ask_parse(), conversation_closed=False
        )
        assert new_session["open_question"] is None
        assert len(trace_lines) >= 1
        for line in trace_lines:
            assert set(line) >= {"slot", "reason"}
        assert any(line["slot"] == "open_question" for line in trace_lines)

    def test_a_newer_question_replaces_the_alive_one(self) -> None:
        from app.services.chatbot.dialogue import clearing
        from app.services.chatbot.dialogue import open_question as oq

        old_question = _open_question(kind="product_pick")
        session = {"focus": {}, "open_question": old_question}

        cleared_session, _trace_lines = clearing.apply(
            session, _new_ask_parse(), conversation_closed=False
        )
        assert cleared_session["open_question"] is None

        # The lane then opens a fresh question. It must be a wholesale replacement, not a
        # merge with what used to be open.
        cleared_session["open_question"] = oq.ask(
            "tier_pick", options=[{"code": "gold", "label": "Gold"}], turn_no=4
        )
        assert cleared_session["open_question"]["kind"] == "tier_pick"
        assert cleared_session["open_question"] != old_question
