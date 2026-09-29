"""Phase 2 RED tests - issue #1262 (Samantha case), slice 7, finding F1b.

Turn T3/T4: a kind pick over "Sorento" (customer / transporter) is answered with
position 2 ("Dealer : Cheng Huat Sentul", read as picking option 2), and the bot
stores the printed label "Sorento (customer)" as the customer instead of re-typing
the raw word "Sorento" under the picked kind.

AC-S7-1: each kind-pick option carries the raw token and its kind; the label is
display only.
AC-S7-2: answering with a position re-types the word; "Sorento (customer)" never
lands in `raw`, `canonical_code` or `uuid`.

Plan: PLAN-chatbot-samantha-slices-26sep.md, slice 7. UAC:
chatbot-samantha-slices-26sep-acceptance-criteria.md.
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import build_policy, entity, verdict


def test_t4_kind_pick_options_carry_the_raw_token():
    """AC-S7-1. `turn/reconcile.py`'s two-kind-hit branch builds each option with a
    printed `label` ("Sorento (customer)") but no `raw` and no `code` - `turn/apply.py`'s
    pick arm then has nothing but the label to fall back to. Red: `option.get("raw")`
    is None, not "Sorento".
    """
    from app.services.chatbot.turn.reconcile import apply_reconciliation

    entities = [entity("Sorento", hint="customer")]
    resolved = {"Sorento": {"customer": 1, "transporter": 1}}

    result = apply_reconciliation(entities, resolved)

    assert result.kind_pick_options is not None
    assert len(result.kind_pick_options) == 2
    for option in result.kind_pick_options:
        assert option.get("raw") == "Sorento", (
            f"kind-pick option carries no raw token, only a printed label: {option!r}"
        )
        assert option.get("entity_type") in ("customer", "transporter")


def test_t4_kind_pick_answer_rewrites_hint_not_label():
    """AC-S7-2. Two turns: T3 arms the kind pick over "Sorento" (customer/transporter);
    T4 answers it with position 2 (`reference_positions: [2]`, the parser's own read of
    "Dealer : Cheng Huat Sentul"). The picked focus entity must carry `raw` "Sorento"
    and `hint` "customer" - never the printed label "Sorento (customer)" anywhere.

    Red today: `turn/apply.py`'s pick arm falls back to `option.get("label")` when
    neither `code` nor a uuid is on the option, so `focus.customers[0]["raw"]` and
    `["canonical_code"]` both come back as the label string.
    """
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=None, profile=Profile())
    v1 = verdict(domain_hint=None, entities=[entity("Sorento", hint="customer")])
    resolved = {"Sorento": {"customer": 1, "transporter": 1}}

    state1, plan1 = apply(state, v1, build_policy(), resolved=resolved)

    assert plan1.ask is not None and plan1.ask.kind == "kind_pick"

    state1 = State(focus=state1.focus, pending=plan1.ask, profile=state1.profile)
    v2 = verdict(reference_positions=[2])

    state2, _plan2 = apply(state1, v2, build_policy())

    assert state2.focus.customers, "the pick did not settle anything onto focus.customers"
    picked = state2.focus.customers[0]
    assert picked.get("raw") == "Sorento", picked
    assert picked.get("hint") == "customer", picked

    label = "Sorento (customer)"
    for field_name in ("raw", "canonical_code", "uuid"):
        assert picked.get(field_name) != label, (
            f"the printed pick label leaked into focus.customers[0][{field_name!r}]: {picked!r}"
        )


def test_n1_kind_pick_orders_by_resolver_hit_strength():
    """Fix lane round 2, N1: the options are ordered by a stated rule - the resolver's
    own hit count per kind, most hits first, ties alphabetical - never by a priority
    tuned to reproduce one transcript's numbering."""
    from app.services.chatbot.turn.reconcile import apply_reconciliation

    entities = [{"raw": "Sorento", "hint": "brand", "confident": True, "current_message": True}]
    stronger = apply_reconciliation(entities, {"Sorento": {"transporter": 1, "customer": 3}})
    assert [o["entity_type"] for o in stronger.kind_pick_options] == ["customer", "transporter"]
    tied = apply_reconciliation(entities, {"Sorento": {"transporter": 2, "customer": 2}})
    assert [o["entity_type"] for o in tied.kind_pick_options] == ["customer", "transporter"]
    reversed_strength = apply_reconciliation(entities, {"Sorento": {"customer": 1, "transporter": 4}})
    assert [o["entity_type"] for o in reversed_strength.kind_pick_options] == ["transporter", "customer"]
