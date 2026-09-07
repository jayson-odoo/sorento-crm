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
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output
from tests.chatbot.test_r3_pending_end_to_end import _session_of, _stub_parser
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
            "cid": CONTACT_ID,
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


class TestATeamClarifyAnswerIsConsumedAndResolvesTheEscalation:
    """AC-501/AC-505, D1. Turn 08e74db8 (cold ask) then 0d7d5a23 (the answer)."""

    def test_marketing_product_after_a_team_clarify_ask_assigns_to_marketing_product(
        self, seeded, session_factory, monkeypatch, stub_assignment_seams
    ):
        # -- turn 1: "escalate to marketing", no pending offer, prior team `purchasing` ---- #
        # `out_of_scope` completes IN-PROCESS (`engine.py:1875` -> `_run_escalation_arm`),
        # so `run_turn` alone already carries the composed clarify reply - no `complete_turn`
        # round trip needed for this lane.
        turn1_qf = _parser_output(
            message_type="request_for_help",
            intent_hint=None,
            domain_hint=None,
            entities=[],
            is_affirmative=True,
            user_goal="trying to escalate to marketing",
            # The parser's own word for this message under the amended contract (AC-821 /
            # owner rule R-a, landed with item 5 of this same lane): "marketing" is not one
            # of the eight catalogue teams, so the model returns the customer's word
            # verbatim rather than picking one of the three marketing teams for them. Null
            # here would now mean "named no team", which is a DIFFERENT turn (mt-r2) and is
            # assigned rather than asked about.
            routing={"suggested_team": "marketing", "suggested_agent": None},
            escalation={"is_escalation_confirmation": False, "company_pick": None},
        )
        _stub_parser(monkeypatch, turn1_qf)
        envelope1 = _envelope(is_test=False)
        # The seeded row's phone. The escalation lane's assignee / SLA seams read it off
        # the envelope, not off the row, and a live (non `is_test`) turn reaches them.
        envelope1.contact["phone"] = "+60000000009"
        envelope1.message["contact"]["phone"] = "+60000000009"
        envelope1.message["message"]["messageId"] = "ZZT-team-clarify-t1"
        envelope1.message["message"]["message"]["text"] = "escalate to marketing"

        head1 = engine_mod.run_turn(envelope1, session_factory=session_factory)
        assert head1.branch_kind == "out_of_scope", (head1.branch_kind, head1.error)

        reply1 = (head1.reply or {}).get("text") or ""
        assert "Which team should I pass this to" in reply1, reply1
        assert "marketing product" in reply1, reply1

        stored1 = _session_of(session_factory)["variables"]
        assert stored1.get("selection_context") == "team_clarify", stored1

        # -- turn 2: "marketing product" answers the ask -------------------------------- #
        # Production shape (0d7d5a23): the parser's OWN routing names `marketing_product`,
        # but emits `message_type: casual` for the bare noun phrase - exactly what a direct
        # answer to "which team" looks like with no verb in it.
        turn2_qf = _parser_output(
            message_type="casual",
            intent_hint=None,
            domain_hint=None,
            entities=[],
            is_affirmative=None,
            user_goal="trying to select marketing product",
            routing={"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"},
            escalation={"is_escalation_confirmation": False, "company_pick": None},
        )
        _stub_parser(monkeypatch, turn2_qf)
        # LIVE, like turn 1. A dry run is isolated from the session on purpose (AC-812),
        # so `is_test=True` here would leave `_session_of` reading turn 1's state back and
        # the "marker is cleared" assertion below could never be false.
        envelope2 = _envelope(is_test=False)
        envelope2.contact["phone"] = "+60000000009"
        envelope2.message["contact"]["phone"] = "+60000000009"
        envelope2.message["message"]["messageId"] = "ZZT-team-clarify-t2"
        envelope2.message["message"]["message"]["text"] = "marketing product"

        head2 = engine_mod.run_turn(envelope2, session_factory=session_factory)

        assert head2.ctx["parse"]["output"]["routing"]["suggested_team"] == "marketing_product", (
            "the carried previous routing ('purchasing') must not overwrite the parser's own "
            "team for THIS turn while a team_clarify is open: "
            f"{head2.ctx['parse']['output']['routing']!r}"
        )
        assert head2.branch_kind != "low_signal", (
            "a team_clarify answer must not fall through to the canned low_signal reply "
            f"('Hi! How can I help you today?'): branch_kind={head2.branch_kind!r}"
        )
        assert head2.branch_kind == "out_of_scope", (
            "a resolved team_clarify pick must re-enter the escalation lane: "
            f"branch_kind={head2.branch_kind!r}"
        )

        comments = [a for a in (head2.actions or []) if a.get("kind") == "add_comment"]
        assert any("Team: marketing_product" in (a.get("text") or "") for a in comments), (
            f"the resolved pick must assign to marketing_product, not the stale carried team: "
            f"{comments!r}"
        )
        sends = [a for a in (head2.actions or []) if a.get("kind") == "send_message"]
        assert sends and all((s.get("text") or "").strip() for s in sends), (
            f"the customer must get a non-empty reply once the pick resolves: {sends!r}"
        )
        stored2 = _session_of(session_factory)["variables"]
        assert stored2.get("selection_context") != "team_clarify", (
            f"the clarify marker must be cleared once the pick resolves: {stored2!r}"
        )


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
            "cid": CONTACT_ID,
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


class TestTheTeamClarifyHasABoundedLifetime:
    """B1. One turn, and now for real: `_offer_carry` must not re-arm the label."""

    def test_an_unanswered_clarify_is_gone_the_next_turn_even_with_a_stale_roster(
        self, seeded, session_factory, monkeypatch, stub_assignment_seams
    ):
        _seed_open_team_clarify(session_factory)

        # The mt-r2 shape: a request for help that answers nothing and names no team.
        head = _run(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="request_for_help",
                intent_hint=None,
                domain_hint=None,
                entities=[],
                is_affirmative=None,
                user_goal="trying to talk to a human",
                routing={"suggested_team": None, "suggested_agent": None},
                escalation={"is_escalation_confirmation": False, "company_pick": None},
            ),
            text_body="I want to talk to a human",
            msg_id="ZZT-clarify-ttl-1",
        )
        assert head.branch_kind == "out_of_scope", (head.branch_kind, head.error)

        stored = _session_of(session_factory)["variables"]
        assert stored.get("selection_context") != "team_clarify", (
            "an unanswered team clarify must not survive the turn after it, whatever "
            f"roster an earlier turn left behind: {stored.get('selection_context')!r}"
        )
        assert (stored.get("pending") or {}).get("kind") != "team_clarify", (
            "the marker must not be re-armed either - it outranks member_offer and "
            f"escalation_offer in `pending.derive` and would mask a real one: {stored.get('pending')!r}"
        )


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


class TestATapOnAPersistedQuickReplyResolvesTheClarify:
    """S1. The second source of `_team_clarify_pick` had no test at all: blanking
    `pending.options` reddened nothing. This is the TAP - the customer pressed a button
    whose text this codebase composed, and the parser came back with no team for it."""

    def test_a_reply_equal_to_a_persisted_option_label_assigns_that_team(
        self, seeded, session_factory, monkeypatch, stub_assignment_seams
    ):
        _seed_open_team_clarify(session_factory)

        head = _run(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="casual",
                intent_hint=None,
                domain_hint=None,
                entities=[],
                is_affirmative=None,
                user_goal="trying to answer which team",
                # The parser named NO team for the tap. Source 1 cannot help here, so
                # only the persisted quick-reply match can resolve it.
                routing={"suggested_team": None, "suggested_agent": None},
                escalation={"is_escalation_confirmation": False, "company_pick": None},
            ),
            # Our own label, as the button carried it, with the casing and padding a tap
            # can arrive with. Matched by strip + casefold EQUALITY, never a substring.
            text_body="  Marketing Form ",
            msg_id="ZZT-clarify-tap",
        )
        assert head.branch_kind == "out_of_scope", (head.branch_kind, head.error)
        comments = [a for a in (head.actions or []) if a.get("kind") == "add_comment"]
        assert any("Team: marketing_form" in (a.get("text") or "") for a in comments), (
            f"a tap on a quick reply WE persisted must resolve to that team: {comments!r}"
        )
        stored = _session_of(session_factory)["variables"]
        assert stored.get("selection_context") != "team_clarify", stored.get("selection_context")
