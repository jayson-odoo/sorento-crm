"""Project task service (S2b, UAC Group N).

A task is work someone plans on a project. It is deliberately not a ticket: a ticket is
raised BY someone about a problem and carries SLA clocks and Respond.io links.

Tasks are also what make a project's next action derivable, which is why no
``next_action_date`` column exists anywhere (AC-N6).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.projects import (
    TASK_LINK_TYPES,
    TASK_PHASES,
    TASK_PHASE_DELIVERY,
    TASK_PHASE_PURSUIT,
    Project,
    ProjectTask,
    ProjectTemplateTask,
)
from app.models.status import Status
from app.schemas.common import MAX_PAGE_LIMIT
from app.services.error_handler import AppException

TASK_ENTITY_TYPE = "project_task"

# Status keys that cannot be entered without their context (AC-N4a). Keyed on the
# stable ``key``, never the label: an admin renaming "Escalate" to "Needs Help" must
# not silently disable the guard, and ``key`` is the identifier the engine promises is
# stable across forked graphs.
STATUS_KEY_ESCALATE = "escalate"
STATUS_KEY_STUCK = "stuck"
STATUS_KEY_DONE = "done"


def _status_or_422(db: Session, status_id: str) -> Status:
    status = db.query(Status).filter(Status.id == status_id).first()
    if status is None or status.entity_type != TASK_ENTITY_TYPE:
        raise AppException(
            status_code=422,
            message="That task status does not exist.",
            code="project_task_status_invalid",
        )
    return status


def _assert_user_exists(db: Session, user_id: str) -> None:
    from app.models.user import User

    if db.query(User.id).filter(User.id == user_id).first() is None:
        raise AppException(
            status_code=422,
            message="That person could not be found.",
            code="project_task_escalate_user_invalid",
        )


def can_edit_task(
    db: Session,
    task: ProjectTask,
    project: Project,
    user_id: str,
    permissions: Set[str],
) -> bool:
    """Whoever can edit the project, plus the task's own assignee (AC-N10).

    The assignee is included because the work is theirs: a task assigned to someone who
    then cannot mark it done is a task that never gets marked done.
    """
    from app.services.project_service import can_edit_project

    if task.assignee_user_id and task.assignee_user_id == user_id:
        return True
    return can_edit_project(db, project, user_id, permissions)


def assert_can_edit_task(
    db: Session,
    task: ProjectTask,
    project: Project,
    user_id: str,
    permissions: Set[str],
) -> None:
    if can_edit_task(db, task, project, user_id, permissions):
        return
    raise AppException(
        status_code=403,
        message=(
            f"This task belongs to {project.project_code}, which another salesperson "
            "owns. Ask to join the project, or have the task assigned to you."
        ),
        code="project_task_not_editable",
    )


def change_task_status(
    db: Session,
    *,
    task: ProjectTask,
    project: Project,
    to_status_id: str,
    actor_user_id: str,
    permissions: Set[str],
    escalated_to_user_id: Optional[str] = None,
    stuck_reason: Optional[str] = None,
) -> ProjectTask:
    """Move a task, enforcing both the graph and the required context.

    Validation order matters: the context requirement is checked BEFORE anything is
    written, so a refused move leaves the task exactly as it was rather than
    half-escalated.
    """
    assert_can_edit_task(db, task, project, actor_user_id, permissions)

    target = _status_or_422(db, to_status_id)

    if target.key == STATUS_KEY_ESCALATE:
        if not escalated_to_user_id:
            raise AppException(
                status_code=422,
                message=(
                    "Say who you are escalating to. An escalated task with nobody "
                    "named looks handled when it is not."
                ),
                code="project_task_escalate_requires_user",
            )
        _assert_user_exists(db, escalated_to_user_id)

    if target.key == STATUS_KEY_STUCK and not (stuck_reason or "").strip():
        raise AppException(
            status_code=422,
            message=(
                "Say what you are stuck on. Without a reason nobody else can unblock "
                "it."
            ),
            code="project_task_stuck_requires_reason",
        )

    from app.services import status_service

    scope_id = _task_scope_id(project)
    if task.status_id is None:
        initial = status_service.initial_status(db, TASK_ENTITY_TYPE, scope_id)
        if to_status_id != initial.id:
            raise AppException(
                status_code=422,
                message=(
                    f"This task has no status yet, so it can only start at "
                    f"'{initial.label}'."
                ),
                code="project_task_status_not_started",
            )
    else:
        status_service.assert_transition_allowed(
            db, TASK_ENTITY_TYPE, task.status_id, to_status_id, scope_id=scope_id
        )

    task.status_id = to_status_id

    # The context belongs to the status, so leaving a status clears it. A card still
    # reading "Escalated to Eric" after Eric handed it back sends the next reader to
    # the wrong person.
    task.escalated_to_user_id = (
        escalated_to_user_id if target.key == STATUS_KEY_ESCALATE else None
    )
    task.stuck_reason = (
        stuck_reason.strip() if target.key == STATUS_KEY_STUCK and stuck_reason else None
    )

    # completed_at tracks the terminal rung, both ways: a stale stamp on a reopened
    # task would hide it from every open-task list, My Tasks included.
    if target.is_terminal or target.key == STATUS_KEY_DONE:
        task.completed_at = task.completed_at or datetime.utcnow()
    else:
        task.completed_at = None

    db.flush()
    _touch_project_activity(db, project, task_completed=bool(task.completed_at))
    return task


def _task_scope_id(project: Project) -> Optional[str]:
    """A task's graph is scoped by its PROJECT's template, one hop away.

    This is exactly why the status registry takes a ``scope_resolver`` callable rather
    than a column name on the record.
    """
    return getattr(project, "template_id", None)


# --------------------------------------------------------------- activity

# AC-N8 extends the AC-H2 whitelist: creating or completing a task is real work, so it
# advances the project's staleness clock. Editing a description is not.
def _touch_project_activity(
    db: Session, project: Project, *, task_completed: bool = False, task_created: bool = False
) -> None:
    if not (task_completed or task_created):
        return
    project.last_meaningful_activity_at = datetime.utcnow()
    db.flush()


# ------------------------------------------------------------ instantiation


def instantiate_template_tasks(
    db: Session,
    *,
    project: Project,
    template_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    reference_date: Optional[date] = None,
) -> List[ProjectTask]:
    """Create a project's opening checklist from its template (AC-N1).

    Due dates come from ``default_offset_days`` counted from the project's
    registration date. A template task with no offset produces a task with no due
    date, which is honest for "chase the PO" where the date depends on events rather
    than elapsed time -- inventing one would put a fake overdue badge on every project.

    Idempotent per template task: re-running never duplicates a task that is already
    there, so a repaired or re-applied template does not double the checklist.
    """
    template_id = template_id or project.template_id
    if not template_id:
        return []

    anchor = reference_date or (
        project.created_at.date() if project.created_at else date.today()
    )

    template_tasks = (
        db.query(ProjectTemplateTask)
        .filter(
            ProjectTemplateTask.template_id == template_id,
            ProjectTemplateTask.is_active.is_(True),
        )
        .order_by(ProjectTemplateTask.sort_order.asc(), ProjectTemplateTask.name.asc())
        .all()
    )
    if not template_tasks:
        return []

    already = {
        row[0]
        for row in db.query(ProjectTask.source_template_task_id)
        .filter(
            ProjectTask.project_id == project.id,
            ProjectTask.source_template_task_id.isnot(None),
        )
        .all()
    }

    initial_status_id = _initial_task_status_id(db, project)

    created: List[ProjectTask] = []
    for template_task in template_tasks:
        if template_task.id in already:
            continue
        created.append(
            ProjectTask(
                company_id=project.company_id,
                project_id=project.id,
                name=template_task.name,
                description=template_task.description,
                task_phase=template_task.task_phase,
                category=template_task.category,
                status_id=initial_status_id,
                due_date=(
                    anchor + timedelta(days=template_task.default_offset_days)
                    if template_task.default_offset_days is not None
                    else None
                ),
                sort_order=template_task.sort_order,
                source_template_task_id=template_task.id,
                created_by=actor_user_id,
            )
        )
    for task in created:
        db.add(task)
    db.flush()
    return created


def _initial_task_status_id(db: Session, project: Project) -> Optional[str]:
    """None rather than an exception when no task graph is configured.

    A project's checklist is worth having even before an admin has built the task
    status graph; refusing would make template instantiation fail the whole
    registration.
    """
    from app.services import status_service

    try:
        return status_service.initial_status(
            db, TASK_ENTITY_TYPE, _task_scope_id(project)
        ).id
    except AppException:
        return None


# ------------------------------------------------------------------- CRUD


def _assert_phase(phase: Optional[str]) -> None:
    if phase and phase not in TASK_PHASES:
        raise AppException(
            status_code=422,
            message="A task phase must be either pursuit or delivery.",
            code="project_task_phase_invalid",
        )


def _assert_link(link_type: Optional[str], link_id: Optional[str]) -> None:
    if link_type and link_type not in TASK_LINK_TYPES:
        raise AppException(
            status_code=422,
            message=(
                "A task can link to a quotation version, a sample, or a purchase "
                "order."
            ),
            code="project_task_link_type_invalid",
        )
    # Half a link points nowhere and renders as a broken chip.
    if bool(link_type) != bool(link_id):
        raise AppException(
            status_code=422,
            message="A linked artifact needs both its type and its id.",
            code="project_task_link_incomplete",
        )


def create_task(
    db: Session,
    *,
    project: Project,
    payload: Dict[str, Any],
    actor_user_id: str,
    permissions: Set[str],
) -> ProjectTask:
    from app.services.project_service import assert_can_edit_project

    assert_can_edit_project(db, project, actor_user_id, permissions)

    name = (payload.get("name") or "").strip()
    if not name:
        raise AppException(
            status_code=422,
            message="A task needs a name.",
            code="project_task_name_required",
        )
    _assert_phase(payload.get("task_phase"))
    _assert_link(payload.get("linked_entity_type"), payload.get("linked_entity_id"))

    assignee = payload.get("assignee_user_id")
    if assignee:
        _assert_user_exists(db, assignee)

    task = ProjectTask(
        company_id=project.company_id,
        project_id=project.id,
        name=name,
        description=payload.get("description"),
        task_phase=payload.get("task_phase") or TASK_PHASE_PURSUIT,
        category=payload.get("category"),
        status_id=payload.get("status_id") or _initial_task_status_id(db, project),
        assignee_user_id=assignee,
        start_date=payload.get("start_date"),
        due_date=payload.get("due_date"),
        sort_order=int(payload.get("sort_order") or 0),
        linked_entity_type=payload.get("linked_entity_type"),
        linked_entity_id=payload.get("linked_entity_id"),
        created_by=actor_user_id,
    )
    db.add(task)
    db.flush()
    _touch_project_activity(db, project, task_created=True)
    return task


_EDITABLE_FIELDS = (
    "name",
    "description",
    "task_phase",
    "category",
    "assignee_user_id",
    "start_date",
    "due_date",
    "sort_order",
    "linked_entity_type",
    "linked_entity_id",
)


def update_task(
    db: Session,
    *,
    task: ProjectTask,
    project: Project,
    payload: Dict[str, Any],
    actor_user_id: str,
    permissions: Set[str],
) -> ProjectTask:
    """Edit a task's fields.

    Status is NOT editable here: it goes through ``change_task_status`` so the graph
    and the Escalate/Stuck context requirements cannot be bypassed by a plain field
    update.
    """
    assert_can_edit_task(db, task, project, actor_user_id, permissions)

    if "task_phase" in payload:
        _assert_phase(payload.get("task_phase"))
    if "linked_entity_type" in payload or "linked_entity_id" in payload:
        _assert_link(
            payload.get("linked_entity_type", task.linked_entity_type),
            payload.get("linked_entity_id", task.linked_entity_id),
        )
    if payload.get("assignee_user_id"):
        _assert_user_exists(db, payload["assignee_user_id"])

    if "name" in payload:
        name = (payload["name"] or "").strip()
        if not name:
            raise AppException(
                status_code=422,
                message="A task needs a name.",
                code="project_task_name_required",
            )
        payload["name"] = name

    for field in _EDITABLE_FIELDS:
        if field in payload:
            setattr(task, field, payload[field])
    db.flush()
    return task


def delete_task(
    db: Session,
    *,
    task: ProjectTask,
    project: Project,
    actor_user_id: str,
    permissions: Set[str],
) -> None:
    from app.services.project_service import assert_can_edit_project

    # Deleting is a project-owner act, not an assignee one: an assignee dropping a task
    # off the checklist would erase work the owner planned.
    assert_can_edit_project(db, project, actor_user_id, permissions)
    db.delete(task)
    db.flush()


def get_task_or_404(db: Session, project_id: str, task_id: str) -> ProjectTask:
    task = (
        db.query(ProjectTask)
        .filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id)
        .first()
    )
    if task is None:
        raise AppException(
            status_code=404,
            message="Task not found on this project.",
            code="project_task_not_found",
        )
    return task


# ------------------------------------------------------------------ queries


def list_tasks(
    db: Session,
    *,
    project_id: str,
    task_phase: Optional[str] = None,
) -> List[ProjectTask]:
    query = db.query(ProjectTask).filter(ProjectTask.project_id == project_id)
    if task_phase:
        _assert_phase(task_phase)
        query = query.filter(ProjectTask.task_phase == task_phase)
    return query.order_by(
        ProjectTask.sort_order.asc(), ProjectTask.created_at.asc()
    ).all()


def default_phase_for(project: Project) -> str:
    """The phase the Tasks tab opens on (AC-N3).

    Pursuit while the project is still being chased, delivery once it is won -- the
    tab should already be showing the work that is actually live.
    """
    return TASK_PHASE_DELIVERY if project.outcome == "won" else TASK_PHASE_PURSUIT


def open_task_status_ids(db: Session, scope_id: Optional[str] = None) -> List[str]:
    """Task statuses that count as still open.

    Terminal statuses are excluded, which is what "open" means for the next-action
    derivation and for My Tasks.
    """
    return [
        row[0]
        for row in db.query(Status.id)
        .filter(
            Status.entity_type == TASK_ENTITY_TYPE,
            Status.is_terminal.is_(False),
        )
        .all()
    ]


def next_action_for_projects(
    db: Session, project_ids: List[str]
) -> Dict[str, Dict[str, Any]]:
    """The earliest open task per project, which IS the next action (AC-N6).

    Derived, never stored. Two records of the same promise drift apart, and the one
    nobody updates is the one the pipeline report reads.

    Tasks with no due date are excluded from the DATE but still counted as open work,
    because "chase the PO, no date" is not a commitment to act by a particular day.
    """
    if not project_ids:
        return {}

    open_ids = open_task_status_ids(db)
    if not open_ids:
        return {}

    rows = (
        db.query(
            ProjectTask.project_id,
            func.min(ProjectTask.due_date).label("next_due"),
            func.count(ProjectTask.id).label("open_count"),
        )
        .filter(
            ProjectTask.project_id.in_(project_ids),
            ProjectTask.status_id.in_(open_ids),
            ProjectTask.completed_at.is_(None),
        )
        .group_by(ProjectTask.project_id)
        .all()
    )

    out: Dict[str, Dict[str, Any]] = {}
    today = date.today()
    for project_id, next_due, open_count in rows:
        out[project_id] = {
            "next_action_date": next_due,
            "open_task_count": open_count,
            "next_action_overdue": bool(next_due and next_due < today),
        }
    return out


def my_tasks(
    db: Session,
    *,
    user_id: str,
    company_id: str,
    include_unassigned_owned: bool = False,
    page: int = 1,
    limit: int = 50,
) -> tuple:
    """One user's open tasks across every project, overdue first (AC-N9).

    Not an ecohub pattern: its tasks live inside a single project because its user
    works one project at a time. Sorento has salespeople holding dozens of concurrent
    pursuits, so a cross-project worklist is the difference between a tool that gets
    opened daily and one that does not.

    Ordering puts dated work before undated: a task with no due date is real but it is
    not what you act on this morning. NULLS LAST is explicit because Postgres sorts
    NULLs first on ASC by default, which would bury every overdue task.
    """
    open_ids = open_task_status_ids(db)
    if not open_ids:
        return [], 0

    query = (
        db.query(ProjectTask)
        .join(Project, Project.id == ProjectTask.project_id)
        .filter(
            Project.company_id == company_id,
            ProjectTask.status_id.in_(open_ids),
            ProjectTask.completed_at.is_(None),
        )
    )
    # Escalated-to counts as mine. Escalation asks for help without handing the work
    # over, so the task stays with its assignee -- which means the escalatee learns about
    # it here or not at all.
    mine = or_(
        ProjectTask.assignee_user_id == user_id,
        ProjectTask.escalated_to_user_id == user_id,
    )
    if include_unassigned_owned:
        # A project owner's unassigned tasks are still their problem; without this they
        # are invisible to everyone until someone happens to open the project.
        mine = or_(
            mine,
            (ProjectTask.assignee_user_id.is_(None))
            & (Project.owner_user_id == user_id),
        )
    query = query.filter(mine)

    total = query.count()
    page = max(1, int(page or 1))
    limit = max(1, min(int(limit or 50), MAX_PAGE_LIMIT))
    rows = (
        query.order_by(
            ProjectTask.due_date.asc().nullslast(),
            ProjectTask.created_at.asc(),
        )
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return rows, total


# ------------------------------------------------- template checklist admin


def list_template_tasks(
    db: Session, *, template_id: str, include_inactive: bool = False
) -> List[ProjectTemplateTask]:
    query = db.query(ProjectTemplateTask).filter(
        ProjectTemplateTask.template_id == template_id
    )
    if not include_inactive:
        query = query.filter(ProjectTemplateTask.is_active.is_(True))
    return query.order_by(
        ProjectTemplateTask.sort_order.asc(), ProjectTemplateTask.name.asc()
    ).all()


def create_template_task(
    db: Session, *, template_id: str, company_id: str, payload: Dict[str, Any]
) -> ProjectTemplateTask:
    name = (payload.get("name") or "").strip()
    if not name:
        raise AppException(
            status_code=422,
            message="A checklist item needs a name.",
            code="project_template_task_name_required",
        )
    _assert_phase(payload.get("task_phase"))

    offset = payload.get("default_offset_days")
    if offset is not None and int(offset) < 0:
        raise AppException(
            status_code=422,
            message="A due-date offset counts days forward from registration, so it cannot be negative.",
            code="project_template_task_offset_invalid",
        )

    row = ProjectTemplateTask(
        template_id=template_id,
        company_id=company_id,
        name=name,
        description=payload.get("description"),
        task_phase=payload.get("task_phase") or TASK_PHASE_PURSUIT,
        category=payload.get("category"),
        sort_order=int(payload.get("sort_order") or 0),
        default_offset_days=offset,
        is_active=payload.get("is_active", True),
    )
    db.add(row)
    db.flush()
    return row


def get_template_task_or_404(db: Session, template_task_id: str) -> ProjectTemplateTask:
    row = (
        db.query(ProjectTemplateTask)
        .filter(ProjectTemplateTask.id == template_task_id)
        .first()
    )
    if row is None:
        raise AppException(
            status_code=404,
            message="Checklist item not found.",
            code="project_template_task_not_found",
        )
    return row


def update_template_task(
    db: Session, *, template_task: ProjectTemplateTask, payload: Dict[str, Any]
) -> ProjectTemplateTask:
    """Edits the TEMPLATE only.

    It never retro-applies to projects already created from it (AC-N11): a project's
    checklist is a snapshot of the template at registration, and silently rewriting
    live projects would change what people already committed to.
    """
    if "task_phase" in payload:
        _assert_phase(payload.get("task_phase"))
    if "name" in payload:
        name = (payload["name"] or "").strip()
        if not name:
            raise AppException(
                status_code=422,
                message="A checklist item needs a name.",
                code="project_template_task_name_required",
            )
        payload["name"] = name

    for field in (
        "name",
        "description",
        "task_phase",
        "category",
        "sort_order",
        "default_offset_days",
        "is_active",
    ):
        if field in payload:
            setattr(template_task, field, payload[field])
    db.flush()
    return template_task


def delete_template_task(db: Session, *, template_task: ProjectTemplateTask) -> None:
    """Blocked once any project's task came from it (AC-N11).

    The FK is ``ON DELETE SET NULL``, so deleting would silently sever the provenance
    of live work rather than failing loudly -- the task would stay on the project with
    no record of which checklist item it came from.
    """
    in_use = (
        db.query(func.count(ProjectTask.id))
        .filter(ProjectTask.source_template_task_id == template_task.id)
        .scalar()
    )
    if in_use:
        raise AppException(
            status_code=409,
            message=(
                f'"{template_task.name}" is already on {in_use} project'
                f'{"" if in_use == 1 else "s"}. Deactivate it instead of deleting, so '
                "new projects skip it while existing work keeps its history."
            ),
            code="project_template_task_in_use",
        )
    db.delete(template_task)
    db.flush()


# ------------------------------------------------------------ serialisation


def serialize_tasks(
    db: Session,
    tasks_in: List[ProjectTask],
    *,
    actor_user_id: Optional[str] = None,
    permissions: Optional[Set[str]] = None,
    projects_by_id: Optional[Dict[str, Project]] = None,
) -> List[Dict[str, Any]]:
    """Resolve names, statuses and the overdue flag in bulk.

    ``is_overdue`` and ``days_until_due`` are computed here rather than in the browser
    so a client in another timezone cannot disagree with the server about what is late.
    """
    if not tasks_in:
        return []

    permissions = permissions or set()

    if projects_by_id is None:
        project_ids = {t.project_id for t in tasks_in}
        projects_by_id = {
            p.id: p
            for p in db.query(Project).filter(Project.id.in_(project_ids)).all()
        }

    status_ids = {t.status_id for t in tasks_in if t.status_id}
    statuses = (
        {s.id: s for s in db.query(Status).filter(Status.id.in_(status_ids)).all()}
        if status_ids
        else {}
    )

    from app.services.project_service import resolve_user_names

    names = resolve_user_names(
        db,
        [t.assignee_user_id for t in tasks_in] + [t.escalated_to_user_id for t in tasks_in],
    )

    today = date.today()
    out: List[Dict[str, Any]] = []
    for task in tasks_in:
        status = statuses.get(task.status_id) if task.status_id else None
        project = projects_by_id.get(task.project_id)
        is_open = task.completed_at is None and not (status.is_terminal if status else False)
        out.append(
            {
                "id": task.id,
                "project_id": task.project_id,
                "project_code": getattr(project, "project_code", None),
                "project_title": getattr(project, "title", None),
                "name": task.name,
                "description": task.description,
                "task_phase": task.task_phase,
                "category": task.category,
                "status_id": task.status_id,
                "status_key": status.key if status else None,
                "status_label": status.label if status else None,
                "is_open": is_open,
                "assignee_user_id": task.assignee_user_id,
                "assignee_name": names.get(task.assignee_user_id),
                "escalated_to_user_id": task.escalated_to_user_id,
                "escalated_to_name": names.get(task.escalated_to_user_id),
                "stuck_reason": task.stuck_reason,
                "start_date": task.start_date,
                "due_date": task.due_date,
                "completed_at": task.completed_at,
                # Only OPEN work can be overdue. A task finished two days late is
                # history, not something to chase this morning.
                "is_overdue": bool(is_open and task.due_date and task.due_date < today),
                "days_until_due": (task.due_date - today).days if task.due_date else None,
                "sort_order": task.sort_order,
                "source_template_task_id": task.source_template_task_id,
                "linked_entity_type": task.linked_entity_type,
                "linked_entity_id": task.linked_entity_id,
                "can_edit": bool(
                    project is not None
                    and actor_user_id
                    and can_edit_task(db, task, project, actor_user_id, permissions)
                ),
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            }
        )
    return out


def serialize_template_tasks(
    db: Session, rows: List[ProjectTemplateTask]
) -> List[Dict[str, Any]]:
    if not rows:
        return []
    counts = dict(
        db.query(ProjectTask.source_template_task_id, func.count(ProjectTask.id))
        .filter(ProjectTask.source_template_task_id.in_([r.id for r in rows]))
        .group_by(ProjectTask.source_template_task_id)
        .all()
    )
    return [
        {
            "id": row.id,
            "template_id": row.template_id,
            "name": row.name,
            "description": row.description,
            "task_phase": row.task_phase,
            "category": row.category,
            "sort_order": row.sort_order,
            "default_offset_days": row.default_offset_days,
            "is_active": row.is_active,
            "in_use_count": counts.get(row.id, 0),
        }
        for row in rows
    ]


# ---------------------------------------------------------------- history


# Columns worth showing on a timeline. A diff of `updated_at` is noise, and
# `sort_order` churn from a drag-reorder would drown the changes people care about.
_HISTORY_FIELDS = {
    "name": "Name",
    "description": "Description",
    "status_id": "Status",
    "assignee_user_id": "Assignee",
    "escalated_to_user_id": "Escalated to",
    "stuck_reason": "Stuck reason",
    "start_date": "Start date",
    "due_date": "Due date",
    "completed_at": "Completed",
    "task_phase": "Phase",
    "category": "Category",
}

# The audit listener writes "CREATE" for a new row (audit_service._session_before_flush);
# older and hand-written rows say "INSERT". Reading only one of them is not a cosmetic
# miss: a creation that is not recognised as one falls through to the field diff below
# and the timeline opens with "Name changed to Visit the architect", "Status changed to
# Not Started" - every populated column reported as a change nobody made, and no "created"
# row at all. Same pair as activity_service._fe_action, for the same reason.
_CREATED_ACTIONS = ("CREATE", "INSERT")


def task_history(db: Session, task_id: str) -> List[Dict[str, Any]]:
    """One task's timeline, read from the audit trail (AC-N7).

    Status and user ids are resolved to labels and names: a timeline row reading
    "status_id changed from 6dca3796 to f8744fb5" is technically a history and
    practically useless.
    """
    from app.models.audit import AuditLog

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "project_tasks", AuditLog.entity_id == task_id)
        .order_by(AuditLog.changed_at.asc())
        .all()
    )
    if not rows:
        return []

    # Collect every id that appears on either side of a status/user change, so the
    # lookups are two queries rather than two per row.
    status_ids: set = set()
    user_ids: set = set()
    for row in rows:
        for values in (row.old_values or {}, row.new_values or {}):
            if values.get("status_id"):
                status_ids.add(values["status_id"])
            for field in ("assignee_user_id", "escalated_to_user_id"):
                if values.get(field):
                    user_ids.add(values[field])
        if row.user_id:
            user_ids.add(row.user_id)

    status_labels = (
        {s.id: s.label for s in db.query(Status).filter(Status.id.in_(status_ids)).all()}
        if status_ids
        else {}
    )
    from app.services.project_service import resolve_user_names

    names = resolve_user_names(db, list(user_ids))

    def _render(field: str, raw: Any) -> Optional[str]:
        if raw in (None, ""):
            return None
        if field == "status_id":
            return status_labels.get(raw, "a removed status")
        if field in ("assignee_user_id", "escalated_to_user_id"):
            return names.get(raw, "a removed user")
        return str(raw)

    out: List[Dict[str, Any]] = []
    for row in rows:
        actor = names.get(row.user_id) or "System"
        if row.action in _CREATED_ACTIONS:
            out.append(
                {
                    "at": row.changed_at,
                    "actor_name": actor,
                    "action": "created",
                    "field": None,
                    "from_value": None,
                    "to_value": (row.new_values or {}).get("name"),
                }
            )
            continue
        if row.action == "DELETE":
            out.append(
                {
                    "at": row.changed_at,
                    "actor_name": actor,
                    "action": "deleted",
                    "field": None,
                    "from_value": None,
                    "to_value": None,
                }
            )
            continue

        old = row.old_values or {}
        new = row.new_values or {}
        for field, label in _HISTORY_FIELDS.items():
            if field not in new:
                continue
            if old.get(field) == new.get(field):
                continue
            out.append(
                {
                    "at": row.changed_at,
                    "actor_name": actor,
                    "action": "changed",
                    "field": label,
                    "from_value": _render(field, old.get(field)),
                    "to_value": _render(field, new.get(field)),
                }
            )
    return out
