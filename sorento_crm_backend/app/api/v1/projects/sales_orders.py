"""Sales order drafts, findings, publish, and the revision delta (P7, P11). Contract sections 5 and 6.

Routes live at the module root rather than under `/projects/{project_id}` because they
are addressed both ways: nested for listing, and directly by id for everything else.
See `documentation/plans/CONTRACT-project-lead-to-so.md`.

Rights sit on the PROJECT, exactly as quotations and customer POs do: whoever may work the
pursuit may draft against it. Two grants are read here rather than added to the registry,
which another slice owns:

- ``projects.projects.edit`` builds, corrects, regroups and publishes.
- ``projects.projects.manage`` is the sales-manager grant, and it is what lets a hard stop
  be acknowledged (D9). The permission is checked in the SERVICE, so the rule lives in one
  place and holds for any future caller.

Every refusal comes from the services. The routes translate, they do not decide.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import permission_slugs
from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.project_sales_order import (
    AcknowledgeFindingRequest,
    AmendmentCreateRequest,
    AmendmentCreateResponse,
    AmendmentDetail,
    AmendmentPreviewRequest,
    AmendmentPreviewResponse,
    AmendmentPublishResponse,
    BuildSalesOrdersRequest,
    BuildSalesOrdersResponse,
    ProjectSalesOrderDetail,
    ProjectSalesOrderLineRow,
    ProjectSalesOrderRow,
    PublishRequest,
    PublishResponse,
    RegroupRequest,
    SalesOrderDeleteResponse,
    SalesOrderDocumentSave,
    SalesOrderLineUpdate,
    SalesOrderWorksheet,
    ScheduleVersionOption,
    SODraftFindingRow,
)
from app.services import project_po_service as po_svc
from app.services import project_record_navigation as record_nav
from app.services import project_service as projects
from app.services.error_handler import AppException, handle_internal_error
from app.services.project_so_delta_service import ProjectSODeltaService
from app.services.project_so_draft_service import ProjectSODraftService
from app.services.uuid_path_param import validate_uuid_path

logger = logging.getLogger(__name__)

router = APIRouter()

VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"
# Deleting a draft is its own grant, the way it is on the customer PO beside it: correcting an
# order and removing it are different privileges even though both act on a proposal.
DELETE = "projects.projects.delete"


def _order_for_edit(db: Session, pso_id: str, current_user: dict):
    """Ownership is the PROJECT's rule, re-checked in the service that owns it."""
    validate_uuid_path(pso_id, resource="Sales order")
    service = ProjectSODraftService(db)
    order = service.get_order(pso_id)
    project = projects.get_project_or_404(db, order.project_id)
    projects.assert_can_edit_project(
        db, project, current_user["id"], permission_slugs(db, current_user["id"])
    )
    return service, order


# ------------------------------------------------------------- version pickers
#
# The build and the delta both make the user choose a document version, so both need a
# list of them.
#
# PO versions are NOT listed here: P4 already serves `GET /purchase-orders/{po_id}/versions`
# from `po_intake.py`, which mounts before this router, so a second declaration of that
# path would be dead code -- and two endpoints answering one question is how a screen ends
# up showing a version list that disagrees with the confirm screen.
#
# Schedule versions ARE listed here, per PURCHASE ORDER. P6's
# `/delivery-schedules/{schedule_id}/versions` is per schedule ROW, and R2 arrived from
# SLG Construction as a different schedule row for the same PO -- so a per-schedule list
# hides the revision the delta exists to compute.


@router.get(
    "/purchase-orders/{po_id}/delivery-schedule-versions",
    response_model=ListResponse[ScheduleVersionOption],
)
async def list_schedule_versions(
    po_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """Across every schedule row on this PO: a revision may arrive from another company."""
    try:
        validate_uuid_path(po_id, resource="Purchase order")
        po_svc.get_po(db, po_id)
        data = ProjectSODraftService(db).list_schedule_versions(po_id)
        return {
            "data": data,
            "pagination": {"total": len(data), "page": 1, "limit": max(len(data), 1)},
            "empty": not data,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ----------------------------------------------------------------------- build


@router.post(
    "/purchase-orders/{po_id}/build-sales-orders",
    response_model=BuildSalesOrdersResponse,
    status_code=status.HTTP_201_CREATED,
)
async def build_sales_orders(
    po_id: str,
    payload: BuildSalesOrdersRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Draft the sales orders for one PO version and one schedule version.

    Idempotent per that pair: re-running replaces the drafts it produced before and leaves
    published orders alone, which is reported back rather than silently done.
    """
    try:
        validate_uuid_path(po_id, resource="Purchase order")
        validate_uuid_path(payload.schedule_version_id, resource="Delivery schedule version")
        po = po_svc.get_po(db, po_id)
        project = projects.get_project_or_404(db, po.project_id)
        projects.assert_can_edit_project(
            db, project, current_user["id"], permission_slugs(db, current_user["id"])
        )
        body = ProjectSODraftService(db).build(
            po_id,
            payload.schedule_version_id,
            split_by=payload.split_by,
            actor_user_id=current_user["id"],
        )
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ------------------------------------------------------------------ list + detail


@router.get(
    "/projects/{project_id}/sales-orders",
    response_model=ListResponse[ProjectSalesOrderRow],
)
async def list_project_sales_orders(
    project_id: str,
    query: Optional[str] = Query(None, description="Matches provisional ref, doc no or area"),
    so_status: Optional[List[str]] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    sort: str = Query("created_at"),
    dir: str = Query("desc"),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(project_id, resource="Project")
        projects.get_project_or_404(db, project_id)
        service = ProjectSODraftService(db)
        rows, total = service.list_for_project(
            project_id,
            query=query,
            status=so_status,
            page=page,
            limit=limit,
            sort=sort,
            direction=dir,
        )
        # One derivation for the whole page: the review state is computed, not stored, and
        # asking per row would run the line mapping once per sales order.
        states = service.review_states_for(rows)
        return {
            "data": [service.serialize_row(row, review_states=states) for row in rows],
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/projects/{project_id}/sales-orders/neighbours")
async def get_sales_order_neighbours(
    project_id: str,
    id: str = Query(..., description="Sales order id to resolve neighbours for"),
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """Prev/next of one order within this project's sales orders.

    The same set, in the same order, the list above returns unfiltered - so the detail
    pager and the tab the user came from cannot disagree. Returns
    ``{total, index, prev_id, next_id}`` with a 1-based ``index`` and circular neighbours.
    """
    try:
        validate_uuid_path(project_id, resource="Project")
        validate_uuid_path(id, resource="Sales order")
        projects.get_project_or_404(db, project_id)
        return record_nav.sales_order_neighbours(db, project_id=project_id, pso_id=id)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/sales-orders/{pso_id}", response_model=ProjectSalesOrderDetail)
async def get_sales_order(
    pso_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(pso_id, resource="Sales order")
        service = ProjectSODraftService(db)
        order = service.get_order(pso_id)
        # The one-order map, passed in rather than left to the row serializer's fallback,
        # so the detail derives its review state exactly once.
        return service.serialize_detail(
            order, review_states=service.review_states_for([order])
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ------------------------------------------------------------------ draft edits


@router.put("/sales-orders/{pso_id}", response_model=ProjectSalesOrderDetail)
async def save_sales_order(
    pso_id: str,
    payload: SalesOrderDocumentSave,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Save the WHOLE sales order in one request: the header, and the full line set.

    **Why this exists.** The detail screen is an edit VIEW now, the way the quotation document
    and the customer PO already are. Writing per line meant a ten-line correction was ten
    requests, each able to half-land and leave an order in a state nobody typed. One request
    makes a Save atomic: either the arrangement the reviewer made is what is stored, or nothing
    moved.

    **The body's ``lines`` is the full desired set, in display order.** A stored line carries
    its ``id``; a new one arrives without one. **Anything stored whose id is absent from the
    body is DELETED**, so a client that omits the lines it did not touch will silently wipe
    them and must always send everything it is showing. ``line_no`` comes from array position,
    and ``amount`` is recomputed as ``qty * unit_price`` rather than accepted.

    **``lines`` absent leaves the lines alone**, which is what a header-only save sends. An
    empty array is refused (422 ``so_lines_required``): an order with no lines is not a
    proposal, and deleting the order is the honest way to say that.

    A PUBLISHED or AMENDED order is refused 409 ``so_not_editable``, before anything is
    written. It is in AutoCount, and the way to change it is an amendment carrying an order
    change notice (finding G9) - the amendment path computes its delta between two DOCUMENT
    versions, so a free-hand correction cannot be routed through it and is refused instead.

    Answers the same body ``GET /sales-orders/{pso_id}`` does, so the client reads one shape.
    """
    try:
        service, order = _order_for_edit(db, pso_id, current_user)
        service.save_document(order, payload.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(order)
        return service.serialize_detail(
            order, review_states=service.review_states_for([order])
        )
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/sales-orders/{pso_id}", response_model=SalesOrderDeleteResponse)
async def delete_sales_order(
    pso_id: str,
    current_user: dict = Depends(require_permission(DELETE)),
    db: Session = Depends(get_db),
):
    """Hard delete, so building the draft can be repeated.

    The build is idempotent per (PO version, schedule version), which corrects a draft that
    was rebuilt - but not one that should never have existed, or one cut on the wrong key. So
    the draft goes, its lines go, and everything hanging off them goes with it: findings,
    allocations and the claims they raised, the order inquiry and its rows, amendments and the
    change notices they carried, divergences and their compared rows, and superseded supply
    decisions. The purchase order and its delivery schedule are untouched, which is what makes
    the rebuild possible.

    It REFUSES, 409, anything that is a live commitment rather than a proposal: a published or
    amended order, one linked to an AutoCount document, one carrying a published amendment, and
    one whose supply has been confirmed. Those are amended, never deleted. Every refusal comes
    from the service.
    """
    try:
        validate_uuid_path(pso_id, resource="Sales order")
        service = ProjectSODraftService(db)
        order = service.get_order(pso_id)
        project = projects.get_project_or_404(db, order.project_id)
        projects.assert_can_edit_project(
            db, project, current_user["id"], permission_slugs(db, current_user["id"])
        )
        reference = order.provisional_ref
        deleted = service.delete_order(order)
        db.commit()
        return {"success": True, "provisional_ref": reference, "deleted": deleted}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/sales-orders/{pso_id}/findings/{finding_id}/acknowledge",
    response_model=SODraftFindingRow,
)
async def acknowledge_finding(
    pso_id: str,
    finding_id: str,
    payload: AcknowledgeFindingRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """403 on a hard stop without the sales-manager grant. The reason stays forever."""
    try:
        validate_uuid_path(finding_id, resource="Finding")
        service, order = _order_for_edit(db, pso_id, current_user)
        # Checked BEFORE the write: a finding id from another order must not be
        # acknowledged through a path that claims otherwise.
        if finding_id not in {row["id"] for row in service.serialize_findings(order)}:
            raise AppException(
                status_code=404,
                message="That finding is not on this sales order.",
                code="finding_foreign_order",
            )
        service.acknowledge_finding(
            finding_id,
            reason=payload.reason,
            actor_user_id=current_user["id"],
            permissions=permission_slugs(db, current_user["id"]),
        )
        db.commit()
        db.refresh(order)
        body = next(
            (row for row in service.serialize_findings(order) if row["id"] == finding_id), None
        )
        if body is None:
            raise AppException(
                status_code=404, message="Finding not found.", code="finding_not_found"
            )
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put(
    "/sales-orders/{pso_id}/lines/{line_id}", response_model=ProjectSalesOrderLineRow
)
async def update_sales_order_line(
    pso_id: str,
    line_id: str,
    payload: SalesOrderLineUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(line_id, resource="Sales order line")
        service, order = _order_for_edit(db, pso_id, current_user)
        service.update_line(order, line_id, payload.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(order)
        detail = service.serialize_detail(
            order, review_states=service.review_states_for([order])
        )
        body = next((row for row in detail["lines"] if row["id"] == line_id), None)
        if body is None:
            raise AppException(
                status_code=404, message="Sales order line not found.", code="so_line_not_found"
            )
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/sales-orders/{pso_id}/regroup", response_model=List[ProjectSalesOrderRow]
)
async def regroup_sales_order(
    pso_id: str,
    payload: RegroupRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Re-split the draft. The shape is remembered for this customer and proposed next time."""
    try:
        service, order = _order_for_edit(db, pso_id, current_user)
        orders = service.regroup(
            order, [group.model_dump() for group in payload.groups]
        )
        states = service.review_states_for(orders)
        rows = [service.serialize_row(row, review_states=states) for row in orders]
        db.commit()
        return rows
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# -------------------------------------------------------------------- publish


@router.post("/sales-orders/{pso_id}/publish", response_model=PublishResponse)
async def publish_sales_order(
    pso_id: str,
    payload: Optional[PublishRequest] = None,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """409 listing the blocking findings when any hard stop is unacknowledged.

    `acknowledge_blocking` waves them all through under one reason, on the sales-manager
    grant: 403 without it, 422 without a reason. Body-less POSTs keep the old behaviour.
    """
    try:
        service, order = _order_for_edit(db, pso_id, current_user)
        ask = payload or PublishRequest()
        body = service.publish(
            order,
            actor_user_id=current_user["id"],
            acknowledge_blocking=ask.acknowledge_blocking,
            reason=ask.reason,
            permissions=permission_slugs(db, current_user["id"]),
        )
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ------------------------------------------------------------------- sponsorship
#
# Group K (P12). Mounted under the sales-order router because what comes back IS a sales
# order, even though the thing it is built from lives in procurement.


@router.post(
    "/sponsorship-forms/{form_id}/build-sales-order",
    response_model=ProjectSalesOrderDetail,
)
async def build_sponsorship_sales_order(
    form_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """An approved sponsorship form becomes a draft at price zero (AC-K1).

    Rights are the PROJECT's, checked in the service once the form names one: whoever may
    work the pursuit may draft against it, and a form with no project is refused outright.
    """
    try:
        validate_uuid_path(form_id, resource="Sponsorship form")
        service = ProjectSODraftService(db)
        order = service.build_from_sponsorship_form(
            form_id, actor_user_id=current_user["id"]
        )
        project = projects.get_project_or_404(db, order.project_id)
        projects.assert_can_edit_project(
            db, project, current_user["id"], permission_slugs(db, current_user["id"])
        )
        body = service.serialize_detail(
            order, review_states=service.review_states_for([order])
        )
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/sales-orders/{pso_id}/confirm-costing", response_model=ProjectSalesOrderDetail
)
async def confirm_sales_order_costing(
    pso_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Accounts releases the costing hold (AC-K3, D28), handing it to the normal gate."""
    try:
        service, order = _order_for_edit(db, pso_id, current_user)
        service.confirm_costing(order, actor_user_id=current_user["id"])
        body = service.serialize_detail(
            order, review_states=service.review_states_for([order])
        )
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/sales-orders/{pso_id}/worksheet", response_model=SalesOrderWorksheet)
def sales_order_worksheet(
    pso_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """The AutoCount worksheet as data (Stage 1A, J02): the same document the CSV carries.

    Read-only, and the same grant as the detail beside it. ``can_export`` is answered here
    rather than on the screen so the publish gate has one owner.

    Plain ``def``, so FastAPI runs the whole handler in a threadpool: everything below is
    synchronous SQLAlchemy over a 100-line order, and on the event loop it holds up every
    other request the worker is serving (CLAUDE.md, the flyer-read measurement).
    """
    try:
        validate_uuid_path(pso_id, resource="Sales order")
        service = ProjectSODraftService(db)
        return service.worksheet(service.get_order(pso_id))
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/sales-orders/{pso_id}/import-file")
def sales_order_import_file(
    pso_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """The stage 1 AutoCount import file (D3), generated on demand rather than stored.

    Generated per request so it always matches the order as it stands: a stored file goes
    stale the moment an amendment publishes, and a stale import file is how a wrong
    document reaches AutoCount.

    The export gate is enforced here, not merely reported: `can_export` false means this
    document must not reach AutoCount, and a bookmarked url or a tab opened before the
    finding was raised would otherwise walk it straight out. Plain ``def`` for the same
    reason as the worksheet above.
    """
    try:
        validate_uuid_path(pso_id, resource="Sales order")
        service = ProjectSODraftService(db)
        order = service.get_order(pso_id)
        service.assert_can_export(order)
        filename, body = service.import_file(order)
        return Response(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


# ------------------------------------------------------- amendments and the OCN


@router.post(
    "/sales-orders/{pso_id}/amendments/preview", response_model=AmendmentPreviewResponse
)
async def preview_amendment(
    pso_id: str,
    payload: AmendmentPreviewRequest,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """Writes nothing. `unmatched` is never silently empty."""
    try:
        validate_uuid_path(pso_id, resource="Sales order")
        return ProjectSODeltaService(db).preview(
            pso_id,
            po_version_id=payload.po_version_id,
            schedule_version_id=payload.schedule_version_id,
        )
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/sales-orders/{pso_id}/amendments",
    response_model=AmendmentCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_amendment(
    pso_id: str,
    payload: AmendmentCreateRequest,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Persists the amendment and auto-drafts its order change notice from the same delta."""
    try:
        _service, order = _order_for_edit(db, pso_id, current_user)
        body = ProjectSODeltaService(db).create(
            order.id,
            po_version_id=payload.po_version_id,
            schedule_version_id=payload.schedule_version_id,
            reason=payload.reason,
            actor_user_id=current_user["id"],
        )
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/amendments/{amendment_id}", response_model=AmendmentDetail)
async def get_amendment(
    amendment_id: str,
    _user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(amendment_id, resource="Amendment")
        return ProjectSODeltaService(db).get_amendment(amendment_id)
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/amendments/{amendment_id}/publish", response_model=AmendmentPublishResponse
)
async def publish_amendment(
    amendment_id: str,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    """Applies the delta and moves the sales order to `amended`. 409 without an approver."""
    try:
        validate_uuid_path(amendment_id, resource="Amendment")
        service = ProjectSODeltaService(db)
        detail = service.get_amendment(amendment_id)
        project_id = ProjectSODraftService(db).get_order(
            detail["project_sales_order_id"]
        ).project_id
        project = projects.get_project_or_404(db, project_id)
        projects.assert_can_edit_project(
            db, project, current_user["id"], permission_slugs(db, current_user["id"])
        )
        body = service.publish_amendment(amendment_id, actor_user_id=current_user["id"])
        db.commit()
        return body
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
