"""AGENTIC-P1 round 8: the steps of a turn (from its stored trace) and the heading nit. Red first."""
from __future__ import annotations

import pytest

TRACE = [
    {"kind": "agent_round", "kind_of_call": "round", "prompt_tokens": 100, "completion_tokens": 10, "cached_tokens": 40, "ms": 5, "tool_calls": 2},
    {"kind": "agent_tool", "name": "crm_report_ask", "args": {}, "status": "ok", "ms": 120, "result_chars": 900, "more": 0},
    {"kind": "agent_tool", "name": "crm_resolve", "args": {}, "status": "empty", "ms": 3, "result_chars": 50, "more": 0},
    {"kind": "agent_round", "kind_of_call": "round", "prompt_tokens": 200, "completion_tokens": 20, "cached_tokens": 60, "ms": 6, "tool_calls": 1},
    {"kind": "agent_tool", "name": "answer", "args": {}, "status": "ok", "ms": 0, "result_chars": 5, "more": 0},
    {"kind": "agent_tool", "name": "plan", "args": {}, "status": "ok", "ms": 0, "result_chars": 5, "more": 0},
    {"kind": "agent_tool", "name": "(extra calls)", "args": {"skipped": 2}, "status": "denied", "ms": 0, "result_chars": 0, "more": 0},
    {"kind": "agent_round", "kind_of_call": "final", "prompt_tokens": 50, "completion_tokens": 5, "cached_tokens": 0, "ms": 4, "tool_calls": 1},
    {"stage": "received", "status": "ok"},
]


def test_steps_are_built_from_the_stored_trace():
    from app.services.chatbot.agent.memory import steps_from_trace

    steps = steps_from_trace(TRACE)
    assert steps == {
        "rounds": 2,
        "prompt_tokens": 350,
        "completion_tokens": 35,
        "cached_tokens": 100,
        "tool_calls": [
            {"name": "crm_report_ask", "status": "ok", "ms": 120},
            {"name": "crm_resolve", "status": "empty", "ms": 3},
        ],
    }


@pytest.mark.parametrize("trace", [None, [], "bad", [{"kind": "agent_tool"}], [None, 3]])
def test_a_missing_or_odd_trace_gives_empty_steps(trace):
    from app.services.chatbot.agent.memory import steps_from_trace

    steps = steps_from_trace(trace)
    assert steps["rounds"] == 0 and steps["prompt_tokens"] == 0 and steps["completion_tokens"] == 0
    assert steps["cached_tokens"] == 0
    assert steps["tool_calls"] == []


@pytest.mark.parametrize(
    "reply",
    ["### 3. Stock", "3.", "3) Incoming", "- 3. Stock", "## 12) Heading", "* 4. Item", "1. Stock\n2. Incoming"],
)
def test_a_number_in_a_heading_or_list_marker_is_never_a_figure(reply):
    from app.services.chatbot.agent.loop import unsupported_figures

    assert unsupported_figures(reply, []) == []


def test_a_real_number_after_a_heading_marker_is_still_checked():
    from app.services.chatbot.agent.loop import unsupported_figures

    assert unsupported_figures("### 3. Stock has 9,999", []) == ["9,999"]
    assert unsupported_figures("In 3. places", []) == ["3"]
