"""S0 episode boundaries - tester-first RED, from the UAC and the lane A contract.

Covers AC-MEM002, AC-MEM003, AC-MEM004, AC-MEM005, AC-MEM006, AC-MEM013, AC-MEM025, and
the "no embedding enqueued" line of contract section 3.

**No implementation exists yet.** `app.services.chatbot.turn.memory` has `write_episode`
(the OLD, single-turn-id writer `engine.py::_write_episode` still calls) but NOT
`write_episode_for_reset`, the new function the contract names
(`memory.write_episode_for_reset(db, *, contact_respond_id, is_test, resetting_turn_id)
-> frame | None`). Tests that call it directly fail at
`AttributeError: module 'app.services.chatbot.turn.memory' has no attribute
'write_episode_for_reset'` - a missing-function red, not a fixture bug. Tests that drive
the full engine (`engine_mod.run_turn`) instead fail on a real assertion: today's
`engine.py::_write_episode` writes `turn_ids=[<the resetting turn's own id>]` and a
placeholder `"Closed the {domain} topic."` summary, never the full closed range, and it
has no `is_test` / human-intervened gate at all.

**Ambiguity flagged to the captain**: AC-MEM005 clause (c) - "a replay step writes
nothing" for a NON-console dry run - is already true of today's code (`engine.py` only
calls the writer `if not dry_run`, with no ingress check at all), so
`TestConsoleException::test_non_console_dry_run_writes_no_frame` passes against the
CURRENT code. It is kept as a non-regression guard (the new console carve-out must not
widen to every dry run) and named as such rather than silently invented as a red test.

Postgres only (`tests/chatbot/conftest.py::session_factory`, a blank scratch schema);
every turn seeded fresh, nothing borrowed.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.models.conversation_frame import ConversationFrame
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.turn import memory as memory_mod
from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import _envelope, stub_access, stub_parser  # noqa: F401

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _cid() -> str:
    return f"ZZT-mem-{uuid.uuid4().hex[:10]}"


def _seed_contact(session_factory, contact_respond_id: str) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {
            "cid": contact_respond_id,
            "phone": f"+6011{uuid.uuid4().hex[:8]}",
            "sv": json.dumps({"variables": {}}),
        },
    )
    db.commit()


def _set_turn_created_at(session_factory, turn_id: str, when: datetime) -> None:
    db = session_factory()
    db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).update({"created_at": when})
    db.commit()


def _turn_row(session_factory, turn_id: str) -> ChatbotTurn:
    return session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()


def _turns(session_factory, contact_respond_id: str, is_test: bool | None = None) -> list[ChatbotTurn]:
    q = (
        session_factory()
        .query(ChatbotTurn)
        .filter(ChatbotTurn.contact_respond_id == contact_respond_id)
    )
    if is_test is not None:
        q = q.filter(ChatbotTurn.is_test.is_(is_test))
    return q.order_by(ChatbotTurn.created_at.asc()).all()


def _frames(session_factory, contact_respond_id: str, is_test: bool | None = None) -> list[ConversationFrame]:
    q = (
        session_factory()
        .query(ConversationFrame)
        .filter(ConversationFrame.contact_respond_id == contact_respond_id)
    )
    if is_test is not None:
        q = q.filter(ConversationFrame.is_test.is_(is_test))
    return q.order_by(ConversationFrame.last_activity_at.asc()).all()


def _run(
    session_factory,
    stub_parser,
    stub_access,
    *,
    v: dict[str, Any],
    message_id: str,
    envelope_overrides: dict[str, Any] | None = None,
):
    stub_access()
    stub_parser(v)
    envelope = _envelope(**(envelope_overrides or {}))
    envelope.message["message"]["messageId"] = message_id
    return engine_mod.run_turn(envelope, session_factory=session_factory)


# --------------------------------------------------------------------------- #
# AC-MEM002: topic switch closes exactly the turns before it
# --------------------------------------------------------------------------- #


class TestTopicSwitchClosesEpisode:
    def test_three_live_turns_close_as_one_frame_on_the_fourth_topic_reset(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        from tests.chatbot.test_engine import CONTACT_ID

        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)
        base = datetime(2026, 9, 24, 10, 2, tzinfo=timezone.utc)

        r1 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]),
                   message_id="ZZT-mem2-t1")
        _set_turn_created_at(session_factory, r1.turn_id, base)

        r2 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]),
                   message_id="ZZT-mem2-t2")
        _set_turn_created_at(session_factory, r2.turn_id, base + timedelta(minutes=1))

        r3 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]),
                   message_id="ZZT-mem2-t3")
        _set_turn_created_at(session_factory, r3.turn_id, base + timedelta(minutes=2))

        r4 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="order", topic_reset=True, entities=[entity("chin chun", hint="customer")]),
                   message_id="ZZT-mem2-t4")
        _set_turn_created_at(session_factory, r4.turn_id, base + timedelta(days=1))

        frames = _frames(session_factory, cid, is_test=False)
        assert len(frames) == 1, f"expected exactly one frame after the reset, got {len(frames)}"
        frame = frames[0]
        assert list(frame.turn_ids) == [r1.turn_id, r2.turn_id, r3.turn_id], (
            "the frame must carry ALL THREE closed turns, oldest first - today's "
            f"engine writes turn_ids=[<the resetting turn>] only; got {list(frame.turn_ids)}"
        )
        assert frame.close_reason == "topic_switch"
        assert frame.last_activity_at == (base + timedelta(minutes=2)).replace(tzinfo=None), (
            "last_activity_at must be T3's created_at (naive UTC), not the frame's write time"
        )
        assert frame.is_test is False

        # T5 (no reset) then T6 (reset) opens the second frame over [T4, T5].
        r5 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="order", entities=[entity("chin chun", hint="customer")]),
                   message_id="ZZT-mem2-t5")
        _set_turn_created_at(session_factory, r5.turn_id, base + timedelta(days=1, minutes=1))

        r6 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="promotion", topic_reset=True),
                   message_id="ZZT-mem2-t6")
        _set_turn_created_at(session_factory, r6.turn_id, base + timedelta(days=2))

        frames2 = _frames(session_factory, cid, is_test=False)
        assert len(frames2) == 2, f"expected a second frame after the second reset, got {len(frames2)}"
        assert list(frames2[1].turn_ids) == [r4.turn_id, r5.turn_id], list(frames2[1].turn_ids)


# --------------------------------------------------------------------------- #
# AC-MEM003 (Q2): time never closes an episode
# --------------------------------------------------------------------------- #


class TestTimeNeverCloses:
    def test_three_day_old_previous_turn_with_no_topic_reset_closes_nothing(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        from tests.chatbot.test_engine import CONTACT_ID

        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)

        r1 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]),
                   message_id="ZZT-mem3-t1")
        old = datetime.now(timezone.utc) - timedelta(days=3)
        _set_turn_created_at(session_factory, r1.turn_id, old)

        r2 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]),
                   message_id="ZZT-mem3-t2")

        assert _frames(session_factory, cid) == [], (
            "a 3-day-old previous turn with no topic_reset must close NOTHING - time is "
            "never a close trigger (owner ruling, Q2)"
        )

    def test_no_idle_close_reason_anywhere_under_chatbot_services(self) -> None:
        """Grep guard: no file under `app/services/chatbot/` treats `idle` as a close
        reason. Matches `close_reason="idle"`, `close_reason='idle'` or a bare `"idle"` /
        `'idle'` string literal used as a close reason value."""
        chatbot_dir = BACKEND_ROOT / "app" / "services" / "chatbot"
        offenders: list[str] = []
        pattern = re.compile(r"close_reason\s*=\s*[\"']idle[\"']")
        for path in chatbot_dir.rglob("*.py"):
            text_content = path.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(text_content):
                offenders.append(str(path))
        assert offenders == [], f"'idle' used as a close_reason in: {offenders}"


# --------------------------------------------------------------------------- #
# AC-MEM004 (Q2): human takeover closes nothing
# --------------------------------------------------------------------------- #


class TestHumanInterventionClosesNothing:
    def test_human_intervened_turn_with_topic_reset_writes_no_frame(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        from tests.chatbot.test_engine import CONTACT_ID

        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)

        r1 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]),
                   message_id="ZZT-mem4-t1")

        stub_access()
        stub_parser(verdict(domain_hint="order", topic_reset=True))
        envelope = _envelope(
            contact={
                "id": CONTACT_ID,
                "firstName": "ZZT",
                "custom_fields": [{"name": "is_human_intervened", "value": "true"}],
            }
        )
        envelope.message["message"]["messageId"] = "ZZT-mem4-t2"
        engine_mod.run_turn(envelope, session_factory=session_factory)

        assert _frames(session_factory, cid) == [], (
            "is_human_intervened=true must close nothing, even with topic_reset=true - "
            "today's engine has no such gate at all"
        )


# --------------------------------------------------------------------------- #
# AC-MEM005: empty range, console exception, cross-world isolation
# --------------------------------------------------------------------------- #


class TestEmptyAndConsoleAndCrossWorld:
    def test_topic_reset_on_the_very_first_turn_writes_nothing(self, session_factory) -> None:
        cid = _cid()
        _seed_contact(session_factory, cid)
        db = session_factory()

        frame = memory_mod.write_episode_for_reset(
            db, contact_respond_id=cid, is_test=False, resetting_turn_id=str(uuid.uuid4())
        )

        assert frame is None
        assert _frames(session_factory, cid) == []

    def test_console_dry_run_topic_reset_writes_one_is_test_frame_and_nothing_else(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        from tests.chatbot.test_engine import CONTACT_ID

        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)

        r1 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]),
                   message_id="ZZT-mem5-console-1",
                   envelope_overrides={"is_test": True, "ingress": "console"})

        before_usage = session_factory().execute(text("SELECT count(*) FROM ai_assistant_usage_logs")).scalar()
        before_session_vars = session_factory().execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": cid}
        ).scalar()

        r2 = _run(session_factory, stub_parser, stub_access,
                   v=verdict(domain_hint="order", topic_reset=True),
                   message_id="ZZT-mem5-console-2",
                   envelope_overrides={"is_test": True, "ingress": "console"})

        frames = _frames(session_factory, cid, is_test=True)
        assert len(frames) == 1, (
            "D14's third named exception (Q15): a CONSOLE dry run may write an "
            f"is_test=true frame - got {len(frames)}"
        )
        assert frames[0].is_test is True

        after_usage = session_factory().execute(text("SELECT count(*) FROM ai_assistant_usage_logs")).scalar()
        after_session_vars = session_factory().execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": cid}
        ).scalar()
        assert after_usage == before_usage, "a console dry run must write nothing outside chatbot.turns"
        assert after_session_vars == before_session_vars

    def test_non_console_dry_run_writes_no_frame(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        """NOT a red test against today's code (see module docstring): kept as a
        non-regression guard that the console carve-out does not widen to every dry
        run (clone/replay/harness)."""
        from tests.chatbot.test_engine import CONTACT_ID

        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)

        _run(session_factory, stub_parser, stub_access,
             v=verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]),
             message_id="ZZT-mem5-clone-1",
             envelope_overrides={"test_run_id": "clone-run-1"})
        _run(session_factory, stub_parser, stub_access,
             v=verdict(domain_hint="order", topic_reset=True),
             message_id="ZZT-mem5-clone-2",
             envelope_overrides={"test_run_id": "clone-run-1"})

        assert _frames(session_factory, cid) == []

    def test_live_range_never_includes_is_test_turns_and_vice_versa(self, session_factory) -> None:
        cid = _cid()
        _seed_contact(session_factory, cid)
        db = session_factory()

        live_ids = []
        test_ids = []
        base = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
        for i in range(3):
            row = ChatbotTurn(
                contact_respond_id=cid,
                message_id=f"ZZT-mem5-live-{i}",
                ingress="webhook",
                envelope={},
                is_test=False,
                status="done",
                created_at=base + timedelta(minutes=i),
            )
            db.add(row)
            db.flush()
            live_ids.append(row.id)
        for i in range(3):
            row = ChatbotTurn(
                contact_respond_id=cid,
                message_id=None,
                ingress="console",
                envelope={},
                is_test=True,
                status="done",
                created_at=base + timedelta(minutes=i),
            )
            db.add(row)
            db.flush()
            test_ids.append(row.id)
        db.commit()

        live_frame = memory_mod.write_episode_for_reset(
            db, contact_respond_id=cid, is_test=False, resetting_turn_id=live_ids[2]
        )
        assert live_frame is not None
        assert set(live_frame.turn_ids) == {live_ids[0], live_ids[1]}, (
            "the LIVE range must never pick up an is_test turn"
        )

        test_frame = memory_mod.write_episode_for_reset(
            db, contact_respond_id=cid, is_test=True, resetting_turn_id=test_ids[2]
        )
        assert test_frame is not None
        assert set(test_frame.turn_ids) == {test_ids[0], test_ids[1]}, (
            "the IS_TEST range must never pick up a live turn"
        )


# --------------------------------------------------------------------------- #
# AC-MEM006: idempotent close under the unique key
# --------------------------------------------------------------------------- #


class TestIdempotentClose:
    def test_two_calls_over_the_same_range_produce_one_frame(self, session_factory) -> None:
        """A genuinely concurrent two-connection race is impractical on the shared
        blank scratch schema (one connection, savepoints - see conftest.py), so this
        calls the writer twice SEQUENTIALLY over the identical range and relies on
        `ON CONFLICT DO NOTHING` against the unique key
        `(contact_respond_id, is_test, turn_ids[1])` to make the second call a no-op.
        The DDL-level guarantee is asserted separately below via `pg_indexes`.
        """
        cid = _cid()
        _seed_contact(session_factory, cid)
        db = session_factory()
        base = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)
        turn_ids = []
        for i in range(2):
            row = ChatbotTurn(
                contact_respond_id=cid, message_id=f"ZZT-mem6-{i}", ingress="webhook",
                envelope={}, is_test=False, status="done", created_at=base + timedelta(minutes=i),
            )
            db.add(row)
            db.flush()
            turn_ids.append(row.id)
        resetting_id = str(uuid.uuid4())
        db.commit()

        f1 = memory_mod.write_episode_for_reset(
            db, contact_respond_id=cid, is_test=False, resetting_turn_id=resetting_id
        )
        f2 = memory_mod.write_episode_for_reset(
            db, contact_respond_id=cid, is_test=False, resetting_turn_id=resetting_id
        )
        assert f1 is not None
        # ON CONFLICT DO NOTHING: the second call over the SAME first-turn-id must not
        # insert a second row.
        frames = _frames(session_factory, cid)
        assert len(frames) == 1, f"two calls over the same range must yield one frame, got {len(frames)}"

    def test_unique_index_exists_on_contact_is_test_first_turn(self, session_factory) -> None:
        row = session_factory().execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :n"),
            {"n": "uq_conversation_frames_contact_test_first_turn"},
        ).first()
        assert row is not None, (
            "expected a unique index named uq_conversation_frames_contact_test_first_turn "
            "on conversation_frames(contact_respond_id, is_test, (turn_ids[1]))"
        )


# --------------------------------------------------------------------------- #
# AC-MEM025 (Q7): retention by count, trimmed on write
# --------------------------------------------------------------------------- #


class TestRetentionTrim:
    def _seed_closed_frame(self, db, *, contact_respond_id, is_test, last_activity_at, turn_id) -> str:
        frame = ConversationFrame(
            contact_id=contact_respond_id,
            contact_respond_id=contact_respond_id,
            space_id="0",
            channel="whatsapp",
            domain="inventory",
            status="closed",
            close_reason="topic_switch",
            turn_ids=[turn_id],
            started_at=last_activity_at,
            opened_at=last_activity_at,
            last_activity_at=last_activity_at,
            closed_at=last_activity_at,
            is_test=is_test,
        )
        db.add(frame)
        db.flush()
        return frame.id

    def test_21st_live_frame_trims_the_oldest_and_leaves_other_sides_alone(self, session_factory) -> None:
        cid_a = _cid()
        cid_b = _cid()
        _seed_contact(session_factory, cid_a)
        _seed_contact(session_factory, cid_b)
        db = session_factory()

        now = datetime(2026, 9, 25, 0, 0)
        # A-live: 20 frames, newest last. Index 0 is 500 days old (the TRUE oldest,
        # the one the 21st write must trim); index 5 is 400 days old (the SECOND
        # oldest - old, but not the oldest, so it must survive the trim). Every other
        # index is recent (at most 18 days), so neither special age is accidentally
        # beaten by an ordinary one. Coordinator fix, 26 Sep 2026: the prior version
        # put the 400-day frame at index 5 while leaving every OTHER index at
        # `19 - i` (<=19 days), which made the 400-day frame the chronological
        # oldest of the 20 by nearly 400 days - the test then asserted the SAME id
        # was both "trimmed" (`oldest_a_live_id`) and "must survive" (`the_400_day_id`),
        # a self-contradiction that could never pass.
        a_live_ids = []
        for i in range(20):
            if i == 0:
                when = now - timedelta(days=500)
            elif i == 5:
                when = now - timedelta(days=400)
            else:
                when = now - timedelta(days=(19 - i))
            fid = self._seed_closed_frame(
                db, contact_respond_id=cid_a, is_test=False,
                last_activity_at=when, turn_id=f"ZZT-mem25-a-live-{i}",
            )
            a_live_ids.append((fid, when))
        # A-test: 20 frames (must stay untouched by an A-live write).
        for i in range(20):
            self._seed_closed_frame(
                db, contact_respond_id=cid_a, is_test=True,
                last_activity_at=now - timedelta(days=(19 - i)), turn_id=f"ZZT-mem25-a-test-{i}",
            )
        # B: 5 frames (must stay untouched by an A write).
        for i in range(5):
            self._seed_closed_frame(
                db, contact_respond_id=cid_b, is_test=False,
                last_activity_at=now - timedelta(days=(4 - i)), turn_id=f"ZZT-mem25-b-{i}",
            )
        db.commit()

        oldest_a_live_id, oldest_a_live_when = min(a_live_ids, key=lambda pair: pair[1])
        the_400_day_id = next(fid for fid, when in a_live_ids if when == now - timedelta(days=400))

        new_turn = ChatbotTurn(
            contact_respond_id=cid_a, message_id="ZZT-mem25-a-live-new", ingress="webhook",
            envelope={}, is_test=False, status="done", created_at=now - timedelta(minutes=1),
        )
        db.add(new_turn)
        db.flush()
        resetting = ChatbotTurn(
            contact_respond_id=cid_a, message_id="ZZT-mem25-a-live-reset", ingress="webhook",
            envelope={}, is_test=False, status="done", created_at=now,
        )
        db.add(resetting)
        db.commit()

        frame = memory_mod.write_episode_for_reset(
            db, contact_respond_id=cid_a, is_test=False, resetting_turn_id=resetting.id
        )
        assert frame is not None

        a_live_after = _frames(session_factory, cid_a, is_test=False)
        assert len(a_live_after) == 20, f"A-live must stay at 20 after the 21st write, got {len(a_live_after)}"
        a_live_ids_after = {f.id for f in a_live_after}
        assert oldest_a_live_id not in a_live_ids_after, "the oldest A-live frame must be trimmed"
        assert the_400_day_id in a_live_ids_after, "a 400-day-old frame that is NOT the oldest must survive"

        a_test_after = _frames(session_factory, cid_a, is_test=True)
        assert len(a_test_after) == 20, "A-test side must be untouched by an A-live write"

        b_after = _frames(session_factory, cid_b)
        assert len(b_after) == 5, "contact B's frames must be untouched by A's write"

    def test_no_scheduler_job_touches_conversation_frames(self) -> None:
        candidates = list((BACKEND_ROOT / "app" / "services").glob("scheduler*.py")) + list(
            (BACKEND_ROOT / "app" / "tasks").glob("*.py") if (BACKEND_ROOT / "app" / "tasks").is_dir() else []
        )
        offenders = [str(p) for p in candidates if "conversation_frames" in p.read_text(encoding="utf-8", errors="ignore")]
        assert offenders == [], f"retention must be trimmed on write, never by a scheduled sweep: {offenders}"


# --------------------------------------------------------------------------- #
# AC-MEM013: contact delete removes its frames
# --------------------------------------------------------------------------- #


class TestContactDeleteRemovesFrames:
    def test_deleting_a_contact_deletes_its_frames_and_leaves_others(self, session_factory) -> None:
        from app.services.contact_service import ContactService

        cid_a = _cid()
        cid_b = _cid()
        db = session_factory()
        db.execute(
            text(
                "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
                "VALUES (:pk, :cid, :phone, CAST(:sv AS jsonb))"
            ),
            {"pk": str(uuid.uuid4()), "cid": cid_a, "phone": f"+6011{uuid.uuid4().hex[:8]}", "sv": "{}"},
        )
        internal_id = db.execute(
            text("SELECT id FROM respond_contacts WHERE respond_io_id = :cid"), {"cid": cid_a}
        ).scalar()
        now = datetime(2026, 9, 25, 0, 0)
        self_seed = TestRetentionTrim()
        self_seed._seed_closed_frame(
            db, contact_respond_id=cid_a, is_test=False, last_activity_at=now, turn_id="ZZT-mem13-a-1"
        )
        self_seed._seed_closed_frame(
            db, contact_respond_id=cid_b, is_test=False, last_activity_at=now, turn_id="ZZT-mem13-b-1"
        )
        db.commit()

        ContactService(db).delete_contact(internal_id)

        assert _frames(session_factory, cid_a) == [], "the deleted contact's frames must be gone"
        assert len(_frames(session_factory, cid_b)) == 1, "another contact's frames must survive"


# --------------------------------------------------------------------------- #
# Never enqueues an embedding (contract section 3)
# --------------------------------------------------------------------------- #


class TestNoEmbeddingEnqueued:
    def test_write_episode_for_reset_never_enqueues_an_embedding(self, session_factory, monkeypatch) -> None:
        from app.services import embedding_service as embedding_service_mod

        cid = _cid()
        _seed_contact(session_factory, cid)
        db = session_factory()
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            embedding_service_mod.EmbeddingEventService,
            "queue_event",
            lambda self, **kwargs: calls.append(kwargs),
        )

        row = ChatbotTurn(
            contact_respond_id=cid, message_id="ZZT-mem-noembed-1", ingress="webhook",
            envelope={}, is_test=False, status="done", created_at=datetime(2026, 9, 20, 8, 0),
        )
        db.add(row)
        db.commit()

        memory_mod.write_episode_for_reset(
            db, contact_respond_id=cid, is_test=False, resetting_turn_id=str(uuid.uuid4())
        )

        frame_calls = [c for c in calls if c.get("source_type") == "conversation_frame"]
        assert frame_calls == [], f"the S0 writer must not enqueue an embedding, got {frame_calls}"
