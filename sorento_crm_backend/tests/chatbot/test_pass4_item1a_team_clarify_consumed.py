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
        self, seeded, session_factory, monkeypatch
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
            routing={"suggested_team": None, "suggested_agent": None},
            escalation={"is_escalation_confirmation": False, "company_pick": None},
        )
        _stub_parser(monkeypatch, turn1_qf)
        envelope1 = _envelope(is_test=False)
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
        envelope2 = _envelope(is_test=True)
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
