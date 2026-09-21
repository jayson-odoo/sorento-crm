"""Owner console pass 4, item 1a (7 Sep 2026): a `team_clarify` answer is never consumed.

Production turns 08e74db8-91e9-48d9-9d6e-a5a7ca42aad5 -> 0d7d5a23-f5f3-46e5-92d6-a7f31c10560b
(n8n execs 15500464 / 15500487, `turns-lane3`), replayed here with the parser stubbed at the
`_parser_raw` seam (D11 / LESSONS-LEARNT #102 - the production shape, not an n8n-invented one).

Turn 1: no pending offer, previous domain `master_products`, previous routing carried
`purchasing`. "escalate to marketing" arrives `request_for_help` with `routing.suggested_team:
null` (the parser named no team). `branch_kind == "out_of_scope"` runs `_run_escalation_arm`
IN-PROCESS (`engine.py:1875`), which reaches `escalation.py`'s D1 clarify arm
(`_person_routing`, ~:692-762): no parser team, no open offer, but the previous turn's routing
(`purchasing`) is not the chain's hard default (H64/AC-815), so it asks "Which team should I
pass this to - ... or it admin?" and persists `selection_context: team_clarify`
(`tail/compile_state.py:2074`).

Turn 2: "marketing product" answers that ask. The parser's OWN raw team for this turn is
`marketing_product` (`_parser_raw.routing.suggested_team`) - measured off the production
capture. But the parser also emits `message_type: casual` for this bare noun phrase (no verb),
and `output_exchange.py`'s routing chain only reads `llm_team_n` when `req_help` is true
(~line 2120: `suggested_team = _nullish(llm_team_n if req_help else None, ...)`) - so a
NON-`request_for_help` team pick is discarded outright, the chain falls through to
`prior_routing.suggested_team` (the STALE `purchasing` carried from before the escalation was
even asked for), and `route.decide`'s `is_low_signal()` arm (`message_type == "casual"`)
answers with the canned "Hi! How can I help you today?" - never reading
`selection_context: team_clarify` at all. `grep -rn '"team_clarify"' app/services/chatbot/`
shows the marker is WRITTEN (`tail/compile_state.py:2074`) but nothing in `head/route.py` or
`head/output_exchange.py` ever reads `previous_conversation_state.selection_context` to relax
the `req_help` gate or to keep routing the turn back to the escalation lane - there is no
consumer of a `team_clarify` answer today.

This is a genuinely unbuilt consumption path, not a narrow regression - Phase 2 test-first
per PRINCIPLES.md, red before the fix exists.

Retired 16 Sep 2026 (AC-1592, coordinator ruling, "team_pick Pending shape") -
`TestATeamClarifyAnswerIsConsumedAndResolvesTheEscalation.test_marketing_product_
after_a_team_clarify_ask_assigns_to_marketing_product`,
`TestTheTeamClarifyHasABoundedLifetime.test_an_unanswered_clarify_is_gone_the_
next_turn_even_with_a_stale_roster`, `TestATapOnAPersistedQuickReplyResolvesThe
Clarify.test_a_reply_equal_to_a_persisted_option_label_assigns_that_team`. All
three build state around the OLD, pre-rearch `selection_context: "team_clarify"`
marker and a `pending.kind: "team_clarify"` - neither exists under the S3 rearch:
`"team_clarify"` is not a member of `PENDING_KINDS`' eight-name vocabulary
(`_turn_helpers.py`), superseded by `"team_pick"`. Replacement coverage:
`test_rearch_s3_team_pick_and_866.py::TestPort866AsRunTurnCases.
test_108_family_word_resolves_open_offers_team` covers the direct parallel of
this file's own "answer with a family word resolves the open team offer" claim.
`TestABusinessQuestionIsNotReadAsAClarifyAnswer.test_a_business_query_naming_a_
team_is_answered_not_escalated` is NOT retired - it only asserts a NEGATIVE
(`branch_kind != "out_of_scope"`), true regardless of whether team_clarify itself
still resolves, and stayed green.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output
from tests.chatbot.test_r3_pending_end_to_end import _stub_parser
from tests.chatbot.test_s5_escalation_lane import _services


@pytest.fixture()
def stub_assignment_seams(monkeypatch):
    """The round-robin draw and the SLA write, stubbed. Nothing else.

    Both turns here run LIVE (`is_test=False`), because a dry run is isolated from the
    session (AC-812) and the "the marker is cleared" assertion below reads the session -
    with `is_test=True` it would read turn 1's state back and could never be false.

    A live assignment needs an `sla_policies` row with code `NORMAL`, a team, its members
    and a round-robin cursor, none of which exist on a blank test schema and none of which
    this file is about. `escalation_services.build` is the seam the lane already has for
    exactly this, so the LANE runs for real - the clarify decision, the catalogue
    narrowing, the tail, the session write - and only the two writes are stood in for."""
    from app.services.chatbot.lanes import escalation_services

    monkeypatch.setattr(escalation_services, "build", lambda db: _services())


@pytest.fixture()
def seeded(session_factory):
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {
            "cid": str(CONTACT_ID),
            "phone": "+60000000009",
            "sv": json.dumps(
                {
                    "variables": {
                        "message_type": "business_query",
                        "intent_hint": "check_product",
                        "domain_hint": "master_products",
                        "entities": [
                            {
                                "raw": "srtwc287",
                                "hint": "product",
                                "canonical_code": "SRTWC287",
                                "current_message": True,
                                "confident": True,
                            }
                        ],
                        "routing": {
                            "suggested_team": "purchasing",
                            "suggested_agent": "general_enquiries",
                        },
                        "escalation": {"is_escalation_confirmation": False},
                        "response": "Previous turn (master_products): returned 15 records",
                        "selection_context": None,
                        "pending": None,
                    }
                }
            ),
        },
    )
    db.commit()
    # `out_of_scope` only completes in-process once the OWNER has switched it on
    # (`delegate.delegate_for`, D5) - a fresh blank schema has no `system_settings` row.
    set_chatbot_switches(session_factory)
    db.execute(text("UPDATE system_settings SET chatbot_completed_lanes = CAST(:l AS jsonb)"), {"l": '["out_of_scope"]'})
    db.commit()
    return db


# --------------------------------------------------------------------------- #
# Opus review of #713, blocker B1. The docstrings, AC-822 and the PR body all
# claimed the clarify expires after one turn because `_offer_carry` needs a
# roster and a clarify has none. MEASURED FALSE: the clarify arm carries the
# PREVIOUS turn's roster forward (`tail/compile_state.py` ~:2075) BEFORE it
# stamps the marker (~:2081), and production dump 0d7d5a23's own
# `previous_conversation_state` is `team_clarify` with a `last_result_set` of
# FIFTEEN rows (the mt-r2 dumps carry ten). `topic.changed` returns False
# whenever either domain is falsy and a clarify turn's `domain_hint` is None, and
# the ttl branch is `member_offer` only - so the label was carried indefinitely.
# --------------------------------------------------------------------------- #

CLARIFY_OPTIONS = [
    {"team": "marketing_product", "label": "marketing product"},
    {"team": "marketing_form", "label": "marketing form"},
    {"team": "marketing_promotion", "label": "marketing promotion"},
]

# The roster the production dump carries under its `team_clarify` label: rows left
# over from an EARLIER, unrelated customer picker. Non-empty is the whole point -
# an empty one cannot tell the fixed carry from the broken one.
STALE_ROSTER = [
    {"idx": i, "uuid": f"ZZT-stale-{i}", "label": f"ZZT Stale Row {i}", "entity_type": "customer"}
    for i in range(1, 16)
]


def _seed_open_team_clarify(session_factory, *, roster=None) -> None:
    """The state a team-clarify ask persists, in the shape production writes it."""
    db = session_factory()
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE respond_io_id = :cid"),
        {
            "cid": str(CONTACT_ID),
            "sv": json.dumps(
                {
                    "variables": {
                        "message_type": "request_for_help",
                        "intent_hint": None,
                        "domain_hint": None,
                        "entities": [],
                        "routing": {
                            "suggested_team": "customer_service",
                            "suggested_agent": "general_enquiries",
                        },
                        "escalation": {"is_escalation_confirmation": False},
                        "response": (
                            "Which team should I pass this to - marketing product, "
                            "marketing form or marketing promotion?"
                        ),
                        "selection_context": "team_clarify",
                        "last_result_set": STALE_ROSTER if roster is None else roster,
                        "pending": {
                            "kind": "team_clarify",
                            "team": "customer_service",
                            "domain": None,
                            "options": CLARIFY_OPTIONS,
                        },
                    }
                }
            ),
        },
    )
    db.commit()


def _run(session_factory, monkeypatch, *, qf, text_body, msg_id):
    _stub_parser(monkeypatch, qf)
    envelope = _envelope(is_test=False)
    envelope.contact["phone"] = "+60000000009"
    envelope.message["contact"]["phone"] = "+60000000009"
    envelope.message["message"]["messageId"] = msg_id
    envelope.message["message"]["message"]["text"] = text_body
    return engine_mod.run_turn(envelope, session_factory=session_factory)


class TestABusinessQuestionIsNotReadAsAClarifyAnswer:
    """B1's sibling: the clarify is open, and the customer asks something else that
    happens to carry a team. That is a QUESTION, not an answer to "which team", and
    retyping it `request_for_help` would escalate a turn the customer wanted answered."""

    def test_a_business_query_naming_a_team_is_answered_not_escalated(
        self, seeded, session_factory, monkeypatch, stub_assignment_seams
    ):
        _seed_open_team_clarify(session_factory)

        head = _run(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="business_query",
                intent_hint="check_stock",
                domain_hint="inventory",
                entities=[
                    {
                        "raw": "SRTWC287",
                        "hint": "product",
                        "canonical_code": None,
                        "current_message": True,
                        "confident": True,
                    }
                ],
                routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
                escalation={"is_escalation_confirmation": False, "company_pick": None},
            ),
            text_body="SRTWC287 got stock",
            msg_id="ZZT-clarify-bq",
        )
        assert head.branch_kind != "out_of_scope", (
            "a business question that names a team must be ANSWERED while a clarify is "
            f"open, never retyped into an escalation: {head.branch_kind!r}"
        )
        assert head.ctx["parse"]["output"]["message_type"] == "business_query", (
            f"the message type must not be rewritten: {head.ctx['parse']['output']['message_type']!r}"
        )
