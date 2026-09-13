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

# Security review round 4 audit: `pending` / `routing` / `routing_brand` /
# `routing_company` below are LEGACY keys a real five-key session can never hold
# (`contracts.SESSION_VAR_KEYS`) - the SAME class of shape B1's kill test found masking a
# defect in the old AC-1127 fixture. Here they are legitimate rather than a mistake: this
# dict is `documentation/plans/chatbot/evidence/escalation-routing-real-turns.json`'s own
# `previous_state_excerpt` for the 11 Sep 12:55 turn, byte-for-byte, which the plan's own
# note says is what the CONSOLE actually showed for that historical turn - and AC-1144's
# whole point is replaying the real capture, not a synthesised one. Killed by hand for
# AC-1101 (stripped every legacy key except `open_question` and `response`, reran): the
# result was byte-identical, because neither `_post_process` nor `suggest_follow_up`
# reads `pending` / `routing_brand` / `routing_company` for the arms these tests exercise
# - only `open_question` (added here on top of the real excerpt, since the excerpt
# predates the picker being persisted that way - see the comment below) and `response`
# (read by `offer_is_open`'s legacy regex fallback) matter to this file's assertions.
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

# Security review round 4 audit: same legitimacy as `TURN_1_PREVIOUS_STATE` above - this
# is the evidence file's own `previous_state_excerpt` for the 11 Sep 12:56 turn, verbatim.
# Killed by hand for AC-1103 and AC-1104 (stripped every legacy key, reran both): both
# results were byte-identical, since `offer_is_open` reads only `open_question` /
# `response` and neither AC touches team narrowing (where a fake `routing` key would
# actually matter - see `test_escalation_routing_team.py`'s AC-1113/1114/1115 audit).
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


# --------------------------------------------------------------------------- #
# Security review round 3, S2: suggest_follow_up's decline arm must not retype a
# named-team help request either.
# --------------------------------------------------------------------------- #


def test_s2_round3_a_declined_picker_offer_still_keeps_a_named_team_help_request() -> None:
    """Security review round 3, item S2. `suggest_follow_up`'s `has_entity_pick /
    has_pos_pick` arm already guards against retyping a named-team help request
    (`_named_team_help`, `output_exchange.py` ~1417/~3417), but its SIBLING arm - a bare
    "no" over an open picker (`is_affirmative is False`) - does not: it unconditionally
    sets `message_type = "casual"` and clears the entities. A help request that ALSO
    names a team ("no, escalate to marketing") must stay `request_for_help` (D1) rather
    than being read as a plain decline of the picker.

    Security review round 4 audit: this fixture used to also carry `pending` and
    `routing` keys alongside `open_question` - a shape a real five-key session cannot
    hold. Killed by hand (removed both, reran): byte-identical result, since neither key
    is read anywhere in `suggest_follow_up`'s decline arm or `_named_team_help`."""
    previous_state = {
        "open_question": {
            "kind": "product_pick",
            "options": [
                {"idx": 1, "uuid": "u1", "code": "SRTWCY8840", "label": "SRTWCY8840", "entity_type": "product"},
                {"idx": 2, "uuid": "u2", "code": "SRTWCY8840-SH", "label": "SRTWCY8840-SH", "entity_type": "product"},
            ],
            "expects": "pick",
            "asked_at_turn": 1,
            "asked_at": None,
            "payload": {"domain": "inventory"},
        },
    }
    parser_raw = _full_emission(
        message_type="request_for_help",
        is_affirmative=False,
        entities=[],
        routing={"suggested_team": "marketing", "suggested_agent": None},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        user_goal="trying to escalate to marketing, not pick a product",
    )

    qf = _post_process(parser_raw, previous_state, message="no, escalate to marketing")

    assert qf["message_type"] == "request_for_help", (
        "a help request naming a team must survive a decline over an open picker, not be "
        f"retyped casual: {qf!r}"
    )


# --------------------------------------------------------------------------- #
# Security review round 3, B2: a help request naming a team must not be retyped
# into a business-query pick just because it ALSO answers a stale open picker.
# --------------------------------------------------------------------------- #

_OPEN_PRODUCT_PICK = {
    "kind": "product_pick",
    "options": [
        {"idx": 1, "uuid": "u1", "code": "SRTWCY8840", "label": "SRTWCY8840", "entity_type": "product"},
        {"idx": 2, "uuid": "u2", "code": "SRTWCY8840-SH", "label": "SRTWCY8840-SH", "entity_type": "product"},
    ],
    "expects": "pick",
    "asked_at_turn": 1,
    "asked_at": None,
    "payload": {"domain": "inventory"},
}


def _run_with_answered_pick(parser_raw: dict, *, emits_v3: bool) -> dict:
    """`engine.run_turn`'s own three-line sequence for a picked-answer turn
    (`_resolve_open_question` then `post_process` then `suggest_follow_up`), reproduced
    directly rather than through the full engine so this file's fixtures stay in one
    place. Not a new helper on `_post_process` itself - that helper's existing callers
    (AC-1101/AC-1103/AC-1104) never need `_answered` and stay untouched."""
    from app.services.chatbot.engine import _resolve_open_question

    variables = {"open_question": dict(_OPEN_PRODUCT_PICK)}
    answered = _resolve_open_question(
        variables, parser_raw=parser_raw, emits_v3=emits_v3, referenced_result_set=None, turn_no=2
    )
    parent_input = {
        "latest_user_message": "",
        "contact_id": "ZZT-esc-head-1",
        "previous_conversation_state": variables,
        "parser_emits_v3": emits_v3,
        "_answered": answered,
        "turn_no": 2,
    }
    parse_block = post_process({"output": dict(parser_raw)}, {}, parent_input)
    parse_block = suggest_follow_up(parse_block, parent_input)
    return parse_block["output"]


def test_b2_a_named_team_help_request_that_also_answers_a_v3_pick_stays_a_help_request() -> None:
    """Security review round 3, item B2, v3 case: the parser emits a `request_for_help`
    naming team `marketing` AND, under prompt v3, resolves the open `product_pick`
    itself (`answers_open_question.picks: [2]`, matching the code `SRTWCY8840-SH` it also
    named as an entity). `apply_open_question_outcome` (`output_exchange.py` ~1170)
    overwrites `message_type` to `business_query` unconditionally whenever the outcome
    resolves a product, with no read of `named_team_help` - the escalation the parser
    correctly named is lost the same way AC-1101's suggest-pick arm lost it."""
    parser_raw = _full_emission(
        message_type="request_for_help",
        entities=[
            {"raw": "SRTWCY8840-SH", "hint": "product", "confident": True, "canonical_code": "SRTWCY8840-SH", "current_message": True}
        ],
        routing={"suggested_team": "marketing", "suggested_agent": None},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        user_goal="trying to escalate to marketing about SRTWCY8840-SH",
    )
    parser_raw["answers_open_question"] = {"resolved": True, "picks": [2], "yes_no": None, "free_text": None}
    # The three other v3-only keys `_assert_emission` requires once `emits_v3` is True.
    # `asks: []` takes `dialogue.intake.flatten`'s v1 fallback path, which reads THIS
    # emission's own flat `entities` / `domain_hint` unchanged rather than re-deriving
    # them from a v3 `asks` list this fixture does not build.
    parser_raw["asks"] = []
    parser_raw["anaphora"] = False
    parser_raw["topic_reset"] = False

    qf = _run_with_answered_pick(parser_raw, emits_v3=True)

    assert qf["message_type"] == "request_for_help", (
        f"a named-team help request must survive answering an open picker: {qf!r}"
    )
    branch, _tier = decide(_decide_ctx(qf))
    assert branch == "out_of_scope", (
        f"it must reach the escalation lane, not the business lane: {branch!r}"
    )


def test_b2_a_named_team_help_request_that_also_answers_a_positional_pick_stays_a_help_request() -> None:
    """Security review round 3, item B2, v1/positional case: the SAME shape, resolved
    through `reference_positions` (the v1 path `_resolve_open_question` falls back to
    when the emission carries no `answers_open_question` at all)."""
    parser_raw = _full_emission(
        message_type="request_for_help",
        entities=[],
        reference_positions=[2],
        routing={"suggested_team": "marketing", "suggested_agent": None},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        user_goal="trying to escalate to marketing, position 2",
    )

    qf = _run_with_answered_pick(parser_raw, emits_v3=False)

    assert qf["message_type"] == "request_for_help", (
        f"a named-team help request must survive a positional pick too: {qf!r}"
    )
    branch, _tier = decide(_decide_ctx(qf))
    assert branch == "out_of_scope", branch


# --------------------------------------------------------------------------- #
# Security review round 3, N7: the head half of AC-1125's resume. Only
# lane-level tests (`test_escalation_routing_brand.py`) covered this before, and
# they hand-build `_answered` rather than running the real head chain.
# --------------------------------------------------------------------------- #

_DEFERRED_PRODUCT_PICK = {
    "kind": "product_pick",
    "options": [
        {"idx": 1, "uuid": "u1", "code": "SRTWC6030-SH-BL", "label": "SRTWC6030-SH-BL", "entity_type": "product"},
    ],
    "expects": "pick",
    "asked_at_turn": 1,
    "asked_at": None,
    # D6/AC-1125: the escalation lane armed this did-you-mean with the team word the
    # customer typed on the DEFERRED turn - "marketing_product", an exact catalogue word.
    "payload": {"then": {"escalate": {"team_word": "marketing_product"}}},
}


def test_n7_a_resumed_deferred_escalation_pick_stays_on_the_escalation_lane() -> None:
    """Security review round 3, item N7 (AC-1125, head half). `open_question._product_pick`
    already sets `outcome.escalate = True` for a pick against a `then.escalate` payload,
    and `apply_open_question_outcome`'s own `if outcome.escalate:` branch (run AFTER its
    entities branch) correctly restamps `message_type = request_for_help`. But the SAME
    turn also still has an open `product_pick` in `PICKER_KINDS`, so `suggest_follow_up`
    runs its OWN `has_entity_pick` guard afterwards - and its `_named_team_help` check
    reads THIS turn's raw parser team word, which is null (the customer just typed "1";
    the team word is the DEFERRED one, on the question's payload, not retyped). RED
    today: `suggest_follow_up` retypes the resumed turn `business_query` a second time,
    undoing what `apply_open_question_outcome` had just set."""
    from app.services.chatbot.engine import _resolve_open_question

    variables = {"open_question": dict(_DEFERRED_PRODUCT_PICK)}
    parser_raw = _full_emission(
        message_type="casual",
        entities=[],
        reference_positions=[1],
        routing={"suggested_team": None, "suggested_agent": None},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        user_goal="picking option 1",
    )
    answered = _resolve_open_question(
        variables, parser_raw=parser_raw, emits_v3=False, referenced_result_set=None, turn_no=2
    )
    assert answered["outcome"] is not None and answered["outcome"].escalate is True, (
        "the pick itself must resume the deferred escalation - if this fails, the defect "
        f"is upstream of what N7 targets: {answered!r}"
    )

    parent_input = {
        "latest_user_message": "1",
        "contact_id": "ZZT-esc-head-1",
        "previous_conversation_state": variables,
        "parser_emits_v3": False,
        "_answered": answered,
        "turn_no": 2,
    }
    parse_block = post_process({"output": dict(parser_raw)}, {}, parent_input)
    parse_block = suggest_follow_up(parse_block, parent_input)
    qf = parse_block["output"]

    # N8: the message_type check above is a WEAKER signal than it looks - it survives
    # `suggest_follow_up` here only because `_DEFERRED_PRODUCT_PICK`'s payload carries no
    # "domain" key, so that function's own retype guard (`if jsc.truthy(o.get(
    # "domain_hint"))`) never activates on this fixture at all, whichever way
    # `_named_team_help` reads. The assertion that actually PROVES the resume is the
    # branch one below, which reads `route.decide`'s `wants_escalation_or_help()` - and
    # that predicate's FIRST clause is `escalation.is_escalation_confirmation is True`
    # (set by `apply_open_question_outcome`'s `outcome.escalate` branch), independent of
    # `message_type` entirely. A fixture WITH a domain on the payload would be a sharper
    # test of the message_type half; this one is not it.
    assert qf["message_type"] == "request_for_help", (
        f"a resumed deferred escalation must survive suggest_follow_up too: {qf!r}"
    )
    branch, _tier = decide(_decide_ctx(qf))
    assert branch == "out_of_scope", (
        f"it must reach the escalation lane, not the business lane: {branch!r}"
    )


# --------------------------------------------------------------------------- #
# Security review round 3 re-check, B3: the member-offer ladder's plain-decline
# arm must not swallow a named-team help request either.
# --------------------------------------------------------------------------- #

_OPEN_MEMBER_OFFER = {
    "kind": "member_offer",
    "options": [
        {"uuid": "m1", "label": "Ali"},
        {"uuid": "m2", "label": "Bee"},
    ],
    "expects": "yes_no",
    "asked_at_turn": 1,
    "asked_at": None,
    "payload": {},
}


def test_b3_a_declined_member_offer_still_keeps_a_named_team_help_request() -> None:
    """Security review round 3 re-check, item B3. Fixed by the coder's commit
    `c8b948fe8` between the previous round and this one: the member-offer ladder's
    plain-decline arm (`output_exchange.py` ~3187) had no `named_team_help` guard, unlike
    its two siblings (the switch-word arm and `suggest_follow_up`'s own decline arm), and
    Tier 1's retarget only saves an EXACT catalogue word - a family word like `marketing`
    falls straight through it. "no, escalate to marketing" over an open member roster
    came back `casual` with `escalation_declined: true` before the fix. GREEN now (the
    guard `test_b3_..._companion` below pins the OTHER half - a plain "no" with no team
    word still declines)."""
    previous_state = {"open_question": dict(_OPEN_MEMBER_OFFER)}
    parser_raw = _full_emission(
        message_type="request_for_help",
        is_affirmative=False,
        entities=[],
        routing={"suggested_team": "marketing", "suggested_agent": None},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        user_goal="no, escalate to marketing",
    )

    qf = _post_process(parser_raw, previous_state, message="no, escalate to marketing")

    assert qf["message_type"] == "request_for_help", (
        f"a named-team help request must survive declining an open member offer: {qf!r}"
    )
    assert qf["escalation"].get("escalation_declined") is not True, (
        f"declining the ROSTER is not declining the ESCALATION the customer asked for "
        f"instead: {qf['escalation']!r}"
    )
    branch, _tier = decide(_decide_ctx(qf))
    assert branch == "out_of_scope", (
        f"it must reach the escalation lane, not be silently declined: {branch!r}"
    )


def test_b3_companion_a_plain_no_with_no_team_word_still_declines_the_member_offer() -> None:
    """Security review round 3 re-check, B3 companion (guard): a bare "no", naming no
    team at all, must still decline the member offer exactly as it did before the fix -
    the fix narrows on `named_team_help`, it does not remove the decline arm."""
    previous_state = {"open_question": dict(_OPEN_MEMBER_OFFER)}
    parser_raw = _full_emission(
        message_type="request_for_help",
        is_affirmative=False,
        entities=[],
        routing={"suggested_team": None, "suggested_agent": None},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        user_goal="no thanks",
    )

    qf = _post_process(parser_raw, previous_state, message="no thanks")

    assert qf["message_type"] == "casual", (
        f"a plain decline naming no team must still be casual: {qf!r}"
    )
    assert qf["escalation"].get("escalation_declined") is True, (
        f"a plain decline must still say so deterministically: {qf['escalation']!r}"
    )
