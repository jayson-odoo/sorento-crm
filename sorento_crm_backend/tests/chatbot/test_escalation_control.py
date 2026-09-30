"""ESCALATION-CONTROL (owner, 30 Sep 2026; PLAN-escalation-control-30sep.md).

"We need to be able to control each contact that they cannot access the escalation:
cannot force escalate, won't be offered escalation; this is for dealer."

A contact whose access type bars escalation ("Sorento Dealer" is seeded barred), or
whose own override does, is offered no hand-off on a miss, sees no routing picker, and
asking for a person or answering an old offer gets "Please refer to your salesman."
(owner ruling (b), the existing `turn/task.py::REFER_TO_SALESMAN`) with no hand-off.
Staff and unbarred contacts are unchanged; an "allow" override on a dealer restores offers.

Engine turns reuse `test_escalation_agent_carry.py`'s harness: the real engine, the
`/external/next-assignee` and SLA seams captured at their own boundary.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from app.services.chatbot import escalation_control
from app.services.chatbot.turn.pending import ask as pending_ask
from app.services.chatbot.turn.state import Profile, escalation_barred, offers_escalation
from app.services.chatbot.turn.task import REFER_TO_SALESMAN
from app.services.escalation_policy import resolve as resolve_policy

from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_escalation_agent_carry import (
    _capture_next_assignee,
    _capture_sla,
    _second_turn_envelope,
    _seed_contact,
    _seed_product,
    _stub_incoming_probe_empty,
    _write_open_question,
    _yes_verdict,
)

pytestmark = pytest.mark.usefixtures("_no_real_mcp_calls", "_stub_casual_llm")

DEALER_TYPE = "zzt_sorento_dealer"


def _contact_pk(session_factory) -> str:
    return session_factory().execute(
        text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": str(CONTACT_ID)}
    ).scalar()


def _make_dealer(session_factory, *, override: bool | None = None) -> str:
    """The contact holds a "Sorento Dealer" type that bars escalation (the seed's value),
    plus the contact's own override when one is given."""
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO contact_access_types (code, name, is_active, escalation_allowed) "
            "VALUES (:code, 'Sorento Dealer', true, false) ON CONFLICT (code) DO NOTHING"
        ),
        {"code": DEALER_TYPE},
    )
    pk = db.execute(
        text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": str(CONTACT_ID)}
    ).scalar()
    db.execute(
        text("INSERT INTO respond_contact_access_types (contact_id, access_type_code) VALUES (:c, :t)"),
        {"c": pk, "t": DEALER_TYPE},
    )
    db.execute(
        text("UPDATE respond_contacts SET escalation_allowed = :o WHERE id = :c"),
        {"o": override, "c": pk},
    )
    db.commit()
    return pk


def _reply(result: Any) -> str:
    """The reply text and every action the turn would send, as one string."""
    import json

    reply = result.reply if isinstance(result.reply, dict) else {}
    return " ".join([str(reply.get("text") or ""), json.dumps(result.actions or [], default=str)])


def _open_question(session_factory) -> Any:
    row = session_factory().execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
        {"c": str(CONTACT_ID)},
    ).first()
    return (row.session_vars or {}).get("open_question")


def _incoming_miss(session_factory, monkeypatch, stub_parser, stub_access):
    """A real incoming ETA miss (AC-1785's turn 1): for an unbarred contact the reply
    offers "Would you like me to escalate to purchasing team?" and arms a team_pick."""
    _seed_product(session_factory, code="ZZTSC07")
    _stub_incoming_probe_empty(monkeypatch)
    stub_parser(
        verdict(
            domain_hint="incoming",
            intent_hint="check_incoming",
            entities=[entity("ZZTSC07", hint="product", confident=True)],
            routing={"suggested_team": "purchasing", "suggested_agent": "incoming_stock_enquiries"},
        )
    )
    stub_access()
    return engine_mod.run_turn(_envelope(), session_factory=session_factory)


def _help_verdict() -> dict[str, Any]:
    return verdict(
        message_type="request_for_help",
        domain_hint=None,
        intent_hint=None,
        entities=[],
        user_goal="wants to talk to a human",
        routing={"suggested_team": "customer_service", "suggested_agent": "general_enquiries"},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )


# --------------------------------------------------------------------------- #
# Resolution (R1)
# --------------------------------------------------------------------------- #


class TestResolution:
    def test_a_contact_with_no_access_type_is_allowed(self, session_factory) -> None:
        _seed_contact(session_factory, phone="+60000009001")
        policy = resolve_policy(session_factory(), _contact_pk(session_factory))
        assert policy.allowed is True and policy.source == "default"

    def test_the_dealer_type_bars_and_names_itself(self, session_factory) -> None:
        _seed_contact(session_factory, phone="+60000009002")
        pk = _make_dealer(session_factory)
        policy = resolve_policy(session_factory(), pk)
        assert (policy.allowed, policy.source, policy.source_label) == (False, "access_type", "Sorento Dealer")

    def test_the_contact_override_wins_both_ways(self, session_factory) -> None:
        _seed_contact(session_factory, phone="+60000009003")
        pk = _make_dealer(session_factory, override=True)
        assert resolve_policy(session_factory(), pk).allowed is True
        db = session_factory()
        db.execute(text("UPDATE respond_contacts SET escalation_allowed = false WHERE id = :c"), {"c": pk})
        db.execute(text("DELETE FROM respond_contact_access_types WHERE contact_id = :c"), {"c": pk})
        db.commit()
        policy = resolve_policy(session_factory(), pk)
        assert (policy.allowed, policy.source) == (False, "contact")

    def test_the_profile_carries_it(self, session_factory) -> None:
        from app.services.chatbot.turn_runtime import load_profile

        _seed_contact(session_factory, phone="+60000009004")
        _make_dealer(session_factory)
        profile, _ = load_profile(session_factory(), str(CONTACT_ID))
        assert profile.escalation_allowed is False


#: Mr Loo (respond 487555417, owner hand test of #1406): office, dealer and end-user
#: types across three brands. (name, escalation_allowed, sort_order) as the seed leaves them.
MR_LOO_TYPES = [
    ("Sorento Office", True, 1),
    ("Sorento Dealer", False, 2),
    ("Mocha Dealer", False, 3),
    ("Mocha Office", True, 4),
    ("Cabana Office", True, 5),
    ("Cabana Dealer", False, 6),
    ("End User", True, 7),
]


def _give_types(session_factory, pk: str, types: list[tuple[str, bool, int]]) -> None:
    db = session_factory()
    for name, allowed, order in types:
        code = f"zzt_{name.lower().replace(' ', '_')}"
        db.execute(
            text(
                "INSERT INTO contact_access_types (code, name, is_active, escalation_allowed, sort_order) "
                "VALUES (:code, :name, true, :allowed, :order) ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "name": name, "allowed": allowed, "order": order},
        )
        db.execute(
            text("INSERT INTO respond_contact_access_types (contact_id, access_type_code) VALUES (:c, :t)"),
            {"c": pk, "t": code},
        )
    db.commit()


class TestMergeAcrossAccessTypes:
    """Owner hand test, 30 Sep 2026 ("why doesn't it allow to escalate to human?"): allowed
    when ANY of the contact's types allows, blocked only when EVERY type blocks."""

    def test_office_plus_dealer_is_allowed_via_the_office_type(self, session_factory) -> None:
        _seed_contact(session_factory, phone="+60000009011")
        pk = _contact_pk(session_factory)
        _give_types(session_factory, pk, MR_LOO_TYPES)
        policy = resolve_policy(session_factory(), pk)
        assert (policy.allowed, policy.source, policy.source_label) == (True, "access_type", "Sorento Office")

    def test_dealer_only_is_blocked(self, session_factory) -> None:
        _seed_contact(session_factory, phone="+60000009012")
        pk = _contact_pk(session_factory)
        _give_types(session_factory, pk, [("Sorento Dealer", False, 2), ("Mocha Dealer", False, 3)])
        policy = resolve_policy(session_factory(), pk)
        assert (policy.allowed, policy.source_label) == (False, "Sorento Dealer")

    def test_an_override_block_on_a_mixed_contact_blocks(self, session_factory) -> None:
        _seed_contact(session_factory, phone="+60000009013")
        pk = _contact_pk(session_factory)
        _give_types(session_factory, pk, MR_LOO_TYPES)
        db = session_factory()
        db.execute(text("UPDATE respond_contacts SET escalation_allowed = false WHERE id = :c"), {"c": pk})
        db.commit()
        policy = resolve_policy(session_factory(), pk)
        assert (policy.allowed, policy.source) == (False, "contact")

    def test_mr_loo_asking_for_a_person_is_handed_over(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000009014")
        _give_types(session_factory, _contact_pk(session_factory), MR_LOO_TYPES)
        bodies = _capture_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        stub_parser(_help_verdict())
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert result.branch_kind == "out_of_scope" and len(bodies) == 1, (result.branch_kind, bodies)
        assert REFER_TO_SALESMAN not in _reply(result)


# --------------------------------------------------------------------------- #
# The helper every offer site reads (R2)
# --------------------------------------------------------------------------- #


class TestOffersEscalation:
    def test_the_three_audiences(self) -> None:
        assert offers_escalation(Profile()) is True
        assert offers_escalation(None) is True
        assert offers_escalation(Profile(tier="office")) is False
        assert offers_escalation(Profile(escalation_allowed=False)) is False
        assert escalation_barred(Profile(tier="office")) is False

    def test_no_offer_site_reads_the_staff_check_alone(self) -> None:
        """Every bot-initiated offer gate reads `offers_escalation`, so a gate still calling
        `is_staff_profile` directly would offer a dealer. The one call left is
        `answer_bridge`'s staff-only roster trim, which the barred strip right after it
        (`without_escalation`) covers."""
        import ast

        root = Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot"
        calls: dict[str, int] = {}
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "is_staff_profile":
                    key = str(path.relative_to(root))
                    calls[key] = calls.get(key, 0) + 1
        assert calls == {"answer_bridge.py": 1, "turn/state.py": 1}, calls

#: Every "no offer for this audience" scenario the staff suite pins, one per offer builder
#: (`turn/compose.py`'s composer offer, `answer_bridge`'s cross-domain ladder rung, the
#: order miss, `not_found_error_message`'s outstanding and catalogue branches, the
#: withheld-offer pending, the did-you-mean roster). Replayed with the audience swapped
#: from staff to a BARRED DEALER: whichever builder fires, it must stay silent.
_STAFF_NO_OFFER_SCENARIOS = [
    "test_t10_staff_inventory_miss_gets_no_warehouse_escalation_offer",
    "test_t11_staff_stock_miss_composer_offer_absent",
    "test_staff_ladder_rung_gets_no_warehouse_escalation_offer",
    "test_staff_order_miss_gets_no_customer_service_offer",
    "test_staff_outstanding_report_empty_miss_gets_no_offer",
    "test_staff_catalog_could_not_find_miss_gets_no_offer",
    "test_withheld_offer_arms_no_hidden_escalation",
    "test_staff_did_you_mean_roster_stays_open_without_an_offer",
]


@pytest.mark.parametrize("scenario", _STAFF_NO_OFFER_SCENARIOS)
def test_every_offer_builder_is_silent_for_a_barred_dealer(scenario, request, monkeypatch) -> None:
    import inspect

    from tests.chatbot import test_samantha_26sep_s11_escalation_audience as staff_suite

    def barred_dealer(**kwargs: Any) -> Profile:
        return Profile(**{**kwargs, "tier": "dealer", "escalation_allowed": False})

    monkeypatch.setattr(staff_suite, "Profile", barred_dealer)
    fn = getattr(staff_suite, scenario)
    fn(**{name: request.getfixturevalue(name) for name in inspect.signature(fn).parameters})


# --------------------------------------------------------------------------- #
# The backstop (R2): whatever composed the reply, no offer survives
# --------------------------------------------------------------------------- #


class TestStripOffers:
    def test_the_offer_sentence_goes_and_the_salesman_line_stands(self) -> None:
        answer = SimpleAnswer("No stock found.\n\nWould you like me to escalate to purchasing team?")
        out = escalation_control.strip_offers(answer, Profile(escalation_allowed=False))
        assert out.text == f"No stock found.\n\n{REFER_TO_SALESMAN}"

    def test_a_routing_picker_goes_whole(self) -> None:
        text_ = (
            "Couldn't find ZZT.\n\nWould you like me to escalate to customer service team?\n\n"
            "Please choose who to route to (reply with the number):\n1. Alice\n2. Bob\n\n"
            "If you have no preference, just reply 'yes' and we'll assign automatically."
        )
        question = pending_ask(
            "member_offer",
            [
                {"position": 1, "label": "Alice", "entity_type": "member"},
                {"position": 2, "label": "Bob", "entity_type": "member"},
            ],
            team="customer_service",
        )
        out = escalation_control.strip_offers(SimpleAnswer(text_, question), Profile(escalation_allowed=False))
        assert out.question is None
        assert out.text == f"Couldn't find ZZT.\n\n{REFER_TO_SALESMAN}"

    def test_a_roster_keeps_its_products_and_loses_its_members(self) -> None:
        question = pending_ask(
            "product_pick",
            [
                {"position": 1, "label": "ZZT-A", "entity_type": "product", "uuid": str(uuid.uuid4())},
                {"position": 2, "label": "Alice", "entity_type": "member"},
            ],
            team="customer_service",
            payload={"escalate_offered": True},
        )
        out = escalation_control.strip_offers(SimpleAnswer("Did you mean:\n1. ZZT-A", question), Profile(escalation_allowed=False))
        assert [o["label"] for o in out.question.options] == ["ZZT-A"]
        assert "escalate_offered" not in out.question.payload and out.question.team is None

    def test_a_reply_with_no_offer_is_untouched(self) -> None:
        answer = SimpleAnswer("Here is the stock.")
        assert escalation_control.strip_offers(answer, Profile(escalation_allowed=False)) is answer


class SimpleAnswer:
    """The `turn/compose.Answer` fields `strip_offers` reads."""

    def __new__(cls, text_: str, question: Any = None):
        from app.services.chatbot.turn.compose import Answer

        return Answer(text=text_, question=question)


# --------------------------------------------------------------------------- #
# Engine turns (R3, R5)
# --------------------------------------------------------------------------- #


class TestDealerIsNeverOfferedAndCannotForce:
    def test_a_miss_offers_no_escalation_and_arms_nothing(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000009101")
        _make_dealer(session_factory)
        result = _incoming_miss(session_factory, monkeypatch, stub_parser, stub_access)
        reply = _reply(result)
        assert "escalate" not in reply.lower(), reply
        assert "route to" not in reply.lower(), reply
        oq = _open_question(session_factory)
        assert oq is None or oq.get("kind") not in {"team_pick", "member_offer", "company_pick"}, oq

    def test_asking_for_a_person_gets_the_salesman_line_and_no_hand_off(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000009102")
        _make_dealer(session_factory)
        bodies = _capture_next_assignee(monkeypatch)
        sla = _capture_sla(monkeypatch)
        stub_parser(_help_verdict())
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert bodies == [] and sla == [], (bodies, sla)
        assert REFER_TO_SALESMAN in _reply(result), _reply(result)
        assert "routed" not in _reply(result).lower()

    def test_a_stale_yes_to_an_old_offer_hands_nothing_over(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000009103")
        _make_dealer(session_factory)
        _write_open_question(
            session_factory,
            open_question={
                "kind": "team_pick",
                "expects": "yes_no",
                "team": "purchasing",
                "asked_at_turn": 1,
                "payload": {"agent": "incoming_stock_enquiries"},
                "options": [{"position": 1, "label": "Yes", "entity_type": "team", "payload": {"team": "purchasing"}}],
            },
        )
        bodies = _capture_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        stub_parser(_yes_verdict())
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert bodies == [], bodies
        assert REFER_TO_SALESMAN in _reply(result), _reply(result)


class TestUnbarredContactsAreUnchanged:
    def test_a_plain_contact_is_still_offered_and_handed_over(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000009201")
        bodies = _capture_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        _incoming_miss(session_factory, monkeypatch, stub_parser, stub_access)
        assert (_open_question(session_factory) or {}).get("kind") == "team_pick"
        stub_parser(_yes_verdict())
        result = engine_mod.run_turn(_second_turn_envelope(), session_factory=session_factory)
        assert result.branch_kind == "out_of_scope" and len(bodies) == 1, (result.branch_kind, bodies)

    def test_a_staff_profile_still_asks_for_a_person_and_is_handed_over(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000009202")
        db = session_factory()
        db.execute(
            text("UPDATE respond_contacts SET chatbot_profile = CAST(:p AS jsonb) WHERE respond_io_id = :c"),
            {"p": '{"tier": "office"}', "c": str(CONTACT_ID)},
        )
        db.commit()
        bodies = _capture_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        stub_parser(_help_verdict())
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert result.branch_kind == "out_of_scope" and len(bodies) == 1, (result.branch_kind, bodies)

    def test_an_allow_override_on_a_dealer_restores_the_offer(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000009203")
        _make_dealer(session_factory, override=True)
        result = _incoming_miss(session_factory, monkeypatch, stub_parser, stub_access)
        assert "escalate" in _reply(result).lower(), _reply(result)
        assert (_open_question(session_factory) or {}).get("kind") == "team_pick"
