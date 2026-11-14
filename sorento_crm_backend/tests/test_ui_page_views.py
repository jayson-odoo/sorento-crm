"""UI-V2 phase 0, slice S1: page-view telemetry ingest and retention (UAC D-1 .. D-4).

Copies the client-error ingest (tests/test_client_error_report.py): any signed-in principal,
user id from the session, 16 KB body cap, the table is the rate-limit counter, 90-day retention.

ASSUMED request shape (the PLAN does not pin it; change ``_body`` if the contract says otherwise):
    {"items": [{"route", "viewport", "ms_to_first_data", "ui_version", "at"}, ...]}

Rows are read and seeded with raw SQL on the table name the PLAN gives (``ui_page_views``), so
these tests do not depend on the ORM class name, and nothing from the new code is imported at
module level (the service is imported inside the one test that needs it).

Run:
    SORENTO_ENV_FILE=.env.ci-tests venv/bin/python -m pytest tests/test_ui_page_views.py -q
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.user import User
from tests._ai_usage_client import api_client
from tests._pg_fixture import TEST_PREFIX, blank_session

URL = "/api/v1/system/page-views"
MAX_BODY_BYTES = 16 * 1024
RATE_LIMIT_PER_HOUR = 120
SOME_UUID = "3f2b8a52-1c3d-4e5f-8a9b-0c1d2e3f4a5b"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _item(**over):
    item = {
        "route": "/project-sales/order-inquiries",
        "viewport": "desktop",
        "ms_to_first_data": 420,
        "ui_version": "v2",
        "at": "2026-11-12T08:00:00Z",
    }
    item.update(over)
    return item


def _body(items, **top):
    return {"items": items, **top}


def _seed_user(db, user_id: str, email: str | None = None) -> str:
    db.add(
        User(
            id=user_id,
            email=email or f"{TEST_PREFIX.lower()}-pv-{user_id[:8]}@test.invalid",
            name=f"{TEST_PREFIX} PageView User",
            status="ACTIVE",
        )
    )
    db.commit()
    return user_id


def _rows(db):
    return db.execute(
        text(
            "SELECT user_id, route, viewport, ui_version, ms_to_first_data "
            "FROM ui_page_views ORDER BY route"
        )
    ).fetchall()


def _count(db) -> int:
    return db.execute(text("SELECT count(*) FROM ui_page_views")).scalar()


def _insert_view(db, user_id: str, route: str, created_at: datetime) -> None:
    db.execute(
        text(
            "INSERT INTO ui_page_views "
            "(id, user_id, route, viewport, ui_version, ms_to_first_data, viewed_at, created_at) "
            "VALUES (CAST(:id AS uuid), :u, :r, 'desktop', 'v2', 100, :t, :t)"
        ),
        {"id": str(uuid.uuid4()), "u": user_id, "r": route, "t": created_at},
    )


# --------------------------------------------------------------------------- #
# D-1 - a batch is stored against the session user                              #
# --------------------------------------------------------------------------- #


def test_page_views_batch_stored_with_session_user(db):
    other = _seed_user(db, str(uuid.uuid4()))
    items = [
        _item(route="/inventory/stock-inquiries", user_id=other),
        _item(route="/project-sales/order-inquiries", viewport="phone", user_id=other),
        _item(route="/user-management/settings", viewport="tablet", ms_to_first_data=None, user_id=other),
    ]
    with api_client(db, []) as client:
        me = _seed_user(db, client.actor["id"], client.actor["email"])
        r = client.post(URL, json=_body(items, user_id=other))
    assert r.status_code == 204
    rows = _rows(db)
    assert len(rows) == 3
    assert {str(row.user_id) for row in rows} == {me}
    assert {row.viewport for row in rows} == {"desktop", "phone", "tablet"}
    assert {row.ui_version for row in rows} == {"v2"}
    assert sorted(row.ms_to_first_data for row in rows if row.ms_to_first_data is not None) == [420, 420]


# --------------------------------------------------------------------------- #
# D-2 - routes are stored as patterns                                           #
# --------------------------------------------------------------------------- #


def test_page_views_route_normalised(db):
    items = [
        _item(route=f"/project-sales/order-inquiries/{SOME_UUID}?tab=lines&q=secret"),
        _item(route="/inventory/stock-inquiries/12345"),
        _item(route="/project-sales/customers?q=customer+name#frag"),
    ]
    with api_client(db, []) as client:
        _seed_user(db, client.actor["id"], client.actor["email"])
        r = client.post(URL, json=_body(items))
    assert r.status_code == 204
    stored = sorted(row.route for row in _rows(db))
    assert stored == [
        "/inventory/stock-inquiries/[id]",
        "/project-sales/customers",
        "/project-sales/order-inquiries/[id]",
    ]
    for route in stored:
        assert "?" not in route and SOME_UUID not in route and "12345" not in route


def test_page_views_route_any_segment_with_a_digit_is_an_id(db):
    """Order numbers and codes are ids too, not only UUIDs and bare digits."""
    items = [
        _item(route="/project-sales/order-inquiries/SPO-2026-0012"),
        _item(route="/inventory/products/AB12"),
        _item(route="/user-management/settings/appearance"),
    ]
    with api_client(db, []) as client:
        _seed_user(db, client.actor["id"], client.actor["email"])
        r = client.post(URL, json=_body(items))
    assert r.status_code == 204
    assert sorted(row.route for row in _rows(db)) == [
        "/inventory/products/[id]",
        "/project-sales/order-inquiries/[id]",
        "/user-management/settings/appearance",
    ]


@pytest.mark.parametrize("bad", ["/a b", "/a<script>", "/caf\u00e9", "/a%20b", "/x;y"])
def test_page_views_route_with_odd_characters_is_422(db, bad):
    with api_client(db, []) as client:
        _seed_user(db, client.actor["id"], client.actor["email"])
        r = client.post(URL, json=_body([_item(route=bad)]))
    assert r.status_code == 422
    assert _count(db) == 0


# --------------------------------------------------------------------------- #
# D-3 - validation, auth, body cap, rate limit                                  #
# --------------------------------------------------------------------------- #


def test_page_views_validation(db):
    cases = {
        "51 items": _body([_item() for _ in range(51)]),
        "viewport watch": _body([_item(viewport="watch")]),
        "ms -1": _body([_item(ms_to_first_data=-1)]),
        "ms 600001": _body([_item(ms_to_first_data=600001)]),
    }
    with api_client(db, []) as client:
        _seed_user(db, client.actor["id"], client.actor["email"])
        for label, payload in cases.items():
            r = client.post(URL, json=payload)
            assert r.status_code == 422, label
    assert _count(db) == 0


def test_page_views_unauthenticated_401():
    from app.main import app

    app.dependency_overrides.clear()
    r = TestClient(app).post(URL, json=_body([_item()]))
    assert r.status_code == 401


def test_page_views_body_cap_413(db):
    payload = _body([_item(route="/x" + "y" * (MAX_BODY_BYTES + 10))])
    with api_client(db, []) as client:
        _seed_user(db, client.actor["id"], client.actor["email"])
        r = client.post(URL, json=payload)
    assert r.status_code == 413
    assert _count(db) == 0


def test_page_views_rate_limited_429(db):
    with api_client(db, []) as client:
        me = _seed_user(db, client.actor["id"], client.actor["email"])
        now = datetime.utcnow()
        # 120 POSTS: each post stamps its rows with one created_at, so seed 120 distinct stamps.
        for i in range(RATE_LIMIT_PER_HOUR):
            _insert_view(db, me, "/seeded", now - timedelta(minutes=5) - timedelta(seconds=i))
        db.commit()
        r = client.post(URL, json=_body([_item()]))
    assert r.status_code == 429
    assert _count(db) == RATE_LIMIT_PER_HOUR


def _seed_posts(db, user_id: str, posts: int, rows_per_post: int) -> None:
    """`posts` posts in the last hour; the rows of one post share one created_at."""
    base = datetime.utcnow() - timedelta(minutes=5)
    for i in range(posts):
        stamp = base - timedelta(seconds=i)
        for _ in range(rows_per_post):
            _insert_view(db, user_id, "/seeded", stamp)
    db.commit()


def test_rate_limit_counts_posts_not_rows(db):
    """119 posts of 3 rows (357 rows): the 120th post passes, the 121st is refused.

    Kills a limiter that counts rows (357 >= 120 would already refuse the first)."""
    with api_client(db, []) as client:
        me = _seed_user(db, client.actor["id"], client.actor["email"])
        _seed_posts(db, me, posts=119, rows_per_post=3)
        allowed = client.post(URL, json=_body([_item(), _item(), _item()]))
        refused = client.post(URL, json=_body([_item()]))
    assert allowed.status_code == 204
    assert refused.status_code == 429


def test_rate_limit_row_ceiling_1200_per_hour(db):
    """100 posts of 12 rows is 1200 rows: under the post limit, at the row ceiling."""
    with api_client(db, []) as client:
        me = _seed_user(db, client.actor["id"], client.actor["email"])
        _seed_posts(db, me, posts=100, rows_per_post=12)
        r = client.post(URL, json=_body([_item()]))
    assert r.status_code == 429
    assert _count(db) == 1200


def test_rate_limit_just_under_the_row_ceiling_passes(db):
    with api_client(db, []) as client:
        me = _seed_user(db, client.actor["id"], client.actor["email"])
        _seed_posts(db, me, posts=100, rows_per_post=11)  # 1100 rows
        r = client.post(URL, json=_body([_item()]))
    assert r.status_code == 204


# --------------------------------------------------------------------------- #
# D-4 - 90-day retention                                                        #
# --------------------------------------------------------------------------- #


def test_page_views_prune_90_days(db):
    from app.services import ui_page_view_service as svc

    me = _seed_user(db, str(uuid.uuid4()))
    now = datetime.utcnow()
    _insert_view(db, me, "/old", now - timedelta(days=91))
    _insert_view(db, me, "/new", now - timedelta(days=89))
    db.commit()

    svc.prune_older_than(db)
    db.commit()

    assert [row.route for row in _rows(db)] == ["/new"]


def test_daily_prune_task_deletes_old_page_views(db):
    """The 90-day retention rides the api_call_log_prune handler; guard the hook itself."""
    from app.scheduler.task_scheduler import _handler_api_call_log_prune

    me = _seed_user(db, str(uuid.uuid4()))
    now = datetime.utcnow()
    _insert_view(db, me, "/old", now - timedelta(days=91))
    _insert_view(db, me, "/new", now - timedelta(days=89))
    db.commit()

    result = _handler_api_call_log_prune(db, None)

    assert "rows_deleted" in result  # the handler still does its own work
    assert [row.route for row in _rows(db)] == ["/new"]
