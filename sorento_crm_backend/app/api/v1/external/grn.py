"""External API for GRN creation."""
from datetime import date
from typing import Union, List as ListType
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external import GRNRequest
from app.schemas.procurement import PickingHeaderCreate, PickingLineCreate, PickingHeaderResponse
from app.services.procurement_service import PickingHeaderService
from app.models.procurement import SPOAllocation
from app.api.v1.external.utils import parse_date_value, get_products_by_code, normalize_code

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

    # Resolve SPO allocations if provided as spo_number + spo_line_number (location is based on SPO, no need to match location)
    spo_lookup_pairs = [
        (line.spo_allocation, line.spo_allocation_line)
        for line in payload.grn_lines
        if line.spo_allocation and line.spo_allocation_line is not None
    ]
    spo_map = {}
    if spo_lookup_pairs:
        spo_allocations = db.query(SPOAllocation).filter(
            or_(*[
                and_(
                    SPOAllocation.spo_number == spo_number,
                    SPOAllocation.spo_line_number == spo_line_number,
                )
                for spo_number, spo_line_number in spo_lookup_pairs
            ])
        ).all()
        # Key by (spo_number, spo_line_number) for lookup; ensure spo_line_number is int for consistency
        spo_map = {}
        for alloc in spo_allocations:
            key = (alloc.spo_number, int(alloc.spo_line_number) if alloc.spo_line_number is not None else None)
            spo_map[key] = alloc
        missing_pairs = [
            {"spo_number": sn, "spo_line_number": ln}
            for sn, ln in spo_lookup_pairs
            if (sn, int(ln) if ln is not None else None) not in spo_map
        ]
        if missing_pairs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Missing SPO allocation", "pairs": missing_pairs},
            )

    try:
        picking_date = parse_date_value(payload.goods_receive_notes.picking_date) or date.today()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    grn = PickingHeaderCreate(
        picking_number=payload.goods_receive_notes.picking_number,
        picking_type="goods_received",
        picking_date=picking_date,
        notes=payload.goods_receive_notes.notes,
        picking_lines=[
            PickingLineCreate(
                spo_allocation_id=alloc.id if (alloc := (
                    spo_map.get((line.spo_allocation, int(line.spo_allocation_line)))
                    if line.spo_allocation is not None and line.spo_allocation_line is not None
                    else None
                )) else None,
                product_id=products_map[normalize_code(line.product_code)].id,
                quantity_expected=line.quantity,
                quantity_picked=line.quantity,
                uom_id=line.uom_id,
                destination_warehouse_id=alloc.warehouse_id if alloc else None,
            )
            for line in payload.grn_lines
        ],
    )

    created_by = None if current_user.get("id") == "system" else current_user["id"]
    service = PickingHeaderService(db)
    return service.create_grn(grn, created_by=created_by)
