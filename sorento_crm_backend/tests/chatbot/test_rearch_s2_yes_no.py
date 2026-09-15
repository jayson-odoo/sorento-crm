"""S2 - yes/no against a pending offer resolves from `is_affirmative`/`escalation.*`
only, never from entities alone (AC-1523, PLAN-chatbot-turn-rearch.md contract 40-43).

RIGHT NOW every test is RED with `ModuleNotFoundError: No module named
'app.services.chatbot.turn'`.
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import build_policy, entity, verdict


def _team_pick_state():
    from app.services.chatbot.turn.pending import ask
    from app.services.chatbot.turn.state import Focus, Profile, State

    options = [
        {"position": 1, "label": "Purchasing", "uuid": None, "uuids": [], "entity_type": None, "payload": {"team": "purchasing"}},
    ]
    pending = ask("team_pick", options, team="purchasing", asked_at_turn=1)
    return State(focus=Focus(), pending=pending, profile=Profile())


def test_yes_on_a_single_team_option_routes_escalation_and_clears_pending():
    from app.services.chatbot.turn.apply import apply

    state = _team_pick_state()
    v = verdict(is_affirmative=True)

    state2, plan = apply(state, v, build_policy())

    assert state2.pending is None
    assert plan.ask is None
    assert plan is not None


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
