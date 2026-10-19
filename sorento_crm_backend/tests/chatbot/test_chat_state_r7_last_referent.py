"""CHAT-STATE r7 LAST-REFERENT (red): one open referent, chosen by recency, never by type.

Owner rule 20 Oct 07:04, crew a51605376 (a): a list the bot showed stays open; a bare number or a
pick refers to the NEWEST of {the last list, the pending question, the stock task owed a value}.
Every row kind of a list is pickable. UAC: chat-state-last-referent-r7-acceptance-criteria.md.

Seams the tests assume (named by the plan, not read from code that does not exist yet):
  * `turn/chat_state.open_referent(state)` returns the newest of the three referents;
  * a stored `Focus.last_list` row carries `shown_at_turn` (the list stamp) beside its
    `position / label / code / entity_type / uuid`;
  * `tail.last_list_after` takes the turn number the list is shown at.

REAL SHAPE of a promotion-files reply (AC-R7-9): the MCP presenter `_promotions`
(sorento_crm_mcp/sorento_crm_mcp/presenters.py:1051-1064) emits ONE item per promotion file, `title` =
the file name, `fields` = [company_name, Promotion (the file name), Start Date, End Date], and NO
`entity_id`; the engine's section is `Section(domain="promotion", figures=[<those items>])`
(turn/compose.py:49-54) and the label reader is `answer._promo_label_of` (lanes/business/answer.py:1714-1722,
title first, else the "Promotion" field). The file name is therefore the only key such a row has.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.chatbot.turn import chat_state
from app.services.chatbot.turn import question as question_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.compose import Answer, Section
from app.services.chatbot.turn.pending import ask
from app.services.chatbot.turn.state import Focus, State
from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict

DOMAINS = ["inventory", "incoming", "order", "sales", "product_attachment", "promotion"]
KINDS = ["product", "customer", "brand", "promotion", "attachment", "order"]
BRANDS = ["SORENTO", "MOCHA"]

CODE = "MKS9505-GM-HC"
FILE_1, FILE_2 = "Raya Promo A3.pdf", "Merdeka Promo A4.pdf"


# ------------------------------------------------------------------------------------- shapes
def _promo_figure(name: str) -> dict[str, Any]:
    """One item of the real `_promotions` presenter (see the module docstring)."""
    return {
        "title": name,
        "fields": [
            {"key": "company_name", "label": "Company", "value": "SORENTO"},
            {"label": "Promotion", "value": name},
            {"label": "Start Date", "value": "2026-10-01"},
            {"label": "End Date", "value": "2026-10-31"},
        ],
    }


def _promo_rows(shown_at: int) -> list[dict[str, Any]]:
    return [
        {"position": i, "label": n, "code": n, "entity_type": "promotion", "shown_at_turn": shown_at}
        for i, n in enumerate((FILE_1, FILE_2), 1)
    ]


def _product_rows(shown_at: int, codes=("SRT1", "SRT2", "SRT3")) -> list[dict[str, Any]]:
    return [
        {"position": i, "label": c, "code": c, "entity_type": "product", "shown_at_turn": shown_at}
        for i, c in enumerate(codes, 1)
    ]


def _owed_task(code: str = CODE, *, touched: int = 1):
    return ht.stock_task([(code, None)], opened_at_turn=touched, touched_at_turn=touched)


def _state(*, last_list=None, pending=None, tasks=(), products=(), turn_no=4, path=True) -> State:
    focus = Focus(products=ht.product_rows(*products), tasks=tuple(tasks), domains=["inventory"], last_list=last_list)
    return State(focus=focus, pending=pending, turn_no=turn_no, state_path=path)


def _op(op: str, position: int | None = None, axis: str | None = None) -> dict[str, Any]:
    return {"op": op, "axis": axis, "position": position}


def _open_question(state: State):
    return question_mod.open_question(state.pending, state.focus.tasks)


def _changes(state: State, v: dict[str, Any], monkeypatch):
    ran: list[int] = []
    real = chat_state.apply_changes

    def counted(*a, **k):
        ran.append(1)
        return real(*a, **k)

    monkeypatch.setattr(chat_state, "apply_changes", counted)
    applied = chat_state.apply_changes(
        state, v, open_question=_open_question(state), domains=DOMAINS, kinds=KINDS, brands=BRANDS,
        positions_read_elsewhere=False,
    )
    # AC-R7-9: the state path really ran (the counter), the turn did not slide to a legacy path.
    assert ran, "apply_changes never ran: the state path was not exercised"
    return applied


def _full_turn(state: State, v: dict[str, Any], monkeypatch):
    """The engine's order: the state applier over the shown State, then the turn APPLY."""
    applied = _changes(state, v, monkeypatch)
    out_state, plan = apply(applied.state, applied.verdict, build_policy())
    return applied, out_state, plan


def _referent(state: State):
    fn = getattr(chat_state, "open_referent", None)
    if fn is None:
        pytest.fail("chat_state.open_referent(state) does not exist yet: no single open referent")
    return fn(state)


def _which(ref, state: State) -> str | None:
    """Classify an `open_referent` return as 'list' / 'pending' / 'task' without fixing its shape."""
    from app.services.chatbot.turn.task import Task

    if ref is None:
        return None
    if ref is state.pending and state.pending is not None:
        return "pending"
    if isinstance(ref, Task):
        return "task"
    if isinstance(ref, list):
        return "list"
    kind = ref.get("kind") if isinstance(ref, dict) else getattr(ref, "kind", None)
    if kind in ("list", "last_list"):
        return "list"
    if kind in ("pending", "question"):
        return "pending"
    if kind in ("task", "stock_qty"):
        return "task"
    pytest.fail(f"cannot classify the open_referent return: {ref!r}")


def _picked_entities(v: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in v.get("entities") or [] if isinstance(e, dict)]


def _stock_answered_with_one(out_state: State, v: dict[str, Any], plan) -> bool:
    if v.get("demand_qty") == 1 or "bare_number_is_the_quantity" in plan.trace.rules_fired:
        return True
    return any(
        s.value == 1 for t in out_state.focus.tasks or () if t.kind == "stock_qty" for s in t.slots
    )


# ----------------------------------------------------------------- 1. AC-R7-1 (audit row 6, the headline)
@pytest.mark.parametrize(
    "reading",
    [
        verdict(reference_positions=[1], entities=[], state_changes=[_op("pick", 1)]),
        verdict(demand_qty=1, entities=[], state_changes=[_op("answer")]),
    ],
    ids=["reference_positions-1", "demand_qty-1"],
)
def test_r7_1_a_one_after_a_promo_file_list_picks_file_1_not_the_older_how_many(monkeypatch, reading):
    # how-many for MKS9505-GM-HC asked at turn 1; the NEXT reply (turn 3) listed two promo files.
    state = _state(last_list=_promo_rows(shown_at=3), tasks=(_owed_task(touched=1),), products=(CODE,), turn_no=4)
    applied, out_state, plan = _full_turn(state, reading, monkeypatch)
    v = applied.verdict
    assert not _stock_answered_with_one(out_state, v, plan), (
        "the older how-many took the bare 1 as the quantity", v.get("demand_qty"), plan.trace.rules_fired,
    )
    picked = [e for e in _picked_entities(v) if e.get("hint") == "promotion"]
    in_axis = out_state.focus.extra.get("promotion") or []
    keys = {e.get("canonical_code") for e in picked} | {r.get("canonical_code") for r in in_axis if isinstance(r, dict)}
    assert FILE_1 in keys and FILE_2 not in keys, ("promo file 1 was not picked", keys)
    held = [t for t in out_state.focus.tasks if t.kind == "stock_qty"]
    assert held and all(s.value is None for t in held for s in t.slots), "the stock task must stay held, unanswered"


# ------------------------------------------------------------------ 2. AC-R7-2 guard (must PASS today)
def test_r7_2_guard_list_pick_how_many_asked_then_2_is_the_quantity(monkeypatch):
    # list shown turn 1, the pick + how-many (task touched) turn 2: the NEWEST referent is the how-many.
    state = _state(
        last_list=_product_rows(shown_at=1), tasks=(_owed_task("SRT2", touched=2),), products=("SRT2",), turn_no=3
    )
    v = verdict(reference_positions=[2], entities=[])
    out_state, plan = apply(state, v, build_policy())
    assert v.get("demand_qty") == 2, ("2 must be the quantity, never item 2 of the list", v.get("demand_qty"))
    assert not any(e.get("canonical_code") == "SRT2" and e.get("current_message") for e in v.get("entities") or [])


# ------------------------------------------------------------------------------------------- 3. AC-R7-3
def _roster(asked_at: int):
    options = [
        {"position": 1, "label": "Acme Trading", "code": "C0001", "name": "Acme Trading",
         "entity_type": "customer", "payload": {}},
        {"position": 2, "label": "Beta Bhd", "code": "C0002", "name": "Beta Bhd", "entity_type": "customer", "payload": {}},
    ]
    return ask("customer_pick", options, asked_at_turn=asked_at)


def test_r7_3_a_roster_asked_after_a_list_takes_the_number(monkeypatch):
    state = _state(last_list=_product_rows(shown_at=2), pending=_roster(asked_at=3), turn_no=4)
    applied = _changes(state, verdict(reference_positions=[1], entities=[], state_changes=[_op("pick", 1)]), monkeypatch)
    answer = applied.verdict.get("open_question_answer") or {}
    assert applied.valid and answer.get("picked") == [1], ("the number must answer the newer roster", answer)
    assert "SRT1" not in {e.get("canonical_code") for e in _picked_entities(applied.verdict)}


def test_r7_3_a_list_shown_after_a_roster_takes_the_number(monkeypatch):
    state = _state(last_list=_product_rows(shown_at=4), pending=_roster(asked_at=2), turn_no=5)
    applied = _changes(state, verdict(reference_positions=[1], entities=[], state_changes=[_op("pick", 1)]), monkeypatch)
    codes = {e.get("canonical_code") for e in _picked_entities(applied.verdict)}
    assert "SRT1" in codes and "C0001" not in codes, ("the number must pick from the newer list, not the old roster", codes)


# ------------------------------------------------------------------------------------------- 4. AC-R7-4
def _list_after(previous, *, question=None, sections=None, turn_no: int):
    from app.services.chatbot.turn.tail import last_list_after

    kwargs: dict[str, Any] = {"question": question, "sections": sections if sections is not None else []}
    turn_params = [p for p in inspect.signature(last_list_after).parameters if "turn" in p]
    if not turn_params:
        pytest.fail("tail.last_list_after takes no turn number: the list cannot be stamped shown_at_turn")
    kwargs[turn_params[0]] = turn_no
    return last_list_after(previous, **kwargs)


def _stamps(rows) -> set:
    return {r.get("shown_at_turn") for r in rows or []}


def test_r7_4_a_newer_list_replaces_the_older_one_and_its_stamp():
    old = _product_rows(shown_at=2)
    fresh = Section(domain="promotion", figures=[_promo_figure(FILE_1), _promo_figure(FILE_2)])
    rows = _list_after(old, sections=[fresh], turn_no=5)
    assert [r.get("label") for r in rows] == [FILE_1, FILE_2]
    assert _stamps(rows) == {5}, ("a new list carries the turn it was shown at", _stamps(rows))


def test_r7_4_a_turn_showing_nothing_keeps_the_list_and_its_original_stamp():
    old = _product_rows(shown_at=2)
    rows = _list_after(old, sections=[Section(domain="inventory", figures=[])], turn_no=6)
    assert rows == old and _stamps(rows) == {2}, ("kept list must keep stamp 2", _stamps(rows))


def test_r7_4_a_no_option_question_after_a_list_is_the_open_referent_and_the_list_stays_stored():
    list_rows = _product_rows(shown_at=2)
    clarify = ask("clarify", [], asked_at_turn=3)
    state = _state(last_list=list_rows, pending=clarify, turn_no=4)
    assert _which(_referent(state), state) == "pending"
    assert state.focus.last_list == list_rows


def test_r7_4_the_newest_of_the_three_wins_by_stamp_not_by_type():
    # list newest -> list; stock task newest -> task
    s1 = _state(last_list=_promo_rows(shown_at=3), tasks=(_owed_task(touched=1),), products=(CODE,), turn_no=4)
    assert _which(_referent(s1), s1) == "list"
    s2 = _state(last_list=_promo_rows(shown_at=1), tasks=(_owed_task(touched=3),), products=(CODE,), turn_no=4)
    assert _which(_referent(s2), s2) == "task"


# ------------------------------------------------------------------------------------------- 5. AC-R7-5
ROW_KINDS = [
    ("product", "SRT1", "products"),
    ("attachment", "SRT1-brochure.pdf", "attachment"),
    ("promotion", FILE_1, "promotion"),
    ("order", "SO417636", "order"),
]


def _bucket(focus: Focus, bucket: str):
    return focus.products if bucket == "products" else focus.extra.get(bucket) or []


@pytest.mark.parametrize("kind,key,bucket", ROW_KINDS, ids=[k[0] for k in ROW_KINDS])
def test_r7_5_a_pick_on_every_row_kind_writes_its_key_to_the_matching_axis(monkeypatch, kind, key, bucket):
    rows = [
        {"position": 1, "label": key, "code": key, "entity_type": kind, "shown_at_turn": 3},
        {"position": 2, "label": "other", "code": "OTHER", "entity_type": kind, "shown_at_turn": 3},
    ]
    state = _state(last_list=rows, turn_no=4)
    applied, out_state, _plan = _full_turn(
        state, verdict(reference_positions=[1], entities=[], state_changes=[_op("pick", 1)]), monkeypatch
    )
    assert applied.valid is True, applied.log.get("rejected")
    held = {r.get("canonical_code") for r in _bucket(out_state.focus, bucket) if isinstance(r, dict)}
    assert key in held, (f"{kind} pick did not land on the {bucket} axis", held)


@pytest.mark.parametrize("kind", [k[0] for k in ROW_KINDS])
def test_r7_5_a_row_with_no_key_fails_the_pick_never_a_guess(monkeypatch, kind):
    rows = [{"position": 1, "label": "something", "code": None, "entity_type": kind, "shown_at_turn": 3}]
    applied = _changes(_state(last_list=rows, turn_no=4), verdict(state_changes=[_op("pick", 1)]), monkeypatch)
    assert applied.valid is False and applied.log["rejected"], "a keyless row must be refused, not guessed"


def test_r7_5_the_writer_keeps_kind_and_key_of_a_real_promotion_files_reply():
    section = Section(domain="promotion", figures=[_promo_figure(FILE_1), _promo_figure(FILE_2)])
    rows = _list_after(None, sections=[section], turn_no=3)
    assert [(r.get("entity_type"), r.get("code")) for r in rows] == [("promotion", FILE_1), ("promotion", FILE_2)]


# ------------------------------------------------------------------------------------------- 6. AC-R7-6
def test_r7_6_an_older_stock_task_under_a_newer_list_prints_as_held_not_as_the_open_question():
    state = _state(last_list=_promo_rows(shown_at=3), tasks=(_owed_task(touched=1),), products=(CODE,), turn_no=4)
    v = chat_state.view(state, _open_question(state))
    assert v["task_is_question"] is False, "the older how-many must not be printed as THE open question"
    assert "owed" not in (v["open_question"] or {}), ("open question still the stock task", v["open_question"])
    text = chat_state.render(v) or ""
    assert "pending task: the open question" not in text
    assert "pending task: {" in text, ("the older task must still be printed, as held", text)


def test_r7_6_guard_a_newer_stock_task_over_an_older_list_stays_the_open_question():
    state = _state(last_list=_promo_rows(shown_at=1), tasks=(_owed_task(touched=3),), products=(CODE,), turn_no=4)
    v = chat_state.view(state, _open_question(state))
    assert v["task_is_question"] is True


def test_r7_6_the_view_has_one_open_referent():
    state = _state(last_list=_promo_rows(shown_at=3), tasks=(_owed_task(touched=1),), products=(CODE,), turn_no=4)
    assert _which(_referent(state), state) == "list"
    v = chat_state.view(state, _open_question(state))
    open_things = [bool(v["task_is_question"]), bool(v["open_question"]) and "owed" in v["open_question"]]
    assert sum(open_things) == 0, ("the list is the referent; no second open question", v)


# ------------------------------------------------------------------------------------------- 7. AC-R7-7
def test_r7_7_guard_state_off_records_no_list():
    from app.services.chatbot.turn import tail

    state = _state(last_list=None, path=False, turn_no=3)
    answer = Answer(sections=[Section(domain="promotion", figures=[_promo_figure(FILE_1), _promo_figure(FILE_2)])])
    payload = tail.session_payload(state, answer, SimpleNamespace())
    assert "last_list" not in payload["focus"], payload["focus"].get("last_list")


@pytest.mark.parametrize("reading", [verdict(reference_positions=[1], entities=[])], ids=["reference_positions-1"])
def test_r7_7_guard_state_off_the_legacy_bare_number_rule_is_unchanged(reading):
    # state path OFF: even with a list stored, the legacy rule fires (byte-identical to today).
    state = _state(last_list=_promo_rows(shown_at=3), tasks=(_owed_task(touched=1),), products=(CODE,), turn_no=4, path=False)
    _out, plan = apply(state, reading, build_policy())
    assert reading.get("demand_qty") == 1
    assert "bare_number_is_the_quantity" in plan.trace.rules_fired
