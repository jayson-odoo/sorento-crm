"""Fuzzy resolver: embedding pre-resolve + ilike expansion.

Used by list endpoints whose `*_query` parameters need to match shortforms,
fragments, and aliases (e.g. customer_query="YOTU" → "YOTU BUILDER SDN BHD").
Always falls back to raw ilike on the query term itself, so callers work even
when the embedding provider is unavailable or the source_type is not yet
indexed.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def resolve_via_embedding_then_ilike(
    db: Session,
    query: str,
    *,
    source_type: str,
    ilike_columns: list,
    canonical_model: Optional[Any] = None,
    canonical_fields: tuple[str, ...] = (),
    extra_filter_builders: Optional[list[Callable[[str], Any]]] = None,
    top_k: int = 10,
) -> tuple[Optional[Any], list[str]]:
    """Embedding pre-resolve + ilike expansion.

    Steps:
      1. Always include the raw `query` term as an ilike pattern.
      2. If `canonical_model` + `canonical_fields` provided, embed the query,
         top-k search the given `source_type`, look up the canonical fields on
         the matched rows, and add each canonical value as an ilike pattern.
      3. OR each pattern across `ilike_columns` and any `extra_filter_builders`
         (callables that take the LIKE pattern and return a clause — used for
         relationship.has(...) clauses or other cross-table OR branches).

    Returns `(filter_clause | None, matched_canonical_values)`. Embedding
    failures degrade silently to raw-ilike-only matching.
    """
    term = (query or "").strip()
    if not term:
        return None, []

    canonical_values: list[str] = []
    if canonical_model is not None and canonical_fields:
        try:
            from app.api.v1.external.rag import _embed_query
            from app.services.embedding_service import EmbeddingReadService

            vec = _embed_query(term)
            hits = EmbeddingReadService(db).search_current(
                vec, source_type=source_type, top_k=top_k
            )
            source_ids = [str(c.source_id) for c, _, _ in hits if c.source_id]
            if source_ids:
                cols = [getattr(canonical_model, f) for f in canonical_fields]
                rows = (
                    db.query(*cols)
                    .filter(canonical_model.id.in_(source_ids))
                    .all()
                )
                for row in rows:
                    # SQLAlchemy Row is iterable but not a tuple subclass; iterate
                    # directly so each column value is captured cleanly.
                    for v in tuple(row):
                        if v and v not in canonical_values:
                            canonical_values.append(str(v))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Fuzzy resolve failed for source_type=%s term=%r: %s",
                source_type,
                term,
                exc,
            )

    patterns = [term, *canonical_values]
    clauses = []
    for p in patterns:
        like = f"%{p}%"
        per_pattern = [c.ilike(like) for c in ilike_columns]
        if extra_filter_builders:
            per_pattern.extend(b(like) for b in extra_filter_builders)
        if per_pattern:
            clauses.append(or_(*per_pattern))
    if not clauses:
        return None, canonical_values
    return or_(*clauses), canonical_values
