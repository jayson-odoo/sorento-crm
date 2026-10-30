"""CHATBOT-FAIL-TRIAGE-B2 AC-7f: what main does today with the parser's team word.

Stubbed parser; the seam is `test_pass4_item1b_marketing_ambiguous_clarify.py`'s. Asserts only
what holds with and without #2018: the clarify options and no silent route.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output
from tests.chatbot.test_r3_pending_end_to_end import _stub_parser

MARKETING = ("marketing product", "marketing form", "marketing promotion")
OTHERS = ("purchasing", "customer service", "warehouse", "it admin")


@pytest.fixture()
def seeded(session_factory):
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": str(CONTACT_ID), "phone": "+60000000009", "sv": json.dumps({"variables": {}})},
    )
    db.commit()
    set_chatbot_switches(session_factory)
    db.execute(text("UPDATE system_settings SET chatbot_completed_lanes = CAST(:l AS jsonb)"), {"l": '["out_of_scope"]'})
    db.commit()
    return db


def _ask(session_factory, monkeypatch, *, team, said):
    qf = _parser_output(
        message_type="request_for_help", intent_hint=None, domain_hint=None, entities=[],
        is_affirmative=True, user_goal=f"trying to escalate to {said}",
        routing={"suggested_team": team, "suggested_agent": None},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    _stub_parser(monkeypatch, qf)
    envelope = _envelope(is_test=True)
    envelope.contact["phone"] = "+60000000009"
    envelope.message["contact"]["phone"] = "+60000000009"
    envelope.message["message"]["messageId"] = f"ZZT-b2-team-{team}"
    envelope.message["message"]["message"]["text"] = f"escalate to {said}"
    return engine_mod.run_turn(envelope, session_factory=session_factory)


def _send_text(head) -> str:
    return " ".join((a.get("text") or "") for a in (head.actions or []) if a.get("kind") == "send_message")


def _comments(head):
    return [a for a in (head.actions or []) if a.get("kind") == "add_comment"]


def test_marketing_word_asks_once_over_exactly_the_marketing_teams(seeded, session_factory, monkeypatch):
    head = _ask(session_factory, monkeypatch, team="marketing", said="marketing")
    assert head.branch_kind == "out_of_scope", (head.branch_kind, head.error)
    assert not _comments(head), _comments(head)
    body = _send_text(head)
    assert all(t in body for t in MARKETING), body
    assert not any(t in body for t in OTHERS), body
    assert "Sorry" not in body, body


def test_marketing_product_routes_to_that_team_without_a_clarify(seeded, session_factory, monkeypatch):
    head = _ask(session_factory, monkeypatch, team="marketing_product", said="product marketing team")
    assert head.branch_kind == "out_of_scope", (head.branch_kind, head.error)
    comments = _comments(head)
    assert comments and any("marketing" in (c.get("text") or "").lower() and "product" in (c.get("text") or "").lower() for c in comments), (comments, head.actions)
    assert not any(t in _send_text(head) for t in ("marketing form", "marketing promotion")), _send_text(head)


def test_an_unknown_team_word_asks_over_the_teams_never_a_default(seeded, session_factory, monkeypatch):
    head = _ask(session_factory, monkeypatch, team="sales", said="sales team")
    assert head.branch_kind == "out_of_scope", (head.branch_kind, head.error)
    assert not _comments(head), f"an unknown team word must ask, never assign: {_comments(head)!r}"
    body = _send_text(head)
    assert "Sorry" not in body, body
    assert all(t in body for t in ("purchasing", "customer service", "warehouse")), body
