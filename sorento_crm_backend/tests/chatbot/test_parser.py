"""The parser seam: the strict schema, the registry fallback and the failure contract.

AC-104 (the prompt comes from the registry, fallback = the live n8n system message
verbatim) and AC-105 / R5 (strict structured output; anything else is a failed stage, no
soft default). No LLM is called here - `parse` is exercised against a fake provider.
"""
from __future__ import annotations

import json

import pytest

from app.services.ai_prompt_registry import PROMPT_KEYS, render
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT
from tests._pg_fixture import pg_session


class TestPromptRegistration:
    def test_the_key_is_registered_and_active(self) -> None:
        spec = PROMPT_KEYS["chatbot_semantic_parser"]
        assert spec.active is True
        assert spec.variables == ["current_date"]

    def test_the_fallback_is_the_live_n8n_system_message_verbatim(self) -> None:
        """AC-104. Two mechanical edits only: n8n's `=` marker and its `$now` expression."""
        assert PROMPT_KEYS["chatbot_semantic_parser"].fallback() == SEMANTIC_PARSER_PROMPT
        assert SEMANTIC_PARSER_PROMPT.startswith("You are the Sorento Semantic Parser.")
        assert not SEMANTIC_PARSER_PROMPT.startswith("=")
        # The prompt's own OUTPUT block, which is what the strict schema is built from.
        assert "== OUTPUT (exactly these keys, no others, no comments) ==" in SEMANTIC_PARSER_PROMPT
        # No n8n expression survives: the registry substitutes {{current_date}} instead.
        assert "$now" not in SEMANTIC_PARSER_PROMPT

    def test_rendering_substitutes_the_date_where_n8n_put_it(self) -> None:
        with pg_session() as db:
            text, _version = render(
                db, "chatbot_semantic_parser", current_date="Thursday, 04 September 2026"
            )
        assert "CURRENT DATE: Thursday, 04 September 2026" in text
        assert "{{current_date}}" not in text

    def test_a_missing_variable_is_refused_rather_than_rendered_blank(self) -> None:
        with pg_session() as db, pytest.raises(ValueError, match="current_date"):
            render(db, "chatbot_semantic_parser")


class TestStrictSchema:
    def test_it_forbids_extra_keys_at_the_provider(self) -> None:
        """"exactly these keys, no others" becomes a guarantee, not an instruction."""
        assert parser_mod.PARSE_OUTPUT_JSON_SCHEMA["additionalProperties"] is False

    def test_every_declared_key_is_required(self) -> None:
        schema = parser_mod.PARSE_OUTPUT_JSON_SCHEMA
        assert set(schema["required"]) == set(schema["properties"])

    def test_it_declares_the_keys_the_prompt_declares(self) -> None:
        """The schema and the prompt's OUTPUT block must not drift apart."""
        block = SEMANTIC_PARSER_PROMPT.split("== OUTPUT (exactly these keys")[1]
        for key in parser_mod.PARSE_OUTPUT_JSON_SCHEMA["properties"]:
            assert f'"{key}"' in block, f"{key} is in the schema but not in the prompt"


class _FakeProvider:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})

        class _Result:
            content = self._content

        return _Result()


@pytest.fixture()
def config() -> parser_mod.ParserConfig:
    return parser_mod.ParserConfig(
        system_prompt="stub",
        prompt_version=3,
        provider="openai",
        model="gpt-test",
        api_key="sk-test",
    )


def _valid() -> dict:
    return {key: None for key in parser_mod.DECLARED_KEYS}


def _install(monkeypatch, provider) -> None:
    import app.services.llm_provider as llm

    monkeypatch.setattr(llm, "get_provider", lambda *_a, **_k: provider)


class TestParse:
    def test_it_passes_the_strict_schema_and_temperature_zero(self, monkeypatch, config) -> None:
        provider = _FakeProvider(json.dumps(_valid()))
        _install(monkeypatch, provider)
        parser_mod.parse(config, "user block")
        call = provider.calls[0]
        assert call["json_schema"] is parser_mod.PARSE_OUTPUT_JSON_SCHEMA
        assert call["temperature"] == 0.0

    def test_an_unknown_key_is_tolerated(self, monkeypatch, config) -> None:
        """The plan names this risk: a model that occasionally adds a key must not fail
        a turn that works today."""
        payload = _valid() | {"a_key_nobody_declared": 1}
        _install(monkeypatch, _FakeProvider(json.dumps(payload)))
        assert parser_mod.parse(config, "b")["a_key_nobody_declared"] == 1

    def test_a_missing_key_is_rejected_and_names_it(self, monkeypatch, config) -> None:
        payload = _valid()
        del payload["domain_hint"]
        _install(monkeypatch, _FakeProvider(json.dumps(payload)))
        with pytest.raises(parser_mod.ParserError, match="domain_hint"):
            parser_mod.parse(config, "b")

    def test_empty_content_is_a_failure_not_an_empty_object(self, monkeypatch, config) -> None:
        """A truncated structured emission would validate as `{}` and route on nothing."""
        _install(monkeypatch, _FakeProvider("   "))
        with pytest.raises(parser_mod.ParserError, match="empty"):
            parser_mod.parse(config, "b")

    def test_non_json_content_is_a_failure(self, monkeypatch, config) -> None:
        _install(monkeypatch, _FakeProvider("I'm afraid I can't do that"))
        with pytest.raises(parser_mod.ParserError, match="non-JSON"):
            parser_mod.parse(config, "b")

    def test_a_provider_exception_is_a_failure_not_a_default(self, monkeypatch, config) -> None:
        class _Boom:
            def chat(self, *_a, **_k):
                raise TimeoutError("read timeout")

        _install(monkeypatch, _Boom())
        with pytest.raises(parser_mod.ParserError, match="read timeout"):
            parser_mod.parse(config, "b")


class TestUserBlock:
    def test_it_is_the_two_lines_the_n8n_agent_node_sends(self) -> None:
        block = parser_mod.build_user_block(
            previous_response="Previous turn (promotion): returned 1 records",
            latest_user_message="the august one",
            pending_kind=None,
        )
        assert block == (
            "Previous response: Previous turn: returned 1 records\n"
            "Current user message: the august one"
        )

    def test_the_pending_marker_is_the_one_addition_s1_makes(self) -> None:
        """R3 / D11: stated as a fact, not left to be inferred from the previous reply."""
        block = parser_mod.build_user_block(
            previous_response="Would you like me to escalate this?",
            latest_user_message="yes",
            pending_kind="escalation_offer",
        )
        assert block.endswith(
            "Pending: the assistant is waiting for a escalation_offer reply."
        )
