"""Understand what a customer asked for, using the same vocabulary the ranker scores.

This is the *semantic* half of spec search. The ranker (`product_spec_search`) stays
deterministic and explainable on purpose — every point it awards can be pointed at. What
it could never do is understand language: it matched registry synonyms as literal
substrings, so one dropped letter ("inteligent") resolved nothing, and any phrasing not
already written into the synonym list was invisible.

Fuzzy string distance was the cheap answer and it is the wrong one. It buys tolerance for
typos and nothing else: it cannot know that "for my kitchen" means a kitchen sink, that
"the toilet where the pipe goes into the wall" is a P-trap, or that "not too deep"
qualifies a dimension. Those need a model that understands language, which is what this
module adds.

**The model never invents vocabulary.** It is handed the registry — the same rows the
ranker weights and the n8n parser reads — and every key and value it returns is validated
back against those rows. Anything unrecognised is dropped, not coerced. So the model
decides *meaning*; the registry still decides *what exists*. That boundary is what keeps
a hallucinated `mounting=levitating` out of a customer's shortlist.

Degrades to the deterministic resolver on any failure — no key, no provider, bad JSON,
timeout. Search that got worse when the LLM had a bad day would be a worse product than
search that never used one.

Ticket: jayson-odoo/sorento-crm#98.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.ai_assistant import AIAssistantUsageLog
from app.services.llm_provider import get_provider
from app.services.product_spec_registry import active_registry, merged_synonyms
from app.services.product_spec_search import (
    SELF_SYNONYM_KEY,
    normalise_quantity,
    resolve_terms_to_specs,
)

logger = logging.getLogger(__name__)

# Understanding one short sentence. Kept small and cheap: this runs on a customer's
# message, so it is on the latency path of a WhatsApp reply.
_MAX_OUTPUT_TOKENS = 700
_TEMPERATURE = 0.0

_SYSTEM_PROMPT = """You read a customer's sanitaryware enquiry and map it onto a fixed \
vocabulary of product specifications.

You will be given the ONLY specifications that exist. Use nothing else.

Rules:
- Return a specification ONLY when the customer's words genuinely mean it. Silence is \
correct and expected; a wrong specification is worse than a missing one, because it \
puts the wrong product in front of a buyer.
- Never invent a spec_key or an enum value. Use the exact strings given to you.
- Understand meaning, not just words: misspellings, plurals, local phrasing, and \
descriptions of a thing rather than its name ("the pipe goes into the wall" = a P-trap, \
"pipe goes into the floor" = an S-trap).
- For numeric specs return a plain number in the unit stated for that key. Convert if \
the customer used another unit (8 inch = 203.2 mm).
- Put words that carry meaning but map onto no spec — a brand, a model name, a room, a \
colour you were not given — into free_terms.
- If the customer is not describing a product at all, return empty lists.

Reply with JSON only:
{"specs": [{"key": "<spec_key>", "value": <string|number|boolean>}], \
"free_terms": ["..."], "notes": "<one short sentence on anything ambiguous>"}"""


@dataclass
class Understanding:
    """What the customer meant, in the ranker's own terms."""

    specs: list[dict] = field(default_factory=list)
    free_terms: list[str] = field(default_factory=list)
    notes: str = ""
    # How this was produced, so the preview screen can be honest about it and a
    # reviewer can tell a model result from a fallback.
    source: str = "deterministic"
    model: str | None = None
    elapsed_ms: int | None = None


def _vocabulary(db: Session) -> tuple[list[dict], dict[str, Any]]:
    """The registry rendered for a prompt, plus an index to validate replies against."""
    described: list[dict] = []
    index: dict[str, Any] = {}

    for row in active_registry(db):
        synonyms = merged_synonyms(row)
        entry: dict[str, Any] = {
            "spec_key": row.spec_key,
            "means": row.label,
            "type": row.data_type,
        }
        if row.unit:
            entry["unit"] = row.unit
        if row.allowed_values:
            entry["allowed_values"] = list(row.allowed_values)
        # Synonyms are what a customer might say. `_self` names the measurement itself
        # ("thickness", "trap"), the rest name a value ("wall hung", "double bowl").
        customer_words = sorted(
            {w for value, words in synonyms.items() for w in words if value != SELF_SYNONYM_KEY}
        )
        if customer_words:
            entry["customers_say"] = customer_words[:40]
        if synonyms.get(SELF_SYNONYM_KEY):
            entry["called"] = list(synonyms[SELF_SYNONYM_KEY])
        if row.applies_when:
            entry["only_for"] = row.applies_when

        described.append(entry)
        index[row.spec_key] = row

    return described, index


def _coerce(row, value: Any) -> Any | None:
    """Force a model's value into the shape the catalog stores, or reject it.

    Rejection is the important half. A value the registry does not recognise is
    dropped rather than passed through, so the model can be wrong without the wrongness
    reaching a customer.
    """
    data_type = (row.data_type or "").lower()

    if data_type == "boolean":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"true", "yes", "1"}

    if data_type == "numeric":
        # The model was told the key's unit, but customers volunteer their own and
        # models echo them. Re-normalise defensively.
        if isinstance(value, (int, float)):
            return float(value)
        converted = normalise_quantity(str(value))
        return converted

    text = str(value).strip()
    if not text:
        return None

    allowed = list(row.allowed_values or [])
    if not allowed:
        # Open vocabularies (`class`, `brand`) are sourced from the catalog, so there
        # is no closed list to check against. Pass the text through.
        return text

    lowered = text.lower().replace(" ", "_")
    for candidate in allowed:
        if str(candidate).lower() == lowered:
            return candidate

    # Give the model's phrasing one chance against the synonym table before dropping it.
    for candidate, words in merged_synonyms(row).items():
        if candidate == SELF_SYNONYM_KEY:
            continue
        if any(str(w).lower() == text.lower() for w in words):
            return candidate

    logger.info("spec understanding: dropped unknown value %r for %s", value, row.spec_key)
    return None


def _validate(payload: dict, index: dict[str, Any]) -> tuple[list[dict], list[str], str]:
    specs: list[dict] = []
    seen: set[str] = set()

    for item in payload.get("specs") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        row = index.get(key)
        if row is None:
            logger.info("spec understanding: dropped unknown key %r", key)
            continue
        if key in seen:
            continue
        value = _coerce(row, item.get("value"))
        if value is None:
            continue
        specs.append({"key": key, "value": value})
        seen.add(key)

    free_terms = [str(t).strip() for t in (payload.get("free_terms") or []) if str(t).strip()]
    notes = str(payload.get("notes") or "").strip()
    return specs, free_terms, notes


def _resolve_provider(db: Session):
    """Same provider the rest of the CRM's AI features use. None when unconfigured."""
    from app.models.ai_assistant import AIAssistantConfig

    cfg = (
        db.query(AIAssistantConfig)
        .order_by(AIAssistantConfig.created_at.asc())
        .first()
    )
    provider_name = (cfg.provider if cfg else "openai") or "openai"
    model_name = (cfg.model if cfg else "") or ""
    api_key = (cfg.api_key_ciphertext if cfg else "") or settings.openai_api_key or ""
    if not api_key:
        return None, provider_name, model_name

    if not model_name:
        model_name = "gpt-4o" if provider_name == "openai" else "claude-sonnet-4-6"
    try:
        return get_provider(provider_name, api_key, model=model_name), provider_name, model_name
    except ValueError:
        logger.warning("spec understanding: unknown provider %r", provider_name)
        return None, provider_name, model_name


def understand_phrase(
    db: Session,
    phrase: str,
    *,
    user_id: str | None = None,
    allow_model: bool = True,
) -> Understanding:
    """Map a customer's sentence onto registry specs, semantically where possible.

    Always returns something usable. The deterministic resolver is both the fallback
    and the floor: whatever the model finds is merged ON TOP of it, so a literal
    synonym match can never be lost by asking a model.
    """
    phrase = (phrase or "").strip()
    if not phrase:
        return Understanding()

    # The deterministic reading first — it is free, and it is the floor.
    baseline = resolve_terms_to_specs(db, [phrase])
    fallback = Understanding(specs=baseline, free_terms=[phrase], source="deterministic")

    if not allow_model:
        return fallback

    provider, provider_name, model_name = _resolve_provider(db)
    if provider is None:
        return fallback

    described, index = _vocabulary(db)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Specifications that exist:\n"
                + json.dumps(described, ensure_ascii=False)
                + "\n\nCustomer said:\n"
                + phrase
            ),
        },
    ]

    started = time.monotonic()
    try:
        result = provider.chat(
            messages,
            temperature=_TEMPERATURE,
            max_tokens=_MAX_OUTPUT_TOKENS,
            response_format={"type": "json_object"},
        )
        payload = json.loads(result.content or "{}")
    except Exception as exc:  # noqa: BLE001 - any provider failure degrades, never raises
        logger.warning("spec understanding failed, using deterministic reading: %s", exc)
        return fallback

    elapsed_ms = int((time.monotonic() - started) * 1000)
    specs, free_terms, notes = _validate(payload if isinstance(payload, dict) else {}, index)

    # The model supplements the literal reading, it does not replace it. If a synonym
    # matched outright, that is not something a model should be able to talk us out of.
    merged = list(specs)
    stated = {entry["key"] for entry in merged}
    merged.extend(entry for entry in baseline if entry["key"] not in stated)

    # The whole phrase always stays available as free text: it is what the rendered
    # sentence is matched against, and dropping it would lose recall the model cannot
    # replace.
    terms = [phrase] + [t for t in free_terms if t.lower() != phrase.lower()]

    try:
        db.add(
            AIAssistantUsageLog(
                user_id=user_id,
                feature="spec_search",
                provider=provider_name,
                model=model_name,
                prompt_tokens=int(result.prompt_tokens or 0),
                completion_tokens=int(result.completion_tokens or 0),
                total_tokens=int(result.total_tokens or 0),
                tool_calls_count=0,
                response_time_ms=elapsed_ms,
                was_answered=bool(merged),
            )
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 - never fail a search over bookkeeping
        logger.warning("spec understanding: usage log failed: %s", exc)
        db.rollback()

    return Understanding(
        specs=merged,
        free_terms=terms,
        notes=notes,
        source="semantic",
        model=model_name,
        elapsed_ms=elapsed_ms,
    )
