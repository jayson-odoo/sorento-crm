"""Status-engine entities owned by the Project Sales module.

Discovered by ``app/status_engine/discovery.py``; core never names this file.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.projects import Project
from app.modules.projects.bootstrap import MODULE_KEY
from app.status_engine.registry import StatusEntity, register_status_entity

PROJECT_ENTITY_TYPE = "project"


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
