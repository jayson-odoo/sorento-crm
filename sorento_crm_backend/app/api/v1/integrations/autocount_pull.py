"""AutoCount pull + review (PLAN-autocount-pull-review.md). SR1: start / current / status.

Every route resolves the pull first (owner-only, P12) and checks the PERMISSION OF ITS
OWN ENTITY (AC-PM-2) - a user holding only the products permission gets 403 on a stock
pull, even one they own, and 404 on one they do not (AC-BD-7: not-owned and not-found are
answered identically, so a pull's existence is never revealed to anyone but its owner).

`GET /current` is the one exception: it is a convenience lookup keyed to the caller's own
company + entity + open pulls, and answers "no open pull" (404) rather than "no permission"
(403) for an entity the caller cannot pull - there is nothing to find either way, and this
route reveals nothing about a pull the caller does not already own.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.services import autocount_pull_service as pull_service
from app.services.error_handler import AppException
from app.services.foundryx_autocount_client import FoundryxPullError
from app.services.job_service import active_company_id_from_scope
from app.services.user_service import UserPermissionService

# Module-gated at the mount in app/api/v1/__init__.py (require_any_module_enabled("product",
# "inventory") - the router covers both entities and neither gates the other).
router = APIRouter()


class PullStartBody(BaseModel):
    entity: str


def _permission_slug(entity: str) -> str:
    slug = pull_service.ENTITY_PERMISSIONS.get(entity)
    if not slug:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Unknown entity '{entity}'. Expected one of: "
            f"{', '.join(sorted(pull_service.ENTITY_PERMISSIONS))}.",
            code="UNKNOWN_ENTITY",
        )
    return slug


def _require_entity_permission(db: Session, user: dict, entity: str) -> None:
    slug = _permission_slug(entity)
    if not UserPermissionService(db).check_user_has_permission(user["id"], slug):
        raise AppException(
            status_code=status.HTTP_403_FORBIDDEN,
            message=f"Permission required: {slug}",
            code="FORBIDDEN",
        )


def _require_single_company(db: Session) -> str:
    """Refuse a pull with no single company to attribute it to.

    Same reasoning as `outstanding_import._require_single_company`: FoundryX answers for
    ONE AutoCount book, so an all-companies or multi-company scope has no single company
    code to ask it about.
    """
    company_id = active_company_id_from_scope(db)
    if not company_id:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Select a single company before pulling from AutoCount.",
            code="SINGLE_COMPANY_REQUIRED",
        )
    return company_id


def _raise_foundryx_error(exc: FoundryxPullError):
    raise AppException(status_code=exc.status, message=exc.message, code=exc.code) from exc


@router.post("")
def start_pull(
    body: PullStartBody,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AC-PL-2..7: permission, single-company guard, reuse-or-build."""
    _require_entity_permission(db, current_user, body.entity)
    company_id = _require_single_company(db)
    try:
        job = pull_service.start_pull(
            db, user_id=current_user["id"], company_id=company_id, entity=body.entity
        )
    except FoundryxPullError as exc:
        _raise_foundryx_error(exc)
    return pull_service.serialize(job)


@router.get("/current")
def get_current_pull(
    entity: str = Query(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AC-PL-4: the caller's own open pull for the active company + entity, else 404."""
    _permission_slug(entity)  # 404 for an entity this lane does not know at all
    company_id = active_company_id_from_scope(db)
    job = pull_service.find_open_pull(
        db, user_id=current_user["id"], company_id=company_id, entity=entity
    )
    if job is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND, message="No open pull.", code="NOT_FOUND"
        )
    return pull_service.serialize(job)


@router.get("/{job_id}")
def get_pull(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AC-BD-1..4, AC-BD-7: owner-only read that advances a `building` pull."""
    job = pull_service.get_owned_pull(db, job_id=job_id, user_id=current_user["id"])
    if job is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND, message="Job not found", code="NOT_FOUND"
        )
    _require_entity_permission(db, current_user, pull_service.entity_of(job))
    try:
        return pull_service.refresh_pull_status(db, job)
    except FoundryxPullError as exc:
        _raise_foundryx_error(exc)
