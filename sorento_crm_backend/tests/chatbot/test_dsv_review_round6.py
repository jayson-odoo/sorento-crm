"""Dealer stock verdict - review round 6 (live evidence Run 3, findings A and C to F).

`tests/chatbot/journeys/dealer-stock-verdict.EVIDENCE.md`, "Run 3 (6429a20e5)". One test
(or one parametrized table) per finding, each built from the REAL verdict the live trace
recorded for the failing turn, so the input is what production actually produced rather
than a shape invented here.

Style: hand-built `State`/verdict/`policy` through `apply()`, the same harness
`test_dsv_apply_tasks.py` and `test_dsv_review_round1.py` use.
"""
from __future__ import annotations

import pytest

from tests.chatbot._turn_helpers import build_policy, entity, verdict


def _state(focus, *, pending=None, turn_no=0):
    from app.services.chatbot.turn.state import Profile, State

    return State(focus=focus, pending=pending, profile=Profile(), turn_no=turn_no)


def _stock_task(*, slots, status="open", opened_at_turn=1, touched_at_turn=1, domain="inventory"):
    from app.services.chatbot.turn.task import Slot, Task

    return Task(
        kind="stock_qty",
        domain=domain,
        status=status,
        opened_at_turn=opened_at_turn,
        touched_at_turn=touched_at_turn,
        slots=tuple(Slot(key=k, label=l, value=v) for (k, l, v) in slots),
    )


def _slot_values(task):
    return {s.label: s.value for s in task.slots}


def _task_of_kind(focus, kind):
    for t in focus.tasks:
        if t.kind == kind:
            return t
    raise AssertionError(f"no {kind!r} task on focus.tasks: {focus.tasks}")


# --------------------------------------------------------------------------- #
# Finding A (D16): a quantity for SOME products never drops the others
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "message, named, quantity",
    [
        # Case B turn 2 (trace 340d4822): "make MHS1028 80" - a RESTATED quantity.
        ("make MHS1028 80", "MHS1028", 80),
        # Case C turn 2 (trace 264a7153): "MHS1028 60" - a RESTATEMENT that changes
        # nothing (the slot already holds 60), which must still not answer MHS1028
        # alone and close the question MSK11A-QT is still owed against.
        ("MHS1028 60", "MHS1028", 60),
    ],
)
def test_a_quantity_for_one_task_product_asks_for_the_rest_and_fetches_nothing(
    message, named, quantity
):
    """D16. Both live turns answered MHS1028 alone and closed the task, leaving
    MSK11A-QT - which the previous turn had explicitly asked for - unanswered and
    unasked. The merge keeps every slot; the turn's outcome is the question for what is
    still missing, and NO fetch: a verdict is never shown while a product still owes a
    quantity (D14)."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(
        slots=[("uuid-mhs", "MHS1028", 60), ("uuid-msk", "MSK11A-QT", None)]
    )
    focus = Focus(tasks=(task,), domains=["inventory"])
    v = verdict(
        domain_hint="inventory",
        entities=[entity(named, hint="product", quantity=quantity)],
    )

    state2, plan = apply(_state(focus, turn_no=2), v, build_policy())

    stock = _task_of_kind(state2.focus, "stock_qty")
    assert _slot_values(stock) == {"MHS1028": quantity, "MSK11A-QT": None}, (
        "the still-open product stays on the task"
    )
    assert plan.fetch == [], "no verdict is fetched while a product still owes a quantity"
    assert plan.trace.task_question == (
        f"Noted: MHS1028 x {quantity}. How many units do you need for MSK11A-QT?"
    )


def test_the_last_missing_quantity_fetches_the_whole_task():
    """The other half of the same rule: once NOTHING is missing the fetch runs, and it
    carries every slot and every quantity - including the ones stated turns ago."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(
        slots=[("uuid-mhs", "MHS1028", 60), ("uuid-msk", "MSK11A-QT", None)]
    )
    focus = Focus(tasks=(task,), domains=["inventory"])
    v = verdict(
        domain_hint="inventory",
        entities=[entity("MSK11A-QT", hint="product", quantity=110)],
    )

    state2, plan = apply(_state(focus, turn_no=2), v, build_policy())

    assert len(plan.fetch) == 1
    spec = plan.fetch[0]
    assert [e["uuid"] for e in spec.entities] == ["uuid-mhs", "uuid-msk"]
    assert spec.filters["requested_quantities"] == {"uuid-mhs": 60, "uuid-msk": 110}
    assert plan.trace.task_question is None


def test_proceed_anyway_still_fetches_with_a_slot_unanswered():
    """D15 is the one way a fetch happens with a product still missing: the dealer said
    to go ahead, so the missing ones are DROPPED (named in the reply) rather than asked
    for again."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(
        slots=[("uuid-mhs", "MHS1028", 60), ("uuid-msk", "MSK11A-QT", None)]
    )
    focus = Focus(tasks=(task,), domains=["inventory"])
    v = verdict(domain_hint="inventory", proceed_anyway=True, entities=[])

    _state2, plan = apply(_state(focus, turn_no=3), v, build_policy())

    assert len(plan.fetch) == 1
    assert plan.fetch[0].filters["requested_quantities"] == {"uuid-mhs": 60}
    assert plan.fetch[0].filters["not_checked"] == ["MSK11A-QT"]


# --------------------------------------------------------------------------- #
# Finding C (D29, re-ruled in review round 7): a quantity narrows to the exact code
# --------------------------------------------------------------------------- #


def _family(token="CB313"):
    """What the resolver hands `apply()` for ONE typed family-grouped code: the code
    itself plus its siblings, every row carrying the same typed `raw` (the live shape,
    trace e6459937 - `state_diff.products.after` listed all four)."""
    codes = ["CB313", "CB313A-NL", "CB313-NL", "CB313-L"]
    return {
        "product": [
            {
                "raw": token,
                "hint": "product",
                "canonical_code": code,
                "uuid": f"uuid-{code}",
                "current_message": True,
                "confident": True,
            }
            for code in codes
        ]
    }


def _entries(*codes, answered=()):
    return [
        {
            "product_id": f"uuid-{code}",
            "product_code": code,
            "product_name": code,
            "needs_quantity": code not in answered,
            "requested_qty": 1200 if code in answered else None,
            "available": None,
            "verdict": None,
            "running_low": None,
            "disclaimer": None,
        }
        for code in codes
    ]


def test_a_quantity_fetches_the_exact_code_and_not_its_siblings():
    """D29 (finding C, case H rows 5-8, trace e6459937). "stock for CB313 1200?" is one
    literal product code with one quantity; the resolver expanded it to the whole family
    and the reply answered four products, then asked for three quantities the dealer had
    never mentioned. A quantity is stated ABOUT a product, so the entity that carries one
    resolves to its exact code alone - one verdict line, nothing owed, no task."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    v = verdict(
        domain_hint="inventory",
        entities=[entity("CB313", hint="product", quantity=1200)],
    )

    _state2, plan = apply(
        _state(Focus(), turn_no=1), v, build_policy(), candidates=_family()
    )

    assert [e["canonical_code"] for e in plan.fetch[0].entities] == ["CB313"]


def test_the_same_ask_without_a_quantity_still_lists_the_family():
    """The other half, unchanged for everybody: "stock for CB313?" names no quantity, so
    the family stands, the reply answers all of them and the task collects a quantity
    per product (or the dealer says proceed)."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    v = verdict(domain_hint="inventory", entities=[entity("CB313", hint="product")])

    _state2, plan = apply(
        _state(Focus(), turn_no=1), v, build_policy(), candidates=_family()
    )

    assert [e["canonical_code"] for e in plan.fetch[0].entities] == [
        "CB313",
        "CB313A-NL",
        "CB313-NL",
        "CB313-L",
    ]


def test_a_family_prefix_with_no_exact_match_keeps_the_whole_family():
    """D29's escape hatch: "CB31" is not a product code of its own, so there is nothing
    exact to narrow to and the family is what the question was about - quantity or no
    quantity."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    v = verdict(
        domain_hint="inventory",
        entities=[entity("CB31", hint="product", quantity=1200)],
    )

    _state2, plan = apply(
        _state(Focus(), turn_no=1), v, build_policy(), candidates=_family(token="CB31")
    )

    assert len(plan.fetch[0].entities) == 4


def test_a_second_product_without_a_quantity_is_untouched_by_the_narrowing():
    """One sentence can do both: a quantity for one code narrows THAT code only, and a
    product named beside it with no quantity keeps every row the resolver placed."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    candidates = _family()
    candidates["product"] = candidates["product"] + [
        {
            "raw": "MHS1028",
            "hint": "product",
            "canonical_code": "MHS1028",
            "uuid": "uuid-mhs-mocha",
            "current_message": True,
            "confident": True,
        },
        {
            "raw": "MHS1028",
            "hint": "product",
            "canonical_code": "MHS1028",
            "uuid": "uuid-mhs-sorento",
            "current_message": True,
            "confident": True,
        },
    ]
    v = verdict(
        domain_hint="inventory",
        entities=[
            entity("CB313", hint="product", quantity=1200),
            entity("MHS1028", hint="product"),
        ],
    )

    _state2, plan = apply(
        _state(Focus(), turn_no=1), v, build_policy(), candidates=candidates
    )

    assert [e["uuid"] for e in plan.fetch[0].entities] == [
        "uuid-CB313",
        "uuid-mhs-mocha",
        "uuid-mhs-sorento",
    ], "both company rows of the code with no quantity stay; only the siblings go"


def test_the_task_holds_every_entry_the_block_answered():
    """Review round 7: with the narrowing done at the fetch, the SLOT seam is back to
    the backend's own rule (D25) - every entry in the reply becomes a slot, including a
    product this message did not name (the task's own products on a fill turn)."""
    from app.services.chatbot.turn.task import tasks_after_reply

    block = _entries("MHS1028", "MSK11A-QT", answered=("MHS1028",))

    tasks = tasks_after_reply((), [{"stock_availability": block}], turn_no=1)

    assert [s.label for s in tasks[0].slots] == ["MHS1028", "MSK11A-QT"]


# --------------------------------------------------------------------------- #
# Finding D (D13): a top-level demand_qty on the turn that OPENS the task
# --------------------------------------------------------------------------- #


def test_demand_qty_belongs_to_the_one_product_named_when_no_entity_carries_it():
    """Finding D, case H row 10 (trace 69b0ee35). "stock for CWC8315-NEW 75?" parsed
    with `entities[].quantity: null` and `demand_qty: 75` - the same sentence shape that
    parsed the other way one turn earlier. With exactly ONE product code named, the
    number can only be for that product, so the fetch carries it and the dealer is
    answered instead of asked again."""
    from app.services.chatbot.turn.plan import FetchSpec
    from app.services.chatbot.turn_runtime import _spec_quantities

    spec = FetchSpec(domain="inventory", entities=[], filters={}, date_window=None)
    out = {
        "entities": [{"raw": "CWC8315-NEW", "canonical_code": "CWC8315-NEW", "quantity": None}],
        "demand_qty": 75,
    }
    resolved = [{"uuid": "uuid-cwc", "code": "CWC8315-NEW", "canonical_code": "CWC8315-NEW"}]

    assert _spec_quantities(out, spec, resolved)["requested_quantities"] == {"uuid-cwc": 75}


def test_demand_qty_covers_every_company_variant_of_that_one_code():
    """One code, two companies, one product as far as the dealer is concerned (the same
    rule the backend's own per-code merge follows) - so the number is for both rows."""
    from app.services.chatbot.turn.plan import FetchSpec
    from app.services.chatbot.turn_runtime import _spec_quantities

    spec = FetchSpec(domain="inventory", entities=[], filters={}, date_window=None)
    out = {"entities": [{"raw": "MHS1028", "canonical_code": "MHS1028"}], "demand_qty": 60}
    resolved = [
        {"uuid": "uuid-mocha", "canonical_code": "MHS1028"},
        {"uuid": "uuid-sorento", "canonical_code": "MHS1028"},
    ]

    assert _spec_quantities(out, spec, resolved)["requested_quantities"] == {
        "uuid-mocha": 60,
        "uuid-sorento": 60,
    }


def test_demand_qty_is_not_guessed_across_two_named_products():
    """The same boundary the task's own bare-number fallback keeps (D13): with two
    products named, one number belongs to neither."""
    from app.services.chatbot.turn.plan import FetchSpec
    from app.services.chatbot.turn_runtime import _spec_quantities

    spec = FetchSpec(domain="inventory", entities=[], filters={}, date_window=None)
    out = {
        "entities": [
            {"raw": "MHS1028", "canonical_code": "MHS1028"},
            {"raw": "MSK11A-QT", "canonical_code": "MSK11A-QT"},
        ],
        "demand_qty": 60,
    }
    resolved = [
        {"uuid": "uuid-mhs", "canonical_code": "MHS1028"},
        {"uuid": "uuid-msk", "canonical_code": "MSK11A-QT"},
    ]

    assert "requested_quantities" not in _spec_quantities(out, spec, resolved)


def test_a_per_entity_quantity_still_wins_over_demand_qty():
    """The fallback fires only when no entity carried a quantity of its own."""
    from app.services.chatbot.turn.plan import FetchSpec
    from app.services.chatbot.turn_runtime import _spec_quantities

    spec = FetchSpec(domain="inventory", entities=[], filters={}, date_window=None)
    out = {
        "entities": [{"raw": "CWC8315-NEW", "canonical_code": "CWC8315-NEW", "quantity": 935}],
        "demand_qty": 75,
    }
    resolved = [{"uuid": "uuid-cwc", "canonical_code": "CWC8315-NEW"}]

    assert _spec_quantities(out, spec, resolved)["requested_quantities"] == {"uuid-cwc": 935}


# --------------------------------------------------------------------------- #
# Finding E (D21/D24): the fill fetches the TASK's domain, not the detour's
# --------------------------------------------------------------------------- #


def test_a_fill_after_a_detour_fetches_the_tasks_own_domain():
    """Finding E, case D turn 4 (trace c811446e): the fill turn planned
    `domains: ['incoming']` and called the incoming-shipment tool, because the detour
    before it left `incoming` on the focus and on the parser's own `domain_hint`. The
    task is the question being answered, so its domain is the turn's."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(
        slots=[("uuid-mhs", "MHS1028", None), ("uuid-msk", "MSK11A-QT", None)],
        status="parked",
    )
    focus = Focus(tasks=(task,), domains=["incoming"])
    v = verdict(
        domain_hint="incoming",
        entities=[
            entity("MHS1028", hint="product", quantity=60),
            entity("MSK11A-QT", hint="product", quantity=110),
        ],
    )

    state2, plan = apply(_state(focus, turn_no=4), v, build_policy())

    assert plan.domains == ["inventory"]
    assert [s.domain for s in plan.fetch] == ["inventory"]
    assert plan.fetch[0].filters["requested_quantities"] == {
        "uuid-mhs": 60,
        "uuid-msk": 110,
    }
    assert state2.focus.domains == ["inventory"]


# --------------------------------------------------------------------------- #
# Finding F (D22): resume by naming makes no tool call
# --------------------------------------------------------------------------- #


def test_naming_the_task_products_again_resumes_it_without_fetching():
    """Finding F, case E turn 3 (trace e1de83f8): "back to the stock check" made a real
    tool call for MSK11A-QT and lost the `Noted: MHS1028 x 60.` recap. The parser hands
    back the focus products as entities on a turn like this, and that alone must not
    turn a resume into a fetch: nothing new was named and no quantity was given, so the
    turn re-states what is noted and asks for what is still missing."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(
        slots=[("uuid-mhs", "MHS1028", 60), ("uuid-msk", "MSK11A-QT", None)],
        status="parked",
    )
    focus = Focus(tasks=(task,), domains=["promotion"])
    v = verdict(
        domain_hint="inventory",
        entities=[
            entity("MHS1028", hint="product"),
            entity("MSK11A-QT", hint="product"),
        ],
    )

    state2, plan = apply(_state(focus, turn_no=3), v, build_policy())

    assert plan.fetch == [], "a resume answers from the task, it does not call the tool"
    assert plan.trace.task_question == (
        "Noted: MHS1028 x 60. How many units do you need for MSK11A-QT?"
    )
    assert _task_of_kind(state2.focus, "stock_qty").status == "open"


def test_a_new_product_on_the_tasks_domain_is_still_a_fresh_ask():
    """The boundary: a product the task is NOT collecting for is a new question, not a
    resume, and it fetches as it always has."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(slots=[("uuid-mhs", "MHS1028", 60), ("uuid-msk", "MSK11A-QT", None)])
    focus = Focus(tasks=(task,), domains=["inventory"])
    v = verdict(domain_hint="inventory", entities=[entity("CB313", hint="product")])

    _state2, plan = apply(_state(focus, turn_no=3), v, build_policy())

    assert [s.domain for s in plan.fetch] == ["inventory"]
    assert plan.trace.task_question is None


# --------------------------------------------------------------------------- #
# Case F turn 3 (D23): a close clears the products with the task
# --------------------------------------------------------------------------- #


def test_closing_the_task_clears_the_products_it_was_about():
    """Case F turn 3 (trace b08b3dcb): "never mind the stock check" closed the task, but
    the products stayed on the focus (the parser hands them back as entities), so the
    bare "60" typed next re-asked the closed question. What the task was about goes with
    the task."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(slots=[("uuid-mhs", "MHS1028", None), ("uuid-msk", "MSK11A-QT", None)])
    focus = Focus(
        tasks=(task,),
        domains=["inventory"],
        products=[entity("MHS1028", hint="product", uuid="uuid-mhs")],
    )
    v = verdict(
        topic_reset=True,
        domain_hint="inventory",
        entities=[
            entity("MHS1028", hint="product"),
            entity("MSK11A-QT", hint="product"),
        ],
    )

    state2, _plan = apply(_state(focus, turn_no=4), v, build_policy())

    assert state2.focus.tasks == ()
    assert state2.focus.products == []


def test_a_reset_aimed_elsewhere_parks_and_keeps_the_products():
    """The boundary: a reset aimed at ANOTHER domain parks the task (D23), so what it is
    about has to survive with it."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(slots=[("uuid-mhs", "MHS1028", None)])
    focus = Focus(
        tasks=(task,),
        domains=["inventory"],
        products=[entity("MHS1028", hint="product", uuid="uuid-mhs")],
    )
    v = verdict(
        topic_reset=True,
        domain_hint="promotion",
        entities=[entity("MSK11A-QT", hint="product")],
    )

    state2, _plan = apply(_state(focus, turn_no=4), v, build_policy())

    assert _task_of_kind(state2.focus, "stock_qty").status == "parked"
    assert [e["raw"] for e in state2.focus.products] == ["MSK11A-QT"]


# --------------------------------------------------------------------------- #
# Finding B: the ask order, end to end from the lane's own serialiser
# --------------------------------------------------------------------------- #


def test_the_quantity_map_crosses_the_mcp_in_the_order_the_dealer_asked():
    """Finding B, case A/B turn 1: asked "stock for MWT5727SS-CR 5, MHS1028 60, ...",
    answered "Noted: MHS1028 x 60, MWT5727SS-CR x 5." - the products came back in a
    different order from the one they were named in. The lane sorted the map's keys
    before sending it, throwing away the only record of the asked order the fetch
    carries besides `product_ids` itself."""
    from app.services.chatbot.lanes.business import fetch as fetch_lane

    first = "6136ea6b-1699-46ec-8e8e-f60c8bb64310"
    second = "1136ea6b-1699-46ec-8e8e-f60c8bb64311"
    trigger = {
        "entities": [
            {"uuid": first, "entity_type": "product", "code": "MWT5727SS-CR"},
            {"uuid": second, "entity_type": "product", "code": "MHS1028"},
        ],
        "tool": "crm_inventory_stock_balance_list",
        "semantic_input": {
            "contact_id": "404285551",
            "space_id": "364817",
            "requested_quantities": {first: 5, second: 60},
        },
    }

    out = fetch_lane.entity_ids_transformer(trigger)

    assert out["product_ids"] == [first, second]
    assert out["requested_quantities"] == f'{{"{first}":5,"{second}":60}}'
