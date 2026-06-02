"""
Sweeper tests for IntegrationLogService.process_pending_logs.

Covers the Phase 2 extension that marks `sent` rows whose n8n callback
never arrived as failed with error_code=N8N_CALLBACK_TIMEOUT.
See app/services/integration_service.py and
docs/plans/PLAN-upload-activity-drawer.md §4.5.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.models.integration import IntegrationLog
from app.services.integration_service import IntegrationLogService


@pytest.fixture
def db_session():
    """SQLite-backed session with integration_log + lookup_bindings tables.

    The wider model set uses JSONB columns that SQLite can't render; we don't
    need most of them. lookup_bindings is required because a global SQLAlchemy
    before-insert listener (`lookup_write_listener`) validates writes against
    it — once the listener is registered via app import side-effects in
    another test, every IntegrationLog INSERT/UPDATE looks for the table.
    """
    from app.models.lookup import LookupBinding

    engine = create_engine("sqlite:///:memory:")
    IntegrationLog.__table__.create(bind=engine)
    LookupBinding.__table__.create(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_sent_log(session: Session, processed_at: datetime, *, status="sent") -> IntegrationLog:
    log = IntegrationLog(
        integration_channel="n8n",
        business_table="attachments",
        business_id=str(uuid.uuid4()),
        direction="outbound",
        endpoint="https://example.invalid/webhook",
        http_method="POST",
        status=status,
        processed_at=processed_at,
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


def test_stale_sent_row_marked_failed_with_n8n_timeout(db_session, monkeypatch):
    monkeypatch.setenv("N8N_CALLBACK_TIMEOUT_MINUTES", "10")
    stale = _make_sent_log(
        db_session,
        processed_at=datetime.utcnow() - timedelta(minutes=11),
    )

    service = IntegrationLogService(db_session)
    result = service.process_pending_logs()

    db_session.refresh(stale)
    assert stale.status == "failed"
    assert stale.error_code == "N8N_CALLBACK_TIMEOUT"
    assert result["timed_out"] == 1


def test_recent_sent_row_left_alone(db_session, monkeypatch):
    monkeypatch.setenv("N8N_CALLBACK_TIMEOUT_MINUTES", "10")
    fresh = _make_sent_log(
        db_session,
        processed_at=datetime.utcnow() - timedelta(minutes=2),
    )

    service = IntegrationLogService(db_session)
    result = service.process_pending_logs()

    db_session.refresh(fresh)
    assert fresh.status == "sent"  # untouched
    assert result["timed_out"] == 0


def test_timeout_minutes_env_override_is_respected(db_session, monkeypatch):
    """Custom env value moves the sweep window."""
    monkeypatch.setenv("N8N_CALLBACK_TIMEOUT_MINUTES", "60")
    # processed_at 30 min ago — would be stale at default 10min, fresh at 60min.
    log = _make_sent_log(
        db_session,
        processed_at=datetime.utcnow() - timedelta(minutes=30),
    )

    service = IntegrationLogService(db_session)
    result = service.process_pending_logs()

    db_session.refresh(log)
    assert log.status == "sent"
    assert result["timed_out"] == 0


def test_default_timeout_minutes_is_ten(db_session, monkeypatch):
    """No env → default 10 minutes."""
    monkeypatch.delenv("N8N_CALLBACK_TIMEOUT_MINUTES", raising=False)
    service = IntegrationLogService(db_session)
    assert service._get_n8n_callback_timeout_minutes() == 10
