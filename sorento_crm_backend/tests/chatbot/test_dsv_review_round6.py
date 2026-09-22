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


def _family():
    """What the resolver hands `apply()` for ONE typed family-grouped code: the code
    itself plus its siblings (live trace e6459937 / 05ae3025 listed all four).

    Review round 8 - the ROW SHAPE matters and round 7's fixture had it wrong: a
    candidate row carries its OWN code under every name, never the token the customer
    typed (`turn_runtime.candidates_by_kind` builds `{"raw": code, "canonical_code":
    code, ...}`). With `raw` set to the typed token instead, round 7's rule passed its
    unit test and did nothing in production."""
    codes = ["CB313", "CB313A-NL", "CB313-NL", "CB313-L"]
    return {
        "product": [
            {
                "raw": code,
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
        _state(Focus(), turn_no=1), v, build_policy(), candidates=_family()
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
#
# Review round 9 moved this rule to ONE seam - `turn/apply.py::_normalise_demand_qty`,
# which runs before the task step, the narrowing and the fetch - and deleted the copy
# that lived in `turn_runtime._spec_quantities`. These four tests moved with it: same
# scenarios, same boundaries, now graded on the plan the turn actually produces.
# --------------------------------------------------------------------------- #


def _fetch_quantities(v, candidates):
    """The quantities the TOOL CALL ends up carrying, through the real two-step path:
    `apply()` normalises the verdict (review round 9) and `turn_runtime._spec_quantities`
    maps the per-entity quantity onto the uuids the resolver placed - the same order
    production runs them in (`engine.py` builds `lane_parse_output` off the verdict
    `apply()` has just normalised)."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus
    from app.services.chatbot.turn_runtime import _spec_quantities

    plan = apply(_state(Focus(), turn_no=1), v, build_policy(), candidates=candidates)[1]
    spec = plan.fetch[0]
    out = _spec_quantities({"entities": v.get("entities")}, spec, spec.entities)
    return out.get("requested_quantities")


def _candidate(code, uuid):
    return {
        "raw": code,
        "hint": "product",
        "canonical_code": code,
        "uuid": uuid,
        "current_message": True,
        "confident": True,
    }


def test_demand_qty_belongs_to_the_one_product_named_when_no_entity_carries_it():
    """Finding D, case H row 10 (trace 69b0ee35). "stock for CWC8315-NEW 75?" parsed
    with `entities[].quantity: null` and `demand_qty: 75` - the same sentence shape that
    parsed the other way one turn earlier. With exactly ONE product code named, the
    number can only be for that product, so the fetch carries it and the dealer is
    answered instead of asked again."""
    quantities = _fetch_quantities(
        verdict(
            domain_hint="inventory",
            demand_qty=75,
            entities=[entity("CWC8315-NEW", hint="product")],
        ),
        {"product": [_candidate("CWC8315-NEW", "uuid-cwc")]},
    )

    assert quantities == {"uuid-cwc": 75}


def test_demand_qty_covers_every_company_variant_of_that_one_code():
    """One code, two companies, one product as far as the dealer is concerned (the same
    rule the backend's own per-code merge follows) - so the number is for both rows."""
    quantities = _fetch_quantities(
        verdict(
            domain_hint="inventory",
            demand_qty=60,
            entities=[entity("MHS1028", hint="product")],
        ),
        {
            "product": [
                _candidate("MHS1028", "uuid-mocha"),
                _candidate("MHS1028", "uuid-sorento"),
            ]
        },
    )

    assert quantities == {"uuid-mocha": 60, "uuid-sorento": 60}


def test_demand_qty_is_not_guessed_across_two_named_products():
    """The same boundary the task's own bare-number fallback keeps (D13): with two
    products named, one number belongs to neither."""
    quantities = _fetch_quantities(
        verdict(
            domain_hint="inventory",
            demand_qty=60,
            entities=[
                entity("MHS1028", hint="product"),
                entity("MSK11A-QT", hint="product"),
            ],
        ),
        {
            "product": [
                _candidate("MHS1028", "uuid-mhs"),
                _candidate("MSK11A-QT", "uuid-msk"),
            ]
        },
    )

    assert quantities is None


def test_a_per_entity_quantity_still_wins_over_demand_qty():
    """The normalisation fires only when no entity carried a quantity of its own."""
    quantities = _fetch_quantities(
        verdict(
            domain_hint="inventory",
            demand_qty=75,
            entities=[entity("CWC8315-NEW", hint="product", quantity=935)],
        ),
        {"product": [_candidate("CWC8315-NEW", "uuid-cwc")]},
    )

    assert quantities == {"uuid-cwc": 935}


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


# --------------------------------------------------------------------------- #
# Review round 8, finding 3 (D23): "never mind" closes the task beside an offer
# --------------------------------------------------------------------------- #


def test_never_mind_closes_the_task_even_when_an_escalation_offer_is_open():
    """Live evidence Run 4, case F turn 2 (trace 15126963). The reply before it ended
    with "Would you like me to escalate to purchasing team?", so BOTH an escalation
    offer and the stock task were live. "never mind the stock check" parsed exactly as
    the close rule needs it - `topic_reset: true`, `domain_hint: "inventory"`,
    `is_affirmative: false`, no entities (verdict read from the trace) - but the turn
    routed `escalation_declined` and the task came out of it still `open` with both
    slots empty, so the bare "60" typed next re-opened the closed question.

    The decline owns the REPLY; it does not own the task. The task step has already run
    by the time the offer is answered, and its answer must not be thrown away with the
    rest of the turn."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.pending import ask as pending_ask
    from app.services.chatbot.turn.state import Focus

    offer = pending_ask(
        "team_pick",
        [
            {
                "position": 1,
                "label": "purchasing",
                "entity_type": "team",
                "payload": {"team": "purchasing"},
            }
        ],
        asked_at_turn=1,
    )
    task = _stock_task(
        slots=[("uuid-mhs", "MHS1028", None), ("uuid-msk", "MSK11A-QT", None)]
    )
    focus = Focus(
        tasks=(task,),
        domains=["inventory"],
        products=[entity("MHS1028", hint="product", uuid="uuid-mhs")],
    )
    v = verdict(
        topic_reset=True,
        domain_hint="inventory",
        is_affirmative=False,
        entities=[],
        user_goal="trying to cancel the stock check",
    )

    state2, plan = apply(_state(focus, pending=offer, turn_no=2), v, build_policy())

    assert plan.trace.lane == "escalation_declined", "the decline still owns the reply"
    assert state2.focus.tasks == (), "and the stock check is over"
    assert state2.focus.products == [], "what it was about goes with it (D23)"


def test_a_plain_decline_with_no_topic_reset_leaves_the_task_alone():
    """The boundary: "no thanks" answers the OFFER and says nothing about the stock
    check, so the task rides on exactly as it was."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.pending import ask as pending_ask
    from app.services.chatbot.turn.state import Focus

    offer = pending_ask(
        "team_pick",
        [
            {
                "position": 1,
                "label": "purchasing",
                "entity_type": "team",
                "payload": {"team": "purchasing"},
            }
        ],
        asked_at_turn=1,
    )
    task = _stock_task(slots=[("uuid-mhs", "MHS1028", 60), ("uuid-msk", "MSK11A-QT", None)])
    focus = Focus(tasks=(task,), domains=["inventory"])
    v = verdict(is_affirmative=False, entities=[])

    state2, plan = apply(_state(focus, pending=offer, turn_no=2), v, build_policy())

    assert plan.trace.lane == "escalation_declined"
    stock = _task_of_kind(state2.focus, "stock_qty")
    assert _slot_values(stock) == {"MHS1028": 60, "MSK11A-QT": None}


# --------------------------------------------------------------------------- #
# Review round 9, finding 4: a bare number with nothing open plans no fetch
# --------------------------------------------------------------------------- #


def test_a_bare_number_with_no_task_and_no_product_plans_nothing():
    """Live evidence Run 5, case F turn 3 (trace cfcca4a8), the most severe finding of
    the pass. After "never mind the stock check" closed the task and cleared the
    products, a bare "60" parsed as `demand_qty: 60`, `domain_hint: "inventory"`,
    `entities: []` (verdict read off the trace) and `decide()` read it as a CARRY that
    answered nothing - yet the turn still planned an inventory fetch with no product
    filter at all, so the tool's own "no filter = every product" default answered with a
    catalogue page and the dealer was asked to quantify ~50 products they had never
    mentioned.

    Nothing was named, nothing is open, and there is nothing carried to re-answer: the
    turn has nothing to look up. Same shape as `idle_chat_plans_nothing`, for the same
    reason."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    focus = Focus(domains=["inventory"])
    v = verdict(
        domain_hint="inventory",
        intent_hint="check_stock",
        demand_qty=60,
        entities=[],
        user_goal="trying to set the quantity to 60 for the current stock task",
    )

    _state2, plan = apply(_state(focus, turn_no=3), v, build_policy())

    assert plan.fetch == [], "a catalogue-wide stock fetch is not an answer to '60'"
    assert plan.ask is None


def test_an_open_task_still_answers_a_bare_number():
    """The boundary that must not move: with a task open, the same bare number is the
    D13 fallback's own input and the task still drives its fetch."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(slots=[("uuid-mhs", "MHS1028", None)])
    focus = Focus(tasks=(task,), domains=["inventory"])
    v = verdict(domain_hint="inventory", demand_qty=60, entities=[])

    _state2, plan = apply(_state(focus, turn_no=3), v, build_policy())

    assert [s.domain for s in plan.fetch] == ["inventory"]
    assert plan.fetch[0].filters["requested_quantities"] == {"uuid-mhs": 60}


def test_a_carried_product_still_answers_a_bare_number():
    """The other boundary: the products axis still carries what the conversation is
    about, so the fetch is scoped and the turn is answerable. Only the UNSCOPED fetch is
    refused."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    focus = Focus(
        domains=["inventory"],
        products=[entity("MHS1028", hint="product", uuid="uuid-mhs")],
    )
    v = verdict(domain_hint="inventory", demand_qty=60, entities=[])

    _state2, plan = apply(_state(focus, turn_no=3), v, build_policy())

    assert [s.domain for s in plan.fetch] == ["inventory"]
    assert [e["canonical_code"] for e in plan.fetch[0].entities] == ["MHS1028"]


# --------------------------------------------------------------------------- #
# Review round 9, finding 5: demand_qty is normalised before the narrowing (D13)
# --------------------------------------------------------------------------- #


def _cb313_plan(v):
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    return apply(_state(Focus(), turn_no=1), v, build_policy(), candidates=_family())[1]


def test_both_parse_shapes_of_one_quantified_code_plan_the_same_fetch():
    """Finding 5, case H rows 5 and 6 (traces 05ae3025 and 17bdb411): the SAME sentence
    shape parsed two ways one turn apart - "CB313 1200" put the number on
    `entities[].quantity`, "CB313 361" put it on the top-level `demand_qty`. D29's
    narrowing read only the per-entity field, so the second shape fetched the whole
    family again. With exactly one product code named the two are the same statement, so
    the verdict is normalised once, before anything reads it."""
    per_entity = _cb313_plan(
        verdict(
            domain_hint="inventory",
            entities=[entity("CB313", hint="product", quantity=361)],
        )
    )
    top_level = _cb313_plan(
        verdict(
            domain_hint="inventory",
            demand_qty=361,
            entities=[entity("CB313", hint="product")],
        )
    )

    assert [e["canonical_code"] for e in per_entity.fetch[0].entities] == ["CB313"]
    assert [e["canonical_code"] for e in top_level.fetch[0].entities] == ["CB313"]
    assert (
        top_level.fetch[0].filters == per_entity.fetch[0].filters
    ), "the two shapes are one statement and plan one fetch"


def test_demand_qty_is_not_spread_over_two_named_codes():
    """The boundary D13 already keeps everywhere else: two codes named, one number - it
    belongs to neither, and the family narrowing does not fire either."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    candidates = _family()
    candidates["product"] = candidates["product"] + [
        {
            "raw": "MHS1028",
            "hint": "product",
            "canonical_code": "MHS1028",
            "uuid": "uuid-mhs",
            "current_message": True,
            "confident": True,
        }
    ]
    v = verdict(
        domain_hint="inventory",
        demand_qty=361,
        entities=[entity("CB313", hint="product"), entity("MHS1028", hint="product")],
    )

    _state2, plan = apply(_state(Focus(), turn_no=1), v, build_policy(), candidates=candidates)

    assert len(plan.fetch[0].entities) == 5, "nothing narrowed, nothing quantified"
    assert "requested_quantities" not in plan.fetch[0].filters


def test_no_task_opens_when_the_only_named_code_was_answered():
    """Finding 6: the stray four-slot CB313 task Run 5 saw riding into the next row's
    turn was the family expansion's own doing. With the fetch narrowed, the reply
    answers the one code, nothing is owed and no task opens."""
    from app.services.chatbot.turn.task import tasks_after_reply

    block = _entries("CB313", answered=("CB313",))

    assert tasks_after_reply((), [{"stock_availability": block}], turn_no=1) == ()


# --------------------------------------------------------------------------- #
# Review round 9, finding 7: no cross-domain boilerplate on an availability reply
# --------------------------------------------------------------------------- #


def _availability_envelope(codes):
    return {
        "has_result": True,
        "intro": "Sorry, we do not have enough stock for that quantity.",
        "items": [{"title": f"{code} x 180: Not available.", "fields": []} for code in codes],
        "stock_availability": [
            {
                "product_id": f"uuid-{code}",
                "product_code": code,
                "product_name": code,
                "needs_quantity": False,
                "requested_qty": 180,
                "available": False,
                "verdict": "not_available",
                "running_low": False,
                "disclaimer": {
                    "sources": ["purchase"],
                    "limited": True,
                    "incoming_eta": None,
                    "purchase_eta_days": 90,
                },
            }
            for code in codes
        ],
    }


def test_the_crossdomain_probe_does_not_run_on_an_availability_reply():
    """Finding 7, case H rows 7 and 8. The verdict line was exactly right
    ("SRT392-24 x 180: Not available, but there is limited purchase, ETA in 90 days.")
    and the reply then appended the cross-domain probe's own boilerplate - "No stock and
    no incoming for SRT392-24, but PO is placed:..." - a sentence about our stock and our
    incoming, which is precisely what the dealer mode exists not to say (D17) and what
    the verdict line has already answered in the dealer's own terms."""
    from app.services.chatbot.lanes.business.answer import crossdomain_zeroset

    out = crossdomain_zeroset(
        _availability_envelope(["SRT392-24"]),
        parser={"domain_hint": "inventory", "message_type": "business_query"},
        resolved={
            "tokens": ["SRT392-24"],
            "resolutions": [
                {
                    "token": "SRT392-24",
                    "matches": [
                        {
                            "entity_type": "product",
                            "canonical_code": "SRT392-24",
                            "uuid": "uuid-SRT392-24",
                            "match_tier": "exact",
                        }
                    ],
                }
            ],
        },
        session_block=None,
    )

    assert out["_xd"]["active"] is False
    assert out["_xd"]["why"] == "stock_availability"


def test_a_detailed_stock_reply_still_runs_the_crossdomain_probe():
    """The boundary: only the DEALER block turns it off. A staff / detailed answer with
    nothing found is exactly what the probe exists for, and it is untouched."""
    from app.services.chatbot.lanes.business.answer import crossdomain_zeroset

    out = crossdomain_zeroset(
        {"has_result": False, "items": [], "intro": "No matching results found."},
        parser={"domain_hint": "inventory", "message_type": "business_query"},
        resolved={
            "tokens": ["SRT392-24"],
            "resolutions": [
                {
                    "token": "SRT392-24",
                    "matches": [
                        {
                            "entity_type": "product",
                            "canonical_code": "SRT392-24",
                            "uuid": "uuid-SRT392-24",
                            "match_tier": "exact",
                        }
                    ],
                }
            ],
        },
        session_block=None,
    )

    assert out["_xd"]["active"] is True


# --------------------------------------------------------------------------- #
# Review round 10: no cross-domain LADDER on an availability reply either
# --------------------------------------------------------------------------- #
#
# Live evidence Run 6, turn 9c1b634c (case H row 7, "SRT392-24 180"): the lane's own
# envelope was already right - `lane_text` read exactly "Sorry, we do not have enough
# stock for that quantity. 1. SRT392-24 x 180: Not available, but there is limited
# purchase, ETA in 90 days." with a one-entry `stock_availability` block - and the reply
# the dealer received then carried "No stock and no incoming for SRT392-24, but PO is
# placed: *Product Code:* SRT392-24 ... Would you like me to escalate to purchasing
# team?" appended after it.
#
# Round 9 gated `crossdomain_zeroset`. This block comes from the ladder's PO rung, run
# through the HIT bridge (`answer_bridge.apply_crossdomain_hit`), which rebuilds the
# item it hands the ladder as `{"answers": envelope["figures"]}` - dropping the
# availability block, so round 9's gate never saw it.


def _availability_hit_envelope():
    return {
        "figures": [
            {
                "title": "SRT392-24 x 180: Not available, but there is limited purchase, ETA in 90 days.",
                "fields": [],
            }
        ],
        "stock_availability": [
            {
                "product_id": "uuid-srt",
                "product_code": "SRT392-24",
                "product_name": "SRT392-24",
                "needs_quantity": False,
                "requested_qty": 180,
                "available": False,
                "verdict": "not_available",
                "running_low": False,
                "disclaimer": {
                    "sources": ["purchase"],
                    "limited": True,
                    "incoming_eta": None,
                    "purchase_eta_days": 90,
                },
            }
        ],
    }


def _ladder_probe():
    from app.services.chatbot.lanes.business.services import AnswerServices

    calls: list[str] = []

    def mcp_probe(name, args):
        calls.append(name)
        return {
            "answers": [
                {"fields": [{"label": "Product Code", "value": "SRT392-24"}, {"label": "Qty", "value": "300"}]}
            ],
            "has_result": True,
        }

    return AnswerServices(mcp_probe=mcp_probe, family_fetch=lambda q: {"data": []}), calls


def _run_hit_bridge(envelope):
    from app.services.chatbot import answer_bridge
    from app.services.chatbot.turn import compose as turn_compose

    services, calls = _ladder_probe()
    answer = turn_compose.Answer(
        text=(
            "Sorry, we do not have enough stock for that quantity.\n\n"
            "1. SRT392-24 x 180: Not available, but there is limited purchase, ETA in 90 days."
        )
    )
    out = answer_bridge.apply_crossdomain_hit(
        answer,
        envelope=envelope,
        parser={"domain_hint": "inventory", "message_type": "business_query", "routing": {}},
        resolved={
            "tokens": ["SRT392-24"],
            "resolutions": [
                {
                    "token": "SRT392-24",
                    "matches": [
                        {
                            "entity_type": "product",
                            "canonical_code": "SRT392-24",
                            "uuid": "uuid-srt",
                            "match_tier": "exact",
                        }
                    ],
                }
            ],
        },
        entities_names=[],
        crossdomain_ladder={"inventory": ["incoming", "purchase_order"]},
        ctx={"session": {"session_vars": {"variables": {}}}, "access": {"attributes": []}},
        services=services,
        contact_id="404285551",
        space_id="364817",
        asked_at_turn=1,
    )
    return answer, out, calls


def test_no_ladder_rung_runs_on_an_availability_reply():
    """D17: the verdict lines are the whole answer. No rung is probed, nothing is listed
    beside the verdict, and no escalate offer is minted to compete with the dealer's own
    open stock task (the shape Run 4's case F turned into a lost never-mind)."""
    answer, out, calls = _run_hit_bridge(_availability_hit_envelope())

    assert calls == [], "the ladder must not probe at all on a dealer reply"
    assert out.text == answer.text, "the verdict line is the whole answer"
    assert out.question is None, "and no escalation is offered beside it"


def test_a_detailed_zero_stock_reply_still_climbs_the_ladder():
    """The boundary: a staff / detailed answer whose rows read zero is exactly what the
    ladder exists for, and it is untouched."""
    detailed = {
        "figures": [
            {
                "fields": [
                    {"label": "Product Code", "value": "SRT392-24"},
                    {"label": "Quantity On Hand", "value": "0"},
                ]
            }
        ]
    }

    answer, out, calls = _run_hit_bridge(detailed)

    assert calls, "a detailed zero-stock hit still probes the other domain"
    assert out.text != answer.text
