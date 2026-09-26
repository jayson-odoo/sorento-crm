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
