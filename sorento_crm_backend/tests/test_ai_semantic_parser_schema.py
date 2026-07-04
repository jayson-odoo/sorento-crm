"""Contract tests for the Semantic Parser schema (M0).

Covers the ``ParseResult`` Pydantic model, the ``fallback_parse`` degrade path,
the ``date_range.from`` alias round-trip, and the hand-written
``PARSE_RESULT_JSON_SCHEMA`` OpenAI strict-mode compliance (every top-level
property required + ``additionalProperties: false``).
"""
from __future__ import annotations

import json

from app.schemas.ai_semantic_parser import (
    PARSE_RESULT_JSON_SCHEMA,
    PARSE_RESULT_SCHEMA_NAME,
    ParseResult,
    fallback_parse,
)

_FULL_VALID = {
    "standalone_query": "list DOs for ACME last month",
    "intent": "data_query",
    "language": "en",
    "confidence": 0.82,
    "form_target": None,
    "entities": {
        "record_ref": None,
        "domain": "orders",
        "customer": "ACME",
        "product": None,
        "date_range": {"from": "2026-06-01", "to": "2026-06-30"},
        "time_scope": "range",
    },
    "signals": {
        "targets_open_record": False,
        "is_write_intent": False,
        "needs_clarification": False,
        "clarify_question": None,
        "clarify_options": [],
    },
}


def test_model_validate_json_full_object():
    parsed = ParseResult.model_validate_json(json.dumps(_FULL_VALID))
    assert parsed.intent == "data_query"
    assert parsed.language == "en"
    assert parsed.confidence == 0.82
    assert parsed.entities.domain == "orders"
    assert parsed.entities.customer == "ACME"
    assert parsed.entities.time_scope == "range"
    assert parsed.entities.date_range.from_ == "2026-06-01"
    assert parsed.entities.date_range.to == "2026-06-30"
    assert parsed.signals.is_write_intent is False
    assert parsed.signals.clarify_options == []


def test_fallback_parse_is_unknown_and_seeds_query():
    fb = fallback_parse("hi there")
    assert fb.intent == "unknown"
    assert fb.standalone_query == "hi there"
    # Defaults are safe: no write, no clarify, not targeting a record.
    assert fb.signals.is_write_intent is False
    assert fb.signals.needs_clarification is False
    assert fb.signals.targets_open_record is False


def test_fallback_parse_handles_empty():
    assert fallback_parse("").intent == "unknown"
    assert fallback_parse("").standalone_query == ""


def test_date_range_from_alias_round_trips():
    # Ingest via the wire alias "from" → stored on `from_`.
    parsed = ParseResult.model_validate(_FULL_VALID)
    assert parsed.entities.date_range.from_ == "2026-06-01"
    # Dump BY ALIAS reproduces the wire key "from" (never "from_").
    dumped = parsed.model_dump(by_alias=True)
    assert dumped["entities"]["date_range"]["from"] == "2026-06-01"
    assert "from_" not in dumped["entities"]["date_range"]


def _assert_strict(schema: dict, path: str = "root"):
    """Every object node must forbid extra props and require every property."""
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False, f"{path}: additionalProperties must be False"
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert props == required, f"{path}: required {required} must equal properties {props}"
        for name, sub in schema.get("properties", {}).items():
            _assert_strict(sub, f"{path}.{name}")


def test_json_schema_is_openai_strict_compliant():
    schema = PARSE_RESULT_JSON_SCHEMA
    assert isinstance(schema, dict)
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    top_props = set(schema["properties"].keys())
    top_required = set(schema["required"])
    assert top_props == top_required, "every top-level property must be in required"
    # Recursively enforce strictness on nested objects (entities, date_range, signals).
    _assert_strict(schema)


def test_json_schema_name_constant():
    assert PARSE_RESULT_SCHEMA_NAME == "semantic_parse_result"
