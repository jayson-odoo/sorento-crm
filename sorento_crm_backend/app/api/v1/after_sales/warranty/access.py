"""Who may use the warranty configuration API (after-sales P2, owner Q1 = admins only).

Reads: anyone who can see service jobs (admins pass every permission check by role).
Writes: role `admin` or `superadmin`, judged on the effective user. One place, so a ruling is a one-line change.
"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_permission_with_api_key
from app.services.user_service import UserPermissionService

JOBS_VIEW = "after_sales.service_jobs.view"

can_read = require_permission_with_api_key(JOBS_VIEW)


def can_write(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    roles = UserPermissionService(db).get_user_role_slugs(current_user["id"])
    if not roles & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        raise HTTPException(status_code=403, detail="Admin access is required to change warranty configuration.")
    return current_user
