"""Backfill closed episodes for every contact's LIVE chatbot turns (chatbot memory
lane A, contract section 3 / PLAN-chatbot-memory-26sep.md section 5.3).

For each contact, walks all `is_test = false` turns in order and closes an episode at
every turn that switches topic (`episode_digest.close_trigger`: `topic_reset: true`, or a
planned domain other than the open conversation's newest one, fix lane round 3) - the
SAME rule and the SAME writer the live
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

Fix round 6: every run also rewrites a stored summary still in the pre round 6 tag
shape (`rerender_summaries`), console frames included. Until it runs, every reader
shows such a frame through `episode_digest.readable_summary`, never the tags.
"""
from __future__ import annotations

import sys

from sqlalchemy import String, cast, distinct
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.chatbot_turn import ChatbotTurn
from app.models.conversation_frame import ConversationFrame
from app.services.chatbot.turn import episode_digest
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


def _topic_switches(turns: list[ChatbotTurn]) -> list[ChatbotTurn]:
    """The turns the live engine would close an episode at, oldest first: the same
    `episode_digest.close_trigger` over each turn's `apply` record, with the open
    domain carried the way the engine reads it (the newest planned domain since the
    last switch, the switching turn's own included), and never while a human has the
    chat (`engine.py`'s same guard; reviewer pass at d89110c0, S16)."""
    switches: list[ChatbotTurn] = []
    open_domain: str | None = None
    for turn in turns:
        as_dict = memory_mod._turn_to_digest_dict(turn)
        domain = episode_digest.topic_domain(as_dict)
        envelope = turn.envelope if isinstance(turn.envelope, dict) else {}
        human = memory_mod.contact_is_human_intervened(envelope.get("contact"))
        trigger = episode_digest.close_trigger(episode_digest.turn_verdict(as_dict), domain, open_domain)
        if trigger is not None and not human:
            switches.append(turn)
            open_domain = domain
        elif domain:
            open_domain = domain
    return switches


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


def rerender_summaries(db: Session) -> int:
    """Fix round 6: rewrite every stored summary still in the old tag shape
    (`Tue 8 Sep, 639 turns: (declined); ...`) by running the SAME `digest()` over the
    frame's own turns, live and console frames alike (the owner hand-tests from the
    console). A frame whose turns are gone gets the sentence its own columns and old
    tags give (`episode_digest.readable_summary`, what every reader shows meanwhile).
    Returns the number rewritten; a second run rewrites nothing."""
    rewritten = 0
    for frame in db.query(ConversationFrame).yield_per(200):
        if not episode_digest.is_legacy_summary(frame.summary):
            continue
        rows = (
            db.query(ChatbotTurn)
            .filter(cast(ChatbotTurn.id, String).in_([str(t) for t in frame.turn_ids or []]))
            .order_by(ChatbotTurn.created_at.asc())
            .all()
        )
        if rows:
            summary = episode_digest.digest([memory_mod._turn_to_digest_dict(r) for r in rows])["summary"]
        else:
            summary = episode_digest.readable_summary(frame.summary, frame.domain, frame.entities)
        db.query(ConversationFrame).filter(ConversationFrame.id == frame.id).update(
            {ConversationFrame.summary: summary}, synchronize_session=False
        )
        rewritten += 1
    return rewritten


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
        resets = _topic_switches(turns)
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

    summaries_rewritten = rerender_summaries(db)

    db.commit()
    return {
        "contacts": len(contacts),
        "frames_written": frames_written,
        "placeholders_deleted": placeholders_deleted,
        "frames_rebuilt": frames_rebuilt,
        "summaries_rewritten": summaries_rewritten,
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
            f"frames_rebuilt={counts['frames_rebuilt']} "
            f"summaries_rewritten={counts['summaries_rewritten']}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
