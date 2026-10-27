"""HA-TIER1-N8N-BOX: GET /api/v1/health/role, the Cloudflare Load Balancing monitor.

200 only when the node's database accepts writes, so the LB sends no users to a warm standby
until its replica is promoted (documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md
sections 2 and 5). Unauthenticated: states only, never error text or lag.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import app.database as database
from app.main import app


class _RowSession:
    def __init__(self, in_recovery):
        self.in_recovery = in_recovery

    def execute(self, *a, **kw):
        value = self.in_recovery

        class _R:
            def scalar(self_inner):
                return value

        return _R()

    def close(self):
        pass


def test_primary_is_200_without_credentials():
    response = TestClient(app).get("/api/v1/health/role")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "role": "primary"}


def test_hot_standby_is_503_and_states_only(monkeypatch):
    monkeypatch.setattr(database, "SessionLocal", lambda: _RowSession(True))
    response = TestClient(app).get("/api/v1/health/role")
    assert response.status_code == 503
    # No lag on a public URL: it would show when the business is active (security review N1).
    assert response.json() == {"status": "standby", "role": "standby"}
    assert '"status":"healthy"' not in response.text


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
