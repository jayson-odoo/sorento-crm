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


def backfill(db: Session) -> dict[str, int]:
    """Run the backfill once. Returns `{contacts, frames_written,
    placeholders_deleted}`. Commits its own work - callers do not need to."""
    contacts = _live_contacts(db)
    frames_written = 0
    placeholders_deleted = 0

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
        for turn in turns:
            if not _has_topic_reset(turn):
                continue
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
            f"placeholders_deleted={counts['placeholders_deleted']}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
