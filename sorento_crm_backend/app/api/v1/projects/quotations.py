"""Quotation API (S3, UAC Group E).

Three route shapes, and the URLs say which is which:

- ``/projects/{id}/quotations`` -- the scopes of one project.
- ``/quotations/{id}/versions`` and ``/versions/{id}/lines`` -- the revision history and
  its contents. Lines hang off a VERSION, never off a quotation, because "which version
  was this line on" is the whole point of the model.
- ``/config/series`` and ``/config/price-floors`` -- the two pieces of policy the alerts
  read. Under /config with the project types, because that is where an admin already is.

Editing a frozen version returns 422 from the service; the route does not second-guess
it, so the rule lives in exactly one place.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import acting_company_id, permission_slugs
from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse
from app.schemas.projects import (
    PriceFloorRuleResponse,
    PriceFloorRuleUpsert,
    ProjectQuotationCreate,
    ProjectQuotationLineCreate,
    ProjectQuotationLineResponse,
    ProjectQuotationLineUpdate,
    ProjectQuotationOutcomeRequest,
    ProjectQuotationResponse,
    ProjectQuotationUpdate,
    ProjectQuotationVersionResponse,
    ProjectSeriesCreate,
    ProjectSeriesResponse,
    ProjectSeriesUpdate,
)
from app.services import project_pricing_service as pricing
from app.services import project_quotation_service as svc
from app.services import project_service as projects
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"
DELETE = "projects.projects.delete"
CONFIG_VIEW = "projects.types.view"
CONFIG_EDIT = "projects.types.edit"


def _envelope(data: List[dict]):
    return {
        "data": data,
        "pagination": {"total": len(data), "page": 1, "limit": max(len(data), 1)},
        "empty": not data,
    }


def _notify_breaches(db: Session, line, actor_user_id: str) -> None:
    """Tell management a line just went below its floor (AC-E6, AC-E6a).

    Best-effort by design: the price is already saved by the time this runs, and a
    notification backend that is down must not 500 a successful save. Same rule as every
    other post-commit side effect in the codebase.
    """
    events = svc.pop_breach_events(line)
    if not events:
        return
    for event in events:
        logger.warning(
            "project quotation line below floor: line=%s quotation=%s price=%s floor=%s (%s)",
            event["line_id"],
            event["quotation_id"],
            event["unit_price"],
            event["floor_value"],
            event["floor_level"],
        )
    # S5b: the fan-out itself. Management only -- the person who typed the price does not
    # need telling what they just did, and the recipient rule lives in one place
    # (project_notify_service) so it cannot drift from the PO and staleness alerts.
    from app.models.projects import Project, ProjectQuotation
    from app.services import project_notify_service as notify

    project = (
        db.query(Project)
        .join(ProjectQuotation, ProjectQuotation.project_id == Project.id)
        .filter(ProjectQuotation.id == str(events[0]["quotation_id"]))
        .first()
    )
    if project is None:
        return
    for event in events:
        notify.notify_floor_breach(
            db, project=project, event=event, actor_user_id=actor_user_id
        )


# --------------------------------------------------------------- quotations


@router.get(
    "/projects/{project_id}/quotations",
    response_model=ListResponse[ProjectQuotationResponse],
)
async def list_quotations(
    project_id: str,
    # API-key readable (AC-K1): `crm_project_quotations_list` answers "what did we quote".
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        from app.models.projects import ProjectQuotation

        rows = (
            db.query(ProjectQuotation)
            .filter(ProjectQuotation.project_id == project_id)
            .order_by(ProjectQuotation.created_at.asc())
            .all()
        )
        return _envelope(svc.serialize_quotations(db, rows))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/projects/{project_id}/quotations",
    response_model=ProjectQuotationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_quotation(
    project_id: str,
    payload: ProjectQuotationCreate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Opens version 1 with it: a quotation with no version has nowhere to put a line."""
    try:
        validate_uuid_path(project_id, resource="Project")
        project = projects.get_project_or_404(db, project_id)
        projects.assert_can_edit_project(
            db, project, current_user["id"], permission_slugs(db, current_user["id"])
        )
        quotation = svc.create_quotation(
            db,
            project=project,
            actor_user_id=current_user["id"],
            payload=payload.model_dump(exclude_unset=True),
        )
        db.commit()
        db.refresh(quotation)
        return svc.serialize_quotations(db, [quotation])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put("/quotations/{quotation_id}", response_model=ProjectQuotationResponse)
async def update_quotation(
    quotation_id: str,
    payload: ProjectQuotationUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(quotation_id, resource="Quotation")
        quotation = _quotation_for_edit(db, quotation_id, current_user)
        svc.update_quotation(
            db, quotation=quotation, payload=payload.model_dump(exclude_unset=True)
        )
        db.commit()
        db.refresh(quotation)
        return svc.serialize_quotations(db, [quotation])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/quotations/{quotation_id}/outcome", response_model=ProjectQuotationResponse)
async def set_quotation_outcome(
    quotation_id: str,
    payload: ProjectQuotationOutcomeRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Win or lose ONE scope; the project's outcome is re-derived from all of them.

    The project's STATUS is deliberately untouched (AC-E10a) -- a project at "PO
    Received" with an open Common Area scope is still live on the board.
    """
    try:
        validate_uuid_path(quotation_id, resource="Quotation")
        quotation = _quotation_for_edit(db, quotation_id, current_user)
        svc.set_outcome(
            db,
            quotation=quotation,
            outcome=payload.outcome,
            loss_reason=payload.loss_reason,
        )
        db.commit()
        db.refresh(quotation)
        return svc.serialize_quotations(db, [quotation])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/quotations/{quotation_id}")
async def delete_quotation(
    quotation_id: str,
    current_user: dict = Depends(require_permission(DELETE)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(quotation_id, resource="Quotation")
        quotation = _quotation_for_edit(db, quotation_id, current_user)
        svc.delete_quotation(db, quotation)
        db.commit()
        return {"success": True}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


def _quotation_for_edit(db: Session, quotation_id: str, current_user: dict):
    """Load a quotation and check edit rights on its PROJECT.

    Rights live on the project, not the quotation: the owner and collaborators of a
    pursuit are who may price it, and duplicating that rule here would be a second copy
    to keep in step.
    """
    from app.models.projects import ProjectQuotation

    quotation = (
        db.query(ProjectQuotation).filter(ProjectQuotation.id == quotation_id).first()
    )
    if not quotation:
        from app.services.error_handler import AppException

        raise AppException(
            status_code=404, message="Quotation not found.", code="quotation_not_found"
        )
    project = projects.get_project_or_404(db, quotation.project_id)
    projects.assert_can_edit_project(
        db, project, current_user["id"], permission_slugs(db, current_user["id"])
    )
    return quotation


# ----------------------------------------------------------------- versions


@router.get(
    "/quotations/{quotation_id}/versions",
    response_model=ListResponse[ProjectQuotationVersionResponse],
)
async def list_versions(
    quotation_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Newest first. ``is_current`` is derived from MAX(version_no), not stored."""
    try:
        validate_uuid_path(quotation_id, resource="Quotation")
        rows = svc.list_versions(db, quotation_id)
        return _envelope(svc.serialize_versions(db, rows))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/quotations/{quotation_id}/revise",
    response_model=ProjectQuotationVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def revise_quotation(
    quotation_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Freeze the current version, open the next with its lines carried across (AC-E3)."""
    try:
        validate_uuid_path(quotation_id, resource="Quotation")
        quotation = _quotation_for_edit(db, quotation_id, current_user)
        version = svc.revise(db, quotation=quotation, actor_user_id=current_user["id"])
        db.commit()
        db.refresh(version)
        return svc.serialize_versions(db, [version])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# -------------------------------------------------------------------- lines


@router.get(
    "/quotation-versions/{version_id}/lines",
    response_model=ListResponse[ProjectQuotationLineResponse],
)
async def list_lines(
    version_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(version_id, resource="Quotation version")
        return _envelope(svc.serialize_lines(db, svc.list_lines(db, version_id)))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/quotation-versions/{version_id}/lines",
    response_model=ProjectQuotationLineResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_line(
    version_id: str,
    payload: ProjectQuotationLineCreate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(version_id, resource="Quotation version")
        version, _quotation = _version_for_edit(db, version_id, current_user)
        line = svc.upsert_line(
            db,
            version=version,
            actor_user_id=current_user["id"],
            payload=payload.model_dump(exclude_unset=True),
        )
        _notify_breaches(db, line, current_user["id"])
        db.commit()
        db.refresh(line)
        return svc.serialize_lines(db, [line])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(
    "/quotation-versions/{version_id}/lines/{line_id}",
    response_model=ProjectQuotationLineResponse,
)
async def update_line(
    version_id: str,
    line_id: str,
    payload: ProjectQuotationLineUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Saves IN PLACE on the current version (AC-E2). No new version is created."""
    try:
        validate_uuid_path(version_id, resource="Quotation version")
        validate_uuid_path(line_id, resource="Line")
        version, _quotation = _version_for_edit(db, version_id, current_user)
        line = _line_or_404(db, version_id, line_id)
        line = svc.upsert_line(
            db,
            version=version,
            actor_user_id=current_user["id"],
            line=line,
            payload=payload.model_dump(exclude_unset=True),
        )
        _notify_breaches(db, line, current_user["id"])
        db.commit()
        db.refresh(line)
        return svc.serialize_lines(db, [line])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/quotation-versions/{version_id}/lines/{line_id}")
async def delete_line(
    version_id: str,
    line_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(version_id, resource="Quotation version")
        validate_uuid_path(line_id, resource="Line")
        version, _quotation = _version_for_edit(db, version_id, current_user)
        line = _line_or_404(db, version_id, line_id)
        svc.delete_line(db, version=version, line=line)
        db.commit()
        return {"success": True}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


def _version_for_edit(db: Session, version_id: str, current_user: dict):
    from app.models.projects import ProjectQuotationVersion

    from app.services.error_handler import AppException

    version = (
        db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.id == version_id)
        .first()
    )
    if not version:
        raise AppException(
            status_code=404,
            message="Quotation version not found.",
            code="quotation_version_not_found",
        )
    quotation = _quotation_for_edit(db, version.quotation_id, current_user)
    return version, quotation


def _line_or_404(db: Session, version_id: str, line_id: str):
    from app.models.projects import ProjectQuotationLine

    from app.services.error_handler import AppException

    line = (
        db.query(ProjectQuotationLine)
        .filter(
            ProjectQuotationLine.id == line_id,
            ProjectQuotationLine.version_id == version_id,
        )
        .first()
    )
    if not line:
        raise AppException(
            status_code=404, message="Line not found.", code="quotation_line_not_found"
        )
    return line


# ------------------------------------------------------------------- config


@router.get("/config/loss-reasons", response_model=List[dict])
async def list_loss_reasons(
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """The configured loss reasons (AC-E9). Empty means an admin has not set any up, and
    marking a quotation lost will refuse until they do."""
    try:
        return svc.loss_reasons(db)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/config/series", response_model=ListResponse[ProjectSeriesResponse])
async def list_series(
    include_inactive: bool = Query(False),
    _user: dict = Depends(require_permission(CONFIG_VIEW)),
    db: Session = Depends(get_db),
):
    try:
        return _envelope(
            _serialize_series(
                db,
                company_id=acting_company_id(db),
                include_inactive=include_inactive,
            )
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/config/series",
    response_model=ProjectSeriesResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_series(
    payload: ProjectSeriesCreate,
    _user: dict = Depends(require_permission(CONFIG_EDIT)),
    db: Session = Depends(get_db),
):
    try:
        from app.models.projects import ProjectSeries

        body = payload.model_dump(exclude_unset=True)
        category_ids = body.pop("category_ids", []) or []
        series = ProjectSeries(company_id=acting_company_id(db), **body)
        db.add(series)
        db.flush()
        pricing.set_series_categories(db, series=series, category_ids=category_ids)
        db.commit()
        db.refresh(series)
        return _serialize_series(db, company_id=series.company_id, series_id=series.id)[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put("/config/series/{series_id}", response_model=ProjectSeriesResponse)
async def update_series(
    series_id: str,
    payload: ProjectSeriesUpdate,
    _user: dict = Depends(require_permission(CONFIG_EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(series_id, resource="Series")
        from app.models.projects import ProjectSeries

        from app.services.error_handler import AppException

        series = db.query(ProjectSeries).filter(ProjectSeries.id == series_id).first()
        if not series:
            raise AppException(
                status_code=404, message="Series not found.", code="series_not_found"
            )

        body = payload.model_dump(exclude_unset=True)
        category_ids = body.pop("category_ids", None)
        for field, value in body.items():
            setattr(series, field, value)
        if category_ids is not None:
            pricing.set_series_categories(db, series=series, category_ids=category_ids)
        db.commit()
        db.refresh(series)
        return _serialize_series(db, company_id=series.company_id, series_id=series.id)[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/config/series/{series_id}")
async def delete_series(
    series_id: str,
    _user: dict = Depends(require_permission(CONFIG_EDIT)),
    db: Session = Depends(get_db),
):
    """Blocked while a quotation still nominates it: deleting would silently turn every
    line on that quotation standard, erasing an alert somebody was acting on."""
    try:
        validate_uuid_path(series_id, resource="Series")
        from app.models.projects import ProjectQuotation, ProjectSeries

        from app.services.error_handler import AppException

        series = db.query(ProjectSeries).filter(ProjectSeries.id == series_id).first()
        if not series:
            raise AppException(
                status_code=404, message="Series not found.", code="series_not_found"
            )
        in_use = (
            db.query(ProjectQuotation)
            .filter(ProjectQuotation.series_id == series_id)
            .count()
        )
        if in_use:
            raise AppException(
                status_code=409,
                message=(
                    f"{in_use} quotation(s) use this series. Deactivate it instead, so "
                    "their alerts stay meaningful."
                ),
                code="series_in_use",
            )
        db.delete(series)
        db.commit()
        return {"success": True}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


def _serialize_series(
    db: Session,
    *,
    company_id: str,
    series_id: Optional[str] = None,
    include_inactive: bool = True,
) -> List[dict]:
    from app.models.product import ProductCategory
    from app.models.projects import (
        ProjectQuotation,
        ProjectSeries,
        ProjectSeriesCategory,
    )

    query = db.query(ProjectSeries).filter(ProjectSeries.company_id == company_id)
    if series_id:
        query = query.filter(ProjectSeries.id == series_id)
    elif not include_inactive:
        query = query.filter(ProjectSeries.is_active.is_(True))
    rows = query.order_by(ProjectSeries.name.asc()).all()
    if not rows:
        return []

    ids = [row.id for row in rows]
    nominated: dict = {}
    for link in (
        db.query(ProjectSeriesCategory)
        .filter(ProjectSeriesCategory.series_id.in_(ids))
        .all()
    ):
        nominated.setdefault(link.series_id, []).append(link.category_id)

    category_ids = {cid for values in nominated.values() for cid in values}
    names = (
        {
            row.id: row.category_name
            for row in db.query(ProductCategory)
            .filter(ProductCategory.id.in_(category_ids))
            .all()
        }
        if category_ids
        else {}
    )

    brand_ids = {row.brand_id for row in rows if row.brand_id}
    brand_names = {}
    if brand_ids:
        from app.models.product import Brand

        brand_names = {
            row.id: row.brand_name
            for row in db.query(Brand).filter(Brand.id.in_(brand_ids)).all()
        }

    from sqlalchemy import func

    counts = dict(
        db.query(ProjectQuotation.series_id, func.count(ProjectQuotation.id))
        .filter(ProjectQuotation.series_id.in_(ids))
        .group_by(ProjectQuotation.series_id)
        .all()
    )

    out = []
    for row in rows:
        mine = nominated.get(row.id, [])
        out.append(
            {
                "id": row.id,
                "name": row.name,
                "brand_id": row.brand_id,
                "brand_name": brand_names.get(row.brand_id or ""),
                "description": row.description,
                "is_active": row.is_active,
                "category_ids": mine,
                "category_names": [names.get(cid, "") for cid in mine],
                "covered_category_count": len(
                    pricing.category_with_descendants(db, mine)
                ),
                "quotation_count": counts.get(row.id, 0),
            }
        )
    return out


@router.get("/config/price-floors", response_model=ListResponse[PriceFloorRuleResponse])
async def list_price_floors(
    _user: dict = Depends(require_permission(CONFIG_VIEW)),
    db: Session = Depends(get_db),
):
    """Most specific first, which is the order they take effect in."""
    try:
        rules = pricing.list_floor_rules(db, company_id=acting_company_id(db))
        return _envelope(_serialize_floors(db, rules))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/config/price-floors",
    response_model=PriceFloorRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_price_floor(
    payload: PriceFloorRuleUpsert,
    current_user: dict = Depends(require_permission(CONFIG_EDIT)),
    db: Session = Depends(get_db),
):
    """Upsert per level: editing "the Basins floor" means exactly that, not a second
    competing Basins rule."""
    try:
        rule = pricing.upsert_floor_rule(
            db,
            company_id=acting_company_id(db),
            payload=payload.model_dump(exclude_unset=True),
            actor_user_id=current_user["id"],
        )
        db.commit()
        db.refresh(rule)
        return _serialize_floors(db, [rule])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/config/price-floors/{rule_id}")
async def delete_price_floor(
    rule_id: str,
    _user: dict = Depends(require_permission(CONFIG_EDIT)),
    db: Session = Depends(get_db),
):
    """Hard delete. Floors already applied are stored ON their lines (AC-E7), so this
    cannot rewrite quoted history."""
    try:
        validate_uuid_path(rule_id, resource="Price floor rule")
        from app.models.projects import PriceFloorRule

        from app.services.error_handler import AppException

        rule = db.query(PriceFloorRule).filter(PriceFloorRule.id == rule_id).first()
        if not rule:
            raise AppException(
                status_code=404,
                message="Price floor rule not found.",
                code="floor_rule_not_found",
            )
        pricing.delete_floor_rule(db, rule)
        db.commit()
        return {"success": True}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


def _serialize_floors(db: Session, rules) -> List[dict]:
    from app.models.product import Product, ProductCategory

    product_ids = {r.product_id for r in rules if r.product_id}
    category_ids = {r.category_id for r in rules if r.category_id}
    products = (
        {
            row.id: row.product_code
            for row in db.query(Product).filter(Product.id.in_(product_ids)).all()
        }
        if product_ids
        else {}
    )
    categories = (
        {
            row.id: row.category_name
            for row in db.query(ProductCategory)
            .filter(ProductCategory.id.in_(category_ids))
            .all()
        }
        if category_ids
        else {}
    )

    out = []
    for rule in rules:
        level = (
            pricing.LEVEL_PRODUCT
            if rule.product_id
            else pricing.LEVEL_CATEGORY
            if rule.category_id
            else pricing.LEVEL_SYSTEM
        )
        out.append(
            {
                "id": rule.id,
                "product_id": rule.product_id,
                "product_code": products.get(rule.product_id or ""),
                "category_id": rule.category_id,
                "category_name": categories.get(rule.category_id or ""),
                "mode": rule.mode,
                "value": rule.value,
                "notes": rule.notes,
                "is_active": rule.is_active,
                "level": level,
            }
        )
    return out
