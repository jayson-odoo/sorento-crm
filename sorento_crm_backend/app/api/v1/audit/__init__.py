"""Audit log API."""
from fastapi import APIRouter
from app.api.v1.audit import audit_logs

router = APIRouter()
router.include_router(audit_logs.router, prefix="/logs", tags=["audit"])
