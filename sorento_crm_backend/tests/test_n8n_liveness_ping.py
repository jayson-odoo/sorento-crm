"""n8n liveness probe — run_n8n_liveness_ping (System Health WS1d).

Service-level unit test over a sqlite fixture. The outbound webhook send is
mocked (IntegrationLogService.send_webhook_for_log) so no real HTTP fires; we
assert the probe seeds a healthcheck integration_log carrying its own id and
returns the small run-log dict.
"""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import JSON

from app.database import Base
from app.models.integration import IntegrationLog
from app.models.lookup import LookupBinding
from app.services import n8n_liveness_service as mod
from app.services.integration_service import IntegrationLogService
from app.services.n8n_liveness_service import (
    HEALTHCHECK_BUSINESS_TABLE,
    HEALTHCHECK_CHANNEL,
    run_n8n_liveness_ping,
)


def _prep(*models):
    for model in models:
        for col in model.__table__.columns:
            if isinstance(col.type, (JSONB, ARRAY)):
                col.type = JSON()
                col.server_default = None


@pytest.fixture
def db():
    _prep(IntegrationLog, LookupBinding)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine, tables=[IntegrationLog.__table__, LookupBinding.__table__]
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_ping_seeds_healthcheck_log_and_returns_sent(db, monkeypatch):
    sent_for = {}

    def _fake_send(self, log_id, **kw):
        sent_for["log_id"] = str(log_id)
        return True, None

    monkeypatch.setattr(IntegrationLogService, "send_webhook_for_log", _fake_send)

    out = run_n8n_liveness_ping(db)

    # Exactly one healthcheck row created.
    rows = db.query(IntegrationLog).all()
    assert len(rows) == 1
    log = rows[0]
    assert log.integration_channel == HEALTHCHECK_CHANNEL
    assert log.business_table == HEALTHCHECK_BUSINESS_TABLE
    assert log.direction == "outbound"
    assert log.http_method == "POST"

    # Payload carries its own integration_log_id so n8n echoes it back to /status.
    assert log.request_payload
    payload = json.loads(log.request_payload)
    assert payload["integration_log_id"] == str(log.id)

    # Return dict shape.
    assert out["log_id"] == str(log.id)
    assert out["sent"] is True
    assert out["error"] is None
    assert out["url"] == mod._ping_url()
    # The send was invoked for the freshly-created log.
    assert sent_for["log_id"] == str(log.id)


def test_ping_reports_send_failure(db, monkeypatch):
    monkeypatch.setattr(
        IntegrationLogService,
        "send_webhook_for_log",
        lambda self, log_id, **kw: (False, "boom"),
    )

    out = run_n8n_liveness_ping(db)

    assert out["sent"] is False
    assert out["error"] == "boom"
    # The row is still persisted (probe seeded before send).
    assert db.query(IntegrationLog).count() == 1


def test_ping_url_env_override(monkeypatch):
    monkeypatch.setenv("N8N_LIVENESS_PING_URL", "https://custom.example/ping")
    assert mod._ping_url() == "https://custom.example/ping"
    monkeypatch.delenv("N8N_LIVENESS_PING_URL", raising=False)
    assert mod._ping_url() == mod.DEFAULT_PING_URL
