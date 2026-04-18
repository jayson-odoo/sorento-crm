"""Core services for embedding event queue and retrieval."""
from __future__ import annotations

from datetime import datetime
import hashlib
import uuid
import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_
from sqlalchemy import func

from app.config import settings
from app.models.embeddings import EmbeddingQueue, EmbeddingDocument, EmbeddingChunk
from app.services.queue_service import enqueue_job

logger = logging.getLogger(__name__)


EMBEDDING_NOISE_FIELDS = {"created_at", "updated_at", "updated_by", "synced_to_excel", "last_synced_to_excel"}


class EmbeddingEventService:
    def __init__(self, db: Session):
        self.db = db

    def queue_event(
        self,
        *,
        source_type: str,
        source_id: str,
        event_type: str,
        source_key: Optional[str] = None,
        source_updated_at: Optional[datetime] = None,
        changed_fields: Optional[list[str]] = None,
        payload: Optional[dict[str, Any]] = None,
        triggered_by: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> EmbeddingQueue:
        changed_fields = changed_fields or []
        if changed_fields and not self._has_semantic_change(changed_fields):
            logger.debug("Skip embedding queue event for %s:%s due to non-semantic changes", source_type, source_id)
            raise ValueError("No embedding-relevant fields changed")

        event_id = str(uuid.uuid4())
        correlation_id = correlation_id or str(uuid.uuid4())
        event_payload = {
            "event_id": event_id,
            "event_type": event_type,
            "event_version": 1,
            "occurred_at": datetime.utcnow().isoformat(),
            "source_type": source_type,
            "source_id": source_id,
            "source_key": source_key,
            "source_updated_at": source_updated_at.isoformat() if source_updated_at else None,
            "changed_fields": changed_fields,
            "correlation_id": correlation_id,
            "triggered_by": triggered_by,
            "payload": payload or {},
        }
        queue_item = EmbeddingQueue(
            source_type=source_type,
            source_id=source_id,
            event_type=event_type,
            event_version=1,
            source_updated_at=source_updated_at,
            payload=event_payload,
            status="pending",
            correlation_id=correlation_id,
        )
        self.db.add(queue_item)
        self.db.flush()

        job = enqueue_job(
            _get_embedding_worker(),
            str(queue_item.id),
            queue_name=settings.embedding_queue_name,
            job_timeout=900,
        )
        queue_item.rq_job_id = job.id
        self.db.commit()
        self.db.refresh(queue_item)
        return queue_item

    def request_rebuild(self, source_type: str, source_id: str, triggered_by: Optional[str] = None) -> EmbeddingQueue:
        return self.queue_event(
            source_type=source_type,
            source_id=source_id,
            event_type="embedding.rebuild_requested",
            changed_fields=["manual_rebuild"],
            triggered_by=triggered_by or "system",
        )

    @staticmethod
    def _has_semantic_change(changed_fields: list[str]) -> bool:
        return any(field not in EMBEDDING_NOISE_FIELDS for field in changed_fields)


class EmbeddingReadService:
    def __init__(self, db: Session):
        self.db = db

    def find_latest_current_hash(
        self,
        source_type: str,
        source_id: str,
        model_name: str,
        model_version: str,
    ) -> Optional[str]:
        row = (
            self.db.query(EmbeddingChunk.source_hash)
            .filter(
                EmbeddingChunk.source_type == source_type,
                EmbeddingChunk.source_id == source_id,
                EmbeddingChunk.is_current.is_(True),
                EmbeddingChunk.model_name == model_name,
                EmbeddingChunk.model_version == model_version,
            )
            .first()
        )
        return row[0] if row else None

    def mark_previous_non_current(self, source_type: str, source_id: str, model_name: str, model_version: str) -> None:
        now = datetime.utcnow()
        (
            self.db.query(EmbeddingChunk)
            .filter(
                EmbeddingChunk.source_type == source_type,
                EmbeddingChunk.source_id == source_id,
                EmbeddingChunk.model_name == model_name,
                EmbeddingChunk.model_version == model_version,
                EmbeddingChunk.is_current.is_(True),
            )
            .update({EmbeddingChunk.is_current: False, EmbeddingChunk.superseded_at: now}, synchronize_session=False)
        )

    @staticmethod
    def deterministic_hash(payload: dict[str, Any]) -> str:
        body = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def search_current(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        source_type: Optional[str] = None,
        visibility_scope: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[tuple[EmbeddingChunk, EmbeddingDocument, float]]:
        similarity_expr = (1 - EmbeddingChunk.embedding.cosine_distance(query_embedding)).label("similarity")
        filters = [EmbeddingChunk.is_current.is_(True), EmbeddingDocument.is_active.is_(True)]
        if source_type:
            filters.append(EmbeddingChunk.source_type == source_type)
        if visibility_scope:
            filters.append(EmbeddingDocument.visibility_scope == visibility_scope)
        if tenant_id:
            filters.append(EmbeddingDocument.metadata_json["tenant_id"].astext == tenant_id)
        rows = (
            self.db.query(EmbeddingChunk, EmbeddingDocument, similarity_expr)
            .join(EmbeddingDocument, EmbeddingDocument.id == EmbeddingChunk.document_id)
            .filter(and_(*filters))
            .order_by(similarity_expr.desc())
            .limit(max(1, min(top_k, 30)))
            .all()
        )
        return rows

    def queue_metrics(self) -> dict[str, int]:
        rows = (
            self.db.query(EmbeddingQueue.status, func.count(EmbeddingQueue.id))
            .group_by(EmbeddingQueue.status)
            .all()
        )
        counts = {status: int(count) for status, count in rows}
        return {
            "pending": counts.get("pending", 0),
            "processing": counts.get("processing", 0),
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
            "dead_letter": counts.get("dead_letter", 0),
            "skipped": counts.get("skipped", 0),
        }

    def replay_dead_letters(self, limit: int = 100) -> int:
        items = (
            self.db.query(EmbeddingQueue)
            .filter(EmbeddingQueue.status == "dead_letter")
            .order_by(EmbeddingQueue.created_at.asc())
            .limit(max(1, min(limit, 1000)))
            .all()
        )
        for item in items:
            item.status = "pending"
            item.available_at = datetime.utcnow()
        self.db.commit()
        for item in items:
            job = enqueue_job(
                _get_embedding_worker(),
                str(item.id),
                queue_name=settings.embedding_queue_name,
                job_timeout=900,
            )
            item.rq_job_id = job.id
        self.db.commit()
        return len(items)


def _get_embedding_worker():
    # Imported lazily to avoid circular imports.
    from app.services.embedding_worker import process_embedding_queue_item

    return process_embedding_queue_item
