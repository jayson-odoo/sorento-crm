"""Ideation brain extractor (D-CONFIRM) - the sorento-side NLU for `ideate` turns.

shared-service `create_idea` runs NO LLM: it composes the echo/summary and owns the
durable draft, but it needs sorento to hand it STRUCTURED updates, never free text
to parse. So each `ideate` turn we run one small, schema-forced LLM step that reads
the user's message in the context of the current draft (its status + still-missing
fields) and emits:

    { fields: {answer_key: value}, remove: [answer_key], confirm: bool }

- ``fields`` - answer-key -> value updates the user just supplied.
- ``remove`` - answer keys the user asked to clear ("remove who", "forget the module").
- ``confirm`` - ``true`` ONLY on an explicit confirmation of a ``review`` summary
  (guarded deterministically below: confirm can never be true unless status=="review").

Reuses the same provider plumbing as the semantic parser (``get_provider`` +
``json_schema`` forced output) and the prompt registry (``ideate_extractor`` key).
On any failure (no api key, provider/parse error) it degrades to an EMPTY extraction
so the turn still calls ``create_idea`` with ``message_text`` - never raises.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.services import ai_prompt_registry
from app.services.ai_assistant_service import AIAssistantConfigService
from app.services.llm_provider import get_provider

logger = logging.getLogger(__name__)


IDEATE_EXTRACTION_SCHEMA_NAME = "ideate_extraction"

# OpenAI strict-mode json_schema: every property required, additionalProperties
# false, no open-ended object maps (``fields`` is an array of {key,value} pairs
# so dynamic answer keys stay strict-compliant).
IDEATE_EXTRACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fields": {
            "type": "array",
            "description": (
                "Field updates the user supplied this turn, as {key,value} pairs. "
                "key is the intake answer key (one of: problem, proposed_solution, "
                "impact, department); value is the user's answer as plain text. "
                "Empty when the turn adds nothing."
            ),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
        },
        "remove": {
            "type": "array",
            "description": "Answer keys the user asked to clear/remove this turn.",
            "items": {"type": "string"},
        },
        "confirm": {
            "type": "boolean",
            "description": (
                "true ONLY when the user explicitly confirms the review summary is "
                "correct (e.g. 'yes', 'confirm', 'that's right'). false otherwise."
            ),
        },
    },
    "required": ["fields", "remove", "confirm"],
}


@dataclass
class IdeateExtraction:
    fields: dict[str, str] = field(default_factory=dict)
    remove: list[str] = field(default_factory=list)
    confirm: bool = False


def extract_ideate_turn(
    db: Session,
    *,
    message_text: str,
    status: str | None = None,
    missing: list[str] | None = None,
    field_labels: dict[str, str] | None = None,
) -> IdeateExtraction:
    """Extract ``{ fields, remove, confirm }`` from ``message_text`` given the draft
    context. Never raises - degrades to an empty extraction on any failure.

    ``confirm`` is force-cleared unless ``status == "review"`` (D-CONFIRM / AC-11b):
    a confirmation only means anything once the draft is being reviewed.
    """
    raw = (message_text or "").strip()
    if not raw:
        return IdeateExtraction()

    try:
        config = AIAssistantConfigService(db).get()
    except Exception:  # noqa: BLE001 - never break the turn on a config read
        logger.warning("ideate_extractor: config read failed; empty extraction", exc_info=True)
        return IdeateExtraction()

    api_key = config.api_key_ciphertext or settings.openai_api_key
    if not api_key:
        return IdeateExtraction()

    try:
        system, _version = ai_prompt_registry.render(db, "ideate_extractor")
    except Exception:  # noqa: BLE001
        logger.warning("ideate_extractor: prompt render failed; empty extraction", exc_info=True)
        return IdeateExtraction()

    context_lines: list[str] = []
    context_lines.append(f"Current draft status: {status or 'new'}")
    if missing:
        context_lines.append(f"Fields still missing: {', '.join(missing)}")
    if field_labels:
        labels = ", ".join(f"{k} ({v})" for k, v in field_labels.items())
        context_lines.append(f"Known field keys: {labels}")
    user_block = "\n".join(context_lines) + f"\n\nUser message:\n{raw}"

    messages_in = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_block},
    ]

    try:
        provider = get_provider(config.provider, api_key, config.model)
        result = provider.chat(
            messages_in,
            temperature=0.0,
            model=config.model,
            max_tokens=512,
            json_schema=IDEATE_EXTRACTION_JSON_SCHEMA,
            json_schema_name=IDEATE_EXTRACTION_SCHEMA_NAME,
        )
        data = json.loads((result.content or "").strip() or "{}")
    except Exception:  # noqa: BLE001 - provider/parse error → empty extraction
        logger.warning("ideate_extractor: LLM call failed; empty extraction", exc_info=True)
        return IdeateExtraction()

    fields: dict[str, str] = {}
    for pair in data.get("fields") or []:
        if isinstance(pair, dict) and pair.get("key"):
            fields[str(pair["key"])] = str(pair.get("value", ""))
    remove = [str(k) for k in (data.get("remove") or []) if k]
    confirm = bool(data.get("confirm", False))

    # Deterministic guard: a confirmation only counts while reviewing (AC-11b).
    if status != "review":
        confirm = False

    return IdeateExtraction(fields=fields, remove=remove, confirm=confirm)
