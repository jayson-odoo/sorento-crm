"""Complaint management API routes."""
from fastapi import APIRouter
from app.api.v1.complaints import (
    complaints,
    complaint_root_causes,
    complaint_resolutions,
    service_jobs,
    technicians,
)

router = APIRouter()

router.include_router(complaints.router, prefix="/complaints", tags=["complaints"])
router.include_router(
    complaint_root_causes.router,
    prefix="/complaint-root-causes",
    tags=["complaint-root-causes"],
)
router.include_router(
    complaint_resolutions.router,
    prefix="/complaint-resolutions",
    tags=["complaint-resolutions"],
)
# S6. Under the complaints module because that is where every job comes from today,
# NOT because a job belongs to a complaint - the entity itself is requester-agnostic
# (ADR-0009) and its source is a polymorphic pair.
router.include_router(
    service_jobs.router,
    prefix="/service-jobs",
    tags=["service-jobs"],
)
router.include_router(
    technicians.router,
    prefix="/technicians",
    tags=["technicians"],
)
router.include_router(
    technicians.provider_router,
    prefix="/external-providers",
    tags=["external-providers"],
)
