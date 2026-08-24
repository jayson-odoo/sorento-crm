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
from app.services.field_access import CLEARANCE_PERMISSION, apply_field_access
from app.services.error_handler import handle_internal_error
from app.services.incoming_stock_service import IncomingStockService
from app.services.uuid_list_param import parse_uuid_list


router = APIRouter()


@router.get("/by-product")
def get_incoming_for_product(
    entities: Optional[list[str]] = Query(
        None,
        description="DEPRECATED - free-text entity bag. Prefer `product_ids`.",
    ),
    product_ids: Optional[list[str]] = Query(
        None,
        description="Canonical product UUIDs (csv/JSON/repeated). Preferred filter.",
    ),
    product_id: Optional[list[str]] = Query(
        None,
        description="Legacy: product UUID / product_code. Direct callers can keep using this.",
    ),
    query: Optional[str] = Query(
        None,
        description="Free-text search over product_code and product_name.",
    ),
    eta_from: Optional[date] = Query(None, description="Include shipments with ETA on/after this date (YYYY-MM-DD)."),
    eta_to: Optional[date] = Query(None, description="Include shipments with ETA on/before this date (YYYY-MM-DD)."),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Answer 'any incoming for product X?' questions.

    Returns, per matched product: total remaining incoming quantity, nearest ETA, per-warehouse
    allocation summary, and the individual open shipments. Optional `eta_from` / `eta_to`
    narrow to shipments arriving within a date window.
    """
    from app.services.entity_filter_helpers import (
        normalize_entities_query_param,
        resolve_or_empty,
    )

    resolved_product_filter: list[str] = []
    # Validated UUID list from the canonical param.
    uuid_list = parse_uuid_list(product_ids, param_name="product_ids")
    if uuid_list:
        resolved_product_filter.extend(uuid_list)
    # Legacy product_id (UUID-or-code, comma-separated allowed).
    for raw in product_id or []:
        if raw is None:
            continue
        for piece in str(raw).split(","):
            piece = piece.strip()
            if piece:
                resolved_product_filter.append(piece)

    # Resolve entities → product_codes → push through legacy product_ids path.
    entity_echo = None
    norm = normalize_entities_query_param(entities)
    if norm:
        buckets = resolve_or_empty(db, norm)
        if buckets is not None:
            entity_echo = buckets.as_echo()
            if not buckets.product_codes:
                return {
                    "data": [],
                    "empty": True,
                    "resolved_entities": entity_echo,
                }
            resolved_product_filter.extend(buckets.product_codes)
    try:
        svc = IncomingStockService(db)
        result = svc.incoming_for_product(
            product_ids=resolved_product_filter or None,
            query=query,
            eta_from=eta_from,
            eta_to=eta_to,
            limit=limit,
        )
        if entity_echo is not None and isinstance(result, dict):
            result["resolved_entities"] = entity_echo
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/shipments")
def get_incoming_shipments(
    entities: Optional[list[str]] = Query(
        None,
        description="DEPRECATED - free-text entity bag. Prefer `shipment_ids` / `supplier_ids`.",
    ),
    shipment_ids: Optional[list[str]] = Query(
        None,
        description="Canonical inbound-shipment UUIDs (csv/JSON/repeated).",
    ),
    supplier_ids: Optional[list[str]] = Query(
        None,
        description="Canonical supplier UUIDs to narrow shipments to those suppliers.",
    ),
    query: Optional[str] = Query(
        None,
        description="Free-text search over shipment_number, container, BOL, invoice.",
    ),
    eta_from: Optional[date] = Query(None, description="Include shipments with ETA on/after this date."),
    eta_to: Optional[date] = Query(None, description="Include shipments with ETA on/before this date."),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Answer 'any incoming shipments?' / 'what is arriving this month?' questions."""
    from app.services.entity_filter_helpers import (
        normalize_entities_query_param,
        resolve_or_empty,
    )

    entity_echo = None
    extra_query = query
    shipment_uuid_list = parse_uuid_list(shipment_ids, param_name="shipment_ids")
    supplier_uuid_list = parse_uuid_list(supplier_ids, param_name="supplier_ids")
    norm = normalize_entities_query_param(entities)
    if norm:
        buckets = resolve_or_empty(db, norm)
        if buckets is not None:
            entity_echo = buckets.as_echo()
            if buckets.shipment_numbers:
                # service supports free-text `query` that searches shipment_number;
                # join multiple resolved numbers with OR via repeated calls? Simplest:
                # use first resolved shipment_number as the search term. If multiple,
                # narrow via service-side IN by extending `query` to first hit.
                extra_query = buckets.shipment_numbers[0]
            elif not buckets.has_resolved_filter:
                return {
                    "data": [],
                    "empty": True,
                    "resolved_entities": entity_echo,
                }
    try:
        svc = IncomingStockService(db)
        result = svc.incoming_shipments(
            query=extra_query,
            shipment_ids=shipment_uuid_list,
            supplier_ids=supplier_uuid_list,
            eta_from=eta_from,
            eta_to=eta_to,
            page=page,
            limit=limit,
        )
        if entity_echo is not None and isinstance(result, dict):
            result["resolved_entities"] = entity_echo
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/list")
def get_incoming_list(
    product_ids: Optional[list[str]] = Query(
        None,
        description="Canonical product UUIDs or product_codes/SKUs (csv/JSON/repeated). When set, lines are filtered to these products.",
    ),
    shipment_ids: Optional[list[str]] = Query(
        None,
        description="Canonical inbound-shipment UUIDs (csv/JSON/repeated).",
    ),
    supplier_ids: Optional[list[str]] = Query(
        None,
        description="Canonical supplier UUIDs to narrow shipments to those suppliers.",
    ),
    query: Optional[str] = Query(
        None,
        description="Free-text search over shipment_number, container, BOL, invoice.",
    ),
    eta_from: Optional[date] = Query(None, description="Include shipments with ETA on/after this date (YYYY-MM-DD)."),
    eta_to: Optional[date] = Query(None, description="Include shipments with ETA on/before this date (YYYY-MM-DD)."),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    contact_id: Optional[str] = Query(
        None,
        description=(
            "The contact this question is being asked ON BEHALF OF - either the "
            "respond_contacts.id or the Respond.io id. When set, clearance dates "
            "are returned only for the fields allowed on that contact's own agent "
            "grants; the API key's privileges do not apply to a contact's question. "
            "Denied fields are absent, and the reason is in `field_access.denied`."
        ),
    ),
    space_id: Optional[str] = Query(
        None,
        description=(
            "Respond.io workspace id. Only used to disambiguate `contact_id` when "
            "it is a Respond.io id: the same id can exist in two workspaces, and "
            "resolving to the wrong one would answer with a stranger's grants."
        ),
    ),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Unified incoming-stock list - shipment-rooted with nested product lines.

    One MCP tool covers both "any incoming for product X?" (pass `product_ids`)
    and "what is arriving this month / from supplier Y?" (pass `eta_*` /
    `supplier_ids` / `shipment_ids`). Each shipment row carries its still-incoming
    product lines with per-warehouse allocations and the packing-list attachment.
    No aggregate totals - callers sum the line quantities themselves. At least one
    narrowing filter is required.
    """
    # product_ids may be UUIDs or product_codes, csv-joined or repeated; flatten
    # to individual tokens (the service resolves both UUID and code per token).
    flat_product_ids: list[str] = []
    for raw in product_ids or []:
        if raw is None:
            continue
        for piece in str(raw).split(","):
            piece = piece.strip()
            if piece:
                flat_product_ids.append(piece)
    try:
        svc = IncomingStockService(db)
        # product_ids may be UUIDs or product_codes; the service resolves both, so
        # pass through raw rather than via parse_uuid_list (which rejects codes).
        result = svc.incoming_list(
            product_ids=flat_product_ids or None,
            shipment_ids=parse_uuid_list(shipment_ids, param_name="shipment_ids"),
            supplier_ids=parse_uuid_list(supplier_ids, param_name="supplier_ids"),
            query=query,
            eta_from=eta_from,
            eta_to=eta_to,
            page=page,
            limit=limit,
        )
        # Clearance dates are OMITTED, not nulled, for an unentitled caller: absent
        # means "you may not see this", null would mean "not reached yet", and an
        # LLM reading the response will narrate a null as the latter. The reason
        # rides along in a `field_access` block so the answer can say "I can't
        # share that" instead of inventing a status.
        return apply_field_access(
            db,
            result,
            resource="incoming_stock",
            current_user=current_user,
            contact_id=contact_id,
            space_id=space_id,
            staff_permission=CLEARANCE_PERMISSION,
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
    entities: Optional[list[str]] = Query(
        None,
        description="DEPRECATED - free-text entity bag. Prefer `shipment_ids` / `product_ids`.",
    ),
    shipment_ids: Optional[list[str]] = Query(
        None,
        description="Canonical inbound-shipment UUIDs (csv/JSON/repeated).",
    ),
    product_ids: Optional[list[str]] = Query(
        None,
        description="Canonical product UUIDs to narrow GRNs to lines referencing these products.",
    ),
    shipment_id: Optional[str] = Query(
        None,
        description="Legacy: shipment UUID or business reference.",
    ),
    product_id: Optional[str] = Query(
        None,
        description="Legacy: product UUID or product_code.",
    ),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Surface GRN (goods received note) records only when the user explicitly asks."""
    from app.services.entity_filter_helpers import (
        normalize_entities_query_param,
        resolve_or_empty,
    )
    from app.services.identifier_resolver import resolve_identifier
    from app.models.procurement import InboundShipment as _InboundShipment
    from app.models.product import Product as _Product

    entity_echo = None
    shipment_uuids: Optional[list[str]] = parse_uuid_list(shipment_ids, param_name="shipment_ids")
    product_uuids: Optional[list[str]] = parse_uuid_list(product_ids, param_name="product_ids")
    norm = normalize_entities_query_param(entities)
    if norm:
        buckets = resolve_or_empty(db, norm)
        if buckets is not None:
            entity_echo = buckets.as_echo()
            # Resolve ALL bucket entries to UUIDs (do not collapse to [0]). Merge
            # with explicit kwargs so callers can mix entities + typed UUIDs.
            if buckets.shipment_numbers:
                acc: list[str] = list(shipment_uuids or [])
                for code in buckets.shipment_numbers:
                    ids = resolve_identifier(
                        db,
                        code,
                        _InboundShipment,
                        code_fields=(
                            "shipment_number",
                            "shipping_container_number",
                            "bill_of_lading_number",
                            "invoice_number",
                        ),
                    )
                    if ids:
                        acc.extend(ids)
                shipment_uuids = list(dict.fromkeys(acc)) or None
            if buckets.product_codes:
                acc = list(product_uuids or [])
                for code in buckets.product_codes:
                    ids = resolve_identifier(
                        db, code, _Product, code_fields=("product_code",)
                    )
                    if ids:
                        acc.extend(ids)
                product_uuids = list(dict.fromkeys(acc)) or None
            if not shipment_uuids and not product_uuids and not shipment_id and not product_id:
                return {
                    "data": [],
                    "empty": True,
                    "message": "No product or shipment resolved from entities.",
                    "resolved_entities": entity_echo,
                }
    try:
        if not shipment_uuids and not product_uuids and not shipment_id and not product_id:
            return {
                "data": [],
                "empty": True,
                "message": "Provide entities or shipment_id or product_id.",
            }
        svc = IncomingStockService(db)
        result = svc.grn_records(
            shipment_id=shipment_id,
            product_id=product_id,
            shipment_uuids=shipment_uuids,
            product_uuids=product_uuids,
            limit=limit,
        )
        if entity_echo is not None and isinstance(result, dict):
            result["resolved_entities"] = entity_echo
        return result
    except Exception as e:
        raise handle_internal_error(str(e))
