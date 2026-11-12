"""Complaints (`/complaint-management/complaints`), with root cause and resolution.

`Complaint` is not company scoped: the list narrows only by the contact's brand scope
(`complaints_service._build_list_query`), so `scope` repeats that clause. The contact person, phone and address
are left out of the allowlist.
"""
from __future__ import annotations

from app.models.complaint_master_data import ComplaintResolution, ComplaintRootCause
from app.models.complaints import Complaint
from app.models.service_jobs import ServiceJob
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef


def _own(me):
    from app.services.own_scope import request_clause

    return request_clause(Complaint, me)


def _brand_scope(db) -> list:
    from app.services.contact_brand_scope import complaint_in_scope_clauses

    return list(complaint_in_scope_clauses(db))


def _job_scope(db) -> list:
    from app.services import service_job_service

    return service_job_service.job_brand_clauses(db)


def _job_user_scope(db, user_id) -> list:
    """The jobs of the complaints this reader may see: the same rule as the Service Jobs screen."""
    from sqlalchemy import select

    from app.services import service_job_service

    limit = service_job_service.limit_for(db, str(user_id))
    if limit is None:
        return []
    return [ServiceJob.complaint_id.in_(select(Complaint.id).where(limit.clause()))]


register(
    EntityDef(
        key="service_job",
        label="Service jobs",
        module="complaints",
        model=ServiceJob,
        view_permission="complaint_management.service_jobs.view",
        fields={
            "job_number": FieldDef("Job number"),
            "scheduled_from": FieldDef("Scheduled from", note="UTC; the screen shows Malaysian time"),
            "scheduled_to": FieldDef("Scheduled to"),
            "customer_agreed_by": FieldDef("Agreed by"),
            "arrived_at": FieldDef("Arrived at"),
            "completed_at": FieldDef("Completed at"),
            "verified_at": FieldDef("Verified at"),
            "created_at": FieldDef("Created at"),
        },
        relations={"complaint": ("complaint", "complaint_id")},
        name_by=("job_number",),
        screen_path="/complaint-management/service-jobs/{id}",
        pages=("/complaint-management/service-jobs",),
        routes=("GET /api/v1/complaints-management/service-jobs",),
        hint="service jobs: a technician sent to a complaint's site",
        date_field="scheduled_from",
        scope=_job_scope,
        user_scope=_job_user_scope,
    ),
    EntityDef(
        key="complaint_root_cause",
        label="Complaint root causes",
        module="complaints",
        model=ComplaintRootCause,
        view_permission=None,
        fields={"name": FieldDef("Root cause")},
    ),
    EntityDef(
        key="complaint_resolution",
        label="Complaint resolutions",
        module="complaints",
        model=ComplaintResolution,
        view_permission=None,
        fields={"name": FieldDef("Resolution")},
    ),
    EntityDef(
        key="complaint",
        label="Complaints",
        module="complaints",
        model=Complaint,
        view_permission="complaint_management.complaints.view",
        own_permission="complaint_management.complaints.view_own",
        own_clause=_own,
        fields={
            "complaint_number": FieldDef("Complaint number"),
            "complaint_date": FieldDef("Complaint date"),
            "status": FieldDef("Status"),
            "customer_name": FieldDef("Customer"),
            # Lists every line's code; the screen cuts it to the contact's brands (`in_scope_product_codes`).
            "product_code": FieldDef("Product code", whole_document=True),
            "complaint_type": FieldDef("Complaint type"),
            "salesperson": FieldDef("Salesperson"),
            "created_at": FieldDef("Created at"),
            "resolved_at": FieldDef("Resolved at"),
        },
        relations={
            "root_cause": ("complaint_root_cause", "root_cause_id"),
            "resolution": ("complaint_resolution", "resolution_id"),
        },
        name_by=("complaint_number", "customer_name"),
        screen_path="/complaint-management/complaints/{id}",
        pages=("/complaint-management",),
        routes=("GET /api/v1/complaints-management/complaints/",),
        hint="complaints with root cause and resolution",
        scope=_brand_scope,
    ),
)
