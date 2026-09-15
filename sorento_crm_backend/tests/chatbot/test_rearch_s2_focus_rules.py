"""S2 - the seven focus rules, ported as calls through `apply()` (AC-1525,
PLAN-chatbot-turn-rearch.md).

Scope note (tester's own call, flagged in the report): the source port
(`origin/feat/chatbot-focus:tests/chatbot/test_focus_rules.py`) has ~50 cases across
six rule classes, written against the OLD per-rule function API (`fr.replace_same_axis`,
`fr.Outputs`, `fr.Turn`, ...). This file writes ONE representative case per rule
(matching the captain's one-line description of each) through the NEW `apply()` entry
point instead of porting every old case - the old file's fine-grained edge cases (mixed
confident/unconfident entities, focus-trace entries, TTL decay, the legacy-session
projection) are a fuller port left for whenever the coder's replay corpus or a follow-up
slice exercises them; this file is the seven-rule skeleton the AC's one-liner asks for.

RIGHT NOW every test is RED with `ModuleNotFoundError: No module named
'app.services.chatbot.turn'`.
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import RESET_KEEPS, build_policy, entity, verdict


def _state(focus):
    from app.services.chatbot.turn.state import Profile, State

    return State(focus=focus, pending=None, profile=Profile())


def test_1_replace_same_axis_a_new_product_replaces_only_the_product():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    focus = Focus(products=[entity("SRTWC8517")], customers=[entity("ABC", hint="customer")])
    v = verdict(entities=[entity("SRTKS6091")])

    state2, _plan = apply(_state(focus), v, build_policy())

    assert [p["raw"] for p in state2.focus.products] == ["SRTKS6091"]
    assert [c["raw"] for c in state2.focus.customers] == ["ABC"]


def test_2_reset_on_topic_clears_all_but_reset_keeps():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    focus = Focus(
        products=[entity("SRTWC8517")],
        customers=[entity("ABC", hint="customer")],
        tier=["dealer"],
        brands=["sorento"],
    )
    # `topic_reset` is a v3 Verdict key (captain ruling, item 2, 16 Sep 2026).
    v = verdict(entities=[], topic_reset=True)

    state2, _plan = apply(_state(focus), v, build_policy())

    kept = {k for k in ("products", "customers", "tier", "brands") if getattr(state2.focus, k, None)}
    assert kept == RESET_KEEPS


def test_3_reuse_alive_a_continuation_inherits_what_it_did_not_restate():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    focus = Focus(products=[entity("SRTWC8517")], tier=["dealer"])
    v = verdict(entities=[], intent_hint="check_stock")

    state2, _plan = apply(_state(focus), v, build_policy())

    assert [p["raw"] for p in state2.focus.products] == ["SRTWC8517"]
    assert state2.focus.tier == ["dealer"]


def test_4_domains_from_asks_the_domain_moves_and_the_product_stays():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    focus = Focus(products=[entity("SRTWC8517")], domains=["inventory"])
    v = verdict(domain_hint="incoming")

    state2, _plan = apply(_state(focus), v, build_policy())

    assert state2.focus.domains == ["incoming"]
    assert [p["raw"] for p in state2.focus.products] == ["SRTWC8517"]


def test_5_date_restated_only_a_turn_with_no_date_word_gets_no_window():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    focus = Focus(date_window=None)
    v = verdict(date_mode=None, date_filter_start=None, date_filter_end=None)

    state2, _plan = apply(_state(focus), v, build_policy())

    assert state2.focus.date_window is None


def test_6_anaphora_reuses_the_alive_product_slot():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    focus = Focus(products=[entity("SRTWC8517")])
    v = verdict(entities=[], anaphora={"backward_reference": True})

    state2, _plan = apply(_state(focus), v, build_policy())

    assert [p["raw"] for p in state2.focus.products] == ["SRTWC8517"]


def test_7_confident_guard_an_unconfident_entity_never_replaces_an_alive_slot():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    focus = Focus(products=[entity("SRTWC8517")])
    v = verdict(entities=[entity("one siew srtkt72ss", confident=False)])

    state2, _plan = apply(_state(focus), v, build_policy())

    assert [p["raw"] for p in state2.focus.products] == ["SRTWC8517"]


def test_document_and_status_both_set_from_one_verdict():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    focus = Focus()
    v = verdict(document=["DO"], status="outstanding")

    state2, _plan = apply(_state(focus), v, build_policy())

    assert state2.focus.document == ["DO"]
    assert state2.focus.status == "outstanding"


def test_a_status_only_verdict_keeps_the_prior_document():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    focus = Focus(document=["DO"], status="outstanding")
    v = verdict(document=[], status="delivered")

    state2, _plan = apply(_state(focus), v, build_policy())

    assert state2.focus.document == ["DO"]
    assert state2.focus.status == "delivered"
