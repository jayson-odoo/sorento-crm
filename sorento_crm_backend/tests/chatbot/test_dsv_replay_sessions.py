"""Dealer stock verdict - S3, the session-level `focus.tasks` / `open_question`
assertions the structural replay gate (`test_turn_replay.py`) does not check.

`test_turn_replay.py::_compare` grades `branch_kind`, `action_kinds`, `tools`,
`entity_ids`, `pending` (option labels only) and `canned`/`text` - never
`session_patch["focus"]["tasks"]`. That file is NEVER edited here (captain's brief);
instead this file drives the SAME `case-dsv-*.json` fixtures through the SAME private
harness helpers (`_install_stubs`, `_build_envelope`, `_seed_contact`,
`_seed_case_customers`, `_seed_case_products`, `_apply_switches`, `_write_session_vars`)
imported straight from `tests.chatbot.test_turn_replay`, and asserts on
`result.session_patch["focus"].get("tasks")` / `result.session_patch["open_question"]`
turn by turn - the load-bearing content of AC-1761 to AC-1774, AC-1779, AC-1784, AC-1785.

RIGHT NOW every test here is RED: `focus_to_wire` does not write a `"tasks"` key at all
(no `turn/state.py::Focus.tasks` field exists yet), so `session_patch["focus"].get(
"tasks")` reads `None` on every turn of every case, and every assertion below that
expects a populated task list fails cleanly on that missing key - never on a fixture
load failure (the fixture-loading half of every case here is already proven by
`test_turn_replay.py::test_replay` picking up the exact same files; see the tester's
report for the two cases where fixture realism was traded down to a working roster
mechanism, `case-dsv-08`, rather than the UAC's literal `product_pick` shape).

Two flagged simplifications carried from `test_dsv_apply_tasks.py` apply here too:
`pending_media` is not modelled (D24 tie in `case-dsv-10` is exercised via the two
tasks being open, not via a live `session.ideation.pending_media` flag), and the
"ideation closes on the tool's word" half of AC-1786 is not replay-tested here (it needs
a NON-dry-run turn to reach a real `crm_ideation_turn` call, and every replay-harness
turn is `dry_run=True` by construction - `Envelope.dry_run` is `is_test or test_run_id or
mode != "live"`, and `_build_envelope` sets both `is_test` and `test_run_id` on every
turn); see `test_dsv_apply_tasks.py::test_ideation_task_kind_closes_on_the_tools_complete_status_only`
for that half instead.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.chatbot.test_engine import stub_parser  # noqa: F401 - fixture import
from tests.chatbot.test_turn_replay import (
    REPLAY_ROOT,
    _apply_switches,
    _build_envelope,
    _install_stubs,
    _seed_case_customers,
    _seed_case_products,
    _seed_contact,
    _write_session_vars,
)


def _replay(case_name: str, session_factory, stub_parser, monkeypatch) -> list[dict]:
    """Runs every turn of `case_name` (a `console/case-dsv-*` stem) through the real
    `engine.run_turn`, the same way `test_turn_replay.py::test_replay` does, and returns
    the list of `session_patch` dicts, one per turn - the piece that file computes and
    then throws away after `_compare`."""
    from app.services.chatbot import engine as engine_mod

    path = REPLAY_ROOT / "console" / f"{case_name}.json"
    payload = json.loads(path.read_text())
    turns = payload["turns"]
    case_id = f"console/{case_name}.json"

    contact_id = ((turns[0].get("envelope") or {}).get("contact") or {}).get("id") or 999999999
    _seed_contact(session_factory, contact_id=contact_id)
    _seed_case_customers(session_factory, case_id=case_id)
    _seed_case_products(session_factory, case_id=case_id)

    patches: list[dict] = []
    for step_no, turn in enumerate(turns, start=1):
        _apply_switches(session_factory, turn.get("switches"))
        _install_stubs(monkeypatch, stub_parser, turn=turn)
        envelope = _build_envelope(turn, message_id=f"dsv-sess-{case_name}-{step_no}")
        result = engine_mod.run_turn(envelope, session_factory=session_factory)
        patches.append(result.session_patch or {})
        if step_no < len(turns) and result.session_patch is not None:
            _write_session_vars(session_factory, contact_id=contact_id, payload=result.session_patch)
    return patches


def _tasks_of(patch: dict) -> list[dict]:
    focus = patch.get("focus") or {}
    tasks = focus.get("tasks")
    assert tasks is not None, (
        "session_patch['focus'] carries no 'tasks' key at all - Focus.tasks / "
        "focus_to_wire do not exist yet (AC-1770)"
    )
    return tasks


def _task(patch: dict, kind: str) -> dict:
    matches = [t for t in _tasks_of(patch) if t.get("kind") == kind]
    assert matches, f"no {kind!r} task on session_patch['focus']['tasks']: {_tasks_of(patch)}"
    return matches[0]


def _slot_values(task: dict) -> dict:
    return {s["key"]: s.get("value") for s in task.get("slots") or []}


# --------------------------------------------------------------------------- #
# AC-1761: four products, two quantities - the task opens
# --------------------------------------------------------------------------- #


def test_case_01_opens_a_stock_task_with_two_slots_still_missing(session_factory, stub_parser, monkeypatch):
    patches = _replay("case-dsv-01-four-products-two-quantities-asks", session_factory, stub_parser, monkeypatch)
    patch = patches[-1]

    task = _task(patch, "stock_qty")
    assert task["domain"] == "inventory"
    assert task["status"] == "open"
    slots = _slot_values(task)
    assert len(slots) == 4, slots
    filled = {k: v for k, v in slots.items() if v is not None}
    missing = {k for k, v in slots.items() if v is None}
    assert sorted(filled.values()) == [5, 60], slots
    assert len(missing) == 2, slots
    assert patch.get("open_question") is None, "a task is not a roster (AC-1761)"


# --------------------------------------------------------------------------- #
# AC-1762: quantities complete - the task closes
# --------------------------------------------------------------------------- #


def test_case_02_task_closes_once_every_slot_is_answered(session_factory, stub_parser, monkeypatch):
    patches = _replay("case-dsv-02-quantities-complete-answers", session_factory, stub_parser, monkeypatch)
    final = patches[-1]

    assert _tasks_of(final) == [], _tasks_of(final)


# --------------------------------------------------------------------------- #
# AC-1763: proceed_anyway - the task closes and drops the unmet slots
# --------------------------------------------------------------------------- #


def test_case_03_proceed_anyway_closes_the_task(session_factory, stub_parser, monkeypatch):
    patches = _replay("case-dsv-03-proceed-anyway-not-checked", session_factory, stub_parser, monkeypatch)
    final = patches[-1]

    assert _tasks_of(final) == [], _tasks_of(final)


# --------------------------------------------------------------------------- #
# AC-1764 (D16): a restated quantity replaces, the missing list is unchanged
# --------------------------------------------------------------------------- #


def test_case_04_restated_quantity_replaces_the_earlier_one(session_factory, stub_parser, monkeypatch):
    patches = _replay("case-dsv-04-restated-quantity-replaces", session_factory, stub_parser, monkeypatch)
    final = patches[-1]

    task = _task(final, "stock_qty")
    slots = _slot_values(task)
    b_value = next((v for k, v in slots.items() if v == 80), None)
    assert b_value == 80, f"B was restated to 80: {slots}"
    still_missing = sum(1 for v in slots.values() if v is None)
    assert still_missing == 2, f"C and D must still be missing: {slots}"


# --------------------------------------------------------------------------- #
# AC-1767: a detailed-policy contact opens no task at all
# --------------------------------------------------------------------------- #


def test_case_05_detailed_contact_opens_no_task(session_factory, stub_parser, monkeypatch):
    patches = _replay("case-dsv-05-detailed-contact-unchanged", session_factory, stub_parser, monkeypatch)
    final = patches[-1]

    assert _tasks_of(final) == [], (
        "a detailed-mode reply carries no stock_availability shape and must not open "
        f"a task: {_tasks_of(final)}"
    )


# --------------------------------------------------------------------------- #
# AC-1771: detour parks the task; a later fill closes it
# --------------------------------------------------------------------------- #


def test_case_06_detour_parks_the_task_slots_unchanged(session_factory, stub_parser, monkeypatch):
    patches = _replay("case-dsv-06-detour-parks-then-fills", session_factory, stub_parser, monkeypatch)
    opened, detoured, filled = patches[0], patches[1], patches[2]

    opened_task = _task(opened, "stock_qty")
    assert opened_task["status"] == "open"

    parked_task = _task(detoured, "stock_qty")
    assert parked_task["status"] == "parked"
    assert _slot_values(parked_task) == _slot_values(opened_task), (
        "the promotion detour must not touch the task's own slots"
    )

    assert _tasks_of(filled) == [], "every slot answered on turn 3 closes the task"


# --------------------------------------------------------------------------- #
# AC-1772: resume by naming re-opens and re-asks only what is missing
# --------------------------------------------------------------------------- #


def test_case_07_resume_by_naming_reopens_the_task(session_factory, stub_parser, monkeypatch):
    patches = _replay("case-dsv-07-resume-by-naming-reasks-missing", session_factory, stub_parser, monkeypatch)
    resumed = patches[-1]

    task = _task(resumed, "stock_qty")
    assert task["status"] == "open", "naming the stock check again must resume it"
    slots = _slot_values(task)
    assert sum(1 for v in slots.values() if v is None) == 2, (
        f"the same two slots are still missing, nothing was asked twice: {slots}"
    )


# --------------------------------------------------------------------------- #
# AC-1773: a roster elsewhere does not close or alter the open task
# --------------------------------------------------------------------------- #


def test_case_08_a_roster_does_not_touch_the_open_task(session_factory, stub_parser, monkeypatch):
    patches = _replay("case-dsv-08-roster-inside-form", session_factory, stub_parser, monkeypatch)
    opened, after_roster = patches[0], patches[1]

    opened_task = _task(opened, "stock_qty")
    still_open_task = _task(after_roster, "stock_qty")
    assert still_open_task["status"] == "open"
    assert _slot_values(still_open_task) == _slot_values(opened_task), (
        "an unrelated roster must not change the task's own slots"
    )


# --------------------------------------------------------------------------- #
# AC-1774: proceed while parked
# --------------------------------------------------------------------------- #


def test_case_09_proceed_anyway_closes_a_parked_task_too(session_factory, stub_parser, monkeypatch):
    patches = _replay("case-dsv-09-proceed-while-parked", session_factory, stub_parser, monkeypatch)
    final = patches[-1]

    assert _tasks_of(final) == [], _tasks_of(final)


# --------------------------------------------------------------------------- #
# AC-1779 (D24): two tasks at once, the tie roster and its resolution
# --------------------------------------------------------------------------- #


def test_case_10_two_tasks_tie_then_resolve_by_position(session_factory, stub_parser, monkeypatch):
    patches = _replay("case-dsv-10-tie-asks-which-task", session_factory, stub_parser, monkeypatch)
    after_stock_open, after_ideate_open, after_tie, after_resolved = patches

    stock1 = _task(after_stock_open, "stock_qty")
    assert stock1["status"] == "open"

    idea = _task(after_ideate_open, "ideation")
    assert idea["status"] == "open"
    stock2 = _task(after_ideate_open, "stock_qty")
    assert stock2["status"] == "open", "opening the ideation task must not touch the stock task"

    tie_tasks = _tasks_of(after_tie)
    assert len(tie_tasks) == 2, tie_tasks
    for t in tie_tasks:
        assert t["status"] == "open", f"neither task changes while the tie is unresolved: {tie_tasks}"
    open_question = after_tie.get("open_question") or {}
    assert open_question.get("kind") == "task_pick", open_question
    assert len(open_question.get("options") or []) == 2, open_question

    resolved_stock = _task(after_resolved, "stock_qty")
    slots = _slot_values(resolved_stock)
    assert any(v == 110 for v in slots.values()), (
        f"the tie-breaking pick must apply the carried number to the stock task: {slots}"
    )


# --------------------------------------------------------------------------- #
# AC-1784 / AC-1785: ideation as the second task kind
# --------------------------------------------------------------------------- #


def test_case_11_ideation_opens_a_task(session_factory, stub_parser, monkeypatch):
    patches = _replay("case-dsv-11-ideation-opens-task", session_factory, stub_parser, monkeypatch)
    final = patches[-1]

    idea = _task(final, "ideation")
    assert idea["status"] == "open"
    assert idea.get("slots") in ([], None), "IdeationTask owns no slots of its own (D26)"


def test_case_12_a_stock_ask_parks_ideation_and_naming_it_resumes(session_factory, stub_parser, monkeypatch):
    patches = _replay(
        "case-dsv-12-ideation-parks-on-stock-ask-resumes-by-naming", session_factory, stub_parser, monkeypatch
    )
    opened, parked, resumed = patches

    idea_open = _task(opened, "ideation")
    assert idea_open["status"] == "open"

    idea_parked = _task(parked, "ideation")
    assert idea_parked["status"] == "parked", (
        "a stock ask must park the ideation task silently, per D22"
    )

    idea_resumed = _task(resumed, "ideation")
    assert idea_resumed["status"] == "open", "naming ideate again resumes it"
