"""S2 - yes/no against a pending offer resolves from `is_affirmative`/`escalation.*`
only, never from entities alone (AC-1523, PLAN-chatbot-turn-rearch.md contract 40-43).

RIGHT NOW every test is RED with `ModuleNotFoundError: No module named
'app.services.chatbot.turn'`.
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import build_policy, entity, verdict


def _team_pick_state(*, with_carried_focus: bool = False):
    from app.services.chatbot.turn.pending import ask
    from app.services.chatbot.turn.state import Focus, Profile, State

    options = [
        {"position": 1, "label": "Purchasing", "uuid": None, "uuids": [], "entity_type": None, "payload": {"team": "purchasing"}},
    ]
    pending = ask("team_pick", options, team="purchasing", asked_at_turn=1)
    focus = Focus()
    if with_carried_focus:
        # The browser-pass-3 shape (16 Sep 2026): the offer followed a real
        # business_query fetch, so the focus a "yes"/"1" answers against still
        # carries the domain and the customer that fetch resolved - `must_narrow_one`
        # is already satisfied (one customer), so a planner that does not
        # short-circuit here has something real to fetch, which is exactly what
        # reproduces the live bug (the identical prior answer re-runs) rather than
        # an empty-focus test that would pass on `plan.fetch == []` by accident.
        focus.domains = ["order"]
        focus.customers = [entity("HANLIM TRADING SDN BHD [A/C II]", hint="customer")]
    return State(focus=focus, pending=pending, profile=Profile())


class TestAnAcceptedOfferNeverFallsThroughToAFetch:
    """AC-1593 (browser pass 3, 16 Sep 2026, turns 3af6c1aa "yes" / 67fcbb6a "1"):
    `_answer_pending`'s accept branch (`is_affirmative is True` /
    `escalation.is_escalation_confirmation is True`) and the resolved-pick branch
    (`answers_open_question.resolved is True`) both clear the pending but return NO
    short-circuit plan, so `apply()`'s ordinary planner runs next over whatever focus
    the offer's own fetch left behind - on a live turn with a carried customer/domain,
    that is a full re-fetch of the identical prior answer, which is the exact defect
    both failing turns showed (byte-for-byte replay of the previous business_query
    reply, escalate offer re-asked, "yes" never reaching the escalation lane at all).

    The fix belongs in `apply.py::_answer_pending`, mirroring the DECLINE branch
    immediately below it (`escalation.get("escalation_declined") is True ...`, which
    already short-circuits `Plan(domains=[], fetch=[], ask=None, ...)` and sets
    `trace.lane = "escalation_declined"`) - an ACCEPT of an OFFER-kind pending needs
    the same shape, `trace.lane = "escalation"` (the existing `route.py::_LANE_BRANCH`
    entry, `"escalation": "out_of_scope"`, unchanged - this is not a new branch kind).
    The team itself needs no new plumbing: `engine.py` already calls
    `turn_runtime.lane_parse_output(verdict, ..., pending=state_in.pending, ...)` with
    the ORIGINAL (pre-apply) pending, and that function already reads
    `pending.team` for any `OFFER_KINDS` pending whose verdict named no team of its
    own (turn_runtime.py line ~393) - so once `route()` reaches the escalation arm at
    all, the team is already there.
    """

    def test_yes_short_circuits_to_escalation_with_no_fetch(self):
        from app.services.chatbot.turn.apply import apply

        state = _team_pick_state(with_carried_focus=True)
        v = verdict(is_affirmative=True)

        state2, plan = apply(state, v, build_policy())

        assert state2.pending is None
        assert plan.ask is None
        assert plan.fetch == [], "an accepted offer must never re-fetch the carried focus"
        assert plan.trace.lane == "escalation", plan.trace.lane

    def test_escalation_confirmation_short_circuits_to_escalation_with_no_fetch(self):
        from app.services.chatbot.turn.apply import apply

        state = _team_pick_state(with_carried_focus=True)
        v = verdict(
            escalation={"is_escalation_confirmation": True, "escalation_declined": None, "company_pick": None}
        )

        state2, plan = apply(state, v, build_policy())

        assert state2.pending is None
        assert plan.ask is None
        assert plan.fetch == [], "an accepted offer must never re-fetch the carried focus"
        assert plan.trace.lane == "escalation", plan.trace.lane

    def test_a_bare_pick_of_the_single_option_short_circuits_to_escalation_with_no_fetch(self):
        """Browser pass 3 turn 9 (`67fcbb6a`): a numbered "1" against the SAME
        single-option yes/no offer answers it as `reference_positions: [1]` - not
        `is_affirmative` - one EXPLICIT position, which is the mirror `_answer_offer`
        accepts for an `ESCALATION_OFFER_KINDS` pending (owner ruling, hand pass 3,
        `answers_open_question` retired; `_picked_positions`'s one-position-only rule
        for an escalation offer, `5b33fde02`)."""
        from app.services.chatbot.turn.apply import apply

        state = _team_pick_state(with_carried_focus=True)
        v = verdict(reference_positions=[1])

        state2, plan = apply(state, v, build_policy())

        assert state2.pending is None
        assert plan.ask is None
        assert plan.fetch == [], "a pick that resolves an OFFER must never re-fetch the carried focus"
        assert plan.trace.lane == "escalation", plan.trace.lane


def test_escalation_declined_clears_pending_and_asks_nothing():
    from app.services.chatbot.turn.apply import apply

    state = _team_pick_state()
    v = verdict(escalation={"is_escalation_confirmation": None, "escalation_declined": True, "company_pick": None})

    state2, plan = apply(state, v, build_policy())

    assert state2.pending is None
    assert state2.focus == state.focus
    assert plan.ask is None


def test_is_affirmative_false_with_own_entities_is_not_a_decline():
    """A "no" that carries its own entities updates focus instead of closing the offer -
    contract: "no" with own entities is not a decline."""
    from app.services.chatbot.turn.apply import apply

    state = _team_pick_state()
    v = verdict(
        is_affirmative=False,
        entities=[entity("SRTWC8517", hint="product")],
    )

    state2, _plan = apply(state, v, build_policy())

    products = getattr(state2.focus, "products", [])
    assert any(p.get("raw") == "SRTWC8517" for p in products), products
    assert state2.pending is not None, "an entity-bearing 'no' is not treated as a decline"


def test_an_answer_never_consumes_a_question_this_turn_will_ask():
    """A verdict that both answers the CURRENT pending and triggers a NEW ask (from
    narrowing) applies the answer, and the new ask - not a re-print of the old one -
    is what `plan.ask` carries."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.pending import ask
    from app.services.chatbot.turn.state import Focus, Profile, State

    options = [
        {"position": 1, "label": "Purchasing", "uuid": None, "uuids": [], "entity_type": None, "payload": {}},
    ]
    pending = ask("team_pick", options, team="purchasing", asked_at_turn=1)
    state = State(focus=Focus(), pending=pending, profile=Profile())

    v = verdict(
        is_affirmative=True,
        domain_hint="incoming",
        entities=[entity("wc286", hint="product", confident=True)],
    )

    state2, plan = apply(state, v, build_policy())

    assert state2.pending is None or plan.ask is not None
    if plan.ask is not None:
        assert plan.ask.kind != "team_pick"
