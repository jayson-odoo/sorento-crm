"""Backfill closed episodes for every contact's LIVE chatbot turns (chatbot memory
lane A, contract section 3 / PLAN-chatbot-memory-26sep.md section 5.3).

For each contact, walks all `is_test = false` turns in order and closes an episode at
every turn whose `apply` verdict carries `topic_reset: true` - the SAME writer the live
engine calls (`app.services.chatbot.turn.memory.write_episode_for_reset`), so the
backfill and the live path can never disagree on a summary, entities or turn_ids for
the identical range (AC-MEM029): there is only one writer, and only one `digest()` it
calls.

Idempotent: `write_episode_for_reset`'s own `ON CONFLICT DO NOTHING` (on
`(contact_respond_id, is_test, turn_ids[1])`) makes a re-run over the same turns a
no-op, and this script re-checks/re-deletes the placeholder frames every run too - a
second pass changes nothing (`frames_written` reads 0, `placeholders_deleted` reads 0).

`is_test` turns (console, clone, replay, harness) are never walked - they have no
place in the LIVE episode history this backfill exists to seed.

Usage:
    python scripts/backfill_chatbot_episodes.py [--dry-run]
"""
from __future__ import annotations

import sys

from sqlalchemy import distinct
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.chatbot_turn import ChatbotTurn
from app.models.conversation_frame import ConversationFrame
from app.services.chatbot.turn import memory as memory_mod

#: The old placeholder writer's summary (`engine.py::_write_episode`, retired by this
#: lane) - `f"Closed the {domain} topic."`. Matched with a wildcard for the domain.
_PLACEHOLDER_LIKE = "Closed the %topic."


def _live_contacts(db: Session) -> list[str]:
    rows = (
        db.query(distinct(ChatbotTurn.contact_respond_id))
        .filter(ChatbotTurn.is_test.is_(False))
        .all()
    )
    return [r[0] for r in rows if r[0]]


def _has_topic_reset(turn: ChatbotTurn) -> bool:
    """A reset the live engine would close an episode at: `topic_reset: true`, and not
    while a human has the chat (`engine.py`'s same guard; reviewer pass at d89110c0,
    S16)."""
    envelope = turn.envelope if isinstance(turn.envelope, dict) else {}
    if memory_mod.contact_is_human_intervened(envelope.get("contact")):
        return False
    trace = turn.trace if isinstance(turn.trace, list) else []
    for record in trace:
        if not isinstance(record, dict) or record.get("kind") != "apply":
            continue
        verdict = record.get("verdict")
        if isinstance(verdict, dict) and verdict.get("topic_reset") is True:
            return True
    return False


def _delete_placeholders(db: Session, contact_respond_id: str) -> int:
    """The old writer's `"Closed the {domain} topic."` frames - deleted outright, not
    counted against the newest-20 cap `write_episode_for_reset`'s own trim keeps."""
    return (
        db.query(ConversationFrame)
        .filter(
            ConversationFrame.contact_respond_id == contact_respond_id,
            ConversationFrame.is_test.is_(False),
            ConversationFrame.summary.like(_PLACEHOLDER_LIKE),
        )
        .delete(synchronize_session=False)
    )


def _drop_frames_spanning_a_reset(db: Session, contact_respond_id: str, reset_ids: set[str]) -> int:
    """A frame the live writer closed before this backfill ran can span several
    episodes: the first live reset of a contact with no frames takes its whole history
    as one (reviewer pass at d89110c0, S4). A correct frame starts at a reset and holds
    no other, so a frame with a reset past its first turn is dropped, with every other
    frame of the contact, and the history is rebuilt from the turns. Returns the number
    of frames dropped (0 on a contact already rebuilt, which keeps a re-run a no-op)."""
    frames = (
        db.query(ConversationFrame)
        .filter(
            ConversationFrame.contact_respond_id == contact_respond_id,
            ConversationFrame.is_test.is_(False),
        )
        .all()
    )
    if not any(str(tid) in reset_ids for f in frames for tid in (f.turn_ids or [])[1:]):
        return 0
    for frame in frames:
        db.delete(frame)
    db.flush()
    return len(frames)


def backfill(db: Session) -> dict[str, int]:
    """Run the backfill once. Returns `{contacts, frames_written,
    placeholders_deleted, frames_rebuilt}`. Commits its own work - callers do not
    need to."""
    contacts = _live_contacts(db)
    frames_written = 0
    placeholders_deleted = 0
    frames_rebuilt = 0

    for contact_respond_id in contacts:
        placeholders_deleted += _delete_placeholders(db, contact_respond_id)

        turns = (
            db.query(ChatbotTurn)
            .filter(
                ChatbotTurn.contact_respond_id == contact_respond_id,
                ChatbotTurn.is_test.is_(False),
            )
            .order_by(ChatbotTurn.created_at.asc())
            .all()
        )
        resets = [turn for turn in turns if _has_topic_reset(turn)]
        frames_rebuilt += _drop_frames_spanning_a_reset(
            db, contact_respond_id, {str(turn.id) for turn in resets}
        )
        for turn in resets:
            frame = memory_mod.write_episode_for_reset(
                db,
                contact_respond_id=contact_respond_id,
                is_test=False,
                resetting_turn_id=turn.id,
            )
            if frame is not None:
                frames_written += 1

    db.commit()
    return {
        "contacts": len(contacts),
        "frames_written": frames_written,
        "placeholders_deleted": placeholders_deleted,
        "frames_rebuilt": frames_rebuilt,
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    dry_run = "--dry-run" in argv

    db = SessionLocal()
    try:
        if dry_run:
            contacts = _live_contacts(db)
            print(f"[dry-run] {len(contacts)} contact(s) with live chatbot turns.")
            return 0
        counts = backfill(db)
        print(
            f"contacts={counts['contacts']} "
            f"frames_written={counts['frames_written']} "
            f"placeholders_deleted={counts['placeholders_deleted']} "
            f"frames_rebuilt={counts['frames_rebuilt']}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
