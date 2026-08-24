"""Backend-owned SLA policy binding for conversation SLA
(PLAN-conversation-policy-binding).

Covers:
- AccessAgentService.resolve_policy_id_for: zero / one / many-distinct (UAC-8)
- AccessAgentService.set_agent_teams: cast one policy across all tier rows of a
  code; a newly added tier row inherits it (UAC-2, UAC-3)
- ConversationSLATrackingService._resolve_tier_with_clamp: exact / clamp-down /
  clamp-up-to-lowest / zero-tier None (UAC-9, UAC-10)
- create_tracking: bound policy wins over payload policy_id (UAC-4); current_tier
  forced to 1 (UAC-5); unbound + payload policy_id = D8 fallback (UAC-7 rollout);
  unbound + no policy_id raises (UAC-7 end-state)
- ConversationSLATrackingCreate schema: missing/empty agent_code/team_set_code
  -> ValidationError (UAC-6)
- Sub-hour: tier response_hours=0.5 read as 0.5 float (UAC-11)

Run with:
    pytest tests/test_conversation_policy_binding.py -q
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.models.access import (
    AccessAgent,
    AgentTeam,
    AgentTeamRoundRobinCursor,
    RespondContact,
    Team,
    TeamMember,
)
from app.models.sla import (
    ConversationSLAEventLog,
    ConversationSLATracking,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import User
from app.schemas.sla import ConversationSLATrackingCreate
from app.services.error_handler import AppException
from app.services.sla_service import ConversationSLATrackingService
from app.services.user_service import AccessAgentService
from tests._pg_fixture import blank_session

PHONE = "+60123456789"


# AgentTeam's two PARTIAL unique indexes (postgresql_where) now keep their WHERE
# clause, so multi-tier rows of the same (agent, code) no longer falsely collide
# and no index-stripping shim is needed. That was the reason this file's set_agent_teams
# cases could not be trusted on sqlite.
@pytest.fixture
def db():
    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


# ---------------------------------------------------------------------------
# seed helpers
# ---------------------------------------------------------------------------

def _policy(db, *, code, name=None, tiers=None) -> str:
    """Create an SLA policy with the given tiers.

    ``tiers`` = list of (tier_level, response_hours, resolution_hours).
    """
    pid = str(uuid.uuid4())
    db.add(SLAPolicy(id=pid, code=code, name=name or code))
    for level, resp, reso in (tiers or []):
        db.add(
            SLAPolicyTier(
                id=str(uuid.uuid4()),
                policy_id=pid,
                tier_level=level,
                tier_name=f"Tier {level}",
                response_hours=resp,
                resolution_hours=reso,
            )
        )
    db.commit()
    return pid


def _agent(db, code="AGENT1") -> str:
    aid = str(uuid.uuid4())
    db.add(AccessAgent(id=aid, code=code, name=code))
    db.commit()
    return aid


def _team(db, name) -> str:
    tid = str(uuid.uuid4())
    db.add(Team(id=tid, name=name))
    db.commit()
    return tid


def _contact(db) -> str:
    cid = str(uuid.uuid4())
    db.add(RespondContact(id=cid, phone_number=PHONE, name="Test Contact", session_vars={}))
    db.commit()
    return cid


def _user(db, *, email="agent1@test.com", respond_user_id="900001") -> str:
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=email, name="Agent One", respond_user_id=respond_user_id))
    db.commit()
    return uid


# ---------------------------------------------------------------------------
# resolve_policy_id_for (UAC-8)
# ---------------------------------------------------------------------------

def test_resolve_policy_zero_bindings_returns_none(db):
    aid = _agent(db)
    tid = _team(db, "T1")
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=aid, code="purchasing", team_id=tid, tier=1))
    db.commit()
    assert AccessAgentService(db).resolve_policy_id_for(aid, "purchasing", company_id="00000000-0000-0000-0000-000000000001") is None


def test_resolve_policy_one_binding_returns_that_id(db):
    aid = _agent(db)
    tid = _team(db, "T1")
    pid = _policy(db, code="STD", tiers=[(1, 4, 24)])
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=aid, code="purchasing", team_id=tid, tier=1, policy_id=pid))
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=aid, code="purchasing", team_id=tid, tier=2, policy_id=pid))
    db.commit()
    assert AccessAgentService(db).resolve_policy_id_for(aid, "purchasing", company_id="00000000-0000-0000-0000-000000000001") == pid


def test_resolve_policy_two_distinct_raises_409(db):
    aid = _agent(db)
    tid = _team(db, "T1")
    p1 = _policy(db, code="STD", tiers=[(1, 4, 24)])
    p2 = _policy(db, code="FAST", tiers=[(1, 1, 8)])
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=aid, code="purchasing", team_id=tid, tier=1, policy_id=p1))
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=aid, code="purchasing", team_id=tid, tier=2, policy_id=p2))
    db.commit()
    with pytest.raises(AppException) as exc:
        AccessAgentService(db).resolve_policy_id_for(aid, "purchasing", company_id="00000000-0000-0000-0000-000000000001")
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# set_agent_teams cast + inherit (UAC-2, UAC-3)
# ---------------------------------------------------------------------------

def test_set_agent_teams_casts_policy_across_all_tier_rows(db):
    """One policy_id on the group is stamped onto every tier row of that code."""
    aid = _agent(db)
    t1 = _team(db, "T1")
    t2 = _team(db, "T2")
    pid = _policy(db, code="STD", tiers=[(1, 4, 24), (2, 2, 12)])
    svc = AccessAgentService(db)

    # Only tier 1 carries the policy_id in the payload; the cast must apply it to tier 2.
    svc.set_agent_teams(aid, [
        {"code": "purchasing", "team_id": t1, "tier": 1, "policy_id": pid},
        {"code": "purchasing", "team_id": t2, "tier": 2},
    ])

    rows = db.query(AgentTeam).filter(AgentTeam.agent_id == aid, AgentTeam.code == "purchasing").all()
    assert len(rows) == 2
    assert {str(r.policy_id) for r in rows} == {pid}  # identical across all tier rows (UAC-2)


def test_set_agent_teams_new_tier_row_inherits_policy(db):
    """Re-saving with an added tier row inherits the team set's policy (UAC-3)."""
    aid = _agent(db)
    t1 = _team(db, "T1")
    t2 = _team(db, "T2")
    t3 = _team(db, "T3")
    pid = _policy(db, code="STD", tiers=[(1, 4, 24)])
    svc = AccessAgentService(db)

    svc.set_agent_teams(aid, [
        {"code": "purchasing", "team_id": t1, "tier": 1, "policy_id": pid},
        {"code": "purchasing", "team_id": t2, "tier": 2, "policy_id": pid},
    ])

    # Admin adds a new tier-3 row; group picker stamps policy_id on the group, but
    # even if one row omits it, the cast applies the group's policy to all rows.
    svc.set_agent_teams(aid, [
        {"code": "purchasing", "team_id": t1, "tier": 1, "policy_id": pid},
        {"code": "purchasing", "team_id": t2, "tier": 2},
        {"code": "purchasing", "team_id": t3, "tier": 3},
    ])

    rows = db.query(AgentTeam).filter(AgentTeam.agent_id == aid, AgentTeam.code == "purchasing").all()
    assert len(rows) == 3
    assert all(str(r.policy_id) == pid for r in rows)  # new tier inherited, never NULL


# ---------------------------------------------------------------------------
# _resolve_tier_with_clamp (UAC-9, UAC-10)
# ---------------------------------------------------------------------------

def test_resolve_tier_exact_match(db):
    pid = _policy(db, code="STD", tiers=[(1, 4, 24), (2, 2, 12)])
    svc = ConversationSLATrackingService(db)
    tier = svc._resolve_tier_with_clamp(pid, 2)
    assert tier is not None and tier.tier_level == 2


def test_resolve_tier_clamps_down_to_highest_defined(db):
    """Request tier 3, policy only has 1-2 -> clamp to tier 2 (UAC-10)."""
    pid = _policy(db, code="STD", tiers=[(1, 4, 24), (2, 2, 12)])
    svc = ConversationSLATrackingService(db)
    tier = svc._resolve_tier_with_clamp(pid, 3)
    assert tier is not None and tier.tier_level == 2


def test_resolve_tier_request_below_all_clamps_to_lowest(db):
    """Request tier 1 but policy only defines tiers 2-3 -> lowest defined (tier 2)."""
    pid = _policy(db, code="STD", tiers=[(2, 2, 12), (3, 1, 6)])
    svc = ConversationSLATrackingService(db)
    tier = svc._resolve_tier_with_clamp(pid, 1)
    assert tier is not None and tier.tier_level == 2


def test_resolve_tier_zero_tiers_returns_none(db):
    pid = _policy(db, code="EMPTY", tiers=[])
    svc = ConversationSLATrackingService(db)
    assert svc._resolve_tier_with_clamp(pid, 1) is None


# ---------------------------------------------------------------------------
# create_tracking policy resolution + tier forcing (UAC-4, UAC-5, UAC-7)
# ---------------------------------------------------------------------------

def _bound_setup(db, *, policy_tiers=None):
    """Agent + team set bound to BOUND policy; a separate WRONG policy exists too."""
    aid = _agent(db, code="AGENT1")
    t1 = _team(db, "T1")
    uid = _user(db)
    _contact(db)
    bound = _policy(db, code="BOUND", tiers=policy_tiers or [(1, 4, 24)])
    wrong = _policy(db, code="WRONG", tiers=[(1, 99, 99)])
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=aid, code="purchasing", team_id=t1, tier=1, policy_id=bound))
    db.commit()
    return {"agent_id": aid, "user_id": uid, "bound": bound, "wrong": wrong}


def test_create_tracking_uses_bound_policy_over_payload(db):
    """UAC-4: bound policy wins even if payload sends a different policy_id."""
    s = _bound_setup(db)
    svc = ConversationSLATrackingService(db)
    payload = ConversationSLATrackingCreate(
        agent_code="AGENT1",
        team_set_code="purchasing",
        contact_phone_number=PHONE,
        assigned_to_id=s["user_id"],
        policy_id=s["wrong"],  # deliberately wrong
        current_tier=3,
    )
    tracking = svc.create_tracking(payload)
    assert str(tracking.policy_id) == s["bound"]


def test_create_tracking_forces_tier_1(db):
    """UAC-5: n8n-supplied current_tier ignored; created row is tier 1."""
    s = _bound_setup(db, policy_tiers=[(1, 4, 24), (2, 2, 12), (3, 1, 6)])
    svc = ConversationSLATrackingService(db)
    payload = ConversationSLATrackingCreate(
        agent_code="AGENT1",
        team_set_code="purchasing",
        contact_phone_number=PHONE,
        assigned_to_id=s["user_id"],
        current_tier=3,
    )
    tracking = svc.create_tracking(payload)
    assert tracking.current_tier == 1


def test_create_tracking_unbound_falls_back_to_payload_policy(db):
    """UAC-7 rollout (D8): unbound team set + payload policy_id -> uses it + warns."""
    aid = _agent(db, code="AGENT1")
    t1 = _team(db, "T1")
    uid = _user(db)
    _contact(db)
    fallback = _policy(db, code="FALLBACK", tiers=[(1, 4, 24)])
    # team set row exists but policy NOT bound
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=aid, code="purchasing", team_id=t1, tier=1))
    db.commit()

    svc = ConversationSLATrackingService(db)
    payload = ConversationSLATrackingCreate(
        agent_code="AGENT1",
        team_set_code="purchasing",
        contact_phone_number=PHONE,
        assigned_to_id=uid,
        policy_id=fallback,
    )
    tracking = svc.create_tracking(payload)
    assert str(tracking.policy_id) == fallback


def test_create_tracking_unbound_no_policy_raises(db):
    """UAC-7 end-state: unbound + no payload policy_id -> raises (no SLA policy bound)."""
    aid = _agent(db, code="AGENT1")
    t1 = _team(db, "T1")
    uid = _user(db)
    _contact(db)
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=aid, code="purchasing", team_id=t1, tier=1))
    db.commit()

    svc = ConversationSLATrackingService(db)
    payload = ConversationSLATrackingCreate(
        agent_code="AGENT1",
        team_set_code="purchasing",
        contact_phone_number=PHONE,
        assigned_to_id=uid,
    )
    with pytest.raises(AppException) as exc:
        svc.create_tracking(payload)
    detail = exc.value.detail
    message = detail.get("message") if isinstance(detail, dict) else str(detail)
    assert "no sla policy bound" in str(message).lower()


# ---------------------------------------------------------------------------
# schema required fields (UAC-6)
# ---------------------------------------------------------------------------

def test_schema_missing_agent_code_raises():
    with pytest.raises(ValidationError):
        ConversationSLATrackingCreate(
            team_set_code="purchasing",
            contact_phone_number=PHONE,
        )


def test_schema_empty_agent_code_raises():
    with pytest.raises(ValidationError):
        ConversationSLATrackingCreate(
            agent_code="   ",
            team_set_code="purchasing",
            contact_phone_number=PHONE,
        )


def test_schema_missing_team_set_code_raises():
    with pytest.raises(ValidationError):
        ConversationSLATrackingCreate(
            agent_code="AGENT1",
            contact_phone_number=PHONE,
        )


def test_schema_empty_team_set_code_raises():
    with pytest.raises(ValidationError):
        ConversationSLATrackingCreate(
            agent_code="AGENT1",
            team_set_code="",
            contact_phone_number=PHONE,
        )


# ---------------------------------------------------------------------------
# sub-hour SLA (UAC-11)
# ---------------------------------------------------------------------------

def test_sub_hour_tier_response_hours_read_as_half_float(db):
    """A WAREHOUSE_FAST tier with response_hours=0.5 is stored/read as 0.5, not
    rounded. (_working_due rounds sub-day to 0 working days, so the 30-min due_at
    is only attainable via the calendar fallback - the float fidelity is what the
    backend guarantees here.)"""
    pid = _policy(db, code="WAREHOUSE_FAST", tiers=[(1, Decimal("0.5"), Decimal("1.0"))])
    svc = ConversationSLATrackingService(db)
    tier = svc._resolve_tier_with_clamp(pid, 1)
    assert tier is not None
    assert float(tier.response_hours) == 0.5
