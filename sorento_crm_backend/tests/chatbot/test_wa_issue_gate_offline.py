"""WA-COMPLAINT-INTAKE round 12: the frozen gate turns and the routing pin, offline (no LLM, no DB).

Contract: documentation/plans/chatbot/PROMPT-wa-issue-ideate.md, "Round 12".

* The gate turns live in `tests/chatbot/fixtures/wa_issue_gate_turns.json` (owner turns OWN1-OWN3, G01, G03,
  G05, G08, G09, and the negatives GD2, G10, GH1) and are run live by `test_wa_issue_parser_gate_live.py`. Here only their structure and
  expectations are pinned, so the live run cannot drift from the contract silently.
* The routing code needs no change: `turn/apply.py` `_HELP_EXEMPT_DOMAINS` already sends a `request_for_help`
  verdict whose `domain_hint` is ideate to the ideate lane, never to escalation. Pinned here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "wa_issue_gate_turns.json"

IDEATE = {"domain_hint": "ideate", "suggested_team": None}
EXPECTED = {
    "OWN1": IDEATE,
    "OWN2": IDEATE,
    "OWN3": IDEATE,
    "G05": IDEATE,
    "G01": IDEATE,
    "G03": IDEATE,
    "G08": {"domain_hint": "portal_link", "message_type_not": "request_for_help"},
    "G09": {"message_type": "request_for_help"},
    # Review N2: the gate's own negatives, frozen beside the positives.
    "GD2": {"domain_hint": "order", "message_type_not": "request_for_help", "domain_hint_not": "ideate"},
    "G10": {"domain_hint": "inventory"},
    "GH1": {"message_type": "request_for_help", "domain_hint_not": "ideate"},
}
OWNER_TEXT = "i want to report this is not the answer i want to the IT team"
MESSAGES = {
    "OWN1": OWNER_TEXT,
    "OWN2": OWNER_TEXT,
    "OWN3": "i want to report to the IT team",
    "G05": "hi good morning, the sales order list keeps loading and never opens",
    "G01": "the stock page shows a blank screen on my phone",
    "G03": "I want to report a problem",
    "G08": "the basin we delivered to the customer arrived cracked",
    "G09": "get me IT support",
    "GD2": "my order shows the wrong status",
    "G10": "how many SRTWC8152 do we have in stock",
    "GH1": "can someone call me about my quotation",
}
CONTACTS = {"GD2": "dealer", "G10": "staff", "GH1": "staff"}


def _turns() -> list[dict]:
    assert FIXTURE.is_file(), f"missing frozen gate turns {FIXTURE.name}"
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    return data


def test_R12_gate_fixture_holds_exactly_the_frozen_turns():
    turns = _turns()
    ids = [t["id"] for t in turns]
    assert len(ids) == len(set(ids)), "duplicate gate turn id"
    assert set(ids) == set(EXPECTED)


@pytest.mark.parametrize("turn_id", sorted(EXPECTED))
def test_R12_gate_turn_shape_and_expectation(turn_id):
    (turn,) = [t for t in _turns() if t["id"] == turn_id]
    assert set(turn) == {"id", "message", "previous_response", "contact", "expect"}
    assert turn["message"] == MESSAGES[turn_id]
    assert turn["contact"] in {"staff", "dealer"}
    assert isinstance(turn["previous_response"], str) and turn["previous_response"]
    assert turn["expect"] == EXPECTED[turn_id]
    if turn_id in CONTACTS:
        assert turn["contact"] == CONTACTS[turn_id]


def test_R12_owner_turn_1_carries_a_prior_bot_reply_and_turn_2_none():
    by_id = {t["id"]: t for t in _turns()}
    assert by_id["OWN1"]["previous_response"] != "(none)"
    assert by_id["OWN2"]["previous_response"] == "(none)"
    assert by_id["OWN3"]["previous_response"] == "(none)"


# --------------------------------------------------------------------------- #
# Routing pin: a help request about an issue report goes to ideate, not escalation
# --------------------------------------------------------------------------- #
def test_R12_request_for_help_with_ideate_domain_is_not_escalated():
    from app.services.chatbot.turn.apply import _lane, _lane_of
    from tests.chatbot._turn_helpers import build_policy

    verdict = {
        "message_type": "request_for_help",
        "domain_hint": "ideate",
        "intent_hint": "submit_idea",
        "routing": {"suggested_team": "it_admin", "suggested_agent": "it_support"},
        "escalation": {},
    }
    policy = build_policy()
    assert _lane_of(verdict, ["ideate"], policy) != "escalation"
    assert _lane(verdict, ["ideate"], policy) not in {"escalation", "escalation_barred"}
    assert _lane(verdict, ["ideate"], policy, barred=True) not in {"escalation", "escalation_barred"}


def test_R12_control_request_for_help_with_no_domain_still_escalates():
    """Control: the pin above is the exemption, not a lane that never escalates."""
    from app.services.chatbot.turn.apply import _lane_of
    from tests.chatbot._turn_helpers import build_policy

    verdict = {
        "message_type": "request_for_help",
        "domain_hint": None,
        "intent_hint": None,
        "routing": {"suggested_team": "it_admin", "suggested_agent": "it_support"},
        "escalation": {},
        "entities": [],
    }
    assert _lane_of(verdict, [], build_policy()) == "escalation"
