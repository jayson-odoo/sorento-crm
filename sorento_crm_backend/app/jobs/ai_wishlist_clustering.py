"""Cluster unanswered AI assistant queries by cosine similarity.

Run with::

    python -m app.jobs.ai_wishlist_clustering

The job is idempotent: it embeds any unanswered queries from the past 30 days
that don't yet have an embedding, finds the closest existing cluster (cosine
threshold 0.85) or creates a new one, and refreshes ``count`` /
``last_seen_at`` on the matched cluster.

If pgvector is not available on the database, embeddings are stored as JSON
arrays in the ``embedding`` column; the similarity math is then performed in
Python instead of via SQL.
"""
from __future__ import annotations

import logging
import math
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.ai_assistant import (
    AIAssistantMessage,
    AIAssistantUnansweredQuery,
    AIAssistantWishlistCluster,
)
from app.services.llm_provider import OpenAIProvider


logger = logging.getLogger(__name__)

CLUSTER_SIM_THRESHOLD = 0.85
WINDOW_DAYS = 30


def _get_embedder() -> Optional[OpenAIProvider]:
    if not settings.openai_api_key:
        logger.warning("ai_wishlist_clustering: OPENAI_API_KEY not set; cannot embed unanswered queries")
        return None
    return OpenAIProvider(settings.openai_api_key, settings.embedding_model_name)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _embedding_to_list(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, list):
        return [float(x) for x in value]
    # pgvector returns numpy-like arrays; coerce
    try:
        return [float(x) for x in value]  # type: ignore[arg-type]
    except Exception:
        return []


def _find_best_cluster(
    db: Session,
    embedding: list[float],
) -> tuple[Optional[AIAssistantWishlistCluster], float]:
    """Return (cluster, similarity) for the closest existing cluster, or (None, 0.0)."""
    clusters = db.query(AIAssistantWishlistCluster).all()
    best: Optional[AIAssistantWishlistCluster] = None
    best_score = 0.0
    for cluster in clusters:
        existing = _embedding_to_list(cluster.representative_embedding)
        if not existing:
            continue
        score = _cosine(embedding, existing)
        if score > best_score:
            best = cluster
            best_score = score
    return best, best_score


def run_clustering_job(*, db: Optional[Session] = None) -> dict[str, int]:
    """Embed and cluster the recent unanswered queries.

    Returns a small report dict for logging/CLI use.
    """
    own_session = db is None
    session = db or SessionLocal()
    try:
        embedder = _get_embedder()
        if embedder is None:
            return {"processed": 0, "skipped": 0, "new_clusters": 0, "matched": 0}

        cutoff = datetime.utcnow() - timedelta(days=WINDOW_DAYS)
        rows = (
            session.query(AIAssistantUnansweredQuery, AIAssistantMessage)
            .join(AIAssistantMessage, AIAssistantMessage.id == AIAssistantUnansweredQuery.message_id)
            .filter(AIAssistantUnansweredQuery.created_at >= cutoff)
            .all()
        )

        processed = 0
        skipped = 0
        new_clusters = 0
        matched = 0

        for unanswered, message in rows:
            existing = _embedding_to_list(unanswered.embedding)
            if existing and unanswered.cluster_id:
                skipped += 1
                continue
            text_value = (message.content or "").strip()
            if not text_value:
                skipped += 1
                continue
            try:
                vector = embedder.embed(text_value)
            except Exception:
                logger.exception("ai_wishlist_clustering: embedding failed for message_id=%s", message.id)
                skipped += 1
                continue
            unanswered.embedding = vector

            cluster, score = _find_best_cluster(session, vector)
            now = datetime.utcnow()
            if cluster is not None and score >= CLUSTER_SIM_THRESHOLD:
                cluster.count = int(cluster.count or 0) + 1
                cluster.last_seen_at = now
                unanswered.cluster_id = cluster.id
                matched += 1
            else:
                new_cluster = AIAssistantWishlistCluster(
                    representative_question=text_value[:1000],
                    count=1,
                    last_seen_at=now,
                    representative_embedding=vector,
                )
                session.add(new_cluster)
                session.flush()  # populate id
                unanswered.cluster_id = new_cluster.id
                new_clusters += 1

            processed += 1

        session.commit()
        report = {
            "processed": processed,
            "skipped": skipped,
            "new_clusters": new_clusters,
            "matched": matched,
        }
        logger.info("ai_wishlist_clustering report=%s", report)
        return report
    finally:
        if own_session:
            session.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    report = run_clustering_job()
    print(f"ai_wishlist_clustering: {report}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    # NOTE: ops should wire this to the scheduler (cron or scheduled_tasks
    # row); see app/main.py:startup_event for how other periodic jobs are
    # registered. Not auto-scheduled here to avoid breaking startup on
    # environments without OPENAI_API_KEY.
    sys.exit(main())
