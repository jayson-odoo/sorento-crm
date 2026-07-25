"""Form handling-lock ("I'm handling this") — Phase 2 ROUTE-layer tests.

Complements tests/test_form_handling_lock.py (service + guard, 25 tests) by
exercising the three new FastAPI endpoints through a TestClient with real auth
dependency resolution (PLAN-form-handling-lock §8 / §12 P2-2..P2-5, P2-17):

  POST /api/v1/sla-management/form-sla-tracking/{id}/claim
  POST /api/v1/sla-management/form-sla-tracking/{id}/take-over
  POST /api/v1/sla-management/form-sla-tracking/{id}/release
  GET  /api/v1/sla-management/form-sla-tracking?source_entity_type=&source_entity_id=

Covers per endpoint: eligible happy path (200 + body shape incl. handled_by_*),
non-eligible -> 403, unauth -> 401, take-over wrong/null expected -> 409, release
by non-holder -> 403. Plus the GET serializer's FE-resolver fields.

Runs against an in-memory sqlite bind (CLAUDE.md "sqlite pytest fixtures" gotcha):
pg ``UUID(as_uuid=False)`` works as-is; JSONB columns swapped to JSON; the
AgentTeam partial-unique indexes dropped; ``lookup_bindings`` created so a
globally-registered lookup validator can't fault on inserts during a full-suite
run. ``UserPermissionService.get_user_role_slugs`` is monkeypatched (the GET
serializer's ``viewer_is_admin`` reads it, and no role tables are seeded here).

Run: venv/bin/pytest tests/test_form_handling_lock_routes.py -q
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models.access import (
    AccessAgent,
    AgentTeam,
    Team,
    TeamMember,
)
from app.models.sla import (
    ConversationSLAEventLog,
    ConversationSLATracking,
    HANDLING_CLAIMED,
    HANDLING_RELEASED,
    HANDLING_TAKEN_OVER,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import SystemSetting, User
from tests._pg_fixture import blank_session


BASE = "/api/v1/sla-management/form-sla-tracking"


# --------------------------------------------------------------------------- #
# blank Postgres schema (mirrors tests/test_form_handling_lock.py)            #
# --------------------------------------------------------------------------- #
@pytest.fixture
def db():
    with blank_session() as s:
        yield s


@pytest.fixture
def seed(db):
    policy_id = str(uuid.uuid4())
    db.add(SLAPolicy(id=policy_id, code="FORM", name="Form"))
    for lvl in (1, 2, 3):
        db.add(
            SLAPolicyTier(
                id=str(uuid.uuid4()),
                policy_id=policy_id,
                tier_level=lvl,
                tier_name=f"Tier {lvl}",
                response_hours=4,
                resolution_hours=24,
            )
        )
    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code="complaint", name="Complaint"))

    team1 = str(uuid.uuid4())
    team2 = str(uuid.uuid4())
    db.add(Team(id=team1, name="Tier 1"))
    db.add(Team(id=team2, name="Tier 2"))
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=agent_id, code="cs", team_id=team1, tier=1))
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=agent_id, code="cs", team_id=team2, tier=2))

    users = {}
    for key, email in (
        ("assignee", "assignee@t.com"),
        ("member_a", "a@t.com"),
        ("member_b", "b@t.com"),
        ("outsider", "out@t.com"),
        ("admin", "admin@t.com"),
    ):
        uid = str(uuid.uuid4())
        db.add(User(id=uid, email=email, name=key, status="ACTIVE"))
        users[key] = uid
    for uid in (users["assignee"], users["member_a"]):
        db.add(TeamMember(id=str(uuid.uuid4()), team_id=team1, user_id=uid))
    db.add(TeamMember(id=str(uuid.uuid4()), team_id=team2, user_id=users["member_b"]))

    db.add(
        SystemSetting(
            id=str(uuid.uuid4()),
            name="Co",
            handling_lock_enabled_types="complaint",
        )
    )
    db.commit()
    return {"policy_id": policy_id, "agent_id": agent_id, "users": users}


def _tracker(db, seed, *, tier=2, resolved=False, entity="complaint", handled_by=None):
    now = datetime.utcnow()
    t = ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=seed["policy_id"],
        current_tier=tier,
        initiated_at=now - timedelta(hours=5),
        current_tier_started_at=now - timedelta(hours=2),
        due_at=now + timedelta(hours=4),
        due_at_resolution=now + timedelta(hours=20),
        is_resolved=resolved,
        source_entity_type=entity,
        source_entity_id=str(uuid.uuid4()),
        agent_id=seed["agent_id"],
        team_set_code="cs",
        assigned_to_id=seed["users"]["assignee"],
        handled_by_id=handled_by,
        handled_at=now if handled_by else None,
    )
    db.add(t)
    db.commit()
    return t


# --------------------------------------------------------------------------- #
# TestClient wiring — dynamic actor + no-op notify + patched role slugs        #
# --------------------------------------------------------------------------- #
_ACTOR: dict = {"id": None}


@pytest.fixture(autouse=True)
def _no_notify(monkeypatch):
    """Handling notify fan-out is best-effort; stub it so route tests don't touch
    real notification/whatsapp infra (covered in the notify/outbox test file)."""
    from app.services.notification_service import NotificationService

    monkeypatch.setattr(
        NotificationService,
        "create_with_channel_preferences",
        lambda self, user_id, **kw: None,
    )
    yield


@pytest.fixture(autouse=True)
def _patch_roles(monkeypatch, seed):
    """GET serializer computes ``viewer_is_admin`` via role slugs; only the seeded
    admin user is an admin. No role tables are created in this fixture."""
    from app.services.user_service import UserPermissionService

    admin_id = seed["users"]["admin"]
    monkeypatch.setattr(
        UserPermissionService,
        "get_user_role_slugs",
        lambda self, uid: ({"admin"} if str(uid) == admin_id else set()),
    )
    yield


@pytest.fixture
def client(db):
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def anon_client(db):
    """No auth override — the real get_current_user runs, rejecting anon requests
    before the route body."""
    from app.main import app
    from app.database import get_db

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _act_as(seed, key):
    _ACTOR["id"] = seed["users"][key]


def _events(db, tid, etype):
    return (
        db.query(ConversationSLAEventLog)
        .filter(
            ConversationSLAEventLog.sla_tracking_id == tid,
            ConversationSLAEventLog.event_type == etype,
        )
        .all()
    )


# =========================================================================== #
# claim                                                                        #
# =========================================================================== #
def test_claim_happy_200_body(client, db, seed):  # P2-2
    t = _tracker(db, seed, tier=2)
    _act_as(seed, "member_a")
    r = client.post(f"{BASE}/{t.id}/claim")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["handled_by_id"] == seed["users"]["member_a"]
    assert body["handled_by_name"] == "member_a"
    assert body["handled_at"] is not None
    assert len(_events(db, t.id, HANDLING_CLAIMED)) == 1


def test_claim_non_eligible_403(client, db, seed):  # P2-3
    t = _tracker(db, seed, tier=2)
    _act_as(seed, "outsider")
    r = client.post(f"{BASE}/{t.id}/claim")
    assert r.status_code == 403, r.text


def test_claim_unauth_401(anon_client, db, seed):  # P2-17 auth-deny
    t = _tracker(db, seed, tier=2)
    r = anon_client.post(f"{BASE}/{t.id}/claim")
    assert r.status_code in (401, 403), r.text


def test_claim_concurrent_409(client, db, seed):  # P2-2
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    _act_as(seed, "member_b")
    r = client.post(f"{BASE}/{t.id}/claim")
    assert r.status_code == 409, r.text


# =========================================================================== #
# take-over                                                                    #
# =========================================================================== #
def test_take_over_happy_200_body(client, db, seed):  # P2-4
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    _act_as(seed, "member_b")
    r = client.post(
        f"{BASE}/{t.id}/take-over",
        json={"expected_handler_id": seed["users"]["member_a"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["handled_by_id"] == seed["users"]["member_b"]
    assert body["handled_by_name"] == "member_b"
    assert body["handled_at"] is not None
    assert body["previous_handler_id"] == seed["users"]["member_a"]
    assert len(_events(db, t.id, HANDLING_TAKEN_OVER)) == 1


def test_take_over_wrong_expected_409(client, db, seed):  # P2-4
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    _act_as(seed, "member_b")
    r = client.post(
        f"{BASE}/{t.id}/take-over",
        json={"expected_handler_id": seed["users"]["outsider"]},  # wrong holder
    )
    assert r.status_code == 409, r.text
    db.refresh(t)
    assert t.handled_by_id == seed["users"]["member_a"]  # unchanged


def test_take_over_null_expected_409(client, db, seed):  # P2-4
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    _act_as(seed, "member_b")
    r = client.post(f"{BASE}/{t.id}/take-over", json={})  # expected_handler_id null
    assert r.status_code == 409, r.text
    db.refresh(t)
    assert t.handled_by_id == seed["users"]["member_a"]


def test_take_over_non_eligible_403(client, db, seed):  # P2-4 auth-deny
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    _act_as(seed, "outsider")
    r = client.post(
        f"{BASE}/{t.id}/take-over",
        json={"expected_handler_id": seed["users"]["member_a"]},
    )
    assert r.status_code == 403, r.text


def test_take_over_unauth_401(anon_client, db, seed):  # P2-17 auth-deny
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    r = anon_client.post(
        f"{BASE}/{t.id}/take-over",
        json={"expected_handler_id": seed["users"]["member_a"]},
    )
    assert r.status_code in (401, 403), r.text


# =========================================================================== #
# release                                                                      #
# =========================================================================== #
def test_release_holder_200(client, db, seed):  # P2-5
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    _act_as(seed, "member_a")
    r = client.post(f"{BASE}/{t.id}/release")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["handled_by_id"] is None
    assert body["handled_by_name"] is None
    assert body["handled_at"] is None
    assert len(_events(db, t.id, HANDLING_RELEASED)) == 1


def test_release_non_holder_403(client, db, seed):  # P2-5
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    _act_as(seed, "member_b")
    r = client.post(f"{BASE}/{t.id}/release")
    assert r.status_code == 403, r.text


def test_release_unauth_401(anon_client, db, seed):  # P2-17 auth-deny
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    r = anon_client.post(f"{BASE}/{t.id}/release")
    assert r.status_code in (401, 403), r.text


# =========================================================================== #
# GET serializer — the fields the FE state resolver consumes                   #
# =========================================================================== #
def test_get_includes_fe_resolver_fields_unclaimed(client, db, seed):  # P2-2/P2-14 contract
    t = _tracker(db, seed, tier=2)
    _act_as(seed, "member_a")
    r = client.get(
        BASE,
        params={
            "source_entity_type": "complaint",
            "source_entity_id": t.source_entity_id,
        },
    )
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert len(rows) == 1
    row = rows[0]
    for key in (
        "flag_enabled",
        "viewer_eligible",
        "viewer_is_admin",
        "handled_by_id",
        "handled_by_name",
        "handled_at",
    ):
        assert key in row, f"missing {key} in GET serializer"
    assert row["flag_enabled"] is True
    assert row["viewer_eligible"] is True  # member_a is in the tier-1 chain
    assert row["viewer_is_admin"] is False
    assert row["handled_by_id"] is None
    assert row["handled_by_name"] is None
    assert row["handled_at"] is None


def test_get_reflects_holder_and_viewer_flags(client, db, seed):  # P2-6 FE inputs
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    _act_as(seed, "outsider")  # not in the team chain
    r = client.get(
        BASE,
        params={
            "source_entity_type": "complaint",
            "source_entity_id": t.source_entity_id,
        },
    )
    assert r.status_code == 200, r.text
    row = r.json()["data"][0]
    assert row["handled_by_id"] == seed["users"]["member_a"]
    assert row["handled_by_name"] == "member_a"
    assert row["handled_at"] is not None
    assert row["viewer_eligible"] is False
    assert row["viewer_is_admin"] is False


def test_get_admin_viewer_flag(client, db, seed):  # P2-6 FE inputs
    t = _tracker(db, seed, tier=2)
    _act_as(seed, "admin")
    r = client.get(
        BASE,
        params={
            "source_entity_type": "complaint",
            "source_entity_id": t.source_entity_id,
        },
    )
    assert r.status_code == 200, r.text
    row = r.json()["data"][0]
    assert row["viewer_is_admin"] is True


def test_get_rejects_non_form_type_422(client, db, seed):  # scope guard
    _act_as(seed, "member_a")
    r = client.get(
        BASE,
        params={"source_entity_type": "conversation", "source_entity_id": str(uuid.uuid4())},
    )
    assert r.status_code == 422, r.text
