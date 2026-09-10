"""SCM-side half of the text glossary (S2, text glossary lane, R11 -
PLAN-text-glossary.md "Design"). `app.services.translation_service` stays generic and
knows nothing about PI rows; this module is the two things a PI row needs on top of it:

- `fill` - one `translation_service.translate` call over a batch of freshly written or
  updated rows, caching the hit onto each row's own `description_en`.
- `rebind` - point every `proforma_invoice_line` / `proforma_invoice_packing_line` on
  file whose `description` matches a given source text at a new (or cleared) English,
  called from `translation_service.remember` / `update_target_text` / `delete_memory`
  so a correction anywhere reaches every row that shares the word (R2/R4).
"""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.scm import ProformaInvoiceLine, ProformaInvoicePackingLine
from app.services import translation_service


def fill(
    db: Session,
    rows: Iterable[object],
    *,
    attr: str = "description",
    target: str = "description_en",
) -> None:
    """One `translation_service.translate` call over every `attr` on `rows` (empties and
    duplicates included - `translate` itself skips the empties and de-duplicates), then
    sets `target` to the hit text, or `None` for a miss. A description with no CJK script
    never reaches the model and lands `None` (R7 - `translate`'s own `_has_source_script`
    guard, not anything this function has to repeat)."""
    rows = list(rows)
    texts = [getattr(row, attr, None) for row in rows]
    hits = translation_service.translate(db, texts)
    for row, text in zip(rows, texts):
        hit = hits.get(text) if text else None
        setattr(row, target, hit.text if hit else None)
    _persist_ai_hits(db, hits)


def _persist_ai_hits(db: Session, hits: dict) -> None:
    """`translate()` normally writes an AI answer back itself (`_ai_fill_chunk`) - this
    is the safety net for whatever reached `translate()`'s answer WITHOUT going through
    that chunk writer (a caller stubbing `_ai_fill` itself rather than the provider it
    calls). Upsert-if-absent, so the normal path - where the row already exists by the
    time this runs - is one extra SELECT and nothing else."""
    from app.models.translation_memory import SOURCE_AI, TranslationMemory

    seen: set[str] = set()
    for original, hit in hits.items():
        if hit is None or hit.source != SOURCE_AI or not hit.text:
            continue
        normalized = translation_service.normalize_source_text(original)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        existing = (
            db.query(TranslationMemory)
            .filter(
                TranslationMemory.source_text == normalized,
                TranslationMemory.source_lang == "zh",
                TranslationMemory.target_lang == "en",
            )
            .first()
        )
        if existing is not None:
            continue
        db.add(
            TranslationMemory(
                id=str(uuid.uuid4()),
                source_text=normalized,
                source_lang="zh",
                target_lang="en",
                target_text=hit.text,
                source=SOURCE_AI,
            )
        )
    db.flush()


def _normalized_description(column):
    """The same normalisation `translation_service.normalize_source_text` applies in
    Python, done in SQL so it can sit in a `WHERE` clause: trim, then collapse internal
    whitespace to one space."""
    return func.regexp_replace(func.btrim(column), r"\s+", " ", "g")


def rebind(db: Session, source_text: str, target_text: Optional[str]) -> dict:
    """Every `proforma_invoice_line` / `proforma_invoice_packing_line` on file whose
    `description` normalises to `source_text` (the memory's own normalised key) gets
    `description_en` set to `target_text` - `None` to clear it (a forgotten word, R2's
    "delete un-teaches"). Through the ORM, one row at a time, so the company-scope filter
    applies exactly as `supplier_code_alias_service._rebind` relies on for the same
    reason. Returns `{"lines": n, "packing_rows": n}`."""
    normalized = translation_service.normalize_source_text(source_text)

    lines = (
        db.query(ProformaInvoiceLine)
        .filter(_normalized_description(ProformaInvoiceLine.description) == normalized)
        .all()
    )
    for line in lines:
        line.description_en = target_text

    packing_rows = (
        db.query(ProformaInvoicePackingLine)
        .filter(_normalized_description(ProformaInvoicePackingLine.description) == normalized)
        .all()
    )
    for row in packing_rows:
        row.description_en = target_text

    db.flush()
    return {"lines": len(lines), "packing_rows": len(packing_rows)}
