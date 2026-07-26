"""Status-engine entities owned by the Project Sales module.

Discovered by ``app/status_engine/discovery.py``; core never names this file.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.projects import Project, ProjectLead, ProjectTask
from app.modules.projects.bootstrap import MODULE_KEY
from app.status_engine.registry import StatusEntity, register_status_entity

PROJECT_ENTITY_TYPE = "project"
PROJECT_TASK_ENTITY_TYPE = "project_task"
PROJECT_LEAD_ENTITY_TYPE = "project_lead"


def _project_scope(record: Project) -> Optional[str]:
    """A project's graph belongs to its TEMPLATE, not the project.

    "Our status engine should be able to set for project entity, and overridable by
    template." A property development and a hotel fitout do not share a funnel, and
    the template is where that variation is already configured.

    Returns None for a template-less project, which resolves the default graph --
    templates are optional, and a renovation registered in a hurry has none.
    """
    return getattr(record, "template_id", None)


def _count_projects(db: Session, status_id: str) -> int:
    return db.query(Project).filter(Project.status_id == status_id).count()


def _migrate_projects(db: Session, from_status_id: str, to_status_id: str) -> int:
    return (
        db.query(Project)
        .filter(Project.status_id == from_status_id)
        .update({Project.status_id: to_status_id}, synchronize_session=False)
    )


def register() -> None:
    _register_project()
    _register_project_task()
    _register_project_lead()


def _register_project() -> None:
    register_status_entity(
        StatusEntity(
            entity_type=PROJECT_ENTITY_TYPE,
            label="Project",
            module=MODULE_KEY,
            count_records=_count_projects,
            migrate_records=_migrate_projects,
            model=Project,
            status_attr="status_id",
            record_label_attr="title",
            scope_resolver=_project_scope,
            scope_label="Template",
            # The funnel must terminate somewhere and start somewhere, or projects
            # are created status-less and nothing can ever be counted as closed.
            required_flags=["is_initial", "is_terminal"],
            # Whitelisted for auto-edge conditions. Deliberately narrow: outcome and
            # the critical flag are what a rule would gate on. NOT the whole schema
            # -- exposing every column makes every column a public contract.
            fact_attrs=("outcome", "is_critical", "developer_party_id", "type_id"),
        )
    )


def _project_task_scope(record: ProjectTask) -> Optional[str]:
    """A task's graph is its PROJECT's template, which is one hop from the record.

    This is the case the registry's ``scope_resolver`` callable exists for: a column
    name on the record could not express it, and a per-entity escape hatch would have
    been a second mechanism doing the same job.
    """
    project = getattr(record, "project", None)
    if project is not None:
        return getattr(project, "template_id", None)
    # No relationship loaded (the common path -- tasks are fetched flat), so resolve it
    # from the FK. Cheap: one indexed lookup, and only on transition checks.
    from app.models.projects import Project as _Project

    session = getattr(record, "_sa_instance_state", None)
    session = session.session if session is not None else None
    if session is None or not record.project_id:
        return None
    row = (
        session.query(_Project.template_id)
        .filter(_Project.id == record.project_id)
        .first()
    )
    return row[0] if row else None


def _count_tasks(db: Session, status_id: str) -> int:
    return db.query(ProjectTask).filter(ProjectTask.status_id == status_id).count()


def _migrate_tasks(db: Session, from_status_id: str, to_status_id: str) -> int:
    return (
        db.query(ProjectTask)
        .filter(ProjectTask.status_id == from_status_id)
        .update({ProjectTask.status_id: to_status_id}, synchronize_session=False)
    )


def _register_project_task() -> None:
    register_status_entity(
        StatusEntity(
            entity_type=PROJECT_TASK_ENTITY_TYPE,
            label="Project Task",
            module=MODULE_KEY,
            count_records=_count_tasks,
            migrate_records=_migrate_tasks,
            model=ProjectTask,
            status_attr="status_id",
            record_label_attr="name",
            scope_resolver=_project_task_scope,
            scope_label="Template",
            required_flags=["is_initial", "is_terminal"],
            # Narrow on purpose. `task_phase` and `category` are what an auto edge
            # would gate on; the escalation and stuck fields are NOT exposed because
            # they are enforced by the service, and a rule reading them would be a
            # second, weaker copy of that guard.
            fact_attrs=("task_phase", "category", "assignee_user_id"),
        )
    )


def _count_leads(db: Session, status_id: str) -> int:
    return db.query(ProjectLead).filter(ProjectLead.status_id == status_id).count()


def _migrate_leads(db: Session, from_status_id: str, to_status_id: str) -> int:
    return (
        db.query(ProjectLead)
        .filter(ProjectLead.status_id == from_status_id)
        .update({ProjectLead.status_id: to_status_id}, synchronize_session=False)
    )


def _register_project_lead() -> None:
    """Entity #3 (AC-O7), and the first one with NO scoped graphs.

    A lead has no template -- the template is chosen at registration, which is after a
    lead stops being a lead -- so there is nothing to scope on. One lead funnel per
    install. Omitting ``scope_resolver`` is what says so: the API derives
    ``supports_scoped_graphs`` from it, so the admin is never offered a scope picker
    that could only ever resolve the default.
    """
    register_status_entity(
        StatusEntity(
            entity_type=PROJECT_LEAD_ENTITY_TYPE,
            label="Lead",
            module=MODULE_KEY,
            count_records=_count_leads,
            migrate_records=_migrate_leads,
            model=ProjectLead,
            status_attr="status_id",
            record_label_attr="title",
            required_flags=["is_initial", "is_terminal"],
            fact_attrs=("outcome", "source", "developer_party_id", "customer_id"),
        )
    )
