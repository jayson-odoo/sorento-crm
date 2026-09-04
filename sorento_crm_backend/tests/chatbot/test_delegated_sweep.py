"""AC-260: a turn an n8n lane never finished is failed by the sweep, not left as a ghost.

Blank Postgres schema (`tests/chatbot/conftest.py`), because these tests count rows and
compare statuses on a table the shared prod-copy database also holds.

The behaviour under test is the SETTLING RULE, not the scheduler: `start_scheduler`
registering the tick is one `add_job` line covered by reading it, while "which rows flip"
is the part that can silently be wrong.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot_turn_sweep import sweep_stalled_delegated_turns

NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
TTL = 10


@pytest.fixture()
def db(session_factory):
    return session_factory()


def _turn(
    db,
    *,
    status: str,
    age_minutes: int,
    is_test: bool = False,
    trace: list | None = None,
) -> ChatbotTurn:
    started = NOW - timedelta(minutes=age_minutes)
    row = ChatbotTurn(
        contact_respond_id=f"ZZT-contact-{uuid.uuid4().hex[:8]}",
        message_id=f"ZZT-wamid-{uuid.uuid4().hex[:8]}",
        ingress="webhook",
        envelope={"message": {}, "contact": {"id": "ZZT"}},
        is_test=is_test,
        status=status,
        stage="routed",
        branch_kind="business_query",
        attempt=1,
        trace=trace if trace is not None else [],
        started_at=started,
        created_at=started,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_a_delegated_turn_past_the_ttl_becomes_failed(db):
    row = _turn(db, status="delegated", age_minutes=TTL + 5)

    assert sweep_stalled_delegated_turns(db, now=NOW, ttl_minutes=TTL) == 1

    db.refresh(row)
    assert row.status == "failed"
    assert row.stage == "delegated"
    assert row.error == "n8n lane did not complete within 10 minutes"
    assert row.finished_at is not None
    # Retry (R4: failed turns only) can now reach it, which is the point of the sweep.
    assert row.status == "failed"


def test_the_failure_is_explained_on_the_trace_as_a_note(db):
    """A stage row would claim a ninth stage ran. The screen renders notes as footer
    lines, so the operator is told what happened without the timeline growing a step."""
    row = _turn(
        db,
        status="delegated",
        age_minutes=TTL + 1,
        trace=[{"stage": "routed", "status": "ok", "started_at": NOW.isoformat(), "ms": 5,
                "summary": "Routed.", "why": "because", "facts": {}, "error": None, "raw": None}],
    )

    sweep_stalled_delegated_turns(db, now=NOW, ttl_minutes=TTL)

    db.refresh(row)
    assert len(row.trace) == 2
    note = row.trace[-1]
    assert note["kind"] == "note"
    assert note["stage"] == "delegated"
    assert note["status"] == "failed"
    assert "did not complete within 10 minutes" in note["error"]
    assert note["facts"]["ttl_minutes"] == TTL


def test_a_fresh_delegated_turn_is_left_alone(db):
    """The lane is still within its window. Failing it here would answer the customer
    twice: the lane finishes, calls `/complete`, and a retry has already gone out."""
    row = _turn(db, status="delegated", age_minutes=TTL - 1)

    assert sweep_stalled_delegated_turns(db, now=NOW, ttl_minutes=TTL) == 0

    db.refresh(row)
    assert row.status == "delegated"
    assert row.trace == []


def test_done_and_failed_turns_are_untouched(db):
    done = _turn(db, status="done", age_minutes=TTL * 10)
    failed = _turn(db, status="failed", age_minutes=TTL * 10)

    assert sweep_stalled_delegated_turns(db, now=NOW, ttl_minutes=TTL) == 0

    db.refresh(done)
    db.refresh(failed)
    assert done.status == "done"
    assert failed.status == "failed"


def test_a_test_turn_is_swept_too(db):
    """D14 is about what a test turn WRITES elsewhere. A clone turn hanging in
    `delegated` is exactly as misleading on the trace screen as a live one."""
    row = _turn(db, status="delegated", age_minutes=TTL + 30, is_test=True)

    assert sweep_stalled_delegated_turns(db, now=NOW, ttl_minutes=TTL) == 1

    db.refresh(row)
    assert row.status == "failed"


def test_a_second_sweep_changes_nothing(db):
    """Idempotent: the tick runs every minute, and a row it already settled is no longer
    `delegated`, so it is not read again and the note is not appended twice."""
    row = _turn(db, status="delegated", age_minutes=TTL + 5)

    assert sweep_stalled_delegated_turns(db, now=NOW, ttl_minutes=TTL) == 1
    first_trace = list(row.trace or [])
    assert sweep_stalled_delegated_turns(db, now=NOW, ttl_minutes=TTL) == 0

    db.refresh(row)
    assert row.trace == first_trace
    assert len(row.trace) == 1


def test_the_ttl_comes_from_settings_when_not_given(db, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "chatbot_delegated_ttl_minutes", 1, raising=False)
    row = _turn(db, status="delegated", age_minutes=2)

    assert sweep_stalled_delegated_turns(db, now=NOW) == 1

    db.refresh(row)
    assert row.error == "n8n lane did not complete within 1 minutes"
