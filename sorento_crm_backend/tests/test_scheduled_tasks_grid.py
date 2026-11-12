"""SCHEDULED-TASKS-GRID: GET /system/scheduled-tasks sorts, filters and pages server-side.

Owner rules (9 Nov): every column sortable server-side, every dropdown filter multi-select.
Rows are scoped by the `zzt` search so the blank schema's own seeds never count.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from tests._pg_fixture import TEST_PREFIX, blank_session

URL = "/api/v1/system/scheduled-tasks"
P = TEST_PREFIX.lower()


@pytest.fixture
def db():
    from app.models.base import set_company_scope

    with blank_session() as s:
        set_company_scope(s, None)
        yield s


@pytest.fixture
def tasks(db):
    from app.models.scheduled_task import ScheduledTask

    now = datetime.utcnow()
    rows = [
        ScheduledTask(key=f"{P}_grid_alpha", name=f"{TEST_PREFIX} Alpha", enabled=True,
                      interval_unit="hours", interval_value=1, last_status="success",
                      last_run_at=now - timedelta(hours=2), next_run_at=now + timedelta(minutes=5)),
        ScheduledTask(key=f"{P}_grid_bravo", name=f"{TEST_PREFIX} Bravo", enabled=False,
                      interval_unit="seconds", interval_value=30, last_status="failed",
                      last_error="ZZT boom in company Mocha",
                      last_run_at=now - timedelta(hours=1), next_run_at=now + timedelta(minutes=1)),
        ScheduledTask(key=f"{P}_grid_charlie", name=f"{TEST_PREFIX} Charlie", enabled=True,
                      interval_unit="minutes", interval_value=2),
    ]
    db.add_all(rows)
    db.commit()
    return rows


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope

    who = {"id": str(uuid.uuid4()), "email": f"{P}-grid@zzt.test"}

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: who
    app.dependency_overrides[get_current_user_or_api_key] = lambda: who
    app.dependency_overrides[apply_company_scope] = lambda: None
    try:
        yield TestClient(app)
    finally:
        for dep in (get_db, get_current_user, get_current_user_or_api_key, apply_company_scope):
            app.dependency_overrides.pop(dep, None)


def _names(client, **params):
    resp = client.get(URL, params={"query": P, **params})
    assert resp.status_code == 200, resp.text
    return [row["name"].removeprefix(f"{TEST_PREFIX} ") for row in resp.json()["data"]]


def test_default_order_is_by_name(client, tasks):
    assert _names(client) == ["Alpha", "Bravo", "Charlie"]


def test_frequency_sorts_by_the_real_interval_length(client, tasks):
    assert _names(client, sort="frequency", dir="asc") == ["Bravo", "Charlie", "Alpha"]
    assert _names(client, sort="frequency", dir="desc") == ["Alpha", "Charlie", "Bravo"]


@pytest.mark.parametrize(
    "sort,expected",
    [
        ("name", ["Charlie", "Bravo", "Alpha"]),
        ("key", ["Charlie", "Bravo", "Alpha"]),
        ("enabled", ["Alpha", "Charlie", "Bravo"]),  # true first, then name
        ("last_status", ["Alpha", "Bravo", "Charlie"]),  # success > failed, never last
        ("last_run_at", ["Bravo", "Alpha", "Charlie"]),
        ("next_run_at", ["Alpha", "Bravo", "Charlie"]),
        ("last_error", ["Bravo", "Alpha", "Charlie"]),
    ],
)
def test_every_column_sorts_server_side_desc_with_nulls_last(client, tasks, sort, expected):
    assert _names(client, sort=sort, dir="desc") == expected


def test_an_unknown_sort_is_refused(client, tasks):
    assert client.get(URL, params={"sort": "nope"}).status_code == 422


def test_enabled_filter(client, tasks):
    assert _names(client, enabled="false") == ["Bravo"]
    assert _names(client, enabled=["true", "false"]) == ["Alpha", "Bravo", "Charlie"]


def test_an_unknown_enabled_value_is_refused(client, tasks):
    assert client.get(URL, params={"enabled": "maybe"}).status_code == 422


def test_last_status_filter_is_multi_value_and_knows_never(client, tasks):
    assert _names(client, last_status=["failed", "never"]) == ["Bravo", "Charlie"]
    assert _names(client, last_status="success,failed") == ["Alpha", "Bravo"]


def test_frequency_unit_filter_is_multi_value(client, tasks):
    assert _names(client, interval_unit=["seconds", "hours"]) == ["Alpha", "Bravo"]


def test_search_reads_the_last_error(client, tasks):
    resp = client.get(URL, params={"query": "boom in company"})
    assert [r["key"] for r in resp.json()["data"]] == [f"{P}_grid_bravo"]


def test_pages_with_the_total_across_pages(client, tasks):
    resp = client.get(URL, params={"query": P, "limit": 2, "page": 2})
    body = resp.json()
    assert body["pagination"] == {"total": 3, "page": 2, "limit": 2}
    assert [r["key"] for r in body["data"]] == [f"{P}_grid_charlie"]
