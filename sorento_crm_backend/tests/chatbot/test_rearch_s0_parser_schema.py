"""S0 - one parser schema, v3 shape, plus `document`/`status`/`anaphora.
backward_reference`/`entities[].hint_confident` (AC-1506, PLAN-chatbot-turn-rearch.md).

`head/parser.py::_build_json_schema` already takes no `prompt_version` argument and
already returns the identical object on every call - there is no dual v1/v3 branch to
retire there today. What IS still true today, and is this file's real red: the schema
does not carry the new keys, and `SEMANTIC_PARSER_PROMPT_SLIM` (the retired v1-era
prompt body) still exists in `app/services/chatbot_parser_prompt.py`. `V1_ONLY_KEYS`,
`emits_v3` and `schema_for` do not exist anywhere in this tree today either - included
in the grep guard anyway (AC-1506's own list), so the guard keeps meaning something once
the coder's later slices might reintroduce one of these names.
"""
from __future__ import annotations

import pathlib

import pytest

RETIRED_NAMES = ["V1_ONLY_KEYS", "emits_v3", "SEMANTIC_PARSER_PROMPT_SLIM", "schema_for"]

CHATBOT_PACKAGE = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot"
PARSER_PROMPT_FILE = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot_parser_prompt.py"
)


def _source_files() -> list[pathlib.Path]:
    files = list(CHATBOT_PACKAGE.rglob("*.py"))
    if PARSER_PROMPT_FILE.exists():
        files.append(PARSER_PROMPT_FILE)
    return files


@pytest.mark.parametrize("name", RETIRED_NAMES)
def test_retired_name_does_not_appear_in_chatbot_or_parser_prompt(name):
    hits = [f for f in _source_files() if name in f.read_text(encoding="utf-8", errors="ignore")]
    assert not hits, f"{name} still referenced in: {hits}"


def _schema():
    from app.services.chatbot.head.parser import _build_json_schema

    return _build_json_schema()


def test_schema_builder_is_stable_across_calls():
    """No version-dependent branch: two calls (standing in for "a v1-looking" and a
    "v3-looking" prompt text, since the builder takes no prompt-text argument at all
    today - see module docstring) return an identical schema."""
    assert _schema() == _schema()


def test_schema_declares_document_and_status_keys():
    schema = _schema()
    props = schema["properties"]
    assert "document" in props, props.keys()
    assert "status" in props, props.keys()


def test_schema_declares_anaphora_backward_reference():
    schema = _schema()
    props = schema["properties"]
    assert "anaphora" in props, props.keys()
    anaphora = props["anaphora"]
    assert "backward_reference" in anaphora.get("properties", {}), anaphora


def test_schema_entities_items_declare_hint_confident():
    schema = _schema()
    entities = schema["properties"]["entities"]
    item_props = entities["items"]["properties"]
    assert "hint_confident" in item_props, item_props.keys()
