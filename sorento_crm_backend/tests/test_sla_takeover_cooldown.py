"""Takeover cooldown: pending-intent, cancel/reject, void, commit sweep.

Backend lane for UAC-takeover-cooldown. Notifications are patched (asserted only where
the AC is about channels); the commit sweep reuses the synchronous takeover, whose
_notify_reassignment is patched as in test_sla_takeover_reassign.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app.models.access import (
    AccessAgent,
    AgentTeam,
    AgentTeamRoundRobinCursor,
    RespondContact,
    Team,
    TeamMember,
)
from app.models.integration import IntegrationLog
from app.models.sla import (
    ConversationSLAEventLog,
    ConversationSLATracking,
    SlaTakeoverRequest,
    SLAPolicy,
    SLAPolicyTier,
    TAKEOVER_PENDING,
    TAKEOVER_COMMITTED,
    TAKEOVER_CANCELLED,
    TAKEOVER_REJECTED,
    TAKEOVER_VOIDED,
)
from app.models.user import (
    SystemSetting,
    User,
    UserRole,
    UserRoleAssignment,
)
from app.services.error_handler import AppException
from app.services.sla_service import ConversationSLATrackingService
from app.services.sla_takeover_service import SlaTakeoverService
from tests import _pg_fixture
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        # descendant_team_ids() drops to raw text() SQL on Postgres ("FROM teams"),
        # which the engine's schema_translate_map does not rewrite -- unqualified
        # names would resolve against the real public schema and read live rows.
        # SET LOCAL is scoped to the outer transaction, so it unwinds with it.
        blank = _pg_fixture._BLANK["name"]
        session.execute(text(f'SET LOCAL search_path TO "{blank}", "{blank}_scm"'))
        yield session


# ---- builders -------------------------------------------------------------

def _user(db, name, respond_user_id=None) -> str:
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{name}@x.com", name=name, status="ACTIVE",
                respond_user_id=respond_user_id))
    db.commit()
    return uid


def _admin(db, name) -> str:
    uid = _user(db, name)
    role_id = str(uuid.uuid4())
    db.add(UserRole(id=role_id, name="Admin", slug="admin"))
    db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=uid, role_id=role_id))
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


def _agent(db) -> str:
    aid = str(uuid.uuid4())
    db.add(AccessAgent(id=aid, code="a", name="A"))
    db.commit()
    return aid


def _agent_team(db, agent_id, team_id, code="cs", tier=1):
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=agent_id, code=code, team_id=team_id, tier=tier))
    db.commit()


def _policy(db) -> str:
    pid = str(uuid.uuid4())
    db.add(SLAPolicy(id=pid, code="p", name="Policy"))
    db.commit()
    return pid


def _track(db, pid, *, assignee, src="complaint") -> str:
    tid = str(uuid.uuid4())
    db.add(ConversationSLATracking(
        id=tid, policy_id=pid, current_tier=1, assigned_to_id=assignee,
        current_tier_started_at=datetime(2026, 6, 1, 9, 0, 0),
        due_at=datetime(2026, 6, 1, 14, 0, 0),
        due_at_resolution=datetime(2026, 6, 2, 9, 0, 0),
        is_resolved=False, source_entity_type=src, source_entity_id=str(uuid.uuid4()),
    ))
    db.commit()
    return tid


def _set_cooldown(db, seconds: int):
    row = db.query(SystemSetting).first()
    if row is None:
        db.add(SystemSetting(id=str(uuid.uuid4()), name="Co",
                             takeover_cooldown_seconds=seconds))
    else:
        row.takeover_cooldown_seconds = seconds
    db.commit()


def _scene(db, *, cooldown=60, assignee_present=True):
    """me (initiator) + peer (owner) share a team with an agent chain. Returns
    (svc, me, peer, team, tid)."""
    pid = _policy(db)
    me = _user(db, "me", respond_user_id="r-me")
    peer = _user(db, "peer", respond_user_id="r-peer")
    team = _team(db, "T")
    _member(db, team, me)
    _member(db, team, peer)
    agent_id = _agent(db)
    _agent_team(db, agent_id, team, code="cs", tier=1)
    tid = _track(db, pid, assignee=(peer if assignee_present else None))
    _set_cooldown(db, cooldown)
    return SlaTakeoverService(db), me, peer, team, tid


# Mock at the notification-create layer so the real takeover notify helpers still run
# (channel kwargs are assertable) without needing notification/delivery tables. Coverage
# fan-out + the synchronous reassign notify are stubbed (they query other tables).
@pytest.fixture(autouse=True)
def notif():
    with patch("app.services.notification_service.NotificationService."
               "create_with_channel_preferences") as cwp, \
         patch("app.services.coverage_subscription_service.fan_out_coverage_copies"), \
         patch("app.services.sla_service.ConversationSLATrackingService._notify_reassignment"):
        yield cwp


# ---- config ---------------------------------------------------------------

def test_cooldown_default_60_when_no_row(db):
    assert SlaTakeoverService(db).cooldown_seconds() == 60


def test_cooldown_reads_setting(db):
    _set_cooldown(db, 120)
    assert SlaTakeoverService(db).cooldown_seconds() == 120


# ---- initiate -------------------------------------------------------------

def test_initiate_creates_pending_no_assignment_change(db):
    svc, me, peer, team, tid = _scene(db, cooldown=60)
    result = svc.initiate(tid, me, team)
    assert result["committed"] is False
    req = result["request"]
    assert req["status"] == TAKEOVER_PENDING
    assert req["initiator_id"] == me
    assert req["contested_assignee_id"] == peer
    assert req["commit_at"] is not None
    # assignment unchanged
    t = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()
    assert t.assigned_to_id == peer


def test_initiate_cooldown_zero_commits_instantly(db):
    svc, me, peer, team, tid = _scene(db, cooldown=0)
    result = svc.initiate(tid, me, team)
    assert result["committed"] is True
    assert db.query(SlaTakeoverRequest).count() == 0
    t = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()
    assert t.assigned_to_id == me


def test_initiate_unassigned_commits_instantly(db):
    svc, me, peer, team, tid = _scene(db, cooldown=60, assignee_present=False)
    result = svc.initiate(tid, me, team)
    assert result["committed"] is True
    assert db.query(SlaTakeoverRequest).count() == 0


def test_initiate_fcfs_returns_existing_pending(db):
    svc, me, peer, team, tid = _scene(db, cooldown=60)
    first = svc.initiate(tid, me, team)
    second = svc.initiate(tid, me, team)
    assert second.get("already_pending") is True
    assert second["request"]["request_id"] == first["request"]["request_id"]
    assert db.query(SlaTakeoverRequest).filter(
        SlaTakeoverRequest.status == TAKEOVER_PENDING).count() == 1


def test_initiate_resolved_blocked(db):
    svc, me, peer, team, tid = _scene(db, cooldown=60)
    db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).update(
        {"is_resolved": True})
    db.commit()
    with pytest.raises(AppException):
        svc.initiate(tid, me, team)
    assert db.query(SlaTakeoverRequest).count() == 0


# ---- cancel ---------------------------------------------------------------

def test_cancel_by_initiator(db):
    svc, me, peer, team, tid = _scene(db)
    rid = svc.initiate(tid, me, team)["request"]["request_id"]
    out = svc.cancel(rid, me)
    assert out["status"] == TAKEOVER_CANCELLED
    assert out["resolution_reason"] == "cancel"
    t = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()
    assert t.assigned_to_id == peer  # unchanged


def test_cancel_by_admin(db):
    svc, me, peer, team, tid = _scene(db)
    admin = _admin(db, "boss")
    rid = svc.initiate(tid, me, team)["request"]["request_id"]
    assert svc.cancel(rid, admin)["status"] == TAKEOVER_CANCELLED


def test_cancel_by_stranger_denied(db):
    svc, me, peer, team, tid = _scene(db)
    stranger = _user(db, "rando")
    rid = svc.initiate(tid, me, team)["request"]["request_id"]
    with pytest.raises(AppException):
        svc.cancel(rid, stranger)
    assert svc.get_pending_for_tracking(tid) is not None


# ---- reject ---------------------------------------------------------------

def test_reject_by_owner(db):
    svc, me, peer, team, tid = _scene(db)
    rid = svc.initiate(tid, me, team)["request"]["request_id"]
    out = svc.reject(rid, peer)
    assert out["status"] == TAKEOVER_REJECTED
    assert out["resolution_reason"] == "reject"
    t = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()
    assert t.assigned_to_id == peer


def test_reject_by_admin(db):
    svc, me, peer, team, tid = _scene(db)
    admin = _admin(db, "boss")
    rid = svc.initiate(tid, me, team)["request"]["request_id"]
    assert svc.reject(rid, admin)["status"] == TAKEOVER_REJECTED


def test_reject_by_stranger_denied(db):
    svc, me, peer, team, tid = _scene(db)
    stranger = _user(db, "rando")
    rid = svc.initiate(tid, me, team)["request"]["request_id"]
    with pytest.raises(AppException):
        svc.reject(rid, stranger)
    assert svc.get_pending_for_tracking(tid) is not None


# ---- implicit void --------------------------------------------------------

def test_resolve_voids_pending(db):
    from app.schemas.sla import ConversationSLATrackingUpdate

    svc, me, peer, team, tid = _scene(db)
    svc.initiate(tid, me, team)
    # owner resolves via update_tracking (the real resolve entrypoint)
    ConversationSLATrackingService(db).update_tracking(
        tid, ConversationSLATrackingUpdate(is_resolved=True, resolved_by=peer)
    )
    req = db.query(SlaTakeoverRequest).first()
    assert req.status == TAKEOVER_VOIDED
    assert req.resolution_reason == "resolved"


def test_owner_reassign_away_voids_pending(db):
    svc, me, peer, team, tid = _scene(db)
    third = _user(db, "carol", respond_user_id="r-carol")
    _member(db, team, third)
    svc.initiate(tid, me, team)
    # owner (peer) reassigns their own task to carol
    ConversationSLATrackingService(db).reassign(tid, peer, third)
    req = db.query(SlaTakeoverRequest).first()
    assert req.status == TAKEOVER_VOIDED
    assert req.resolution_reason == "reassigned"
    t = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()
    assert t.assigned_to_id == third


def test_third_party_reassign_blocked_while_pending(db):
    svc, me, peer, team, tid = _scene(db)
    third = _user(db, "carol", respond_user_id="r-carol")
    _member(db, team, third)
    svc.initiate(tid, me, team)
    # a non-owner (me) tries to reassign the contested task -> blocked
    with pytest.raises(AppException):
        ConversationSLATrackingService(db).reassign(tid, me, third)
    assert svc.get_pending_for_tracking(tid) is not None


# ---- commit sweep ---------------------------------------------------------

def _force_due(db, rid):
    db.query(SlaTakeoverRequest).filter(SlaTakeoverRequest.id == rid).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)})
    db.commit()


def test_commit_due_commits_unchallenged(db):
    svc, me, peer, team, tid = _scene(db)
    rid = svc.initiate(tid, me, team)["request"]["request_id"]
    _force_due(db, rid)
    out = svc.commit_due()
    assert out["committed"] == 1 and out["voided"] == 0
    req = db.query(SlaTakeoverRequest).filter(SlaTakeoverRequest.id == rid).first()
    assert req.status == TAKEOVER_COMMITTED
    t = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()
    assert t.assigned_to_id == me  # flipped to initiator


def test_commit_revalidate_resolved_voids(db):
    svc, me, peer, team, tid = _scene(db)
    rid = svc.initiate(tid, me, team)["request"]["request_id"]
    # resolve directly (bypass update_tracking active-void) then force due
    db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).update(
        {"is_resolved": True})
    db.commit()
    _force_due(db, rid)
    out = svc.commit_due()
    assert out["committed"] == 0 and out["voided"] == 1
    req = db.query(SlaTakeoverRequest).filter(SlaTakeoverRequest.id == rid).first()
    assert req.status == TAKEOVER_VOIDED and req.resolution_reason == "resolved"


def test_commit_revalidate_owner_changed_voids(db):
    svc, me, peer, team, tid = _scene(db)
    other = _user(db, "owner2")
    rid = svc.initiate(tid, me, team)["request"]["request_id"]
    # silently change the owner (not via reassign, so no active void)
    db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).update(
        {"assigned_to_id": other})
    db.commit()
    _force_due(db, rid)
    out = svc.commit_due()
    assert out["voided"] == 1
    req = db.query(SlaTakeoverRequest).filter(SlaTakeoverRequest.id == rid).first()
    assert req.status == TAKEOVER_VOIDED and req.resolution_reason == "reassigned"


def test_commit_revalidate_initiator_ineligible_voids(db):
    svc, me, peer, team, tid = _scene(db)
    rid = svc.initiate(tid, me, team)["request"]["request_id"]
    # strip initiator's membership -> no longer eligible to act
    db.query(TeamMember).filter(TeamMember.user_id == me).delete()
    db.commit()
    _force_due(db, rid)
    out = svc.commit_due()
    assert out["voided"] == 1
    req = db.query(SlaTakeoverRequest).filter(SlaTakeoverRequest.id == rid).first()
    assert req.status == TAKEOVER_VOIDED and req.resolution_reason == "ineligible"
    t = db.query(ConversationSLATracking).filter(ConversationSLATracking.id == tid).first()
    assert t.assigned_to_id == peer  # unchanged


def test_commit_at_frozen_against_setting_change(db):
    svc, me, peer, team, tid = _scene(db, cooldown=60)
    rid = svc.initiate(tid, me, team)["request"]["request_id"]
    before = db.query(SlaTakeoverRequest).filter(SlaTakeoverRequest.id == rid).first().commit_at
    _set_cooldown(db, 5)  # change global setting mid-flight
    after = db.query(SlaTakeoverRequest).filter(SlaTakeoverRequest.id == rid).first().commit_at
    assert before == after


# ---- list helpers ---------------------------------------------------------

def test_pending_by_tracking_ids_maps_only_pending(db):
    svc, me, peer, team, tid = _scene(db)
    svc.initiate(tid, me, team)
    m = svc.pending_by_tracking_ids([tid, str(uuid.uuid4())])
    assert tid in m and m[tid]["status"] == TAKEOVER_PENDING


def test_get_takeover_row_includes_latest(db):
    svc, me, peer, team, tid = _scene(db)
    svc.initiate(tid, me, team)
    row = svc.get_takeover_row(tid, peer)
    assert row["id"] == tid
    assert row["takeover"]["status"] == TAKEOVER_PENDING


# ---- notification channels ------------------------------------------------

def test_start_notification_to_owner_with_assignment_gating(db, notif):
    """Start notify targets the contested owner, in-app + assignment toggles, deep link."""
    svc, me, peer, team, tid = _scene(db)
    svc.initiate(tid, me, team)
    # the start notification is the create call addressed to the owner (peer)
    start_calls = [c for c in notif.call_args_list
                   if c.kwargs.get("user_id") == peer
                   and c.kwargs.get("event_type") == "takeover_pending"]
    assert len(start_calls) == 1
    k = start_calls[0].kwargs
    assert k["send_in_app"] is True
    assert k["email_pref_attr"] == "notify_email_on_assignment"
    assert k["whatsapp_pref_attr"] == "notify_whatsapp_on_assignment"
    assert str(tid) in (k.get("data") or {}).get("tracking_id", "")


def test_cancel_notification_in_app_only(db, notif):
    """Cancel notify uses send_email=False, send_whatsapp=False, in-app on."""
    svc, me, peer, team, tid = _scene(db)
    rid = svc.initiate(tid, me, team)["request"]["request_id"]
    notif.reset_mock()
    svc.cancel(rid, me)
    cancel_calls = [c for c in notif.call_args_list
                    if c.kwargs.get("event_type") == "takeover_cancelled"]
    assert len(cancel_calls) == 1
    k = cancel_calls[0].kwargs
    assert k["send_email"] is False
    assert k["send_whatsapp"] is False
    assert k["send_in_app"] is True
    assert k["user_id"] == peer
