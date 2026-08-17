"""S5b staleness ladder (UAC Group H: AC-H2, AC-H4, AC-H6).

The ladder decides when to tap somebody on the shoulder about a project nobody has
touched. Two properties matter more than the arithmetic:

1. **It cannot be gamed.** Opening the record, fixing a typo or re-running an import must
   not look like work (AC-H2). If it did, the whole ladder becomes decorative within a
   week of somebody noticing.
2. **It never reassigns anything.** Level 3 opens the project to takeover REQUESTS and
   says so; a manager still decides (AC-H6). An ownership change nobody chose is how a
   pipeline tool loses the sales team.

Tests run on Postgres via ``blank_session``. Every row carries the zzt marker so a
cleanup can never reach real data.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.status import Status
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-stale"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


@pytest.fixture()
def seeded():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Owner")
        yield db, str(company_id), owner


def _status_id(db, key: str) -> str:
    return str(
        db.query(Status.id)
        .filter(
            Status.entity_type == "project",
            Status.scope_id.is_(None),
            Status.key == key,
        )
        .scalar()
    )


def _project(db, company_id, owner, *, status_key="registered", idle_days=0, title=None):
    from app.models.projects import Project
    from app.services import project_service as prj

    project = prj.register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=title or f"{MARKER} {uuid.uuid4().hex[:10]}",
        owner_user_id=owner,
    )
    db.flush()
    # Arranged directly: walking the funnel rung by rung is S2's test, and the ladder
    # only cares which rung the project SITS on.
    project.status_id = _status_id(db, status_key)
    project.last_meaningful_activity_at = datetime.utcnow() - timedelta(days=idle_days)
    db.flush()
    return project


# ------------------------------------------------------------------ thresholds


def test_the_seeded_funnel_carries_staleness_thresholds():
    """AC-H4. A ladder with no thresholds never fires, which reads as "not built"."""
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)

        by_key = {
            s.key: s.stale_after_days
            for s in db.query(Status)
            .filter(Status.entity_type == "project", Status.scope_id.is_(None))
            .all()
        }
        for key in ("identified", "registered", "specified", "quoted", "tendering"):
            assert by_key[key] is not None, f"{key} has no threshold"
        # Later rungs are tighter: a project in Tendering left alone for a month is a
        # different problem from one sitting at Identified.
        assert by_key["tendering"] < by_key["registered"]
        # Terminal rungs never go stale -- there is nothing to chase on a lost project.
        assert by_key["lost"] is None
        assert by_key["po_received"] is None


def test_a_tuned_threshold_survives_reseeding():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)

        quoted = (
            db.query(Status)
            .filter(
                Status.entity_type == "project",
                Status.scope_id.is_(None),
                Status.key == "quoted",
            )
            .first()
        )
        quoted.stale_after_days = 3
        db.flush()

        project_seed_service.run(db, company_id=company_id)
        db.refresh(quoted)
        assert quoted.stale_after_days == 3


# ------------------------------------------------------------------ the ladder


def test_a_project_touched_today_is_not_stale(seeded):
    from app.services import project_staleness_service as svc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, idle_days=0)

    result = svc.evaluate(db, project=project)
    assert result["level"] == 0
    assert result["reason"] is None


def test_the_ladder_climbs_one_rung_per_threshold_multiple(seeded):
    """AC-H6. Nudge at the threshold, warn at twice it, unattended at three times.

    Multiples rather than three separately configured numbers: an admin who tunes one
    number gets a coherent ladder, and nobody has to explain why level 2 fires before
    level 1 because somebody typed the days in the wrong order.
    """
    from app.services import project_staleness_service as svc

    db, company_id, owner = seeded
    threshold = svc.threshold_for(db, project=_project(db, company_id, owner))
    assert threshold, "the seeded Registered rung must have a threshold"

    for idle, expected in (
        (threshold - 1, 0),
        (threshold, 1),
        (threshold * 2, 2),
        (threshold * 3, 3),
        (threshold * 10, 3),
    ):
        project = _project(db, company_id, owner, idle_days=idle)
        result = svc.evaluate(db, project=project)
        assert result["level"] == expected, f"{idle} idle days should be level {expected}"
        if expected:
            assert result["reason"] == "no_activity"


def test_a_rung_with_no_threshold_never_goes_stale(seeded):
    """A terminal project is not neglected, it is finished."""
    from app.services import project_staleness_service as svc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="registered", idle_days=999)
    project.status_id = _status_id(db, "po_received")
    db.flush()

    assert svc.evaluate(db, project=project)["level"] == 0


def test_a_lost_project_is_never_chased(seeded):
    """Outcome, not just status: a project marked lost while still sitting on a live rung
    is a decided ending, and nagging its owner about it is noise."""
    from app.models.projects import OUTCOME_LOST
    from app.services import project_staleness_service as svc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, idle_days=999)
    project.outcome = OUTCOME_LOST
    db.flush()

    assert svc.evaluate(db, project=project)["level"] == 0


def test_an_overdue_task_drives_the_ladder_ahead_of_inactivity(seeded):
    """AC-H3. The overdue next action is the PRIMARY trigger.

    A project worked on yesterday but carrying a task that was due three weeks ago is
    not idle -- it is late. Reporting it as fine until inactivity catches up would hide
    exactly the case the client described.
    """
    from app.services import project_staleness_service as svc
    from app.services import project_task_service as tasks

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, idle_days=0)
    threshold = svc.threshold_for(db, project=project)

    tasks.create_task(
        db,
        project=project,
        actor_user_id=owner,
        permissions={"projects.projects.edit"},
        payload={
            "name": f"{MARKER} chase the developer",
            "assignee_user_id": owner,
            "due_date": (datetime.utcnow() - timedelta(days=threshold + 1)).date(),
        },
    )
    db.flush()
    # create_task counts as meaningful work, so the inactivity clock is at zero here.
    project.last_meaningful_activity_at = datetime.utcnow()
    db.flush()

    result = svc.evaluate(db, project=project)
    assert result["level"] >= 1
    assert result["reason"] == "overdue_task"


def test_an_open_task_due_tomorrow_keeps_the_project_off_the_ladder(seeded):
    """Having a plan IS the work. A project with an in-date task is not neglected even
    when nobody has typed anything for a while."""
    from app.services import project_staleness_service as svc
    from app.services import project_task_service as tasks

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, idle_days=90)
    tasks.create_task(
        db,
        project=project,
        actor_user_id=owner,
        permissions={"projects.projects.edit"},
        payload={
            "name": f"{MARKER} site visit booked",
            "assignee_user_id": owner,
            "due_date": (datetime.utcnow() + timedelta(days=1)).date(),
        },
    )
    project.last_meaningful_activity_at = datetime.utcnow() - timedelta(days=90)
    db.flush()

    assert svc.evaluate(db, project=project)["level"] == 0


# ------------------------------------------------------------------ the sweep


def test_the_sweep_stamps_the_level_and_reports_what_it_did(seeded):
    from app.services import project_staleness_service as svc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, idle_days=400)

    summary = svc.sweep(db)
    db.refresh(project)

    assert summary["scanned"] >= 1
    assert summary["raised"] >= 1
    assert project.stale_level == 3
    assert project.stale_reason == "no_activity"
    assert project.stale_since is not None


def test_the_sweep_is_idempotent_and_does_not_renotify(seeded):
    """A daily sweep that re-notifies every morning trains people to filter the alert."""
    from app.services import project_staleness_service as svc

    db, company_id, owner = seeded
    _project(db, company_id, owner, idle_days=400)

    first = svc.sweep(db)
    second = svc.sweep(db)
    assert first["raised"] >= 1
    assert second["raised"] == 0
    assert second["unchanged"] >= 1


def test_real_work_clears_the_ladder(seeded):
    """AC-H2. The way off the ladder is to do something, and it takes effect at once."""
    from app.services import project_activity_service as activity
    from app.services import project_staleness_service as svc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, idle_days=400)
    svc.sweep(db)
    db.refresh(project)
    assert project.stale_level == 3

    activity.record_project_event(
        db, project=project, template="stage_changed", actor_id=owner
    )
    db.flush()

    assert project.stale_level == 0
    assert project.stale_since is None
    summary = svc.sweep(db)
    db.refresh(project)
    assert project.stale_level == 0
    assert summary["raised"] == 0


def test_only_whitelisted_system_events_count_as_work(seeded):
    """AC-H2. An import or a field edit must not reset the clock."""
    from app.services import project_activity_service as activity

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, idle_days=400)
    was = project.last_meaningful_activity_at

    activity.record_project_event(
        db, project=project, template="imported", actor_id=owner
    )
    db.flush()
    assert project.last_meaningful_activity_at == was

    activity.record_project_event(
        db, project=project, template="po_recorded", actor_id=owner
    )
    db.flush()
    assert project.last_meaningful_activity_at > was


def test_a_human_post_always_counts_as_work(seeded):
    """A salesperson writing "developer says decision moved to March" is the single most
    valuable thing in the record, so a user post advances the clock unconditionally."""
    from app.services import project_activity_service as activity

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, idle_days=400)
    was = project.last_meaningful_activity_at

    activity.note_user_activity(db, project_id=str(project.id), actor_id=owner)
    db.flush()
    db.refresh(project)
    assert project.last_meaningful_activity_at > was
    assert project.stale_level == 0


def test_unattended_opens_the_project_to_takeover_but_reassigns_nothing(seeded):
    """AC-H6, the line that matters most in this group."""
    from app.services import project_staleness_service as svc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, idle_days=400)
    svc.sweep(db)
    db.refresh(project)

    assert project.stale_level == 3
    assert svc.is_unattended(project) is True
    # The owner is untouched. Nothing in this slice may change it.
    assert project.owner_user_id == owner
