"""S2: project as status-engine entity #1 (UAC Group B/G, ADR-0001).

The funnel is configurable, not an enum. A project's stage graph is the DEFAULT
graph for ``entity_type='project'``, overridable per template via a fork -- which is
what the user asked for: "our status engine should be able to set for project entity,
and overridable by template".
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.models.projects import Project, ProjectTemplate, ProjectType
from app.models.status import Status
from app.services import status_service
from app.status_engine.registry import get_status_entity

from ._pg_fixture import blank_session

MARKER = "zzt-pse"
ENTITY = "project"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _status(db, key: str, label: str, *, initial=False, terminal=False, scope=None):
    status = Status(
        id=_uid(),
        entity_type=ENTITY,
        scope_id=scope,
        key=key,
        label=label,
        is_initial=initial,
        is_terminal=terminal,
        sort_order=0,
    )
    db.add(status)
    db.flush()
    return status


def _template(db, company_id: str) -> ProjectTemplate:
    ptype = ProjectType(
        id=_uid(),
        company_id=company_id,
        name=f"{MARKER} Property Development",
        code=f"{MARKER}-prop",
        derives_delivery_from_launch=True,
    )
    db.add(ptype)
    db.flush()
    template = ProjectTemplate(
        id=_uid(), company_id=company_id, type_id=ptype.id, name=f"{MARKER} High Rise"
    )
    db.add(template)
    db.flush()
    return template


def test_project_is_a_registered_status_entity():
    entity = get_status_entity(ENTITY)
    assert entity is not None, "the projects module must register its status entity"
    assert entity.status_attr == "status_id"
    assert entity.model is Project


def test_a_new_project_starts_in_the_graphs_initial_status():
    with blank_session() as db:
        _status(db, "identified", "Identified", initial=True)
        _status(db, "po_received", "PO Received", terminal=True)

        initial = status_service.initial_status(db, ENTITY)

        assert initial.key == "identified"


def test_a_template_fork_overrides_the_default_funnel_for_its_projects():
    """One graph does not fit every project type.

    A property development runs a long funnel (registration, specification,
    tendering); a hotel fitout does not. The template owns the fork, and a project
    resolves its graph through its template -- one hop from the record, which is why
    the entity carries a ``scope_resolver`` callable rather than a column name.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        template = _template(db, company_id)

        _status(db, "identified", "Identified", initial=True)
        _status(db, "po_received", "PO Received", terminal=True)
        _status(db, "walkthrough", "Site Walkthrough", initial=True, scope=template.id)

        project = Project(
            id=_uid(),
            company_id=company_id,
            project_code=f"{MARKER}-1",
            title="Tropicana Aman Phase 2",
            normalised_title="tropicana aman phase 2",
            template_id=template.id,
        )
        db.add(project)
        db.flush()

        graph = status_service.graph_for_record(db, ENTITY, project)

        assert graph.initial is not None
        assert graph.initial.key == "walkthrough"
        assert {s.key for s in graph.statuses} == {"walkthrough"}


def test_a_project_with_no_template_resolves_the_default_funnel():
    """Templates are optional: a hotel renovation registered in a hurry has none."""
    with blank_session() as db:
        company_id = _sorento(db)
        _status(db, "identified", "Identified", initial=True)

        project = Project(
            id=_uid(),
            company_id=company_id,
            project_code=f"{MARKER}-2",
            title="Menara Star HQ Toilet Renovation",
            normalised_title="menara star hq toilet renovation",
        )
        db.add(project)
        db.flush()

        graph = status_service.graph_for_record(db, ENTITY, project)

        assert graph.initial is not None
        assert graph.initial.key == "identified"


def test_a_status_holding_projects_cannot_be_deleted():
    """The engine's block-delete-if-referenced needs a working record count.

    Without it an admin can delete a status out from under live projects, leaving
    them pointing at nothing.
    """
    with blank_session() as db:
        company_id = _sorento(db)
        tendering = _status(db, "tendering", "Tendering", initial=True)

        db.add(
            Project(
                id=_uid(),
                company_id=company_id,
                project_code=f"{MARKER}-3",
                title="Eco Majestic Clubhouse",
                normalised_title="eco majestic clubhouse",
                status_id=tendering.id,
            )
        )
        db.flush()

        assert status_service.count_records_in_status(db, tendering) == 1
