"""#865 fix round 5: escalation words win over product words (owner hand test of round 4,
28 Sep 00:05 to 00:07 MYT, console :3082).

The owner's messages, in his order, on one console conversation:

    check spec srtwc286                                              spec answer (right)
    please esclate to marketing team                                 marketing_product (right)
    ok                                                               low_signal (right)
    pelase escalate to marketing team MWc-SC8609-)PP water closet    the SRTWC286 spec answer again
    pelase escalate to marketing team MWc-SC8609-PP water closet     "Which one do you mean? 1. water
                                                                     closet (promotion) 2. water closet
                                                                     (attachment_type)"
    1                                                                a product miss offering "escalate
                                                                     to customer service team?"

The merged rules this is reconciled with:

* The parser prompt's MESSAGE TYPE rule 1: a message that asks for a specific team or to
  ESCALATE is `request_for_help`, and "it takes priority over business_query,
  clarification, and casual ... even if they also mention a product or order". The
  fourth message broke it (the parser read a product query); `user_goal` kept the words.
* #706 (H69): an explicit team beats a pending offer.
* #1142 (R6 to R9): the team follows the question's domain; the flat `customer_service`
  literal is only the last rung, never the answer when a team is known.
* #952 hand pass 10 (contract 111, the #866 port): an escalation naming an unrecognised
  product code asks the product did-you-mean before anything else.

The fix: an escalate word plus a named team (read off the parser's `user_goal`, as round
4's `_named_teams` already does) is a help request whatever product code, typo or class
word follows; such a turn plans no fetch and asks no narrowing or kind question; its
product words are the escalation's focus; and a typo is resolved INSIDE the escalation by
the resolver's own trigram did-you-mean, one question, answered by a number, after which
the escalation goes out with the picked product's brand and team.

Every test drives the real engine through `console_service.run_console_turn` (dry run,
one contact, `session_vars` carried turn to turn) with the parser stubbed.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_escalation_agent_carry import (
    _capture_real_next_assignee,
    _capture_sla,
    _seed_contact,
)
from tests.chatbot.test_escalation_brand_from_focus import (
    MOCHA_COMPANY_ID,
    _escalation_verdict,
    _looked_up_routing,
    _product_verdict,
    _seed_borrowable_envelope,
    _seed_marketing_product_team,
    _seed_mocha_company_item,
    _seed_owners_catalogue,
    _stub_any_product_tool,
)
from tests.chatbot.test_rearch_s3_attribute_first import _link_contact_company

pytestmark = pytest.mark.usefixtures("_no_real_mcp_calls", "_stub_casual_llm")

ROUTED_TO_MARKETING = (
    "This inquiry has been routed to the respective person-in-charge (PIC) from "
    "marketing product team. We will get back to you soon. Thanks for your patience."
)
DID_YOU_MEAN = (
    'Couldn\'t find "MWc-SC8609-)PP". Did you mean:\n'
    "1. MWC-SC8609-PP\n"
    "2. MWC-SC8606-PP\n"
    "3. MWC-SC86-PP\n"
    "Reply with the number and I will pass it to the marketing product team."
)


def _typo_verdict() -> dict[str, Any]:
    """Message 4 as the parser misread it: a master_products business query, the typo'd
    code unsure, the class word beside it, the domain's team (purchasing). `user_goal`,
    the parser's own reading of the message, still says what the customer asked."""
    return verdict(
        message_type="business_query",
        domain_hint="master_products",
        intent_hint="check_product",
        user_goal="trying to escalate MWc-SC8609-)PP water closet to the marketing team",
        entities=[
            entity("MWc-SC8609-)PP", hint="product", confident=False),
            entity("water closet", hint="product_type"),
        ],
        routing={"suggested_team": "purchasing", "suggested_agent": "purchasing"},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )


def _fixed_code_verdict() -> dict[str, Any]:
    """Message 5: a help request naming the code and the class word, no domain of its
    own - the shape `_help_request_is_an_ask` used to turn into a product ask."""
    return verdict(
        message_type="request_for_help",
        domain_hint=None,
        intent_hint=None,
        user_goal="trying to escalate MWc-SC8609-PP water closet to the marketing team",
        entities=[
            entity("MWc-SC8609-PP", hint="product", confident=True),
            entity("water closet", hint="product_type"),
        ],
        routing={"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )


def _position(position: int) -> dict[str, Any]:
    return verdict(
        message_type="casual",
        reference_positions=[position],
        routing={"suggested_team": None, "suggested_agent": None},
    )


OWNERS_28SEP_ROUND5: list[tuple[str, dict[str, Any]]] = [
    ("check spec srtwc286", _product_verdict("master_products", "check_product", "srtwc286")),
    (
        "please esclate to marketing team",
        _escalation_verdict(user_goal="trying to escalate to the marketing team", team="marketing_product"),
    ),
    ("ok", verdict(message_type="casual", is_affirmative=True)),
    ("pelase escalate to marketing team MWc-SC8609-)PP water closet", _typo_verdict()),
    ("pelase escalate to marketing team MWc-SC8609-PP water closet", _fixed_code_verdict()),
    ("1", _position(1)),
]


def _seed_round5_catalogue(session_factory) -> None:
    """Round 4's catalogue plus the two Mocha siblings the owner's did-you-mean named, and
    the contact linked to the Mocha company too: his did-you-mean offered Mocha codes, so
    his contact sees them."""
    _seed_owners_catalogue(session_factory)
    _seed_mocha_company_item(session_factory, code="MWC-SC8606-PP")
    _seed_mocha_company_item(session_factory, code="MWC-SC86-PP")


def _two_kinds_for_water_closet(monkeypatch) -> None:
    """The owner's fifth message asked "Which one do you mean? water closet (promotion) /
    water closet (attachment_type)": the resolver placed the class word in two kinds.
    Reproduced at the resolver seam, so whatever reaches `apply()` sees that same map."""
    import dataclasses

    from app.services.chatbot import turn_runtime

    real = turn_runtime.resolve_kinds

    def resolve_kinds(*args: Any, **kwargs: Any):
        outcome = real(*args, **kwargs)
        entities = (((kwargs.get("ctx") or {}).get("parse") or {}).get("output") or {}).get("entities") or []
        if not any(isinstance(e, dict) and e.get("raw") == "water closet" for e in entities):
            return outcome
        kinds = dict(outcome.resolved_kinds or {})
        kinds["water closet"] = {"promotion": 1, "attachment_type": 1}
        return dataclasses.replace(outcome, resolved_kinds=kinds)

    monkeypatch.setattr(turn_runtime, "resolve_kinds", resolve_kinds)


def _replay(session_factory, monkeypatch, stub_parser, stub_access, messages) -> list[tuple[Any, list]]:
    from app.services.chatbot import console_service

    _seed_round5_catalogue(session_factory)
    _seed_contact(session_factory, phone="+60000865500")
    _link_contact_company(session_factory, company_id=MOCHA_COMPANY_ID)
    _seed_borrowable_envelope(session_factory)
    _seed_marketing_product_team(session_factory)
    monkeypatch.setattr(console_service, "SessionLocal", session_factory)
    stub_access()
    _stub_any_product_tool(monkeypatch)
    _two_kinds_for_water_closet(monkeypatch)
    calls = _capture_real_next_assignee(monkeypatch)
    sla = _capture_sla(monkeypatch)

    results: list[tuple[Any, list]] = []
    session_vars: dict[str, Any] = {}
    db = session_factory()
    try:
        for text_, parsed in messages:
            stub_parser(parsed)
            before = len(calls)
            turn = console_service.run_console_turn(
                db,
                contact_respond_id=str(CONTACT_ID),
                text=text_,
                session_vars=session_vars,
                run_id="zzt-865-r5",
            )
            results.append((turn, list(calls[before:])))
            print("DIAG", repr(text_), turn.branch_kind, turn.send_messages, [c["body"].get("team_code") for c in calls[before:]], (turn.trace_summary or {}).get("routing_line"))
            session_vars = turn.session_vars or {}
    finally:
        db.close()
    assert sla == [], "a console turn is a dry run: no SLA row"
    return results


def _assert_escalated(session_factory, turn, calls, *, brand: str | None, assignee: str, company: str | None):
    assert turn.branch_kind == "out_of_scope", (turn.branch_kind, turn.send_messages)
    assert len(calls) == 1, calls
    body = calls[0]["body"]
    assert (body["team_code"], body["brand_code"]) == ("marketing_product", brand), body
    assert calls[0]["response"].get("assignee_name") == assignee, calls[0]["response"]
    routing = _looked_up_routing(session_factory, turn.turn_id)
    assert routing["team_code"] == "marketing_product", routing
    assert routing["brand_code"] == brand, routing
    assert routing.get("product_company") == company, routing
    assert turn.send_messages[-1] == ROUTED_TO_MARKETING, turn.send_messages


def _no_customer_service_offer(turn) -> None:
    text_ = " ".join(turn.send_messages or []).lower()
    assert "customer service" not in text_, turn.send_messages


class TestTheOwnersRound4HandTestReplayed:
    def test_the_six_messages_in_one_console_conversation(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        """R1 to R4: every turn's branch kind, team, brand and reply."""
        results = _replay(session_factory, monkeypatch, stub_parser, stub_access, OWNERS_28SEP_ROUND5)
        (spec, spec_calls), second, (ok, ok_calls), (typo, typo_calls), fixed, (one, one_calls) = results

        assert spec.branch_kind == "business_query", spec.branch_kind
        assert spec_calls == []

        _assert_escalated(session_factory, *second, brand="sorento", assignee="ZZT Tay Zhi Yang", company="Sorento")

        assert ok.branch_kind == "low_signal", ok.branch_kind
        assert ok_calls == []

        # The typo: an escalation, not a spec answer. One question, inside the escalation:
        # the resolver's own did-you-mean, answered by a number, naming the team it goes to.
        assert typo.branch_kind == "out_of_scope", (typo.branch_kind, typo.send_messages)
        assert typo_calls == [], "nothing is drawn until the product is settled"
        assert typo.send_messages == [DID_YOU_MEAN], typo.send_messages
        _no_customer_service_offer(typo)

        # The corrected code: an escalation, never the kind menu.
        _assert_escalated(session_factory, *fixed, brand="mocha", assignee="ZZT Kia Yee", company="Mocha")
        _no_customer_service_offer(fixed[0])

        # "1" after the escalation went out: the did-you-mean was closed by it, so the
        # number answers nothing, draws nobody, and offers no customer service.
        assert one.branch_kind != "out_of_scope", (one.branch_kind, one.send_messages)
        assert one_calls == []
        _no_customer_service_offer(one)

    def test_the_typo_then_its_number_escalates_with_the_picked_products_brand(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        """R2: the did-you-mean answered straight away sends the escalation out, to the
        team the customer named, with the PICKED product's brand and company."""
        messages = [OWNERS_28SEP_ROUND5[0], OWNERS_28SEP_ROUND5[3], ("1", _position(1))]
        (_spec, _), (typo, typo_calls), (one, one_calls) = _replay(
            session_factory, monkeypatch, stub_parser, stub_access, messages
        )
        assert typo.send_messages == [DID_YOU_MEAN], typo.send_messages
        assert typo_calls == []
        _assert_escalated(session_factory, one, one_calls, brand="mocha", assignee="ZZT Kia Yee", company="Mocha")
        routing = _looked_up_routing(session_factory, one.turn_id)
        assert routing["routing_source"] == "focus_product", routing
        assert one.trace_summary["routing_line"] == (
            "Routing: team marketing_product, brand mocha, source focus_product, "
            "found in Mocha, assignee ZZT Kia Yee"
        ), one.trace_summary
        _no_customer_service_offer(one)

    @pytest.mark.parametrize(
        "message_type", ["business_query", "request_for_help", "clarification", "casual"]
    )
    def test_an_escalate_word_and_a_team_escalate_whatever_the_parser_typed_the_message(
        self, session_factory, stub_parser, stub_access, monkeypatch, message_type
    ) -> None:
        """R1: the message type the parser chose does not decide it; the escalate word
        and the team in its own reading of the message do."""
        parsed = {**_fixed_code_verdict(), "message_type": message_type, "domain_hint": "master_products"}
        [(turn, calls)] = _replay(
            session_factory,
            monkeypatch,
            stub_parser,
            stub_access,
            [("pelase escalate to marketing team MWc-SC8609-PP water closet", parsed)],
        )
        _assert_escalated(session_factory, turn, calls, brand="mocha", assignee="ZZT Kia Yee", company="Mocha")

    def test_a_product_ask_that_mentions_a_team_in_passing_is_still_a_product_ask(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        """R5: no escalate word, no escalation. "the marketing team's catalogue for X" is
        a question about X."""
        parsed = _product_verdict(
            "master_products",
            "check_product",
            "srtwc286",
            user_goal="trying to get the spec of SRTWC286 for the marketing team",
        )
        [(turn, calls)] = _replay(
            session_factory,
            monkeypatch,
            stub_parser,
            stub_access,
            [("spec srtwc286 for marketing team", parsed)],
        )
        assert turn.branch_kind == "business_query", turn.branch_kind
        assert calls == []
