"""Coverage redirects assignment/escalation (per-coverage redirect_assignments toggle).

Covers PLAN-coverage-redirect-assignment.md:
- active_coverer_for: only redirect=True, non-expired, single.
- subscribe mode matrix: self-coverage, sole-redirect-coverer enforcement, multiple
  notify-only allowed, same-subscriber upsert.
- resolve_assignee_with_coverage: swap / passthrough / notify-only passthrough / one-hop
  / best-effort on falsy.
- RR fairness: cursor still advances to the COVERED user; only the returned dict swaps.
- expired coverage = no redirect (forward-only revert).
- notify-only unchanged: still fans out via active_subscribers_for; active_coverer_for None.

Most routing surfaces (form _start_for_config / _escalate_tracker, conversation
get_escalation_assignee_for_tier, reassign) apply this same helper right before
``assigned_to_id`` is set; they are exercised here via the helper (and, for RR, via the
real get_next_assignee → resolve chain) - see the harness note at the bottom of the file.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.access import (
    AccessAgent,
    AgentTeam,
    AgentTeamRoundRobinCursor,
    Team,
    TeamMember,
)
from app.models.notification import (
    Notification,
    NotificationDelivery,
    NotificationSubscription,
)
from app.models.user import User
from app.services.coverage_subscription_service import (
    CoverageSubscriptionService,
    coverage_note,
    resolve_assignee_with_coverage,
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
    db.add(User(id=uid, email=f"{name}@x.com", name=name, status="ACTIVE", **kw))
    db.commit()
    return uid


def _team(db, name, parent_id=None) -> str:
    tid = str(uuid.uuid4())
    db.add(Team(id=tid, name=name, parent_team_id=parent_id))
    db.commit()
    return tid


def _member(db, team_id, user_id, **kw):
    db.add(TeamMember(id=str(uuid.uuid4()), team_id=team_id, user_id=user_id, **kw))
    db.commit()


def _raw_sub(db, subscriber, target, *, redirect=False, is_active=True, expires_at=None,
             created_at=None):
    """Insert a NotificationSubscription directly, bypassing subscribe() enforcement,
    so tests can construct arbitrary coverage states (including ones subscribe() rejects)."""
    sub = NotificationSubscription(
        id=str(uuid.uuid4()),
        subscriber_id=subscriber,
        target_user_id=target,
        is_active=is_active,
        redirect_assignments=redirect,
        expires_at=expires_at,
    )
    db.add(sub)
    db.commit()
    if created_at is not None:
        setattr(sub, "created_at", created_at)
        db.commit()
    return sub


# ===========================================================================
# 1. active_coverer_for
# ===========================================================================

def test_active_coverer_for_returns_on_coverer(db):
    target = _user(db, "target")
    cover = _user(db, "cover")
    _raw_sub(db, cover, target, redirect=True)
    assert CoverageSubscriptionService(db).active_coverer_for(target) == cover


def test_active_coverer_for_none_when_notify_only(db):
    target = _user(db, "target")
    cover = _user(db, "cover")
    _raw_sub(db, cover, target, redirect=False)  # notify-only
    assert CoverageSubscriptionService(db).active_coverer_for(target) is None


def test_active_coverer_for_excludes_expired(db):
    target = _user(db, "target")
    cover = _user(db, "cover")
    _raw_sub(db, cover, target, redirect=True,
             expires_at=datetime.utcnow() - timedelta(hours=1))
    assert CoverageSubscriptionService(db).active_coverer_for(target) is None


def test_active_coverer_for_none_when_no_coverage(db):
    target = _user(db, "target")
    assert CoverageSubscriptionService(db).active_coverer_for(target) is None


def test_active_coverer_for_future_expiry_still_active(db):
    target = _user(db, "target")
    cover = _user(db, "cover")
    _raw_sub(db, cover, target, redirect=True,
             expires_at=datetime.utcnow() + timedelta(days=1))
    assert CoverageSubscriptionService(db).active_coverer_for(target) == cover


# ===========================================================================
# 2. subscribe mode matrix
# ===========================================================================

def test_subscribe_self_coverage_422(db):
    me = _user(db, "me")
    _member(db, _team(db, "T"), me)
    with pytest.raises(AppException) as ei:
        CoverageSubscriptionService(db).subscribe(me, me, redirect_assignments=True)
    assert ei.value.status_code == 422


def test_subscribe_add_on_when_other_on_coverage_exists_409(db):
    target = _user(db, "target")
    a = _user(db, "a")
    b = _user(db, "b")
    team = _team(db, "T")
    for u in (target, a, b):
        _member(db, team, u)
    CoverageSubscriptionService(db).subscribe(a, target, redirect_assignments=True)
    with pytest.raises(AppException) as ei:
        CoverageSubscriptionService(db).subscribe(b, target, redirect_assignments=True)
    assert ei.value.status_code == 409


def test_subscribe_add_on_when_other_off_coverage_exists_409(db):
    # Decision 3: adding ON rejects if ANY active coverage exists (ON or OFF) by another.
    target = _user(db, "target")
    a = _user(db, "a")
    b = _user(db, "b")
    team = _team(db, "T")
    for u in (target, a, b):
        _member(db, team, u)
    CoverageSubscriptionService(db).subscribe(a, target, redirect_assignments=False)
    with pytest.raises(AppException) as ei:
        CoverageSubscriptionService(db).subscribe(b, target, redirect_assignments=True)
    assert ei.value.status_code == 409


def test_subscribe_add_off_when_on_coverage_exists_409(db):
    target = _user(db, "target")
    a = _user(db, "a")
    b = _user(db, "b")
    team = _team(db, "T")
    for u in (target, a, b):
        _member(db, team, u)
    CoverageSubscriptionService(db).subscribe(a, target, redirect_assignments=True)
    with pytest.raises(AppException) as ei:
        CoverageSubscriptionService(db).subscribe(b, target, redirect_assignments=False)
    assert ei.value.status_code == 409


def test_subscribe_add_off_when_only_off_coverage_allowed(db):
    # Multiple notify-only coverers per target are allowed.
    target = _user(db, "target")
    a = _user(db, "a")
    b = _user(db, "b")
    team = _team(db, "T")
    for u in (target, a, b):
        _member(db, team, u)
    svc = CoverageSubscriptionService(db)
    svc.subscribe(a, target, redirect_assignments=False)
    svc.subscribe(b, target, redirect_assignments=False)  # no conflict
    active = set(svc.active_subscribers_for(target))
    assert active == {a, b}
    assert svc.active_coverer_for(target) is None  # neither redirects


def test_subscribe_add_on_when_no_coverage_allowed(db):
    target = _user(db, "target")
    a = _user(db, "a")
    team = _team(db, "T")
    _member(db, team, target)
    _member(db, team, a)
    sub = CoverageSubscriptionService(db).subscribe(a, target, redirect_assignments=True)
    assert sub.redirect_assignments is True
    assert CoverageSubscriptionService(db).active_coverer_for(target) == a


def test_subscribe_same_subscriber_upsert_flip_off_to_on(db):
    target = _user(db, "target")
    a = _user(db, "a")
    team = _team(db, "T")
    _member(db, team, target)
    _member(db, team, a)
    svc = CoverageSubscriptionService(db)
    exp1 = datetime.utcnow() + timedelta(days=1)
    first = svc.subscribe(a, target, expires_at=exp1, redirect_assignments=False)
    first_id = first.id
    exp2 = datetime.utcnow() + timedelta(days=7)
    second = svc.subscribe(a, target, expires_at=exp2, redirect_assignments=True)
    # Same row updated, no conflict.
    assert second.id == first_id
    rows = (
        db.query(NotificationSubscription)
        .filter(NotificationSubscription.target_user_id == target)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].redirect_assignments is True
    assert rows[0].expires_at == exp2
    assert svc.active_coverer_for(target) == a


# ===========================================================================
# 3. resolve_assignee_with_coverage
# ===========================================================================

def _assignee_dict(uid, email="x@x.com", name="X"):
    return {"id": uid, "email": email, "name": name, "respond_user_id": None}


def test_resolve_swaps_when_on_coverage(db):
    target = _user(db, "target")
    cover = _user(db, "cover")
    _raw_sub(db, cover, target, redirect=True)
    new_assignee, covered_for = resolve_assignee_with_coverage(
        db, _assignee_dict(target)
    )
    assert new_assignee["id"] == cover
    assert covered_for == target


def test_resolve_passthrough_when_no_coverage(db):
    target = _user(db, "target")
    a = _assignee_dict(target)
    new_assignee, covered_for = resolve_assignee_with_coverage(db, a)
    assert new_assignee["id"] == target
    assert covered_for is None


def test_resolve_passthrough_when_notify_only(db):
    target = _user(db, "target")
    cover = _user(db, "cover")
    _raw_sub(db, cover, target, redirect=False)  # notify-only never redirects
    new_assignee, covered_for = resolve_assignee_with_coverage(
        db, _assignee_dict(target)
    )
    assert new_assignee["id"] == target
    assert covered_for is None


def test_resolve_one_hop_only(db):
    # A covered by B, B covered by C -> resolving A returns B, not C.
    a = _user(db, "a")
    b = _user(db, "b")
    c = _user(db, "c")
    _raw_sub(db, b, a, redirect=True)  # B covers A
    _raw_sub(db, c, b, redirect=True)  # C covers B
    new_assignee, covered_for = resolve_assignee_with_coverage(db, _assignee_dict(a))
    assert new_assignee["id"] == b  # one hop only, not C
    assert covered_for == a


def test_resolve_best_effort_on_falsy(db):
    # None / empty dict / missing id -> passthrough, no crash.
    assert resolve_assignee_with_coverage(db, None) == (None, None)
    assert resolve_assignee_with_coverage(db, {}) == ({}, None)
    d = {"email": "x@x.com"}
    assert resolve_assignee_with_coverage(db, d) == (d, None)


def test_resolve_swapped_dict_shape(db):
    # The coverer dict carries the canonical fields used downstream.
    target = _user(db, "target")
    cover = _user(db, "cover", respond_user_id="RU-9")
    _raw_sub(db, cover, target, redirect=True)
    new_assignee, _ = resolve_assignee_with_coverage(db, _assignee_dict(target))
    assert new_assignee["id"] == cover
    assert new_assignee["email"] == "cover@x.com"
    assert new_assignee["respond_user_id"] == "RU-9"


def test_coverage_note_suffix(db):
    target = _user(db, "Charissa")
    assert coverage_note(db, target) == " (covering for Charissa)"
    assert coverage_note(db, None) == ""


# ===========================================================================
# 5. RR fairness: cursor advances to COVERED user; only returned dict swaps
# ===========================================================================

def test_rr_cursor_advances_to_covered_user_not_coverer(db):
    from app.services.user_service import AccessAgentService

    # Single-member team whose only member is "covered"; coverer is elsewhere.
    covered = _user(db, "covered")
    coverer = _user(db, "coverer")
    team = _team(db, "RRTeam")
    _member(db, team, covered)

    agent_id = str(uuid.uuid4())
    db.add(AccessAgent(id=agent_id, code="rr-agent", name="RR Agent", is_active=True))
    db.commit()
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=agent_id, code="ts", team_id=team, tier=1))
    db.commit()

    # Coverage: coverer auto-covers covered.
    _raw_sub(db, coverer, covered, redirect=True)

    agent_svc = AccessAgentService(db)
    assignee = agent_svc.get_next_assignee(agent_id, team)
    assert assignee is not None and assignee["id"] == covered  # RR picked covered

    # Apply coverage redirect (what the routing surfaces do).
    redirected, covered_for = resolve_assignee_with_coverage(db, assignee)
    assert redirected["id"] == coverer  # task lands on coverer
    assert covered_for == covered

    # Cursor still points at the COVERED user (fairness): only the dict was swapped.
    cursor = (
        db.query(AgentTeamRoundRobinCursor)
        .filter(
            AgentTeamRoundRobinCursor.agent_id == agent_id,
            AgentTeamRoundRobinCursor.team_id == team,
        )
        .first()
    )
    assert cursor is not None
    assert str(cursor.last_assigned_user_id) == covered


# ===========================================================================
# 6. Forward-only / coverage end: expired -> no redirect
# ===========================================================================

def test_expired_coverage_no_redirect(db):
    target = _user(db, "target")
    cover = _user(db, "cover")
    _raw_sub(db, cover, target, redirect=True,
             expires_at=datetime.utcnow() - timedelta(minutes=1))
    new_assignee, covered_for = resolve_assignee_with_coverage(
        db, _assignee_dict(target)
    )
    assert new_assignee["id"] == target  # passthrough
    assert covered_for is None


def test_inactive_coverage_no_redirect(db):
    target = _user(db, "target")
    cover = _user(db, "cover")
    _raw_sub(db, cover, target, redirect=True, is_active=False)
    new_assignee, covered_for = resolve_assignee_with_coverage(
        db, _assignee_dict(target)
    )
    assert new_assignee["id"] == target
    assert covered_for is None


# ===========================================================================
# 7. Notify-only unchanged: still in fan-out; active_coverer_for None
# ===========================================================================

def test_notify_only_still_fans_out_but_no_redirect(db):
    target = _user(db, "target")
    cover = _user(db, "cover")
    _raw_sub(db, cover, target, redirect=False)
    svc = CoverageSubscriptionService(db)
    # In the notify fan-out path (active_subscribers_for), the coverer is still included.
    assert cover in svc.active_subscribers_for(target)
    # But redirect routing ignores notify-only.
    assert svc.active_coverer_for(target) is None
