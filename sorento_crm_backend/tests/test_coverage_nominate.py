"""Self-service coverer nomination: a user nominates a scope-B colleague to cover
THEM while away — no manage_team permission. Plus the covered party may list + revoke
their own coverage.

Service-level (routes gate only get_current_user, no permission). Mirrors the
Postgres fixture pattern in test_coverage_hod_assign.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.access import Team, TeamMember
from app.models.notification import (
    Notification,
    NotificationDelivery,
    NotificationSubscription,
)
from app.models.user import User
from app.services.coverage_subscription_service import CoverageSubscriptionService
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        # descendant_team_ids runs a raw-SQL recursive CTE on an unqualified
        # `teams`, which schema_translate_map does not rewrite -- see the note in
        # test_coverage_hod_assign. Align search_path with the blank schema.
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


def _user(db, name, **kw) -> str:
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{name}@x.com", name=name, status="ACTIVE", **kw))
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


def _two_teammates(db):
    """me + a colleague in the same team -> colleague is in my scope-B."""
    team = _team(db, "Squad")
    me = _user(db, "me")
    mate = _user(db, "mate")
    _member(db, team, me)
    _member(db, team, mate)
    return me, mate


# ---- nominate_coverer -----------------------------------------------------

def test_nominate_creates_row_with_self_audit(db):
    me, mate = _two_teammates(db)
    sub = CoverageSubscriptionService(db).nominate_coverer(me, mate, redirect_assignments=True)
    # The colleague is the coverer (subscriber); I'm the covered party.
    assert sub.subscriber_id == mate and sub.target_user_id == me
    assert sub.created_by_id == me  # self-arranged
    assert bool(sub.redirect_assignments) is True


def test_nominate_notifies_coverer(db):
    me, mate = _two_teammates(db)
    CoverageSubscriptionService(db).nominate_coverer(me, mate)
    notes = db.query(Notification).filter(Notification.user_id == mate).all()
    assert len(notes) == 1
    assert "coverage" in notes[0].title.lower()


def test_nominate_redirect_routing_active(db):
    me, mate = _two_teammates(db)
    CoverageSubscriptionService(db).nominate_coverer(me, mate, redirect_assignments=True)
    assert CoverageSubscriptionService(db).active_coverer_for(me) == mate


def test_nominate_coverer_out_of_scope_rejected(db):
    me, _mate = _two_teammates(db)
    outsider = _user(db, "outsider")
    _member(db, _team(db, "Far"), outsider)
    with pytest.raises(AppException):
        CoverageSubscriptionService(db).nominate_coverer(me, outsider)


def test_nominate_self_as_coverer_rejected(db):
    me, _mate = _two_teammates(db)
    with pytest.raises(AppException):
        CoverageSubscriptionService(db).nominate_coverer(me, me)


# ---- list_coverage_for_me -------------------------------------------------

def test_list_coverage_for_me_returns_who_covers_me(db):
    me, mate = _two_teammates(db)
    svc = CoverageSubscriptionService(db)
    svc.nominate_coverer(me, mate)
    rows = svc.list_coverage_for_me(me)
    assert len(rows) == 1
    r = rows[0]
    assert r["subscriber_id"] == mate and r["subscriber_name"] == "mate"
    assert r["target_user_id"] == me


def test_list_coverage_for_me_excludes_coverage_i_give(db):
    me, mate = _two_teammates(db)
    svc = CoverageSubscriptionService(db)
    # I cover mate (I'm the subscriber) -> must NOT appear in "who covers me".
    svc.subscribe(me, mate)
    assert svc.list_coverage_for_me(me) == []


# ---- deactivate_by_id: covered party may revoke ---------------------------

def test_covered_party_can_revoke_own_coverage(db):
    me, mate = _two_teammates(db)
    svc = CoverageSubscriptionService(db)
    sub = svc.nominate_coverer(me, mate)
    # I'm the covered party (not the subscriber), no manage perm -> still allowed.
    svc.deactivate_by_id(sub.id, me, can_manage=False)
    assert db.query(NotificationSubscription).count() == 0


def test_uninvolved_user_cannot_revoke(db):
    me, mate = _two_teammates(db)
    stranger = _user(db, "stranger")
    _member(db, _team(db, "Far"), stranger)
    svc = CoverageSubscriptionService(db)
    sub = svc.nominate_coverer(me, mate)
    with pytest.raises(AppException):
        svc.deactivate_by_id(sub.id, stranger, can_manage=False)
    assert db.query(NotificationSubscription).count() == 1
