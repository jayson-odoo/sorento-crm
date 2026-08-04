"""S5 - reading a dealer's WhatsApp burst with the model (AC-C7, AC-C8).

Kept OUT of `complaint_intake_service` on purpose. That service is the transaction - burst
to Complaint, idempotent on the burst key - and this is the one part of the path that talks
to a model and can therefore be slow, expensive or unavailable. Separating them is what lets
the service take an injected extraction, which is what makes AC-C8 testable: the service's
tests assert what it DOES with a result, never how English was parsed.

**The prompt is registry data** (AC-C7). `intake_extractor` is versioned, labelled and
publishable without a redeploy, and carries a hardcoded fallback so a database outage cannot
take intake down.

**A model failure is not an intake failure.** Every path here returns an EMPTY extraction
rather than raising. The service then writes a Complaint carrying the raw transcript and asks
the dealer for what is missing - which is precisely the human process this slice replaces, so
degrading to it is the correct floor. Raising would leave the message in WhatsApp, and that
is where it already goes to die.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services import ai_prompt_registry

logger = logging.getLogger(__name__)

PROMPT_KEY = "intake_extractor"

# The model is asked for JSON and usually complies. When it wraps the object in prose or a
# fenced block, take the outermost object rather than failing: a recoverable formatting
# habit is not a reason to lose a dealer's message.
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def empty_extraction() -> Dict[str, Any]:
    """What every failure returns. A complete, valid answer that says nothing."""
    return {
        "shop_name": None,
        "lines": [],
        "defect_description": None,
        "requested_resolution": None,
        "prompt_versions": [],
    }


def _coerce_lines(raw: Any) -> List[Dict[str, Any]]:
    """One entry per product named, and never a guess.

    A model that returns a bare string instead of an object is still telling us something
    a human can read, so it becomes `claimed_text` with no code rather than nothing.
    """
    out: List[Dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            text = item.strip()
            if text:
                out.append({"claimed_text": text, "model_code_raw": None, "quantity": 1})
            continue
        if not isinstance(item, dict):
            continue
        claimed = str(item.get("claimed_text") or "").strip() or None
        code = str(item.get("model_code_raw") or "").strip() or None
        if not claimed and not code:
            continue
        quantity = item.get("quantity")
        try:
            quantity = max(1, int(quantity))
        except (TypeError, ValueError):
            # A receipt that did not say is one, not zero: zero would tell the ledger the
            # dealer reported nothing.
            quantity = 1
        out.append(
            {"claimed_text": claimed or code, "model_code_raw": code, "quantity": quantity}
        )
    return out


def _parse(text: str) -> Optional[Dict[str, Any]]:
    body = (text or "").strip()
    if not body:
        return None
    try:
        return json.loads(body)
    except ValueError:
        pass
    match = _JSON_BLOCK.search(body)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except ValueError:
        return None


def extract_burst(db: Session, transcript: str) -> Dict[str, Any]:
    """Read one burst. Returns the extraction shape, never raises.

    `transcript` is the burst verbatim and in order - the sequence is part of the meaning,
    since photos routinely arrive before the words that explain them.
    """
    if not (transcript or "").strip():
        return empty_extraction()

    try:
        prompt, version = ai_prompt_registry.render(db, PROMPT_KEY)
    except Exception:  # noqa: BLE001 - the registry's own fallback should prevent this
        logger.warning("Intake prompt could not be resolved", exc_info=True)
        return empty_extraction()

    provider, model_name = _resolve_provider(db)
    if provider is None:
        # A fresh install with no key configured. Intake still works; it just learns
        # nothing from the words, which is the same position the office starts from.
        logger.info("Intake extraction skipped: no AI provider configured.")
        return empty_extraction()

    try:
        # `response_format=json_object` and temperature 0: the same extraction from the
        # same burst every time, because a report that reads differently on a retry is a
        # report nobody trusts.
        reply = provider.chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": transcript},
            ],
            temperature=0.0,
            model=model_name,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
    except Exception:  # noqa: BLE001
        logger.warning("Intake extraction call failed", exc_info=True)
        return empty_extraction()

    text = reply if isinstance(reply, str) else (
        (reply or {}).get("content") if isinstance(reply, dict) else str(reply or "")
    )
    parsed = _parse(str(text or ""))
    if not isinstance(parsed, dict):
        logger.warning("Intake extraction returned no readable JSON.")
        return empty_extraction()

    out = empty_extraction()
    out["shop_name"] = str(parsed.get("shop_name") or "").strip() or None
    out["defect_description"] = str(parsed.get("defect_description") or "").strip() or None
    out["requested_resolution"] = str(parsed.get("requested_resolution") or "").strip() or None
    out["lines"] = _coerce_lines(parsed.get("lines"))
    # AC-C7: every turn records which prompt produced it, or a bad extraction cannot be
    # traced to the version that caused it and publishing a fix proves nothing.
    out["prompt_versions"] = [{"name": PROMPT_KEY, "version": version}]
    if model_name:
        out["model"] = model_name
    return out


def _resolve_provider(db: Session):
    """The configured provider, or (None, None). NEVER an exception.

    Same source as every other AI call site here, and the same reason a missing key is not
    an error: raising would turn every dealer message on an unconfigured install into a
    lost report for a step that is an accelerator, not a precondition.
    """
    try:
        from app.config import settings
        from app.models.ai_assistant import AIAssistantConfig
        from app.services.llm_provider import get_provider
    except Exception:  # noqa: BLE001
        return None, None

    try:
        cfg = (
            db.query(AIAssistantConfig)
            .order_by(AIAssistantConfig.created_at.asc())
            .first()
        )
    except Exception:  # noqa: BLE001
        logger.warning("Intake provider lookup failed", exc_info=True)
        return None, None

    name = (getattr(cfg, "provider", None) or "openai") if cfg else "openai"
    model_name = ((getattr(cfg, "model", None) or "") if cfg else "") or ""
    api_key = ((getattr(cfg, "api_key_ciphertext", None) or "") if cfg else "") or (
        getattr(settings, "openai_api_key", "") or ""
    )
    if not api_key:
        return None, None
    if not model_name:
        model_name = "gpt-4o" if name == "openai" else "claude-sonnet-4-6"
    try:
        return get_provider(name, api_key, model=model_name), model_name
    except Exception:  # noqa: BLE001
        logger.warning("Intake provider %s is not usable", name)
        return None, None
