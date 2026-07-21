"""Coverage subscriptions: CRUD, scope-B, expiry, and assignment/escalation fan-out."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.models.access import Team, TeamMember
from app.models.notification import (
    Notification,
    NotificationDelivery,
    NotificationSubscription,
)
from app.models.user import User
from app.services.coverage_subscription_service import (
    CoverageSubscriptionService,
    fan_out_coverage_copies,
)
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


# ---- CRUD / scope ---------------------------------------------------------

def test_subscribe_creates_active_row(db):
    me = _user(db, "me")
    target = _user(db, "charissa")
    team = _team(db, "T")
    _member(db, team, me)
    _member(db, team, target)
    sub = CoverageSubscriptionService(db).subscribe(me, target)
    assert sub.is_active is True
    assert sub.subscriber_id == me and sub.target_user_id == target


def test_self_subscription_rejected(db):
    me = _user(db, "me")
    team = _team(db, "T")
    _member(db, team, me)
    with pytest.raises(AppException):
        CoverageSubscriptionService(db).subscribe(me, me)


def test_subscribe_scope_b_enforced(db):
    me = _user(db, "me")
    outsider = _user(db, "outsider")
    _member(db, _team(db, "Mine"), me)
    _member(db, _team(db, "Other"), outsider)
    with pytest.raises(AppException):
        CoverageSubscriptionService(db).subscribe(me, outsider)


def test_unsubscribe_hard_deletes(db):
    me = _user(db, "me")
    target = _user(db, "t")
    team = _team(db, "T")
    _member(db, team, me)
    _member(db, team, target)
    svc = CoverageSubscriptionService(db)
    svc.subscribe(me, target)
    svc.unsubscribe(me, target)
    row = (
        db.query(NotificationSubscription)
        .filter(NotificationSubscription.subscriber_id == me)
        .first()
    )
    assert row is None  # hard delete: row removed, never lingers as "Inactive"


def test_expiry_deactivates_past_rows(db):
    me = _user(db, "me")
    target = _user(db, "t")
    team = _team(db, "T")
    _member(db, team, me)
    _member(db, team, target)
    svc = CoverageSubscriptionService(db)
    svc.subscribe(me, target, expires_at=datetime.utcnow() - timedelta(days=1))
    count = svc.deactivate_expired_subscriptions()
    assert count == 1
    assert svc.active_subscribers_for(target) == []


def test_active_subscribers_excludes_expired_and_inactive(db):
    target = _user(db, "t")
    a = _user(db, "a")
    b = _user(db, "b")
    c = _user(db, "c")
    team = _team(db, "T")
    for u in (target, a, b, c):
        _member(db, team, u)
    svc = CoverageSubscriptionService(db)
    svc.subscribe(a, target)  # active
    svc.subscribe(b, target, expires_at=datetime.utcnow() - timedelta(hours=1))  # expired
    svc.subscribe(c, target)
    svc.unsubscribe(c, target)  # inactive
    assert set(svc.active_subscribers_for(target)) == {a}


# ---- fan-out --------------------------------------------------------------

def _make_sub(db, subscriber, target):
    db.add(
        NotificationSubscription(
            id=str(uuid.uuid4()),
            subscriber_id=subscriber,
            target_user_id=target,
            is_active=True,
        )
    )
    db.commit()


def _fanout(db, target, actor=None):
    fan_out_coverage_copies(
        db,
        target_user_id=target,
        actor_user_id=actor,
        notification_type="form_sla",
        title="New SLA assignment",
        body="X assigned",
        data={},
        source_entity_type="form_sla_tracking",
        source_entity_id="tr-1",
        event_type="assigned",
        email_pref_attr="notify_email_on_assignment",
        whatsapp_pref_attr="notify_whatsapp_on_assignment",
    )


def test_fan_out_copies_to_active_subscriber(db):
    target = _user(db, "charissa")
    cover = _user(db, "cover")
    _make_sub(db, cover, target)
    _fanout(db, target)
    notes = db.query(Notification).filter(Notification.user_id == cover).all()
    assert len(notes) == 1
    assert "covering for charissa" in notes[0].title.lower()


def test_fan_out_skips_when_subscriber_is_assignee(db):
    # Subscriber covers the target but the target IS the assignee -> no copy to target.
    target = _user(db, "charissa")
    _make_sub(db, target, target)  # would be rejected by subscribe(), but force the row
    _fanout(db, target)
    # No self-copy (dedup).
    assert db.query(Notification).filter(Notification.user_id == target).count() == 0


def test_fan_out_skips_actor(db):
    target = _user(db, "charissa")
    actor = _user(db, "actor")
    _make_sub(db, actor, target)
    _fanout(db, target, actor=actor)
    assert db.query(Notification).filter(Notification.user_id == actor).count() == 0


def test_fan_out_email_gated_by_subscriber_toggle(db):
    target = _user(db, "charissa")
    # cover has email-on-assignment OFF -> no email delivery, in-app still fires.
    cover = _user(db, "cover", notify_email_on_assignment=False)
    _make_sub(db, cover, target)
    _fanout(db, target)
    note = db.query(Notification).filter(Notification.user_id == cover).first()
    assert note is not None
    channels = {
        d.channel
        for d in db.query(NotificationDelivery)
        .filter(NotificationDelivery.notification_id == note.id)
        .all()
    }
    assert "in_app" in channels
    assert "email" not in channels


def test_fan_out_inactive_subscriber_skipped(db):
    target = _user(db, "charissa")
    cover = _user(db, "cover")
    db.add(
        NotificationSubscription(
            id=str(uuid.uuid4()),
            subscriber_id=cover,
            target_user_id=target,
            is_active=False,
        )
    )
    db.commit()
    _fanout(db, target)
    assert db.query(Notification).filter(Notification.user_id == cover).count() == 0
