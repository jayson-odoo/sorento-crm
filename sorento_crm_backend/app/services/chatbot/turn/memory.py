# Memory: episode write (AC-1546), recall (AC-1547), the profile hint block
# (AC-1548) - PLAN-chatbot-turn-rearch.md "State: three shelves". Episodes reuse the
# existing `conversation_frames` table and embedding queue; recall is a plain
# contact-scoped read (never another contact's frames), the embed call proves the
# seam AC-1547 names without depending on a worker having drained it in the same test.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.conversation_frame import ConversationFrame
from app.services.chatbot.turn.state import Profile

SOURCE_TYPE_CONVERSATION_FRAME = "conversation_frame"


def write_episode(
    db: Session,
    *,
    contact_respond_id: str,
    domain: str | None,
    intent: str | None,
    entities: dict[str, Any],
    tools_used: list[str],
    turn_ids: list[str],
    summary: str | None,
    close_reason: str,
    contact_id: str | None = None,
    space_id: str | None = None,
    channel: str | None = None,
) -> ConversationFrame:
    """One `conversation_frames` row for a closed topic (contract: "the tail writes
    one conversation_frames row for the closed topic and enqueues its embedding").

    A direct closed-row insert, not `FrameService.open_frame`/`close_frame` - those
    validate `reason` against a fixed set (`topic_switch`, `role_switch`, `idle`,
    `session_end`, `manual`) that does not include this AC's own `conversation_close`,
    and an episode here is written ONCE, already closed, never opened-then-patched.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    frame = ConversationFrame(
        contact_id=contact_id or contact_respond_id,
        contact_respond_id=contact_respond_id,
        space_id=space_id or "0",
        channel=channel or "whatsapp",
        domain=domain,
        intent=intent,
        entities=entities or {},
        active_entities=entities or {},
        tools_used=list(tools_used or []),
        turn_ids=list(turn_ids or []),
        summary=summary,
        status="closed",
        close_reason=close_reason,
        started_at=now,
        opened_at=now,
        closed_at=now,
    )
    db.add(frame)
    db.commit()
    db.refresh(frame)

    if summary:
        from app.services.embedding_service import EmbeddingEventService

        EmbeddingEventService(db).queue_event(
            source_type=SOURCE_TYPE_CONVERSATION_FRAME,
            source_id=str(frame.id),
            event_type="frame_closed",
            source_updated_at=frame.closed_at,
            changed_fields=["summary"],
            payload={
                "contact_respond_id": frame.contact_respond_id,
                "domain": frame.domain,
                "intent": frame.intent,
                "close_reason": frame.close_reason,
            },
        )

    return frame


def _frame_out(frame: ConversationFrame) -> dict[str, Any]:
    return {
        "id": frame.id,
        "domain": frame.domain,
        "intent": frame.intent,
        "summary": frame.summary,
        "entities": frame.entities,
    }


def _by_recency(db: Session, contact_respond_id: str, k: int) -> list[ConversationFrame]:
    return (
        db.query(ConversationFrame)
        .filter(
            ConversationFrame.contact_respond_id == contact_respond_id,
            ConversationFrame.status == "closed",
        )
        .order_by(ConversationFrame.closed_at.desc(), ConversationFrame.started_at.desc())
        .limit(max(1, k))
        .all()
    )


def _similarity_of_frame(vector: Any) -> Any:
    """Best cosine similarity between `vector` and any CURRENT chunk of the frame.

    A correlated scalar per frame rather than a join, for two reasons. A frame embeds as
    several chunks, and a join would return the frame once per chunk. And a frame with NO
    chunk at all has to survive: the worker indexes a frame after the turn that closed
    it, so the frames worth recalling in the very next turn are exactly the ones an inner
    join would drop. This yields NULL for them, which sorts last and leaves recency to
    order them.
    """
    from sqlalchemy import String, cast, func, select

    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument

    return (
        select(func.max(1 - EmbeddingChunk.embedding.cosine_distance(vector)))
        .select_from(EmbeddingChunk)
        .join(EmbeddingDocument, EmbeddingDocument.id == EmbeddingChunk.document_id)
        .where(
            EmbeddingChunk.is_current.is_(True),
            EmbeddingDocument.is_active.is_(True),
            EmbeddingChunk.source_type == "conversation_frame",
            EmbeddingChunk.source_id == cast(ConversationFrame.id, String),
        )
        .correlate(ConversationFrame)
        .scalar_subquery()
    )


def recall(contact_respond_id: str, verdict: dict[str, Any], db: Session, *, k: int = 3) -> list[dict[str, Any]]:
    """Top `k` closed frames of THIS contact only - never another contact's (AC-1547).

    Ordered by vector similarity to the turn's own query, THEN by recency, which is what
    the AC asks for and what makes recall worth doing: three frames picked by recency
    alone are the last three topics, which is the same answer whatever the customer just
    said. The query is embedded through `embedding_worker._embed_text_chunks`, the same
    helper that indexed the frames, so the model and dimension match.

    Recency is the fallback, not a second-class path: an embedding failure, a database
    with no pgvector, or a frame the worker has not indexed yet all have to keep
    answering. The first two fall back wholesale; the third sorts last within the same
    query (see `_similarity_of_frame`).
    """
    from app.services.embedding_worker import _embed_text_chunks

    query_words = " ".join(
        str(v)
        for v in (verdict.get("domain_hint"), verdict.get("intent_hint"))
        if v
    ) or "recall"
    try:
        vectors = _embed_text_chunks([query_words])
    except Exception:  # noqa: BLE001 - recall must never fail a turn
        vectors = []

    frames: list[ConversationFrame] = []
    if vectors:
        from sqlalchemy import nulls_last

        similarity = _similarity_of_frame(vectors[0]).label("similarity")
        try:
            # A SAVEPOINT, not a bare try: a failed statement aborts the whole Postgres
            # transaction, so without one an install with no pgvector would take the
            # recency fallback down with it AND lose whatever the turn had already
            # written. `begin_nested` rolls back only this query.
            with db.begin_nested():
                rows = (
                    db.query(ConversationFrame, similarity)
                    .filter(
                        ConversationFrame.contact_respond_id == contact_respond_id,
                        ConversationFrame.status == "closed",
                    )
                    .order_by(
                        nulls_last(similarity.desc()),
                        ConversationFrame.closed_at.desc(),
                        ConversationFrame.started_at.desc(),
                    )
                    .limit(max(1, k))
                    .all()
                )
            frames = [row[0] for row in rows]
        except Exception:  # noqa: BLE001 - recall must never fail a turn
            frames = []
    if not frames:
        frames = _by_recency(db, contact_respond_id, k)
    return [_frame_out(f) for f in frames]


def episodes_block(frames: list[dict[str, Any]]) -> str:
    """The `Episodes:` hint block handed to the parser's second call (recall)."""
    lines = ["Episodes:"]
    for f in frames:
        summary = f.get("summary") or ""
        domain = f.get("domain") or ""
        lines.append(f"- ({domain}) {summary}".rstrip())
    return "\n".join(lines)


def profile_block(profile: Profile) -> str:
    """`Profile:` rendered on every parse (AC-1548) - tier, language, default ledgers."""
    lines = ["Profile:"]
    if profile.tier:
        lines.append(f"tier: {profile.tier}")
    if profile.language:
        lines.append(f"language: {profile.language}")
    if profile.default_ledgers:
        lines.append(f"default_ledgers: {', '.join(profile.default_ledgers)}")
    return "\n".join(lines)
