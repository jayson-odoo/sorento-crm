"""PLAN-chatbot-escalation-routing.md, "Verb (one guard, head)". AC-1101, AC-1103, AC-1104.

RED, written before the coder's slice S1 (Phase 2, test-first). Fed to `output_exchange`
directly - the pure post-processor - with the REAL captured turns from
`documentation/plans/chatbot/evidence/escalation-routing-real-turns.json`, verbatim. AC-1102
is covered by the existing, UNTOUCHED `test_pass4_item5_no_team_named_keeps_default_routing.py`
(run alongside this file; not duplicated here).

D11-clean throughout: every assertion reads `_post_process`'s STRUCTURED output
(`message_type`, `escalation.is_escalation_confirmation`) and `route.decide`'s structured
`branch_kind`, never the customer's or the bot's words.
"""
from __future__ import annotations

from app.services.chatbot.head.output_exchange import post_process, suggest_follow_up
from app.services.chatbot.head.route import decide


def _post_process(parser_raw: dict, previous_state: dict, *, message: str = "") -> dict:
    """One turn through the real post-processing chain - `engine.run_turn`'s own two
    calls, in its own order (`app/services/chatbot/engine.py`, the `parse_block =
    post_process(...); parse_block = suggest_follow_up(...)` pair): `post_process` first,
    then `suggest_follow_up` on the SAME item. The suggest-pick retype arm this file's
    AC-1101 targets lives in `suggest_follow_up`, not `post_process` - reproduced here
    rather than shortcut to the pure post-processor alone.
    """
    parent_input = {
        "latest_user_message": message,
        "contact_id": "ZZT-esc-head-1",
        "previous_conversation_state": previous_state,
    }
    parse_block = post_process({"output": dict(parser_raw)}, {}, parent_input)
    parse_block = suggest_follow_up(parse_block, parent_input)
    return parse_block["output"]


def _decide_ctx(qf: dict) -> dict:
    """The six-key hub `route.decide` reads: `parse.output` plus an allowed access."""
    return {
        "contact": {"id": "ZZT-esc-head-1", "custom_fields": []},
        "text": {"message": {"message": {"type": "text", "text": ""}}},
        "session": {"session_vars": {"variables": {}}},
        "parse": {"output": qf},
        "access": {"allowed": True, "decision": "allow"},
        "media": None,
    }


# --------------------------------------------------------------------------- #
# The 11 Sep 12:55 turn (turn_1): a suggest offer open, an escalation naming a team
# --------------------------------------------------------------------------- #

TURN_1_PARSER_RAW = {
    "message_type": "request_for_help",
    "intent_hint": "check_product",
    "domain_hint": "master_products",
    "scope_intent": None,
    "is_affirmative": True,
    "user_goal": "trying to escalate to marketing and check the product for SRTWC60630-SH",
    "access_levels": [],
    "broaden_axis": None,
    "date_mode": None,
    "date_filter_start": None,
    "date_filter_end": None,
    "match_mode": "and",
    "demand_qty": None,
    "entities": [
        {"raw": "BIDET SEAT COVER", "hint": "category", "confident": True, "canonical_code": None, "current_message": True},
        {"raw": "SRTWC60630-SH", "hint": "product", "confident": True, "canonical_code": None, "current_message": True},
    ],
    "entity_op": "replace_combine",
    "scope_exclusive": False,
    "requested_attributes": [],
    "contains_flyer": False,
    "reference_positions": [],
    "reference_target": None,
    "person_mention": None,
    "is_active": None,
    "order_status": None,
    "correction": False,
    "group_by": None,
    "top_n": None,
    "routing": {"suggested_team": "marketing", "suggested_agent": None},
    "escalation": {"is_escalation_confirmation": False, "company_pick": None},
}

TURN_1_PREVIOUS_STATE = {
    "pending": None,
    "routing": {"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
    "entities": [{"raw": "srtwt61012-gm", "hint": "product", "confident": True, "canonical_code": "SRTWT61012-GM", "current_message": True}],
    "domain_hint": "inventory",
    "intent_hint": "check_stock",
    "message_type": "business_query",
    "routing_brand": "sorento",
    "routing_brand_source": "resolved",
    "routing_company": "00000000-0000-0000-0000-000000000001",
    "response": "Previous turn (inventory): returned 1 records",
    # The five-key session's own shape for the evidence file's legacy `selection_context:
    # suggest_offer` + `last_result_set` pair (migration `517_chatbot_session_5key`
    # converts every stored session to this on deploy - see `dialogue/open_question.py`'s
    # module docstring). `suggest_follow_up` keys its retype arm on `open_question.kind` in
    # `PICKER_KINDS`, so this is the shape that actually reaches that arm today.
    "open_question": {
        "kind": "product_pick",
        "options": [
            {"idx": 1, "uuid": "c877d4aa-6444-4513-87a8-af8212a5f1d8", "code": "SRTWCY8840", "label": "SRTWCY8840", "entity_type": "product"},
            {"idx": 2, "uuid": "e189b0ab-f644-41f2-a932-92430b28872a", "code": "SRTWCY8840-SH", "label": "SRTWCY8840-SH", "entity_type": "product"},
            {"idx": 3, "uuid": "81e5ae99-d6a0-44d5-88e2-a893db9681f9", "code": "SRTWCY8840-FT", "label": "SRTWCY8840-FT", "entity_type": "product"},
        ],
        "expects": "pick",
        "asked_at_turn": 1,
        "asked_at": None,
        "payload": {"domain": "inventory"},
    },
}


def test_ac1101_a_named_team_help_request_is_routed_to_escalation_over_a_stale_suggest_offer() -> None:
    """AC-1101 / D1. Measured on origin/main, 13 Sep 2026 (plan "Why" table, row 1): this
    exact turn is retyped `business_query` by the suggest-pick arm because a suggest offer
    was left open, and the escalation the parser correctly named is lost. D1: a
    `request_for_help` turn that names a team is an escalation, full stop, whatever the
    previous turn left open - no retype arm applies to it."""
    qf = _post_process(TURN_1_PARSER_RAW, TURN_1_PREVIOUS_STATE, message="ESCALTE TO MARKETING BIDET SEAT COVER FOR SRTWC60630-SH")

    assert qf["message_type"] == "request_for_help", (
        "a help request naming a team must stay request_for_help whatever offer was open: "
        f"got {qf['message_type']!r} (today's suggest-pick arm retypes it business_query)"
    )

    branch, _tier = decide(_decide_ctx(qf))
    assert branch == "out_of_scope", (
        f"a request_for_help turn naming a team must reach the escalation lane: {branch!r}"
    )


# --------------------------------------------------------------------------- #
# The 11 Sep 12:56 turn (turn_3): the confirmation flag with nothing pending
# --------------------------------------------------------------------------- #

def _full_emission(**overrides) -> dict:
    """A well-formed 26-key emission, the same base
    `tests/chatbot/test_output_exchange_rules.py::parser_output` uses - `_assert_emission`
    refuses anything short of the full declared v1/v2 contract, and the evidence file's
    captures are the ABBREVIATED view a production console shows, not the wire shape."""
    base = {
        "message_type": "business_query",
        "intent_hint": None,
        "domain_hint": None,
        "scope_intent": None,
        "is_affirmative": None,
        "user_goal": "trying to check something",
        "access_levels": [],
        "broaden_axis": None,
        "date_mode": None,
        "date_filter_start": None,
        "date_filter_end": None,
        "match_mode": "and",
        "demand_qty": None,
        "entities": [],
        "entity_op": "replace_combine",
        "scope_exclusive": False,
        "requested_attributes": [],
        "contains_flyer": False,
        "reference_positions": [],
        "reference_target": None,
        "person_mention": None,
        "is_active": None,
        "order_status": None,
        "correction": False,
        "routing": {"suggested_team": None, "suggested_agent": None},
        "escalation": {"is_escalation_confirmation": False, "company_pick": None},
    }
    base.update(overrides)
    return base


TURN_3_PARSER_RAW = _full_emission(
    message_type="request_for_help",
    intent_hint=None,
    domain_hint=None,
    is_affirmative=True,
    user_goal="trying to escalate to marketing",
    entities=[],
    entity_op="reuse",
    routing={"suggested_team": "marketing", "suggested_agent": None},
    escalation={"is_escalation_confirmation": True, "company_pick": None},
)

TURN_3_PREVIOUS_STATE = {
    "pending": None,
    "routing": {"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
    "entities": [
        {"raw": "MARKETING", "hint": "customer", "confident": True, "canonical_code": None, "current_message": True},
        {"raw": "SRTWC6030-SH", "hint": "product", "confident": True, "canonical_code": None, "current_message": True},
    ],
    "domain_hint": "master_products",
    "intent_hint": "check_product",
    "message_type": "business_query",
    "routing_brand": "sorento",
    "routing_brand_source": "resolved",
    "routing_company": "00000000-0000-0000-0000-000000000001",
    "routing_companies": [
        {
            "codes": ["SRTWC6030-SH-MW", "SRTWC6030-SH-MG", "SRTWC6030-SH-BL", "SRTWC6030-SH-MK", "SRTWC6030-SH-UF"],
            "labels": ["SRTWC6030-SH-MW", "SRTWC6030-SH-MG", "SRTWC6030-SH-BL", "SRTWC6030-SH-MK", "SRTWC6030-SH-UF"],
            "brand_code": "sorento",
            "company_id": "00000000-0000-0000-0000-000000000001",
            "company_name": "Sorento",
        }
    ],
    "selection_context": None,
    "response": "Previous turn (master_products): returned 5 records",
}


def test_ac1103_the_confirmation_flag_is_ignored_with_nothing_pending() -> None:
    """AC-1103 (plan "Verb", second paragraph): `escalation.is_escalation_confirmation:
    true` from the parser is honoured only while an offer is open (`offer_is_open`); with
    `pending: null` and no `open_question` at all it must be forced False. Today nothing in
    `output_exchange` clears the flag against the offer state at all - it passes the
    parser's raw True straight through, which is what made `_person_routing`'s flag-first
    check (pre-D2 ordering) swallow this exact turn (plan "Why" table, row 2)."""
    qf = _post_process(TURN_3_PARSER_RAW, TURN_3_PREVIOUS_STATE, message="ESCALATE TO MARKETING")

    assert qf["escalation"]["is_escalation_confirmation"] is False, (
        "no offer is open on this turn (pending null, no open_question) so the flag must "
        f"be forced False: {qf['escalation']!r}"
    )


def test_ac1104_the_confirmation_flag_still_confirms_over_an_open_one_team_offer() -> None:
    """AC-1104: the OTHER half of AC-1103's rule, kept green as a guard. An OPEN one-team
    `team_pick` offer (`expects: yes_no`, D5's fold of the old escalate-offer) still lets
    the flag confirm - this is the existing behaviour AC-1103 must not disturb."""
    previous_state_with_open_offer = {
        **TURN_3_PREVIOUS_STATE,
        "open_question": {
            "kind": "team_pick",
            # The SAME team the parser names this turn (`marketing`, TURN_3_PARSER_RAW) -
            # a one-team offer for a DIFFERENT team hits the existing "names a different
            # team" retarget arm instead (`output_exchange.py` ~2598), which is a separate,
            # already-covered rule and not what AC-1104 is pinning.
            "options": [{"team": "marketing", "label": "Marketing"}],
            "expects": "yes_no",
            "asked_at_turn": 1,
            "asked_at": None,
            "payload": {"team": "marketing"},
        },
    }
    qf = _post_process(TURN_3_PARSER_RAW, previous_state_with_open_offer, message="yes")

    assert qf["escalation"]["is_escalation_confirmation"] is True, (
        "an open one-team offer must still let the parser's confirmation flag stand: "
        f"{qf['escalation']!r}"
    )
