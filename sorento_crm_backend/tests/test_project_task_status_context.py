"""S2b — Escalate and Stuck force their context (AC-N4a).

The rule exists because a task reading "Escalated" with nobody named, or "Stuck" with
no reason, tells the next person nothing and is worse than leaving it In Progress: it
looks like the problem is being handled when nobody owns it.

Enforced SERVER-side. The dialog in the UI is a convenience; anything posting straight
to the API must hit the same wall, or the guarantee is decorative.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.projects import Project, ProjectTask
from app.models.status import Status, StatusTransition
from app.models.user import User
from app.services import project_task_service as tasks
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-tctx"
ENTITY = "project_task"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _status(db, key, label, **flags):
    row = Status(
        id=_uid(),
        entity_type=ENTITY,
        key=key,
        label=label,
        sort_order=flags.pop("order", 0),
        **flags,
    )
    db.add(row)
    db.flush()
    return row


def _graph(db):
    """The five ecohub rungs, fully connected from Not Started / In Progress.

    Escalate and Stuck are reachable from the live rungs because a task gets stuck or
    escalated at any point, not at one designated moment.
    """
    not_started = _status(db, "not_started", "Not Started", is_initial=True, order=0)
    in_progress = _status(db, "in_progress", "In Progress", order=1)
    escalate = _status(db, "escalate", "Escalate", order=2)
    stuck = _status(db, "stuck", "Stuck", order=3)
    done = _status(db, "done", "Done", is_terminal=True, order=4)

    edges = [
        (not_started, in_progress),
        (not_started, escalate),
        (not_started, stuck),
        (in_progress, escalate),
        (in_progress, stuck),
        (in_progress, done),
        (escalate, in_progress),
        (escalate, done),
        (stuck, in_progress),
        (stuck, escalate),
    ]
    for src, dst in edges:
        db.add(
            StatusTransition(
                id=_uid(),
                entity_type=ENTITY,
                from_status_id=src.id,
                to_status_id=dst.id,
                label=f"{src.key}->{dst.key}",
                trigger_mode="manual",
            )
        )
    db.flush()
    return {
        "not_started": not_started,
        "in_progress": in_progress,
        "escalate": escalate,
        "stuck": stuck,
        "done": done,
    }


def _project(db, company_id: str, owner: str) -> Project:
    project = Project(
        id=_uid(),
        company_id=company_id,
        project_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
        title="Setia Alam Phase 3B",
        normalised_title="setia alam phase 3b",
        owner_user_id=owner,
    )
    db.add(project)
    db.flush()
    return project


def _task(db, project: Project, status: Status, **kwargs) -> ProjectTask:
    task = ProjectTask(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        name=f"{MARKER} Visit the specifying architect",
        status_id=status.id,
        **kwargs,
    )
    db.add(task)
    db.flush()
    return task


def test_escalating_without_naming_anyone_is_refused():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        graph = _graph(db)
        project = _project(db, company_id, owner)
        task = _task(db, project, graph["in_progress"])

        with pytest.raises(AppException) as exc:
            tasks.change_task_status(
                db,
                task=task,
                project=project,
                to_status_id=graph["escalate"].id,
                actor_user_id=owner,
                permissions=set(),
            )

        assert exc.value.status_code == 422
        assert "escalat" in exc.value.detail["message"].lower()
        # Nothing partially applied: the task is still where it was.
        assert task.status_id == graph["in_progress"].id
        assert task.escalated_to_user_id is None


def test_escalating_to_a_named_person_is_accepted_and_recorded():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        manager = _user(db, f"{MARKER} Eric")
        graph = _graph(db)
        project = _project(db, company_id, owner)
        task = _task(db, project, graph["in_progress"])

        tasks.change_task_status(
            db,
            task=task,
            project=project,
            to_status_id=graph["escalate"].id,
            actor_user_id=owner,
            permissions=set(),
            escalated_to_user_id=manager,
        )

        assert task.status_id == graph["escalate"].id
        assert task.escalated_to_user_id == manager


def test_getting_stuck_without_a_reason_is_refused():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        graph = _graph(db)
        project = _project(db, company_id, owner)
        task = _task(db, project, graph["in_progress"])

        with pytest.raises(AppException) as exc:
            tasks.change_task_status(
                db,
                task=task,
                project=project,
                to_status_id=graph["stuck"].id,
                actor_user_id=owner,
                permissions=set(),
            )

        assert exc.value.status_code == 422
        assert "reason" in exc.value.detail["message"].lower()
        assert task.status_id == graph["in_progress"].id


def test_a_whitespace_only_reason_does_not_count_as_a_reason():
    """A space bar is the path of least resistance past a required field."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        graph = _graph(db)
        project = _project(db, company_id, owner)
        task = _task(db, project, graph["in_progress"])

        with pytest.raises(AppException) as exc:
            tasks.change_task_status(
                db,
                task=task,
                project=project,
                to_status_id=graph["stuck"].id,
                actor_user_id=owner,
                permissions=set(),
                stuck_reason="   ",
            )
        assert exc.value.status_code == 422


def test_getting_stuck_with_a_reason_is_accepted_and_recorded():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        graph = _graph(db)
        project = _project(db, company_id, owner)
        task = _task(db, project, graph["in_progress"])

        tasks.change_task_status(
            db,
            task=task,
            project=project,
            to_status_id=graph["stuck"].id,
            actor_user_id=owner,
            permissions=set(),
            stuck_reason="Waiting on the architect to confirm the tile spec.",
        )

        assert task.status_id == graph["stuck"].id
        assert task.stuck_reason == "Waiting on the architect to confirm the tile spec."


def test_moving_off_escalate_clears_the_escalation():
    """Otherwise the card still reads "Escalated to Eric" after Eric handed it back,
    and the next reader chases the wrong person."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        manager = _user(db, f"{MARKER} Eric")
        graph = _graph(db)
        project = _project(db, company_id, owner)
        task = _task(
            db, project, graph["escalate"], escalated_to_user_id=manager
        )

        tasks.change_task_status(
            db,
            task=task,
            project=project,
            to_status_id=graph["in_progress"].id,
            actor_user_id=owner,
            permissions=set(),
        )

        assert task.status_id == graph["in_progress"].id
        assert task.escalated_to_user_id is None


def test_moving_off_stuck_clears_the_reason():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        graph = _graph(db)
        project = _project(db, company_id, owner)
        task = _task(db, project, graph["stuck"], stuck_reason="Waiting on the spec.")

        tasks.change_task_status(
            db,
            task=task,
            project=project,
            to_status_id=graph["in_progress"].id,
            actor_user_id=owner,
            permissions=set(),
        )

        assert task.stuck_reason is None


def test_going_from_stuck_to_escalate_swaps_the_context():
    """The common real path: stuck long enough that it gets escalated.

    Both required fields are in play at once -- the old reason must go and the new
    escalation must be named, or the card carries a stale reason next to a live
    escalation.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        manager = _user(db, f"{MARKER} Eric")
        graph = _graph(db)
        project = _project(db, company_id, owner)
        task = _task(db, project, graph["stuck"], stuck_reason="No reply for 2 weeks.")

        tasks.change_task_status(
            db,
            task=task,
            project=project,
            to_status_id=graph["escalate"].id,
            actor_user_id=owner,
            permissions=set(),
            escalated_to_user_id=manager,
        )

        assert task.escalated_to_user_id == manager
        assert task.stuck_reason is None


def test_escalating_to_a_user_who_does_not_exist_is_refused():
    """A dangling id renders as a blank name, which reads as "escalated to nobody"."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        graph = _graph(db)
        project = _project(db, company_id, owner)
        task = _task(db, project, graph["in_progress"])

        with pytest.raises(AppException) as exc:
            tasks.change_task_status(
                db,
                task=task,
                project=project,
                to_status_id=graph["escalate"].id,
                actor_user_id=owner,
                permissions=set(),
                escalated_to_user_id=_uid(),
            )
        assert exc.value.status_code == 422


def test_completing_a_task_stamps_when_it_was_done():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        graph = _graph(db)
        project = _project(db, company_id, owner)
        task = _task(db, project, graph["in_progress"])

        tasks.change_task_status(
            db,
            task=task,
            project=project,
            to_status_id=graph["done"].id,
            actor_user_id=owner,
            permissions=set(),
        )

        assert task.completed_at is not None


def test_reopening_clears_the_completion_stamp_when_the_graph_allows_it():
    """A stale ``completed_at`` on a reopened task hides it from every open-task list,
    My Tasks included -- the work would silently vanish from the person's worklist.

    The seeded default makes Done terminal, so this needs a graph where Done is
    reopenable. That is a legitimate admin configuration (work often turns out
    unfinished), which is exactly why the clearing is not dead code.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")

        not_started = _status(db, "not_started", "Not Started", is_initial=True, order=0)
        in_progress = _status(db, "in_progress", "In Progress", order=1)
        # Reopenable Done: same stable key, is_terminal off, an edge back.
        done = _status(db, "done", "Done", order=2)
        for src, dst in ((not_started, in_progress), (in_progress, done), (done, in_progress)):
            db.add(
                StatusTransition(
                    id=_uid(),
                    entity_type=ENTITY,
                    from_status_id=src.id,
                    to_status_id=dst.id,
                    label=f"{src.key}->{dst.key}",
                    trigger_mode="manual",
                )
            )
        db.flush()

        project = _project(db, company_id, owner)
        task = _task(db, project, in_progress)

        tasks.change_task_status(
            db, task=task, project=project, to_status_id=done.id,
            actor_user_id=owner, permissions=set(),
        )
        assert task.completed_at is not None

        tasks.change_task_status(
            db, task=task, project=project, to_status_id=in_progress.id,
            actor_user_id=owner, permissions=set(),
        )
        assert task.completed_at is None


def test_a_terminal_done_cannot_be_reopened_under_the_seeded_graph():
    """The engine owns this, not the task service: the seeded Done is terminal, so the
    move is refused rather than quietly allowed by task-specific code."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        graph = _graph(db)
        project = _project(db, company_id, owner)
        task = _task(db, project, graph["done"])

        with pytest.raises(AppException) as exc:
            tasks.change_task_status(
                db, task=task, project=project, to_status_id=graph["in_progress"].id,
                actor_user_id=owner, permissions=set(),
            )
        assert exc.value.status_code == 422


def test_an_illegal_task_transition_is_rejected(monkeypatch):
    """AC-N4: the task graph is enforced exactly like the project graph."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        graph = _graph(db)
        project = _project(db, company_id, owner)
        # Done is terminal with no outgoing edges, so nothing may follow it.
        task = _task(db, project, graph["done"])

        with pytest.raises(AppException) as exc:
            tasks.change_task_status(
                db,
                task=task,
                project=project,
                to_status_id=graph["in_progress"].id,
                actor_user_id=owner,
                permissions=set(),
            )
        assert exc.value.status_code == 422
