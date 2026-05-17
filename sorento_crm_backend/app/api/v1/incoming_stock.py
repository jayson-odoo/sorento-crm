"""User-facing incoming-stock API.

Purpose
-------
A tight, business-rule-compliant surface for answering "is there any incoming stock?" questions.
Intended to be the primary route used by the AI assistant / MCP layer. Unlike the underlying
procurement APIs, these routes:

  * exclude already-received lines,
  * compute `remaining_incoming_quantity` server-side,
  * aggregate warehouse allocations by warehouse_code (no SPO leakage),
  * never expose `quantity_received`, `quantity_rejected`, `receipt_status`,
  * never expose internal UUIDs, SPO numbers, picking-line identifiers, or inbound_shipment_lines_id.

See `next_agents/incoming_stock_enquiries.txt` for the source rules and `app/services/
incoming_stock_service.py` for the implementation.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.services.error_handler import handle_internal_error
from app.services.incoming_stock_service import IncomingStockService


router = APIRouter()


@router.get("/by-product")
def get_incoming_for_product(
    product_id: Optional[list[str]] = Query(
        None,
        description=(
            "One or more Product UUIDs / product_codes / SKUs. Accepts repeated query "
            "params (?product_id=A&product_id=B), a JSON array, or a comma-separated "
            "string (e.g. 'SRTMCB8082-BL,SRTWW8082-C'). Either product_id or query "
            "is required."
        ),
    ),
    query: Optional[str] = Query(
        None,
        description="Free-text search over product_code and product_name. Either product_id or query is required.",
    ),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Answer 'any incoming for product X?' questions.

    Returns, per matched product: total remaining incoming quantity, nearest ETA, per-warehouse
    allocation summary, and the individual open shipments (shipment_number, container_number,
    ETA, batch_number, remaining_incoming_quantity, per-shipment warehouse allocations,
    packing-list attachment).
    """
    product_ids: list[str] = []
    for raw in product_id or []:
        if raw is None:
            continue
        for piece in str(raw).split(","):
            piece = piece.strip()
            if piece:
                product_ids.append(piece)
    try:
        svc = IncomingStockService(db)
        return svc.incoming_for_product(product_ids=product_ids or None, query=query, limit=limit)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/shipments")
def get_incoming_shipments(
    query: Optional[str] = Query(
        None,
        description="Free-text search over shipment_number, shipping_container_number, bill_of_lading_number, invoice_number.",
    ),
    eta_from: Optional[date] = Query(None, description="Include shipments with ETA on/after this date."),
    eta_to: Optional[date] = Query(None, description="Include shipments with ETA on/before this date."),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Answer 'any incoming shipments?' / 'what is arriving this month?' questions.

    Only shipments that still have at least one still-incoming line are returned.
    """
    try:
        svc = IncomingStockService(db)
        return svc.incoming_shipments(
            query=query,
            eta_from=eta_from,
            eta_to=eta_to,
            page=page,
            limit=limit,
        )
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/shipments/{shipment_id}/products")
def get_incoming_shipment_products(
    shipment_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Answer 'what products are still incoming on this shipment?'.

    `shipment_id` accepts a UUID or any human-readable reference: shipment_number,
    shipping_container_number, bill_of_lading_number, invoice_number.
    """
    try:
        svc = IncomingStockService(db)
        return svc.shipment_incoming_products(shipment_id)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/shipments/{shipment_id}/attachment")
def get_incoming_shipment_attachment(
    shipment_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Fetch the packing list / shipment document attachment for a shipment.

    Returns `{shipment_number, attachment: {filename, file_path, mime_type}}`, or the same
    shape with `attachment: null` when no file is linked.
    """
    try:
        svc = IncomingStockService(db)
        data = svc.shipment_attachment(shipment_id)
        if data is None:
            return {"data": None, "empty": True}
        return {"data": data, "empty": data.get("attachment") is None}
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/grn")
def get_incoming_stock_grn(
    shipment_id: Optional[str] = Query(
        None,
        description="Shipment UUID or any business reference (shipment_number / container / BOL / invoice).",
    ),
    product_id: Optional[str] = Query(
        None,
        description="Product UUID or product_code / SKU.",
    ),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Surface GRN (goods received note) records only when the user explicitly asks.

    Returns minimal fields (`grn_number`, `grn_date`, `grn_status`, `shipment_number`) — no
    quantities and no internal IDs. Requires at least one of `shipment_id` or `product_id`.
    """
    try:
        if not shipment_id and not product_id:
            return {
                "data": [],
                "empty": True,
                "message": "Provide shipment_id or product_id.",
            }
        svc = IncomingStockService(db)
        return svc.grn_records(shipment_id=shipment_id, product_id=product_id, limit=limit)
    except Exception as e:
        raise handle_internal_error(str(e))
