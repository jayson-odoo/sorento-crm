"""n8n liveness probe — run_n8n_liveness_ping (System Health WS1d).

Service-level unit test over an empty Postgres schema. The outbound webhook send
is mocked (IntegrationLogService.send_webhook_for_log) so no real HTTP fires; we
assert the probe seeds a healthcheck integration_log carrying its own id and
returns the small run-log dict.
"""
import json

import pytest

from app.models.integration import IntegrationLog
from app.services import n8n_liveness_service as mod
from app.services.integration_service import IntegrationLogService
from app.services.n8n_liveness_service import (
    HEALTHCHECK_BUSINESS_TABLE,
    HEALTHCHECK_CHANNEL,
    run_n8n_liveness_ping,
)
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    """Empty Postgres schema over the full real DDL.

    The sqlite version had to rewrite every JSONB/ARRAY column to JSON and null
    its server_default first. That edit was to the shared model metadata, so it
    persisted process-wide and silently changed those columns for whatever ran
    afterwards. On Postgres the real types compile, so it is gone -- along with
    the leak. Blank rather than live because both tests count all rows.
    """
    with blank_session() as session:
        yield session


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
