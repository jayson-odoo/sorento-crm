"""RQ task: re-embed the keep-set records with the configured embedder, then let the guard flip the search
model (LOOKUP-EMBED-CENTRAL). Runs on the `imports` queue; the worker has no reload, restart it after edits."""
from __future__ import annotations

import logging

from app.database import SessionLocal

logger = logging.getLogger(__name__)


def run_records_backfill(model: str | None = None) -> dict:
    from app.models.embeddings import EmbeddingDocument  # noqa: F401  (mapper registration)
    from app.services.embedding_backfill_service import apply_search_model_guard, backfill_records
    from app.services.embedding_settings import resolve_embedder

    db = SessionLocal()
    try:
        if model is None:
            _provider, model = resolve_embedder(db)
        result = backfill_records(db, model)
        flipped = apply_search_model_guard(db, model)
        logger.info(
            "records backfill %s: embedded=%s failed=%s remaining=%s flipped=%s",
            model, result.embedded, result.failed, result.remaining, flipped,
        )
        return {
            "model": model, "embedded": result.embedded, "failed": result.failed,
            "remaining": result.remaining, "flipped": flipped,
        }
    finally:
        db.close()


def embed_missing_lookup_words() -> dict:
    """Keep the `lookup_word` documents and their vectors in step with the lookup rows (queue `imports`)."""
    from app.models.base import set_company_scope
    from app.services import lookup_word_store

    db = SessionLocal()
    try:
        set_company_scope(db, None)
        result = lookup_word_store.sync_lookup_words(db)
        db.commit()
        logger.info("lookup words sync: %s", result)
        return {
            "created": getattr(result, "created", 0), "updated": getattr(result, "updated", 0),
            "retired": getattr(result, "retired", 0), "embedded": getattr(result, "embedded", 0),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
