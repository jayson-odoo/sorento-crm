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
