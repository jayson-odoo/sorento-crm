"""After-sales service jobs (`/after-sales/service-jobs`).

A job is read through the module's own permission and the company filter; the contact's phone and the
address lines are left out of the allowlist.
"""
from __future__ import annotations

from app.models.service_jobs import ServiceJob
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef

register(
    EntityDef(
        key="service_job",
        label="Service jobs",
        module="after_sales",
        model=ServiceJob,
        view_permission="after_sales.service_jobs.view",
        fields={
            "job_number": FieldDef("Job number"),
            "customer_name": FieldDef("Customer"),
            "site_city": FieldDef("City"),
            "scheduled_from": FieldDef("Scheduled from", note="UTC; the screen shows Malaysian time"),
            "scheduled_to": FieldDef("Scheduled to"),
            "customer_agreed_by": FieldDef("Agreed by"),
            "arrived_at": FieldDef("Arrived at"),
            "completed_at": FieldDef("Completed at"),
            "verified_at": FieldDef("Verified at"),
            "created_at": FieldDef("Created at"),
        },
        name_by=("job_number", "customer_name"),
        screen_path="/after-sales/service-jobs/{id}",
        pages=("/after-sales",),
        routes=("GET /api/v1/after-sales/service-jobs",),
        hint="service jobs: a technician sent to a customer's site",
        date_field="scheduled_from",
    ),
)

# Warranty configuration (P2, `/after-sales/warranty`). Read under the service-job view slug, the same
# gate as the configuration read routes (owner Q2 13 Nov: every service-job viewer sees warranty).
# Kinds and kind rules are shared reference rows; policies are per company.
from app.models.warranty import WarrantyKindRule, WarrantyPolicy, WarrantyProductKind  # noqa: E402

register(
    EntityDef(
        key="warranty_kind",
        label="Warranty product kinds",
        module="after_sales",
        model=WarrantyProductKind,
        view_permission="after_sales.service_jobs.view",
        fields={
            "code": FieldDef("Code"),
            "name": FieldDef("Kind"),
            "is_active": FieldDef("Active"),
        },
        name_by=("code", "name"),
        pages=("/after-sales/warranty",),
        routes=("GET /api/v1/after-sales/warranty/kinds",),
        hint="warranty product kinds the policy names (water closet, basin mixer ...)",
    ),
    EntityDef(
        key="warranty_kind_rule",
        label="Warranty kind rules",
        module="after_sales",
        model=WarrantyKindRule,
        view_permission="after_sales.service_jobs.view",
        fields={
            "match_type": FieldDef("Match", note="series, model_list, category or code_prefix"),
            "match_value": FieldDef("Value"),
            "priority": FieldDef("Priority"),
        },
        relations={"kind": ("warranty_kind", "kind_id")},
        name_by=("match_value",),
        pages=("/after-sales/warranty",),
        routes=("GET /api/v1/after-sales/warranty/kind-rules",),
        hint="which products are which warranty kind; a product no rule matches has no warranty rule yet",
    ),
    EntityDef(
        key="warranty_policy",
        label="Warranty policies",
        module="after_sales",
        model=WarrantyPolicy,
        view_permission="after_sales.service_jobs.view",
        fields={
            "version": FieldDef("Version"),
            "effective_from": FieldDef("In force from"),
            "effective_to": FieldDef("In force to", note="empty = still in force"),
        },
        name_by=("version",),
        screen_path="/after-sales/warranty/policies/{id}",
        pages=("/after-sales/warranty",),
        routes=("GET /api/v1/after-sales/warranty/policies",),
        hint="warranty policy versions and the dates each is in force",
        date_field="effective_from",
    ),
)
