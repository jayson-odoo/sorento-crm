"""Dealer stock verdict - S3, `Focus.tasks` and the entity `quantity` axis
(AC-1768, AC-1769, AC-1770). UAC "The open task on the focus (D21 to D23)". PLAN
"The engine (S3)" seams 2 and 3 (`turn/state.py`, `turn/task.py`).

`app/services/chatbot/turn/task.py` does not exist yet and `Focus` has no `tasks` field -
every test that touches either is RED with `ModuleNotFoundError` /
`TypeError: unexpected keyword argument 'tasks'`.

AC-1769 is the one exception, flagged rather than silently dropped (tester's own finding,
reported to the captain): `focus_to_wire` / `focus_from_wire` already pass every entity
dict through `_entity()` OPAQUELY (`{**value, "current_message": False}`), so a `quantity`
key on a product entity already survives the round trip today, with no coder change at
all - which is exactly what the plan itself says ("no wire change"). The test below is
kept (it is on the captain's list and pins real, load-bearing behaviour against a
regression), but it is GREEN on arrival, not RED - see the report for detail.
"""
from __future__ import annotations

import pathlib

import pytest


TURN_DIR = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot" / "turn"
)


# --------------------------------------------------------------------------- #
# AC-1769: entity quantity round trip (see module docstring - already green)
# --------------------------------------------------------------------------- #


def test_focus_entity_quantity_round_trip():
    from app.services.chatbot.turn.state import Focus, focus_from_wire, focus_to_wire

    focus = Focus(
        products=[
            {
                "raw": "MWT5727SS-CR",
                "hint": "product",
                "canonical_code": "MWT5727SS-CR",
                "current_message": True,
                "confident": True,
                "quantity": 5,
            }
        ]
    )

    wire = focus_to_wire(focus)
    restored = focus_from_wire(wire)

    assert restored.products[0]["quantity"] == 5, restored.products[0]


# --------------------------------------------------------------------------- #
# AC-1770: Focus.tasks wire round trip
# --------------------------------------------------------------------------- #


def _build_task():
    from app.services.chatbot.turn.task import Slot, Task

    return Task(
        kind="stock_qty",
        domain="inventory",
        status="open",
        opened_at_turn=1,
        touched_at_turn=3,
        slots=(
            Slot(key="uuid-a", label="A", value=5),
            Slot(key="uuid-b", label="B", value=60),
            Slot(key="uuid-c", label="C", value=None),
        ),
    )


def test_focus_declares_a_tasks_field_defaulting_to_empty():
    from app.services.chatbot.turn.state import Focus

    focus = Focus()
    assert focus.tasks == (), focus.tasks


def test_focus_task_wire_round_trip_carries_every_slot():
    from app.services.chatbot.turn.state import Focus, focus_from_wire, focus_to_wire

    task = _build_task()
    focus = Focus(tasks=(task,))

    wire = focus_to_wire(focus)
    restored = focus_from_wire(wire)

    assert len(restored.tasks) == 1, restored.tasks
    restored_task = restored.tasks[0]
    assert restored_task.kind == "stock_qty"
    assert restored_task.domain == "inventory"
    assert restored_task.status == "open"
    assert restored_task.opened_at_turn == 1
    assert restored_task.touched_at_turn == 3
    assert [(s.key, s.label, s.value) for s in restored_task.slots] == [
        ("uuid-a", "A", 5),
        ("uuid-b", "B", 60),
        ("uuid-c", "C", None),
    ]


def test_focus_task_wire_round_trip_preserves_parked_status():
    from app.services.chatbot.turn.state import Focus, focus_from_wire, focus_to_wire
    from dataclasses import replace

    task = replace(_build_task(), status="parked")
    focus = Focus(tasks=(task,))

    restored = focus_from_wire(focus_to_wire(focus))

    assert restored.tasks[0].status == "parked"


def test_focus_from_wire_with_no_tasks_key_loads_an_empty_list():
    """A focus persisted by a build before this slice shipped carries no `tasks` key at
    all - it must load as "no open task", not as a broken read."""
    from app.services.chatbot.turn.state import focus_from_wire

    restored = focus_from_wire({"products": [], "customers": []})

    assert restored.tasks == (), restored.tasks


def test_two_tasks_of_different_kinds_both_round_trip():
    from dataclasses import replace

    from app.services.chatbot.turn.state import Focus, focus_from_wire, focus_to_wire
    from app.services.chatbot.turn.task import Task

    stock_task = _build_task()
    ideation_task = Task(
        kind="ideation",
        domain="ideate",
        status="open",
        opened_at_turn=2,
        touched_at_turn=2,
        slots=(),
    )
    focus = Focus(tasks=(stock_task, ideation_task))

    restored = focus_from_wire(focus_to_wire(focus))

    assert {t.kind for t in restored.tasks} == {"stock_qty", "ideation"}


# --------------------------------------------------------------------------- #
# AC-1768: apply() stays pure over the new turn/task.py module too
# --------------------------------------------------------------------------- #


def test_task_module_is_covered_by_the_existing_purity_source_scan():
    """`test_rearch_s2_apply_is_pure.py::_turn_files` globs every `*.py` under
    `app/services/chatbot/turn/` and re-runs both of its checks (no import from
    head/dialogue/tail/engine, no `re.`/`.text`/`message.text`/`message[` call) over
    whatever it finds - so `turn/task.py` is swept up automatically and that file is
    never edited here. This test pins the SAME two checks against `turn/task.py`
    specifically, so a regression shows up in this file too, and proves the module
    exists at all (the first assertion) before checking its content."""
    task_path = TURN_DIR / "task.py"
    if not task_path.is_file():
        pytest.fail(f"{task_path} does not exist yet", pytrace=False)

    source = task_path.read_text(encoding="utf-8")
    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "re." not in line, f"task.py:{lineno}: {stripped!r} - no re. in the pure core"
        assert ".text" not in line, f"task.py:{lineno}: {stripped!r} - no .text in the pure core"
        assert "message.text" not in line, f"task.py:{lineno}: {stripped!r}"
        assert "message[" not in line, f"task.py:{lineno}: {stripped!r}"

    import ast

    tree = ast.parse(source, filename=str(task_path))
    forbidden_roots = {"head", "dialogue", "tail", "engine"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if "chatbot" in parts:
                idx = parts.index("chatbot")
                if len(parts) > idx + 1 and parts[idx + 1] in forbidden_roots:
                    pytest.fail(f"task.py imports from chatbot.{parts[idx + 1]}: {node.module}")
