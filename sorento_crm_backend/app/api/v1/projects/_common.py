"""Shared route helpers for the Project Sales module."""
from __future__ import annotations

from typing import Set

from sqlalchemy.orm import Session

from app.services.error_handler import AppException


def acting_company_id(db: Session) -> str:
    """The company a write belongs to.

    Mirrors the ``before_insert`` auto-stamp in ``app.services.company_scope`` on
    purpose: the registration lock is scoped per company, so the clash query must ask
    the same question the insert will answer, or a project could be checked against
    one company and written to another.
    """
    from app.services.company_scope import DEFAULT_COMPANY_ID, get_company_scope

    scope = get_company_scope(db)
    if isinstance(scope, frozenset) and len(scope) == 1:
        return next(iter(scope))
    # None is the deliberate system / all-companies principal; its writes land in the
    # incumbent company, matching every other owned write in the system.
    if scope is None:
        return DEFAULT_COMPANY_ID
    raise AppException(
        status_code=400,
        message=(
            "Pick an active company before working with projects -- a project "
            "registration belongs to exactly one company."
        ),
        code="project_company_ambiguous",
    )


def permission_slugs(db: Session, user_id: str) -> Set[str]:
    """Every permission the user holds, for the in-service ownership checks.

    Route-level ``require_permission`` answers "may they use this endpoint"; the
    service still needs "may they edit THIS project", which turns on
    ``projects.projects.manage``.

    ``get_user_permission_slugs`` already returns every known slug for superadmin and
    admin, so those roles get the manage grant here without a special case.
    """
    from app.services.user_service import UserPermissionService

    return set(UserPermissionService(db).get_user_permission_slugs(user_id))
