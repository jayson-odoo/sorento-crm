"""Admin health dashboard — GET /api/v1/system/health/summary.

The endpoint aggregates five operational tables into one payload. Each metric
block is guarded so a missing/legacy model omits the block rather than 500-ing.
Here the DB is a MagicMock and each per-block builder is monkeypatched to a
deterministic value, so the test pins the response shape + auth-deny path
without needing a live database.
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_db, get_current_user, get_current_user_or_api_key
from app.services.user_service import UserPermissionService
import app.api.v1.system.health as mod


@pytest.fixture
def client(monkeypatch):
    def _db():
        yield MagicMock()

    _user = {"id": "admin"}
    app.dependency_overrides[get_db] = _db
    # System router sits behind a module guard (get_current_user_or_api_key);
    # the route uses require_permission -> get_current_user. Satisfy both + grant.
    app.dependency_overrides[get_current_user] = lambda: _user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _user
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def _stub_all_blocks(monkeypatch):
    monkeypatch.setattr(
        mod,
        "_email_outbox_health",
        lambda db, cutoff, window_end: mod.EmailOutboxHealth(
            pending=3, sent=10, failed=2, cancelled=1, failed_in_window=2, failed_last_24h=2
        ),
    )
    monkeypatch.setattr(
        mod,
        "_imports_health",
        lambda db, cutoff, window_end: mod.ImportsHealth(
            total_last_24h=4, finished_last_24h=3, failed_last_24h=1, success_rate=75.0
        ),
    )
    monkeypatch.setattr(
        mod,
        "_scheduled_tasks_health",
        lambda db, now: mod.ScheduledTasksHealth(total=5, overdue=1, last_run_failed=2),
    )
    monkeypatch.setattr(
        mod,
        "_integrations_health",
        lambda db, cutoff, window_end: mod.IntegrationsHealth(
            channels=[
                mod.IntegrationChannelHealth(
                    channel="respond_io",
                    success=8,
                    failed=1,
                    total=9,
                    top_failures=[
                        mod.FailureSignatureOut(
                            signature="unauthorized",
                            sample_message="Unauthorized",
                            status_code=401,
                            count=1,
                        )
                    ],
                )
            ]
        ),
    )
    monkeypatch.setattr(
        mod,
        "_audit_activity_health",
        lambda db, cutoff, now: mod.AuditActivityHealth(
            count_last_24h=12,
            daily_trend=[mod.AuditTrendPoint(date="2026-06-30", count=12)],
        ),
    )


def test_health_summary_returns_all_blocks(client, monkeypatch):
    _stub_all_blocks(monkeypatch)
    r = client.get("/api/v1/system/health/summary")
    assert r.status_code == 200
    body = r.json()

    assert set(body.keys()) >= {
        "generated_at",
        "email_outbox",
        "imports",
        "scheduled_tasks",
        "integrations",
        "audit_activity",
    }
    assert body["email_outbox"] == {
        "pending": 3,
        "sent": 10,
        "failed": 2,
        "cancelled": 1,
        # Windowed failure count, rendered as the headline so an all-time total
        # can no longer read as a live incident.
        "failed_in_window": 2,
        "failed_last_24h": 2,
    }
    assert body["imports"]["success_rate"] == 75.0
    assert body["scheduled_tasks"]["overdue"] == 1
    assert body["integrations"]["channels"][0]["channel"] == "respond_io"
    # The failure count is only actionable if the cause travels with it.
    fault = body["integrations"]["channels"][0]["top_failures"][0]
    assert fault["status_code"] == 401
    assert fault["sample_message"] == "Unauthorized"
    assert body["audit_activity"]["count_last_24h"] == 12


def test_health_summary_omits_missing_block(client, monkeypatch):
    """A block whose builder returns None (missing/legacy model) is null, not 500."""
    _stub_all_blocks(monkeypatch)
    monkeypatch.setattr(mod, "_integrations_health", lambda db, cutoff, window_end: None)
    r = client.get("/api/v1/system/health/summary")
    assert r.status_code == 200
    assert r.json()["integrations"] is None


def test_health_summary_requires_auth(client, monkeypatch):
    """Auth-only endpoint (matches Audit/Import/Integration Logs): no principal -> 401."""
    from fastapi import HTTPException

    def _deny():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user_or_api_key] = _deny
    r = client.get("/api/v1/system/health/summary")
    assert r.status_code == 401
