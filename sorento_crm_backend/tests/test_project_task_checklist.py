"""S2b - template checklists, derived next action, My Tasks (AC-N1, N6, N9, N11).

The load-bearing claim in this slice is AC-N6: a project's next action is DERIVED from
its earliest open task and stored nowhere. Two records of the same promise drift, and
the one nobody updates is the one the pipeline report reads.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.projects import (
    Project,
    ProjectTask,
    ProjectTemplate,
    ProjectTemplateTask,
    ProjectType,
)
from app.models.status import Status, StatusTransition
from app.models.user import User
from app.services import project_task_service as tasks
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-chk"
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


def _task_graph(db):
    not_started = Status(
        id=_uid(),
        entity_type=ENTITY,
        key="not_started",
        label="Not Started",
        is_initial=True,
        sort_order=0,
    )
    in_progress = Status(
        id=_uid(), entity_type=ENTITY, key="in_progress", label="In Progress", sort_order=1
    )
    done = Status(
        id=_uid(),
        entity_type=ENTITY,
        key="done",
        label="Done",
        is_terminal=True,
        sort_order=2,
    )
    db.add_all([not_started, in_progress, done])
    db.flush()
    for src, dst in ((not_started, in_progress), (in_progress, done), (not_started, done)):
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
    return not_started, in_progress, done


def _template(db, company_id: str) -> ProjectTemplate:
    ptype = ProjectType(
        id=_uid(),
        company_id=company_id,
        name=f"{MARKER} Property Development",
        code=f"{MARKER}-prop",
    )
    db.add(ptype)
    db.flush()
    template = ProjectTemplate(
        id=_uid(), company_id=company_id, type_id=ptype.id, name=f"{MARKER} High Rise"
    )
    db.add(template)
    db.flush()
    return template


def _template_task(db, template, name, *, offset=None, phase="pursuit", category=None, order=0):
    row = ProjectTemplateTask(
        id=_uid(),
        company_id=template.company_id,
        template_id=template.id,
        name=name,
        task_phase=phase,
        category=category,
        sort_order=order,
        default_offset_days=offset,
    )
    db.add(row)
    db.flush()
    return row


def _project(db, company_id, owner, *, template=None, outcome="open") -> Project:
    project = Project(
        id=_uid(),
        company_id=company_id,
        project_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
        title="Setia Alam Phase 3B",
        normalised_title=f"setia alam {uuid.uuid4().hex[:6]}",
        owner_user_id=owner,
        template_id=template.id if template else None,
        outcome=outcome,
    )
    db.add(project)
    db.flush()
    return project


def test_a_template_checklist_is_instantiated_onto_the_project():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        not_started, _ip, _done = _task_graph(db)
        template = _template(db, company_id)
        _template_task(db, template, "Visit the architect", offset=7, category="Spec-in", order=0)
        _template_task(db, template, "Submit quotation", offset=30, category="Commercial", order=1)
        project = _project(db, company_id, owner, template=template)

        created = tasks.instantiate_template_tasks(
            db, project=project, actor_user_id=owner, reference_date=date(2026, 1, 1)
        )

        assert [t.name for t in created] == ["Visit the architect", "Submit quotation"]
        assert [t.due_date for t in created] == [date(2026, 1, 8), date(2026, 1, 31)]
        assert [t.category for t in created] == ["Spec-in", "Commercial"]
        # Every task starts on the graph's first rung, same as the project does.
        assert {t.status_id for t in created} == {not_started.id}


def test_a_template_task_without_an_offset_gets_no_due_date():
    """"Chase the PO" depends on events, not elapsed time.

    Inventing a date would put a fake overdue badge on the project and train people to
    ignore the real ones.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        _task_graph(db)
        template = _template(db, company_id)
        _template_task(db, template, "Chase the PO", offset=None)
        project = _project(db, company_id, owner, template=template)

        created = tasks.instantiate_template_tasks(db, project=project)

        assert created[0].due_date is None


def test_instantiating_twice_does_not_duplicate_the_checklist():
    """Re-applying a repaired template must not double every task."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        _task_graph(db)
        template = _template(db, company_id)
        _template_task(db, template, "Visit the architect", offset=7)
        project = _project(db, company_id, owner, template=template)

        tasks.instantiate_template_tasks(db, project=project)
        second = tasks.instantiate_template_tasks(db, project=project)

        assert second == []
        assert db.query(ProjectTask).filter(ProjectTask.project_id == project.id).count() == 1


def test_a_deactivated_template_task_is_not_instantiated():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        _task_graph(db)
        template = _template(db, company_id)
        retired = _template_task(db, template, "Fax the drawings", offset=3)
        retired.is_active = False
        db.flush()
        _template_task(db, template, "Email the drawings", offset=3, order=1)
        project = _project(db, company_id, owner, template=template)

        created = tasks.instantiate_template_tasks(db, project=project)

        assert [t.name for t in created] == ["Email the drawings"]


def test_a_project_with_no_template_gets_no_checklist():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        _task_graph(db)
        project = _project(db, company_id, owner)

        assert tasks.instantiate_template_tasks(db, project=project) == []


def test_a_checklist_still_instantiates_before_the_task_graph_is_configured():
    """The checklist is worth having on day one; refusing would make template
    instantiation fail the whole registration."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        template = _template(db, company_id)
        _template_task(db, template, "Visit the architect", offset=7)
        project = _project(db, company_id, owner, template=template)

        created = tasks.instantiate_template_tasks(db, project=project)

        assert len(created) == 1
        assert created[0].status_id is None


# ----------------------------------------------------- derived next action


def test_the_next_action_is_the_earliest_open_task():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        not_started, _ip, done = _task_graph(db)
        project = _project(db, company_id, owner)

        for name, due in (
            ("Later", date.today() + timedelta(days=20)),
            ("Sooner", date.today() + timedelta(days=3)),
        ):
            db.add(
                ProjectTask(
                    id=_uid(),
                    company_id=company_id,
                    project_id=project.id,
                    name=name,
                    status_id=not_started.id,
                    due_date=due,
                )
            )
        db.flush()

        derived = tasks.next_action_for_projects(db, [project.id])[project.id]

        assert derived["next_action_date"] == date.today() + timedelta(days=3)
        assert derived["open_task_count"] == 2
        assert derived["next_action_overdue"] is False


def test_a_completed_task_is_not_the_next_action():
    """Otherwise finishing the soonest task never advances the next action, and the
    project looks permanently due."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        not_started, _ip, done = _task_graph(db)
        project = _project(db, company_id, owner)

        db.add(
            ProjectTask(
                id=_uid(),
                company_id=company_id,
                project_id=project.id,
                name="Done already",
                status_id=done.id,
                due_date=date.today() - timedelta(days=5),
            )
        )
        db.add(
            ProjectTask(
                id=_uid(),
                company_id=company_id,
                project_id=project.id,
                name="Still open",
                status_id=not_started.id,
                due_date=date.today() + timedelta(days=9),
            )
        )
        db.flush()

        derived = tasks.next_action_for_projects(db, [project.id])[project.id]

        assert derived["next_action_date"] == date.today() + timedelta(days=9)
        assert derived["open_task_count"] == 1


def test_an_overdue_next_action_is_flagged():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        not_started, _ip, _done = _task_graph(db)
        project = _project(db, company_id, owner)
        db.add(
            ProjectTask(
                id=_uid(),
                company_id=company_id,
                project_id=project.id,
                name="Overdue",
                status_id=not_started.id,
                due_date=date.today() - timedelta(days=2),
            )
        )
        db.flush()

        derived = tasks.next_action_for_projects(db, [project.id])[project.id]

        assert derived["next_action_overdue"] is True


def test_a_project_with_no_open_tasks_has_no_next_action_entry():
    """Absent, not a null date: "no next action" and "next action with no date" are
    different states and the worklist treats them differently."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        _task_graph(db)
        project = _project(db, company_id, owner)

        assert tasks.next_action_for_projects(db, [project.id]) == {}


def test_undated_open_work_still_counts_as_open_without_setting_a_date():
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        not_started, _ip, _done = _task_graph(db)
        project = _project(db, company_id, owner)
        db.add(
            ProjectTask(
                id=_uid(),
                company_id=company_id,
                project_id=project.id,
                name="Chase the PO",
                status_id=not_started.id,
                due_date=None,
            )
        )
        db.flush()

        derived = tasks.next_action_for_projects(db, [project.id])[project.id]

        assert derived["open_task_count"] == 1
        assert derived["next_action_date"] is None
        assert derived["next_action_overdue"] is False


# ------------------------------------------------------------- My Tasks


def test_my_tasks_puts_dated_work_before_undated():
    """Postgres sorts NULLs FIRST on ASC, which would bury every overdue task under
    the undated ones -- the exact opposite of a worklist."""
    with blank_session() as db:
        company_id = _sorento(db)
        me = _user(db, f"{MARKER} Ali")
        not_started, _ip, _done = _task_graph(db)
        project = _project(db, company_id, me)

        for name, due in (
            ("No date", None),
            ("Overdue", date.today() - timedelta(days=3)),
            ("Next week", date.today() + timedelta(days=7)),
        ):
            db.add(
                ProjectTask(
                    id=_uid(),
                    company_id=company_id,
                    project_id=project.id,
                    name=name,
                    status_id=not_started.id,
                    assignee_user_id=me,
                    due_date=due,
                )
            )
        db.flush()

        rows, total = tasks.my_tasks(db, user_id=me, company_id=company_id)

        assert total == 3
        assert [t.name for t in rows] == ["Overdue", "Next week", "No date"]


def test_my_tasks_shows_only_my_open_tasks():
    with blank_session() as db:
        company_id = _sorento(db)
        me = _user(db, f"{MARKER} Ali")
        someone_else = _user(db, f"{MARKER} Siti")
        not_started, _ip, done = _task_graph(db)
        project = _project(db, company_id, me)

        db.add_all([
            ProjectTask(
                id=_uid(), company_id=company_id, project_id=project.id,
                name="Mine open", status_id=not_started.id, assignee_user_id=me,
            ),
            ProjectTask(
                id=_uid(), company_id=company_id, project_id=project.id,
                name="Mine done", status_id=done.id, assignee_user_id=me,
            ),
            ProjectTask(
                id=_uid(), company_id=company_id, project_id=project.id,
                name="Theirs", status_id=not_started.id, assignee_user_id=someone_else,
            ),
        ])
        db.flush()

        rows, total = tasks.my_tasks(db, user_id=me, company_id=company_id)

        assert [t.name for t in rows] == ["Mine open"]
        assert total == 1


def test_my_tasks_shows_work_escalated_to_me():
    """Escalating to somebody who cannot see it is not an escalation.

    The task stays assigned to whoever was already on it -- escalation asks for help,
    it does not hand the work over -- so the escalatee only ever learns about it if
    their own worklist surfaces it.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        me = _user(db, f"{MARKER} Ali")
        assignee = _user(db, f"{MARKER} Siti")
        not_started, _ip, _done = _task_graph(db)
        project = _project(db, company_id, assignee)

        db.add(
            ProjectTask(
                id=_uid(),
                company_id=company_id,
                project_id=project.id,
                name="Escalated to me",
                status_id=not_started.id,
                assignee_user_id=assignee,
                escalated_to_user_id=me,
            )
        )
        db.flush()

        rows, total = tasks.my_tasks(db, user_id=me, company_id=company_id)

        assert [t.name for t in rows] == ["Escalated to me"]
        assert total == 1


def test_my_tasks_can_include_unassigned_work_on_projects_i_own():
    """An unassigned task on my own project is still my problem; without this it is
    invisible until someone happens to open the project."""
    with blank_session() as db:
        company_id = _sorento(db)
        me = _user(db, f"{MARKER} Ali")
        other_owner = _user(db, f"{MARKER} Siti")
        not_started, _ip, _done = _task_graph(db)
        mine = _project(db, company_id, me)
        theirs = _project(db, company_id, other_owner)

        db.add_all([
            ProjectTask(
                id=_uid(), company_id=company_id, project_id=mine.id,
                name="Unassigned on mine", status_id=not_started.id,
            ),
            ProjectTask(
                id=_uid(), company_id=company_id, project_id=theirs.id,
                name="Unassigned on theirs", status_id=not_started.id,
            ),
        ])
        db.flush()

        default_rows, _ = tasks.my_tasks(db, user_id=me, company_id=company_id)
        assert default_rows == []

        rows, total = tasks.my_tasks(
            db, user_id=me, company_id=company_id, include_unassigned_owned=True
        )
        assert [t.name for t in rows] == ["Unassigned on mine"]
        assert total == 1


# ------------------------------------------------------------ phase default


def test_the_tasks_tab_opens_on_the_phase_that_is_live():
    """AC-N3: pursuit while the project is being chased, delivery once it is won."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        open_project = _project(db, company_id, owner, outcome="open")
        won_project = _project(db, company_id, owner, outcome="won")

        assert tasks.default_phase_for(open_project) == "pursuit"
        assert tasks.default_phase_for(won_project) == "delivery"


# ------------------------------------------------------------------ AC-N8


def test_creating_and_completing_a_task_advances_the_projects_activity_clock():
    """AC-N8. Real work advances staleness; editing a description does not."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        not_started, in_progress, done = _task_graph(db)
        project = _project(db, company_id, owner)
        assert project.last_meaningful_activity_at is None

        task = tasks.create_task(
            db,
            project=project,
            payload={"name": "Visit the architect"},
            actor_user_id=owner,
            permissions=set(),
        )
        after_create = project.last_meaningful_activity_at
        assert after_create is not None

        tasks.update_task(
            db,
            task=task,
            project=project,
            payload={"description": "Bring the sample board"},
            actor_user_id=owner,
            permissions=set(),
        )
        assert project.last_meaningful_activity_at == after_create

        tasks.change_task_status(
            db,
            task=task,
            project=project,
            to_status_id=done.id,
            actor_user_id=owner,
            permissions=set(),
        )
        assert project.last_meaningful_activity_at > after_create


# ----------------------------------------------------------------- AC-N11


def test_a_template_task_that_projects_reference_cannot_be_deleted():
    """AC-N11: deactivate instead. Deleting would erase the provenance of live work."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        _task_graph(db)
        template = _template(db, company_id)
        template_task = _template_task(db, template, "Visit the architect", offset=7)
        project = _project(db, company_id, owner, template=template)
        tasks.instantiate_template_tasks(db, project=project)

        with pytest.raises(AppException) as exc:
            tasks.delete_template_task(db, template_task=template_task)

        assert exc.value.status_code == 409
        assert "deactivate" in exc.value.detail["message"].lower()


def test_an_unused_template_task_can_be_deleted():
    with blank_session() as db:
        company_id = _sorento(db)
        _task_graph(db)
        template = _template(db, company_id)
        template_task = _template_task(db, template, "Fax the drawings", offset=3)

        tasks.delete_template_task(db, template_task=template_task)

        assert (
            db.query(ProjectTemplateTask)
            .filter(ProjectTemplateTask.id == template_task.id)
            .first()
            is None
        )


def test_editing_a_template_checklist_does_not_retro_apply_to_existing_projects():
    """AC-N11. A project's checklist is a snapshot of the template at registration;
    silently adding tasks to live projects would rewrite what people committed to."""
    with blank_session() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        _task_graph(db)
        template = _template(db, company_id)
        _template_task(db, template, "Visit the architect", offset=7)
        project = _project(db, company_id, owner, template=template)
        tasks.instantiate_template_tasks(db, project=project)

        _template_task(db, template, "New step added later", offset=14, order=5)

        assert (
            db.query(ProjectTask).filter(ProjectTask.project_id == project.id).count() == 1
        )


# ------------------------------------------------------- history (AC-N7)


@contextmanager
def _session_owning_the_task_audit_trail():
    """A session where the audit rows for a task are the ones this file writes.

    The audit listeners are global and installed by whoever reaches
    ``register_audit_listeners`` first - the app at startup, and ``test_customer_audit``
    in a suite run - so whether merely seeding a ProjectTask ALSO writes a CREATE row
    depends on which files ran before this one. These three tests state the trail they
    render in full, so they turn the per-row listener off for ``project_tasks`` (the same
    documented hook a bulk import uses) instead of passing alone and failing in a full
    run, which reads as flakiness rather than as an ordering dependency.
    """
    with blank_session() as db:
        db.info["skip_audit_entity_types"] = {ProjectTask.__audit_entity_type__}
        yield db


def test_task_history_reads_from_the_audit_trail_with_readable_values():
    """A timeline row saying "status_id changed from 6dca3796 to f8744fb5" is
    technically a history and practically useless, so ids are resolved to labels.

    No dedicated history table (AC-N7): the audit listeners already capture per-field
    diffs with an actor, and a second store drifts from the first.
    """
    from app.models.audit import AuditLog

    with _session_owning_the_task_audit_trail() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        eric = _user(db, f"{MARKER} Eric")
        not_started, in_progress, _done = _task_graph(db)
        project = _project(db, company_id, owner)
        task = ProjectTask(
            id=_uid(),
            company_id=company_id,
            project_id=project.id,
            name="Visit the architect",
            status_id=not_started.id,
        )
        db.add(task)
        db.flush()

        # Stand in for the audit listeners, which fire on a real request flush. The
        # action is the one THEY write - "CREATE"; "INSERT" only ever came from a
        # hand-written call - so a timeline that renders this row renders a real one.
        #
        # `changed_at` is stamped EXPLICITLY, a minute apart. Its server default is
        # `now()`, which in Postgres is the TRANSACTION timestamp, so two rows added
        # in this one session get the identical value and the timeline's
        # `order_by(changed_at)` is then free to return them either way round. That
        # tie passed locally and failed in CI, reading as "created" arriving second.
        created_at = datetime(2026, 7, 1, 9, 0, 0)
        db.add(
            AuditLog(
                id=_uid(),
                entity_type="project_tasks",
                entity_id=task.id,
                action="CREATE",
                user_id=owner,
                new_values={"name": "Visit the architect"},
                changed_at=created_at,
            )
        )
        db.add(
            AuditLog(
                id=_uid(),
                entity_type="project_tasks",
                entity_id=task.id,
                action="UPDATE",
                user_id=owner,
                old_values={"status_id": not_started.id, "assignee_user_id": None},
                new_values={"status_id": in_progress.id, "assignee_user_id": eric},
                changed_at=created_at + timedelta(minutes=1),
            )
        )
        db.flush()

        history = tasks.task_history(db, task.id)

        assert history[0]["action"] == "created"
        assert history[0]["actor_name"] == f"{MARKER} Ali"
        changes = {(h["field"], h["from_value"], h["to_value"]) for h in history[1:]}
        assert ("Status", "Not Started", "In Progress") in changes
        assert ("Assignee", None, f"{MARKER} Eric") in changes


def test_task_history_ignores_noise_fields():
    """`updated_at` churn and drag-reorder `sort_order` changes would drown the
    changes people actually look for."""
    from app.models.audit import AuditLog

    with _session_owning_the_task_audit_trail() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        not_started, _ip, _done = _task_graph(db)
        project = _project(db, company_id, owner)
        task = ProjectTask(
            id=_uid(),
            company_id=company_id,
            project_id=project.id,
            name="Visit the architect",
            status_id=not_started.id,
        )
        db.add(task)
        db.flush()
        db.add(
            AuditLog(
                id=_uid(),
                entity_type="project_tasks",
                entity_id=task.id,
                action="UPDATE",
                user_id=owner,
                old_values={"sort_order": 0, "updated_at": "2026-01-01T00:00:00"},
                new_values={"sort_order": 3, "updated_at": "2026-01-02T00:00:00"},
            )
        )
        db.flush()

        assert tasks.task_history(db, task.id) == []


def test_a_task_with_no_audit_rows_has_an_empty_history():
    with _session_owning_the_task_audit_trail() as db:
        company_id = _sorento(db)
        owner = _user(db, f"{MARKER} Ali")
        not_started, _ip, _done = _task_graph(db)
        project = _project(db, company_id, owner)
        task = ProjectTask(
            id=_uid(),
            company_id=company_id,
            project_id=project.id,
            name="Fresh",
            status_id=not_started.id,
        )
        db.add(task)
        db.flush()

        assert tasks.task_history(db, task.id) == []
