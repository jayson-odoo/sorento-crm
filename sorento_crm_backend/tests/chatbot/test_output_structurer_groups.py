"""A3 - `output_structurer` renders `groups[]` as headed sections, ONE generic
branch for every tool (AC-905, AC-906).

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A;
`documentation/plans/chatbot/chatbot-growth-r1-acceptance-criteria.md` section A.
"""
from __future__ import annotations

from app.services.chatbot.lanes.business import fetch


def _grouped_envelope() -> dict:
    return {
        "result_type": "orders",
        "intro": "Here are the orders I found.",
        "items": [
            {"title": "A1", "fields": [{"key": "order_number", "label": "Order Number", "value": "A1"}]},
            {"title": "B1", "fields": [{"key": "order_number", "label": "Order Number", "value": "B1"}]},
        ],
        "groups": [
            {
                "key": "ABC",
                "label": "ABC",
                "items": [
                    {"title": "A1", "fields": [{"key": "order_number", "label": "Order Number", "value": "A1"}]},
                ],
            },
            {
                "key": "XYZ",
                "label": "XYZ",
                "items": [
                    {"title": "B1", "fields": [{"key": "order_number", "label": "Order Number", "value": "B1"}]},
                ],
            },
        ],
        "has_result": True,
    }


def test_groups_render_as_headed_sections_in_the_reply_text():
    out = fetch.output_structurer(_grouped_envelope(), {"semantic_input": {}})
    assert "*ABC*" in out["response"]
    assert "*XYZ*" in out["response"]
    assert "1. *Order Number:* A1" in out["response"]
    assert "2. *Order Number:* B1" in out["response"]


def test_groups_do_not_replace_the_flat_answers_state():
    """Grouping is presentation only - a positional pick still resolves against
    the FLAT `answers`, never a per-group slice."""
    out = fetch.output_structurer(_grouped_envelope(), {"semantic_input": {}})
    assert len(out["answers"]) == 2
    assert out["groups"][0]["key"] == "ABC"


def test_no_groups_key_leaves_the_flat_numbered_list_unchanged():
    envelope = _grouped_envelope()
    del envelope["groups"]
    out = fetch.output_structurer(envelope, {"semantic_input": {}})
    assert "groups" not in out
    assert "1. *Order Number:* A1" in out["response"]
    assert "2. *Order Number:* B1" in out["response"]
    assert "*ABC*" not in out["response"]


def test_qs_render_takes_priority_over_groups():
    """A quantity ask (`summary_items` present) suppresses the row list - grouped
    or not, same rule as today (`qs_render`)."""
    envelope = _grouped_envelope()
    envelope["summary_items"] = [
        {"title": None, "fields": [{"key": "x", "label": "Total", "value": 2}]}
    ]
    out = fetch.output_structurer(envelope, {"semantic_input": {}})
    assert "*ABC*" not in out["response"]
    assert "1. *Order Number:*" not in out["response"]
