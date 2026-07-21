"""TCK-2026-000032 — SLA KPI aggregations.

Covers AC-32-F1 (summary reconciles), F2 (per-task rows + trigger split),
F4 (scope partition), F5 (split-clock met/breach), leaderboard.

Run: pytest tests/test_sla_kpi.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.access import RespondContact
from app.models.sla import ConversationSLATracking, ConversationSLAEventLog, SLAPolicy
from app.models.user import User
from app.services import sla_kpi_service as kpi
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


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


def test_stage_partition_is_mece(db, seed):
    s = kpi.kpi_summary(db, scope="form")
    # T1 resolved, T2 responded-not-resolved, no pending in form scope
    assert s["stage_resolved"] == 1
    assert s["stage_responded_open"] == 1
    assert s["stage_pending"] == 0
    # MECE: the three buckets are mutually exclusive and sum to the total (opened)
    assert s["stage_pending"] + s["stage_responded_open"] + s["stage_resolved"] == s["opened"]
    assert s["pct_stage_resolved"] == 50.0
    assert s["pct_stage_responded_open"] == 50.0

    # 'all' scope adds T3 (responded, not resolved -> responded_open bucket)
    a = kpi.kpi_summary(db, scope="all")
    assert a["stage_pending"] + a["stage_responded_open"] + a["stage_resolved"] == a["opened"] == 3
    assert a["stage_responded_open"] == 2  # T2 + T3
    assert a["stage_resolved"] == 1        # T1


def test_timeliness_drilldown_subset_scoped(db, seed):
    s = kpi.kpi_summary(db, scope="form")
    # Responded subset (T1 on time, T2 late) -> within 1, overdue 1
    assert s["responded"] == 2
    assert s["responded_within"] == 1
    assert s["responded_overdue"] == 1
    assert s["responded_within"] + s["responded_overdue"] == s["responded"]  # MECE within subset
    assert s["pct_responded_within"] == 50.0
    # Resolved subset (only T1, on time) -> within 1, overdue 0
    assert s["resolved"] == 1
    assert s["resolved_within"] == 1
    assert s["resolved_overdue"] == 0
    assert s["pct_resolved_within"] == 100.0


def test_open_work_at_risk_drilldown(db, seed):
    s = kpi.kpi_summary(db, scope="form")
    # Form open work: only T2 (responded, unresolved, resolution due in the past -> overdue)
    assert s["stage_responded_open"] == 1
    assert s["responded_open_overdue"] == 1
    assert s["responded_open_within"] == 0
    assert s["responded_open_within"] + s["responded_open_overdue"] == s["stage_responded_open"]
    assert s["stage_pending"] == 0
    assert s["pending_within"] == 0 and s["pending_overdue"] == 0

    # 'all' adds T3 (responded, unresolved, NO resolution due -> on-track/within)
    a = kpi.kpi_summary(db, scope="all")
    assert a["stage_responded_open"] == 2  # T2 + T3
    assert a["responded_open_overdue"] == 1  # T2
    assert a["responded_open_within"] == 1   # T3 (null resolution due => within)
    assert a["responded_open_within"] + a["responded_open_overdue"] == a["stage_responded_open"]


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


def test_tasks_view_state_filter_reconciles_with_cards(db, seed):
    s = kpi.kpi_summary(db, scope="form")
    # view=resolved -> the resolved subset; state filters within/overdue match card counts
    assert kpi.kpi_tasks(db, scope="form", view="resolved")["total"] == s["resolved"]
    assert kpi.kpi_tasks(db, scope="form", view="resolved", state="within")["total"] == s["resolved_within"]
    assert kpi.kpi_tasks(db, scope="form", view="resolved", state="overdue")["total"] == s["resolved_overdue"]
    # view=responded within/overdue
    assert kpi.kpi_tasks(db, scope="form", view="responded")["total"] == s["responded"]
    assert kpi.kpi_tasks(db, scope="form", view="responded", state="overdue")["total"] == s["responded_overdue"]
    # open work: responded_open overdue list == card count
    assert kpi.kpi_tasks(db, scope="form", view="responded_open", state="overdue")["total"] == s["responded_open_overdue"]
    # all scope: pending list (none in seed) + responded_open within/overdue reconcile
    a = kpi.kpi_summary(db, scope="all")
    assert kpi.kpi_tasks(db, scope="all", view="responded_open", state="within")["total"] == a["responded_open_within"]
    assert kpi.kpi_tasks(db, scope="all", view="pending")["total"] == a["stage_pending"]


def test_tasks_escalates_at_payload(db, seed):
    by_id = {r["tracking_id"]: r for r in kpi.kpi_tasks(db, scope="all")["data"]}
    # T1 resolved -> nothing left to escalate.
    assert by_id[seed["t1"]]["escalates_at"] is None
    # T2 responded, unresolved -> escalates on the resolution clock.
    t2 = by_id[seed["t2"]]
    assert t2["escalates_at"] is not None
    assert t2["escalates_at"] == t2["resolution_due"]


def test_tasks_esc_window_overdue(db, seed):
    # T2's resolution clock is 1h in the past -> overdue catches it; T1 (resolved) excluded.
    overdue = kpi.kpi_tasks(db, scope="form", esc_window="overdue")
    assert {r["tracking_id"] for r in overdue["data"]} == {seed["t2"]}
    # A tight future window excludes the already-overdue T2.
    assert kpi.kpi_tasks(db, scope="form", esc_window="1h")["total"] == 0


def test_tasks_esc_window_future(db, seed):
    now = datetime.utcnow()
    pid = db.query(SLAPolicy).first().id
    tid = str(uuid.uuid4())
    # Pending (unresponded) row escalating on the response clock 2h out.
    db.add(ConversationSLATracking(
        id=tid, policy_id=pid, current_tier=1,
        source_entity_type="complaint", source_entity_id="c9",
        initiated_at=now, current_tier_started_at=now,
        due_at=now + timedelta(hours=2), is_responded=False, is_resolved=False,
    ))
    db.commit()
    assert tid in {r["tracking_id"] for r in kpi.kpi_tasks(db, scope="form", esc_window="4h")["data"]}
    assert tid not in {r["tracking_id"] for r in kpi.kpi_tasks(db, scope="form", esc_window="1h")["data"]}


def test_tasks_sort_response_time(db, seed):
    # response_time: T3=1.0, T1=2.0, T2=8.0 (all scope). Sort maps FE key -> column.
    asc = [r["response_time_hours"] for r in kpi.kpi_tasks(db, scope="all", sort="response_time_hours", dir="asc")["data"]]
    assert asc == [1.0, 2.0, 8.0]
    desc = [r["response_time_hours"] for r in kpi.kpi_tasks(db, scope="all", sort="response_time_hours", dir="desc")["data"]]
    assert desc == [8.0, 2.0, 1.0]


def test_tasks_sort_assignee_name(db, seed):
    # Joined-name sort: Alice (T1,T2) before Bob (T3) ascending.
    names = [r["assignee_name"] for r in kpi.kpi_tasks(db, scope="all", sort="assignee_name", dir="asc")["data"]]
    assert names == sorted(names)
    assert names[0] == "Alice" and names[-1] == "Bob"


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
