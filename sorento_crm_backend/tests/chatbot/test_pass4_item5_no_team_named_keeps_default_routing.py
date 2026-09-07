"""Owner console pass 4, item 5 (coordinator priority, 7 Sep 2026): a request naming NO
team at all gets asked to pick from all eight teams, when it should keep the default/derived
routing - a regression against #705 introduced by #706's H64/D1 clarify arm.

Production turns 1f0428cb-bd7b-41f3-a3e7-9af4531d9896 (run 1) and
9089ef88-c5b1-48fa-92cc-04805718e7aa (run 2), n8n execs 15501799 / 15502378, `turns-lane3`
round 12. Both: "I want to talk to a human" after an UNRELATED product-browse turn (the
customer had been asking about master_products, picked item 2, then asked for a human - no
domain, no team, no product in the current message). `_parser_raw` names no team
(`routing.suggested_team: null`) and is NOT an acceptance (`is_escalation_confirmation:
false`); the previous turn's carried routing is `purchasing` (H64's own inheritance premise),
and CRM answers "Which team should I pass this to - purchasing, purchasing certification,
customer service, marketing product, marketing form, warehouse, marketing promotion or it
admin?" instead of assigning to a team at all.

`escalation.py` ~:735-760 (`_person_routing`'s D1/H64 arm):

    if offer_is_open(prev):
        return clarify
    derived_team = (
        jsc.get(derive_routing(output), "suggested_team")
        if jsc.truthy(jsc.get(output, "domain_hint"))
        else None
    )
    prior_team = jsc.nullish_str(jsc.get(jsc.get(prev, "routing"), "suggested_team")).strip().lower()
    if derived_team is None and prior_team and prior_team != DEFAULT_SUGGESTED_TEAM:
        return clarify
    return None

H64's own docstring names its target case as "escalate to marketing" - a message that AT LEAST
names a team-ish word. The implemented condition does not check that: it fires whenever the
CURRENT turn names no domain (so `derived_team` is None) and the CARRIED team merely differs
from the hard default, with no read of whether the current message carries ANY team signal at
all. "I want to talk to a human" carries none, and a product-browse turn's carried
`purchasing` is not a stale ESCALATION team the customer is trying to correct - it is simply
whatever team the LAST unrelated business question routed to.

Measured (this file, unit test below): `test_a_fresh_ask_with_no_pending_offer_flows_through_
unguarded` (`test_s5_escalation_lane.py`) is green today but does NOT cover this shape - its
`prev_team` is `"customer_service"`, the hard default itself, so H64's `prior_team !=
DEFAULT_SUGGESTED_TEAM` never evaluates true there. This file's `prev_team="purchasing"` (a
real, non-default carried team from an unrelated turn) is the shape that regresses.

Expected: a request naming no team is ASSIGNED - `out_of_scope` -> human-intervention -
never the eight-team clarify. The clarify exists for a request that itself names an
AMBIGUOUS or DIFFERENT team (item 1b's `marketing`), not for one that names nothing at all.

WHICH team it is assigned to is the routing chain's own result, and the two shapes are
pinned separately below (review of #713, blocker B3, captain's ruling): the CARRIED team
when a previous turn had one - `Team: purchasing` on this dump's shape, because the chain
is `llm_team if req_help -> derived -> prior_routing -> DEFAULT` and a product browse
routes to purchasing by the owner's own table - and the hard default,
`Team: customer_service`, only on a truly cold session with nothing to inherit.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.lanes.escalation import run
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output
from tests.chatbot.test_r3_pending_end_to_end import _stub_parser
from tests.chatbot.test_s5_escalation_lane import _ctx, _item, _services


class TestARequestNamingNoTeamKeepsTheDefaultRoutingEvenOverAStaleCarriedTeam:
    """Lane-unit level (`escalation.run`), the fast and precise reproduction."""

    def test_i_want_to_talk_to_a_human_after_an_unrelated_browse_assigns_not_clarifies(self):
        prev = {
            "routing": {"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
            "domain_hint": "master_products",
        }
        ctx = _ctx(
            routing={"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
            parser_raw={"routing": {"suggested_team": None, "suggested_agent": None}},
            escalation={"is_escalation_confirmation": False, "company_pick": None},
            prev_variables=prev,
            text="I want to talk to a human",
        )
        item = _item(brand_code=None, company_id=None, company_name=None, routing_source="none")
        result = run(ctx, item, services=_services())
        assert result["arm"] == "human-intervention", (
            "a request naming NO team must keep the routing chain's own result - it must "
            "not clarify over the whole catalogue merely because an UNRELATED previous "
            f"turn carried a non-default team: arm={result['arm']!r}"
        )
        # CAPTAIN RULING (review of #713, B3): the team is the CARRIED one, not the table
        # default, and that is the CODE being kept rather than the docs. The chain is
        # `llm_team if req_help -> derived -> prior_routing -> DEFAULT`, which is the
        # pre-#706 behaviour and live parity: a product browse routes to purchasing by the
        # owner's own table, and "talk to a human" straight after it inherits that. The
        # owner's complaint was the eight-team MENU, never the team.
        comment = next(a for a in result["actions"] if a["kind"] == "add_comment")
        assert comment["text"].startswith("Team: purchasing\n"), comment["text"]


class TestARequestNamingNoTeamKeepsTheDefaultRoutingThroughTheEngine:
    """The production seam (LESSONS-LEARNT #102): the real head, the real routing chain,
    the real escalation lane, the parser stubbed at `_parser_raw` only."""

    @pytest.fixture()
    def seeded(self, session_factory):
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
                                    "raw": "SRTWC8505-P-RL",
                                    "hint": "product",
                                    "canonical_code": "SRTWC8505-P-RL",
                                    "current_message": True,
                                    "confident": True,
                                }
                            ],
                            "routing": {
                                "suggested_team": "purchasing",
                                "suggested_agent": "general_enquiries",
                            },
                            "escalation": {"is_escalation_confirmation": False},
                            "response": "Previous turn (master_products): returned 10 records",
                            "selection_context": None,
                            "pending": None,
                        }
                    }
                ),
            },
        )
        db.commit()
        set_chatbot_switches(session_factory)
        db.execute(
            text("UPDATE system_settings SET chatbot_completed_lanes = CAST(:l AS jsonb)"),
            {"l": '["out_of_scope"]'},
        )
        db.commit()
        return db

    def test_i_want_to_talk_to_a_human_assigns_through_the_real_engine(
        self, seeded, session_factory, monkeypatch
    ):
        qf = _parser_output(
            message_type="request_for_help",
            intent_hint=None,
            domain_hint=None,
            entities=[],
            is_affirmative=None,
            user_goal="trying to talk to a human",
            routing={"suggested_team": None, "suggested_agent": None},
            escalation={"is_escalation_confirmation": False, "company_pick": None},
        )
        _stub_parser(monkeypatch, qf)
        envelope = _envelope(is_test=True)
        envelope.contact["phone"] = "+60000000009"
        envelope.message["contact"]["phone"] = "+60000000009"
        envelope.message["message"]["messageId"] = "ZZT-mt-r2-human"
        envelope.message["message"]["message"]["text"] = "I want to talk to a human"

        head = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert head.branch_kind == "out_of_scope", (head.branch_kind, head.error)
        comments = [a for a in (head.actions or []) if a.get("kind") == "add_comment"]
        assert comments, (
            "a request naming no team must assign (an `add_comment` action carrying "
            f"'Team: ...'), not clarify: actions={head.actions!r}"
        )
        # B3, through the REAL routing chain: the carried `purchasing` is what this turn
        # assigns to, because the chain prefers a previous turn's routing over the hard
        # default. Pinned so the difference between "keeps the chain's result" and "keeps
        # the table default" can never again be documented one way and coded the other.
        assert any("Team: purchasing" in (a.get("text") or "") for a in comments), (
            f"the carried team is what the chain resolves to on this shape: {comments!r}"
        )
        sends = [a for a in (head.actions or []) if a.get("kind") == "send_message"]
        send_text = " ".join((s.get("text") or "") for s in sends)
        assert "Which team should I pass this to" not in send_text, (
            f"the eight-team clarify must not fire on a request that names no team: "
            f"{send_text!r}"
        )


class TestATrulyColdRequestGetsTheRoutingTablesOwnDefault:
    """The other half of the B3 pin (review of #713). With NOTHING carried - a cold
    session, no previous routing - the chain falls all the way to its hard default, and
    THAT is where `customer_service` comes from. Stating both shapes in tests is what
    stops "the routing table's default" and "the carried team" being confused again."""

    @pytest.fixture()
    def cold(self, session_factory):
        db = session_factory()
        db.execute(
            text(
                "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
                "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
            ),
            {"cid": CONTACT_ID, "phone": "+60000000009", "sv": json.dumps({"variables": {}})},
        )
        db.commit()
        set_chatbot_switches(session_factory)
        db.execute(
            text("UPDATE system_settings SET chatbot_completed_lanes = CAST(:l AS jsonb)"),
            {"l": '["out_of_scope"]'},
        )
        db.commit()
        return db

    def test_a_cold_request_for_a_human_is_assigned_to_customer_service(
        self, cold, session_factory, monkeypatch
    ):
        qf = _parser_output(
            message_type="request_for_help",
            intent_hint=None,
            domain_hint=None,
            entities=[],
            is_affirmative=None,
            user_goal="trying to talk to a human",
            routing={"suggested_team": None, "suggested_agent": None},
            escalation={"is_escalation_confirmation": False, "company_pick": None},
        )
        _stub_parser(monkeypatch, qf)
        envelope = _envelope(is_test=True)
        envelope.contact["phone"] = "+60000000009"
        envelope.message["contact"]["phone"] = "+60000000009"
        envelope.message["message"]["messageId"] = "ZZT-mt-r2-cold"
        envelope.message["message"]["message"]["text"] = "I want to talk to a human"

        head = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert head.branch_kind == "out_of_scope", (head.branch_kind, head.error)
        comments = [a for a in (head.actions or []) if a.get("kind") == "add_comment"]
        assert any("Team: customer_service" in (a.get("text") or "") for a in comments), (
            f"with nothing carried the chain's hard default is the answer: {comments!r}"
        )
