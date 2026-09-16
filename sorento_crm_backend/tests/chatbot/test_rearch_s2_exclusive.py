"""S2 - a message that names an entity but no domain/status word of its own REFINES
the standing subject: it combines across kinds and replaces only the axis it names
(AC-1524, PLAN-chatbot-turn-rearch.md, journey step 6: "SRT6536-DIY only").

Re-pinned 17 Sep 2026 (coder 20's landed change, `3c19a8533`,
`turn/decide.py::_subject_reading`'s own docstring): `scope_exclusive` is retired as
the discriminator - it asked the wrong question of the two turns it was introduced
for ("Outstsnding DO for 7445" and "For srtwc286 only" differ because the first names
a document AND a status, not because one carries an "only" marker). The real
discriminator is `domain_in_message` (does this message carry a domain/status word of
its own?) read alongside the entities, per the four-row table:

    | domain_in_message | entities | reading                                       |
    | true               | yes      | NEW_ASK - the domain's defaults plus what it  |
    |                    |          |   names; every other carried kind is dropped  |
    | true               | no       | a domain switch over the standing subject     |
    | false              | yes      | REFINE - combine across kinds, replace within |
    |                    |          |   the same kind                               |
    | false              | no       | the CARRY / ANSWER paths                      |

Every test here is the `false` + `yes` row: "SRT6536-DIY only", "BRW only", "IBORN
only" each name one entity and no domain/status word, so each REFINES - the kind
named replaces, every other kind stands. `scope_exclusive=True` (the retired field)
is no longer set in these verdicts; `domain_in_message=False` is what actually drives
the REFINE reading now, and the engine no longer reads `scope_exclusive` at all
(declared in the schema/prompt per the ruling, but dead).

RIGHT NOW every test is RED with `ModuleNotFoundError: No module named
'app.services.chatbot.turn'`.
"""
from __future__ import annotations

from tests.chatbot._turn_helpers import build_policy, entity, verdict


def _family_focus():
    """A customer family of 6 ledgers + one product, the journey-step-6 starting focus."""
    from app.services.chatbot.turn.state import Focus

    return Focus(
        customers=[{"raw": "chin chun", "hint": "customer", "family": True, "uuids": [f"c{i}" for i in range(6)]}],
        products=[entity("SRT6536-DIY")],
    )


def test_product_only_refine_narrows_product_and_keeps_customer_family():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Profile, State

    state = State(focus=_family_focus(), pending=None, profile=Profile())
    v = verdict(
        entities=[entity("SRT6536-DIY", hint="product")],
        domain_in_message=False,
    )

    state2, _plan = apply(state, v, build_policy())

    assert [p["raw"] for p in state2.focus.products] == ["SRT6536-DIY"]
    assert state2.focus.customers == state.focus.customers


def test_location_only_refine_keeps_products_and_customer():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Profile, State

    state = State(focus=_family_focus(), pending=None, profile=Profile())
    v = verdict(
        entities=[entity("BRW", hint="warehouse")],
        domain_in_message=False,
    )

    state2, _plan = apply(state, v, build_policy())

    assert state2.focus.products == state.focus.products
    assert state2.focus.customers == state.focus.customers


def test_customer_only_refine_keeps_products():
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Profile, State

    state = State(focus=_family_focus(), pending=None, profile=Profile())
    v = verdict(
        entities=[entity("IBORN", hint="customer")],
        domain_in_message=False,
    )

    state2, _plan = apply(state, v, build_policy())

    assert state2.focus.products == state.focus.products
