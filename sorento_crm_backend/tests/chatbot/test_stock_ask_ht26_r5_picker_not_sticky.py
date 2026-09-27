"""Owner ruling 26 Sep 2026 ~08:25Z, PR #1247 (round 5): "for stock ask, the gist is
let's make the picker not sticky".

The stock ask's which-one pick closes the moment one product is picked from it, and is
forgotten for position resolution: no roster is kept open, nothing carries the list
forward on the stock task, and the parser is not taught that a number can point back
into it. A later bare number is a quantity (the answered product's quantity is revised),
never a pick. A new "check stock <code>" starts a new pick.

Replays the owner's five turns (round 3 hand test, :3087) and then "1", "10", "2", "3",
with the parser stubbed to the reading that broke round 3 (`reference_positions`, no
quantity) and the reading the prompt asks for (`demand_qty`).
"""
from __future__ import annotations

from dataclasses import fields

from app.services.chatbot.turn import task as task_mod
from app.services.chatbot.turn.plan import Trace

from tests.chatbot._turn_helpers import verdict
from tests.chatbot.test_stock_ask_ht26_r4_owner_replay import (
    OWNER_FAMILY,
    TOO_BIG,
    Console,
    _numbered,
)

LIST = _numbered("SRTWC286 matches 10 products. Which one?", OWNER_FAMILY)


def _as_position(n: int) -> dict:
    return verdict(reference_positions=[n], entities=[])


def _as_quantity(n: int) -> dict:
    return verdict(demand_qty=n, entities=[])


def _replay(read) -> Console:
    console = Console()
    console.first_ask("check stock srtwc286")
    console.say("1", _as_position(1))
    for message in ("10", "2", "3", "1", "10", "2", "3"):
        console.say(message, read(int(message)))
    return console


EXPECTED = [
    "check stock srtwc286",
    f"-> {LIST}",
    "1",
    "-> How many units of SRTWC286-SH?",
    "10",
    f"-> SRTWC286-SH x 10: {TOO_BIG}",
    "2",
    f"-> SRTWC286-SH x 2: {TOO_BIG}",
    "3",
    f"-> SRTWC286-SH x 3: {TOO_BIG}",
    "1",
    f"-> SRTWC286-SH x 1: {TOO_BIG}",
    "10",
    f"-> SRTWC286-SH x 10: {TOO_BIG}",
    "2",
    f"-> SRTWC286-SH x 2: {TOO_BIG}",
    "3",
    f"-> SRTWC286-SH x 3: {TOO_BIG}",
]


def test_owner_replay_then_1_10_2_3_read_as_positions_all_revise():
    console = _replay(_as_position)
    assert console.transcript == EXPECTED
    for plan in console.plans[2:]:
        assert "stock_pick_reopened" not in plan.trace.rules_fired
        assert "answer_pending" not in plan.trace.rules_fired


def test_owner_replay_then_1_10_2_3_read_as_quantities_all_revise():
    assert _replay(_as_quantity).transcript == EXPECTED


def test_the_pick_is_closed_once_a_product_is_picked():
    console = Console()
    console.first_ask("check stock srtwc286")
    assert console.state.pending is not None
    console.say("1", _as_position(1))
    assert console.state.pending is None
    (task,) = [t for t in console.state.focus.tasks if t.kind == "stock_qty"]
    wire = task_mod.task_to_wire(task)
    # Nothing about the list survives the pick: not on the task, not on its wire.
    assert "picked_from" not in wire
    assert all("SRTWC286-SH-150" not in str(v) for v in wire.values())


def test_the_task_and_trace_keep_no_list_to_point_into():
    assert "picked_from" not in {f.name for f in fields(task_mod.Task)}
    assert "spent_pick_options" not in {f.name for f in fields(Trace)}


def test_a_no_with_a_number_after_the_pick_never_picks_off_the_old_list():
    """"no, 2" after SRTWC286-SH x 10: the old list is forgotten, so the number is the
    quantity, never SRTWC286-SH-150."""
    console = Console()
    console.first_ask("check stock srtwc286")
    console.say("1", _as_position(1))
    console.say("10", _as_quantity(10))
    text = console.say("no, 2", verdict(reference_positions=[2], is_affirmative=False, entities=[]))
    assert text == f"SRTWC286-SH x 2: {TOO_BIG}"
    assert "stock_pick_reopened" not in console.plans[-1].trace.rules_fired
    assert "SRTWC286-SH-150" not in text


def test_a_new_check_stock_starts_a_new_pick():
    console = Console()
    console.first_ask("check stock srtwc286")
    console.say("1", _as_position(1))
    console.say("10", _as_quantity(10))
    console.say("2", _as_position(2))
    assert console.first_ask("check stock srtwc286") == LIST
    assert console.state.pending is not None
    assert console.say("2", _as_position(2)) == "How many units of SRTWC286-SH-150?"
    assert console.say("5", _as_position(5)) == f"SRTWC286-SH-150 x 5: {TOO_BIG}"
    assert console.say("7", _as_position(7)) == f"SRTWC286-SH-150 x 7: {TOO_BIG}"


def test_the_parser_is_not_taught_a_number_can_point_into_the_old_list():
    from app.services.chatbot_parser_prompt import STOCK_TASK_ADDENDUM

    assert '"no, the 2nd one"' not in STOCK_TASK_ADDENDUM
    assert "reference_positions [2]" not in STOCK_TASK_ADDENDUM
    assert "It is NEVER a position on a" in STOCK_TASK_ADDENDUM
