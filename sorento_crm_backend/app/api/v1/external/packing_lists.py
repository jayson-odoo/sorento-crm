"""External API for packing lists (inbound shipments)."""
import html
import logging
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.external.procurement import PackingListRequest, PackingListCreateResponse
from app.schemas.procurement import InboundShipmentCreate, InboundShipmentLineCreate, InboundShipmentResponse
from app.services.procurement_service import InboundShipmentService
from app.models.procurement import Supplier, InboundShipment
from app.models.resources import Attachment
from app.api.v1.external.utils import parse_date_value, get_products_by_code, normalize_code
from app.services.attachment_notification_helper import (
    build_packing_list_detail_url,
    notify_after_external_attachment_entity,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=PackingListCreateResponse, status_code=status.HTTP_201_CREATED)
def create_packing_list(
    payload: PackingListRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    # Validate supplier only when provided (supplier_id is optional for packing lists)
    if payload.packing_list.supplier_id is not None:
        supplier = db.query(Supplier).filter(Supplier.id == payload.packing_list.supplier_id).first()
        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid supplier_id",
            )

    # Validate attachment
    attachment = db.query(Attachment).filter(Attachment.id == payload.packing_list.attachment_id).first()
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid attachment_id",
        )

    product_codes = [item.product_code for item in payload.packing_list_products]
    products_map = get_products_by_code(db, product_codes)
    missing_codes = [code for code in product_codes if normalize_code(code) not in products_map]
    skipped_product_codes = list(missing_codes)
    if skipped_product_codes:
        logger.warning(
            "Packing list external API: skipping missing product codes (request still processed): %s",
            skipped_product_codes,
        )

    # Only include lines whose product_code exists; skip missing ones
    valid_items = [
        item for item in payload.packing_list_products
        if normalize_code(item.product_code) in products_map
    ]

    # Group by product_id and sum quantity (one row per product per shipment)
    by_product: dict[str, int] = {}
    for item in valid_items:
        product = products_map[normalize_code(item.product_code)]
        product_id = cast(str, product.id)
        by_product[product_id] = by_product.get(product_id, 0) + item.quantity

    try:
        shipment_date = parse_date_value(payload.packing_list.shipment_date)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not shipment_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid shipment_date")

    try:
        estimated_arrival_date = parse_date_value(payload.packing_list.estimated_arrival_date)
        actual_arrival_date = parse_date_value(payload.packing_list.actual_arrival_date)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    shipment = InboundShipmentCreate(
        shipment_number=payload.packing_list.shipment_number,
        supplier_id=payload.packing_list.supplier_id or None,
        shipment_date=shipment_date,
        estimated_arrival_date=estimated_arrival_date,
        actual_arrival_date=actual_arrival_date,
        bill_of_lading_number=payload.packing_list.bill_of_lading_number,
        shipping_container_number=payload.packing_list.shipping_container_number,
        invoice_number=payload.packing_list.invoice_number,
        shipment_status=payload.packing_list.shipment_status or "in_transit",
        total_items_shipped=payload.packing_list.total_items_shipped,
        total_cartons=payload.packing_list.total_cartons,
        notes=payload.packing_list.notes,
        attachment_id=payload.packing_list.attachment_id,
        shipment_lines=[
            InboundShipmentLineCreate(
                product_id=pid,
                quantity_shipped=qty,
            )
            for pid, qty in by_product.items()
        ],
    )

    # External API user has id "system" which is not a valid UUID; pass None for created_by when so
    created_by = current_user["id"] if current_user.get("id") != "system" else None
    service = InboundShipmentService(db)
    created = service.create_shipment(shipment, created_by=created_by)

    try:
        sn = (payload.packing_list.shipment_number or "").strip() or "—"
        aid = payload.packing_list.attachment_id
        summary_plain = (
            f'Packing list / inbound shipment "{sn}" was created in Sorento CRM via the external integration API '
            "(for example n8n)."
        )
        summary_html = (
            f"<p>Packing list / inbound shipment <strong>{html.escape(sn)}</strong> was created "
            "in Sorento CRM via the external integration API (for example n8n).</p>"
        )
        notify_after_external_attachment_entity(
            db,
            [aid],
            payload.notify_user_id,
            notif_type="external_packing_list_created",
            title=f"Packing list created: {sn}",
            summary_plain=summary_plain,
            summary_html=summary_html,
            entity_url=build_packing_list_detail_url(str(created.id)),
            entity_link_text="Open packing list in Sorento CRM",
            warnings=skipped_product_codes or None,
        )
    except Exception as e:
        logger.warning("External packing list notification failed: %s", e, exc_info=True)

    already_existed = bool(getattr(created, "_already_existed", False))
    return PackingListCreateResponse(
        shipment=InboundShipmentResponse.model_validate(created),
        skipped_product_codes=skipped_product_codes,
        unknown_product_codes=skipped_product_codes,
        already_existed=already_existed,
        message=("Packing list updated in place." if already_existed else None),
    )
