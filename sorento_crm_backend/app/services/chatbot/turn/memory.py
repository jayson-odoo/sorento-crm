# Memory: episode write (AC-1546), recall (AC-1547), the profile hint block
# (AC-1548) - PLAN-chatbot-turn-rearch.md "State: three shelves". Episodes reuse the
# existing `conversation_frames` table and embedding queue; recall is a plain
# contact-scoped read (never another contact's frames), the embed call proves the
# seam AC-1547 names without depending on a worker having drained it in the same test.
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import String, cast, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.chatbot_turn import ChatbotTurn
from app.models.conversation_frame import ConversationFrame
from app.services.chatbot.turn.episode_digest import digest
from app.services.chatbot.turn.state import Profile

SOURCE_TYPE_CONVERSATION_FRAME = "conversation_frame"

#: Contract section 2: the four values a context level is ever stored as. "off" is a
#: legitimate OWN level (a contact explicitly opted out even while the system default
#: is on), so it wins over the system default exactly like the other three.
VALID_MEMORY_LEVELS: tuple[str, ...] = ("off", "conversation", "past", "full")

#: Contract section 3 / PLAN 5.5 (Q7 ruling): retention is a COUNT, never a date.
#: Trimmed on write, never by a scheduled sweep.
KEEP_EPISODES = 20


def effective_level(contact_level: str | None, system_memory: dict[str, Any] | None) -> str:
    """The level a turn actually reads (contract section 2): the contact's own level
    when it is one of the four valid values (INCLUDING "off" - an explicit opt-out
    beats the system default); otherwise the system default when memory is switched
    on; otherwise "off"."""
    if contact_level in VALID_MEMORY_LEVELS:
        return contact_level
    memory = system_memory or {}
    if memory.get("enabled") is True:
        default_level = memory.get("default_level")
        if default_level in VALID_MEMORY_LEVELS:
            return default_level
    return "off"


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


def _naive_utc(when: datetime) -> datetime:
    """A naive UTC `datetime`, whatever timezone-awareness it arrived with - every
    frame timestamp is naive UTC, same as every other backend timestamp."""
    if when.tzinfo is not None:
        return when.astimezone(timezone.utc).replace(tzinfo=None)
    return when


def _turn_message_text(row: ChatbotTurn) -> str:
    """The customer's own text for this turn, read off the stored envelope - never the
    reply, never the parser's derived verdict (AC-MEM022: outcome reads structured
    data, never text; this is display-only, for `last_user_message`)."""
    envelope = row.envelope if isinstance(row.envelope, dict) else {}
    inner = (envelope.get("message") or {}).get("message") or {}
    text_value = (inner.get("message") or {}).get("text")
    return str(text_value) if text_value else ""


def _turn_to_digest_dict(row: ChatbotTurn) -> dict[str, Any]:
    """Project one `chatbot.turns` row into `episode_digest.digest()`'s input shape."""
    trace = row.trace if isinstance(row.trace, list) else []
    return {
        "id": row.id,
        "created_at": row.created_at,
        "branch_kind": row.branch_kind,
        "status": row.status,
        "message": _turn_message_text(row),
        "trace": trace,
        "result_refs": [],
    }


def _trim_to_newest(db: Session, *, contact_respond_id: str, is_test: bool) -> None:
    """Contract section 3 / PLAN 5.5: the newest `KEEP_EPISODES` frames survive, per
    contact AND per world - writing the 21st deletes the oldest in the SAME
    transaction as the insert. Never a scheduled sweep."""
    keep_ids = (
        select(ConversationFrame.id)
        .where(
            ConversationFrame.contact_respond_id == contact_respond_id,
            ConversationFrame.is_test.is_(is_test),
        )
        .order_by(ConversationFrame.last_activity_at.desc())
        .limit(KEEP_EPISODES)
    )
    db.query(ConversationFrame).filter(
        ConversationFrame.contact_respond_id == contact_respond_id,
        ConversationFrame.is_test.is_(is_test),
        ~ConversationFrame.id.in_(keep_ids),
    ).delete(synchronize_session=False)


def write_episode_for_reset(
    db: Session,
    *,
    contact_respond_id: str,
    is_test: bool,
    resetting_turn_id: str,
) -> ConversationFrame | None:
    """Close the episode a topic-reset turn just ended (contract section 3).

    The range is this contact's `chatbot.turns` on the same `is_test` WORLD that are
    not yet part of any of this contact-and-world's frames, excluding the resetting
    turn itself, oldest first - read through the ORM (never raw SQL: `chatbot.turns`
    lives in its own Postgres schema and only ORM constructs go through the test
    fixture's `schema_translate_map`, `turn_runtime.turn_number`'s own docstring).
    Membership rather than a `last_activity_at` cutoff, so a turn that lands with a
    created_at at or before the last frame's boundary (commit-order jitter, a backfill
    replaying history) is still picked up.

    Two guard rails around the membership test, both needed once a caller (the
    backfill script) can call this over turns that ALL already exist rather than one
    at a time as the live engine does:

    * An UPPER bound at the resetting turn's own `created_at`, when it is a real row
      (a synthetic id - `test_two_calls_over_the_same_range_produce_one_frame` - has
      none, and skips the bound). Without it, membership alone cannot tell a turn
      that has not happened yet (in insertion order) from one that is simply not yet
      closed, and a full-history backfill run - every turn already in the table -
      would close ranges out of order.
    * A LOWER bound at the OLDEST currently-surviving frame's `started_at`, when one
      exists. Retention trims by COUNT (`KEEP_EPISODES`), on purpose (contract section
      3 / PLAN 5.5): once a frame ages out, its turns must stay forgotten, not get
      re-derived into a new frame the next time this runs over the same history - or a
      repeated backfill would churn forever instead of being idempotent.

    Empty range writes nothing. The insert is `ON CONFLICT DO NOTHING` against the
    unique `(contact_respond_id, is_test, turn_ids[1])` index, so two callers racing
    over the identical range produce exactly one frame; the loser reads back `None`
    rather than the winner's row (D14: this path has no reason to disagree with the
    winner's summary). No embedding is enqueued (contract section 3: recall is
    deleted in S3; this writer never had a reader to serve).
    """
    upper_bound = (
        db.query(ChatbotTurn.created_at)
        .filter(ChatbotTurn.id == resetting_turn_id)
        .scalar()
    )
    lower_bound = (
        db.query(ConversationFrame.started_at)
        .filter(
            ConversationFrame.contact_respond_id == contact_respond_id,
            ConversationFrame.is_test.is_(is_test),
        )
        .order_by(ConversationFrame.started_at.asc())
        .limit(1)
        .scalar()
    )
    already_closed = (
        select(func.unnest(ConversationFrame.turn_ids))
        .where(
            ConversationFrame.contact_respond_id == contact_respond_id,
            ConversationFrame.is_test.is_(is_test),
        )
        .scalar_subquery()
    )
    query = db.query(ChatbotTurn).filter(
        ChatbotTurn.contact_respond_id == contact_respond_id,
        ChatbotTurn.is_test.is_(is_test),
        ChatbotTurn.id != resetting_turn_id,
        # `turn_ids` is `ARRAY(Text)` (it also carries synthetic ids in tests and the
        # pre-rearch reader) while `chatbot.turns.id` is UUID - cast to compare.
        ~cast(ChatbotTurn.id, String).in_(already_closed),
    )
    if upper_bound is not None:
        query = query.filter(ChatbotTurn.created_at <= upper_bound)
    if lower_bound is not None:
        query = query.filter(ChatbotTurn.created_at >= lower_bound)
    rows = query.order_by(ChatbotTurn.created_at.asc()).all()
    if not rows:
        return None

    result = digest([_turn_to_digest_dict(r) for r in rows])
    turn_ids = [r.id for r in rows]
    started_at = _naive_utc(rows[0].created_at)
    last_activity_at = _naive_utc(rows[-1].created_at)
    closed_at = datetime.now(timezone.utc).replace(tzinfo=None)

    table = ConversationFrame.__table__
    stmt = (
        pg_insert(table)
        .values(
            id=str(uuid.uuid4()),
            contact_id=contact_respond_id,
            contact_respond_id=contact_respond_id,
            space_id="0",
            channel="whatsapp",
            domain=result.get("domain"),
            intent=result.get("intent"),
            entities=result.get("entities") or {},
            active_entities=result.get("entities") or {},
            tools_used=result.get("tools_used") or [],
            result_refs=result.get("result_refs") or [],
            turn_ids=turn_ids,
            summary=result.get("summary"),
            last_user_message=result.get("last_user_message"),
            status="closed",
            close_reason=result.get("close_reason") or "topic_switch",
            started_at=started_at,
            opened_at=started_at,
            last_activity_at=last_activity_at,
            closed_at=closed_at,
            is_test=is_test,
        )
        .on_conflict_do_nothing(
            index_elements=[
                table.c.contact_respond_id,
                table.c.is_test,
                text("(turn_ids[1])"),
            ]
        )
        .returning(table.c.id)
    )
    inserted_id = db.execute(stmt).scalar()
    if inserted_id is None:
        # ON CONFLICT DO NOTHING fired: another writer already closed this exact
        # range. Nothing of ours landed, so there is nothing of ours to trim for.
        return None

    _trim_to_newest(db, contact_respond_id=contact_respond_id, is_test=is_test)
    db.commit()

    return db.query(ConversationFrame).filter(ConversationFrame.id == inserted_id).first()


# `recall`, `_by_recency`, `_similarity_of_frame`, `_frame_out` and `episodes_block`
# (the AC-1547 second-parse recall path and its own hint block) are DELETED here
# (chatbot memory lane A, contract section 3, Q5 ruling) - the last-3-summaries
# context layer (`turn/context.py`'s L4) replaces what recall existed to do, in
# the SAME parser call rather than a second one. `/external/memory/frames/search`
# keeps answering (`FrameService.search_frames`, never routed through this
# module).


def profile_block(profile: Profile) -> str:
    """`Profile:` rendered on every parse that has something to say (AC-1548) -
    tier, language, default ledgers. Empty (AC-MEM042, chatbot memory lane A) when
    none of the three are set, so `parser.build_user_block`'s `if profile_block:`
    guard skips the line entirely rather than sending a bare "Profile:" header."""
    lines: list[str] = []
    if profile.tier:
        lines.append(f"tier: {profile.tier}")
    if profile.language:
        lines.append(f"language: {profile.language}")
    if profile.default_ledgers:
        lines.append(f"default_ledgers: {', '.join(profile.default_ledgers)}")
    if not lines:
        return ""
    return "\n".join(["Profile:", *lines])
