"""Complaints (`/complaint-management/complaints`), with root cause and resolution.

`Complaint` is not company scoped: the list narrows only by the contact's brand scope
(`complaints_service._build_list_query`), so `scope` repeats that clause. The contact person, phone and address
are left out of the allowlist.
"""
from __future__ import annotations

from app.models.complaint_master_data import ComplaintResolution, ComplaintRootCause
from app.models.complaints import Complaint
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef


def _own(me):
    from app.services.own_scope import request_clause

    return request_clause(Complaint, me)


def _brand_scope(db) -> list:
    from app.services.contact_brand_scope import complaint_in_scope_clauses

    return list(complaint_in_scope_clauses(db))


register(
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
            "product_code": FieldDef("Product code"),
            "complaint_type": FieldDef("Complaint type"),
            "salesperson": FieldDef("Salesperson"),
            "created_at": FieldDef("Created at"),
            "resolved_at": FieldDef("Resolved at"),
        },
        relations={
            "root_cause": ("complaint_root_cause", "root_cause_id"),
            "resolution": ("complaint_resolution", "resolution_id"),
        },
        screen_path="/complaint-management/complaints/{id}",
        pages=("/complaint-management",),
        routes=("GET /api/v1/complaints-management/complaints/",),
        scope=_brand_scope,
    ),
)
