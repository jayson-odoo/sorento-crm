"""Episode writer and digest findings of the reviewer pass on PR #1304 at d89110c0:
S4, S5, S14, S16, S21.

* S5: outcome and offers come from signals the engine really writes. The golden here
  is a trace the engine itself produced in pytest, not a hand-made shape.
* S14: days and times are on the dealers' clock (Asia/Kuala_Lumpur).
* S16: the backfill does not cut at a reset a human had the chat for.
* S4: a frame the live writer closed before the backfill ran is rebuilt.
* S21: a second run over trimmed history digests nothing; a racing insert that hits
  the unique index returns None and leaves the session usable.

Postgres only (`tests/chatbot/conftest.py::session_factory`).
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.models.conversation_frame import ConversationFrame
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.turn import memory as memory_mod
from app.services.chatbot.turn.episode_digest import digest
from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access, stub_parser  # noqa: F401

BACKFILL_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "backfill_chatbot_episodes.py"


def _backfill_module():
    spec = importlib.util.spec_from_file_location("zzt_backfill_round2", BACKFILL_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frames(session_factory, cid: str) -> list[ConversationFrame]:
    return (
        session_factory()
        .query(ConversationFrame)
        .filter(ConversationFrame.contact_respond_id == cid)
        .order_by(ConversationFrame.started_at.asc())
        .all()
    )


class TestS5GoldenFromAnEngineTrace:
    def test_a_lookup_that_found_nothing_reads_not_found_and_the_offer_is_named(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        cid = str(CONTACT_ID)
        stub_access()
        stub_parser(verdict(domain_hint="inventory", entities=[entity("SRTWB1455")]))
        first = _envelope()
        first.message["message"]["messageId"] = "ZZT-r2-s5-1"
        engine_mod.run_turn(first, session_factory=session_factory)

        stub_parser(verdict(domain_hint="order", topic_reset=True, entities=[entity("chin chun", hint="customer")]))
        second = _envelope()
        second.message["message"]["messageId"] = "ZZT-r2-s5-2"
        engine_mod.run_turn(second, session_factory=session_factory)

        (frame,) = _frames(session_factory, cid)
        assert "inventory SRTWB1455 (not found)" in frame.summary, frame.summary
        assert "offered warehouse team, no answer" in frame.summary, frame.summary

    def test_a_denied_plan_reads_denied(self) -> None:
        turn = {
            "id": "t1",
            "created_at": datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc),
            "branch_kind": "business_query",
            "status": "done",
            "message": "sales report",
            "trace": [
                {
                    "kind": "apply",
                    "verdict": {"domain_hint": "sales_report", "entities": []},
                    "plan": {"ask": None, "fetch": [], "denied": ["sales_report"], "domains": ["sales_report"]},
                },
            ],
            "result_refs": [],
        }
        assert "(denied)" in digest([turn])["summary"]


class TestS14DealersClock:
    def test_the_summary_day_is_the_kuala_lumpur_day(self) -> None:
        turn = {
            "id": "t1",
            # Thu 23:10 UTC is Fri 07:10 in Kuala Lumpur.
            "created_at": datetime(2026, 9, 24, 23, 10, tzinfo=timezone.utc),
            "branch_kind": "low_signal",
            "status": "done",
            "message": "hi",
            "trace": [],
            "result_refs": [],
        }
        assert digest([turn])["summary"].startswith("Fri 25 Sep"), digest([turn])["summary"]

    def test_a_naive_utc_time_reads_the_same(self) -> None:
        assert engine_mod._short_day_time(datetime(2026, 9, 24, 23, 10)) == "Fri 07:10"


def _seed_turn(db, cid: str, when: datetime, *, reset: bool, human: bool = False) -> str:
    turn_id = str(uuid.uuid4())
    db.add(
        ChatbotTurn(
            id=turn_id,
            contact_respond_id=cid,
            message_id=f"ZZT-r2-bf-{uuid.uuid4().hex[:8]}",
            ingress="webhook",
            is_test=False,
            status="done",
            branch_kind="business_query",
            created_at=when,
            envelope={
                "contact": {
                    "id": cid,
                    "custom_fields": [{"name": "is_human_intervened", "value": "true" if human else "false"}],
                }
            },
            trace=[{"kind": "apply", "verdict": {"domain_hint": "stock", "topic_reset": reset}, "plan": {"domains": ["stock"]}}],
        )
    )
    return turn_id


def _seed_contact(db) -> str:
    cid = f"ZZT-r2-bf-{uuid.uuid4().hex[:8]}"
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST('{}' AS jsonb))"
        ),
        {"cid": cid, "phone": f"+6011{uuid.uuid4().hex[:8]}"},
    )
    return cid


class TestS16BackfillSkipsAHumanReset:
    def test_a_reset_while_a_human_had_the_chat_is_not_a_cut(self, session_factory) -> None:
        db = session_factory()
        cid = _seed_contact(db)
        base = datetime(2026, 9, 1, 1, 0)
        t0 = _seed_turn(db, cid, base, reset=False)
        t1 = _seed_turn(db, cid, base + timedelta(hours=1), reset=True, human=True)
        t2 = _seed_turn(db, cid, base + timedelta(hours=2), reset=True)
        db.commit()

        _backfill_module().backfill(db)

        (frame,) = _frames(session_factory, cid)
        assert [str(t) for t in frame.turn_ids] == [t0, t1], frame.turn_ids
        assert t2 not in [str(t) for t in frame.turn_ids]


class TestS4BackfillRebuildsALiveFrameThatPredatesIt:
    def test_a_frame_spanning_an_earlier_reset_is_rebuilt(self, session_factory) -> None:
        db = session_factory()
        cid = _seed_contact(db)
        base = datetime(2026, 9, 1, 1, 0)
        t0 = _seed_turn(db, cid, base, reset=False)
        t1 = _seed_turn(db, cid, base + timedelta(hours=1), reset=True)
        t2 = _seed_turn(db, cid, base + timedelta(hours=2), reset=True)
        db.commit()
        # Deployed before the backfill: the first live reset (t2) of a contact with no
        # frames took the whole history as one episode.
        live = memory_mod.write_episode_for_reset(db, contact_respond_id=cid, is_test=False, resetting_turn_id=t2)
        assert [str(t) for t in live.turn_ids] == [t0, t1]

        module = _backfill_module()
        module.backfill(db)

        frames = _frames(session_factory, cid)
        assert [[str(t) for t in f.turn_ids] for f in frames] == [[t0], [t1]], [f.turn_ids for f in frames]
        again = module.backfill(session_factory())
        assert again["frames_written"] == 0 and again["frames_rebuilt"] == 0, again


class TestS21:
    def test_a_second_run_over_trimmed_history_digests_nothing(self, session_factory, monkeypatch) -> None:
        db = session_factory()
        cid = _seed_contact(db)
        base = datetime(2026, 8, 1, 8, 0)
        for i in range(25):
            _seed_turn(db, cid, base + timedelta(hours=i), reset=True)
        db.commit()
        module = _backfill_module()
        module.backfill(db)
        assert len(_frames(session_factory, cid)) == memory_mod.KEEP_EPISODES

        digested: list[int] = []
        real_digest = memory_mod.digest
        monkeypatch.setattr(memory_mod, "digest", lambda turns: digested.append(len(turns)) or real_digest(turns))
        counts = module.backfill(session_factory())
        assert counts["frames_written"] == 0, counts
        assert digested == [], f"trimmed turns were re-derived into frames: {digested}"

    def test_a_racing_insert_on_the_same_first_turn_returns_none(self, session_factory, monkeypatch) -> None:
        db = session_factory()
        cid = _seed_contact(db)
        base = datetime(2026, 9, 1, 1, 0)
        t0 = _seed_turn(db, cid, base, reset=False)
        t1 = _seed_turn(db, cid, base + timedelta(hours=1), reset=True)
        db.commit()

        real_digest = memory_mod.digest

        def digest_while_another_writer_wins(turns):
            # The other writer commits the same range between this writer's read and
            # its insert.
            db.execute(
                text(
                    "INSERT INTO conversation_frames (id, contact_id, contact_respond_id, space_id, channel, "
                    "status, turn_ids, is_test) "
                    "VALUES (gen_random_uuid(), :c, :c, '0', 'whatsapp', 'closed', ARRAY[:t], false)"
                ),
                {"c": cid, "t": t0},
            )
            return real_digest(turns)

        monkeypatch.setattr(memory_mod, "digest", digest_while_another_writer_wins)
        frame = memory_mod.write_episode_for_reset(db, contact_respond_id=cid, is_test=False, resetting_turn_id=t1)
        assert frame is None
        # The session is still usable for the turn's later writes.
        assert db.execute(text("SELECT 1")).scalar() == 1
