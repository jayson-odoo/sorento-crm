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
