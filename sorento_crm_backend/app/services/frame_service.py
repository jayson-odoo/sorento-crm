"""Conversation frame service: open / update / close / search per-topic frames.

Used by n8n chatbot orchestration to persist structured working memory across
turns and recall earlier topics via vector search. On close, the frame's
summary is enqueued in the existing embedding pipeline with
source_type='conversation_frame'; retrieval joins back to the frame row for
structured re-hydration of access_levels_used, active_entities, etc.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, and_, cast
from sqlalchemy.orm import Session

from app.models.conversation_frame import ConversationFrame
from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
from app.services.embedding_service import EmbeddingEventService, EmbeddingReadService

SOURCE_TYPE_CONVERSATION_FRAME = "conversation_frame"

_VALID_CLOSE_REASONS = {"topic_switch", "role_switch", "idle", "session_end", "manual"}

_MUTABLE_PATCH_KEYS = {
    "domain",
    "intent",
    "active_entities",
    "access_levels_used",
    "tools_used",
    "result_refs",
    "pending_request",
    "last_user_message",
    "last_assistant_summary",
}


class FrameService:
    def __init__(self, db: Session):
        self.db = db

    # ------------- read -------------

    def get_open_frame(
        self,
        contact_id: str,
        space_id: str,
        channel: str,
    ) -> Optional[ConversationFrame]:
        return (
            self.db.query(ConversationFrame)
            .filter(
                ConversationFrame.contact_id == contact_id,
                ConversationFrame.space_id == space_id,
                ConversationFrame.channel == channel,
                ConversationFrame.status == "open",
            )
            .order_by(ConversationFrame.started_at.desc())
            .first()
        )

    def get_by_id(self, frame_id: str) -> Optional[ConversationFrame]:
        return self.db.query(ConversationFrame).filter(ConversationFrame.id == frame_id).first()

    # ------------- write -------------

    def open_frame(
        self,
        *,
        contact_id: str,
        space_id: str,
        channel: str,
        domain: Optional[str] = None,
        intent: Optional[str] = None,
        active_entities: Optional[dict[str, Any]] = None,
        access_levels_used: Optional[list[str]] = None,
        tools_used: Optional[list[str]] = None,
        result_refs: Optional[list[Any]] = None,
        pending_request: Optional[dict[str, Any]] = None,
        last_user_message: Optional[str] = None,
        last_assistant_summary: Optional[str] = None,
    ) -> ConversationFrame:
        # Defensive: close any stale open frame for the same contact/channel.
        stale = self.get_open_frame(contact_id, space_id, channel)
        if stale is not None:
            self._mark_closed(
                stale,
                reason="session_end",
                summary=stale.summary or stale.last_assistant_summary or stale.last_user_message,
                enqueue_embedding=False,
            )

        frame = ConversationFrame(
            contact_id=contact_id,
            space_id=space_id,
            channel=channel,
            domain=domain,
            intent=intent,
            active_entities=active_entities or {},
            access_levels_used=access_levels_used or [],
            tools_used=tools_used or [],
            result_refs=result_refs or [],
            pending_request=pending_request or {},
            last_user_message=last_user_message,
            last_assistant_summary=last_assistant_summary,
            status="open",
        )
        self.db.add(frame)
        self.db.commit()
        self.db.refresh(frame)
        return frame

    def update_frame(self, frame_id: str, patch: dict[str, Any]) -> ConversationFrame:
        frame = self.get_by_id(frame_id)
        if frame is None:
            raise ValueError(f"Frame not found: {frame_id}")
        if frame.status != "open":
            raise ValueError(f"Cannot update non-open frame {frame_id} (status={frame.status})")

        for key, value in patch.items():
            if key not in _MUTABLE_PATCH_KEYS:
                continue
            setattr(frame, key, value)

        frame.last_activity_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(frame)
        return frame

    def close_frame(
        self,
        frame_id: str,
        *,
        reason: str,
        summary: Optional[str] = None,
    ) -> ConversationFrame:
        if reason not in _VALID_CLOSE_REASONS:
            raise ValueError(f"Invalid close reason: {reason}")
        frame = self.get_by_id(frame_id)
        if frame is None:
            raise ValueError(f"Frame not found: {frame_id}")
        if frame.status == "closed":
            return frame

        self._mark_closed(frame, reason=reason, summary=summary, enqueue_embedding=True)
        return frame

    def _mark_closed(
        self,
        frame: ConversationFrame,
        *,
        reason: str,
        summary: Optional[str],
        enqueue_embedding: bool,
    ) -> None:
        frame.status = "closed"
        frame.close_reason = reason
        frame.closed_at = datetime.utcnow()
        if summary is not None:
            frame.summary = summary
        self.db.commit()
        self.db.refresh(frame)

        if enqueue_embedding and frame.summary:
            EmbeddingEventService(self.db).queue_event(
                source_type=SOURCE_TYPE_CONVERSATION_FRAME,
                source_id=str(frame.id),
                event_type="frame_closed",
                source_updated_at=frame.closed_at,
                changed_fields=["summary"],
                payload={
                    "contact_id": frame.contact_id,
                    "space_id": frame.space_id,
                    "channel": frame.channel,
                    "domain": frame.domain,
                    "intent": frame.intent,
                    "access_levels_used": list(frame.access_levels_used or []),
                    "closed_at": frame.closed_at.isoformat() if frame.closed_at else None,
                },
            )

    # ------------- search -------------

    def search_frames(
        self,
        *,
        contact_id: str,
        space_id: str,
        query_text: str,
        k: int = 3,
    ) -> list[dict[str, Any]]:
        if not query_text or not query_text.strip():
            return []

        # Embed query using the worker's text-embedding helper to stay aligned
        # on model + dimension with what was indexed at frame-close time.
        from app.services.embedding_worker import _embed_text_chunks  # local import to avoid cycle

        try:
            vectors = _embed_text_chunks([query_text.strip()])
        except Exception:
            return []
        if not vectors:
            return []
        query_embedding = vectors[0]

        similarity_expr = (1 - EmbeddingChunk.embedding.cosine_distance(query_embedding)).label("similarity")
        rows = (
            self.db.query(EmbeddingChunk, ConversationFrame, similarity_expr)
            .join(EmbeddingDocument, EmbeddingDocument.id == EmbeddingChunk.document_id)
            .join(
                ConversationFrame,
                cast(ConversationFrame.id, String) == EmbeddingChunk.source_id,
            )
            .filter(
                EmbeddingChunk.is_current.is_(True),
                EmbeddingDocument.is_active.is_(True),
                EmbeddingChunk.source_type == SOURCE_TYPE_CONVERSATION_FRAME,
                ConversationFrame.contact_id == contact_id,
                ConversationFrame.space_id == space_id,
                ConversationFrame.status == "closed",
            )
            .order_by(similarity_expr.desc())
            .limit(max(1, min(k, 10)))
            .all()
        )

        results: list[dict[str, Any]] = []
        for _chunk, frame, similarity in rows:
            results.append(
                {
                    "frame_id": str(frame.id),
                    "domain": frame.domain,
                    "intent": frame.intent,
                    "active_entities": frame.active_entities or {},
                    "access_levels_used": list(frame.access_levels_used or []),
                    "tools_used": list(frame.tools_used or []),
                    "summary": frame.summary,
                    "closed_at": frame.closed_at.isoformat() if frame.closed_at else None,
                    "similarity_score": float(similarity),
                }
            )
        return results
