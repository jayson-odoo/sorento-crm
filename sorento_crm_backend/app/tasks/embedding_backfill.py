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

