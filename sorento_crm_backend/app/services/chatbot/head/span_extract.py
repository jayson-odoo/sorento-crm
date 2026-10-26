"""The span pass (ENTITY-EXTRACT-MATCH S2): a small model names the mentions of the message, code matches them.

A parser version that carries the `== LOOKUP SPANS ==` line gets this instead of the n-gram lookup of
`lookup_lists.shortlist`: one schema-forced call returns the spans that name a record ("kimlan", "srt", "马桶"),
`list_resolver.resolve` places each on the rows the contact may see, and the lookup blocks hold only those rows.
Like the parser's own call it needs no database session, so `resolve_config` runs inside the turn's session and
`extract` after it is closed. The model follows the parser's ladder (contact override, tag, this prompt's
`production` label, global config), fed the same `llm_choice` the parser got.

Advisory like the lookup: `extract` never raises. A failed, late or unreadable answer leaves the turn on the n-gram lines.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.services.chatbot import llm_call
from app.services.chatbot.head.list_resolver import SPAN_TYPES, Span

logger = logging.getLogger(__name__)

PROMPT_KEY = "chatbot_span_extractor"
FEATURE = "chatbot_span_extract"
SCHEMA_NAME = "chatbot_span_extraction"
#: The call's own budget in seconds, retries and rate-limit waits included (p90 measured 1.2 s).
SPAN_TIMEOUT_SECONDS = 4.0
MAX_TOKENS = 512
#: A message names a handful of things; more than this is a runaway answer.
MAX_SPANS = 24
SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["spans"],
    "properties": {
        "spans": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "type"],
                "properties": {"text": {"type": "string"}, "type": {"type": "string", "enum": list(SPAN_TYPES)}},
            },
        }
    },
}


@dataclass(frozen=True)
class SpanConfig:
    """Everything the call needs, resolved while the session is open."""

    system_prompt: str
    prompt_version: int | None
    provider: str
    model: str
    api_key: str = field(repr=False)
    model_source: str


@dataclass(frozen=True)
class SpanAnswer:
    #: None when the model answered but the answer was unreadable (still billed, so the usage stays).
    spans: list[Span] | None
    usage: dict[str, Any]
    ms: int


def resolve_config(db: Session, *, llm_choice=None) -> SpanConfig:
    """The span prompt, its provider and model, and the API key. Session-bound; raises when no key is set."""
    from app.services import ai_prompt_registry
    from app.services.ai_assistant_service import AIAssistantConfigService
    from app.services.contact_llm_choice import apply_choice

    resolved = ai_prompt_registry.get_prompt(db, PROMPT_KEY)
    system_prompt, version = ai_prompt_registry.render_resolved(db, PROMPT_KEY, resolved)
    provider_label, model_label = ai_prompt_registry.agent_model(db, PROMPT_KEY)
    config = AIAssistantConfigService(db).get()
    if config is None:
        raise ValueError("AI assistant configuration is not set")
    provider, model, api_key, source = apply_choice(
        llm_choice, config, provider_label or config.provider, model_label or config.model,
        model_from_label=bool(model_label),
    )
    if not api_key:
        raise ValueError(f"no API key configured for provider {provider!r}")
    return SpanConfig(system_prompt, version, provider, model, api_key, source)


def _read(content: str | None) -> list[Span]:
    """The spans of the model's JSON, or ValueError when the answer is not `{"spans": [{text, type}]}`."""
    parsed = json.loads(content or "")
    items = parsed.get("spans") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        raise ValueError("the span answer holds no spans list")
    spans: list[Span] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            continue
        kind = item.get("type")
        spans.append(Span(item["text"].strip(), kind if kind in SPAN_TYPES else None))
    return spans[:MAX_SPANS]


def extract(config: SpanConfig, message: str) -> SpanAnswer | None:
    """The model's answer to `message`, or None when the call fails or times out. Never raises."""
    started = time.perf_counter()
    try:
        result = llm_call.chat(
            config.provider,
            config.api_key,
            config.model,
            [{"role": "system", "content": config.system_prompt}, {"role": "user", "content": message}],
            deadline_seconds=SPAN_TIMEOUT_SECONDS,
            temperature=0.0,
            max_tokens=MAX_TOKENS,
            json_schema=SCHEMA,
            json_schema_name=SCHEMA_NAME,
            timeout=SPAN_TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001 - advisory: the n-gram lines take over
        logger.warning("chatbot: span call failed; using the n-gram lookup", exc_info=True)
        return None
    ms = int((time.perf_counter() - started) * 1000)
    usage = {
        "provider": config.provider,
        "model": config.model,
        "prompt_tokens": int(getattr(result, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(result, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(result, "total_tokens", 0) or 0),
        # NULL when the provider reported none (CU-2); `ChatResult` carries 0 for that.
        "cached_tokens": int(getattr(result, "cached_tokens", 0) or 0) or None,
    }
    try:
        spans: list[Span] | None = _read(getattr(result, "content", None))
    except Exception:  # noqa: BLE001 - billed, but unreadable
        logger.warning("chatbot: span answer unreadable; using the n-gram lookup")
        spans = None
    return SpanAnswer(spans, usage, ms)
