"""Dealer stock verdict - S3, the parser schema + the open-task hint block
(AC-1760, AC-1778, AC-1787). UAC
`documentation/plans/chatbot/chatbot-dealer-stock-verdict-acceptance-criteria.md`
"Phase 2 - engine". PLAN `documentation/plans/chatbot/PLAN-chatbot-dealer-stock-verdict.md`
"The engine (S3)", seam 1 and the "hint" lifecycle bullet.

This EXTENDS `test_parser_schema_guard.py`'s triangle without editing that file: its own
parametrized tests (`test_every_key_the_engine_reads_is_declared_in_the_schema`,
`test_every_declared_key_is_named_in_the_prompt`) already cover any TOP-LEVEL key once it
is added to `DECLARED_KEYS` (`proceed_anyway` will be swept up automatically once the
coder adds it there and to `MEASURED_VERDICT_READS`). `entities[].quantity` is nested
under `entities.items.properties` and that guard's parametrization never reaches inside
an array item, so it needs its own assertions here.

RED right now:
- `quantity` is not a key of `entities.items.properties` (AC-1760) - AssertionError.
- `proceed_anyway` is not in `DECLARED_KEYS` / `PARSE_OUTPUT_JSON_SCHEMA["properties"]` -
  AssertionError.
- Neither literal (`entities[].quantity`, `proceed_anyway`) appears anywhere in
  `SEMANTIC_PARSER_PROMPT` (`app/services/chatbot_parser_prompt.py`) - AssertionError.
- `build_user_block` has no reader of `Focus.tasks` at all, so no "Open task: ..." line
  is ever emitted, whatever `focus.tasks` carries - AssertionError on a missing line
  (`Focus` itself is untouched here: a plain `SimpleNamespace`/real `Focus` instance with
  a dynamically-set `.tasks` attribute is enough to prove the reader is missing, without
  this file depending on `turn/task.py` or `Focus.tasks` actually existing as a declared
  field - that dependency belongs to `test_dsv_focus_tasks.py`).
"""
from __future__ import annotations

from app.services.chatbot.head.parser import (
    DECLARED_KEYS,
    PARSE_OUTPUT_JSON_SCHEMA,
    build_user_block,
)
from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT


# --------------------------------------------------------------------------- #
# AC-1760: entities[].quantity and top-level proceed_anyway
# --------------------------------------------------------------------------- #


def test_entities_items_declare_quantity_number_or_null():
    entities = PARSE_OUTPUT_JSON_SCHEMA["properties"]["entities"]
    item_props = entities["items"]["properties"]
    assert "quantity" in item_props, item_props.keys()
    assert item_props["quantity"] == {"type": ["number", "null"]}, item_props["quantity"]


def test_entities_items_require_quantity():
    """D13: `entities[].quantity` is declared REQUIRED, the same way every other
    entity-item key already is - a strict-schema object with `additionalProperties:
    False` must list every key it wants filled in `required`, or the provider is never
    forced to reason about it at all."""
    entities = PARSE_OUTPUT_JSON_SCHEMA["properties"]["entities"]
    assert "quantity" in entities["items"]["required"], entities["items"]["required"]


def test_proceed_anyway_is_a_required_top_level_key_boolean_or_null():
    assert "proceed_anyway" in DECLARED_KEYS, DECLARED_KEYS
    props = PARSE_OUTPUT_JSON_SCHEMA["properties"]
    assert "proceed_anyway" in props, props.keys()
    assert props["proceed_anyway"] == {"type": ["boolean", "null"]}, props["proceed_anyway"]
    assert "proceed_anyway" in PARSE_OUTPUT_JSON_SCHEMA["required"]


def test_fallback_prompt_names_entities_quantity_and_proceed_anyway():
    """D13: 'the prompt change is published by the owner' - but the FALLBACK text
    (this constant) is what ships in this lane, and it must name both new keys by their
    wire name so the model has something to reason about even before publish."""
    assert "entities[].quantity" in SEMANTIC_PARSER_PROMPT, (
        "the fallback prompt never names entities[].quantity - the model has no reason "
        "to ever fill it"
    )
    assert "proceed_anyway" in SEMANTIC_PARSER_PROMPT, (
        "the fallback prompt never names proceed_anyway - the model has no reason to "
        "ever emit it"
    )


# --------------------------------------------------------------------------- #
# AC-1778 / AC-1787: the open-task hint block, and the instruction rule
# --------------------------------------------------------------------------- #


def test_fallback_prompt_names_the_open_task_instruction_rule():
    """AC-1778: the system prompt names the rule that a quantity given for a product in
    the open task sets entities[].quantity for it, whatever the current subject, and
    that add/drop/change/proceed/never-mind are read as instructions on the task."""
    prompt = SEMANTIC_PARSER_PROMPT
    lowered = prompt.lower()
    assert "open task" in lowered, "the prompt never names the open task at all"
    for verb in ("add", "drop", "proceed", "never mind"):
        assert verb in lowered, f"the prompt never teaches {verb!r} as a task instruction"


def _focus_with_tasks(tasks):
    """A bare stand-in for `Focus` carrying `.tasks` - see the module docstring for why
    this does not import `turn/task.py` or rely on `Focus` declaring the field."""
    from types import SimpleNamespace

    return SimpleNamespace(domains=[], customers=[], products=[], document=[], status=None, date_window=None, tasks=tasks)


def _stock_task(*, status="open", touched_at_turn=2):
    return {
        "kind": "stock_qty",
        "domain": "inventory",
        "status": status,
        "opened_at_turn": 1,
        "touched_at_turn": touched_at_turn,
        "slots": [
            {"key": "uuid-a", "label": "A", "value": 5},
            {"key": "uuid-b", "label": "B", "value": 60},
            {"key": "uuid-c", "label": "C", "value": None},
            {"key": "uuid-d", "label": "D", "value": None},
        ],
    }


def _ideation_task(*, status="open", touched_at_turn=1, pending_media=False):
    return {
        "kind": "ideation",
        "domain": "ideate",
        "status": status,
        "opened_at_turn": 1,
        "touched_at_turn": touched_at_turn,
        "slots": [],
        "pending_media": pending_media,
    }


def test_open_task_line_names_noted_and_missing_products():
    """AC-1778. `Open task: stock check. Noted: A x 5, B x 60. Still needs a quantity
    for: C, D.` - the exact sentence the UAC pins."""
    focus = _focus_with_tasks([_stock_task()])

    block = build_user_block(
        previous_response="(none)", latest_user_message="hi", pending_kind=None, focus=focus
    )

    assert (
        "Open task: stock check. Noted: A x 5, B x 60. Still needs a quantity for: C, D."
        in block
    ), block


def test_ideation_open_task_line_says_idea_in_progress():
    """AC-1787. `Open task: idea in progress.`, with ` (media menu open)` appended when
    `pending_media` is set."""
    focus = _focus_with_tasks([_ideation_task()])
    block = build_user_block(
        previous_response="(none)", latest_user_message="hi", pending_kind=None, focus=focus
    )
    assert "Open task: idea in progress." in block, block

    focus_media = _focus_with_tasks([_ideation_task(pending_media=True)])
    block_media = build_user_block(
        previous_response="(none)", latest_user_message="hi", pending_kind=None, focus=focus_media
    )
    assert "Open task: idea in progress. (media menu open)" in block_media, block_media


def test_most_recently_touched_task_prints_first():
    """D24(e): the parser hint lists every open task, most recently touched first."""
    older = _stock_task(touched_at_turn=1)
    newer = _ideation_task(touched_at_turn=5)
    focus = _focus_with_tasks([older, newer])

    block = build_user_block(
        previous_response="(none)", latest_user_message="hi", pending_kind=None, focus=focus
    )

    idea_pos = block.find("Open task: idea in progress.")
    stock_pos = block.find("Open task: stock check.")
    assert idea_pos != -1 and stock_pos != -1, block
    assert idea_pos < stock_pos, (
        "the ideation task (touched turn 5) must print before the stock task "
        f"(touched turn 1): {block!r}"
    )


def test_no_open_task_line_when_focus_carries_no_tasks():
    focus = _focus_with_tasks([])
    block = build_user_block(
        previous_response="(none)", latest_user_message="hi", pending_kind=None, focus=focus
    )
    assert "Open task:" not in block, block


def test_a_parked_task_still_prints_its_hint_line():
    """D22: parking is silent in the REPLY, never in the hint the parser reads next
    turn - a parked task must still be named so the parser can route a resume."""
    focus = _focus_with_tasks([_stock_task(status="parked")])
    block = build_user_block(
        previous_response="(none)", latest_user_message="hi", pending_kind=None, focus=focus
    )
    assert "Open task: stock check." in block, block
