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
    def fake_resolve_config(db, *, current_date, override_version_id=None):
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


class TestAnAbandonedMemberOfferStopsConfirming:
    """AC-816 rule 1's TTL half, end to end: the owner's own sequence.

    A member offer went out, the customer ignored it and asked three stock questions
    instead, and then typed "yes" - about the stock, not the offer. Before the TTL the
    tail re-armed `selection_context` on every one of those turns, so `_offer_is_open` was
    still true four turns later and the head read that "yes" as an escalation
    confirmation: a human was assigned to a conversation nobody had asked to escalate.

    Turn 1 is SEEDED as the persisted offer rather than composed, because building one
    through `complete_turn` needs the CS gate, a roster plan and real team rows - none of
    which this sequence is about. The shape seeded is exactly the shape the tail writes,
    pinned by `test_tail_units.py::TestTheMemberOfferHasTheSameTtlAsTheDymOffer`.
    """

    ROSTER = [{"idx": i, "label": f"Member {i}", "uuid": f"u{i}"} for i in range(1, 4)]

    def _seed_offer(self, session_factory) -> None:
        db = session_factory()
        db.execute(
            text(
                "UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) "
                "WHERE respond_io_id = :cid"
            ),
            {
                "cid": CONTACT_ID,
                "sv": json.dumps(
                    {
                        "variables": {
                            "message_type": "business_query",
                            "domain_hint": "order",
                            "selection_context": "member_offer",
                            "last_result_set": self.ROSTER,
                            "pending": {
                                "kind": "member_offer",
                                "team": "customer_service",
                                "domain": "order",
                                "ttl": 3,
                            },
                        }
                    }
                ),
            },
        )
        db.commit()

    def _answer_turn(self, session_factory, monkeypatch, *, n: int) -> None:
        qf = _parser_output(
            message_type="business_query",
            intent_hint="check_order",
            # The OFFER'S OWN domain, deliberately. A different domain already clears the
            # carry through `topic.changed` (rule 1's second lifetime), so a sequence that
            # switched domains would pass without the TTL and prove nothing about it.
            domain_hint="order",
            routing={
                "suggested_team": "customer_service",
                "suggested_agent": "order_enquiries",
                "team_source": "parser",
            },
        )
        _stub_parser(monkeypatch, qf)
        envelope = _envelope(is_test=False)
        envelope.message["message"]["messageId"] = f"ZZT-r3-member-ttl-{n}"
        envelope.message["message"]["message"]["text"] = "any update on my orders"
        head = engine_mod.run_turn(envelope, session_factory=session_factory)
        engine_mod.complete_turn(
            head.turn_id,
            _fragments(
                item={
                    "allowed": True,
                    "response": "Here are your orders.",
                    "items": [{"title": "SO-10021", "fields": []}],
                }
            ),
            session_factory=session_factory,
        )

    def test_three_stock_answers_later_a_bare_yes_escalates_nobody(
        self, seeded, session_factory, monkeypatch
    ):
        self._seed_offer(session_factory)
        for n in (2, 3, 4):
            self._answer_turn(session_factory, monkeypatch, n=n)

        stored = _session_of(session_factory)["variables"]
        assert stored.get("selection_context") != "member_offer", (
            f"the offer outlived three answered turns: {stored!r}"
        )
        assert (stored.get("pending") or {}).get("kind") != "member_offer", (
            f"the pending marker still says an escalation is open: {stored!r}"
        )

        yes_qf = _parser_output(
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
        _stub_parser(monkeypatch, yes_qf)
        envelope = _envelope(is_test=False)
        envelope.message["message"]["messageId"] = "ZZT-r3-member-ttl-yes"
        envelope.message["message"]["message"]["text"] = "yes"
        head = engine_mod.run_turn(envelope, session_factory=session_factory)

        escalation = head.ctx["parse"]["output"].get("escalation") or {}
        assert escalation.get("is_escalation_confirmation") is not True, (
            "a 'yes' four turns after an ignored offer must not confirm it: "
            f"{escalation!r}"
        )
        actions = [a for a in (head.actions or []) if a.get("kind") == "assign_conversation"]
        assert not actions, f"the turn assigned a human off an abandoned offer: {actions!r}"


class TestAPendingOrderRosterDoesNotSwallowABareProductCode:
    """AC-816 rule 3 on the ORDER domain with a member roster (prod exec 15443838).

    The owner's chain, cold: "delivery to hanlim, product srtwc286" (no orders, escalation
    offer plus a six-name roster, `pending.kind = member_offer`, domain `order`), then
    "last month" - which PASSES, because a date window is a filter in any domain - then
    "rpacc", which came back `offer_hold` with ZERO entities and re-showed the same roster.

    The cause is upstream of rule 3 and is why the inventory version of this turn passes:
    a bare token with no verb is emitted `casual`, the casual arm wipes `entities` and the
    domain-continuity block skips casual outright, so by the time the member ladder asks
    "is this a filter?" there is nothing left to be one. Rule 3's own premise says what a
    bare entity under an open offer IS - a narrowing of the question the offer was made
    about - so the label is decided by STATE (an offer is open, an entity was named), not
    by whether the model heard a verb (D11).

    Turn 1 is SEEDED as the persisted offer, for the same reason as the TTL sequence above:
    composing a real six-name roster needs the CS gate and real team rows, and none of
    that is what this chain is about. Turns 2 and 3 are real `run_turn` calls against the
    REAL resolver on real seeded rows - which is the half that matters, because the whole
    question is what the resolver is asked and what it comes back with.
    """

    ROSTER = [{"idx": i, "label": f"Member {i}", "uuid": f"u{i}"} for i in range(1, 7)]

    def _seed_master(self, session_factory) -> str:
        from app.models.company import Company
        from app.models.order import Customer
        from app.models.product import Product, ProductCategory, UnitOfMeasure
        from tests._pg_fixture import unique_code

        db = session_factory()
        company = Company(name=unique_code("HAN"), code=unique_code("HAN")[:50])
        db.add(company)
        db.flush()
        db.add(
            Customer(
                customer_code="300-H030",
                customer_name="HANLIM TRADING SDN BHD",
                is_active=True,
                company_id=company.id,
            )
        )
        category = ProductCategory(
            category_code=unique_code("CAT")[:50],
            category_name="ZZT rule 3 category",
            company_id=company.id,
        )
        uom = UnitOfMeasure(uom_code=unique_code("UOM")[:20], uom_name="Each", company_id=company.id)
        db.add_all([category, uom])
        db.flush()
        for code in ("SRTWC286", "RPACC"):
            db.add(
                Product(
                    product_code=code,
                    product_name=f"ZZT {code}",
                    category_id=category.id,
                    base_uom_id=uom.id,
                    list_price=10,
                    is_active=True,
                    company_id=company.id,
                )
            )
        db.commit()
        return str(company.id)

    def _seed_offer(self, session_factory) -> None:
        db = session_factory()
        db.execute(
            text(
                "UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) "
                "WHERE respond_io_id = :cid"
            ),
            {
                "cid": CONTACT_ID,
                "sv": json.dumps(
                    {
                        "variables": {
                            "message_type": "business_query",
                            "domain_hint": "order",
                            "intent_hint": "check_order",
                            "selection_context": "member_offer",
                            "last_result_set": self.ROSTER,
                            "entities": [
                                {
                                    "raw": "hanlim",
                                    "hint": "customer",
                                    "canonical_code": "300-H030",
                                    "current_message": False,
                                    "confident": True,
                                }
                            ],
                            "response": (
                                "Would you like me to escalate to customer service team?"
                            ),
                            "pending": {
                                "kind": "member_offer",
                                "team": "customer_service",
                                "domain": "order",
                                "ttl": 3,
                            },
                        }
                    }
                ),
            },
        )
        db.commit()

    def _wire(self, session_factory, monkeypatch, company_id: str) -> None:
        """The REAL resolver seam, scoped to the seeded company the way the engine scopes
        every session it opens (`engine._scoped_factory`, H56).

        The business lane is switched ON so the turn reaches `resolve-entity` at all - off
        it, the head delegates at `routed` and nothing resolves. The FETCH is stubbed to a
        canned success (the same stand-in `test_engine_company_scope` uses): what this
        chain grades is what the resolver was asked and what came back, not the RAG tool
        pick, which needs an embedding provider.
        """
        from tests.chatbot.conftest import set_chatbot_switches
        from tests.chatbot.test_engine_company_scope import (
            _wire_answer_services,
            _wire_answered_fetch,
            _wire_real_resolve_entity,
        )

        set_chatbot_switches(session_factory, business_lane=True)
        db = session_factory()
        db.execute(text("UPDATE system_settings SET chatbot_completed_lanes = CAST(:l AS jsonb)"), {"l": '["business_query"]'})
        db.commit()
        _wire_real_resolve_entity(monkeypatch)
        _wire_answer_services(monkeypatch)
        _wire_answered_fetch(monkeypatch)
        monkeypatch.setattr(
            engine_mod, "_contact_company_scope", lambda factory, cid: frozenset({company_id})
        )

    def _run(self, session_factory, monkeypatch, *, qf, text_body, msg_id):
        _stub_parser(monkeypatch, qf)
        envelope = _envelope(is_test=False)
        envelope.message["message"]["messageId"] = msg_id
        envelope.message["message"]["message"]["text"] = text_body
        return engine_mod.run_turn(envelope, session_factory=session_factory)

    def test_a_bare_product_code_narrows_the_order_query_instead_of_reprompting(
        self, seeded, session_factory, monkeypatch
    ):
        company_id = self._seed_master(session_factory)
        self._seed_offer(session_factory)
        self._wire(session_factory, monkeypatch, company_id)

        # -- turn 2: "last month". A date window is a filter in ANY domain, and this half
        #    already worked - it is here so turn 3 arrives in the state it really does.
        self._run(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="business_query",
                intent_hint=None,
                domain_hint=None,
                entities=[],
                date_mode="range",
                date_filter_start="2026-08-01",
                date_filter_end="2026-08-31",
            ),
            text_body="last month",
            msg_id="ZZT-rule3-order-t2",
        )

        # -- turn 3: "rpacc". A bare token with no verb: the model calls it casual and
        #    names one entity, and the shape guess for a code under an order thread is
        #    the model's, not the state's.
        head = self._run(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="casual",
                intent_hint=None,
                domain_hint=None,
                entities=[
                    {
                        "raw": "rpacc",
                        "hint": "product",
                        "canonical_code": None,
                        "current_message": True,
                        "confident": True,
                    }
                ],
            ),
            text_body="rpacc",
            msg_id="ZZT-rule3-order-t3",
        )

        qf3 = head.ctx["parse"]["output"]
        assert qf3["message_type"] == "business_query", (
            f"a bare code under an open roster is a narrowing, not small talk: {qf3!r}"
        )
        assert qf3["domain_hint"] == "order", (
            f"the carried domain must survive the turn: {qf3.get('domain_hint')!r}"
        )
        raws = {str(e.get("raw")).lower() for e in (qf3.get("entities") or [])}
        assert {"rpacc", "hanlim"} <= raws, (
            f"the new filter and the carried customer must both be in scope: {raws!r}"
        )
        assert (qf3.get("escalation") or {}).get("member_reprompt") is None, (
            f"the roster must not be re-offered as if the code were a bad pick: {qf3!r}"
        )
        assert qf3.get("correction") is not True
        assert qf3.get("member_offer_filter_modification") is True, (
            "rule 3's filter arm is what keeps the offer pending while the question "
            f"narrows: {qf3!r}"
        )

        from tests.chatbot.test_engine_company_scope import _looked_up_resolved, _turn_row

        resolved = _looked_up_resolved(_turn_row(session_factory, head.turn_id))
        product_codes = {
            m.get("canonical_code")
            for res in (resolved.get("resolutions") or [])
            for m in (res.get("matches") or [])
            if m.get("entity_type") == "product"
        }
        assert "RPACC" in product_codes, (
            "the resolver must still reach the product through `fallback_to_all_types`, "
            f"whatever type rule 4 stamped on the bare token: {resolved!r}"
        )


class TestAnOutOfRangePickKeepsTheProductInScope:
    """"promotion 7445" -> a three-tier picker -> "9" -> "all" (prod execs 15445325 /
    15445363).

    The re-prompt was right and the tier list survived, but the session it wrote had no
    product and no domain in it, so the valid "all" that followed answered "I need at
    least one filter" instead of every tier's promotions for 7445. Graded here as the real
    chain, because the defect is entirely in what ONE turn persisted and what the NEXT one
    read back off the database.

    Turn 1 is seeded as the persisted tier offer, for the same reason as the two chains
    above: composing a real tier picker needs the entitlement read and the tier probe, and
    what this chain is about is the two turns after it.
    """

    TIERS = [
        {"idx": 1, "label": "Dealer", "value": "Dealer"},
        {"idx": 2, "label": "End User", "value": "End User"},
        {"idx": 3, "label": "Contractor", "value": "Contractor"},
    ]

    def _seed_offer(self, session_factory) -> None:
        db = session_factory()
        db.execute(
            text(
                "UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) "
                "WHERE respond_io_id = :cid"
            ),
            {
                "cid": CONTACT_ID,
                "sv": json.dumps(
                    {
                        "variables": {
                            "message_type": "business_query",
                            "domain_hint": "promotion",
                            "intent_hint": "check_promotion",
                            "selection_context": "tier_offer",
                            "last_result_set": self.TIERS,
                            "entities": [
                                {
                                    "raw": "7445",
                                    "hint": "product",
                                    "canonical_code": "SRTWC7445",
                                    "current_message": False,
                                    "confident": True,
                                }
                            ],
                            "response": "Which access level?",
                        }
                    }
                ),
            },
        )
        db.commit()

    def _run(self, session_factory, monkeypatch, *, qf, text_body, msg_id):
        _stub_parser(monkeypatch, qf)
        envelope = _envelope(is_test=False)
        envelope.message["message"]["messageId"] = msg_id
        envelope.message["message"]["message"]["text"] = text_body
        return engine_mod.run_turn(envelope, session_factory=session_factory)

    def test_the_next_reply_still_knows_which_product_it_is_all_of(
        self, seeded, session_factory, monkeypatch
    ):
        self._seed_offer(session_factory)

        # -- turn 2: "9". Out of range against a three-row list, and the model emits it
        #    `casual` with no positions and no entities of its own. `complete_turn` is
        #    called explicitly because the TAIL is what persists the session, and this
        #    chain is entirely about what that turn wrote down.
        head2 = self._run(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="casual", intent_hint=None, domain_hint=None, entities=[]
            ),
            text_body="9",
            msg_id="ZZT-tier-oor-9",
        )
        engine_mod.complete_turn(
            head2.turn_id,
            _fragments(item={"allowed": True, "response": "Please choose 1, 2 or 3."}),
            session_factory=session_factory,
        )

        stored = _session_of(session_factory)["variables"]
        assert stored.get("selection_context") == "tier_offer", (
            f"the tier list must survive the bad digit: {stored!r}"
        )
        assert [str(e.get("raw")) for e in (stored.get("entities") or [])] == ["7445"], (
            f"the re-prompt turn persisted no product to be 'all' OF: {stored!r}"
        )
        assert stored.get("domain_hint") == "promotion", stored

        # -- turn 3: "all". Valid, and it must reach the promotion lane with 7445 in scope.
        head = self._run(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="business_query",
                intent_hint=None,
                domain_hint=None,
                entities=[],
                access_levels=["Dealer", "End User", "Contractor"],
            ),
            text_body="all",
            msg_id="ZZT-tier-oor-all",
        )
        qf3 = head.ctx["parse"]["output"]
        assert qf3.get("domain_hint") == "promotion", (
            f"the 'all' turn lost the offer's domain: {qf3!r}"
        )
        assert "7445" in {str(e.get("raw")) for e in (qf3.get("entities") or [])}, (
            f"the 'all' turn has nothing to be all OF: {qf3.get('entities')!r}"
        )
