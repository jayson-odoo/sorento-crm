"""After-sales service API routes: service jobs, the dispatch board, technicians and warranty configuration."""
from fastapi import APIRouter

from app.api.v1.after_sales import service_jobs, technicians, warranty

router = APIRouter()
router.include_router(service_jobs.router, tags=["service-jobs"])
router.include_router(technicians.router, prefix="/technicians", tags=["technicians"])
router.include_router(warranty.router, prefix="/warranty")
