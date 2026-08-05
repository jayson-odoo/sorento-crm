"""Packing lists (Inbound Shipments) API routes."""
from fastapi import APIRouter, Depends, File, Query, HTTPException, UploadFile, status, Body
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key, require_permission
from app.models.procurement import SPOAllocation, PickingHeader, PickingLine
from app.services.procurement_service import (
    DuplicatePackingListError,
    InboundShipmentService,
)
from app.schemas.procurement import (
    InboundShipmentCreate,
    InboundShipmentUpdate,
    InboundShipmentListItemResponse,
    InboundShipmentResponse,
)
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()


class BulkDeletePackingListsRequest(BaseModel):
    ids: list[str]


@router.get("/clearance-checkpoints")
async def list_clearance_checkpoints(
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """The configurable checkpoint definitions the clearance timeline renders.

    A timeline of independent checkpoints, NOT a single-position status graph: the
    real workbook has containers with a gatepass and no inspection, so a container
    reaches whichever checkpoints its dates say it reached, in any combination.

    Definitions live in `statuses` under entity_type `inbound_shipment` and are
    admin-editable in System Management -> Status Graphs. `key` is the
    `inbound_shipments` date column the checkpoint reads and is frozen on update,
    so renaming a checkpoint never breaks the link to its column.

    Deactivated checkpoints are omitted, which is how an admin hides one.
    """
    from app.models.status import Status
    from app.status_engine.entities.inbound_shipment import ENTITY_TYPE

    rows = (
        db.query(Status)
        .filter(
            Status.entity_type == ENTITY_TYPE,
            Status.is_active.is_(True),
            Status.is_archived.is_(False),
        )
        .order_by(Status.sort_order.asc(), Status.label.asc())
        .all()
    )
    return {
        "checkpoints": [
            {
                # The date column on the packing list payload this reads.
                "field": row.key,
                "label": row.label,
                "caption": row.description,
                "group": row.category,
                "color": row.color_hex,
                "sort_order": row.sort_order,
            }
            for row in rows
        ]
    }


@router.post("/container-status-import", status_code=status.HTTP_202_ACCEPTED)
async def import_container_status(
    file: UploadFile = File(..., description="Container Status workbook (.xlsx / .xls / .xlsm)."),
    validate_only: bool = Query(
        False, description="Dry run: report what would change and write nothing."
    ),
    current_user: dict = Depends(
        require_permission("procurement.packing_lists.import_container_status")
    ),
    db: Session = Depends(get_db),
):
    """Queue a container status import, or dry-run it.

    The entry point lives on Packing Lists because one sheet row IS one packing
    list. The workbook is parsed server-side: it holds 9 header blocks across 5
    tabs, so a client-side parse of the first sheet would see one block and miss
    most of the rows.

    ``validate_only=true`` returns 200 with
    ``{valid, errors[], warnings[], summary{total_rows, would_update, would_create,
    error_count}}``. Those summary keys are fixed by the shared frontend upload
    dialog, which renders exactly those and silently drops anything else.
    """
    from fastapi.responses import JSONResponse

    from app.services.excel_macro_stripper import maybe_strip
    from app.services.import_source_store import store_import_source_file
    from app.services.job_service import JobService
    from app.services.queue_service import enqueue_job
    from app.tasks.import_tasks import (
        process_container_status_import,
        validate_container_status_import,
    )

    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls", ".xlsm")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file.filename}. Please upload Excel (.xlsx, .xls or .xlsm).",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty."
        )

    cleaned, cleaned_name = maybe_strip(raw, file.filename)

    if validate_only:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=validate_container_status_import(cleaned, cleaned_name),
        )

    job_service = JobService(db)
    job = job_service.create_job(
        job_type="container_status_import",
        user_id=current_user["id"],
        filename=cleaned_name,
    )
    # Retain the ORIGINAL bytes, pre-macro-strip: the cost columns this importer
    # deliberately skips (D9) survive only in the retained file, and the assistant
    # serves the same workbook back to a contact who asks for it.
    store_import_source_file(job, raw, file.filename, file.content_type)
    db.commit()

    rq_job = enqueue_job(
        process_container_status_import,
        str(job.id),
        cleaned,
        cleaned_name,
        current_user["id"],
        queue_name="imports",
        job_timeout=3600,
        job_id=str(job.job_id),
    )
    job_service.update_job_with_rq_id(job, rq_job.id)

    return {
        "message": "Container status import queued.",
        "job_id": rq_job.id,
        "queued": True,
    }


@router.get("/", response_model=ListResponse[InboundShipmentListItemResponse])
async def get_packing_lists(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
    shipment_status: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get packing lists (inbound shipments) with pagination, filtering, and sorting."""
    try:
        service = InboundShipmentService(db)
        result = service.list_shipments(
            page=page,
            limit=limit,
            query=query,
            supplier_id=supplier_id,
            shipment_status=shipment_status,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/neighbours")
async def get_packing_list_neighbours(
    id: str = Query(..., description="Packing list (inbound shipment) id to resolve neighbours for"),
    query: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
    shipment_status: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Prev/next neighbours of a packing list within the active filtered+sorted list set.

    Accepts the same filter/sort/search params as the list GET (page/limit are
    irrelevant and ignored). Returns ``{total, index, prev_id, next_id}`` with the
    1-based ``index`` and circular wrap-around neighbours. If the record is not in
    the filtered set, falls back to the unfiltered, default-sorted set (D2).
    """
    try:
        service = InboundShipmentService(db)
        return service.neighbours(
            shipment_id=id,
            query=query,
            supplier_id=supplier_id,
            shipment_status=shipment_status,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{shipment_id}", response_model=InboundShipmentResponse)
async def get_packing_list(
    shipment_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get a single packing list by ID. Shipment lines include spo_allocated_quantity, quantity_received, and line_status (stored in DB for n8n/API)."""
    try:
        service = InboundShipmentService(db)
        shipment = service.get_shipment(shipment_id)
        # Refresh and persist line_status so n8n/API always have current value in DB
        service.refresh_shipment_line_statuses(shipment_id)
        # Reload shipment so line_status is in memory (refresh committed)
        shipment = service.get_shipment(shipment_id)
        # SPO allocated total per product on this shipment
        totals = (
            db.query(SPOAllocation.product_id, func.sum(SPOAllocation.allocated_quantity).label("total"))
            .filter(SPOAllocation.inbound_shipment_id == shipment_id)
            .group_by(SPOAllocation.product_id)
            .all()
        )
        spo_by_product = {str(p): int(t) for p, t in totals}
        received_by_product = service.get_received_quantities_by_product(shipment_id)
        allocations = (
            db.query(SPOAllocation)
            .filter(SPOAllocation.inbound_shipment_id == shipment_id)
            .order_by(SPOAllocation.created_at.asc())
            .all()
        )
        related_spo_by_product: dict[str, list[dict]] = {}
        spo_numbers_by_product: dict[str, set[str]] = {}
        all_spo_numbers: set[str] = set()
        for allocation in allocations:
            product_key = str(allocation.product_id)
            normalized_spo = (
                str(allocation.spo_number).strip().replace("/", ".").replace("\\", ".")
                if allocation.spo_number is not None
                else None
            )
            related_spo_by_product.setdefault(product_key, []).append(
                {
                    "id": str(allocation.id),
                    "spo_number": allocation.spo_number,
                    "allocated_quantity": allocation.allocated_quantity,
                    "receipt_status": allocation.receipt_status,
                }
            )
            if normalized_spo:
                spo_numbers_by_product.setdefault(product_key, set()).add(normalized_spo)
                all_spo_numbers.add(normalized_spo)

        related_grns_by_product: dict[str, list[dict]] = {}
        if all_spo_numbers:
            norm_expr = func.replace(
                func.replace(func.trim(PickingHeader.spo_number), "/", "."),
                "\\",
                ".",
            )
            grn_rows = (
                db.query(
                    PickingLine.product_id,
                    PickingHeader.id,
                    PickingHeader.picking_number,
                    PickingHeader.spo_number,
                    PickingHeader.picking_status,
                    PickingHeader.picking_date,
                )
                .join(PickingHeader, PickingLine.picking_header_id == PickingHeader.id)
                .filter(
                    PickingHeader.picking_type == "goods_received",
                    PickingHeader.spo_number.isnot(None),
                    norm_expr.in_(all_spo_numbers),
                )
                .group_by(
                    PickingLine.product_id,
                    PickingHeader.id,
                    PickingHeader.picking_number,
                    PickingHeader.spo_number,
                    PickingHeader.picking_status,
                    PickingHeader.picking_date,
                )
                .order_by(PickingHeader.picking_date.desc().nulls_last(), PickingHeader.picking_number)
                .all()
            )
            for product_id, grn_id, picking_number, spo_number, picking_status, picking_date in grn_rows:
                product_key = str(product_id)
                normalized_spo = (
                    str(spo_number).strip().replace("/", ".").replace("\\", ".")
                    if spo_number
                    else None
                )
                if normalized_spo not in spo_numbers_by_product.get(product_key, set()):
                    continue
                related_grns_by_product.setdefault(product_key, []).append(
                    {
                        "id": str(grn_id),
                        "picking_number": picking_number,
                        "spo_number": spo_number,
                        "picking_status": picking_status,
                        "picking_date": picking_date,
                    }
                )

        for line in shipment.shipment_lines:
            product_key = str(line.product_id)
            setattr(line, "spo_allocated_quantity", spo_by_product.get(product_key, 0))
            setattr(line, "quantity_received", received_by_product.get(product_key, 0))
            setattr(line, "related_spo_allocations", related_spo_by_product.get(product_key, []))
            setattr(line, "related_grns", related_grns_by_product.get(product_key, []))
        return shipment
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=InboundShipmentResponse, status_code=status.HTTP_201_CREATED)
async def create_packing_list(
    shipment_data: InboundShipmentCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new packing list (inbound shipment) with lines."""
    try:
        service = InboundShipmentService(db)
        shipment = service.create_shipment(shipment_data, current_user["id"])
        return shipment
    except HTTPException:
        raise
    except DuplicatePackingListError as exc:
        # Same container + ETA + shipment date as an already-received shipment.
        # Surface the explanation as a 409 — the bare `except Exception` below
        # would otherwise turn a user-fixable mistake into a 500.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{shipment_id}", response_model=InboundShipmentResponse)
async def update_packing_list(
    shipment_id: str,
    shipment_data: InboundShipmentUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a packing list."""
    try:
        service = InboundShipmentService(db)
        shipment = service.update_shipment(shipment_id, shipment_data, current_user["id"])
        return shipment
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_packing_lists(
    body: BulkDeletePackingListsRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk delete packing lists (inbound shipments) by ID."""
    try:
        service = InboundShipmentService(db)
        return service.bulk_delete_shipments(body.ids)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{shipment_id}", status_code=status.HTTP_200_OK)
async def delete_packing_list(
    shipment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a packing list (inbound shipment). Lines and SPO allocations cascade."""
    try:
        service = InboundShipmentService(db)
        service.delete_shipment(shipment_id)
        return {"message": "Packing list deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
