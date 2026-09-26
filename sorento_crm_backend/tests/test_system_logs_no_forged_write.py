"""`system_logs` cannot be forged over HTTP (issue #1281, section 6.3).

`POST /api/v1/user-management/system-logs/` had no permission dependency beyond
the router's module guard and wrote whatever `user_id` and `ip_address` the body
named, so any caller could plant a log line attributed to any user from any
address. Nothing called it: the FE `systemLog()` helper had no importer, and the
backend writes system logs in-process (`app/services/system_log.py`,
`app/services/logging.py`) with the real actor. The route is removed; the two
reads stay, on `user_management.logs.view`.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app
import app.database as app_database
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.models.user import SystemLog, User
from tests._pg_fixture import blank_session

PATH = "/api/v1/user-management/system-logs/"


def test_no_write_route_is_mounted_on_system_logs():
    writes = [
        (route.path, sorted(route.methods))
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/user-management/system-logs")
        and set(getattr(route, "methods", set()) or set()) - {"GET", "HEAD"}
    ]
    assert writes == []


def test_a_forged_post_writes_nothing():
    with blank_session() as db:
        victim = str(uuid.uuid4())
        db.add(User(id=victim, email=f"zz-victim-{victim[:8]}@example.com", status="ACTIVE"))
        db.commit()

        def _override_db():
            yield db

        app.dependency_overrides[app_database.get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: {"id": victim}
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": victim}
        try:
            r = TestClient(app).post(PATH, json={
                "event": "user.login",
                "user_id": victim,
                "ip_address": "203.0.113.7",
                "description": "forged",
            })
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 405, r.text
        assert db.query(SystemLog).filter(SystemLog.user_id == victim).count() == 0
