"""Sample submission and customer-PO API (S4, UAC Group F).

Two route shapes, matching S3's:

- ``/projects/{id}/samples`` and ``/projects/{id}/purchase-orders`` -- what belongs to
  one project.
- ``/samples/{id}``, ``/purchase-orders/{id}`` and ``/purchase-orders/{id}/lines`` --
  the row itself and its contents.

Rights live on the PROJECT for both, the same way quotations do: whoever may work the
pursuit may record what came out of it, and duplicating that rule per child table would
be another copy to keep in step.

Every refusal comes from the services, so the rules ("no sample against a superseded
version", "a mismatch is flagged, never blocked") live in exactly one place.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import ListResponse
from app.schemas.projects import (
    ProjectPurchaseOrderCreate,
    ProjectPurchaseOrderLineCreate,
    ProjectPurchaseOrderLineResponse,
    ProjectPurchaseOrderLineUpdate,
    ProjectPurchaseOrderResponse,
    ProjectPurchaseOrderUpdate,
    ProjectSampleCreate,
    ProjectSampleResponse,
    ProjectSampleUpdate,
    ProjectSponsorshipResponse,
    ProjectSponsorshipRollupResponse,
    SponsorshipConversionResponse,
)
from app.services import project_po_service as po_svc
from app.services import project_sample_service as sample_svc
from app.services import project_service as projects
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"
DELETE = "projects.projects.delete"


def _envelope(data: List[dict]):
    return {
        "data": data,
        "pagination": {"total": len(data), "page": 1, "limit": max(len(data), 1)},
        "empty": not data,
    }


def _project_for_edit(db: Session, project_id: str, current_user: dict):
    validate_uuid_path(project_id, resource="Project")
    project = projects.get_project_or_404(db, project_id)
    projects.assert_can_edit_project(
        db, project, current_user["id"], permission_slugs(db, current_user["id"])
    )
    return project


# ----------------------------------------------------------------------- samples


@router.get(
    "/projects/{project_id}/samples",
    response_model=ListResponse[ProjectSampleResponse],
)
async def list_samples(
    project_id: str,
    version_id: str | None = Query(None, description="Narrow to one quotation version"),
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        rows = sample_svc.list_samples(db, project_id=project_id, version_id=version_id)
        return _envelope(sample_svc.serialize_samples(db, rows))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/projects/{project_id}/samples",
    response_model=ProjectSampleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sample(
    project_id: str,
    payload: ProjectSampleCreate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """409 when the bound version has been superseded (AC-F2), naming the version to use."""
    try:
        project = _project_for_edit(db, project_id, current_user)
        sample = sample_svc.create_sample(
            db,
            project=project,
            actor_user_id=current_user["id"],
            payload=payload.model_dump(exclude_unset=True),
        )
        db.commit()
        db.refresh(sample)
        return sample_svc.serialize_samples(db, [sample])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put("/samples/{sample_id}", response_model=ProjectSampleResponse)
async def update_sample(
    sample_id: str,
    payload: ProjectSampleUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """No superseded check unless the BINDING changes: the feedback being recorded is
    usually the reason the version was superseded in the first place."""
    try:
        validate_uuid_path(sample_id, resource="Sample")
        sample = sample_svc.get_sample(db, sample_id)
        _project_for_edit(db, sample.project_id, current_user)
        sample = sample_svc.update_sample(
            db, sample=sample, payload=payload.model_dump(exclude_unset=True)
        )
        db.commit()
        db.refresh(sample)
        return sample_svc.serialize_samples(db, [sample])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/samples/{sample_id}")
async def delete_sample(
    sample_id: str,
    current_user: dict = Depends(require_permission(DELETE)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(sample_id, resource="Sample")
        sample = sample_svc.get_sample(db, sample_id)
        _project_for_edit(db, sample.project_id, current_user)
        sample_svc.delete_sample(db, sample=sample)
        db.commit()
        return {"success": True}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ---------------------------------------------------------------- purchase orders


@router.get(
    "/projects/{project_id}/purchase-orders",
    response_model=ListResponse[ProjectPurchaseOrderResponse],
)
async def list_purchase_orders(
    project_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        rows = po_svc.list_pos(db, project_id=project_id)
        return _envelope(po_svc.serialize_pos(db, rows))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/projects/{project_id}/purchase-orders",
    response_model=ProjectPurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_purchase_order(
    project_id: str,
    payload: ProjectPurchaseOrderCreate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """The first PO on a project moves its status to PO Received (AC-F10).

    ``status_moved_to_po_received`` reports whether that actually happened: a graph with
    no legal edge from where the project sits leaves the status alone, and the UI says so
    rather than letting the user believe the funnel moved.
    """
    try:
        project = _project_for_edit(db, project_id, current_user)
        po = po_svc.create_po(
            db,
            project=project,
            actor_user_id=current_user["id"],
            payload=payload.model_dump(exclude_unset=True),
        )
        # Read the marker BEFORE the commit + refresh: instance attrs do not survive a
        # re-query, the same trap the SLA services document.
        moved = bool(getattr(po, "_status_moved", False))
        db.commit()
        db.refresh(po)
        body = po_svc.serialize_pos(db, [po])[0]
        body["status_moved_to_po_received"] = moved
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put("/purchase-orders/{po_id}", response_model=ProjectPurchaseOrderResponse)
async def update_purchase_order(
    po_id: str,
    payload: ProjectPurchaseOrderUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(po_id, resource="Purchase order")
        po = po_svc.get_po(db, po_id)
        _project_for_edit(db, po.project_id, current_user)
        po = po_svc.update_po(db, po=po, payload=payload.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(po)
        return po_svc.serialize_pos(db, [po])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/purchase-orders/{po_id}")
async def delete_purchase_order(
    po_id: str,
    current_user: dict = Depends(require_permission(DELETE)),
    db: Session = Depends(get_db),
):
    """Hard delete. The status this PO may have triggered is deliberately NOT rolled
    back: the project genuinely passed through PO Received, and quietly reversing a
    funnel position would hide the correction from everybody watching the board."""
    try:
        validate_uuid_path(po_id, resource="Purchase order")
        po = po_svc.get_po(db, po_id)
        _project_for_edit(db, po.project_id, current_user)
        po_svc.delete_po(db, po=po)
        db.commit()
        return {"success": True}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ------------------------------------------------------------------- PO lines


@router.get(
    "/purchase-orders/{po_id}/lines",
    response_model=ListResponse[ProjectPurchaseOrderLineResponse],
)
async def list_po_lines(
    po_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(po_id, resource="Purchase order")
        po = po_svc.get_po(db, po_id)
        projects.get_project_or_404(db, po.project_id)
        return _envelope(po_svc.serialize_lines(db, po_svc.list_lines(db, po_id=po.id)))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


def _notify_po_mismatch(db: Session, po, line) -> None:
    """Tell the owner and management that a PO line disagrees with what we quoted (AC-F9).

    Fired from the LINE routes rather than from the service so it runs once the line is
    committed: an alert about a line that a later rollback removed is worse than a late one.
    Erosion from v1 (AC-F9a) deliberately does NOT notify -- it is the expected result of a
    negotiation, and alerting on it would make every well-negotiated PO look broken.
    """
    if not (line.model_mismatch or line.price_mismatch):
        return
    try:
        from app.models.projects import Project
        from app.services import project_notify_service as notify

        project = db.query(Project).filter(Project.id == po.project_id).first()
        if project is None:
            return
        notify.notify_po_mismatch(
            db,
            project=project,
            po=po,
            mismatches=[
                {
                    "kind": "model mismatch" if line.model_mismatch else "price mismatch",
                    "product_code": line.product_code,
                    "description": line.description,
                }
            ],
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("PO mismatch notify failed for po=%s line=%s: %s", po.id, line.id, exc)


@router.post(
    "/purchase-orders/{po_id}/lines",
    response_model=ProjectPurchaseOrderLineResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_po_line(
    po_id: str,
    payload: ProjectPurchaseOrderLineCreate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """A mismatch against the bound version is FLAGGED on the returned line, not refused
    (AC-F9): the PO arrived, and hiding it achieves nothing."""
    try:
        validate_uuid_path(po_id, resource="Purchase order")
        po = po_svc.get_po(db, po_id)
        _project_for_edit(db, po.project_id, current_user)
        line = po_svc.upsert_line(
            db, po=po, payload=payload.model_dump(exclude_unset=True)
        )
        db.commit()
        db.refresh(line)
        _notify_po_mismatch(db, po, line)
        return po_svc.serialize_lines(db, [line])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(
    "/purchase-orders/{po_id}/lines/{line_id}",
    response_model=ProjectPurchaseOrderLineResponse,
)
async def update_po_line(
    po_id: str,
    line_id: str,
    payload: ProjectPurchaseOrderLineUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(po_id, resource="Purchase order")
        validate_uuid_path(line_id, resource="Purchase order line")
        po = po_svc.get_po(db, po_id)
        _project_for_edit(db, po.project_id, current_user)
        line = _line_or_404(db, po_id, line_id)
        line = po_svc.upsert_line(
            db, po=po, payload=payload.model_dump(exclude_unset=True), line=line
        )
        db.commit()
        db.refresh(line)
        _notify_po_mismatch(db, po, line)
        return po_svc.serialize_lines(db, [line])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/purchase-orders/{po_id}/lines/{line_id}")
async def delete_po_line(
    po_id: str,
    line_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(po_id, resource="Purchase order")
        validate_uuid_path(line_id, resource="Purchase order line")
        po = po_svc.get_po(db, po_id)
        _project_for_edit(db, po.project_id, current_user)
        po_svc.delete_line(db, line=_line_or_404(db, po_id, line_id))
        db.commit()
        return {"success": True}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


def _line_or_404(db: Session, po_id: str, line_id: str):
    from app.models.projects import ProjectPurchaseOrderLine
    from app.services.error_handler import AppException

    line = (
        db.query(ProjectPurchaseOrderLine)
        .filter(
            ProjectPurchaseOrderLine.id == line_id,
            # Scoped to the PO in the URL: without it, a line id from another PO would
            # be edited through a path that claims otherwise.
            ProjectPurchaseOrderLine.po_id == po_id,
        )
        .first()
    )
    if not line:
        raise AppException(
            status_code=404,
            message="Purchase order line not found.",
            code="po_line_not_found",
        )
    return line


# --------------------------------------------------------------- sponsorship link


@router.get(
    "/projects/{project_id}/sponsorships",
    response_model=ListResponse[ProjectSponsorshipResponse],
)
async def list_project_sponsorships(
    project_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Sponsorship forms linked to this project (AC-F3).

    Read-only here on purpose: the form itself is owned by procurement, and a second
    editor for the same document would be two places to keep in step. The tab links out.
    """
    try:
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        from app.services import sponsorship_link_service as links

        return _envelope(links.list_sponsorships(db, project_id=project_id))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/projects/{project_id}/sponsorships/rollup",
    response_model=ProjectSponsorshipRollupResponse,
)
async def project_sponsorship_rollup(
    project_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """AC-F7, per project and per year."""
    try:
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        from app.services import sponsorship_link_service as links

        return links.sponsorship_rollup(db, project_id=project_id)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get(
    "/sponsorships/conversion", response_model=SponsorshipConversionResponse
)
async def sponsorship_conversion(
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Sponsorship-to-PO conversion for the acting company (AC-F7).

    Declared BEFORE nothing in particular, but note the literal `/sponsorships/...`
    segment: it sits at the module root rather than under a project because it is a
    cross-project number, which is exactly the shape `test_route_shadowing` watches.
    """
    try:
        from app.api.v1.projects._common import acting_company_id
        from app.services import sponsorship_link_service as links

        return links.sponsorship_conversion(db, company_id=acting_company_id(db))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
