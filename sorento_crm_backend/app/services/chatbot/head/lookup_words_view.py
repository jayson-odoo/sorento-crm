"""The Embeddings screen's view of the chatbot's lookup words (LOOKUP-EMBED-CENTRAL, AC-LEC-20, 21).

`words_of_list` lists a list's rows with each word's home and whether it has a stored vector; `try_phrase` runs a
phrase through the live span resolver and shows, per candidate row, what each signal saw.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.chatbot.head import lookup_lists as ll, lookup_word_store, span_extract

logger = logging.getLogger(__name__)

LIST_NAMES = (
    "category", "spec", "file_type", "brand", "promotion_kind", "location", "salesperson", "customer", "sales_channel",
)
#: The data each list is read from, as the screen names it.
LIST_SOURCES = {
    "category": "Categories", "spec": "Spec registry", "file_type": "Attachment types", "brand": "Brands",
    "promotion_kind": "Promotion types", "location": "Warehouses", "salesperson": "Sales agents",
    "customer": "Customers", "sales_channel": "Sales channels",
}
TRY_LIMIT = 8


def _rows(db: Session) -> list[ll.LookupRow]:
    return ll.load_rows(db, include_salespeople=True, include_customers=True, customer_ids=None)


def _stored_texts(db: Session, model: str) -> set[str]:
    from app.models.embeddings import EmbeddingChunk

    rows = (
        db.query(EmbeddingChunk.chunk_text)
        .filter(
            EmbeddingChunk.source_type == lookup_word_store.LOOKUP_SOURCE,
            EmbeddingChunk.model_name == model,
            EmbeddingChunk.is_current.is_(True),
        )
        .distinct()
        .all()
    )
    return {t for (t,) in rows}


_home = span_extract.word_home


def words_of_list(db: Session, list_name: str) -> dict[str, Any]:
    from app.services.embedding_settings import resolve_embedder

    model = resolve_embedder(db)[1]
    stored = _stored_texts(db, model)
    rows = []
    for row in _rows(db):
        if row.list_name != list_name:
            continue
        rows.append(
            {
                "key": row.key,
                "label": row.label,
                "source": LIST_SOURCES.get(list_name, list_name),
                "group": row.group,
                "words": [
                    {"text": t, "home": _home(row, t), "has_vector": t in stored} for t in row.texts
                ],
            }
        )
    return {"list": list_name, "rows": rows}


def try_phrase(db: Session, phrase: str, allowed_lists: set[str] | None = None) -> dict[str, Any]:
    """`allowed_lists` limits the rows the phrase is tried against (the lists the caller may view)."""
    from app.services.embedding_settings import resolve_embedder

    model = resolve_embedder(db)[1]
    rows = [r for r in _rows(db) if allowed_lists is None or r.list_name in allowed_lists]
    try:
        lookup_word_store.load_lookup_vectors(db, model)
    except Exception:  # noqa: BLE001 - the embedder below covers what is not stored
        logger.warning("lookup try: stored vectors not loaded", exc_info=True)
    embed = ll.embedder(db)
    return span_extract.explain_phrase(phrase, rows, embed)
