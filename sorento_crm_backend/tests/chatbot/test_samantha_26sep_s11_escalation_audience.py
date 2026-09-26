"""Phase 2 RED tests - issue #1262 (Samantha case), slice 11, finding F8.

Turns T3/T10/T11: every lookup missed, so `turn/compose.py` offered the domain's
escalation team - to Samantha, a staff sales rep (`respond_contacts.chatbot_profile.
tier == "office"`, owner ruling 2 in the plan). The composer's offer (compose.py,
"ONE open question per turn" section) reads only `envelopes` and each missed domain's
`escalation_team_code`; it never reads `state.profile.tier` at all.

AC-S11-1: a contact whose profile tier is `office` gets no "Would you like me to
escalate" sentence and no offer armed, on a total miss.
AC-S11-2: no audience gets an offer added to a reply while a clarifying question
(a still-open roster, e.g. T3's `kind_pick`) is open.
AC-S11-3 (guard, not a red test): a dealer or end-user contact's total-miss offer is
UNCHANGED (R6 of 22 Sep stands) - this must stay green through the S11 fix.

Plan: PLAN-chatbot-samantha-slices-26sep.md, slice 11. UAC:
chatbot-samantha-slices-26sep-acceptance-criteria.md.
"""
from __future__ import annotations

from app.services.chatbot.turn.compose import compose
from app.services.chatbot.turn.pending import Pending
from app.services.chatbot.turn.policy import Policy
from app.services.chatbot.turn.state import Focus, Profile, State

from tests.chatbot._turn_helpers import TIER_ORDER_FIXTURE, _domain_row


def _policy() -> Policy:
    row = _domain_row("inventory", narrowing={"product": "list_all"})
    row["escalation_team_code"] = "warehouse"
    return Policy.from_rows(domains=[row], kinds=[], tier_order=TIER_ORDER_FIXTURE)


def _total_miss_envelope() -> dict:
    return {
        "domain": "inventory",
        "denied": False,
        "entities": ["M210-GM"],
        "figures": [],
        "files": [],
        "miss": ["M210-GM"],
        "has_result": False,
    }


def test_t10_staff_inventory_miss_gets_no_warehouse_escalation_offer():
    """AC-S11-1 (T10's own turn: the false catalogue-sweep miss offered "Would you
    like me to escalate to warehouse team?" to Samantha, a staff rep). Red: `compose()`
    never reads `state.profile.tier` before arming the offer.
    """
    state = State(focus=Focus(), pending=None, profile=Profile(tier="office"), turn_no=10)

    answer = compose([_total_miss_envelope()], state, _policy(), ctx=None)

    assert answer.offer is None, f"a staff rep must get no bot-initiated offer: {answer.offer!r}"
    assert "escalate" not in answer.text.lower(), answer.text


def test_t11_staff_stock_miss_composer_offer_absent():
    """AC-S11-1 (T11's own turn, the same miss shape repeated once Samantha's stock
    ask kept missing). Kept as its own test because it traces to its own turn in the
    captain's list, not because the code path differs from T10's.
    """
    state = State(focus=Focus(), pending=None, profile=Profile(tier="office"), turn_no=11)

    answer = compose([_total_miss_envelope()], state, _policy(), ctx=None)

    assert answer.offer is None
    assert "Would you like me to escalate" not in answer.text, answer.text


def test_t3_ambiguous_outstanding_ask_clarifies_instead_of_offering_customer_service():
    """AC-S11-2 (T3's own turn): a `kind_pick` armed by an earlier turn is still open
    (a roster, `pending.py::ROSTER_KINDS`) when this turn's fetch also misses on every
    domain - the customer is mid clarifying-question and must not ALSO be offered
    escalation. Red: `compose()`'s offer arm only checks whether THIS turn's own fetch
    asked a question (`_lane_question`); a roster carried in from state.pending is not
    read at all, so the still-open kind_pick gets `escalate_offered` stamped onto it
    and the sentence is printed anyway.
    """
    kind_pick = Pending(
        kind="kind_pick",
        expects=None,
        options=[
            {"position": 1, "label": "Sorento (transporter)", "raw": "Sorento", "entity_type": "transporter"},
            {"position": 2, "label": "Sorento (customer)", "raw": "Sorento", "entity_type": "customer"},
        ],
        team=None,
        payload={},
        asked_at_turn=2,
    )
    state = State(focus=Focus(), pending=kind_pick, profile=Profile(tier="office"), turn_no=3)

    answer = compose([_total_miss_envelope()], state, _policy(), ctx=None)

    assert answer.offer is None, f"a clarifying question is still open, no offer must be added: {answer.offer!r}"
    assert "escalate" not in answer.text.lower(), answer.text


def test_dealer_stock_miss_keeps_the_warehouse_offer():
    """AC-S11-3, the R6 guard: a dealer contact's total-miss offer is UNCHANGED by the
    S11 fix. This must be GREEN today and stay green - it is the guard against an
    over-broad "nobody gets offered escalation" fix.
    """
    state = State(focus=Focus(), pending=None, profile=Profile(tier="dealer"), turn_no=10)

    answer = compose([_total_miss_envelope()], state, _policy(), ctx=None)

    assert answer.offer is not None
    assert answer.offer.teams == ["warehouse"]
    assert "Would you like me to escalate to warehouse team?" in answer.text


# --------------------------------------------------------------------------- #
# AC-S11-1's OTHER offer path: the cross-domain zero-stock ladder. This is a
# SEPARATE mechanism from `turn/compose.py`'s own offer arm above -
# `answer_bridge.py::apply_crossdomain_hit` (~165-272) appends `tail/compose.py::
# crossdomain_compose`'s (~86-103) locked "Would you like me to escalate to X
# team?" phrase whenever the ladder block is non-empty, and neither function reads
# `state.profile.tier` (or any audience signal at all) - a fix scoped to
# `turn/compose.py` alone does not reach this path. Same harness as
# `test_rearch_r11_zero_stock_ladder.py` (a real `engine.run_turn`, Postgres blank
# schema, resolver + MCP tool runner stubbed).
# --------------------------------------------------------------------------- #
from sqlalchemy import text as _sql_text

from tests.chatbot.test_engine import CONTACT_ID as _CONTACT_ID
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401 - fixtures by name
from tests.chatbot.test_rearch_r11_zero_stock_ladder import (
    EMPTY_PO,
    WAREHOUSE_OFFER,
    ZERO_CODE,
    ZERO_UUID,
    _incoming_rows,
    _run as _run_zero_stock_turn,
    _stock_hit,
    _stock_row,
)


def _seed_contact_with_tier(session_factory, *, tier: str) -> None:
    """The same `respond_contacts.chatbot_profile` seed
    `test_rearch_s3_profile_hints.py::_seed_with_profile` uses - a bare row (as
    `test_engine.seeded` inserts) never sets a tier, so this test controls it
    directly rather than depending on that fixture's default.
    """
    import json as _json

    db = session_factory()
    db.execute(
        _sql_text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, "
            "chatbot_profile) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), CAST(:p AS jsonb))"
        ),
        {
            "cid": str(_CONTACT_ID),
            "phone": "+60000000011",
            "sv": _json.dumps({"variables": {}}),
            "p": _json.dumps({"tier": tier, "language": "en", "default_ledgers": []}),
        },
    )
    db.commit()


def test_staff_ladder_rung_gets_no_warehouse_escalation_offer(
    session_factory, stub_parser, stub_access, system_settings_row, monkeypatch
):
    """AC-S11-1, the ladder path: an `office`-tier contact (a staff sales rep) whose
    stock answer climbs the zero-stock -> incoming rung must get no "escalate"
    sentence and no offer - the SAME rule the composer's own offer follows, applied
    to the OTHER mechanism that prints it.

    Red today: `answer_bridge.apply_crossdomain_hit` has no `profile`/tier parameter
    at all and appends the locked phrase whenever `crossdomain_zeroset` found
    something to climb to, regardless of who is asking.
    """
    _seed_contact_with_tier(session_factory, tier="office")

    result, said, probes = _run_zero_stock_turn(
        session_factory, monkeypatch, stub_parser, stub_access,
        codes={ZERO_CODE: ZERO_UUID},
        stock=_stock_hit([_stock_row(ZERO_CODE, 0, "compact")], "compact"),
        incoming=_incoming_rows(ZERO_CODE),
        po=EMPTY_PO,
    )

    assert result.status == "done", result.error
    assert probes, "the ladder must still climb and answer for a staff rep"
    assert WAREHOUSE_OFFER not in said, (
        f"a staff rep must get no bot-initiated escalation offer off the ladder rung: {said!r}"
    )
    assert "escalate" not in said.lower(), said


def test_dealer_ladder_rung_keeps_the_warehouse_offer(
    session_factory, stub_parser, stub_access, system_settings_row, monkeypatch
):
    """Guard (R6): a dealer contact's ladder-rung offer is UNCHANGED by the S11 fix.
    Must be GREEN today and stay green.
    """
    _seed_contact_with_tier(session_factory, tier="dealer")

    result, said, probes = _run_zero_stock_turn(
        session_factory, monkeypatch, stub_parser, stub_access,
        codes={ZERO_CODE: ZERO_UUID},
        stock=_stock_hit([_stock_row(ZERO_CODE, 0, "compact")], "compact"),
        incoming=_incoming_rows(ZERO_CODE),
        po=EMPTY_PO,
    )

    assert result.status == "done", result.error
    assert probes
    assert WAREHOUSE_OFFER in said, said


# --------------------------------------------------------------------------- #
# AC-S11-1's THIRD offer path (coordinator round, 26 Sep 2026, found via the T4
# engine replay after slice 8's kind_pick fix): `answer_bridge.answer_for`'s own
# MISS composer (`lanes/business/answer.py::not_found_error_message`'s
# `build_breakdown_msg` closure) prints "But no order matched these ... Would you
# like me to escalate to customer service team?" unconditionally - a THIRD
# mechanism, beside `turn/compose.py`'s offer arm and the cross-domain ladder,
# that never read `state.profile.tier` either. Written by the coder (not the
# tester) - a gap in the same AC the tester's own T3/T10/T11 reds did not reach,
# because none of them drove a genuine order-domain miss through
# `answer_bridge.answer_for` with an office-tier profile.
# --------------------------------------------------------------------------- #
from app.services.chatbot import answer_bridge as _answer_bridge_mod
from app.services.chatbot import copy as _copy_mod
from app.services.chatbot.lanes.business.services import AnswerServices as _AnswerServices


def _order_miss_parser() -> dict:
    return {
        "domain_hint": "order",
        "intent_hint": "check_order",
        "message_type": "business_query",
        "entities": [{"raw": "STWC26", "hint": "product", "current_message": True, "confident": True}],
        "routing": {"suggested_team": "customer_service", "suggested_agent": "general_enquiries"},
        "access_levels": [],
    }


def _order_miss_ctx(parser: dict) -> dict:
    return {"parse": {"output": parser}, "contact": {"id": "zzt-s11-contact"}, "session": {}}


def _order_miss_services() -> _AnswerServices:
    return _AnswerServices(
        mcp_probe=lambda name, args: {"has_result": False, "answers": []},
        family_fetch=lambda query: {"data": []},
    )


def _run_order_miss(profile) -> str:
    """T4's own shape (`build_breakdown_msg`'s `use_breakdown` arm, `answer.py:3192`):
    a customer resolves cleanly (`found_lines` non-empty) but no ORDER matched for
    them - "But no order matched these", never the "Couldn't find: X" shape a
    wholly-unresolved token takes (`answer.py:3675`, a DIFFERENT branch this helper
    must not accidentally hit)."""
    parser = _order_miss_parser()
    resolved = {
        "resolutions": [
            {
                "token": "Cheng Huat Sentul",
                "matches": [
                    {
                        "uuid": "zzt-cheng-huat",
                        "entity_type": "customer",
                        "canonical_code": "Cheng Huat Sentul",
                        "match_tier": "exact",
                    }
                ],
            }
        ],
        "unresolved_tokens": [],
        "tokens": ["Cheng Huat Sentul"],
    }
    gate = {
        "gate_passed": True,
        "compatible_entities": [
            {"uuid": "zzt-cheng-huat", "entity_type": "customer", "code": "Cheng Huat Sentul"}
        ],
        "gate_debug": {"domain": "order"},
    }
    payload = {"resolved": resolved, "gate": gate, "_exit_kind": "not_found"}
    answer = _answer_bridge_mod.answer_for(
        payload,
        envelope=None,
        parser=parser,
        ctx=_order_miss_ctx(parser),
        canned=_copy_mod.fallback_copy(),
        services=_order_miss_services(),
        db=None,
        asked_at_turn=4,
        profile=profile,
    )
    assert answer is not None, "answer_for returned None for a resolver not_found exit"
    return answer.text


def test_staff_order_miss_gets_no_customer_service_offer():
    """AC-S11-1, the answer_bridge miss composer (coder-written, T4 replay finding):
    an office-tier profile driving a genuine order-domain miss through
    `answer_bridge.answer_for` must get no "Would you like me to escalate" clause -
    the same audience rule `turn/compose.py` and the cross-domain ladder already
    apply, extended to this THIRD site (`not_found_error_message`'s own
    `build_breakdown_msg` closure).
    """
    text = _run_order_miss(Profile(tier="office"))

    assert "escalate" not in text.lower(), text
    assert "matched these" in text.lower(), (
        f"the miss sentence itself must still print - only the offer is gated: {text!r}"
    )


def test_dealer_order_miss_keeps_the_customer_service_offer():
    """Guard (R6): a dealer/non-staff profile's miss offer through this SAME seam is
    UNCHANGED - must be GREEN today and stay green through the fix above.
    """
    text = _run_order_miss(Profile(tier="dealer"))

    assert "would you like me to escalate to customer service team?" in text.lower(), text


def test_clarifying_question_open_at_the_answer_bridge_seam_still_gets_no_fresh_offer_text():
    """AC-S11-2, covered at this THIRD seam too (coordinator's own follow-up ask):
    a clarifying question (a still-open roster, contract 36) carried in from a
    PRIOR turn must not gain a SECOND, bot-initiated escalate sentence when this
    turn's own fetch also misses - checked here for a STAFF profile specifically,
    since that is the audience the miss-composer fix above narrows to; a dealer's
    roster+escalate combine (contract 36's own established behaviour) is
    unchanged and not asserted here.
    """
    from app.services.chatbot.turn.pending import Pending as _Pending

    carried = _Pending(
        kind="customer_pick",
        expects=None,
        options=[
            {"position": 1, "label": "Cheng Huat Sentul", "raw": "Cheng Huat", "entity_type": "customer"},
            {"position": 2, "label": "Cheng Huat Trading", "raw": "Cheng Huat", "entity_type": "customer"},
        ],
        team=None,
        payload={},
        asked_at_turn=3,
    )
    parser = _order_miss_parser()
    resolved = {
        "resolutions": [
            {
                "token": "Cheng Huat Sentul",
                "matches": [
                    {
                        "uuid": "zzt-cheng-huat",
                        "entity_type": "customer",
                        "canonical_code": "Cheng Huat Sentul",
                        "match_tier": "exact",
                    }
                ],
            }
        ],
        "unresolved_tokens": [],
        "tokens": ["Cheng Huat Sentul"],
    }
    gate = {
        "gate_passed": True,
        "compatible_entities": [
            {"uuid": "zzt-cheng-huat", "entity_type": "customer", "code": "Cheng Huat Sentul"}
        ],
        "gate_debug": {"domain": "order"},
    }
    payload = {"resolved": resolved, "gate": gate, "_exit_kind": "not_found"}
    answer = _answer_bridge_mod.answer_for(
        payload,
        envelope=None,
        parser=parser,
        ctx=_order_miss_ctx(parser),
        canned=_copy_mod.fallback_copy(),
        services=_order_miss_services(),
        db=None,
        asked_at_turn=4,
        profile=Profile(tier="office"),
        carried_pending=carried,
    )
    assert answer is not None
    assert "escalate" not in answer.text.lower(), answer.text


# --------------------------------------------------------------------------- #
# Coordinator round 2 (26 Sep 2026): AC-S11-1 names the outstanding-report miss
# EXPLICITLY, and `not_found_error_message` turned out to carry ELEVEN separate
# "Would you like me to escalate" clauses, not one - every branch of its own big
# if/elif tree builds its own copy. Two of the other ten, driven directly (no
# `answer_bridge` round-trip needed - `not_found_error_message` is the ONE place
# every one of them is built, and its own `escalate_message` key is what a caller
# reads verbatim).
# --------------------------------------------------------------------------- #
from app.services.chatbot.lanes.business import answer as _answer_mod


def test_staff_outstanding_report_empty_miss_gets_no_offer():
    """AC-S11-1's own explicit example: an outstanding report that came back with
    nothing still ends in "Would you like me to escalate to X team?" today,
    unconditionally - the `_outstanding_report_text(item)` branch of
    `not_found_error_message`."""
    item = {
        "outstanding_report": True,
        "response": "Product: SRTWC286\nCustomer: all\nLocation: all\nOrder date: all\n\n"
        "*Sales order outstanding*\nNo open sales order.",
    }
    parser = {"domain_hint": "order", "intent_hint": "check_order", "routing": {}}
    resolved = {"resolutions": [], "unresolved_tokens": [], "tokens": []}
    gate = {"gate_passed": True, "compatible_entities": []}

    out = _answer_mod.not_found_error_message(
        item, parser=parser, resolved=resolved, gate=gate, profile=Profile(tier="office")
    )

    text = out.get("escalate_message") or ""
    assert "escalate" not in text.lower(), text
    assert "No open sales order." in text, (
        f"the report's own rendered text must still print - only the offer is gated: {text!r}"
    )


def test_dealer_outstanding_report_empty_miss_keeps_the_offer():
    """Guard (R6): unchanged for a dealer/non-staff profile through this SAME branch."""
    item = {
        "outstanding_report": True,
        "response": "Product: SRTWC286\nCustomer: all\nLocation: all\nOrder date: all\n\n"
        "*Sales order outstanding*\nNo open sales order.",
    }
    parser = {"domain_hint": "order", "intent_hint": "check_order", "routing": {}}
    resolved = {"resolutions": [], "unresolved_tokens": [], "tokens": []}
    gate = {"gate_passed": True, "compatible_entities": []}

    out = _answer_mod.not_found_error_message(
        item, parser=parser, resolved=resolved, gate=gate, profile=Profile(tier="dealer")
    )

    text = out.get("escalate_message") or ""
    assert "would you like me to escalate" in text.lower(), text


def test_staff_catalog_could_not_find_miss_gets_no_offer():
    """The catalog "Couldn't find: X" branch (`not_found_raw and not found_lines` -
    nothing resolved at all, no compatible entities) - a DIFFERENT branch from the
    `build_breakdown_msg`/"But no order matched these" one slice 11's first fix
    covered, and from the outstanding-report one above."""
    item = {}
    parser = {
        "domain_hint": "order",
        "intent_hint": "check_order",
        "entities": [{"raw": "STWC26", "hint": "product", "current_message": True, "confident": True}],
        "routing": {},
    }
    resolved = {
        "resolutions": [{"token": "STWC26", "matches": []}],
        "unresolved_tokens": ["STWC26"],
        "tokens": ["STWC26"],
    }
    gate = {"gate_passed": True, "compatible_entities": []}

    out = _answer_mod.not_found_error_message(
        item, parser=parser, resolved=resolved, gate=gate, profile=Profile(tier="office")
    )

    text = out.get("escalate_message") or ""
    assert "escalate" not in text.lower(), text
    assert "couldn't find" in text.lower(), text


# --------------------------------------------------------------------------- #
# Phase 3 fix-round findings (26 Sep, reviewer pass on the coder's S11 change):
# `turn/compose.py` ~430-470 gates the VISIBLE offer sentence (`if not is_staff and
# not clarifying_open`) but the roster-carry stamp right below it
# (`carried is not None and is_roster(carried.kind)`) runs UNCONDITIONALLY - so a
# staff contact gets no offer TEXT but the pending is stamped `escalate_offered:
# True` anyway, and a later bare "yes" over that pending routes to escalation
# through `turn/apply.py::_answer_pending`'s affirmative arm regardless of the
# hidden text. `clarifying_open = state.pending is not None` is also over-broad in
# the OTHER direction: it hides a DEALER's legitimate offer sentence over an OLD,
# already-fully-answered roster (hand pass 2 item 8's own rule), which is not "a
# clarifying question open right now".
# --------------------------------------------------------------------------- #


def test_withheld_offer_arms_no_hidden_escalation():
    """AC-S11-1/S11-2, office tier, three shapes that all hide the offer SENTENCE
    today (correctly) but must ALSO leave no hidden escalation behind: (1) a carried
    `product_pick` roster, already fully answered, over a fresh miss; (2) no pending
    at all, an order-domain miss composed through `answer_bridge.answer_for` (a
    SEPARATE code path from `turn/compose.py`); (3) a carried `outstanding_detail`
    pending (not a roster) over a miss.
    """
    from app.services.chatbot.turn.apply import apply

    from tests.chatbot._turn_helpers import verdict

    # ---- Shape 1: carried product_pick (an OLD, fully-answered roster) + miss ----
    product_pick = Pending(
        kind="product_pick", expects=None,
        options=[{"position": 1, "label": "A"}, {"position": 2, "label": "B"}],
        team=None, payload={"answered_positions": [1, 2]}, asked_at_turn=1,
    )
    state = State(focus=Focus(), pending=product_pick, profile=Profile(tier="office"), turn_no=5)
    answer = compose([_total_miss_envelope()], state, _policy(), ctx=None)

    assert "escalate" not in answer.text.lower(), answer.text
    pending_after = answer.question
    assert pending_after is not None and pending_after.payload.get("escalate_offered") is not True, (
        f"a hidden offer must not stamp escalate_offered on the pending: {pending_after!r}"
    )

    # A following bare "yes" must NOT route to the escalation lane.
    state2 = State(focus=Focus(), pending=pending_after, profile=Profile(tier="office"))
    _state_out, plan2 = apply(state2, verdict(is_affirmative=True), _build_policy_for_apply())
    assert plan2.trace.lane != "escalation", (
        f"a 'yes' over a withheld offer's pending must not accept an escalation nobody was shown: "
        f"{plan2.trace.lane!r}"
    )

    # ---- Shape 2: no pending, order-domain miss through answer_bridge.answer_for ---
    from app.services.chatbot import answer_bridge
    from app.services.chatbot import copy as copy_mod
    from app.services.chatbot.lanes.business.services import AnswerServices

    product_code = "SRTWC6022"
    parser = {
        "domain_hint": "order", "intent_hint": "check_order", "message_type": "business_query",
        "entities": [{"raw": product_code, "hint": "product", "current_message": True, "confident": True}],
        "routing": {"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
        "access_levels": [],
    }
    resolved = {
        "resolutions": [{
            "token": product_code,
            "matches": [{
                "entity_type": "product", "canonical_code": product_code,
                "uuid": "6136ea6b-1699-46ec-8e8e-f60c8bb64310", "match_tier": "exact",
            }],
        }],
        "unresolved_tokens": [], "tokens": [product_code],
        "intersection": [{
            "entity_type": "product", "canonical_code": product_code,
            "uuid": "6136ea6b-1699-46ec-8e8e-f60c8bb64310",
        }],
    }
    gate = {
        "gate_passed": True,
        "compatible_entities": [
            {"uuid": "6136ea6b-1699-46ec-8e8e-f60c8bb64310", "entity_type": "product", "code": product_code}
        ],
        "gate_debug": {"domain": "order"},
    }
    services = AnswerServices(
        mcp_probe=lambda name, args: {"has_result": False, "answers": []},
        family_fetch=lambda query: {"data": []},
    )
    payload = {"_exit_kind": "not_found", "result_type": "order", "items": [], "has_result": False}
    bridge_answer = answer_bridge.answer_for(
        payload,
        envelope={"raw_fragment": {"outcome": "not_found", "fetch": {"has_result": False}}},
        parser=parser,
        ctx={"contact": {"id": "zzt-s11-answerfor"}},
        canned=copy_mod.fallback_copy(),
        services=services,
        db=None,
        asked_at_turn=5,
        dry_run=True,
        carried_pending=None,
        profile=Profile(tier="office"),
    )
    assert bridge_answer is not None
    assert "escalate" not in bridge_answer.text.lower(), bridge_answer.text
    assert bridge_answer.question is None, (
        f"a staff contact's order miss must arm NO hidden team_pick at all: {bridge_answer.question!r}"
    )

    # ---- Shape 3: carried outstanding_detail pending (not a roster) + miss --------
    outstanding_detail = Pending(
        kind="outstanding_detail", expects=None, options=[], team=None,
        payload={"filters": {}}, asked_at_turn=1,
    )
    state3 = State(focus=Focus(), pending=outstanding_detail, profile=Profile(tier="office"), turn_no=6)
    answer3 = compose([_total_miss_envelope()], state3, _policy(), ctx=None)

    assert "escalate" not in answer3.text.lower(), answer3.text
    assert answer3.question is None or answer3.question.payload.get("escalate_offered") is not True, (
        f"no hidden escalate stamp for a non-roster carried pending either: {answer3.question!r}"
    )


def _build_policy_for_apply():
    from tests.chatbot._turn_helpers import build_policy

    return build_policy()


def test_dealer_carried_roster_miss_keeps_its_offer_text():
    """Hand pass 2 item 8's own rule: a DEALER contact with an OLD, already-answered
    roster (`product_pick`, not a question asked this turn) carried in, over a fresh
    miss, must still get the offer SENTENCE and the roster stays armed with
    `escalate_offered: True` - `clarifying_open = state.pending is not None` is
    over-broad in this direction too: it cannot tell "a roster still being asked"
    from "an old, fully-answered one just sitting on state", so it hides a dealer's
    legitimate offer the same way it (correctly) hides a staff one.
    """
    product_pick = Pending(
        kind="product_pick", expects=None,
        options=[{"position": 1, "label": "A"}, {"position": 2, "label": "B"}],
        team=None, payload={"answered_positions": [1, 2]}, asked_at_turn=1,
    )
    state = State(focus=Focus(), pending=product_pick, profile=Profile(tier="dealer"), turn_no=5)

    answer = compose([_total_miss_envelope()], state, _policy(), ctx=None)

    assert "Would you like me to escalate to warehouse team?" in answer.text, answer.text
    assert answer.question is not None and answer.question.payload.get("escalate_offered") is True, (
        f"the roster must stay armed with escalate_offered once the dealer offer is shown: {answer.question!r}"
    )


def test_dealer_kind_pick_asked_this_turn_gets_no_offer():
    """AC-S11-2 with a DEALER profile (not just office): a clarifying question
    ASKED THIS TURN (a fresh `kind_pick`) must get no offer - text AND the pending
    payload, which currently still gets `escalate_offered: True` stamped even though
    no sentence was shown for it.
    """
    kind_pick = Pending(
        kind="kind_pick", expects=None,
        options=[
            {"position": 1, "label": "Sorento (transporter)"},
            {"position": 2, "label": "Sorento (customer)"},
        ],
        team=None, payload={}, asked_at_turn=3,
    )
    state = State(focus=Focus(), pending=kind_pick, profile=Profile(tier="dealer"), turn_no=3)

    answer = compose([_total_miss_envelope()], state, _policy(), ctx=None)

    assert "escalate" not in answer.text.lower(), answer.text
    assert answer.question is not None and answer.question.payload.get("escalate_offered") is not True, (
        f"a kind pick asked THIS TURN must not be stamped escalate_offered either: {answer.question!r}"
    )


# --------------------------------------------------------------------------- #
# Phase 3 fix-round follow-up (26 Sep, coordinator round 4): a FIFTH site -
# `answer_bridge.answer_for` ~1667's own audience gate drops the WHOLE did-you-mean
# roster question for staff, not just the offer sentence riding on it, because a
# genuinely-ambiguous `product_pick` roster still gets `escalate_offered: True`
# stamped onto it (`test_rearch_r4_bridge_miss.py::TestDidYouMeanRosterMintsAProduct
# Pick::test_pending_kind_product_pick_domain_and_escalate_offered_carried` pins that
# stamp as correct/expected) - and the gate's OWN condition
# (`question.kind in pending.OFFER_KINDS or question.payload.get("escalate_offered")
# is True`) treats "carries the stamp" as reason enough to drop it, even though a
# roster kind (`pending.is_roster`) is a genuine clarifying question, not an
# escalation offer. Uses the reviewer's own fixture
# (`test_rearch_r4_bridge_miss.py::_dym_incoming_scenario`) rather than a second copy.
# --------------------------------------------------------------------------- #


def test_staff_did_you_mean_roster_stays_open_without_an_offer():
    """A staff contact's did-you-mean roster (an unplaced hyphenated incoming code,
    two fuzzy candidates) must still be ASKED - `answer.question` must not be
    `None` - with no `escalate_offered` stamp and no team riding on it, and the
    reply text must carry no "escalate" phrase at all.

    Red today: the whole question is dropped (`answer.question is None`) AND the
    text still ends "...or would you like me to escalate to purchasing team?" - the
    stamped-roster branch of the audience gate removes the QUESTION but nothing
    strips the SENTENCE the miss lane already built into `text` before the gate
    ever runs.
    """
    from app.services.chatbot import answer_bridge
    from app.services.chatbot.turn.state import Profile
    from tests.chatbot.test_rearch_r4_bridge_miss import _canned, _ctx_for, _dym_incoming_scenario

    parser, resolved, extra = _dym_incoming_scenario()
    gate = extra["gate"]
    services = extra["services"]
    payload = {"resolved": resolved, "gate": gate, "_exit_kind": "not_found"}

    answer = answer_bridge.answer_for(
        payload,
        envelope=None,
        parser=parser,
        ctx=_ctx_for(parser),
        canned=_canned(),
        services=services,
        db=None,
        asked_at_turn=3,
        profile=Profile(tier="office"),
    )

    assert answer is not None
    assert answer.question is not None, (
        "a did-you-mean roster is a clarifying question, not an escalation offer - "
        "it must still be asked for a staff contact"
    )
    assert answer.question.payload.get("escalate_offered") is not True, (
        f"no hidden escalate stamp on a staff contact's roster either: {answer.question!r}"
    )
    assert answer.question.team is None, (
        f"no team should ride on a roster nobody was offered escalation for: {answer.question!r}"
    )
    assert "escalate" not in answer.text.lower(), answer.text


def test_dealer_did_you_mean_roster_keeps_its_offer():
    """Guard (R6): the SAME scenario for a dealer profile is UNCHANGED - the roster
    stays armed, carrying its offer stamp and team, and the offer sentence still
    prints, exactly as on main. Must be GREEN today and stay green.
    """
    from app.services.chatbot import answer_bridge
    from app.services.chatbot.turn.state import Profile
    from tests.chatbot.test_rearch_r4_bridge_miss import _canned, _ctx_for, _dym_incoming_scenario

    parser, resolved, extra = _dym_incoming_scenario()
    gate = extra["gate"]
    services = extra["services"]
    payload = {"resolved": resolved, "gate": gate, "_exit_kind": "not_found"}

    answer = answer_bridge.answer_for(
        payload,
        envelope=None,
        parser=parser,
        ctx=_ctx_for(parser),
        canned=_canned(),
        services=services,
        db=None,
        asked_at_turn=3,
        profile=Profile(tier="dealer"),
    )

    assert answer is not None
    assert answer.question is not None
    assert answer.question.payload.get("escalate_offered") is True
    assert answer.question.team == "purchasing"
    assert "would you like me to escalate to purchasing team?" in answer.text.lower(), answer.text
