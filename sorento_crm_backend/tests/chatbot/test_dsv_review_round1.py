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

from tests.chatbot._turn_helpers import _domain_row, _kind_row, build_policy, entity, verdict


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


def test_task_fetch_beats_a_task_question_from_the_same_turn(monkeypatch):
    """Review round 2. `task_mod.run()`'s own contract lets `TaskOutcome` carry a
    `fetch` AND a `question` together - nothing about its return shape rules that out,
    and a future kind that fills one task while resuming another (owing its own
    question) is exactly the case this test stands in for, via a throwaway `run()`
    that returns both. RED before the fix: `if task_outcome.question:` fired
    unconditionally and returned the question-only Plan, silently dropping the fetch
    the fill had already earned."""
    from app.services.chatbot.turn import apply as apply_mod
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.plan import FetchSpec
    from app.services.chatbot.turn.state import Focus
    from app.services.chatbot.turn.task import TaskOutcome

    task = _stock_task(slots=[("uuid-c", "C", 110)])
    focus = Focus(tasks=(task,))
    fake_outcome = TaskOutcome(
        tasks=(task,),
        fetch=FetchSpec(domain="inventory", entities=[], filters={}, date_window=None),
        fetch_domain="inventory",
        question="How many units do you need for D?",
        question_domain="inventory",
    )
    monkeypatch.setattr(apply_mod.task_mod, "run", lambda *a, **k: fake_outcome)
    v = verdict(entities=[entity("C", hint="product", quantity=110)])

    _state2, plan = apply(_state(focus), v, build_policy())

    assert plan.fetch, "the fetch a fill just earned must not be dropped for a question"
    assert plan.ask is None
    assert plan.trace.task_question is None


def test_engine_named_products_reads_only_the_inventory_specs_own_entities(
    session_factory, monkeypatch
):
    """Review round 2, engine level (not just `apply()`'s Plan shape): `engine.py`'s
    `named_products=any(spec.entities for spec in fetch_plan.fetch)` read EVERY
    domain's spec, not just inventory's own - a multi-domain ask that names a product
    for one domain and asks inventory as a bare, general "what stock do we have"
    would have opened a stock task for the whole catalogue page off a product
    inventory itself was never asked about.

    Under today's real `policy_rows.py` config, inventory only narrows on `product`
    (`list_all`), so on a real multi-domain ask its spec either carries the SAME
    resolved entities as every other domain narrowing on `product` too (both formulas
    then agree), or - nothing named at all - gets refused outright by D5(b)'s
    `_REFUSES_EMPTY_SUBJECT` before it ever reaches `fetch_plan.fetch` (so there is no
    inventory spec for either formula to read). A throwaway two-domain `Policy`
    (`load_policy` monkeypatched, `inventory` given NO `product` narrowing kind,
    `takes_date_filter=True` so D5(b) does not refuse it) is what pins a config where
    the two genuinely disagree - the same way this policy could grow a domain like it.
    `turn_task.tasks_after_reply` is spied so the real, PRODUCTION `named_products`
    value this turn computed is read straight off the call, not reconstructed by the
    test. RED before the fix: the spy captures `True` (any spec, off promotion's
    entities alone); the FIX captures `False` (inventory's own spec named nothing)."""
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.turn.policy import Policy
    from tests.chatbot.test_engine import _parser_output
    from tests.chatbot.test_outstanding_lane import (
        PRODUCT_CODE,
        PRODUCT_UUID,
        _run_turn,
        _seed_contact,
    )

    inventory_row = _domain_row("inventory", narrowing={}, tools=("crm_inventory_stock_balance_list",))
    inventory_row["takes_date_filter"] = True
    promotion_row = _domain_row(
        "promotion", narrowing={"product": "narrow_to_code"}, tools=("crm_marketing_promotions_list",)
    )
    policy = Policy.from_rows(
        domains=[inventory_row, promotion_row],
        kinds=[_kind_row("product", default_narrowing="narrow_to_code")],
        tier_order=[],
    )
    monkeypatch.setattr(engine_mod, "load_policy", lambda db: policy)

    captured: list[bool] = []
    real_tasks_after_reply = engine_mod.turn_task.tasks_after_reply

    def _spy(tasks, envelopes, *, turn_no=0, named_products=True):
        captured.append(named_products)
        return real_tasks_after_reply(
            tasks, envelopes, turn_no=turn_no, named_products=named_products
        )

    monkeypatch.setattr(engine_mod.turn_task, "tasks_after_reply", _spy)

    _seed_contact(session_factory, variables={})
    _run_turn(
        session_factory,
        monkeypatch,
        qf=_parser_output(
            domain_hint=None,
            intent_hint=None,
            entities=[
                {
                    "raw": PRODUCT_CODE,
                    "hint": "product",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                },
            ],
            asks=[{"domain": "promotion"}, {"domain": "inventory"}],
        ),
        text_body=f"promo for {PRODUCT_CODE}, and what stock do we have generally?",
        msg_id="zzt-review2-named-products",
        matches={PRODUCT_CODE: {"uuid": PRODUCT_UUID, "code": PRODUCT_CODE, "entity_type": "product"}},
        mcp_response={"has_result": False, "items": []},
    )

    assert captured == [False], (
        "inventory's own spec named nothing (it has no product narrowing kind in "
        "this policy) - a product some OTHER domain's spec named must not count"
    )


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


# --------------------------------------------------------------------------- #
# Review round 3 (live pass, dealer-stock-verdict.EVIDENCE.md, Root cause A):
# `requested_quantities` must cross the MCP boundary as a JSON string, not a
# native dict. The engine's internal representation (`FetchSpec.filters`,
# `_spec_quantities`, tested above) stays a dict all the way up to
# `entity_ids_transformer` in `lanes/business/fetch.py` - this is the ONE seam
# where it turns into the wire arg the MCP tool actually receives.
# --------------------------------------------------------------------------- #


def test_fetch_arg_builder_serialises_requested_quantities_to_a_json_string():
    """RED before the fix: `entity_ids_transformer` put a native dict on
    `out["requested_quantities"]`. The MCP's `_compile_tool` types every query
    param off one fixed `str | int | float | bool | list[str]` union with no
    dict case (`sorento_crm_mcp/server.py::_compile_tool`, `_scalar_union`), so
    a dict-valued call fails Pydantic validation with 5 errors and never
    reaches the backend at all - the backend route already declares
    `requested_quantities: Optional[str]` and parses it with
    `parse_requested_quantities`. The wire arg must therefore be a compact
    JSON string whose `json.loads` recovers the exact map."""
    import json

    from app.services.chatbot.lanes.business import fetch

    trigger = {
        "entities": [],
        "tool": "crm_inventory_stock_balance_list",
        "semantic_input": {
            "requested_quantities": {"uuid-a": 5, "uuid-b": 60},
            "contact_id": "1",
            "space_id": "s",
        },
    }
    out = fetch.entity_ids_transformer(trigger)

    assert isinstance(out["requested_quantities"], str), (
        "a native dict fails MCP-side Pydantic validation before the backend "
        f"is ever reached: {out['requested_quantities']!r}"
    )
    assert json.loads(out["requested_quantities"]) == {"uuid-a": 5, "uuid-b": 60}


def test_fetch_arg_builder_omits_requested_quantities_when_empty():
    """The empty/absent case is unchanged by the string conversion - still
    simply not sent, so a turn with no quantity at all still reaches the
    backend as `needs_quantity` for every product (D14)."""
    from app.services.chatbot.lanes.business import fetch

    trigger = {
        "entities": [],
        "tool": "crm_inventory_stock_balance_list",
        "semantic_input": {"requested_quantities": {}, "contact_id": "1", "space_id": "s"},
    }
    out = fetch.entity_ids_transformer(trigger)

    assert "requested_quantities" not in out


# --------------------------------------------------------------------------- #
# Review round 3, Observation B (`dealer-stock-verdict.EVIDENCE.md`): the raw
# MCP intro reaching the customer with a numbered list of nothing on the
# noted/missing question, and the per-product verdict line (D6/D17) never
# reaching the customer at all even once it exists.
#
# Root cause, precise: `_stock_availability`'s `raw_item` calls
# (`sorento_crm_mcp/presenters.py`) always pass `fields=[]` - "an `availability`
# answer has no fields AT ALL (that is the point of the mode)", per that
# function's own docstring - and put the whole sentence in `title` instead.
# `_item_line` (below) never read `title`, only `fields` - exactly the gotcha
# `_stock_compact`'s own sibling comment already names ("n8n's output-structurer
# walks fields and does not print title", `presenters.py` ~line 1341) and
# deliberately avoids by putting `product_code` into `fields`.
# `_stock_availability` is the one caller that does not follow that precedent.
# --------------------------------------------------------------------------- #


def _availability_render_envelope(*entries: dict) -> dict:
    """One `stock_availability` item per entry, shaped exactly as
    `sorento_crm_mcp/presenters.py::_stock_availability` builds them: `title`
    carries the sentence (or the bare code while still asking), `fields` is
    always empty, `flags` carries `needs_quantity` / `available`."""
    return {
        "result_type": "stock_availability",
        "intro": "How many units do you need for MHS1028 and MSK11A-QT?",
        "items": [
            {
                "title": e["title"],
                "fields": [],
                "flags": {
                    "needs_quantity": e.get("needs_quantity", False),
                    "available": e.get("available"),
                },
            }
            for e in entries
        ],
        "has_result": True,
    }


def test_stock_availability_ask_prints_only_the_intro_no_numbered_list():
    """The ask state (D14): at least one product still needs a quantity, so
    `intro` already says everything relevant. RED before the fix: the items
    loop still ran and appended a numbered list of blank lines (`"1.   2.
    3."`, Observation B's exact symptom, since `fields` is always empty)."""
    from app.services.chatbot.lanes.business import fetch

    envelope = _availability_render_envelope(
        {"title": "MWT5727SS-CR x 5", "needs_quantity": False},
        {"title": "MHS1028", "needs_quantity": True},
        {"title": "MSK11A-QT", "needs_quantity": True},
    )
    out = fetch.output_structurer(envelope, {"semantic_input": {}})

    assert out["response"].strip() == envelope["intro"]


def test_stock_availability_verdict_prints_the_per_product_line():
    """D6/D17: once every product has a quantity, each item's TITLE is the
    exact verdict sentence the presenter built - it must reach the customer.
    RED before the fix: `_item_line` read only `fields` (always empty for this
    mode), so every row printed as an empty numbered line."""
    from app.services.chatbot.lanes.business import fetch

    envelope = _availability_render_envelope(
        {
            "title": "MWT5727SS-CR x 5: Not available, but there is purchase, ETA in 90 days.",
            "needs_quantity": False,
            "available": False,
        },
        {
            "title": "MHS1028 x 60: Not available.",
            "needs_quantity": False,
            "available": False,
        },
    )
    envelope["intro"] = "Sorry, we do not have enough stock for that quantity."
    out = fetch.output_structurer(envelope, {"semantic_input": {}})

    assert (
        "MWT5727SS-CR x 5: Not available, but there is purchase, ETA in 90 days."
        in out["response"]
    )
    assert "MHS1028 x 60: Not available." in out["response"]


def test_stock_availability_ask_with_none_answered_yet_is_also_suppressed():
    """The FIRST ask (Observation B's exact turn): no product has a quantity
    at all, so every entry's `needs_quantity` is true - still just the
    intro, no numbered list of bare codes."""
    from app.services.chatbot.lanes.business import fetch

    envelope = _availability_render_envelope(
        {"title": "MHS1028", "needs_quantity": True},
        {"title": "MSK11A-QT", "needs_quantity": True},
    )
    out = fetch.output_structurer(envelope, {"semantic_input": {}})

    assert out["response"].strip() == envelope["intro"]
