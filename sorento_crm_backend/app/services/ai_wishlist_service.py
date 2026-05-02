"""Service for tracking unanswered AI assistant queries and exposing clusters.

The clustering itself is performed offline by ``app.jobs.ai_wishlist_clustering``;
this module is the read/write boundary used at request time (insert link rows
when a turn was unanswered) and at admin read time (list clusters).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.ai_assistant import (
    AIAssistantUnansweredQuery,
    AIAssistantWishlistCluster,
)


logger = logging.getLogger(__name__)


class AiWishlistService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def tag_unanswered(self, message_id: str) -> None:
        """Insert (or no-op on conflict) a placeholder row for clustering.

        The nightly job fills in the embedding + cluster_id later.
        """
        if not message_id:
            return
        existing = (
            self.db.query(AIAssistantUnansweredQuery)
            .filter(AIAssistantUnansweredQuery.message_id == message_id)
            .first()
        )
        if existing:
            return
        try:
            row = AIAssistantUnansweredQuery(message_id=message_id)
            self.db.add(row)
            self.db.commit()
        except Exception:
            logger.exception("Failed to tag unanswered query message_id=%s", message_id)
            self.db.rollback()

    def list_clusters(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = (
            self.db.query(AIAssistantWishlistCluster)
            .order_by(AIAssistantWishlistCluster.count.desc(), AIAssistantWishlistCluster.last_seen_at.desc())
            .limit(max(1, int(limit)))
            .all()
        )
        return [
            {
                "id": str(r.id),
                "representative_question": r.representative_question or "",
                "category": r.category,
                "count": int(r.count or 0),
                "last_seen_at": r.last_seen_at,
                "created_at": r.created_at,
            }
            for r in rows
        ]
