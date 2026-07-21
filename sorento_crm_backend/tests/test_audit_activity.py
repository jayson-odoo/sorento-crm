"""Cross-Entity Activity Timeline — GET /api/v1/audit/activity.

Exercises the real label resolver over a blank Postgres schema: seeded
AuditLog rows plus a couple of live entity rows (complaint, order, user) so
entity_id -> human label resolution is genuinely tested, including the
hard-deleted fallback (an audit row whose live row is gone). Auth-deny is
pinned separately with a TestClient + dependency overrides.
"""
import uuid
from datetime import datetime, timedelta

import pytest

from app.models.audit import AuditLog
from app.models.user import User
from app.models.complaints import Complaint
from app.models.order import Order
from app.services.activity_service import get_activity_feed
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield from _seeded(session)


def _seeded(session):
    now = datetime(2026, 6, 30, 9, 0, 0)

    # --- live entity rows (for label resolution) ---
    complaint_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    actor_id = str(uuid.uuid4())
    session.add_all([
        User(id=actor_id, email="jane@example.com", name="Jane Tan", status="active"),
        Complaint(id=complaint_id, complaint_number="CMP-1042", status="resolved"),
        Order(id=order_id, order_number="SO-5567"),
    ])
    session.commit()
    # Drop any audit rows the listener auto-wrote for the seed inserts so counts
    # are deterministic; the rows under test are inserted explicitly below.
    session.query(AuditLog).delete()
    session.commit()

    deleted_order_id = str(uuid.uuid4())

    def _audit(entity_type, entity_id, action, minutes, **kw):
        return AuditLog(
            id=str(uuid.uuid4()),
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            changed_at=now - timedelta(minutes=minutes),
            **kw,
        )

    session.add_all([
        _audit(
            "complaint", complaint_id, "UPDATE", 5,
            user_id=actor_id,
            old_values={"status": "pending", "updated_at": "2026-06-30T08:00:00"},
            new_values={"status": "resolved", "updated_at": "2026-06-30T09:00:00"},
            trace_id="trace-abc",
        ),
        _audit(
            "orders", order_id, "CREATE", 20,
            user_id=actor_id,
            new_values={"order_number": "SO-5567"},
            description="New order created",
        ),
        _audit(
            "users", actor_id, "UPDATE", 60,
            user_id=None,  # system actor
            old_values={"name": "Jane"},
            new_values={"name": "Jane Tan"},
        ),
        # Hard-deleted order: no live row, label must fall back to the snapshot.
        _audit(
            "orders", deleted_order_id, "DELETE", 120,
            user_id=actor_id,
            old_values={"order_number": "SO-5560"},
            description="Order deleted",
        ),
    ])
    session.commit()

    session.info["ids"] = {
        "complaint": complaint_id,
        "order": order_id,
        "actor": actor_id,
        "deleted_order": deleted_order_id,
    }
    yield session


def test_happy_path_resolves_labels_changes_and_actors(db):
    out = get_activity_feed(db)
    assert out["pagination"]["total"] == 4
    assert len(out["items"]) == 4

    by_type = {i["entity_type"]: i for i in out["items"]}

    # complaint: live label + href + diffed change (noise field skipped) + summary
    comp = by_type["complaint"]
    assert comp["entity_label"] == "Complaint CMP-1042"
    assert comp["entity_href"] == f"/complaint-management/complaints/{db.info['ids']['complaint']}"
    assert comp["action"] == "updated"
    assert comp["changes"] == [{"field": "Status", "from": "pending", "to": "resolved"}]
    assert comp["summary"] == "Status: pending → resolved"
    assert comp["actor_name"] == "Jane Tan"
    assert comp["trace_id"] == "trace-abc"

    # order create: plural stored type normalised to FE 'order', no changes
    order = next(
        i for i in out["items"] if i["entity_id"] == db.info["ids"]["order"]
    )
    assert order["entity_type"] == "order"
    assert order["entity_label"] == "Order SO-5567"
    assert order["action"] == "created"
    assert order["changes"] == []

    # user update with null actor -> "System"
    user = by_type["user"]
    assert user["entity_label"] == "User Jane Tan"
    assert user["actor_name"] == "System"

    # actors list = distinct real users only (System/null excluded)
    assert out["actors"] == [{"id": db.info["ids"]["actor"], "name": "Jane Tan"}]


def test_deleted_row_falls_back_to_snapshot_label(db):
    out = get_activity_feed(db, action="deleted")
    assert out["pagination"]["total"] == 1
    item = out["items"][0]
    assert item["entity_label"] == "Order SO-5560 (deleted)"
    assert item["entity_href"] is None
    assert item["action"] == "deleted"


def test_entity_type_filter_narrows(db):
    out = get_activity_feed(db, entity_types=["complaint"])
    assert out["pagination"]["total"] == 1
    assert out["items"][0]["entity_type"] == "complaint"


def test_action_filter_maps_created_to_insert_and_create(db):
    out = get_activity_feed(db, action="created")
    assert out["pagination"]["total"] == 1
    assert out["items"][0]["action"] == "created"


def test_user_filter_narrows_but_actors_stay_populated(db):
    out = get_activity_feed(db, user_id=db.info["ids"]["actor"])
    # 3 of 4 rows have this actor (the users UPDATE has null actor)
    assert out["pagination"]["total"] == 3
    # Dropdown still lists the actor even though we filtered on them.
    assert out["actors"] == [{"id": db.info["ids"]["actor"], "name": "Jane Tan"}]


def test_date_filter_narrows(db):
    # All seeded rows are on 2026-06-30.
    assert get_activity_feed(db, date_from="2026-06-30", date_to="2026-06-30")["pagination"]["total"] == 4
    assert get_activity_feed(db, date_from="2026-07-01")["pagination"]["total"] == 0


def test_trace_id_filter_narrows(db):
    out = get_activity_feed(db, trace_id="trace-abc")
    assert out["pagination"]["total"] == 1
    assert out["items"][0]["trace_id"] == "trace-abc"


def test_q_matches_description(db):
    out = get_activity_feed(db, q="deleted")
    assert out["pagination"]["total"] == 1
    assert out["items"][0]["description"] == "Order deleted"


# --------------------------------------------------------------------------- #
# Endpoint wiring + auth deny                                                  #
# --------------------------------------------------------------------------- #
def _client():
    from unittest.mock import MagicMock
    from fastapi.testclient import TestClient
    from app.main import app
    from app.dependencies import get_db, get_current_user, get_current_user_or_api_key
    import app.api.v1.audit.activity as mod

    def _fake_db():
        yield MagicMock()

    _user = {"id": "admin"}
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: _user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: _user
    return TestClient(app), app, mod


def test_endpoint_returns_feed(monkeypatch):
    client, app, mod = _client()
    try:
        monkeypatch.setattr(
            mod,
            "get_activity_feed",
            lambda db, **kw: {
                "items": [{"id": "1", "entity_type": "complaint", "entity_label": "Complaint CMP-1", "action": "updated"}],
                "actors": [{"id": "u1", "name": "Jane Tan"}],
                "pagination": {"page": 1, "limit": 50, "total": 1},
            },
        )
        r = client.get("/api/v1/audit/activity")
        assert r.status_code == 200
        body = r.json()
        assert body["pagination"]["total"] == 1
        assert body["items"][0]["entity_label"] == "Complaint CMP-1"
        assert body["actors"][0]["name"] == "Jane Tan"
    finally:
        app.dependency_overrides.clear()


def test_endpoint_forwards_csv_and_repeatable_entity_types(monkeypatch):
    client, app, mod = _client()
    captured = {}
    try:
        def _spy(db, **kw):
            captured.update(kw)
            return {"items": [], "actors": [], "pagination": {"page": 1, "limit": 50, "total": 0}}

        monkeypatch.setattr(mod, "get_activity_feed", _spy)
        r = client.get("/api/v1/audit/activity?entity_type=complaint,order&entity_type=user")
        assert r.status_code == 200
        assert captured["entity_types"] == ["complaint", "order", "user"]
    finally:
        app.dependency_overrides.clear()


def test_endpoint_requires_auth():
    from fastapi import HTTPException
    from app.main import app
    from app.dependencies import get_current_user_or_api_key

    def _deny():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user_or_api_key] = _deny
    try:
        from fastapi.testclient import TestClient
        r = TestClient(app).get("/api/v1/audit/activity")
        assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()
