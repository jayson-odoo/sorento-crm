"""AGENTIC-IDEATE R3b (AC-R3b-1, AC-R3b-2): the agent marks a turn that ended by asking the user.

Uses the scripted-provider harness of test_agent_loop.py. No live LLM, no network.
"""
from __future__ import annotations

from app.models.chatbot_turn import ChatbotTurn
from app.services.llm_provider import ChatResult
from tests.chatbot.agent.test_agent_loop import (  # noqa: F401
    ScriptedProvider,
    _set_budgets,
    _turn_row,
    answer,
    asks,
    call,
    contact,
    db,
    plain,
    run,
)


def answer_asking(text, *, asked_back=True, cid="ans-1"):
    """A final `answer` call that also carries `asked_back`."""
    return ChatResult(
        content="", prompt_tokens=100, completion_tokens=10, total_tokens=110,
        tool_calls=[
            {
                "id": cid,
                "name": "answer",
                "arguments": {
                    "text": text, "figures": [], "not_found": [], "not_checked": [], "asked_back": asked_back,
                },
            }
        ],
    )


def test_AC_R3b_1_a_final_answer_with_asked_back_stores_true(db, contact):
    result = run(db, contact, ScriptedProvider([answer_asking("What is the idea?")]), text="I want to submit an idea")
    assert _turn_row(db, result).response["asked_back"] is True


def test_AC_R3b_1_a_final_answer_without_it_has_no_key(db, contact):
    result = run(db, contact, ScriptedProvider([answer("Hello.")]), text="hello")
    assert "asked_back" not in _turn_row(db, result).response


def test_AC_R3b_1_a_plain_text_final_has_no_key(db, contact):
    result = run(db, contact, ScriptedProvider([plain("Here you go."), plain("Here you go.")]), text="hello")
    assert "asked_back" not in _turn_row(db, result).response


def test_AC_R3b_1_a_forced_final_at_a_limit_has_no_key(db, contact):
    _set_budgets(db, chatbot_agent_max_rounds=2)
    provider = ScriptedProvider([asks(call(cid="c1")), asks(call(cid="c2")), answer("I could only check part of it.")])
    result = run(db, contact, provider)
    row = _turn_row(db, result)
    assert row.response["status"] == "limited"
    assert "asked_back" not in row.response


def test_AC_R3b_1_a_flagged_forced_final_at_a_limit_drops_the_flag(db, contact):
    _set_budgets(db, chatbot_agent_max_rounds=2)
    provider = ScriptedProvider(
        [asks(call(cid="c1")), asks(call(cid="c2")), answer_asking("I could only check part. Which one?")]
    )
    result = run(db, contact, provider)
    row = _turn_row(db, result)
    assert row.response["status"] == "limited"
    assert "asked_back" not in row.response


def test_AC_R3b_2_the_answer_schema_declares_asked_back():
    from app.services.chatbot.agent import tools

    params = tools.ANSWER_SCHEMA["function"]["parameters"]
    prop = params["properties"].get("asked_back")
    assert prop is not None, "ANSWER_SCHEMA has no asked_back property"
    assert prop["type"] == "boolean"
    assert "asked_back" not in params.get("required", [])
    assert "ask" in prop.get("description", "").lower() or "ask" in tools.ANSWER_SCHEMA["function"]["description"].lower().split("asked_back")[-1]
