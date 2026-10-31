"""Owner rule: a turn is never answered with a blank reply. The `out_of_scope` arm.

Crew eval, 12 Oct 2026 (dry run, test envelope): a "request_for_help" verdict with no
domain, no intent, ZERO entities and a null routing went to `out_of_scope`, and the turn's
reply text was "" with no error and no tool error. The only log line was the dry-run
escalation preview's known 404 ("No team found ... customer_service"). The same message
parsed with one customer entity went `business_query` and answered normally.

The lane DOES build the customer's one message (`ROUTED_TO_PIC_REPLY`, WA-MSG-TRIM) as a
`send_message` action, but the tail composed no text on this arm (`escalate-catalog`'s
`includeResponse: false`), so the turn's `reply.text` - what the console, the eval, the
next turn's `Previous response:` and the chat-history link all read - was null.

CHATBOT-FAIL-TRIAGE AC-7c (#2018, owner 30 Oct 2026: "we shouldn't do no topic escalate to
marketing product, we should clarify"): that same topic-less verdict now asks ONE topic
question instead of routing to a default team. The never-blank rule is unchanged: the
question is the turn's reply, the sent message and the stored row. The routed hand-over
line is pinned on a verdict that names its topic (`inventory`).

Driven through `engine.run_turn` with the harness's `mock_reformulator_output` (G6), so
nothing reaches an LLM. Postgres only, blank schema, via `tests/chatbot/conftest.py`.
"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from fastapi import HTTPException

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot.lanes import escalation_services
from app.services.chatbot.lanes.escalation import ROUTED_TO_PIC_REPLY
from tests.chatbot.test_engine import (  # noqa: F401 - fixtures used by name
    _envelope,
    _turn_row,
    seeded,
    stub_access,
)


def _eval_verdict(domain_hint: str | None = None) -> dict[str, Any]:
    """The crew eval's verdict: every declared key present, almost all of them null."""
    verdict: dict[str, Any] = {key: None for key in parser_mod.DECLARED_KEYS}
    verdict.update(
        {
            "message_type": "request_for_help",
            "domain_hint": domain_hint,
            "intent_hint": None,
            "entities": [],
            "access_levels": [],
            "requested_attributes": [],
            "reference_positions": [],
            "correction": False,
            "contains_flyer": False,
            "routing": {"suggested_team": None, "suggested_agent": None, "team_source": None},
            "escalation": {"is_escalation_confirmation": False, "company_pick": None},
        }
    )
    return verdict


@pytest.fixture()
def no_parser_call(monkeypatch):
    """G6 bypasses the parser; make a call to it fatal so a fall-through cannot pass."""

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub",
            prompt_version=1,
            provider="openai",
            model="gpt-test",
            api_key="sk-test",
        )

    def never(config, user_block):  # pragma: no cover - the assertion IS that it never runs
        raise AssertionError("the parser was called on a harness-bypassed turn")

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", never)


@pytest.fixture()
def no_team_found(monkeypatch):
    """The eval's log line: the dry-run preview's next-assignee read 404s for the team."""
    real_build = escalation_services.build
    calls: list[dict[str, Any]] = []

    def preview(body: dict[str, Any]) -> dict[str, Any]:
        calls.append(body)
        raise HTTPException(
            status_code=404,
            detail=(
                f"No team found for agent and team_code={body.get('team_code')!r} in company "
                "None. Configure that company's team set before routing to it."
            ),
        )

    monkeypatch.setattr(
        escalation_services,
        "build",
        lambda db: dataclasses.replace(real_build(db), preview_assignee=preview),
    )
    return calls


# AC-7c: the topic question over every topic, as `lanes/escalation._topic_clarify` words it
# when the company's reachable pairs are not narrowed (`reachable is None`).
TOPIC_CLARIFY_REPLY = (
    "Which topic is this about - Orders & delivery, Stock & ETA, Product info, Promotions or Forms?"
)


def _run(session_factory, message_id: str, domain_hint: str | None = None):
    return engine_mod.run_turn(
        _envelope(
            is_test=True,
            test_run_id=f"ZZT-oos-blank-{message_id}",
            mock_reformulator_output=_eval_verdict(domain_hint),
        ),
        session_factory=session_factory,
    )


def _assert_reply(session_factory, result, expected: str) -> None:
    assert result.branch_kind == "out_of_scope"
    assert result.status == "done", result
    sends = [a for a in result.actions if a.get("kind") == "send_message"]
    assert [a["text"] for a in sends] == [expected], result.actions

    # The turn's own reply is the message the customer is sent, never blank.
    assert result.reply["text"] == expected, result.reply

    # The persisted row agrees: the console, the eval and the next turn's
    # `Previous response:` all read `response.reply.text` off it.
    row = _turn_row(session_factory, result.turn_id)
    assert row.response["reply"]["text"] == expected, row.response.get("reply")


def test_no_entity_no_topic_request_for_help_asks_the_topic_never_blank(
    session_factory, seeded, stub_access, no_parser_call
) -> None:
    stub_access()
    _assert_reply(session_factory, _run(session_factory, "plain"), TOPIC_CLARIFY_REPLY)


def test_no_entity_request_for_help_with_a_topic_gets_the_handover_reply(
    session_factory, seeded, stub_access, no_parser_call
) -> None:
    stub_access()
    _assert_reply(session_factory, _run(session_factory, "topic", "inventory"), ROUTED_TO_PIC_REPLY)


def test_no_team_found_on_the_preview_still_gets_the_handover_reply(
    session_factory, seeded, stub_access, no_parser_call, no_team_found
) -> None:
    stub_access()
    _assert_reply(session_factory, _run(session_factory, "no-team", "inventory"), ROUTED_TO_PIC_REPLY)
    assert no_team_found, "the preview never ran: the 404 this test is about was not reached"


def test_a_voice_turn_handover_sends_and_persists_the_same_prefixed_line() -> None:
    """A voice/image turn that ends in a hand-over (reviewer should-fix, 16 Oct 2026).

    Before the fix the reply was blank, so `_apply_media_reply_prefix` wrote only the
    "I heard: ..." line into the reply and left the sent action unprefixed: the stored
    reply and the sent message disagreed. With the hand-over line in the reply, the
    prefix lands on both (AC-1817), so the customer reads one message and the record
    matches it.
    """
    from app.services.chatbot.media_intake import MediaIntakeOutcome

    outcome = MediaIntakeOutcome(
        modality="voice",
        decision="accept",
        status="completed",
        stops_here=False,
        rendered_text="can someone help me",
    )
    result = engine_mod.TurnResult(
        reply={"text": ROUTED_TO_PIC_REPLY},
        actions=[{"kind": "send_message", "text": ROUTED_TO_PIC_REPLY}],
    )
    engine_mod._apply_media_reply_prefix(result, outcome)

    expected = f"I heard: can someone help me\n{ROUTED_TO_PIC_REPLY}"
    assert result.reply["text"] == expected
    assert [a["text"] for a in result.actions] == [expected]
