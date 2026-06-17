"""TCK-2026-000032 — SLA KPI aggregations.

Covers AC-32-F1 (summary reconciles), F2 (per-task rows + trigger split),
F4 (scope partition), F5 (split-clock met/breach), leaderboard.

Run: pytest tests/test_sla_kpi.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.access import RespondContact
from app.models.lookup import LookupBinding
from app.models.sla import ConversationSLATracking, ConversationSLAEventLog, SLAPolicy
from app.models.user import User
from app.services import sla_kpi_service as kpi


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.types import JSON as GenericJSON
    for col in list(RespondContact.__table__.columns):
        if isinstance(col.type, JSONB):
            col.type = GenericJSON()
            col.server_default = None
    Base.metadata.create_all(engine, tables=[
        SLAPolicy.__table__, ConversationSLATracking.__table__, ConversationSLAEventLog.__table__,
        RespondContact.__table__, User.__table__, LookupBinding.__table__,
    ])
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def seed(db):
    now = datetime.utcnow()
    pid = str(uuid.uuid4())
    db.add(SLAPolicy(id=pid, code="P", name="P"))
    u1, u2 = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(User(id=u1, email="a@t.com", name="Alice"))
    db.add(User(id=u2, email="b@t.com", name="Bob"))

    def trk(**kw):
        base = dict(
            id=str(uuid.uuid4()), policy_id=pid, current_tier=1,
            initiated_at=now - timedelta(days=1), current_tier_started_at=now - timedelta(days=1),
            due_at=now - timedelta(hours=2), is_responded=False, is_resolved=False,
        )
        base.update(kw)
        t = ConversationSLATracking(**base)
        db.add(t)
        return t

    # T1: form complaint, responded on time, resolved on time
    t1 = trk(source_entity_type="complaint", source_entity_id="c1", assigned_to_id=u1,
             is_responded=True, responded_at=now - timedelta(hours=3), due_at=now - timedelta(hours=2),
             is_resolved=True, resolved_at=now - timedelta(hours=1), due_at_resolution=now + timedelta(hours=1),
             response_time=2.0, resolution_duration=5.0)
    # T2: form complaint, responded LATE, unresolved past resolution due (breach both clocks)
    t2 = trk(source_entity_type="complaint", source_entity_id="c2", assigned_to_id=u1,
             is_responded=True, responded_at=now, due_at=now - timedelta(hours=2),
             is_resolved=False, due_at_resolution=now - timedelta(hours=1),
             response_time=8.0)
    # T3: conversation (no source entity type), responded on time
    t3 = trk(source_entity_type=None, source_entity_id=None, assigned_to_id=u2,
             is_responded=True, responded_at=now - timedelta(hours=3), due_at=now - timedelta(hours=2),
             response_time=1.0)
    db.flush()
    # T2 escalations: 1 auto + 1 manual
    for trig in ("auto", "manual"):
        db.add(ConversationSLAEventLog(
            id=str(uuid.uuid4()), sla_tracking_id=t2.id, event_type="escalation",
            from_tier=1, to_tier=2, event_at=now, trigger=trig,
        ))
    db.commit()
    return {"u1": u1, "u2": u2, "t1": t1.id, "t2": t2.id}


def test_summary_form_scope_reconciles(db, seed):
    s = kpi.kpi_summary(db, scope="form")
    assert s["opened"] == 2  # T1, T2 (not T3 conversation)
    assert s["responded"] == 2
    assert s["resolved"] == 1
    assert s["response_met"] == 1  # T1 on time
    assert s["response_breach"] == 1  # T2 late
    assert s["pct_response_met"] == 50.0
    assert s["resolution_met"] == 1  # T1
    assert s["resolution_breach"] == 1  # T2 unresolved past due
    assert s["escalated"] == 2 and s["escalated_auto"] == 1 and s["escalated_manual"] == 1


def test_scope_partition(db, seed):
    assert kpi.kpi_summary(db, scope="conversation")["opened"] == 1  # T3 only
    assert kpi.kpi_summary(db, scope="all")["opened"] == 3


def test_tasks_rows_and_trigger_split(db, seed):
    res = kpi.kpi_tasks(db, scope="form")
    assert res["total"] == 2
    by_id = {r["tracking_id"]: r for r in res["data"]}
    assert by_id[seed["t1"]]["response_met"] is True
    assert by_id[seed["t1"]]["resolution_met"] is True
    assert by_id[seed["t2"]]["response_met"] is False
    assert by_id[seed["t2"]]["escalations_manual"] == 1
    assert by_id[seed["t2"]]["escalations_auto"] == 1
    # names resolved, no raw UUID leak in name field
    assert by_id[seed["t1"]]["assignee_name"] == "Alice"


def test_leaderboard(db, seed):
    lb = {r["assignee_id"]: r for r in kpi.kpi_leaderboard(db, scope="form")}
    assert lb[seed["u1"]]["total"] == 2
    assert lb[seed["u1"]]["resolved"] == 1
    assert lb[seed["u1"]]["assignee_name"] == "Alice"
    assert lb[seed["u1"]]["breach_count"] >= 2  # T2 response + resolution breach


def test_avg_and_median_response(db, seed):
    s = kpi.kpi_summary(db, scope="form")
    # response_time 2.0 + 8.0 -> avg 5.0, median 5.0
    assert s["avg_response_time_hours"] == 5.0
    assert s["median_response_time_hours"] == 5.0
