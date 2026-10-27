"""HA-TIER1-N8N-BOX: GET /api/v1/health/role, the Cloudflare Load Balancing monitor.

200 only when the node's database accepts writes, so the LB sends no users to a warm standby
until its replica is promoted (documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md
sections 2 and 5). Unauthenticated: states and one number, never error text.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import app.database as database
from app.main import app


class _RowSession:
    def __init__(self, row):
        self.row = row

    def execute(self, *a, **kw):
        row = self.row

        class _R:
            def one(self_inner):
                return row

        return _R()

    def close(self):
        pass


def test_primary_is_200_without_credentials():
    response = TestClient(app).get("/api/v1/health/role")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "role": "primary"}


def test_hot_standby_is_503_with_lag(monkeypatch):
    monkeypatch.setattr(database, "SessionLocal", lambda: _RowSession((True, 2.345)))
    response = TestClient(app).get("/api/v1/health/role")
    assert response.status_code == 503
    assert response.json() == {"status": "standby", "role": "standby", "replay_lag_seconds": 2.3}
    assert '"status":"healthy"' not in response.text


def test_standby_that_never_replayed_reports_null_lag(monkeypatch):
    monkeypatch.setattr(database, "SessionLocal", lambda: _RowSession((True, None)))
    response = TestClient(app).get("/api/v1/health/role")
    assert response.status_code == 503
    assert response.json()["replay_lag_seconds"] is None


def test_db_down_is_503_and_leaks_nothing(monkeypatch):
    class _Broken:
        def execute(self, *a, **kw):
            raise RuntimeError('connection to server at "db-secret-host", port 6432 failed')

        def close(self):
            pass

    monkeypatch.setattr(database, "SessionLocal", lambda: _Broken())
    response = TestClient(app).get("/api/v1/health/role")
    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "role": "unknown"}
    assert "db-secret-host" not in response.text
