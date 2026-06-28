"""HoD coverage: assign on behalf of team members, team list, revoke by id.

Service-level (the route layer gates with require_permission, covered by test_rbac).
Verifies scope-B for the ACTOR (both coverer + covered), created_by_id audit, the
coverer notification, the team list scoping, and deactivate_by_id authorization.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import JSON, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.access import Team, TeamMember
from app.models.notification import (
    Notification,
    NotificationDelivery,
    NotificationSubscription,
)
from app.models.lookup import LookupBinding  # listener-table workaround
from app.models.user import User
from app.services.coverage_subscription_service import CoverageSubscriptionService
from app.services.error_handler import AppException


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for col in Notification.__table__.columns:
        if col.name == "data":
            col.type = JSON()
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Team.__table__,
            TeamMember.__table__,
            NotificationSubscription.__table__,
            Notification.__table__,
            NotificationDelivery.__table__,
            LookupBinding.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _user(db, name, **kw) -> str:
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{name}@x.com", name=name, status="active", **kw))
    db.commit()
    return uid


def _team(db, name, parent_id=None) -> str:
    tid = str(uuid.uuid4())
    db.add(Team(id=tid, name=name, parent_team_id=parent_id))
    db.commit()
    return tid


def _member(db, team_id, user_id):
    db.add(TeamMember(id=str(uuid.uuid4()), team_id=team_id, user_id=user_id))
    db.commit()


def _hod_with_team(db):
    """HoD in a parent team; A and B in a child team -> both in HoD scope-B."""
    parent = _team(db, "Dept")
    child = _team(db, "Squad", parent_id=parent)
    hod = _user(db, "hod")
    a = _user(db, "alice")
    b = _user(db, "bob")
    _member(db, parent, hod)
    _member(db, child, a)
    _member(db, child, b)
    return hod, a, b


# ---- assign_coverage ------------------------------------------------------

def test_assign_creates_row_with_audit(db):
    hod, a, b = _hod_with_team(db)
    sub = CoverageSubscriptionService(db).assign_coverage(hod, a, b, redirect_assignments=True)
    assert sub.subscriber_id == a and sub.target_user_id == b
    assert sub.created_by_id == hod  # B4: audit
    assert bool(sub.redirect_assignments) is True


def test_assign_notifies_coverer(db):
    hod, a, b = _hod_with_team(db)
    CoverageSubscriptionService(db).assign_coverage(hod, a, b)
    # B7: coverer A gets an in-app notice.
    notes = db.query(Notification).filter(Notification.user_id == a).all()
    assert len(notes) == 1
    assert "coverage" in notes[0].title.lower()


def test_assign_coverer_out_of_scope_rejected(db):
    hod, a, b = _hod_with_team(db)
    outsider = _user(db, "outsider")
    _member(db, _team(db, "Far"), outsider)
    with pytest.raises(AppException):  # B6: coverer not in scope
        CoverageSubscriptionService(db).assign_coverage(hod, outsider, b)


def test_assign_target_out_of_scope_rejected(db):
    hod, a, b = _hod_with_team(db)
    outsider = _user(db, "outsider")
    _member(db, _team(db, "Far"), outsider)
    with pytest.raises(AppException):  # B6: covered not in scope
        CoverageSubscriptionService(db).assign_coverage(hod, a, outsider)


def test_assign_self_coverage_rejected(db):
    hod, a, _b = _hod_with_team(db)
    with pytest.raises(AppException):
        CoverageSubscriptionService(db).assign_coverage(hod, a, a)


def test_assign_redirect_routing_active(db):
    # B8: a HoD-created redirect coverage drives active_coverer_for.
    hod, a, b = _hod_with_team(db)
    CoverageSubscriptionService(db).assign_coverage(hod, a, b, redirect_assignments=True)
    assert CoverageSubscriptionService(db).active_coverer_for(b) == a


# ---- list_team_subscriptions ----------------------------------------------

def test_team_list_scoped_to_actor(db):
    hod, a, b = _hod_with_team(db)
    svc = CoverageSubscriptionService(db)
    svc.assign_coverage(hod, a, b)
    rows = svc.list_team_subscriptions(hod)
    assert len(rows) == 1
    r = rows[0]
    assert r["subscriber_name"] == "alice" and r["target_user_name"] == "bob"
    assert r["assigned_by_hod"] is True and r["created_by_name"] == "hod"


def test_team_list_excludes_out_of_scope(db):
    hod, a, b = _hod_with_team(db)
    # A separate, unrelated coverage between two outsiders.
    o1 = _user(db, "o1")
    o2 = _user(db, "o2")
    far = _team(db, "Far")
    _member(db, far, o1)
    _member(db, far, o2)
    db.add(
        NotificationSubscription(
            id=str(uuid.uuid4()), subscriber_id=o1, target_user_id=o2, is_active=True
        )
    )
    db.commit()
    rows = CoverageSubscriptionService(db).list_team_subscriptions(hod)
    assert all(r["subscriber_id"] != o1 for r in rows)


# ---- deactivate_by_id -----------------------------------------------------

def test_revoke_by_owner(db):
    hod, a, b = _hod_with_team(db)
    sub = CoverageSubscriptionService(db).assign_coverage(hod, a, b)
    # A owns the coverage (subscriber) -> can revoke even without manage perm.
    CoverageSubscriptionService(db).deactivate_by_id(sub.id, a, can_manage=False)
    assert db.query(NotificationSubscription).count() == 0


def test_revoke_by_hod_in_scope(db):
    hod, a, b = _hod_with_team(db)
    sub = CoverageSubscriptionService(db).assign_coverage(hod, a, b)
    CoverageSubscriptionService(db).deactivate_by_id(sub.id, hod, can_manage=True)
    assert db.query(NotificationSubscription).count() == 0


def test_revoke_forbidden_without_owner_or_manage(db):
    hod, a, b = _hod_with_team(db)
    stranger = _user(db, "stranger")
    _member(db, _team(db, "Far"), stranger)
    sub = CoverageSubscriptionService(db).assign_coverage(hod, a, b)
    with pytest.raises(AppException):
        CoverageSubscriptionService(db).deactivate_by_id(sub.id, stranger, can_manage=True)
    assert db.query(NotificationSubscription).count() == 1
