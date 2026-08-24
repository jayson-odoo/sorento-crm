"""Audit log API."""
from fastapi import APIRouter
from app.api.v1.audit import audit_logs, activity

router = APIRouter()
router.include_router(audit_logs.router, prefix="/logs", tags=["audit"])
# Cross-Entity Activity Timeline - label-resolved view over audit_logs.
router.include_router(activity.router, tags=["audit"])
