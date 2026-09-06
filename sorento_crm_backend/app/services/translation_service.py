"""Chinese <-> English translation memory, deterministic-first (R15/R16, purchasing
consolidation batch, lane C).

``translate()`` is the ONLY way any part of this system turns supplier-document text
(品名 descriptions, remarks, footer notes) into English: it reads ``translation_memory``
first (bumping ``hit_count`` on every hit), and only asks the AI Assistant's configured
model for what the memory has never seen. Every AI answer is written back as
``source='ai'`` before it is returned, so the SAME phrase never asks the model twice -
the standing "deterministic post-LLM only" rule: memory is the record, the model only
fills gaps.

No AI key configured, or the provider call fails: every miss comes back as
``TranslationHit(text=None, source=None)`` - never an exception. A translation is a
nicety on top of a supplier-document import, not something that should ever fail an
upload.

``remember()`` is the other write path: an edited preview cell, always ``manual`` and
always overwriting whatever was there (an ``ai`` row or nothing) - a person's correction
outranks the model's guess and is never overwritten back.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.translation_memory import SOURCE_AI, SOURCE_MANUAL, TranslationMemory
from app.models.user import User
from app.services import ai_prompt_registry
from app.services.ai_assistant_service import AIAssistantConfigService
from app.services.error_handler import handle_not_found
from app.services.llm_provider import get_provider, resolve_api_key, resolve_model

logger = logging.getLogger(__name__)

#: One model call per this many misses; a supplier document rarely names more, and a
#: huge one is chunked rather than sent as a single, easy-to-truncate prompt (D4 cap).
_BATCH_SIZE = 200

_WHITESPACE_RE = re.compile(r"\s+")
#: Any CJK ideograph. Good enough to tell "座厕 S-250" (translate it) from "loaded
#: first" or a bare model number (leave it alone) - the boundary this needs is
#: "does this contain the source script at all", not a full language identifier.
_CJK_RE = re.compile(r"[一-鿿]")


def _has_source_script(text: str, source_lang: str) -> bool:
    if source_lang != "zh":
        return True
    return bool(_CJK_RE.search(text))


@dataclass
class TranslationHit:
    text: Optional[str]
    source: Optional[str]


def normalize_source_text(text: Optional[str]) -> str:
    """Trimmed, internal whitespace collapsed - the same string two differently padded
    cells must resolve to, so both hit the same memory row."""
    return _WHITESPACE_RE.sub(" ", (text or "").strip())


def compose_bilingual(hit: Optional[TranslationHit], source_text: Optional[str]) -> Optional[str]:
    """``English (Chinese)`` when the two differ, the source text alone otherwise, and
    ``None`` for nothing said at all (R16/AC-G3)."""
    if not source_text:
        return None
    english = (hit.text if hit else None) or ""
    if not english.strip() or english.strip() == source_text.strip():
        return source_text
    return f"{english.strip()} ({source_text.strip()})"


# --------------------------------------------------------------------------------------
# translate() - memory read + batched AI fill for misses
# --------------------------------------------------------------------------------------


def translate(
    db: Session,
    texts: list[str],
    *,
    source_lang: str = "zh",
    target_lang: str = "en",
) -> dict[str, TranslationHit]:
    """``{original_text: TranslationHit}`` for every non-empty text handed in, keyed by
    the ORIGINAL string (not the normalised one) so a caller never has to re-normalise
    its own keys to look its own answer back up."""
    out: dict[str, TranslationHit] = {}
    #: normalised -> every original spelling that normalises to it, so one memory row
    #: (or one model answer) answers every one of them.
    by_normalized: dict[str, list[str]] = {}
    for t in texts:
        norm = normalize_source_text(t)
        if not norm:
            continue
        by_normalized.setdefault(norm, []).append(t)

    if not by_normalized:
        return out

    existing = _lookup(db, list(by_normalized.keys()), source_lang, target_lang)
    misses: list[str] = []
    for norm, originals in by_normalized.items():
        row = existing.get(norm)
        if row is None:
            misses.append(norm)
            continue
        row.hit_count = (row.hit_count or 0) + 1
        for original in originals:
            out[original] = TranslationHit(text=row.target_text, source=row.source)

    # Only a miss that actually CONTAINS the source script is worth a model call - a
    # supplier's own English remark ("loaded first", "as packed") is not Chinese, has
    # nothing to translate, and asking anyway would be a network round trip for every
    # such line on every apply, memory or not.
    ai_candidates = [m for m in misses if _has_source_script(m, source_lang)]
    if ai_candidates:
        answers = _ai_fill(db, ai_candidates, source_lang=source_lang, target_lang=target_lang)
        for norm, target_text in answers.items():
            for original in by_normalized.get(norm, []):
                out[original] = TranslationHit(text=target_text, source=SOURCE_AI)

    # Anything still missing (AI unconfigured or the call failed) is flagged untranslated
    # rather than silently dropped - the caller decides how to surface that.
    for norm, originals in by_normalized.items():
        for original in originals:
            out.setdefault(original, TranslationHit(text=None, source=None))

    db.flush()
    return out


def _lookup(
    db: Session, normalized_texts: list[str], source_lang: str, target_lang: str
) -> dict[str, TranslationMemory]:
    if not normalized_texts:
        return {}
    rows = (
        db.query(TranslationMemory)
        .filter(
            TranslationMemory.source_lang == source_lang,
            TranslationMemory.target_lang == target_lang,
            TranslationMemory.source_text.in_(normalized_texts),
        )
        .all()
    )
    return {r.source_text: r for r in rows}


_TRANSLATION_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "translations": {
            "type": "array",
            "description": "One entry per input line, in the same order.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                },
                "required": ["source", "target"],
            },
        },
    },
    "required": ["translations"],
}


def _ai_fill(
    db: Session, misses: list[str], *, source_lang: str, target_lang: str
) -> dict[str, str]:
    """One batched model call per ``_BATCH_SIZE`` misses; writes each answer back as an
    ``ai`` row (``misses`` only ever holds normalised text with NO row at all, so this
    never overwrites a ``manual`` one) and returns ``{normalised_text: target_text}``.
    Empty on any failure - never raises."""
    try:
        config = AIAssistantConfigService(db).get()
    except Exception:  # noqa: BLE001 - never fail an upload on a config read
        logger.warning("translation_service: config read failed", exc_info=True)
        return {}

    provider_name = (config.provider or "openai").strip().lower() or "openai"
    api_key = resolve_api_key(config, provider_name)
    if not api_key:
        return {}

    try:
        system, _version = ai_prompt_registry.render(db, "supplier_translation")
    except Exception:  # noqa: BLE001
        logger.warning("translation_service: prompt render failed", exc_info=True)
        return {}

    model_name = resolve_model(config, provider_name)
    out: dict[str, str] = {}
    for start in range(0, len(misses), _BATCH_SIZE):
        chunk = misses[start : start + _BATCH_SIZE]
        out.update(
            _ai_fill_chunk(
                db,
                chunk,
                provider_name=provider_name,
                model_name=model_name,
                api_key=api_key,
                system=system,
                source_lang=source_lang,
                target_lang=target_lang,
            )
        )
    return out


def _ai_fill_chunk(
    db: Session,
    chunk: list[str],
    *,
    provider_name: str,
    model_name: str,
    api_key: str,
    system: str,
    source_lang: str,
    target_lang: str,
) -> dict[str, str]:
    try:
        provider = get_provider(provider_name, api_key, model_name)
        user_content = (
            f"Translate each numbered line from {source_lang} to {target_lang}. Return "
            "one entry per input line, in the SAME order, even if a line is already "
            "English or you are unsure - never omit a line.\n\n"
            + "\n".join(f"{i + 1}. {line}" for i, line in enumerate(chunk))
        )
        result = provider.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            model=model_name,
            max_tokens=4096,
            json_schema=_TRANSLATION_JSON_SCHEMA,
            json_schema_name="supplier_translation",
        )
        data = json.loads((result.content or "").strip() or "{}")
    except Exception:  # noqa: BLE001 - provider/parse error -> this chunk stays untranslated
        logger.warning("translation_service: AI fill failed", exc_info=True)
        return {}

    pairs = data.get("translations") or []
    out: dict[str, str] = {}
    for i, item in enumerate(pairs):
        if not isinstance(item, dict) or i >= len(chunk):
            continue
        target = str(item.get("target") or "").strip()
        if not target:
            continue
        # Matched by POSITION, not by the model's echoed `source` text: `chunk[i]` is
        # what WE asked about and is what the memory row must be keyed on, and a model
        # that re-punctuates or re-cases the source back would otherwise mint a second,
        # near-duplicate row for the same phrase.
        norm = chunk[i]
        if norm in out:
            continue
        # Each insert in its OWN savepoint, flushed immediately: `misses` only ever holds
        # a phrase with NO row yet, but two requests can both miss the same phrase at
        # once, and the unique constraint (`uq_translation_memory_phrase`) is the thing
        # that catches it. A bare `db.add` + one flush at the end of the loop let that
        # `IntegrityError` escape uncaught, breaking this function's own "never raises"
        # contract; a savepoint means the LOSER rolls back only its own insert, not
        # every row this chunk already wrote, and reads back the WINNER's answer instead
        # of a duplicate.
        try:
            with db.begin_nested():
                db.add(
                    TranslationMemory(
                        id=str(uuid.uuid4()),
                        source_text=norm,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        target_text=target,
                        source=SOURCE_AI,
                    )
                )
                db.flush()
        except IntegrityError:
            existing = (
                db.query(TranslationMemory)
                .filter(
                    TranslationMemory.source_text == norm,
                    TranslationMemory.source_lang == source_lang,
                    TranslationMemory.target_lang == target_lang,
                )
                .first()
            )
            if existing is None:
                # Not a race after all - some OTHER constraint failed. Leave this phrase
                # untranslated rather than raise; the docstring's "never raises" holds.
                continue
            target = existing.target_text
        out[norm] = target
    return out


# --------------------------------------------------------------------------------------
# remember() - a manual edit from the upload preview
# --------------------------------------------------------------------------------------


def remember(
    db: Session,
    pairs: list[dict],
    *,
    user_id: Optional[str] = None,
    source_lang: str = "zh",
    target_lang: str = "en",
) -> int:
    """Upsert MANUAL rows from ``[{source_text, target_text}]`` (an edited preview
    cell). Manual always overwrites ``ai``; an empty ``target_text`` is skipped rather
    than stored as a blank translation. Returns the number of rows written."""
    written = 0
    for pair in pairs or []:
        source_text = normalize_source_text(str((pair or {}).get("source_text") or ""))
        target_text = str((pair or {}).get("target_text") or "").strip()
        if not source_text or not target_text:
            continue
        row = (
            db.query(TranslationMemory)
            .filter(
                TranslationMemory.source_text == source_text,
                TranslationMemory.source_lang == source_lang,
                TranslationMemory.target_lang == target_lang,
            )
            .first()
        )
        if row is None:
            db.add(
                TranslationMemory(
                    id=str(uuid.uuid4()),
                    source_text=source_text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    target_text=target_text,
                    source=SOURCE_MANUAL,
                    created_by=user_id,
                )
            )
        else:
            row.target_text = target_text
            row.source = SOURCE_MANUAL
            row.created_by = user_id
        written += 1
    if written:
        db.flush()
    return written


# --------------------------------------------------------------------------------------
# Admin list (AC-G4) - System Management > Translations
# --------------------------------------------------------------------------------------

#: Whitelisted `sort` columns (S6, review round 1) - the FE's own service contract
#: (`translationService.ts`) already documents `?sort&dir` and builds them on every
#: sortable column, so the route accepting them is the smaller diff over stripping that
#: back out. `target_text` is not sortable (`enableSorting: false` on the FE column,
#: it is an inline-editable input, not prose worth ordering by) and is deliberately
#: absent here too, even though the FE could never send it.
_SORT_COLUMNS: dict[str, Any] = {
    "source_text": TranslationMemory.source_text,
    "source": TranslationMemory.source,
    "hit_count": TranslationMemory.hit_count,
    "updated_at": TranslationMemory.updated_at,
}


def list_memory(
    db: Session, *, page: int = 1, limit: int = 50, query: Optional[str] = None,
    sort: Optional[str] = None, dir: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Rows plus total, joined onto the writing user's name (never a bare id in the UI).
    Sorted by `sort`/`dir` when `sort` names a whitelisted column, else newest-touched
    first - the same default this list always had."""
    q = db.query(TranslationMemory)
    if query:
        like = f"%{query.strip()}%"
        q = q.filter(
            or_(
                TranslationMemory.source_text.ilike(like),
                TranslationMemory.target_text.ilike(like),
            )
        )
    total = q.count()
    column = _SORT_COLUMNS.get(sort or "")
    if column is None:
        column, sort_dir = TranslationMemory.updated_at, "desc"
    else:
        sort_dir = "asc" if (dir or "").lower() == "asc" else "desc"
    ordered = column.asc() if sort_dir == "asc" else column.desc()
    rows = (
        q.order_by(ordered)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    user_ids = {r.created_by for r in rows if r.created_by}
    names: dict[str, str] = {}
    if user_ids:
        for uid, name in db.query(User.id, User.name).filter(User.id.in_(user_ids)).all():
            names[str(uid)] = name
    out = [
        {
            "id": r.id,
            "source_text": r.source_text,
            "source_lang": r.source_lang,
            "target_lang": r.target_lang,
            "target_text": r.target_text,
            "source": r.source,
            "created_by_name": names.get(str(r.created_by)) if r.created_by else None,
            "updated_at": r.updated_at,
            "hit_count": r.hit_count,
        }
        for r in rows
    ]
    return out, total


def to_response_dict(db: Session, row: TranslationMemory) -> dict:
    """One row, in the same shape ``list_memory`` returns - used after a write so the
    route never has to duplicate the ``created_by`` -> name join."""
    name = None
    if row.created_by:
        user = db.query(User.name).filter(User.id == row.created_by).first()
        name = user[0] if user else None
    return {
        "id": row.id,
        "source_text": row.source_text,
        "source_lang": row.source_lang,
        "target_lang": row.target_lang,
        "target_text": row.target_text,
        "source": row.source,
        "created_by_name": name,
        "updated_at": row.updated_at,
        "hit_count": row.hit_count,
    }


def get_or_404(db: Session, memory_id: str) -> TranslationMemory:
    row = db.query(TranslationMemory).filter(TranslationMemory.id == memory_id).first()
    if row is None:
        raise handle_not_found("Translation", memory_id)
    return row


def update_target_text(
    db: Session, memory_id: str, target_text: str, *, user_id: Optional[str] = None
) -> TranslationMemory:
    """Inline-edit from the admin list: always ``manual`` from here on, same rule as
    ``remember()`` - the admin correcting a bad AI guess outranks it."""
    row = get_or_404(db, memory_id)
    row.target_text = target_text.strip()
    row.source = SOURCE_MANUAL
    row.created_by = user_id
    db.commit()
    db.refresh(row)
    return row


def delete_memory(db: Session, memory_id: str) -> None:
    row = get_or_404(db, memory_id)
    db.delete(row)
    db.commit()
