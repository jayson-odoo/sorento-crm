"""System-level API routes."""
from fastapi import APIRouter
from app.api.v1.system import import_logs, jobs

router = APIRouter()

router.include_router(import_logs.router, tags=["import-logs"])
router.include_router(jobs.router, tags=["jobs"])
