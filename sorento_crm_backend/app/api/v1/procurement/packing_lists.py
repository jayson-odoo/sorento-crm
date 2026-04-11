"""Packing lists (Inbound Shipments) API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Body
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.models.procurement import SPOAllocation, PickingHeader, PickingLine
from app.services.procurement_service import InboundShipmentService
from app.schemas.procurement import (
    InboundShipmentCreate,
    InboundShipmentUpdate,
    InboundShipmentListItemResponse,
    InboundShipmentResponse,
)
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


class BulkDeletePackingListsRequest(BaseModel):
    ids: list[str]


@router.get("/", response_model=ListResponse[InboundShipmentListItemResponse])
async def get_packing_lists(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
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
