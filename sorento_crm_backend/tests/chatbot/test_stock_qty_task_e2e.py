"""chatbot-stock-ask-v2 S3 - one focused end-to-end pass over the StockQtyTask loop
(PLAN-chatbot-stock-ask-v2-24sep.md "S3", UAC AC-SA301 to AC-SA318's own journey step
1, "the dealer names one or more products; #1118's stock task collects a quantity per
product").

Ports the SHAPE of #1118's own console cases (`case-dsv-01-four-products-two-
quantities-asks.json`, `case-dsv-02-quantities-complete-answers.json`), not their
literal fixtures: a dealer names two products with no quantity, the bot asks for both,
the dealer answers one, the bot still asks for the other, the dealer answers the
second, and the fetch the task then drives carries BOTH quantities in the order the
dealer named the products - the whole loop `Focus.tasks` + `StockQtyTask` exist for.

Deliberately NOT a replay-harness or engine-level test (those weigh thousands of lines
in #1118's own `test_dsv_review_round1.py` / `test_dsv_replay_sessions.py`, which the
captain's brief explicitly said not to port wholesale): this drives the two seams
directly - `turn/task.py::tasks_after_reply` (what the stock tool's OWN reply opens
the task from) and `turn/apply.py::apply` (what a turn that fills a slot does) - the
same two calls `engine.py` makes, in the same order.
"""
from __future__ import annotations

from app.services.chatbot.turn import task as task_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.state import Focus

from tests.chatbot._turn_helpers import build_policy, entity, verdict


def _envelopes(rows):
    return [{"stock_availability": rows}]


def test_two_products_no_quantity_then_answered_one_at_a_time_drives_a_fetch_with_both():
    policy = build_policy()

    # 1. The dealer names two products with no quantity; the stock tool's own reply
    # comes back `needs_quantity` for both (D25: the backend decides who must state a
    # quantity, never the engine). `tasks_after_reply` opens the task from that reply.
    opened = task_mod.tasks_after_reply(
        (),
        _envelopes(
            [
                {
                    "product_id": "uuid-srt5674",
                    "product_code": "SRT5674",
                    "needs_quantity": True,
                    "requested_qty": None,
                },
                {
                    "product_id": "uuid-cwcx604",
                    "product_code": "CWCX604",
                    "needs_quantity": True,
                    "requested_qty": None,
                },
            ]
        ),
        turn_no=1,
        named_products=True,
    )
    assert len(opened) == 1 and opened[0].kind == "stock_qty"
    task = opened[0]
    assert {s.key: s.value for s in task.slots} == {
        "uuid-srt5674": None,
        "uuid-cwcx604": None,
    }

    # 2. The dealer answers ONE of the two ("50 for SRT5674"). The turn fills that
    # slot; the OTHER is still missing, so nothing is fetched yet and the reply is the
    # re-ask naming only what is still owed.
    focus = Focus(tasks=(task,))
    from app.services.chatbot.turn.state import Profile, State

    state = State(focus=focus, pending=None, profile=Profile(), turn_no=2)
    v = verdict(entities=[entity("SRT5674", hint="product", quantity=50, uuid="uuid-srt5674")])
    state, plan = apply(state, v, policy)

    stock = next(t for t in state.focus.tasks if t.kind == "stock_qty")
    assert {s.key: s.value for s in stock.slots} == {
        "uuid-srt5674": 50,
        "uuid-cwcx604": None,
    }
    assert not plan.fetch, "one slot still owed: nothing fetched yet"
    assert plan.trace.task_question is not None
    assert "CWCX604" in plan.trace.task_question, plan.trace.task_question

    # 3. The dealer answers the SECOND product ("300 for CWCX604"). Nothing is owed
    # any more, so the task drives its OWN fetch - carrying BOTH quantities, in the
    # order the dealer named the products (SRT5674 first, per the task's own slot
    # order from step 1).
    v2 = verdict(entities=[entity("CWCX604", hint="product", quantity=300, uuid="uuid-cwcx604")])
    state2, plan2 = apply(state, v2, policy)

    stock2 = next(t for t in state2.focus.tasks if t.kind == "stock_qty")
    assert {s.key: s.value for s in stock2.slots} == {
        "uuid-srt5674": 50,
        "uuid-cwcx604": 300,
    }
    assert len(plan2.fetch) == 1, plan2.fetch
    spec = plan2.fetch[0]
    assert spec.domain == "inventory"
    assert spec.filters.get("requested_quantities") == {
        "uuid-srt5674": 50,
        "uuid-cwcx604": 300,
    }
    assert [e["uuid"] for e in spec.entities] == ["uuid-srt5674", "uuid-cwcx604"], (
        "asked order preserved: SRT5674 named first, CWCX604 second"
    )

    # 4. The tool answers both (neither entry needs a quantity any more): nothing is
    # owed any more. Owner hand test 26 Sep, slice 5 (R1 re-ruled 26 Sep): the check is
    # KEPT as what the last reply answered, so a follow-up can revise it; it is no
    # longer an open question.
    closed = task_mod.tasks_after_reply(
        state2.focus.tasks,
        _envelopes(
            [
                {
                    "product_id": "uuid-srt5674",
                    "product_code": "SRT5674",
                    "needs_quantity": False,
                    "requested_qty": 50,
                },
                {
                    "product_id": "uuid-cwcx604",
                    "product_code": "CWCX604",
                    "needs_quantity": False,
                    "requested_qty": 300,
                },
            ]
        ),
        turn_no=3,
        named_products=True,
    )
    assert [t.status for t in closed] == [task_mod.ANSWERED], closed
    assert {s.key: s.value for s in closed[0].slots} == {
        "uuid-srt5674": 50,
        "uuid-cwcx604": 300,
    }
