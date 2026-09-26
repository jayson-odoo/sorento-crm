"""S1 episode digest - tester-first RED, from the UAC and the lane A contract (section
5.2 "The written summary").

Covers AC-MEM020, AC-MEM021, AC-MEM022, AC-MEM023, AC-MEM024, AC-MEM027, AC-MEM029.

**No implementation exists at all**: `app/services/chatbot/turn/episode_digest.py` and
`scripts/backfill_chatbot_episodes.py` do not exist. Every test below fails at
`ModuleNotFoundError` / `FileNotFoundError`, never a fixture bug.

**Input shape is this tester's own construction**, since there is no code to read it
off (the captain's brief prescribes the outer shape - `{id, created_at, branch_kind,
status, message, trace}` - and this file fills in the `trace` record shapes it needs,
modelled on the REAL shapes `engine.py`/`trace.py` already write today for `apply`
(`verdict`, `plan.ask`), `memory` (`focus`, `open_question`) and stage records
(`stage`, `facts`). Flagged here rather than silently invented; the coder is free to
read the input differently as long as the OUTPUT contract (this file's assertions,
which trace straight to the UAC and section 5.2) holds.

Outcome derivation (AC-MEM022) is read from two structural signals this file puts on
each turn dict, never from prose: `branch_kind` for escalated/declined/denied/
small_talk, the `apply` record's `plan.ask` for asked_back, and a `looked_up` stage
record's `facts.rows_found` (0 = a miss) for answered/not_found. A `replied` stage's
`facts.text` carries what would be rendered to the dealer, deliberately containing the
word "not found" in one test case that must still resolve as `answered` from the
structural signal - proving text is never read.

Postgres only where a test touches the database (`tests/chatbot/conftest.py::
session_factory`); the `digest()` tests themselves are pure and need no database at
all, which is also what AC-MEM020 tests for directly.
"""
from __future__ import annotations

import importlib.util
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, stub_access, stub_parser  # noqa: F401

BACKEND_ROOT = Path(__file__).resolve().parents[2]
EPISODE_DIGEST_PATH = BACKEND_ROOT / "app" / "services" / "chatbot" / "turn" / "episode_digest.py"
BACKFILL_SCRIPT_PATH = BACKEND_ROOT / "scripts" / "backfill_chatbot_episodes.py"


def _turn(
    turn_id: str,
    created_at: datetime,
    *,
    branch_kind: str = "business_query",
    status: str = "done",
    message: str = "",
    domain: str | None = None,
    intent: str | None = None,
    entities: list[dict[str, Any]] | None = None,
    ask: str | None = None,
    rows_found: int | None = None,
    reply_text: str | None = None,
    tools_used: list[str] | None = None,
    result_refs: list[str] | None = None,
    team: str | None = None,
    offer_answer: str | None = None,
    extra_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One synthetic turn dict, in the shape the captain's brief prescribes. See the
    module docstring for why the `trace` record shapes are this tester's own reading."""
    trace: list[dict[str, Any]] = [
        {
            "kind": "apply",
            "verdict": {
                "domain_hint": domain,
                "intent_hint": intent,
                "message_type": "business_query",
                "entities": entities or [],
            },
            "plan": {"domains": [domain] if domain else [], "ask": ask},
        }
    ]
    if rows_found is not None:
        trace.append({"stage": "looked_up", "status": "done", "facts": {"rows_found": rows_found}})
    if tools_used:
        trace.append({"kind": "tool", "name": tools_used[0], "args": {}})
    if team:
        trace.append({"kind": "offer", "team": team, "answer": offer_answer})
    if reply_text is not None:
        trace.append({"stage": "replied", "status": "done", "facts": {"text": reply_text}})
    trace.append(
        {
            "kind": "memory",
            "focus": {"after": {"domains": [domain] if domain else []}},
            "open_question": {"after": None},
        }
    )
    if extra_trace:
        trace.extend(extra_trace)
    return {
        "id": turn_id,
        "created_at": created_at,
        "branch_kind": branch_kind,
        "status": status,
        "message": message,
        "trace": trace,
        "result_refs": result_refs or [],
    }


def _load_digest():
    from app.services.chatbot.turn.episode_digest import digest

    return digest


# --------------------------------------------------------------------------- #
# AC-MEM020 / AC-MEM027: digest is pure, and the memory write path touches no clock math
# --------------------------------------------------------------------------- #


class TestDigestIsPure:
    def test_episode_digest_module_imports_no_sqlalchemy_or_db_symbol(self) -> None:
        assert EPISODE_DIGEST_PATH.is_file(), f"missing: {EPISODE_DIGEST_PATH}"
        source = EPISODE_DIGEST_PATH.read_text(encoding="utf-8")
        forbidden = ["import sqlalchemy", "from sqlalchemy", "app.database", "Session"]
        offenders = [f for f in forbidden if f in source]
        assert offenders == [], f"episode_digest.py must be pure: found {offenders}"

    def test_digest_returns_the_same_output_for_the_same_input(self) -> None:
        digest = _load_digest()
        base = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
        turns = [
            _turn("t1", base, domain="stock", entities=[{"canonical_code": "SRTWB1455"}], rows_found=3),
        ]
        assert digest(list(turns)) == digest(list(turns))

    def test_no_timedelta_in_memory_or_episode_digest_or_profile_facts_or_context(self) -> None:
        """AC-MEM027: no time-value math anywhere the memory write path reaches. Not
        red against today's code (none of these modules use `timedelta` yet - `turn/
        context.py` and `turn/profile_facts.py` do not exist at all), kept as a
        forward guard against the trigger this AC exists to catch."""
        candidates = [
            BACKEND_ROOT / "app" / "services" / "chatbot" / "turn" / "memory.py",
            EPISODE_DIGEST_PATH,
            BACKEND_ROOT / "app" / "services" / "chatbot" / "turn" / "profile_facts.py",
            BACKEND_ROOT / "app" / "services" / "chatbot" / "turn" / "context.py",
        ]
        offenders = []
        for path in candidates:
            if not path.is_file():
                continue
            if "timedelta" in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(path))
        assert offenders == [], f"timedelta found in: {offenders}"


# --------------------------------------------------------------------------- #
# AC-MEM020: digest output shape
# --------------------------------------------------------------------------- #


class TestDigestOutputShape:
    def test_digest_output_carries_the_documented_keys(self) -> None:
        digest = _load_digest()
        base = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
        turns = [
            _turn("t1", base, domain="stock", entities=[{"canonical_code": "SRTWB1455"}], rows_found=3),
            _turn(
                "t2", base + timedelta(minutes=1), domain="incoming",
                entities=[{"canonical_code": "M486-75-BL"}], rows_found=0,
            ),
        ]
        result = digest(turns)
        assert set(result) >= {
            "domains", "entities", "asks", "offers", "small_talk_turns",
            "turn_count", "first_at", "last_at", "close_reason", "summary",
        }, result
        assert result["turn_count"] == 2
        assert result["domains"] == ["stock", "incoming"]


# --------------------------------------------------------------------------- #
# AC-MEM021: the summary line - <=240 chars, no figures, the worked example
# --------------------------------------------------------------------------- #


class TestSummaryRules:
    def test_worked_example_two_stock_turns_then_an_incoming_miss(self) -> None:
        digest = _load_digest()
        # 25 Sep 2026 is a REAL Friday (`datetime.date(2026, 9, 25).strftime("%A")` -
        # measured, not the plan's own fictional "Thu 25 Sep" worked example, which is
        # narrative text, not tied to the real calendar). The digest must print the
        # weekday of whatever date it is actually given.
        base = datetime(2026, 9, 25, 10, 2, tzinfo=timezone.utc)  # Friday
        turns = [
            _turn(
                "t1", base, domain="stock", entities=[{"canonical_code": "SRTWB1455"}],
                rows_found=137, reply_text="SRTWB1455: 137 units at RM45.90",
            ),
            _turn(
                "t2", base + timedelta(minutes=1), domain="stock",
                entities=[{"canonical_code": "SRTWB1455"}], rows_found=137,
                reply_text="Kuching: 45 units",
            ),
            _turn(
                "t3", base + timedelta(minutes=3), domain="incoming",
                entities=[{"canonical_code": "M486-75-BL"}], rows_found=0,
                reply_text="M486-75-BL not found",
            ),
        ]
        result = digest(turns)
        summary = result["summary"]

        assert len(summary) <= 240, summary
        assert summary.startswith("Fri 25 Sep, 3 turns:"), summary
        assert "SRTWB1455 (answered)" in summary, summary
        assert "M486-75-BL (not found)" in summary, summary
        # Coordinator fix, 26 Sep 2026: a blanket `not re.search(r"\d{2,}", summary)`
        # contradicts the date ("25 Sep") and the product codes ("SRTWB1455",
        # "M486-75-BL") this same test just asserted ARE in the summary - it could
        # never pass. AC-MEM021's real rule is narrower: no ANSWER FIGURE (a
        # quantity or a price from what a turn's tool returned) leaks in, which this
        # asserts by naming the exact figures this test seeded, never a blanket
        # digit-run ban.
        assert "137" not in summary, f"a stock quantity must not leak into the summary: {summary!r}"
        assert "45.90" not in summary, f"a price must not leak into the summary: {summary!r}"

    def test_no_digit_run_from_a_turns_figures_leaks_into_the_summary(self) -> None:
        digest = _load_digest()
        base = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)
        turns = [
            _turn(
                "t1", base, domain="stock", entities=[{"canonical_code": "SRTWC287"}],
                rows_found=9876, reply_text="9876 units at 123.45 each",
            ),
        ]
        summary = digest(turns)["summary"]
        assert "9876" not in summary
        assert "123.45" not in summary
        assert len(summary) <= 240


# --------------------------------------------------------------------------- #
# AC-MEM022: outcome, one case per class, from structural data only
# --------------------------------------------------------------------------- #


class TestOutcomeClassification:
    def _one_ask(self, turns: list[dict[str, Any]]) -> dict[str, Any]:
        digest = _load_digest()
        result = digest(turns)
        asks = result["asks"]
        assert len(asks) == 1, asks
        return asks[0]

    def test_answered(self) -> None:
        t = _turn("t1", datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc), domain="stock", rows_found=3)
        assert self._one_ask([t])["outcome"] == "answered"

    def test_not_found(self) -> None:
        t = _turn("t1", datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc), domain="incoming", rows_found=0)
        assert self._one_ask([t])["outcome"] == "not_found"

    def test_asked_back(self) -> None:
        t = _turn("t1", datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc), domain="stock", ask="product_pick")
        assert self._one_ask([t])["outcome"] == "asked_back"

    def test_escalated(self) -> None:
        t = _turn("t1", datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc), branch_kind="out_of_scope", domain="order")
        assert self._one_ask([t])["outcome"] == "escalated"

    def test_declined(self) -> None:
        t = _turn("t1", datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc), branch_kind="escalation_declined", domain="order")
        assert self._one_ask([t])["outcome"] == "declined"

    def test_denied(self) -> None:
        t = _turn("t1", datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc), branch_kind="access_denied", domain="stock")
        assert self._one_ask([t])["outcome"] == "denied"

    def test_small_talk(self) -> None:
        digest = _load_digest()
        t = _turn("t1", datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc), branch_kind="low_signal", domain=None)
        result = digest([t])
        assert result["small_talk_turns"] == 1, result

    def test_outcome_reads_structured_data_never_reply_text(self) -> None:
        """A reply that SAYS 'not found' but whose structured data says a row was
        found must resolve as `answered` - proving the reader never touches
        `reply_text`."""
        t = _turn(
            "t1", datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc), domain="stock",
            rows_found=1, reply_text="Sorry, that item was not found in our system.",
        )
        assert self._one_ask([t])["outcome"] == "answered"


# --------------------------------------------------------------------------- #
# AC-MEM023: the frame row's digest fields, via the live writer
# --------------------------------------------------------------------------- #


class TestFrameCarriesDigestFields:
    def test_no_placeholder_closed_the_topic_string_anywhere_under_app(self) -> None:
        offenders = []
        pattern = re.compile(r"Closed the .*topic\.")
        for path in (BACKEND_ROOT / "app").rglob("*.py"):
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(str(path))
        assert offenders == [], (
            f"the old placeholder summary must be gone, still found in: {offenders}"
        )

    def test_live_reset_frame_carries_summary_entities_tools_domain_intent_last_message(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        from app.services.chatbot import engine as engine_mod

        cid = str(CONTACT_ID)
        db = session_factory()
        db.execute(
            text(
                "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
                "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
            ),
            {"cid": cid, "phone": f"+6011{uuid.uuid4().hex[:8]}", "sv": json.dumps({"variables": {}})},
        )
        db.commit()

        stub_access()
        stub_parser(verdict(domain_hint="inventory", intent_hint="check_stock", entities=[entity("SRTWB1455")]))
        e1 = _envelope()
        e1.message["message"]["messageId"] = "ZZT-memdig23-1"
        e1.message["message"]["message"]["text"] = "stock SRTWB1455"
        engine_mod.run_turn(e1, session_factory=session_factory)

        stub_access()
        stub_parser(verdict(domain_hint="order", topic_reset=True, entities=[entity("chin chun", hint="customer")]))
        e2 = _envelope()
        e2.message["message"]["messageId"] = "ZZT-memdig23-2"
        engine_mod.run_turn(e2, session_factory=session_factory)

        from app.models.conversation_frame import ConversationFrame

        frame = (
            session_factory()
            .query(ConversationFrame)
            .filter(ConversationFrame.contact_respond_id == cid)
            .order_by(ConversationFrame.last_activity_at.desc())
            .first()
        )
        assert frame is not None, "expected the topic-switch turn to write a frame"
        assert frame.summary and "Closed the" not in frame.summary, frame.summary
        assert frame.entities, frame.entities
        assert isinstance(frame.result_refs, list)
        assert isinstance(frame.tools_used, list)
        assert frame.domain == "inventory"
        assert frame.intent == "check_stock"
        assert frame.last_user_message is not None and len(frame.last_user_message) <= 200


# --------------------------------------------------------------------------- #
# AC-MEM024: backfill script
# --------------------------------------------------------------------------- #


class TestBackfillScript:
    def _load_backfill(self):
        spec = importlib.util.spec_from_file_location("zzt_backfill_chatbot_episodes", BACKFILL_SCRIPT_PATH)
        assert spec is not None and spec.loader is not None, BACKFILL_SCRIPT_PATH
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_script_exists_and_exposes_backfill(self) -> None:
        assert BACKFILL_SCRIPT_PATH.is_file(), f"missing: {BACKFILL_SCRIPT_PATH}"
        module = self._load_backfill()
        assert hasattr(module, "backfill"), "expected scripts/backfill_chatbot_episodes.py::backfill(db) -> dict"

    def test_backfill_cuts_episodes_keeps_newest_20_deletes_placeholders_and_is_idempotent(
        self, session_factory
    ) -> None:
        from app.models.chatbot_turn import ChatbotTurn
        from app.models.conversation_frame import ConversationFrame

        module = self._load_backfill()
        db = session_factory()

        cid = f"ZZT-backfill-{uuid.uuid4().hex[:8]}"
        db.execute(
            text(
                "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
                "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
            ),
            {"cid": cid, "phone": f"+6011{uuid.uuid4().hex[:8]}", "sv": "{}"},
        )
        base = datetime(2026, 8, 1, 8, 0)
        # 25 episodes, one turn each, every turn's `apply` verdict recording
        # topic_reset=True so each turn is its own episode boundary.
        for i in range(25):
            row = ChatbotTurn(
                contact_respond_id=cid,
                message_id=f"ZZT-backfill-{i}",
                ingress="webhook",
                is_test=False,
                status="done",
                created_at=base + timedelta(hours=i),
                # Coordinator fix, 26 Sep 2026: `ChatbotTurn.envelope` is NOT NULL
                # (`app/models/chatbot_turn.py:83`) - a minimal, otherwise-unused stub.
                envelope={},
                trace=[
                    {"kind": "apply", "verdict": {"domain_hint": "stock", "topic_reset": True}, "plan": {"domains": ["stock"], "ask": None}},
                    {"stage": "looked_up", "status": "done", "facts": {"rows_found": 1}},
                ],
            )
            db.add(row)
        # Two placeholder frames the backfill must delete.
        for i in range(2):
            db.add(
                ConversationFrame(
                    contact_id=cid, contact_respond_id=cid, space_id="0", channel="whatsapp",
                    domain="stock", status="closed", close_reason="topic_switch",
                    summary="Closed the stock topic.", turn_ids=[f"placeholder-{i}"],
                    started_at=base, opened_at=base, last_activity_at=base, closed_at=base,
                )
            )
        db.commit()

        counts_1 = module.backfill(db)
        assert isinstance(counts_1, dict)

        frames_after_1 = (
            session_factory().query(ConversationFrame)
            .filter(ConversationFrame.contact_respond_id == cid)
            .all()
        )
        assert len(frames_after_1) == 20, f"expected the newest 20 kept, got {len(frames_after_1)}"
        assert all("Closed the" not in (f.summary or "") for f in frames_after_1), (
            "placeholder frames must be deleted by the backfill"
        )

        ids_after_1 = sorted(f.id for f in frames_after_1)
        counts_2 = module.backfill(session_factory())
        frames_after_2 = (
            session_factory().query(ConversationFrame)
            .filter(ConversationFrame.contact_respond_id == cid)
            .all()
        )
        assert sorted(f.id for f in frames_after_2) == ids_after_1, (
            "a second backfill run must change nothing: same count, same ids"
        )
        assert counts_2 == counts_1 or counts_2.get("frames_written", 0) == 0, counts_2


# --------------------------------------------------------------------------- #
# AC-MEM029: the digest is deterministic between the live writer and the backfill
# --------------------------------------------------------------------------- #


class TestBackfillMatchesLiveWriter:
    def test_same_turns_produce_the_same_summary_entities_and_turn_ids(self) -> None:
        digest = _load_digest()
        base = datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc)
        turns = [
            _turn("t1", base, domain="stock", entities=[{"canonical_code": "SRTWB1455"}], rows_found=2),
            _turn("t2", base + timedelta(minutes=1), domain="stock", entities=[{"canonical_code": "SRTWB1455"}], rows_found=2),
        ]
        # The live writer and the backfill are both expected to call the SAME pure
        # `digest()` over the SAME turn range - proven here by calling it twice, once
        # standing in for each caller, over turns built identically.
        from_live = digest(list(turns))
        from_backfill = digest(list(turns))
        assert from_live["summary"] == from_backfill["summary"]
        assert from_live["entities"] == from_backfill["entities"]
