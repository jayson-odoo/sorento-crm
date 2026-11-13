"""Project sales: the records linked to a project (the project page's Related tab, PROJECT-RELATED-RECORDS).

One row per stock inquiry, complaint, purchase request, sponsorship form and new product application whose
Project field names a project, so "what is linked to PS26-0001?" reads the same rows the tab shows. A computed
entity: the rows come from `project_related_records.assistant_rows`, the tab's own registry and per-type rules
(`own_scope.request_access`), never written twice here. A project limited user (`view_own`) reads their own
projects only.
"""
from __future__ import annotations

from app.models.projects import Project
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
