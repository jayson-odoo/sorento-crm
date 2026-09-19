"""AutoCount pull + review (PLAN-autocount-pull-review.md). SR1: start / current / status.
SR3 added the review data (rows, download, compare) and Confirm for `products`; SR4 adds
the `stock_balances` half of every one of those routes - same routes, dispatched by the
pull's own entity, never a separate endpoint.

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
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.base import get_company_scope
from app.models.job import ImportJob
from app.services import autocount_pull_service as pull_service
from app.services.autocount_pull_compare import compare_products, compare_stock
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
    # Bounds (Phase 3 fix round, F-3): a filename is display text, never a file itself -
    # 255 is the same ceiling `original_filename` already carries elsewhere in this repo.
    # `rows` is a checker's own workbook, parsed client-side and posted whole - 200,000
    # is generous for any real stock/products file (the largest today is about 11,840
    # rows) and stops a malformed/hostile body from being read into memory unbounded.
    filename: str = Field(max_length=255)
    rows: list[dict[str, Any]] = Field(max_length=200_000)


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
    """Owner-only 404, then a company re-check, then the permission of the pull's OWN
    entity - AC-BD-7 / P12, shared by every `/{job_id}...` route.

    Phase 3 fix round (F-5, tightened): the owner check alone is not enough once a user
    can switch company scope - the SAME owner, viewing under a company scope that no
    longer covers the pull's own `company_id` (a company switch, not a different
    account), gets the same 404 a non-owner would. This is SET membership against the
    raw four-state scope (`get_company_scope`, `app/models/base.py`), not a
    single-company comparison - a multi-company scope that omits the pull's company is
    refused exactly like a single-company mismatch is:

      - `frozenset({ids})` (single or multi-company): 404 unless the pull's own
        `company_id` is one of `ids`.
      - `None` (all-companies / system, e.g. a superadmin or an X-API-Key caller with no
        contact identity): unrestricted, same as today.
      - `UNSET` (the resolver never ran, or a real user with zero company grants -
        `company_scope_resolver.py`'s own "no grants at all -> leave UNSET" branch): the
        four-state table's own rule for this state is fail-closed (0 rows), so this
        follows the same rule rather than treating it as "no restriction" - a caller
        with no company standing at all gets no owned pull either, whatever they own.
    """
    job = pull_service.get_owned_pull(db, job_id=job_id, user_id=current_user["id"])
    if job is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND, message="Job not found", code="NOT_FOUND"
        )
    scope = get_company_scope(db)
    if scope is not None:
        allowed = isinstance(scope, frozenset) and str(job.company_id) in {str(cid) for cid in scope}
        if not allowed:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND, message="Job not found", code="NOT_FOUND"
            )
    _require_entity_permission(db, current_user, pull_service.entity_of(job))
    return job


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
    """AC-RV-3: the Excel-view rows, mapped from the FoundryX snapshot. Products: every
    row. Stock: FED rows only (AC-SP-2)."""
    job = _resolve_pull(db, current_user, job_id)
    _require_rows_available(job)
    try:
        rows = pull_service.fetch_snapshot_rows(job)
    except FoundryxPullError as exc:
        _raise_foundryx_error(exc)
    if pull_service.entity_of(job) == "products":
        mapped = [pull_service.map_product_row(r) for r in rows]
    else:
        fed = pull_service.classify_stock_rows(db, str(job.company_id), rows)["fed"]
        mapped = [pull_service.map_stock_row(r) for r in fed]
    return pull_service.paginate_rows(mapped, page=page, limit=limit, query=query)


@router.get("/{job_id}/download.xlsx")
def download_pull(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AC-RV-5: the same rows as one workbook, the template's own header row. Stock's
    file is the Stock List file (AC-SC-4) - FED rows only."""
    job = _resolve_pull(db, current_user, job_id)
    _require_rows_available(job)
    try:
        rows = pull_service.fetch_snapshot_rows(job)
    except FoundryxPullError as exc:
        _raise_foundryx_error(exc)
    if pull_service.entity_of(job) == "products":
        mapped = [pull_service.map_product_row(r) for r in rows]
        body = pull_service.build_products_workbook(mapped)
    else:
        fed = pull_service.classify_stock_rows(db, str(job.company_id), rows)["fed"]
        body = pull_service.build_stock_workbook(fed)
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
    stored on the job, the rows and the difference list are returned but never kept.
    Stock compares against the FED rows only (AC-CM-3)."""
    job = _resolve_pull(db, current_user, job_id)
    _require_rows_available(job)
    try:
        pull_rows = pull_service.fetch_snapshot_rows(job)
    except FoundryxPullError as exc:
        _raise_foundryx_error(exc)
    if pull_service.entity_of(job) == "products":
        result = compare_products(body.rows, pull_rows)
    else:
        fed = pull_service.classify_stock_rows(db, str(job.company_id), pull_rows)["fed"]
        result = compare_stock(body.rows, fed)
    job = pull_service.store_compare_summary(db, job, filename=body.filename, result=result)
    # AC-CM-5 / Phase 3 fix round (F-10): `summary` in the response is the SAME shape
    # `GET /{job_id}` returns as `compare` - what got stored, not the raw comparison
    # function's own summary (which carries `only_in_excel`/`only_in_pull` as COUNTS
    # under different keys than the stored one and no `filename`/`compared_at` at all).
    # `differences` and the top-level `only_in_excel`/`only_in_pull` stay the raw LISTS
    # the comparison just computed - never stored (AC-CM-5).
    return {
        "summary": pull_service.serialize(job)["compare"],
        "differences": result.get("differences", []),
        "only_in_excel": result.get("only_in_excel", []),
        "only_in_pull": result.get("only_in_pull", []),
    }


@router.post("/{job_id}/confirm")
def confirm_pull(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AC-PC-1/AC-SC-1: creates + enqueues the apply job once, marks the pull confirmed.
    AC-SP-1: also refused (409) when the pull's own `confirm_blocked_reason` is set -
    entity-agnostic, products never sets it."""
    job = _resolve_pull(db, current_user, job_id)
    try:
        return pull_service.confirm_pull(db, job, user_id=current_user["id"])
    except pull_service.PullNotReadyForConfirm as exc:
        raise AppException(status_code=status.HTTP_409_CONFLICT, message=str(exc), code="NOT_READY")
