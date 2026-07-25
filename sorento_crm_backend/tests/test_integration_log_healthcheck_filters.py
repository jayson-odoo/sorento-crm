"""Integration-log list filters (System Health WS1).

Service-level tests for IntegrationLogService.list_integration_logs:
- created_from / created_to window filter.
- n8n_healthcheck sentinel rows are EXCLUDED by default but INCLUDED when the
  caller passes integration_channel='n8n_healthcheck' explicitly.
"""
import uuid
from datetime import datetime, timedelta

import pytest

from app.models.integration import IntegrationLog
from app.services.integration_service import IntegrationLogService
from app.services.n8n_liveness_service import HEALTHCHECK_CHANNEL
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    """A blank Postgres schema, rolled back after the test.

    Was in-memory sqlite plus a `_prep` helper that rewrote JSONB/ARRAY columns
    to JSON *on the shared model classes*. That mutation was global and
    permanent for the process, so it leaked into every other test importing the
    same models. Postgres needs neither the rewrite nor the hand-picked table
    list.
    """
    with blank_session() as session:
        yield session


def _log(session, *, channel, created_at, status="sent"):
    log = IntegrationLog(
        id=str(uuid.uuid4()),
        integration_channel=channel,
        business_table="attachments",
        business_id=str(uuid.uuid4()),
        direction="outbound",
        endpoint="https://example.invalid/webhook",
        http_method="POST",
        status=status,
        created_at=created_at,
    )
    session.add(log)
    session.commit()
    return log


NOW = datetime(2026, 7, 1, 12, 0, 0)


def test_healthcheck_excluded_by_default(db):
    _log(db, channel="respond_io", created_at=NOW)
    _log(db, channel=HEALTHCHECK_CHANNEL, created_at=NOW)

    svc = IntegrationLogService(db)
    result = svc.list_integration_logs()

    assert result["pagination"].total == 1
    channels = {r.integration_channel for r in result["data"]}
    assert channels == {"respond_io"}


def test_healthcheck_included_when_requested_explicitly(db):
    _log(db, channel="respond_io", created_at=NOW)
    _log(db, channel=HEALTHCHECK_CHANNEL, created_at=NOW)

    svc = IntegrationLogService(db)
    result = svc.list_integration_logs(integration_channel=HEALTHCHECK_CHANNEL)

    assert result["pagination"].total == 1
    assert result["data"][0].integration_channel == HEALTHCHECK_CHANNEL


def test_created_window_filter(db):
    _log(db, channel="respond_io", created_at=NOW - timedelta(days=3))  # old
    _log(db, channel="respond_io", created_at=NOW - timedelta(hours=2))  # in window
    _log(db, channel="respond_io", created_at=NOW + timedelta(days=1))  # future

    svc = IntegrationLogService(db)
    result = svc.list_integration_logs(
        created_from=NOW - timedelta(hours=24),
        created_to=NOW,
    )

    assert result["pagination"].total == 1
    got = result["data"][0].created_at
    assert got == NOW - timedelta(hours=2)


def test_created_from_only(db):
    _log(db, channel="respond_io", created_at=NOW - timedelta(days=2))
    _log(db, channel="respond_io", created_at=NOW)

    svc = IntegrationLogService(db)
    result = svc.list_integration_logs(created_from=NOW - timedelta(hours=1))
    assert result["pagination"].total == 1
