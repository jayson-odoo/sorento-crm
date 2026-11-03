"""MYTEAM-BY-SEGMENT: My Team shows only tasks whose contact segment / brand the viewer serves.

One team (DO Customer Service) holds retail AND project CS. A viewer whose membership is
tagged with segments / brands sees a teammate's task only when the task's contact segments
overlap theirs and the task's brand is one they serve. Untagged = serves all; a contact with
no segment (or a task with no brand) narrows nobody. Same rule as the round-robin pool.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.access import (
    MarketSegment,
    RespondContact,
    Team,
    TeamMember,
    team_member_brands,
    team_member_market_segments,
)
from app.models.sla import ConversationSLATracking, SLAPolicy
from app.models.user import User
from app.services.market_segment_service import member_serves_segments
from app.services.sla_service import ConversationSLATrackingService
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        # descendant_team_ids() runs raw text() SQL over an unqualified `teams`.
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


def _user(db, name) -> str:
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{name}@x.com", name=name, status="ACTIVE"))
    db.commit()
    return uid


def _segments(db, *codes):
    for i, code in enumerate(codes):
        db.add(MarketSegment(code=code, name=code.title(), sort_order=i))
    db.commit()


def _member(db, team_id, user_id, *, segments=(), brands=()) -> str:
    mid = str(uuid.uuid4())
    db.add(TeamMember(id=mid, team_id=team_id, user_id=user_id))
    db.commit()
    for code in segments:
        db.execute(
            team_member_market_segments.insert().values(team_member_id=mid, segment_code=code)
        )
    for code in brands:
        db.execute(team_member_brands.insert().values(team_member_id=mid, brand_code=code))
    db.commit()
    return mid


def _contact(db, *segments) -> str:
    cid = str(uuid.uuid4())
    contact = RespondContact(id=cid, phone_number=f"+60{uuid.uuid4().int % 10**10:010d}")
    db.add(contact)
    db.flush()
    if segments:
        contact.market_segments = (
            db.query(MarketSegment).filter(MarketSegment.code.in_(segments)).all()
        )
    db.commit()
    return cid


def _track(db, pid, *, assignee, contact=None, brand=None, due_h=1) -> str:
    tid = str(uuid.uuid4())
    db.add(
        ConversationSLATracking(
            id=tid,
            policy_id=pid,
            current_tier=1,
            assigned_to_id=assignee,
            due_at=datetime(2026, 6, 1) + timedelta(hours=due_h),
            is_resolved=False,
            source_entity_type="stock_inquiry",
            source_entity_id=str(uuid.uuid4()),
            respond_contact_id=contact,
            brand_code=brand,
        )
    )
    db.commit()
    return tid


@pytest.fixture
def do_cs(db):
    """DO Customer Service: project CS, retail CS, an untagged lead, plus a third
    teammate who holds every task so all three viewers can see them."""
    _segments(db, "project", "retail")
    pid = str(uuid.uuid4())
    db.add(SLAPolicy(id=pid, code="p", name="Policy"))
    db.commit()
    team = str(uuid.uuid4())
    db.add(Team(id=team, name="DO Customer Service"))
    db.commit()
    project_cs = _user(db, "project_cs")
    retail_cs = _user(db, "retail_cs")
    lead = _user(db, "lead")
    holder = _user(db, "holder")
    _member(db, team, project_cs, segments=["project"])
    _member(db, team, retail_cs, segments=["retail"])
    _member(db, team, lead)
    _member(db, team, holder)
    tasks = {
        "project": _track(db, pid, assignee=holder, contact=_contact(db, "project"), due_h=1),
        "retail": _track(db, pid, assignee=holder, contact=_contact(db, "retail"), due_h=2),
        "untagged": _track(db, pid, assignee=holder, contact=_contact(db), due_h=3),
        "no_contact": _track(db, pid, assignee=holder, due_h=4),
    }
    return {
        "pid": pid,
        "team": team,
        "project_cs": project_cs,
        "retail_cs": retail_cs,
        "lead": lead,
        "holder": holder,
        "tasks": tasks,
    }


def _ids(db, viewer) -> set[str]:
    out = ConversationSLATrackingService(db).list_team_pending(viewer)
    ids = {r["id"] for r in out["data"]}
    assert out["total"] == len(ids)
    return ids


def test_project_cs_sees_project_not_retail(db, do_cs):
    t = do_cs["tasks"]
    ids = _ids(db, do_cs["project_cs"])
    assert t["project"] in ids
    assert t["retail"] not in ids


def test_retail_cs_sees_retail_not_project(db, do_cs):
    t = do_cs["tasks"]
    ids = _ids(db, do_cs["retail_cs"])
    assert t["retail"] in ids
    assert t["project"] not in ids


def test_untagged_lead_sees_everything(db, do_cs):
    assert _ids(db, do_cs["lead"]) == set(do_cs["tasks"].values())


def test_contact_without_segment_visible_to_all(db, do_cs):
    t = do_cs["tasks"]
    for viewer in ("project_cs", "retail_cs", "lead"):
        ids = _ids(db, do_cs[viewer])
        assert t["untagged"] in ids, viewer
        assert t["no_contact"] in ids, viewer


def test_paginated_total_counts_only_visible(db, do_cs):
    out = ConversationSLATrackingService(db).list_team_pending(
        do_cs["project_cs"], page=1, limit=1
    )
    # project, untagged, no_contact -> 3 (retail filtered out in the count too).
    assert out["total"] == 3
    assert len(out["data"]) == 1


def test_brand_filters_tasks(db, do_cs):
    mocha_cs = _user(db, "mocha_cs")
    _member(db, do_cs["team"], mocha_cs, brands=["Mocha"])
    pid = do_cs["pid"]
    mocha = _track(db, pid, assignee=do_cs["holder"], brand="mocha", due_h=5)
    cabana = _track(db, pid, assignee=do_cs["holder"], brand="cabana", due_h=6)

    ids = _ids(db, mocha_cs)
    assert mocha in ids
    assert cabana not in ids
    # No segment tag on this viewer -> every segment still visible.
    assert do_cs["tasks"]["retail"] in ids and do_cs["tasks"]["project"] in ids
    # Untagged lead sees both brands.
    lead_ids = _ids(db, do_cs["lead"])
    assert {mocha, cabana} <= lead_ids


def test_member_serves_segments_rule():
    assert member_serves_segments(set(), {"retail"}) is True  # untagged member
    assert member_serves_segments({"project"}, set()) is True  # untagged contact
    assert member_serves_segments({"project"}, {"retail"}) is False
    assert member_serves_segments({"project", "retail"}, {"retail"}) is True


def test_active_coverage_shows_covered_colleague_tasks_in_full(db, do_cs):
    """Crew ruling 3 Nov: while I hold an active coverage of a colleague, that colleague's
    tasks show on My Team unfiltered, so the coverage deep link never opens an empty list."""
    from app.models.notification import NotificationSubscription

    pid = do_cs["pid"]
    project_cs, retail_cs = do_cs["project_cs"], do_cs["retail_cs"]
    retail_contact = _contact(db, "retail")
    covered_task = _track(db, pid, assignee=retail_cs, contact=retail_contact, due_h=7)

    # Without coverage: the retail CS's retail task stays hidden from project CS.
    assert covered_task not in _ids(db, project_cs)

    # An expired / inactive coverage does not lift the filter.
    db.add(
        NotificationSubscription(
            id=str(uuid.uuid4()),
            subscriber_id=project_cs,
            target_user_id=retail_cs,
            is_active=True,
            expires_at=datetime(2020, 1, 1),
        )
    )
    db.commit()
    assert covered_task not in _ids(db, project_cs)

    db.query(NotificationSubscription).delete()
    db.add(
        NotificationSubscription(
            id=str(uuid.uuid4()),
            subscriber_id=project_cs,
            target_user_id=retail_cs,
            is_active=True,
        )
    )
    db.commit()
    ids = _ids(db, project_cs)
    assert covered_task in ids
    # The coverage lifts the filter for the covered colleague only: the holder's
    # retail task is still hidden.
    assert do_cs["tasks"]["retail"] not in ids
