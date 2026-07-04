"""Service-level tests for the M2 AI-assistant trace feature (PLAN §9 UAC T1).

Covers ``app/services/ai_trace.py``:
- ``_truncate_payload`` byte-cap behaviour,
- ``TurnTrace.flush`` persisting a trace + span tree in one shot,
- flush being best-effort (never raising on a broken session),
- ``sweep_expired_traces`` retention buckets (ok vs error/flagged TTLs).

Everything runs against in-memory SQLite. Postgres-only column types are
mapped to sqlite equivalents via ``@compiles`` hooks (CLAUDE.md sqlite
gotchas: JSONB -> TEXT, ARRAY -> TEXT; pg ``UUID(as_uuid=False)`` works as-is).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.ai_assistant import (
    AIAssistantConversation,
    AIAssistantMessage,
    AIAssistantSpan,
    AIAssistantTrace,
)
from app.models.audit import AuditLog
from app.models.lookup import LookupBinding
from app.models.user import SystemSetting, User
from app.services.ai_trace import (
    KIND_AGENT,
    KIND_RETRIEVER,
    TurnTrace,
    _truncate_payload,
    sweep_expired_traces,
)


# --- sqlite type mapping ---------------------------------------------------- #


@compiles(JSONB, "sqlite")  # type: ignore[misc]
def _jsonb_sqlite(_type_, _compiler, **_kw):  # noqa: D401, ANN001
    return "TEXT"


@compiles(ARRAY, "sqlite")  # type: ignore[misc]
def _array_sqlite(_type_, _compiler, **_kw):  # noqa: D401, ANN001
    return "TEXT"


_TABLES = [
    User.__table__,
    SystemSetting.__table__,
    AIAssistantConversation.__table__,
    AIAssistantMessage.__table__,
    AIAssistantTrace.__table__,
    AIAssistantSpan.__table__,
    # Globally-registered listeners from other test modules fire on our inserts
    # when the full suite runs (CLAUDE.md gotcha) — create their tables
    # defensively so insert order across modules is robust.
    LookupBinding.__table__,
    AuditLog.__table__,
]


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=_TABLES)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# UUID-typed columns (conversation/message/trace/span ids) reject non-UUID
# strings on read-back — use valid UUIDs. User.id is a String PK, so a plain
# slug is fine there.
# Must contain hex letters — SQLite's NUMERIC affinity coerces all-digit
# hyphenated strings to floats on read-back.
_CONV_ID = "0a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d"
_MSG_ID = "1b2c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e"


@pytest.fixture
def message(db: Session) -> AIAssistantMessage:
    """A committed assistant message the trace can FK onto."""
    user = User(id="u-trace", email="trace@test.com", name="Trace User", status="ACTIVE")
    conv = AIAssistantConversation(id=_CONV_ID, user_id="u-trace", title="T")
    db.add_all([user, conv])
    db.flush()
    msg = AIAssistantMessage(
        id=_MSG_ID, conversation_id=_CONV_ID, role="assistant", content="answer"
    )
    db.add(msg)
    db.commit()
    return msg


# --- fakes ------------------------------------------------------------------ #


@dataclass
class _FakeChatResult:
    content: str = "the model reply"
    prompt_tokens: int = 10
    completion_tokens: int = 5
    tool_calls: list = field(default_factory=list)
    raw: object | None = None


# --------------------------------------------------------------------------- #
# _truncate_payload                                                           #
# --------------------------------------------------------------------------- #


def test_truncate_payload_under_cap_passthrough():
    value = {"a": 1, "b": ["x", "y"]}
    out = _truncate_payload(value, 16384)
    assert out is value  # identical object, not a copy


def test_truncate_payload_none_returns_none():
    assert _truncate_payload(None, 16384) is None


def test_truncate_payload_over_cap_preserves_structure():
    # A dict with a huge string leaf stays a dict; the string is capped in place
    # with an inline marker so the UI can pretty-print valid nested JSON.
    cap = 2000
    value = {"messages": [{"role": "system", "content": "x" * 20000}]}
    out = _truncate_payload(value, cap)
    assert isinstance(out, dict)
    assert "truncated" not in out  # NOT the flat envelope
    content = out["messages"][0]["content"]
    assert content.startswith("x")
    assert "chars truncated]" in content
    # fits the cap now.
    import json as _json

    assert len(_json.dumps(out).encode("utf-8")) <= cap


def test_truncate_payload_over_cap_caps_long_list():
    cap = 4000
    value = {"items": [{"i": i, "pad": "y" * 50} for i in range(500)]}
    out = _truncate_payload(value, cap)
    assert isinstance(out, dict)
    assert "truncated" not in out
    items = out["items"]
    # capped to 50 elements + 1 marker string.
    assert len(items) == 51
    assert isinstance(items[-1], str) and "items truncated]" in items[-1]


def test_truncate_payload_non_serializable_falls_back_to_envelope():
    class _Weird:
        def __repr__(self) -> str:
            return "W" * 5000

    out = _truncate_payload(_Weird(), 100)
    # A bare object can't be structure-preserved (not str/dict/list) → last-resort
    # flat envelope.
    assert isinstance(out, dict) and out["truncated"] is True


# --------------------------------------------------------------------------- #
# TurnTrace.flush                                                             #
# --------------------------------------------------------------------------- #


def _build_trace() -> TurnTrace:
    tt = TurnTrace(user_id="u-trace", conversation_id=_CONV_ID, session_id="s-1", env="test")
    tt.add_llm_span(
        name="chat gpt-4o",
        model="gpt-4o",
        messages_in=[{"role": "user", "content": "hi"}],
        result=_FakeChatResult(),
        started_perf=time.perf_counter(),
        prompt_name="agent_system",
        prompt_version=1,
    )
    tt.add_tool_span(
        tool_name="crm_inventory_stock_balance_list",
        tool_call_id="call-1",
        args={"product": "widget"},
        result_text='{"rows": 3}',
        started_perf=time.perf_counter(),
        ok=True,
    )
    tt.add_span(
        kind=KIND_RETRIEVER,
        name="rag select",
        query="stock of widget",
        documents=[{"id": "d1", "content": "doc", "score": 0.9}],
        top_k=5,
    )
    return tt


def test_flush_persists_trace_and_spans(db: Session, message: AIAssistantMessage):
    tt = _build_trace()
    trace_id = tt.flush(db, message_id=message.id, status="ok")

    assert trace_id == tt.trace_id
    traces = db.query(AIAssistantTrace).all()
    assert len(traces) == 1
    trace = traces[0]
    assert trace.message_id == message.id
    assert trace.conversation_id == _CONV_ID

    spans = db.query(AIAssistantSpan).filter_by(trace_id=trace_id).all()
    # root AGENT + LLM + TOOL + RETRIEVER
    assert len(spans) == 4
    assert trace.span_count == 4

    # Root AGENT span present and parentless.
    roots = [s for s in spans if s.span_kind == KIND_AGENT]
    assert len(roots) == 1
    assert roots[0].parent_id is None

    # Every non-root span parents onto the root.
    non_root = [s for s in spans if s.span_kind != KIND_AGENT]
    assert all(s.parent_id == roots[0].id for s in non_root)


def test_flush_totals_sum_span_tokens(db: Session, message: AIAssistantMessage):
    tt = _build_trace()
    tt.flush(db, message_id=message.id)
    trace = db.query(AIAssistantTrace).one()
    # Only the LLM span carries tokens (10 in / 5 out).
    assert trace.total_tokens_in == 10
    assert trace.total_tokens_out == 5


def test_flush_dotted_order_sorts_in_emit_order(db: Session, message: AIAssistantMessage):
    tt = _build_trace()
    tt.flush(db, message_id=message.id)
    ordered = (
        db.query(AIAssistantSpan)
        .filter_by(trace_id=tt.trace_id)
        .order_by(AIAssistantSpan.dotted_order.asc())
        .all()
    )
    kinds = [s.span_kind for s in ordered]
    assert kinds[0] == KIND_AGENT  # root emitted first
    assert kinds == ["AGENT", "LLM", "TOOL", "RETRIEVER"]
    # dotted_order strings are strictly increasing.
    dorders = [s.dotted_order for s in ordered]
    assert dorders == sorted(dorders)
    assert len(set(dorders)) == 4


def test_flush_status_error_recorded(db: Session, message: AIAssistantMessage):
    tt = _build_trace()
    tt.flush(db, message_id=message.id, status="error")
    trace = db.query(AIAssistantTrace).one()
    assert trace.status == "error"


def test_flush_is_best_effort_on_broken_session(db: Session, message: AIAssistantMessage, monkeypatch):
    tt = _build_trace()

    def _boom(*_a, **_k):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(db, "add", _boom)
    # Must swallow and return None, never raise.
    result = tt.flush(db, message_id=message.id)
    assert result is None
    # Nothing persisted.
    assert db.query(AIAssistantTrace).count() == 0


# --------------------------------------------------------------------------- #
# sweep_expired_traces                                                        #
# --------------------------------------------------------------------------- #


def _seed_trace(db: Session, *, label: str, status: str, flagged: bool, days_old: int) -> str:
    """Insert a trace with a valid-UUID id, return that id (labels are for the
    test's own bookkeeping — UUID columns reject slug ids)."""
    tid = str(uuid.uuid4())
    created = datetime.utcnow() - timedelta(days=days_old)
    db.add(
        AIAssistantTrace(
            id=tid,
            session_id=label,  # stash the human label somewhere queryable
            status=status,
            flagged=flagged,
            created_at=created,
            started_at=created,
            ended_at=created,
        )
    )
    return tid


def test_sweep_expired_traces_buckets(db: Session):
    # Settings row with default TTLs (ok=30d, error/flagged=90d).
    db.add(SystemSetting(id=str(uuid.uuid4()), ai_trace_ttl_days=30, ai_trace_error_ttl_days=90))
    db.commit()

    _seed_trace(db, label="ok-old", status="ok", flagged=False, days_old=40)       # expired
    _seed_trace(db, label="ok-new", status="ok", flagged=False, days_old=10)       # kept
    _seed_trace(db, label="err-mid", status="error", flagged=False, days_old=40)   # kept (<90)
    _seed_trace(db, label="err-old", status="error", flagged=False, days_old=100)  # expired
    _seed_trace(db, label="flag-mid", status="ok", flagged=True, days_old=40)      # kept (<90)
    _seed_trace(db, label="flag-old", status="ok", flagged=True, days_old=100)     # expired
    db.commit()

    counts = sweep_expired_traces(db)

    assert counts == {"ok_deleted": 1, "error_deleted": 2}
    remaining = {t.session_id for t in db.query(AIAssistantTrace).all()}
    assert remaining == {"ok-new", "err-mid", "flag-mid"}


def test_sweep_falls_back_to_defaults_without_settings_row(db: Session):
    # No SystemSetting row → read yields None → defaults 30/90 used.
    _seed_trace(db, label="ok-old", status="ok", flagged=False, days_old=45)  # > 30 default
    _seed_trace(db, label="ok-new", status="ok", flagged=False, days_old=5)   # kept
    db.commit()

    counts = sweep_expired_traces(db)

    assert counts["ok_deleted"] == 1
    remaining = {t.session_id for t in db.query(AIAssistantTrace).all()}
    assert remaining == {"ok-new"}
