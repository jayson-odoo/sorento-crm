"""System-level API routes."""
from fastapi import APIRouter
from app.api.v1.system import import_logs, jobs, calendar, outgoing_mails, scheduled_tasks, numbering_rules

router = APIRouter()

router.include_router(import_logs.router, tags=["import-logs"])
router.include_router(jobs.router, tags=["jobs"])
router.include_router(calendar.router, tags=["calendar"])
router.include_router(outgoing_mails.router, tags=["outgoing-mails"])
router.include_router(scheduled_tasks.router, tags=["scheduled-tasks"])
router.include_router(numbering_rules.router, tags=["numbering-rules"])
