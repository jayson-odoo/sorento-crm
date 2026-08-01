"""Project Sales API routes."""
from fastapi import APIRouter

from app.api.v1.projects import (
    forecast,
    leads,
    parties,
    po_intake,
    projects,
    quotations,
    sales_orders,
    samples_pos,
    schedules,
    tasks,
    types,
)

router = APIRouter()

# Config first: /config/types and /config/templates would otherwise be captured by
# the /{project_id} path in the projects router.
# Reports before the projects router for the same reason config is: /reports/forecast is a
# literal segment that /projects/{project_id} must not capture.
router.include_router(forecast.router, tags=["project-reports"])
router.include_router(types.router, prefix="/config", tags=["project-config"])
# Tasks mount at the module root because they span three shapes: nested under a
# project, the cross-project /my-tasks worklist, and template checklist admin. Before
# the projects router, so /projects/{id}/tasks is not captured by /projects/{id}.
router.include_router(tasks.router, tags=["project-tasks"])
# Quotations mount at the root for the same reason as tasks: they span three shapes
# (nested under a project, then /quotations/{id} and /quotation-versions/{id} for the
# revision history) plus their own /config surface.
router.include_router(quotations.router, tags=["project-quotations"])
# Samples and customer POs mount at the root for the same reason: both are nested
# under a project for listing but addressed directly for editing.
router.include_router(samples_pos.router, tags=["project-samples-pos"])
# Phase 2 document intake. Root-mounted for the same reason as the three above: a PO
# version, a schedule version and an SO draft are each listed under a project but
# addressed directly by id. All three MUST precede the projects router.
router.include_router(po_intake.router, tags=["project-po-intake"])
router.include_router(schedules.router, tags=["project-delivery-schedules"])
router.include_router(sales_orders.router, tags=["project-sales-orders"])
router.include_router(parties.router, prefix="/parties", tags=["project-parties"])
# Leads before projects for the same reason config is: /leads/{id}/qualify returns a
# PROJECT, but the route itself lives under the leads prefix.
router.include_router(leads.router, prefix="/leads", tags=["project-leads"])
router.include_router(projects.router, prefix="/projects", tags=["projects"])
