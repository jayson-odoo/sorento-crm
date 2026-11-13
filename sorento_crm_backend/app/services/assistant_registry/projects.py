"""Project sales entities for the assistant.

1. Project sales: the records linked to a project (the project page's Related tab, PROJECT-RELATED-RECORDS).

One row per stock inquiry, complaint, purchase request, sponsorship form and new product application whose
Project field names a project, so "what is linked to PS26-0001?" reads the same rows the tab shows. A computed
entity: the rows come from `project_related_records.assistant_rows`, the tab's own registry and per-type rules
(`own_scope.request_access`), never written twice here. A project limited user (`view_own`) reads their own
projects only.

2. Project import runs (`/project-sales/import`, PLAN-project-import-12nov.md).

A run is an `import_jobs` row of `job_type = project_po_register`; its run number, stage and
counts live in `job_metadata`, so those fields are read through expressions over the JSON, the
same words the runs grid shows. `ImportJob` is job-tracking infrastructure, not a
`CompanyScopedMixin` model, so `scope` repeats what `project_import.service.list_runs` applies:
this job type, and the caller's company scope.

Only the runs list is registered. The rows and value lines inside one run are not
(`# ai: not-for-assistant` on their routes), and there is no action: an import or a revert
creates or removes hundreds of records and stays on the screen, with a person looking at the
preview.
"""
from __future__ import annotations

import sqlalchemy as sa

from app.models.job import ImportJob
from app.models.projects import Project
from app.models.user import User
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef


def _rows(db, user_id, own_only, date_from, date_to, *, limit):
    from app.services.project_related_records import assistant_rows

    return assistant_rows(db, user_id, own_only, date_from, date_to, limit=limit)


def _own(me):
    from app.services.own_scope import project_clause

    return project_clause(me)


register(
    EntityDef(
        key="project_related_record",
        label="Project related records",
        module="projects",
        model=Project,
        view_permission="projects.projects.view",
        own_permission="projects.projects.view_own",
        own_clause=_own,
        fields={
            "project_code": FieldDef("Project code", kind="text"),
            "project_title": FieldDef("Project", kind="text"),
            "type": FieldDef(
                "Type", kind="text",
                note="Stock Inquiry, Complaint, Purchase request, Sponsorship form or New product application.",
            ),
            "number": FieldDef("Number", kind="text"),
            "status": FieldDef("Status", kind="text"),
            "approval_status": FieldDef("Approval", kind="text", note="Purchase requests and sponsorship forms only."),
            "date": FieldDef("Date", kind="date"),
            "raised_by": FieldDef("Raised by", kind="text"),
            "subject": FieldDef("Subject", kind="text"),
            "value": FieldDef("Value (RM)", kind="number"),
        },
        name_by=("number",),
        list_fields=("project_code", "type", "status", "date", "raised_by", "subject"),
        compute=_rows,
        screen_path="{path}",
        pages=("/project-sales",),
        routes=("GET /api/v1/project-sales/projects/{project_id}/related-records",),
        hint="stock inquiries, complaints, PRs, sponsorship forms and NPAs linked to a project",
    ),
)


# --------------------------------------------------------------- project import runs

_JOB_TYPE = "project_po_register"


def _meta(*path: str):
    return ImportJob.job_metadata[path].astext if len(path) > 1 else ImportJob.job_metadata[path[0]].astext


def _count(outcome: str):
    """The run's count of one outcome: the import's own once imported, else the preview's."""
    return lambda: sa.cast(
        sa.func.coalesce(_meta("result_counts", outcome), _meta("preview_counts", outcome), "0"),
        sa.Integer,
    )


def _uploaded_by():
    return (
        sa.select(User.name).where(User.id == ImportJob.user_id).correlate(ImportJob).scalar_subquery()
    )


def _scope(db) -> list:
    from app.models.base import get_company_scope

    clauses = [ImportJob.job_type == _JOB_TYPE]
    scope = get_company_scope(db)
    if isinstance(scope, frozenset):
        clauses.append(ImportJob.company_id.in_([str(c) for c in scope] or [None]))
    elif scope is not None:
        clauses.append(sa.false())
    return clauses


register(
    EntityDef(
        key="project_import_run",
        label="Project import runs",
        module="projects",
        model=ImportJob,
        view_permission="projects.import.view",
        fields={
            "run_no": FieldDef("Run no.", expr=lambda: _meta("run_no"), kind="text"),
            "filename": FieldDef("File"),
            "uploaded_by": FieldDef("Uploaded by", expr=_uploaded_by, kind="text"),
            "uploaded_at": FieldDef("Uploaded on", column="created_at"),
            "status": FieldDef(
                "Status", expr=lambda: _meta("phase"), kind="text",
                note="draft, previewed, importing, imported or reverted",
            ),
            "rows": FieldDef("Rows", column="total_rows"),
            "created": FieldDef("Created", expr=_count("created"), kind="number"),
            "skipped": FieldDef("Skipped", expr=_count("skipped"), kind="number"),
            "to_review": FieldDef("To review", expr=_count("needs_review"), kind="number"),
        },
        name_by=("run_no", "filename"),
        screen_path="/project-sales/import/{id}",
        pages=("/project-sales/import",),
        routes=("GET /api/v1/projects/import/runs",),
        hint="uploads of the PO register workbook: status, rows, created, skipped, to review",
        scope=_scope,
        date_field="uploaded_at",
        list_fields=("run_no", "filename", "status", "uploaded_at", "created", "to_review"),
    ),
)
