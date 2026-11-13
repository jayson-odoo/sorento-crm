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
