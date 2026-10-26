"""SALES-TARGET-CHAT slice 2, UAC O5-1: the `opportunity` parser key is flag-gated by the prompt.

A raw template carrying the LOG OPPORTUNITY line turns `ParserConfig.opportunity` on and the strict
schema gains a required, nullable `opportunity` object {title, amount_rm, close_date}; a template
without the line (prod v63) keeps today's schema unchanged. Fake templates only.
"""
from __future__ import annotations

import json

import pytest

from app.services.chatbot.head import closed_lists_prompt
from tests.chatbot.test_chat_state_parser_input import (  # noqa: F401 - fixture + helper
    _fresh_prompt_cache,
    _resolve,
)

LINE = '== LOG OPPORTUNITY: order_status "log_opportunity", domain_hint "order" =='
CLOSED = "Rules {{current_date}}.\n" + closed_lists_prompt.MARKER + "\nlisted items.\n"
PLAIN = "Rules {{current_date}}.\nlisted items.\n"


def _schema(config):
    from app.services.chatbot.head import parser

    return config.json_schema or parser._base_schema(config)


def _nullable_object(prop: dict) -> bool:
    types = prop.get("type")
    if isinstance(types, list):
        return "object" in types and "null" in types
    options = prop.get("anyOf") or prop.get("oneOf") or []
    kinds = [o.get("type") for o in options]
    return "object" in kinds and "null" in kinds


def _object_part(prop: dict) -> dict:
    if prop.get("type") in ("object", ["object", "null"], ["null", "object"]):
        return prop
    return next(o for o in (prop.get("anyOf") or prop.get("oneOf")) if o.get("type") == "object")


def _baseline() -> dict:
    """Today's schema for a plain prompt: no state, no report fields, no by_words."""
    from app.services.chatbot.head import parser

    return parser.without_by_words(parser.without_report_fields(parser.PARSE_OUTPUT_JSON_SCHEMA))


@pytest.mark.parametrize("base", [CLOSED, PLAIN], ids=["closed_lists", "plain"])
def test_opportunity_key_only_with_its_section(monkeypatch, session_factory, base) -> None:
    """O5-1, line present: the flag is on and the strict schema carries the key."""
    config = _resolve(monkeypatch, session_factory, base + LINE + "\nsection text\n")
    assert config.opportunity is True
    schema = _schema(config)
    assert "opportunity" in schema["properties"] and "opportunity" in schema["required"]
    prop = schema["properties"]["opportunity"]
    assert _nullable_object(prop), prop
    inner = _object_part(prop)
    assert set(inner["properties"]) == {"title", "amount_rm", "close_date"}
    assert set(inner.get("required", [])) == {"title", "amount_rm", "close_date"}
    if base is PLAIN:
        stripped = json.loads(json.dumps(schema))
        stripped["properties"].pop("opportunity")
        stripped["required"].remove("opportunity")
        assert json.dumps(stripped, sort_keys=True) == json.dumps(_baseline(), sort_keys=True)


@pytest.mark.parametrize("base", [CLOSED, PLAIN], ids=["closed_lists", "plain"])
def test_opportunity_key_absent_without_its_section(monkeypatch, session_factory, base) -> None:
    """O5-1, line absent (v63): the flag is off and the schema is today's, unchanged."""
    config = _resolve(monkeypatch, session_factory, base + "section text\n")
    assert config.opportunity is False
    schema = _schema(config)
    assert "opportunity" not in schema["properties"] and "opportunity" not in schema["required"]
    if base is PLAIN:
        assert json.dumps(schema, sort_keys=True) == json.dumps(_baseline(), sort_keys=True)
