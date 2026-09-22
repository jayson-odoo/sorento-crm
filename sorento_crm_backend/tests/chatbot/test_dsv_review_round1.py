"""Dealer stock verdict - review round 1, the engine half.

One test per behaviour the reviewer and the security reviewer named, each written to
fail against the code as it stood before the fix (the red reason is in each docstring)
and to pass after it. The S3 suite (`test_dsv_apply_tasks.py`, `test_dsv_focus_tasks.py`,
`test_dsv_replay_sessions.py`) is untouched by this file.

Findings covered here:

* R-S2 - a turn that answers a task runs the SAME tail every other answering turn runs:
  the grant / `row.supported` gate inside `_narrow_and_plan`, the counted-set cursor
  clear, and `new_ask_closes_stale_roster`. The task fetch used to be an early return
  that skipped all three.
* R-S3 - "just proceed" with nothing noted closes the task, fetches nothing and says
  `Not checked: ...` once.
* R-S4 / SEC-N3 - a reply row with no `product_code` must not put a UUID in the reply
  or in the parser hint.
* R-S5 - a `task_pick` answer that applied nothing must re-ask, never fetch.
* SEC-S2 - an ask that named no product opens no task, and a task's slots and the
  sentences built from them are capped.
* SEC-N4 - a slot value that is not an int degrades to "not sent", never to a 400 on
  the whole fetch.
"""
from __future__ import annotations

from dataclasses import replace

from tests.chatbot._turn_helpers import build_policy, entity, verdict


def _state(focus, *, pending=None, turn_no=0, profile=None):
    from app.services.chatbot.turn.state import Profile, State

    return State(
        focus=focus,
        pending=pending,
        profile=profile if profile is not None else Profile(),
        turn_no=turn_no,
    )


def _stock_task(*, slots, status="open", not_checked=()):
    from app.services.chatbot.turn.task import Slot, Task

    return Task(
        kind="stock_qty",
        domain="inventory",
        status=status,
        opened_at_turn=1,
        touched_at_turn=1,
        slots=tuple(Slot(key=k, label=l, value=v) for (k, l, v) in slots),
        not_checked=tuple(not_checked),
    )


def _slot_values(task):
    return {s.key: s.value for s in task.slots}


def _availability_envelope(rows):
    return [{"domain": "inventory", "stock_availability": rows}]


# --------------------------------------------------------------------------- #
# R-S2: a task-answering turn runs the tail rules
# --------------------------------------------------------------------------- #


def test_task_fetch_closes_a_stale_roster_about_something_else():
    """R-S2. A `product_pick` armed two turns earlier, about a product this task is not
    collecting for, is a question the bot has finished asking; an answering turn closes
    it (`new_ask_closes_stale_roster`). RED before the fix: the task fetch returned its
    own Plan before that rule ran, so the stale roster survived and the dealer's next
    bare number answered IT instead of the task."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.pending import ask as pending_ask
    from app.services.chatbot.turn.state import Focus

    stale = pending_ask(
        "product_pick",
        [
            {
                "position": 1,
                "label": "ZZZ-OTHER-1",
                "code": "ZZZ-OTHER-1",
                "entity_type": "product",
                "uuid": "uuid-zzz",
            }
        ],
        asked_at_turn=1,
    )
    task = _stock_task(slots=[("uuid-c", "C", None)])
    focus = Focus(tasks=(task,))
    v = verdict(entities=[entity("C", hint="product", quantity=110)])

    state2, plan = apply(_state(focus, pending=stale, turn_no=3), v, build_policy())

    assert plan.fetch, "the filled task still fetches"
    assert state2.pending is None, (
        "a stale roster about another product must close on the turn that answers the "
        "task, the same as on any other answering turn"
    )


def test_task_fetch_clears_the_counted_set_cursor():
    """R-S2. `focus.set_page` is where a counted-set answer got to; any fetch that is
    not the next page of that set closes it, or a later "more" pages a set the customer
    has left. RED before the fix: the task fetch's early return skipped the clear."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(slots=[("uuid-c", "C", None)])
    focus = Focus(tasks=(task,), set_page={"set_key": {"domain": "inventory"}, "offset": 5})
    v = verdict(entities=[entity("C", hint="product", quantity=110)])

    state2, plan = apply(_state(focus), v, build_policy())

    assert plan.fetch
    assert state2.focus.set_page is None


def test_task_fetch_is_refused_when_the_domain_grant_is_revoked():
    """R-S2 / the grant gate. `_narrow_and_plan` refuses a domain this contact is not
    granted (`profile.grants` is a concrete list, so a domain absent from it is
    deny-by-default) - a rule the task fetch skipped entirely, so a revoked inventory
    grant still reached the stock tool. RED before the fix: `plan.fetch` was non-empty
    and `plan.denied` was empty."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus, Profile

    task = _stock_task(slots=[("uuid-c", "C", None)])
    focus = Focus(tasks=(task,))
    v = verdict(entities=[entity("C", hint="product", quantity=110)])

    state2, plan = apply(
        _state(focus, profile=Profile(grants=["promotion"])), v, build_policy()
    )

    assert plan.fetch == [], "a domain this contact is not granted is never fetched"
    assert plan.denied == ["inventory"]
    assert _slot_values(state2.focus.tasks[0]) == {"uuid-c": 110}, (
        "the quantity is still recorded - the refusal is about the READ, not about "
        "what the dealer said"
    )


def test_task_fetch_carries_the_task_slots_not_only_this_turns_entities():
    """R-S2, the half the rewire must not lose: the fetch is still the TASK's, so a
    turn that answers two of four products fetches all four with every quantity the
    dealer has given across turns."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(
        slots=[("uuid-a", "A", 5), ("uuid-b", "B", 60), ("uuid-c", "C", None), ("uuid-d", "D", None)]
    )
    focus = Focus(tasks=(task,))
    v = verdict(
        entities=[
            entity("C", hint="product", quantity=110),
            entity("D", hint="product", quantity=20),
        ]
    )

    _state2, plan = apply(_state(focus), v, build_policy())

    assert len(plan.fetch) == 1
    spec = plan.fetch[0]
    assert spec.domain == "inventory"
    assert [e["uuid"] for e in spec.entities] == ["uuid-a", "uuid-b", "uuid-c", "uuid-d"]
    assert spec.filters["requested_quantities"] == {
        "uuid-a": 5,
        "uuid-b": 60,
        "uuid-c": 110,
        "uuid-d": 20,
    }


# --------------------------------------------------------------------------- #
# R-S3: proceed with nothing noted
# --------------------------------------------------------------------------- #


def test_proceed_with_nothing_noted_closes_the_task_and_fetches_nothing():
    """R-S3 (reviewer ruling). "Just proceed" before any quantity was given leaves no
    product to ask about: the task is finished, nothing is fetched, and the reply is the
    single line naming what went unchecked. RED before the fix: the task survived with
    zero slots, printed an `Open task:` hint line forever, and `Not checked` was never
    said because the fetch it rode on never happened."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(slots=[("uuid-c", "C", None), ("uuid-d", "D", None)])
    focus = Focus(tasks=(task,))

    state2, plan = apply(_state(focus), verdict(proceed_anyway=True), build_policy())

    assert state2.focus.tasks == (), "an emptied task does not ride on"
    assert plan.fetch == [], "there is nothing left to look up"
    assert plan.trace.task_question == "Not checked: C and D."


def test_proceed_with_some_noted_still_fetches_and_names_the_rest():
    """R-S3's other half, unchanged: with something noted, the noted products ARE
    fetched and the dropped ones ride to the composer as `not_checked`."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.state import Focus

    task = _stock_task(slots=[("uuid-a", "A", 5), ("uuid-c", "C", None)])
    focus = Focus(tasks=(task,))

    _state2, plan = apply(_state(focus), verdict(proceed_anyway=True), build_policy())

    assert len(plan.fetch) == 1
    assert [e["uuid"] for e in plan.fetch[0].entities] == ["uuid-a"]
    assert plan.fetch[0].filters["not_checked"] == ["C"]


# --------------------------------------------------------------------------- #
# R-S4 / SEC-N3: no UUID ever reaches a person
# --------------------------------------------------------------------------- #


def test_a_reply_row_with_no_code_falls_back_to_the_name():
    """R-S4 / SEC-N3. RED before the fix: `str(row["product_id"])` was the label, so the
    uuid was printed in the question and in the parser hint."""
    from app.services.chatbot.turn.task import tasks_after_reply

    tasks = tasks_after_reply(
        (),
        _availability_envelope(
            [
                {
                    "product_id": "00000000-0000-0000-0000-0000000000a1",
                    "product_code": None,
                    "product_name": "Basin Mixer",
                    "needs_quantity": True,
                    "requested_qty": None,
                }
            ]
        ),
        turn_no=1,
    )

    assert [s.label for s in tasks[0].slots] == ["Basin Mixer"]


def test_a_reply_row_with_neither_code_nor_name_is_dropped():
    """R-S4 / SEC-N3: there is no way to ask a person about a row that has no name of
    any kind, so it is not collected for at all - never asked about by its uuid."""
    from app.services.chatbot.turn.task import tasks_after_reply

    tasks = tasks_after_reply(
        (),
        _availability_envelope(
            [
                {
                    "product_id": "00000000-0000-0000-0000-0000000000a1",
                    "product_code": None,
                    "product_name": None,
                    "needs_quantity": True,
                    "requested_qty": None,
                },
                {
                    "product_id": "00000000-0000-0000-0000-0000000000a2",
                    "product_code": "MHS1028",
                    "needs_quantity": True,
                    "requested_qty": None,
                },
            ]
        ),
        turn_no=1,
    )

    assert [s.label for s in tasks[0].slots] == ["MHS1028"]


# --------------------------------------------------------------------------- #
# R-S5: a tie answer that applied nothing
# --------------------------------------------------------------------------- #


def test_task_pick_that_applies_nothing_reasks_instead_of_fetching():
    """R-S5. `fill_value` applies the carried number only to a task with exactly ONE
    slot still owed; with two owed it applies nothing. RED before the fix: the turn
    fetched anyway, answering a question the dealer had not finished with the same gap
    it had before the pick."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.pending import ask as pending_ask
    from app.services.chatbot.turn.state import Focus
    from app.services.chatbot.turn.task import Task

    stock = _stock_task(slots=[("uuid-c", "C", None), ("uuid-d", "D", None)])
    idea = Task(kind="ideation", domain="ideate", status="open", opened_at_turn=1, touched_at_turn=1)
    tie = pending_ask(
        "task_pick",
        [
            {"position": 1, "label": "stock check", "entity_type": "task", "payload": {"task_kind": "stock_qty"}},
            {"position": 2, "label": "idea", "entity_type": "task", "payload": {"task_kind": "ideation"}},
        ],
        payload={"value": 110},
    )
    focus = Focus(tasks=(stock, idea))

    state2, plan = apply(
        _state(focus, pending=tie), verdict(reference_positions=[1]), build_policy()
    )

    assert plan.fetch == [], "nothing was applied, so there is nothing to look up"
    assert plan.trace.task_question == "How many units do you need for C and D?"
    assert state2.pending is None, "the tie itself is still settled"


# --------------------------------------------------------------------------- #
# SEC-S2: no task without a named product, and the caps
# --------------------------------------------------------------------------- #


def test_no_task_opens_when_the_ask_named_no_product():
    """SEC-S2. "What stock do you have?" names nothing, so the reply is a page of the
    CATALOGUE and every row of it carries `needs_quantity`. RED before the fix: a task
    opened with one slot per product (the tool's page cap is 5000) and echoed every code
    into the reply and into every later parser block."""
    from app.services.chatbot.turn.task import tasks_after_reply

    rows = [
        {
            "product_id": f"00000000-0000-0000-0000-{index:012d}",
            "product_code": f"ZZT-{index}",
            "needs_quantity": True,
            "requested_qty": None,
        }
        for index in range(40)
    ]

    assert tasks_after_reply((), _availability_envelope(rows), named_products=False) == ()


def test_an_already_open_task_is_still_updated_when_this_turn_named_nothing():
    """SEC-S2's carve-out: a task that is already open named its products when it
    opened, so a later turn that names none of them (a bare "proceed", a resume) still
    updates it."""
    from app.services.chatbot.turn.task import tasks_after_reply

    task = _stock_task(slots=[("uuid-a", "A", None)])
    rows = [
        {"product_id": "uuid-a", "product_code": "A", "needs_quantity": False, "requested_qty": 5},
        {"product_id": "uuid-b", "product_code": "B", "needs_quantity": True, "requested_qty": None},
    ]

    tasks = tasks_after_reply((task,), _availability_envelope(rows), named_products=False)

    assert _slot_values(tasks[0]) == {"uuid-a": 5, "uuid-b": None}


def test_slots_are_capped_and_the_sentences_count_the_rest():
    """SEC-S2. A reply naming more products than the cap collects for the first
    `MAX_SLOTS` of them, and the sentences enumerate at most `MAX_NAMED` with the rest
    counted - never a reply that lists forty codes."""
    from app.services.chatbot.turn.task import MAX_NAMED, MAX_SLOTS, TASK_KINDS, tasks_after_reply

    rows = [
        {
            "product_id": f"uuid-{index}",
            "product_code": f"ZZT-{index}",
            "needs_quantity": True,
            "requested_qty": None,
        }
        for index in range(40)
    ]

    tasks = tasks_after_reply((), _availability_envelope(rows), named_products=True)

    assert len(tasks[0].slots) == MAX_SLOTS
    question = TASK_KINDS["stock_qty"].question(tasks[0])
    assert f"and {MAX_SLOTS - MAX_NAMED} others" in question
    assert "ZZT-19" not in question
    hint = TASK_KINDS["stock_qty"].hint(tasks[0])
    assert f"and {MAX_SLOTS - MAX_NAMED} others" in hint


# --------------------------------------------------------------------------- #
# SEC-N4: a slot value that is not an int
# --------------------------------------------------------------------------- #


def test_a_non_integer_slot_value_never_reaches_the_tool_args():
    """SEC-N4. A session row written by an older build (or by hand) can carry anything
    JSON can hold. `requested_quantities` is validated at the ROUTE, where one bad value
    is a 400 that kills the whole fetch - so a value that cannot be a quantity is simply
    not sent, and the backend answers `needs_quantity` for that product, which is the
    truth. A digit string is a quantity and still counts."""
    from app.services.chatbot.turn.task import TASK_KINDS

    task = _stock_task(
        slots=[("uuid-a", "A", "5"), ("uuid-b", "B", "lots"), ("uuid-c", "C", {"n": 1})]
    )

    spec = TASK_KINDS["stock_qty"].to_fetch(task)

    assert spec.filters["requested_quantities"] == {"uuid-a": 5}


def test_a_non_integer_slot_value_is_coerced_at_the_runtime_seam_too():
    """SEC-N4's second half: `turn_runtime._spec_quantities` is the LAST seam before the
    value becomes a query param, and a spec built by hand must not be able to 400 the
    fetch either."""
    from app.services.chatbot.turn.plan import FetchSpec
    from app.services.chatbot.turn_runtime import _spec_quantities

    spec = FetchSpec(
        domain="inventory",
        entities=[],
        filters={"requested_quantities": {"uuid-a": "5", "uuid-b": "lots"}},
        date_window=None,
    )

    out = _spec_quantities({"entities": []}, spec, [])

    assert out["requested_quantities"] == {"uuid-a": 5}
