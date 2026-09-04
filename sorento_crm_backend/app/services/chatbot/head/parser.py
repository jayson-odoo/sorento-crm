"""The semantic parser call (AC-104, AC-105, R5).

One LLM call per turn. It is the ONLY place in the engine that reads the customer's words
(D11); everything after it is deterministic over structured state.

R5 closes H44 at the source: the call passes a STRICT `json_schema` to the provider, so a
well-formed object is guaranteed whenever the provider answers at all. A provider error, a
timeout, or a response that still fails validation is a FAILED `understood` stage - never a
soft default, never `intent = unknown` routed as if it were a real answer.

**No DB session is held across this call.** The plan's capacity section is explicit about
it and the 96/100-connection incident is the evidence: `resolve_config` collects everything
the call needs, the caller closes its session, the call runs, the caller reopens. The
signature enforces the discipline - nothing here takes a `Session`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.services.ai_prompt_registry import agent_model, render

logger = logging.getLogger(__name__)

PROMPT_KEY = "chatbot_semantic_parser"

# The parser's own error reply, byte-identical to what the spine sends today when
# `sub-query-reformulator` fails (`sub-error-logger`).
PARSER_ERROR_REPLY = (
    "Sorry, I ran into a problem understanding that. Please try again in a moment."
)

PARSER_MAX_TOKENS = 2048

# NOT bounded by a per-call timeout, and deliberately not pretending to be. The plan's
# timeout table names 8 s for the parser, but `llm_provider.LLMProvider.chat` has no
# timeout parameter at all - each provider builds its own SDK client - so wiring one means
# changing that shared signature and all three implementations, which is core work outside
# this slice. A declared-but-unapplied constant is worse than none: it reads as a
# guarantee. Follow-up: add `timeout` to `LLMProvider.chat` and pass the plan's value here.


class ParserError(RuntimeError):
    """The parse could not be completed. The caller fails the `understood` stage."""


@dataclass(frozen=True)
class ParserConfig:
    """Everything the LLM call needs, resolved BEFORE the session is released."""

    system_prompt: str
    prompt_version: int | None
    provider: str
    model: str
    api_key: str


def _build_json_schema() -> dict[str, Any]:
    """The strict 26-key `ParseOutput` schema the provider is held to (AC-105).

    Built from the prompt's own OUTPUT block. `additionalProperties: false` is what makes
    "exactly these keys, no others" a provider guarantee instead of an instruction, and
    every key is `required` so a silently missing one is a validation failure rather than
    a `None` that reads downstream as "the customer said nothing about it".

    Value types stay permissive (`type: [...]` unions rather than enums) on purpose: the
    parser legitimately emits values the enum does not cover yet, `output_exchange`
    normalises several of them (`"null"` to null, a compound access level to a tier
    token), and rejecting them at the provider would fail turns that work today. The
    vocabularies in `contracts.py` are what the code is written against; this schema is
    what the WIRE is held to.
    """
    string_or_null = {"type": ["string", "null"]}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "message_type": {"type": "string"},
            "intent_hint": string_or_null,
            "domain_hint": string_or_null,
            "scope_intent": string_or_null,
            "is_affirmative": {"type": ["boolean", "null"]},
            "user_goal": string_or_null,
            "access_levels": {"type": "array", "items": {"type": "string"}},
            "broaden_axis": string_or_null,
            "date_mode": string_or_null,
            "date_filter_start": string_or_null,
            "date_filter_end": string_or_null,
            "match_mode": string_or_null,
            "demand_qty": {"type": ["number", "string", "null"]},
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "raw": string_or_null,
                        "hint": string_or_null,
                        "canonical_code": string_or_null,
                        "current_message": {"type": ["boolean", "null"]},
                        "confident": {"type": ["boolean", "null"]},
                    },
                    "required": ["raw", "hint", "canonical_code", "current_message", "confident"],
                },
            },
            "entity_op": string_or_null,
            "scope_exclusive": {"type": ["boolean", "null"]},
            "requested_attributes": {"type": "array", "items": {"type": "string"}},
            "contains_flyer": {"type": ["boolean", "null"]},
            "reference_positions": {"type": "array", "items": {"type": "number"}},
            "reference_target": string_or_null,
            "person_mention": string_or_null,
            "is_active": {"type": ["boolean", "string", "null"]},
            "order_status": string_or_null,
            "correction": {"type": ["boolean", "null"]},
            "routing": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "suggested_team": string_or_null,
                    "suggested_agent": string_or_null,
                    "team_source": string_or_null,
                },
                "required": ["suggested_team", "suggested_agent", "team_source"],
            },
            "escalation": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "is_escalation_confirmation": {"type": ["boolean", "null"]},
                    "company_pick": string_or_null,
                },
                "required": ["is_escalation_confirmation", "company_pick"],
            },
        },
        "required": [
            "message_type",
            "intent_hint",
            "domain_hint",
            "scope_intent",
            "is_affirmative",
            "user_goal",
            "access_levels",
            "broaden_axis",
            "date_mode",
            "date_filter_start",
            "date_filter_end",
            "match_mode",
            "demand_qty",
            "entities",
            "entity_op",
            "scope_exclusive",
            "requested_attributes",
            "contains_flyer",
            "reference_positions",
            "reference_target",
            "person_mention",
            "is_active",
            "order_status",
            "correction",
            "routing",
            "escalation",
        ],
    }


PARSE_OUTPUT_JSON_SCHEMA = _build_json_schema()
PARSE_OUTPUT_SCHEMA_NAME = "chatbot_parse_output"
# The keys the schema declares. Validation is "every required key present, nothing
# unknown kept" - unknown keys are IGNORED (the risk the plan names: a model that
# occasionally adds one must not fail a turn), missing ones are REJECTED.
DECLARED_KEYS: frozenset[str] = frozenset(PARSE_OUTPUT_JSON_SCHEMA["required"])


def resolve_config(db: Session, *, current_date: str) -> ParserConfig:
    """Read the prompt, the per-key model override and the API key. Session-bound.

    Call this, then CLOSE the session, then call `parse`. Everything that needs the
    database happens here so nothing needs it while the provider is answering.
    """
    from app.services.ai_assistant_service import AIAssistantConfigService
    from app.services.llm_provider import resolve_api_key

    system_prompt, prompt_version = render(db, PROMPT_KEY, current_date=current_date)
    provider_override, model_override = agent_model(db, PROMPT_KEY)

    config = AIAssistantConfigService(db).get()
    if config is None:
        raise ParserError("AI assistant configuration is not set")
    provider = provider_override or config.provider
    model = model_override or config.model
    api_key = resolve_api_key(config, provider)
    if not api_key:
        raise ParserError(f"no API key configured for provider {provider!r}")
    return ParserConfig(
        system_prompt=system_prompt,
        prompt_version=prompt_version,
        provider=provider,
        model=model,
        api_key=api_key,
    )


def build_user_block(
    *, previous_response: Any, latest_user_message: Any, pending_kind: str | None
) -> str:
    """The user turn, in the same two lines the n8n `AI Agent` node sends.

    The ONE addition S1 makes (and the only prompt change allowed before S1b): the
    persisted `pending` marker, stated as a fact rather than left for the model to infer
    from the previous reply's wording (R3, D11). The legacy string is still present in
    `previous_response`, so a session written by n8n and one written by the CRM both
    parse the same way during the migration window.
    """
    import re

    previous = re.sub(
        r"^Previous turn \([a-z_]+\)", "Previous turn", str(previous_response or ""), flags=re.I
    )
    lines = [
        f"Previous response: {previous}",
        f"Current user message: {latest_user_message}",
    ]
    if pending_kind:
        lines.append(f"Pending: the assistant is waiting for a {pending_kind} reply.")
    return "\n".join(lines)


def parse(config: ParserConfig, user_block: str) -> dict[str, Any]:
    """One structured-output call. Raises `ParserError`; never returns a default.

    NOTHING here touches the database. That is the rule the capacity section states and
    the reason `ParserConfig` exists.
    """
    from app.services.llm_provider import get_provider

    messages = [
        {"role": "system", "content": config.system_prompt},
        {"role": "user", "content": user_block},
    ]
    try:
        provider = get_provider(config.provider, config.api_key, config.model)
        result = provider.chat(
            messages,
            temperature=0.0,
            model=config.model,
            max_tokens=PARSER_MAX_TOKENS,
            json_schema=PARSE_OUTPUT_JSON_SCHEMA,
            json_schema_name=PARSE_OUTPUT_SCHEMA_NAME,
        )
    except Exception as exc:  # noqa: BLE001 - provider/transport failure is a failed stage
        raise ParserError(f"parser provider call failed: {exc}") from exc

    content = (result.content or "").strip()
    if not content:
        # An empty structured emission (e.g. an Anthropic max_tokens truncation with no
        # tool_use) would validate as `{}` and route confidently on nothing.
        raise ParserError("parser returned empty content")
    try:
        parsed = json.loads(content)
    except Exception as exc:  # noqa: BLE001
        raise ParserError(f"parser returned non-JSON content: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ParserError("parser returned a non-object")
    missing = DECLARED_KEYS - set(parsed)
    if missing:
        raise ParserError(f"parser output missing required key(s): {', '.join(sorted(missing))}")
    return parsed
