"""Ingesting AutoCount's copy of a sales order, and reconciling it (P8a). Contract 6d.

Two ways in, one service. `POST /sales-orders/ingest` takes the canonical document and is
the seam the ESB takes in stage 2; `POST /sales-orders/ingest-file` takes the export a CS
uploads today and parses it into the same shape. Neither knows about the other's transport.

**These routes MUST be mounted before `sales_orders.router`.** `/sales-orders/ingest` and
`/sales-orders/{pso_id}` are the same shape to the router, and whichever is declared first
wins - the same shadowing that once captured an n8n call as a tracking id.

Rights follow the rest of the module: reads take `projects.projects.view`, and resolving
takes `projects.projects.edit` on that project, checked in `project_service` like every
other project write. Ingest additionally accepts the API-key principal, because in stage 2
the caller is the ESB rather than a person.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.project_so_divergence import (
    DivergenceDetail,
    DivergenceRowSummary,
    IngestDocumentPayload,
    IngestResponse,
    ResolveRowRequest,
)
from app.services import project_service as projects
from app.services.error_handler import AppException, handle_internal_error
from app.services.project_so_divergence_service import ProjectSODivergenceService
from app.services.project_so_ingest_service import (
    IngestDocument,
    IngestLine,
    ProjectSOIngestService,
)
from app.services.uuid_path_param import validate_uuid_path
from app.utils.http import content_disposition

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _document(payload: IngestDocumentPayload) -> IngestDocument:
    return IngestDocument(
        doc_no=payload.doc_no,
        customer_code=payload.customer_code,
        customer_po_no=payload.customer_po_no,
        area_group=payload.area_group,
        terms=payload.terms,
        total_amount=payload.total_amount,
        lines=[
            IngestLine(
                line_no=line.line_no,
                product_code=line.product_code,
                description=line.description,
                qty=line.qty,
                unit_price=line.unit_price,
                uom=line.uom,
                delivery_date=line.delivery_date,
            )
            for line in payload.lines
        ],
    )


def _assert_can_resolve(db: Session, divergence_id: str, current_user: dict):
    """Ownership is the PROJECT's rule, re-checked in the service that owns it."""
    validate_uuid_path(divergence_id, resource="Reconciliation")
    service = ProjectSODivergenceService(db)
    detail = service.get_divergence(divergence_id)
    project = projects.get_project_or_404(db, detail["project_id"])
    projects.assert_can_edit_project(
        db, project, current_user["id"], permission_slugs(db, current_user["id"])
    )
    return service


# ----------------------------------------------------------------------- ingest


@router.post("/sales-orders/ingest", response_model=IngestResponse)
async def ingest_sales_order(
    payload: IngestDocumentPayload,
    current_user: dict = Depends(require_permission_with_api_key(EDIT)),
    db: Session = Depends(get_db),
):
    """The canonical document. Stage 2's ESB posts exactly this.

    Never a 404 for an unmatched document: a match back that fails is an ANSWER, and the
    caller needs the reason to hand to a person. The outcome carries it.
    """
    try:
        result = ProjectSOIngestService(db).ingest(
            _document(payload), actor_user_id=current_user.get("id"), source="esb"
        )
        db.commit()
        return result.__dict__
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post("/sales-orders/ingest-file", response_model=IngestResponse)
async def ingest_sales_order_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Stage 1: the export a CS takes out of AutoCount, read by column heading."""
    try:
        payload = await file.read()
        if not payload:
            raise AppException(
                status_code=422, message="That file is empty.", code="so_ingest_empty_file"
            )
        if len(payload) > MAX_UPLOAD_BYTES:
            raise AppException(
                status_code=422,
                message="That file is larger than 10 MB.",
                code="so_ingest_file_too_large",
            )
        from app.services.project_so_ingest_parser import parse_document

        document = parse_document(payload, filename=file.filename or "")
        result = ProjectSOIngestService(db).ingest(
            document, actor_user_id=current_user["id"], source="upload"
        )
        db.commit()
        return result.__dict__
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ------------------------------------------------------------------------ reads


@router.get("/divergences", response_model=ListResponse[DivergenceRowSummary])
async def list_divergences(
    status: Optional[str] = Query(default="open"),
    project_id: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_LIMIT),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """AC-N6: with the age of each, so a stack is visible rather than discovered."""
    try:
        if project_id:
            validate_uuid_path(project_id, resource="Project")
        return ProjectSODivergenceService(db).list_divergences(
            status=status or None, project_id=project_id, page=page, limit=limit
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/divergences/{divergence_id}", response_model=DivergenceDetail)
async def get_divergence(
    divergence_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """Ours, theirs and the difference per row. Rows that agree come through too, so the
    screen can collapse them behind a count instead of pretending they were not read."""
    try:
        validate_uuid_path(divergence_id, resource="Reconciliation")
        return ProjectSODivergenceService(db).get_divergence(divergence_id)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ------------------------------------------------------------------- resolution


@router.post(
    "/divergences/{divergence_id}/rows/{row_id}/resolve", response_model=DivergenceDetail
)
async def resolve_divergence_row(
    divergence_id: str,
    row_id: str,
    payload: ResolveRowRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """AC-N4 and AC-N7: one side wins, and who / when / which / why is recorded."""
    try:
        validate_uuid_path(row_id, resource="Reconciliation row")
        service = _assert_can_resolve(db, divergence_id, current_user)
        service.resolve_line(
            divergence_id,
            row_id,
            resolution=payload.resolution,
            reason=payload.reason,
            actor_user_id=current_user["id"],
        )
        db.commit()
        return service.get_divergence(divergence_id)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/divergences/{divergence_id}/corrective-import-file")
async def corrective_import_file(
    divergence_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Our values, going back to AutoCount. Generated per request, stamped when taken."""
    try:
        service = _assert_can_resolve(db, divergence_id, current_user)
        filename, body = service.corrective_import_file(divergence_id)
        db.commit()
        return Response(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": content_disposition(filename)},
        )
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
