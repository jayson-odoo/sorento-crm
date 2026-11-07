"""Sales opportunities (`/sales/opportunities`) and projects (`/project-sales`) (AI-TOOLS-WAVE3).

Opportunities: `sales.opportunities.view`, or `.view_own` for the opportunities of the user's own sales agents
(`own_scope.opportunity_clause`, as `api/v1/sales/opportunities.py`); the list applies the company scope only
(`opportunity_service.list_opportunities`).

Projects: `projects.projects.view`, or `.view_own` for projects the user owns, collaborates on or registered
through their contact (`own_scope.project_clause`, as `project_service.list_projects`). Approved projects only: the
AI read tools never answer about a registration waiting for approval (PROJECT-REG-PORTAL R4,
`api/v1/projects/projects.py` `_MACHINE_AUTH_METHODS`, `project_service.approved_clause`), so drafts, pending and
rejected registrations stay out, and every result says so. Quotations are wave 4: they have no company-wide list and their value
is computed from versions.
"""
from __future__ import annotations

from app.models.projects import Project
from app.models.sales import SalesOpportunity
from app.services.assistant_registry import register
from app.services.assistant_registry.orders import agent_label_for
from app.services.assistant_registry.types import EntityDef, FieldDef


def _stage(model):
    """The record's stage as its screen prints it: the status engine's label (`statuses.label`)."""

    def expr():
        from sqlalchemy import select

        from app.models.status import Status

        return select(Status.label).where(Status.id == model.status_id).correlate(model).scalar_subquery()

    return expr


def _opportunity_own(m):
    from app.services.own_scope import opportunity_clause

    return opportunity_clause(m)


def _project_own(m):
    from app.services.own_scope import project_clause

    return project_clause(m)


def _project_rules(db, user_id: str | None = None) -> list:
    from app.services.project_service import approved_clause

    return [approved_clause()]


def _project_owner():
    from sqlalchemy import select

    from app.models.user import User

    return select(User.name).where(User.id == Project.owner_user_id).correlate(Project).scalar_subquery()


def _estimated_value():
    from sqlalchemy import select

    from app.models.projects import ProjectSalesProfile

    return (
        select(ProjectSalesProfile.estimated_sales_value)
        .where(ProjectSalesProfile.project_id == Project.id)
        .correlate(Project)
        .scalar_subquery()
    )


register(
    EntityDef(
        key="opportunity",
        label="Sales opportunities",
        module="sales",
        model=SalesOpportunity,
        view_permission="sales.opportunities.view",
        own_permission="sales.opportunities.view_own",
        own_clause=_opportunity_own,
        fields={
            "opportunity_no": FieldDef("Number"),
            "title": FieldDef("Title"),
            "prospect_name": FieldDef("Prospect", note="The name when the opportunity has no customer yet."),
            "agent": FieldDef(
                "Agent", expr=lambda: agent_label_for(SalesOpportunity, SalesOpportunity.sales_agent_id),
                agent_id=lambda: SalesOpportunity.sales_agent_id, note="'CODE - Name'.",
            ),
            "stage": FieldDef("Stage", expr=_stage(SalesOpportunity)),
            "outcome": FieldDef("Outcome", note="open, won or lost."),
            "expected_amount": FieldDef("Amount"),
            "expected_close_date": FieldDef("Close date"),
            "source": FieldDef("Source", note="portal, crm or chat."),
            "lost_reason": FieldDef("Lost reason"),
            "created_at": FieldDef("Created at"),
        },
        relations={"customer": ("customer", "customer_id")},
        name_by=("opportunity_no", "title"),
        list_fields=("agent", "stage", "outcome", "expected_amount", "expected_close_date"),
        date_field="expected_close_date",
        screen_path="/sales/opportunities/{id}",
        pages=("/sales/opportunities",),
        routes=("GET /api/v1/sales/opportunities",),
        hint="sales opportunities (pipeline deals): amount, stage, outcome open|won|lost; period = close date; "
             "agent=<code or name as said>",
    ),
    EntityDef(
        key="project",
        label="Projects",
        module="projects",
        model=Project,
        view_permission="projects.projects.view",
        own_permission="projects.projects.view_own",
        own_clause=_project_own,
        fields={
            "project_code": FieldDef("Code"),
            "title": FieldDef("Title"),
            "stage": FieldDef("Stage", expr=_stage(Project)),
            "outcome": FieldDef("Outcome", note="open, won, lost or dormant."),
            "loss_reason": FieldDef("Loss reason"),
            "estimated_value": FieldDef("Estimated value", expr=_estimated_value),
            "owner": FieldDef("Owner", expr=_project_owner, note="The staff member who owns the project."),
            "approval_state": FieldDef("Approval", note="approved or empty (a staff project); others are not read."),
            "is_critical": FieldDef("Critical"),
            "last_meaningful_activity_at": FieldDef("Last activity"),
            "created_at": FieldDef("Created at"),
        },
        name_by=("project_code", "title"),
        list_fields=("stage", "outcome", "estimated_value", "owner"),
        date_field="created_at",
        scope=_project_rules,
        screen_path="/project-sales/{id}",
        pages=("/project-sales",),
        routes=("GET /api/v1/project-sales/projects/",),
        always_note="Registrations not yet approved excluded.",
        hint="projects (project sales pipeline): stage, outcome, estimated value, owner, critical",
    ),
)
