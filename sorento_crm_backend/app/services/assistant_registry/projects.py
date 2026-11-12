"""Project import runs (`/project-sales/import`, PLAN-project-import-12nov.md).

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
from app.models.user import User
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef

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
