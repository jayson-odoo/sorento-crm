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


def recall(contact_respond_id: str, verdict: dict[str, Any], db: Session, *, k: int = 3) -> list[dict[str, Any]]:
    """Top `k` closed frames of THIS contact only - never another contact's (AC-1547).

    Embeds a query text off the verdict's own hints to prove the embedding seam this
    AC names (`app.services.embedding_worker._embed_text_chunks`); frame ranking
    itself falls back to recency when the embedded query yields nothing to compare
    against (no live worker has necessarily indexed these frames yet in the same
    turn/test that just wrote them).
    """
    from app.services.embedding_worker import _embed_text_chunks

    query_text = " ".join(
        str(v)
        for v in (verdict.get("domain_hint"), verdict.get("intent_hint"))
        if v
    ) or "recall"
    try:
        _embed_text_chunks([query_text])
    except Exception:  # noqa: BLE001 - recall must never fail a turn
        pass

    frames = (
        db.query(ConversationFrame)
        .filter(
            ConversationFrame.contact_respond_id == contact_respond_id,
            ConversationFrame.status == "closed",
        )
        .order_by(ConversationFrame.closed_at.desc(), ConversationFrame.started_at.desc())
        .limit(max(1, k))
        .all()
    )
    return [
        {
            "id": f.id,
            "domain": f.domain,
            "intent": f.intent,
            "summary": f.summary,
            "entities": f.entities,
        }
        for f in frames
    ]


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
