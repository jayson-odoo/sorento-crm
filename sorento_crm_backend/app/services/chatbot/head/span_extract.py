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
#: The sentence a span prompt carries when it asks for a per-span plain English "meaning"; the migration appends the
#: whole paragraph, and a prompt holding this sentence gets the schema with `meaning`.
MEANING_ASK = 'For each span also give "meaning".'
MEANING_PARAGRAPH = (
    "\n\n" + MEANING_ASK + " When the span is written in a language other than English, or gives a measurement in "
    "a unit other than millimetres, \"meaning\" is the plain English form of the span, with any size in millimetres "
    "written as a number followed by mm. When the span is already English and needs no conversion, or you are not "
    "sure what it means, \"meaning\" is null. Never invent a meaning."
)


def _schema(with_meaning: bool) -> dict[str, Any]:
    props: dict[str, Any] = {"text": {"type": "string"}, "type": {"type": "string", "enum": list(SPAN_TYPES)}}
    required = ["text", "type"]
    if with_meaning:
        props["meaning"] = {"type": ["string", "null"]}
        required.append("meaning")
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["spans"],
        "properties": {
            "spans": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": False, "required": required, "properties": props},
            }
        },
    }


#: The schema with `meaning`; a v1 prompt (which never asks for it) is sent `SCHEMA_V1`, see `span_schema`.
SCHEMA: dict[str, Any] = _schema(True)
SCHEMA_V1: dict[str, Any] = _schema(False)


def span_schema(system_prompt: str) -> dict[str, Any]:
    """The meaning schema only when the prompt asks for meanings."""
    return SCHEMA if MEANING_ASK in (system_prompt or "") else SCHEMA_V1


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
    #: None when there are no spans to use: the call failed or the answer was unreadable (`failure` says which).
    spans: list[Span] | None
    usage: dict[str, Any]
    ms: int
    #: "timeout" | "call_error" | "invalid_answer" | None. An unreadable answer was still billed, so its usage stays.
    failure: str | None = None


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
        meaning = item.get("meaning")
        meaning = meaning.strip() if isinstance(meaning, str) and meaning.strip() else None
        spans.append(Span(item["text"].strip(), kind if kind in SPAN_TYPES else None, meaning))
    return spans[:MAX_SPANS]


def extract(config: SpanConfig, message: str) -> SpanAnswer | None:
    """The model's answer to `message`; a failed or late call comes back as an answer with `failure` set. Never raises."""
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
            json_schema=span_schema(config.system_prompt),
            json_schema_name=SCHEMA_NAME,
            timeout=SPAN_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - advisory: the n-gram lines take over
        logger.warning("chatbot: span call failed; using the n-gram lookup", exc_info=True)
        timed_out = isinstance(exc, llm_call.TimedOut)
        return SpanAnswer(None, {}, int((time.perf_counter() - started) * 1000), "timeout" if timed_out else "call_error")
    ms = int((time.perf_counter() - started) * 1000)
    usage = {
        "provider": config.provider,
        "model": config.model,
        "prompt_tokens": int(getattr(result, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(result, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(result, "total_tokens", 0) or 0),
        # A recorded 0 when the provider reported none, as the parser stores it: NULL reads as cache-unknown and
        # leaves the call (and the turn's cost) unpriced (`analytics_connector.prices.cost_sql`).
        "cached_tokens": int(getattr(result, "cached_tokens", 0) or 0),
    }
    try:
        spans: list[Span] | None = _read(getattr(result, "content", None))
    except Exception:  # noqa: BLE001 - billed, but unreadable
        logger.warning("chatbot: span answer unreadable; using the n-gram lookup")
        spans = None
    return SpanAnswer(spans, usage, ms, None if spans is not None else "invalid_answer")


def word_home(row: Any, text: str) -> str | None:
    """Where one of a lookup row's texts came from (`LookupRow.homes`, parallel to `texts`)."""
    if not getattr(row, "homes", None):
        return None
    try:
        return row.homes[row.texts.index(text)]
    except (ValueError, IndexError):
        return None


def _best_text(row: Any, scores: dict[str, float]) -> dict[str, Any]:
    if not scores:
        return {"score": 0.0, "text": None, "home": None}
    text, score = max(scores.items(), key=lambda kv: kv[1])
    return {"score": round(float(score), 4), "text": text, "home": word_home(row, text)}


def explain_phrase(phrase: str, rows: list, embed: Any) -> dict[str, Any]:
    """The Embeddings screen's "Try a phrase": the live resolver's verdict on `phrase` over `rows`, and per
    candidate row what each signal (spelling, vector, partial) saw against that list's floors."""
    from app.services.chatbot.head import candidates as _candidates
    from app.services.chatbot.head import lookup_lists as _lookup_lists
    from app.services.chatbot.head.list_resolver import (
        FLOORS, _FLOORS_OTHER, _meaning_floor, _prepare, _score_list, resolve,
    )

    TRY_LIMIT = 8
    span = Span(phrase)
    verdict = resolve([span], rows, embed=embed)[0].status

    folded = _lookup_lists._fold(phrase)
    grams = _candidates.trigrams(folded)
    indexes = _prepare(rows)
    meaning = None
    if embed is not None and indexes:
        texts = sorted({t[1] for ix in indexes.values() for t in ix.texts})
        meaning = _lookup_lists._meaning(embed, [phrase], texts, any_model=True)

    pool: list[tuple[bool, float, dict[str, Any]]] = []
    for name, index in indexes.items():
        floors = {**FLOORS.get(name, _FLOORS_OTHER)}
        floors["meaning"] = _meaning_floor(embed, name)
        scored = _score_list(index, folded, grams)
        per_row_spell: dict[int, dict[str, float]] = {}
        per_row_vec: dict[int, dict[str, float]] = {}
        for i, text, f, g, _w in index.texts:
            spell = 1.0 if f == folded else _candidates.similarity(grams, g)
            if spell > 0:
                per_row_spell.setdefault(i, {})[text] = spell
            if meaning is not None:
                pidx, tidx, sim = meaning
                per_row_vec.setdefault(i, {})[text] = float(sim[pidx[phrase], tidx[text]])
        for i, row in enumerate(index.rows):
            s = scored.get(i)
            spell = s.spell if s else 0.0
            partial = s.partial if s else 0.0
            vec = per_row_vec.get(i, {})
            best_vec = max(vec.values()) if vec else 0.0
            if floors["meaning"] > 1.0:
                best_vec = 0.0
            if not (spell > 0 or partial > 0 or best_vec > 0):
                continue
            passed = spell >= floors["spell"] or partial >= floors["partial"] or best_vec >= floors["meaning"]
            signals = (
                ("exact" if s and s.exact else "spell", spell),
                ("partial", partial if partial >= floors["partial"] else 0.0),
                ("meaning", best_vec),
            )
            signal, score = max(signals, key=lambda x: x[1])
            pool.append(
                (
                    passed,
                    score,
                    {
                        "list": name,
                        "key": row.key,
                        "label": row.label,
                        "spelling": _best_text(row, per_row_spell.get(i, {})),
                        "vector": _best_text(row, vec) if meaning is not None else None,
                        "partial": round(float(partial), 4),
                        "floors": {k: round(float(v), 4) for k, v in floors.items()},
                        "passed": bool(passed),
                        "signal": signal,
                    },
                )
            )
    pool.sort(key=lambda k: (not k[0], -k[1]))
    return {"verdict": verdict, "candidates": [c for _p, _s, c in pool[:TRY_LIMIT]]}
