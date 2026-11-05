"""AI tools standard, DoD line 8: the `assistant` eval case type (scripts/chatbot_eval/cases.py).

Gold rows name the entity the agent should read or the action it should propose; the grader reads the
turn digest's tool list (trace.build_digest). PLAN-ai-tools-standard-5nov.md 2.5, PLAN-ai-gate-5nov.md.
"""
from __future__ import annotations

import json

import pytest

from scripts.chatbot_eval.cases import (
    grade_assistant,
    load_assistant_gold,
    parse_assistant_case,
)


def _row(**over):
    row = {"id": "asst-scm-01", "module": "scm", "message": "approved POs for Kohler in October?",
           "expect": {"entity": "purchase_order"}}
    row.update(over)
    return row


def test_parse_entity_and_action_cases():
    c = parse_assistant_case(_row())
    assert (c.entity, c.action, c.module) == ("purchase_order", None, "scm")
    a = parse_assistant_case(_row(id="asst-scm-02", expect={"action": "purchase_order.approve"}))
    assert (a.entity, a.action) == (None, "purchase_order.approve")


@pytest.mark.parametrize(
    "over, reason",
    [
        ({"expect": {}}, "missing expect"),
        ({"expect": {"entity": "po", "action": "po.approve"}}, "exactly one"),
        ({"expect": {"entity": "po", "tool": "crm_query"}}, "unknown expect key"),
        ({"expect": {"action": "approve"}}, "<entity>.<verb>"),
        ({"module": ""}, "missing module"),
        ({"message": {"text": "hi"}}, "not text"),
    ],
)
def test_parse_refuses_bad_rows(over, reason):
    with pytest.raises(ValueError, match=reason.replace(".", r"\.").replace("<", "<")):
        parse_assistant_case(_row(**over))


def test_load_reads_assistant_files_only_and_reports_bad_lines(tmp_path):
    good = [_row(), _row(id="asst-scm-02", expect={"action": "purchase_order.approve"})]
    (tmp_path / "assistant_scm.jsonl").write_text(
        "\n".join(json.dumps(r) for r in good) + "\n\nnot json\n" + json.dumps(_row()) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "parser_x.jsonl").write_text("garbage\n", encoding="utf-8")
    cases, invalid = load_assistant_gold(tmp_path)
    assert [c.id for c in cases] == ["asst-scm-01", "asst-scm-02"]
    assert [w for w, _ in invalid] == ["assistant_scm.jsonl:4", "assistant_scm.jsonl:5"]
    assert "duplicate id" in invalid[1][1]


def test_committed_assistant_gold_is_valid():
    """Every committed gold/assistant_*.jsonl row parses and ids are unique across files."""
    _cases, invalid = load_assistant_gold()
    assert invalid == []


def test_grade_entity():
    case = parse_assistant_case(_row())
    tools = [{"tool": "crm_describe", "args": {}},
             {"tool": "crm_query", "args": {"entity": "purchase_order", "limit": 20}}]
    assert grade_assistant(case, tools)[0] == "pass"
    verdict, reason = grade_assistant(case, [{"tool": "crm_query", "args": {"entity": "order"}}])
    assert verdict == "fail" and "crm_query:order" in reason
    assert grade_assistant(case, [])[0] == "no_trace"
    assert grade_assistant(case, None)[0] == "no_trace"


def test_grade_action():
    case = parse_assistant_case(_row(expect={"action": "purchase_order.approve"}))
    assert grade_assistant(case, [{"tool": "crm_act", "args": {"action": "purchase_order.approve"}}])[0] == "pass"
    # reading the right entity is not doing the action
    verdict, reason = grade_assistant(case, [{"tool": "crm_query", "args": {"entity": "purchase_order"}},
                                             {"tool": "crm_act", "args": {"action": "purchase_order.send"}}])
    assert verdict == "fail" and "crm_act:purchase_order.send" in reason
