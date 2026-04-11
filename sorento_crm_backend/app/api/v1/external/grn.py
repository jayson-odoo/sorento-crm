"""External API for GRN creation."""
from datetime import date
from typing import Union, List as ListType
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external.procurement import GRNRequest
from app.schemas.procurement import PickingHeaderCreate, PickingLineCreate, PickingHeaderResponse
from app.services.procurement_service import PickingHeaderService
from app.models.procurement import SPOAllocation
from app.api.v1.external.utils import (
    parse_date_value,
    get_products_by_code,
    get_warehouses_by_code_or_name,
    normalize_code,
)

router = APIRouter()


@router.post("/", response_model=PickingHeaderResponse, status_code=status.HTTP_201_CREATED)
def create_grn(
    payload: Union[GRNRequest, ListType[GRNRequest]],
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    # Accept single object or array with one element (take first)
    if isinstance(payload, list):
        if not payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request body array is empty")
        payload = payload[0]

    if not payload.grn_lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No GRN lines provided")

    product_codes = [item.product_code for item in payload.grn_lines]
    products_map = get_products_by_code(db, product_codes)
    missing_codes = [code for code in product_codes if normalize_code(code) not in products_map]
    if missing_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Missing product codes", "product_codes": missing_codes},
        )

    # Resolve warehouse from location where provided
    locations = [(item.location or "").strip() for item in payload.grn_lines if (item.location or "").strip() and not item.warehouse_id]
    warehouses_by_location = get_warehouses_by_code_or_name(db, locations) if locations else {}
    for loc in locations:
        if loc and normalize_code(loc) not in warehouses_by_location:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Warehouse not found for location", "location": loc},
            )

    # Resolve SPO allocation per line: prefer (spo_number, product_id, warehouse_id); fallback to (spo_number, spo_line_number)
    spo_map_by_triple = {}
    spo_map_by_line = {}
    if any(
        line.spo_allocation and (line.warehouse_id or (line.location or "").strip())
        for line in payload.grn_lines
    ):
        triples = set()
        for line in payload.grn_lines:
            if not line.spo_allocation:
                continue
            product_id = products_map[normalize_code(line.product_code)].id
            if line.warehouse_id:
                wh_id = line.warehouse_id
            elif (line.location or "").strip():
                wh_id = warehouses_by_location.get(normalize_code((line.location or "").strip()))
                wh_id = wh_id.id if wh_id else None
            else:
                wh_id = None
            if wh_id:
                triples.add((line.spo_allocation.strip(), product_id, wh_id))
        if triples:
            for (sn, pid, wid) in triples:
                alloc = (
                    db.query(SPOAllocation)
                    .filter(
                        SPOAllocation.spo_number == sn,
                        SPOAllocation.product_id == pid,
                        SPOAllocation.warehouse_id == wid,
                    )
                    .first()
                )
                if alloc:
                    spo_map_by_triple[(sn, pid, wid)] = alloc

    # Legacy: spo_allocation + spo_allocation_line
    spo_line_pairs = [
        (line.spo_allocation, line.spo_allocation_line)
        for line in payload.grn_lines
        if line.spo_allocation and line.spo_allocation_line is not None
    ]
    if spo_line_pairs:
        spo_allocations = db.query(SPOAllocation).filter(
            or_(*[
                and_(
                    SPOAllocation.spo_number == spo_number,
                    SPOAllocation.spo_line_number == spo_line_number,
                )
                for spo_number, spo_line_number in spo_line_pairs
            ])
        ).all()
        for alloc in spo_allocations:
            key = (alloc.spo_number, int(alloc.spo_line_number) if alloc.spo_line_number is not None else None)
            spo_map_by_line[key] = alloc

    def get_alloc_for_line(line):
        # Prefer match by (spo_number, product_id, warehouse_id)
        if line.spo_allocation:
            product_id = products_map[normalize_code(line.product_code)].id
            if line.warehouse_id:
                wh_id = line.warehouse_id
            elif (line.location or "").strip():
                w = warehouses_by_location.get(normalize_code((line.location or "").strip()))
                wh_id = w.id if w else None
            else:
                wh_id = None
            if wh_id:
                key = (line.spo_allocation.strip(), product_id, wh_id)
                if key in spo_map_by_triple:
                    return spo_map_by_triple[key]
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "No SPO allocation found for spo_number + product + warehouse",
                        "spo_number": line.spo_allocation,
                        "product_code": line.product_code,
                        "warehouse_id": wh_id,
                    },
                )
        # Legacy: spo_number + line
        if line.spo_allocation and line.spo_allocation_line is not None:
            key = (line.spo_allocation, int(line.spo_allocation_line))
            alloc = spo_map_by_line.get(key)
            if alloc is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"message": "Missing SPO allocation", "spo_number": line.spo_allocation, "spo_line_number": line.spo_allocation_line},
                )
            return alloc
        return None

    try:
        picking_date = parse_date_value(payload.goods_receive_notes.picking_date) or date.today()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    picking_lines_payload = []
    for line in payload.grn_lines:
        alloc = get_alloc_for_line(line)
        product_id = products_map[normalize_code(line.product_code)].id
        picking_lines_payload.append(
            PickingLineCreate(
                spo_allocation_id=alloc.id if alloc else None,
                product_id=product_id,
                quantity_expected=line.quantity,
                quantity_picked=line.quantity,
                uom_id=line.uom_id,
                destination_warehouse_id=alloc.warehouse_id if alloc else None,
            )
        )

    grn = PickingHeaderCreate(
        picking_number=payload.goods_receive_notes.picking_number,
        picking_type="goods_received",
        picking_date=picking_date,
        notes=payload.goods_receive_notes.notes,
        picking_lines=picking_lines_payload,
    )

    created_by = None if current_user.get("id") == "system" else current_user["id"]
    service = PickingHeaderService(db)
    return service.create_grn(grn, created_by=created_by)
