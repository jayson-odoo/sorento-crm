"""R3, end to end: the tail WRITES `pending`, a later turn's head READS it (AC-201, D2).

`test_r3_dual_read.py` proves the head's reader (`output_exchange._offer_is_open`)
accepts the marker shape in isolation - a hand-built `previous_conversation_state` dict,
never anything the CRM itself persisted. `test_tail_units.py::TestPendingMarker` proves
the tail WRITES that shape - a hand-built `ctx`, never a real session round trip. Neither
proves the two halves actually agree once a real turn writes what a real later turn
reads off `respond_contacts.session_vars` - that is what only `run_turn -> complete_turn
-> run_turn` on the SAME contact, against the real (blank-schema) database, can show.

Turn 1: the tail composes an escalation offer (`branch_kind = "escalate_offer"`) and
`complete_turn` persists `pending = {kind: escalation_offer, team, domain}`.
Turn 2: the customer's raw parser output carries `is_affirmative = True` and NOTHING
about escalation being confirmed - `is_escalation_confirmation` starts False, exactly as
a real LLM emission would for a bare "yes". The head's own `post_process` step, reading
the persisted `pending` off turn 1's real database row, is what has to flip it, with no
hand-built previous-state and no direct assignment by this test.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import Envelope
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_complete_turn import _fragments
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output


@pytest.fixture()
def seeded(session_factory):
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": CONTACT_ID, "phone": "+60000000009", "sv": json.dumps({"variables": {}})},
    )
    db.commit()
    return db


def _stub_parser(monkeypatch, output: dict[str, Any]) -> None:
    def fake_resolve_config(db, *, current_date):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
        )

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: output)
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, **kw: {"allowed": True, "decision": "allow", "agent_name": "General"},
    )
    monkeypatch.setattr(engine_mod, "default_space_id", lambda db: None)


def _session_of(session_factory) -> dict:
    db = session_factory()
    row = db.execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :cid"),
        {"cid": CONTACT_ID},
    ).first()
    raw = row.session_vars if row is not None else {}
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


class TestPendingSurvivesARealTurnBoundary:
    def test_an_escalation_offer_written_by_turn_1_confirms_itself_on_turn_2(
        self, seeded, session_factory, monkeypatch
    ):
        # -- turn 1: the tail composes the offer and persists `pending` -------------- #
        turn1_qf = _parser_output(
            message_type="business_query",
            intent_hint="check_order",
            domain_hint="order",
            routing={
                "suggested_team": "customer_service",
                "suggested_agent": "order_enquiries",
                "team_source": "parser",
            },
        )
        _stub_parser(monkeypatch, turn1_qf)
        envelope1 = _envelope(is_test=False)
        envelope1.message["message"]["messageId"] = "ZZT-r3-e2e-turn-1"
        head1 = engine_mod.run_turn(envelope1, session_factory=session_factory)
        assert head1.status == "delegated", head1.error

        done1 = engine_mod.complete_turn(
            head1.turn_id,
            _fragments(item={"branch_kind": "escalate_offer", "allowed": True}),
            session_factory=session_factory,
        )
        assert "Would you like me to escalate to customer service team?" in done1.reply["text"]

        stored = _session_of(session_factory)
        assert stored["variables"]["pending"] == {
            "kind": "escalation_offer",
            "team": "customer_service",
            "domain": "order",
        }

        # -- turn 2: a bare "yes" - the PARSER never says the offer was confirmed ---- #
        turn2_qf = _parser_output(
            message_type="casual",
            intent_hint=None,
            domain_hint=None,
            entities=[],
            is_affirmative=True,
            escalation={"is_escalation_confirmation": False, "company_pick": None},
            routing={
                "suggested_team": "customer_service",
                "suggested_agent": "order_enquiries",
                "team_source": "parser",
            },
        )
        # The confirmed-pick predicate route.decide reads alongside the marker
        # (`is_cs_order_enquiry_pick`); this is what the escalate-offer LANE stamps once
        # a member picker is live, reproduced directly here because this test's job is
        # the dual read, not the picker lane itself.
        turn2_qf["suggest_pick_context"] = True
        _stub_parser(monkeypatch, turn2_qf)
        envelope2 = _envelope(is_test=False)
        envelope2.message["message"]["messageId"] = "ZZT-r3-e2e-turn-2"
        envelope2.message["message"]["message"]["text"] = "yes"

        head2 = engine_mod.run_turn(envelope2, session_factory=session_factory)

        assert head2.ctx["parse"]["output"]["escalation"]["is_escalation_confirmation"] is True, (
            "the head's dual read must have confirmed the escalation from `pending` alone, "
            "with no legacy string anywhere in this turn's history"
        )
        assert head2.item["branch_kind"] == "escalate_offer", (
            f"routing landed on {head2.item.get('branch_kind')!r}, not escalate_offer"
        )


class TestPendingPresenceMirrorsWhatWasComposed:
    """R3 task 7's other half: `pending` is present after an offer, absent otherwise -
    exercised through the REAL tail pipeline (`complete_turn`), not just `compile_state`
    in isolation (which `test_tail_units.py::TestPendingMarker` already covers)."""

    def _run(self, session_factory, monkeypatch, *, item: dict[str, Any]) -> dict:
        # `domain_hint = "order"` on purpose: `output_exchange`'s own routing derivation
        # recomputes `routing` off `domain_hint`/`intent_hint` regardless of what the
        # stub hands it, and "order" is the one domain that lands on customer_service /
        # order_enquiries - the pair `escalate_offer`'s canned copy and `pending.team`
        # both key on.
        qf = _parser_output(
            intent_hint="check_order",
            domain_hint="order",
            routing={
                "suggested_team": "customer_service",
                "suggested_agent": "order_enquiries",
                "team_source": "parser",
            },
        )
        _stub_parser(monkeypatch, qf)
        envelope = _envelope(is_test=False)
        envelope.message["message"]["messageId"] = f"ZZT-r3-e2e-{item['branch_kind']}"
        head = engine_mod.run_turn(envelope, session_factory=session_factory)
        done = engine_mod.complete_turn(
            head.turn_id, _fragments(item=item), session_factory=session_factory
        )
        return done.session_patch if done.session_patch is not None else _session_of(session_factory)

    def test_pending_is_present_after_an_escalation_offer(self, seeded, session_factory, monkeypatch):
        patch = self._run(
            session_factory, monkeypatch, item={"branch_kind": "escalate_offer", "allowed": True}
        )
        assert patch["variables"]["pending"] == {
            "kind": "escalation_offer",
            "team": "customer_service",
            "domain": "order",
        }

    def test_pending_is_absent_after_a_plain_answer(self, seeded, session_factory, monkeypatch):
        patch = self._run(
            session_factory, monkeypatch, item={"branch_kind": "not_supported", "allowed": True}
        )
        assert patch["variables"]["pending"] is None
