"""REPORT-SMART-L fix round (live spot check, PR note 6335349880): the parser's JSON schema
follows the prompt version's own text.

A prompt version that never declares `compare_to` must not be offered the count measures
(customers, orders, products) or the `compare_to` property: the model would be forced to emit
keys its prompt does not describe. A version whose text declares `compare_to` gets the extended
enum and the required property. Tested through `resolve_config` on a template string, then the
schema `parse` sends to the provider, for the plain, state and closed-lists variants.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.chatbot.head import parser as P
from app.services.chatbot.head.chat_state_prompt import HEADING
from app.services.chatbot.head.closed_lists_prompt import MARKER as CLOSED_MARKER
from app.services.chatbot.lanes.business import report_ask as RA

BASE = "You read one customer message into JSON. Reports: `measure` qty | amount | null."
DECLARES = " `compare_to` previous_period | last_year | null; measure customers | orders | products."
VARIANTS = {
    "plain": "",
    "state": "\n" + HEADING + "\nstate text",
    "closed": "\n" + CLOSED_MARKER + "\nlists",
    "closed_state": "\n" + CLOSED_MARKER + "\nlists\n" + HEADING + "\nstate text",
}
OLD_MEASURES = {"qty", "amount", None}


def schema_for(monkeypatch, template: str) -> dict[str, Any]:
    """The schema `parse` would send for a prompt version holding `template`."""
    from app.services import chatbot_prompt_vars
    from app.services.ai_assistant_service import AIAssistantConfigService
    from app.services.chatbot import llm_call
    from app.services.chatbot.head import closed_lists_index
    from app.services import llm_provider

    monkeypatch.setattr(P, "get_prompt", lambda db, key, override_version_id=None: SimpleNamespace(text=template))
    monkeypatch.setattr(P, "render_resolved", lambda db, key, resolved, **kw: (resolved.text, 1))
    monkeypatch.setattr(P, "agent_model", lambda db, key: (None, None))
    monkeypatch.setattr(
        AIAssistantConfigService, "get",
        lambda self: SimpleNamespace(provider="openai", model="gpt-test"),
    )
    monkeypatch.setattr(AIAssistantConfigService, "__init__", lambda self, db: None)
    monkeypatch.setattr(llm_provider, "resolve_api_key", lambda config, provider: "sk-test")
    monkeypatch.setattr(closed_lists_index, "read_mode", lambda db: closed_lists_index.MODE_FULL
                        if hasattr(closed_lists_index, "MODE_FULL") else "full")
    monkeypatch.setattr(chatbot_prompt_vars, "closed_list_enum", lambda db: ["a", "b"])
    monkeypatch.setattr(P, "reasoning_effort_setting", lambda db: "off")

    config = P.resolve_config(MagicMock(), current_date="2026-10-22")
    seen: dict[str, Any] = {}

    def fake_chat(*args: Any, **kwargs: Any) -> Any:
        seen["schema"] = kwargs["json_schema"]
        raise RuntimeError("stop after the schema is captured")

    monkeypatch.setattr(llm_call, "chat", fake_chat)
    with pytest.raises(P.ParserError):
        P.parse(config, "x")
    return seen["schema"]


@pytest.mark.parametrize("variant", VARIANTS)
def test_a_prompt_without_compare_to_keeps_the_old_measure_enum_and_no_compare_to(monkeypatch, variant) -> None:
    schema = schema_for(monkeypatch, BASE + VARIANTS[variant])
    assert set(schema["properties"]["measure"]["enum"]) == OLD_MEASURES, variant
    assert "compare_to" not in schema["properties"], variant
    assert "compare_to" not in schema["required"], variant


@pytest.mark.parametrize("variant", VARIANTS)
def test_a_prompt_declaring_compare_to_gets_the_extended_enum_and_the_required_property(monkeypatch, variant) -> None:
    schema = schema_for(monkeypatch, BASE + DECLARES + VARIANTS[variant])
    assert set(schema["properties"]["measure"]["enum"]) == {*RA.METRICS, None}, variant
    assert set(schema["properties"]["compare_to"]["enum"]) == {*RA.COMPARE_TO, None}, variant
    assert "compare_to" in schema["required"], variant


@pytest.mark.parametrize("variant", VARIANTS)
def test_near_miss_the_other_properties_are_the_same_either_way(monkeypatch, variant) -> None:
    old = schema_for(monkeypatch, BASE + VARIANTS[variant])
    new = schema_for(monkeypatch, BASE + DECLARES + VARIANTS[variant])
    assert set(new["properties"]) - set(old["properties"]) == {"compare_to"}, variant
    assert set(new["required"]) - set(old["required"]) == {"compare_to"}, variant
