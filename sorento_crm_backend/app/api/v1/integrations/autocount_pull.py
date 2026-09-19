"""AutoCount pull + review (PLAN-autocount-pull-review.md). SR1: start / current / status.
SR3 adds the review data (rows, download, compare) and Confirm.

Every route resolves the pull first (owner-only, P12) and checks the PERMISSION OF ITS
OWN ENTITY (AC-PM-2) - a user holding only the products permission gets 403 on a stock
pull, even one they own, and 404 on one they do not (AC-BD-7: not-owned and not-found are
answered identically, so a pull's existence is never revealed to anyone but its owner).
`_resolve_pull` is that owner-then-permission step, factored out once and used by every
`/{job_id}...` route below it (AC-BD-7, AC-RV-3d, AC-CM route, AC-PC-1d).

`GET /current` is the one exception: it is a convenience lookup keyed to the caller's own
company + entity + open pulls, and answers "no open pull" (404) rather than "no permission"
(403) for an entity the caller cannot pull - there is nothing to find either way, and this
route reveals nothing about a pull the caller does not already own.

SR3 covers `products` only - `stock_balances` rows/download/compare/confirm are SR4
(AC-SP-*, AC-SC-*); a stock pull that somehow reached `review` (it cannot yet - SR1's
preview task refuses any entity but `products`) answers `NOT_IMPLEMENTED` rather than
guessing at a stock shape.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.job import ImportJob
from app.services import autocount_pull_service as pull_service
from app.services.autocount_pull_compare import compare_products
from app.services.error_handler import AppException
from app.services.foundryx_autocount_client import FoundryxPullError
from app.services.job_service import active_company_id_from_scope
from app.services.user_service import UserPermissionService
from app.utils.http import content_disposition

# Module-gated at the mount in app/api/v1/__init__.py (require_any_module_enabled("product",
# "inventory") - the router covers both entities and neither gates the other).
router = APIRouter()

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class PullStartBody(BaseModel):
    entity: str


class ComparePostBody(BaseModel):
    filename: str
    rows: list[dict[str, Any]]


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


def _resolve_pull(db: Session, current_user: dict, job_id: str) -> ImportJob:
    """Owner-only 404, then the permission of the pull's OWN entity - AC-BD-7 / P12,
    shared by every `/{job_id}...` route."""
    job = pull_service.get_owned_pull(db, job_id=job_id, user_id=current_user["id"])
    if job is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND, message="Job not found", code="NOT_FOUND"
        )
    _require_entity_permission(db, current_user, pull_service.entity_of(job))
    return job


def _require_products_entity(job: ImportJob) -> None:
    """SR3 covers `products` only - see module docstring."""
    if pull_service.entity_of(job) != "products":
        raise AppException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            message="Stock pull review is not available yet.",
            code="NOT_IMPLEMENTED",
        )


def _require_rows_available(job: ImportJob) -> None:
    try:
        pull_service.require_rows_available(job)
    except pull_service.PullRowsNotAvailable as exc:
        raise AppException(status_code=status.HTTP_409_CONFLICT, message=str(exc), code="NOT_READY")


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
    job = _resolve_pull(db, current_user, job_id)
    try:
        return pull_service.refresh_pull_status(db, job)
    except FoundryxPullError as exc:
        _raise_foundryx_error(exc)


@router.get("/{job_id}/rows")
def get_pull_rows(
    job_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    query: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AC-RV-3: the Excel-view rows, mapped from the FoundryX snapshot."""
    job = _resolve_pull(db, current_user, job_id)
    _require_rows_available(job)
    _require_products_entity(job)
    try:
        rows = pull_service.fetch_snapshot_rows(job)
    except FoundryxPullError as exc:
        _raise_foundryx_error(exc)
    mapped = [pull_service.map_product_row(r) for r in rows]
    return pull_service.paginate_rows(mapped, page=page, limit=limit, query=query)


@router.get("/{job_id}/download.xlsx")
def download_pull(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AC-RV-5: the same rows as one workbook, the template's own header row."""
    job = _resolve_pull(db, current_user, job_id)
    _require_rows_available(job)
    _require_products_entity(job)
    try:
        rows = pull_service.fetch_snapshot_rows(job)
    except FoundryxPullError as exc:
        _raise_foundryx_error(exc)
    mapped = [pull_service.map_product_row(r) for r in rows]
    body = pull_service.build_products_workbook(mapped)
    return Response(
        content=body,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": content_disposition(pull_service.download_filename(job))},
    )


@router.post("/{job_id}/compare")
def compare_pull(
    job_id: str,
    body: ComparePostBody,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AC-CM-1..5: advisory compare against the checker's own file - the summary is
    stored on the job, the rows and the difference list are returned but never kept."""
    job = _resolve_pull(db, current_user, job_id)
    _require_rows_available(job)
    _require_products_entity(job)
    try:
        pull_rows = pull_service.fetch_snapshot_rows(job)
    except FoundryxPullError as exc:
        _raise_foundryx_error(exc)
    result = compare_products(body.rows, pull_rows)
    pull_service.store_compare_summary(db, job, filename=body.filename, result=result)
    return result


@router.post("/{job_id}/confirm")
def confirm_pull(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AC-PC-1: creates + enqueues the apply job once, marks the pull confirmed."""
    job = _resolve_pull(db, current_user, job_id)
    _require_products_entity(job)
    try:
        return pull_service.confirm_pull(db, job, user_id=current_user["id"])
    except pull_service.PullNotReadyForConfirm as exc:
        raise AppException(status_code=status.HTTP_409_CONFLICT, message=str(exc), code="NOT_READY")
