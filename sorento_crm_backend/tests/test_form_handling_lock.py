"""Form handling-lock ("I'm handling this") — Phase 2 BE tests.

Covers PLAN-form-handling-lock §12 Phase 2 UAC:
  P2-2  claim happy + concurrent-409
  P2-3  claim non-eligible-403 / non-escalated-reject / flag-off-noop
  P2-4  take-over happy + optimistic-409
  P2-5  release holder / non-holder-403
  P2-6  CTA guard matrix (complaint + PR): non-handler / handler / admin-unclaimed / admin-other-holds
  P2-8  escalation resets handled_by_id
  P2-9  extend handler-gated-when-escalated / assignee-only otherwise
  P2-11 notify actor-exclusion (recipient set)
  P2-13 scope rejects conversation-SLA rows
  P2-15 per-form flag isolation

Run: venv/bin/pytest tests/test_form_handling_lock.py -q
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.access import (
    AccessAgent,
    AgentTeam,
    RespondContact,
    Team,
    TeamMember,
)
from app.models.lookup import LookupBinding
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
from app.services.error_handler import AppException
import app.services.handling_lock_service as hls
from app.services.handling_lock_service import (
    HandlingLockService,
    assert_can_act_on_form,
    eligible_user_ids,
    is_handling_lock_enabled,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, JSONB
    from sqlalchemy.types import JSON as GenericJSON

    for model in (RespondContact, SystemSetting):
        for col in list(model.__table__.columns):
            if isinstance(col.type, (JSONB, PG_ARRAY)):
                col.type = GenericJSON()
                col.server_default = None

    # AgentTeam's two uniqueness indexes are PARTIAL on postgres (postgresql_where on
    # tier IS / IS NOT NULL). sqlite ignores the predicate, turning them into full
    # unique indexes that reject multiple tier rows per (agent, code). Drop them for
    # the sqlite fixture — the tests don't exercise the uniqueness invariant.
    for idx in list(AgentTeam.__table__.indexes):
        if idx.name in (
            "uq_agent_teams_agent_code_tier_null",
            "uq_agent_teams_agent_code_tier_not_null",
        ):
            AgentTeam.__table__.indexes.discard(idx)

    Base.metadata.create_all(
        engine,
        tables=[
            SLAPolicy.__table__,
            SLAPolicyTier.__table__,
            ConversationSLATracking.__table__,
            ConversationSLAEventLog.__table__,
            RespondContact.__table__,
            User.__table__,
            SystemSetting.__table__,
            AccessAgent.__table__,
            Team.__table__,
            TeamMember.__table__,
            AgentTeam.__table__,
            LookupBinding.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


# Recorder for notification fan-out — asserts the recipient set (actor-exclusion).
_NOTIFY_CALLS: list[str] = []


@pytest.fixture(autouse=True)
def _capture_notifications(monkeypatch):
    from app.services.notification_service import NotificationService

    _NOTIFY_CALLS.clear()

    def _rec(self, user_id, **kwargs):
        _NOTIFY_CALLS.append(str(user_id))
        return None

    monkeypatch.setattr(
        NotificationService, "create_with_channel_preferences", _rec
    )
    yield


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
    # Tier 1 members: assignee + member_a. Tier 2 members: member_b.
    for uid in (users["assignee"], users["member_a"]):
        db.add(TeamMember(id=str(uuid.uuid4()), team_id=team1, user_id=uid))
    db.add(TeamMember(id=str(uuid.uuid4()), team_id=team2, user_id=users["member_b"]))

    # Flag ON for complaint only (per-form isolation exercised in a dedicated test).
    db.add(
        SystemSetting(
            id=str(uuid.uuid4()),
            name="Co",
            handling_lock_enabled_types="complaint",
        )
    )
    db.commit()
    return {
        "policy_id": policy_id,
        "agent_id": agent_id,
        "team_set_code": "cs",
        "users": users,
    }


def _tracker(
    db,
    seed,
    *,
    tier=2,
    resolved=False,
    entity="complaint",
    handled_by=None,
    agent=True,
):
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
        agent_id=seed["agent_id"] if agent else None,
        team_set_code=seed["team_set_code"] if agent else None,
        assigned_to_id=seed["users"]["assignee"],
        handled_by_id=handled_by,
        handled_at=now if handled_by else None,
    )
    db.add(t)
    db.commit()
    return t


def _actor(seed, key):
    return {"id": seed["users"][key]}


def _events(db, tid, etype=None):
    q = db.query(ConversationSLAEventLog).filter(
        ConversationSLAEventLog.sla_tracking_id == tid
    )
    if etype:
        q = q.filter(ConversationSLAEventLog.event_type == etype)
    return q.all()


# --------------------------------------------------------------------------- #
# Flag + eligibility                                                          #
# --------------------------------------------------------------------------- #
def test_flag_per_form_isolation(db, seed):  # P2-15
    assert is_handling_lock_enabled(db, "complaint") is True
    for other in ("stock_inquiry", "purchase_request", "sponsorship_form"):
        assert is_handling_lock_enabled(db, other) is False
    assert is_handling_lock_enabled(db, None) is False


def test_eligible_user_ids_spans_chain(db, seed):
    t = _tracker(db, seed, tier=2)
    eligible = eligible_user_ids(db, t)
    assert eligible == {
        seed["users"]["assignee"],
        seed["users"]["member_a"],
        seed["users"]["member_b"],
    }
    assert seed["users"]["outsider"] not in eligible


# --------------------------------------------------------------------------- #
# claim                                                                        #
# --------------------------------------------------------------------------- #
def test_claim_happy(db, seed):  # P2-2
    t = _tracker(db, seed, tier=2)
    out = HandlingLockService(db).claim_handling(t.id, _actor(seed, "member_a"))
    assert out.handled_by_id == seed["users"]["member_a"]
    assert out.handled_at is not None
    logs = _events(db, t.id, HANDLING_CLAIMED)
    assert len(logs) == 1
    assert logs[0].triggered_by_id == seed["users"]["member_a"]


def test_claim_concurrent_409(db, seed):  # P2-2
    t = _tracker(db, seed, tier=2)
    HandlingLockService(db).claim_handling(t.id, _actor(seed, "member_a"))
    with pytest.raises(AppException) as e:
        HandlingLockService(db).claim_handling(t.id, _actor(seed, "member_b"))
    assert e.value.status_code == 409


def test_claim_non_eligible_403(db, seed):  # P2-3
    t = _tracker(db, seed, tier=2)
    with pytest.raises(AppException) as e:
        HandlingLockService(db).claim_handling(t.id, _actor(seed, "outsider"))
    assert e.value.status_code == 403


def test_claim_non_escalated_rejected(db, seed):  # P2-3
    t = _tracker(db, seed, tier=1)
    with pytest.raises(AppException) as e:
        HandlingLockService(db).claim_handling(t.id, _actor(seed, "member_a"))
    assert e.value.status_code == 422


def test_claim_flag_off_rejected(db, seed):  # P2-3 / P2-15
    setting = db.query(SystemSetting).first()
    setting.handling_lock_enabled_types = ""  # flag off for all
    db.commit()
    t = _tracker(db, seed, tier=2)
    with pytest.raises(AppException) as e:
        HandlingLockService(db).claim_handling(t.id, _actor(seed, "member_a"))
    assert e.value.status_code == 422


def test_claim_notifies_others_excludes_actor(db, seed):  # P2-11
    t = _tracker(db, seed, tier=2)
    _NOTIFY_CALLS.clear()
    HandlingLockService(db).claim_handling(t.id, _actor(seed, "member_a"))
    recipients = set(_NOTIFY_CALLS)
    assert seed["users"]["member_a"] not in recipients  # actor never notified
    # assignee + other eligible members are notified.
    assert seed["users"]["assignee"] in recipients
    assert seed["users"]["member_b"] in recipients
    assert seed["users"]["outsider"] not in recipients


# --------------------------------------------------------------------------- #
# take-over                                                                    #
# --------------------------------------------------------------------------- #
def test_take_over_happy(db, seed):  # P2-4
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    _NOTIFY_CALLS.clear()
    out = HandlingLockService(db).take_over_handling(
        t.id, _actor(seed, "member_b"), seed["users"]["member_a"]
    )
    assert out.handled_by_id == seed["users"]["member_b"]
    assert getattr(out, "_previous_handler_id") == seed["users"]["member_a"]
    assert len(_events(db, t.id, HANDLING_TAKEN_OVER)) == 1
    # Only the displaced holder is notified.
    assert set(_NOTIFY_CALLS) == {seed["users"]["member_a"]}


def test_take_over_optimistic_409(db, seed):  # P2-4
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    with pytest.raises(AppException) as e:
        HandlingLockService(db).take_over_handling(
            t.id, _actor(seed, "member_b"), seed["users"]["outsider"]  # wrong expected
        )
    assert e.value.status_code == 409
    db.refresh(t)
    assert t.handled_by_id == seed["users"]["member_a"]  # unchanged


# --------------------------------------------------------------------------- #
# release                                                                      #
# --------------------------------------------------------------------------- #
def test_release_holder(db, seed):  # P2-5
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    _NOTIFY_CALLS.clear()
    out = HandlingLockService(db).release_handling(t.id, _actor(seed, "member_a"))
    assert out.handled_by_id is None
    assert out.handled_at is None
    assert len(_events(db, t.id, HANDLING_RELEASED)) == 1
    # Eligible pool minus the actor is notified.
    recipients = set(_NOTIFY_CALLS)
    assert seed["users"]["member_a"] not in recipients
    assert seed["users"]["member_b"] in recipients


def test_release_non_holder_403(db, seed):  # P2-5
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    with pytest.raises(AppException) as e:
        HandlingLockService(db).release_handling(t.id, _actor(seed, "member_b"))
    assert e.value.status_code == 403


# --------------------------------------------------------------------------- #
# CTA guard matrix                                                             #
# --------------------------------------------------------------------------- #
@pytest.fixture
def _admin_roles(monkeypatch, seed):
    from app.services.user_service import UserPermissionService

    admin_id = seed["users"]["admin"]
    monkeypatch.setattr(
        UserPermissionService,
        "get_user_role_slugs",
        lambda self, uid: ({"admin"} if str(uid) == admin_id else set()),
    )
    yield


def test_guard_non_handler_403(db, seed, _admin_roles):  # P2-6
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    with pytest.raises(AppException) as e:
        assert_can_act_on_form(
            db, t.source_entity_id, _actor(seed, "member_b"),
            source_entity_type="complaint",
        )
    assert e.value.status_code == 403


def test_guard_handler_allowed(db, seed, _admin_roles):  # P2-6
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    # No raise.
    assert_can_act_on_form(
        db, t.source_entity_id, _actor(seed, "member_a"),
        source_entity_type="complaint",
    )


def test_guard_admin_unclaimed_allowed(db, seed, _admin_roles):  # P2-6
    t = _tracker(db, seed, tier=2, handled_by=None)
    assert_can_act_on_form(
        db, t.source_entity_id, _actor(seed, "admin"),
        source_entity_type="complaint",
    )


def test_guard_admin_when_other_holds_403(db, seed, _admin_roles):  # P2-6
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    with pytest.raises(AppException) as e:
        assert_can_act_on_form(
            db, t.source_entity_id, _actor(seed, "admin"),
            source_entity_type="complaint",
        )
    assert e.value.status_code == 403


def test_guard_not_escalated_allows(db, seed, _admin_roles):  # P2-6 / regression
    t = _tracker(db, seed, tier=1, handled_by=None)
    assert_can_act_on_form(
        db, t.source_entity_id, _actor(seed, "outsider"),
        source_entity_type="complaint",
    )


def test_guard_flag_off_allows(db, seed, _admin_roles):  # P2-15 regression
    setting = db.query(SystemSetting).first()
    setting.handling_lock_enabled_types = ""
    db.commit()
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    assert_can_act_on_form(
        db, t.source_entity_id, _actor(seed, "member_b"),
        source_entity_type="complaint",
    )


def test_guard_pr_type(db, seed, _admin_roles):  # P2-6 (PR form)
    # Enable PR too and register a PR agent stage so eligibility resolves.
    setting = db.query(SystemSetting).first()
    setting.handling_lock_enabled_types = "complaint,purchase_request"
    db.commit()
    t = _tracker(db, seed, tier=2, entity="purchase_request",
                 handled_by=seed["users"]["member_a"])
    # non-handler denied
    with pytest.raises(AppException) as e:
        assert_can_act_on_form(db, t.source_entity_id, _actor(seed, "member_b"))
    assert e.value.status_code == 403
    # handler allowed (type auto-resolved from the tracker, no explicit type arg)
    assert_can_act_on_form(db, t.source_entity_id, _actor(seed, "member_a"))


# --------------------------------------------------------------------------- #
# Scope boundary                                                               #
# --------------------------------------------------------------------------- #
def test_claim_rejects_conversation_row(db, seed):  # P2-13
    t = _tracker(db, seed, tier=2, entity="complaint")
    t.source_entity_type = None  # conversation-SLA row
    db.commit()
    with pytest.raises(AppException) as e:
        HandlingLockService(db).claim_handling(t.id, _actor(seed, "member_a"))
    assert e.value.status_code == 422


def test_guard_ignores_conversation_row(db, seed, _admin_roles):  # P2-13
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    t.source_entity_type = None
    db.commit()
    # No form tracker matches -> allow (today's behavior).
    assert_can_act_on_form(db, t.source_entity_id, _actor(seed, "member_b"))


# --------------------------------------------------------------------------- #
# Escalation reset                                                             #
# --------------------------------------------------------------------------- #
def test_escalation_resets_handled_by(db, seed, monkeypatch):  # P2-8
    from app.services.user_service import AccessAgentService
    from app.services.form_sla_service import FormSLAOrchestrator

    monkeypatch.setattr(
        AccessAgentService,
        "get_next_assignee",
        lambda self, a, tid: {"id": seed["users"]["member_b"], "respond_user_id": None},
    )
    monkeypatch.setattr(FormSLAOrchestrator, "_notify_assignee", lambda self, *a, **k: None)

    # Escalate tier 1 -> 2 (team2 exists at tier 2); the reset must clear any lock.
    t = _tracker(db, seed, tier=1, handled_by=seed["users"]["member_a"])
    out = FormSLAOrchestrator(db).escalate_form_tracking(
        t.id, reason="push", actor_user_id=seed["users"]["admin"]
    )
    assert out.current_tier == 2
    assert out.handled_by_id is None
    assert out.handled_at is None


# --------------------------------------------------------------------------- #
# Extend gating                                                                #
# --------------------------------------------------------------------------- #
def _svc(db):
    from app.services.sla_service import ConversationSLATrackingService

    return ConversationSLATrackingService(db)


def test_extend_handler_gated_when_escalated(db, seed):  # P2-9
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    # Handler passes the gate (no raise).
    _svc(db)._assert_can_extend(t, seed["users"]["member_a"])
    # Assignee (non-handler) is now blocked.
    with pytest.raises(AppException) as e:
        _svc(db)._assert_can_extend(t, seed["users"]["assignee"])
    assert e.value.status_code == 403


def test_extend_assignee_only_when_flag_off(db, seed):  # P2-9 regression
    setting = db.query(SystemSetting).first()
    setting.handling_lock_enabled_types = ""
    db.commit()
    t = _tracker(db, seed, tier=2, handled_by=seed["users"]["member_a"])
    # Flag off -> assignee-only, unchanged. Assignee passes; handler (non-assignee) blocked.
    _svc(db)._assert_can_extend(t, seed["users"]["assignee"])
    with pytest.raises(AppException) as e:
        _svc(db)._assert_can_extend(t, seed["users"]["member_a"])
    assert e.value.status_code == 403


def test_extend_assignee_only_when_not_escalated(db, seed):  # P2-9 regression
    t = _tracker(db, seed, tier=1, handled_by=None)
    _svc(db)._assert_can_extend(t, seed["users"]["assignee"])
    with pytest.raises(AppException) as e:
        _svc(db)._assert_can_extend(t, seed["users"]["member_b"])
    assert e.value.status_code == 403
