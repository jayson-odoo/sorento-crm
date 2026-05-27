"""Incoming-stock service: user-facing business logic for "is there incoming stock?" enquiries.

This service enforces the rules from next_agents/incoming_stock_enquiries.txt:

- Only "still incoming" rows are considered:
    * `line_status != 'received'`
    * `remaining_incoming = max(quantity_shipped - quantity_received, 0) > 0`

- The response NEVER exposes:
    * internal UUIDs (shipment id, product id, spo allocation id, attachment id...)
    * `quantity_received`, `quantity_rejected`, `receipt_status`, SPO numbers, picking-line ids
    * any information about what has already been received

- The response DOES expose:
    * product_code, product_name
    * shipment_number, shipping_container_number, estimated_arrival_date, batch_number
    * warehouse_code, warehouse_name, allocated_quantity (aggregated per warehouse)
    * attachment filename / file_path / mime_type (only when present)
    * remaining_incoming_quantity (computed server-side)

The source of truth for "still incoming" is `inbound_shipment_lines`; `spo_allocations` is used
only to aggregate warehouse allocation summaries. GRN / picking data is NEVER read here — it is
surfaced through a separate, explicit method only when the user asks.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Optional

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    InboundShipmentLine,
    PickingHeader,
    PickingLine,
    SPOAllocation,
)
from app.models.product import Product
from app.models.resources import Attachment
from app.services.identifier_resolver import resolve_identifier
from app.services.fuzzy_resolver import resolve_via_embedding_then_ilike


# Line statuses considered "received" and therefore excluded from incoming-stock results.
_RECEIVED_STATUSES = ("received",)


def _remaining_expr():
    """SQL expression: GREATEST(quantity_shipped - quantity_received, 0)."""
    diff = InboundShipmentLine.quantity_shipped - func.coalesce(InboundShipmentLine.quantity_received, 0)
    return case((diff > 0, diff), else_=0)


def _still_incoming_filter():
    """Filter clause: line is still incoming (status != received AND remaining > 0)."""
    remaining = _remaining_expr()
    return and_(
        ~InboundShipmentLine.line_status.in_(_RECEIVED_STATUSES),
        remaining > 0,
    )


def _attachment_payload(attachment: Optional[Attachment]) -> Optional[dict[str, Any]]:
    if attachment is None:
        return None
    return {
        "filename": attachment.original_filename,
        "file_path": attachment.file_path,
        "mime_type": attachment.mime_type,
    }


class IncomingStockService:
    """User-facing incoming-stock retrieval."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def _warehouse_allocations_for(
        self, shipment_product_pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        """Aggregate allocated_quantity by warehouse for each (shipment_id, product_id) pair.

        Returns {(shipment_id, product_id): [{warehouse_code, warehouse_name, allocated_quantity}]}.
        Only SPO allocations with allocated_quantity > 0 are included. No receipt data leaks.
        """
        if not shipment_product_pairs:
            return {}
        shipment_ids = list({sid for sid, _ in shipment_product_pairs})
        product_ids = list({pid for _, pid in shipment_product_pairs})
        rows = (
            self.db.query(
                SPOAllocation.inbound_shipment_id,
                SPOAllocation.product_id,
                Warehouse.warehouse_code,
                Warehouse.warehouse_name,
                func.coalesce(func.sum(SPOAllocation.allocated_quantity), 0).label("allocated_qty"),
            )
            .join(Warehouse, Warehouse.id == SPOAllocation.warehouse_id)
            .filter(
                SPOAllocation.inbound_shipment_id.in_(shipment_ids),
                SPOAllocation.product_id.in_(product_ids),
                SPOAllocation.allocated_quantity > 0,
            )
            .group_by(
                SPOAllocation.inbound_shipment_id,
                SPOAllocation.product_id,
                Warehouse.warehouse_code,
                Warehouse.warehouse_name,
            )
            .order_by(Warehouse.warehouse_code.asc())
            .all()
        )
        result: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for shipment_id, product_id, wh_code, wh_name, qty in rows:
            key = (str(shipment_id), str(product_id))
            result[key].append(
                {
                    "warehouse_code": wh_code,
                    "warehouse_name": wh_name,
                    "allocated_quantity": int(qty or 0),
                }
            )
        return result

    def _attachments_for_shipments(
        self, shipment_ids: list[str]
    ) -> dict[str, Optional[dict[str, Any]]]:
        if not shipment_ids:
            return {}
        rows = (
            self.db.query(InboundShipment.id, Attachment)
            .outerjoin(Attachment, Attachment.id == InboundShipment.attachment_id)
            .filter(InboundShipment.id.in_(shipment_ids))
            .all()
        )
        return {str(sid): _attachment_payload(att) for sid, att in rows}

    # ------------------------------------------------------------------
    # Layer 1 + 2: by product
    # ------------------------------------------------------------------
    def incoming_for_product(
        self,
        *,
        product_id: Optional[str] = None,
        product_ids: Optional[list[str]] = None,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Return incoming-stock summary grouped by product.

        Accepts one or many `product_ids` (UUID or product_code / SKU). Legacy
        single `product_id` parameter is folded into the list. A free-text
        `query` may be supplied instead; results are filtered to still-incoming
        lines only.
        """
        limit = max(1, min(limit, 50))

        raw_ids: list[str] = []
        if product_id:
            raw_ids.append(product_id)
        for value in product_ids or []:
            if value:
                raw_ids.append(value)
        # Dedupe while preserving order.
        raw_ids = list(dict.fromkeys(raw_ids))

        product_filters = []
        matched_candidates: list[str] = []
        if raw_ids:
            resolved_ids: list[str] = []
            for ident in raw_ids:
                ids = resolve_identifier(
                    self.db, ident, Product, code_fields=("product_code",)
                )
                if ids:
                    resolved_ids.extend(ids)
            resolved_ids = list(dict.fromkeys(resolved_ids))
            if not resolved_ids:
                return {"data": [], "empty": True, "matched_candidates": []}
            product_filters.append(Product.id.in_(resolved_ids))
        if query and query.strip():
            fuzzy_clause, canonical_values = resolve_via_embedding_then_ilike(
                self.db,
                query.strip(),
                source_type="product",
                ilike_columns=[Product.product_code, Product.product_name],
                canonical_model=Product,
                canonical_fields=("product_code", "product_name"),
            )
            if fuzzy_clause is not None:
                product_filters.append(fuzzy_clause)
            for v in canonical_values:
                if v and v not in matched_candidates:
                    matched_candidates.append(v)
        if not product_filters:
            # Require at least one product hint to avoid accidental full scans
            return {
                "data": [],
                "empty": True,
                "matched_candidates": matched_candidates,
                "message": "Provide product_id (UUID or product_code) or a query term.",
            }

        remaining = _remaining_expr().label("remaining_incoming")
        rows = (
            self.db.query(
                InboundShipmentLine.shipment_id,
                InboundShipmentLine.product_id,
                InboundShipmentLine.batch_number,
                remaining,
                InboundShipment.shipment_number,
                InboundShipment.shipping_container_number,
                InboundShipment.estimated_arrival_date,
                Product.product_code,
                Product.product_name,
            )
            .join(InboundShipment, InboundShipment.id == InboundShipmentLine.shipment_id)
            .join(Product, Product.id == InboundShipmentLine.product_id)
            .filter(_still_incoming_filter(), *product_filters)
            .order_by(
                Product.product_code.asc(),
                InboundShipment.estimated_arrival_date.asc().nulls_last(),
                InboundShipment.shipment_number.asc(),
            )
            .all()
        )

        if not rows:
            return {"data": [], "empty": True, "matched_candidates": matched_candidates}

        pairs = [(str(r.shipment_id), str(r.product_id)) for r in rows]
        warehouse_map = self._warehouse_allocations_for(pairs)
        attachment_map = self._attachments_for_shipments(
            [str(r.shipment_id) for r in rows]
        )

        grouped: dict[str, dict[str, Any]] = {}
        for r in rows:
            pkey = str(r.product_id)
            bucket = grouped.setdefault(
                pkey,
                {
                    "product_code": r.product_code,
                    "product_name": r.product_name,
                    "total_remaining_incoming_quantity": 0,
                    "nearest_estimated_arrival_date": None,
                    "warehouse_allocation_summary": defaultdict(lambda: {"qty": 0, "name": None}),
                    "shipments": [],
                },
            )
            bucket["total_remaining_incoming_quantity"] += int(r.remaining_incoming or 0)
            if r.estimated_arrival_date is not None:
                current = bucket["nearest_estimated_arrival_date"]
                if current is None or r.estimated_arrival_date < current:
                    bucket["nearest_estimated_arrival_date"] = r.estimated_arrival_date

            ship_allocations = warehouse_map.get((str(r.shipment_id), pkey), [])
            for alloc in ship_allocations:
                agg = bucket["warehouse_allocation_summary"][alloc["warehouse_code"]]
                agg["qty"] += int(alloc["allocated_quantity"] or 0)
                agg["name"] = alloc["warehouse_name"]

            bucket["shipments"].append(
                {
                    "shipment_number": r.shipment_number,
                    "shipping_container_number": r.shipping_container_number,
                    "estimated_arrival_date": r.estimated_arrival_date,
                    "batch_number": r.batch_number,
                    "remaining_incoming_quantity": int(r.remaining_incoming or 0),
                    "warehouse_allocations": ship_allocations,
                    "attachment": attachment_map.get(str(r.shipment_id)),
                }
            )

        data: list[dict[str, Any]] = []
        for bucket in grouped.values():
            summary = [
                {
                    "warehouse_code": code,
                    "warehouse_name": agg["name"],
                    "allocated_quantity": int(agg["qty"]),
                }
                for code, agg in sorted(bucket["warehouse_allocation_summary"].items())
            ]
            bucket["warehouse_allocation_summary"] = summary
            data.append(bucket)

        data.sort(key=lambda d: (d["product_code"] or "").lower())
        return {
            "data": data[:limit],
            "empty": False,
            "pagination": {"total": len(data), "page": 1, "limit": limit},
            "matched_candidates": matched_candidates,
        }

    # ------------------------------------------------------------------
    # Layer 1: shipments (T2)
    # ------------------------------------------------------------------
    def incoming_shipments(
        self,
        *,
        query: Optional[str] = None,
        shipment_ids: Optional[list[str]] = None,
        supplier_ids: Optional[list[str]] = None,
        eta_from: Optional[date] = None,
        eta_to: Optional[date] = None,
        page: int = 1,
        limit: int = 10,
    ) -> dict[str, Any]:
        """List shipments that still have incoming lines, user-facing fields only."""
        page = max(1, page)
        limit = max(1, min(limit, 50))

        incoming_lines = (
            self.db.query(
                InboundShipmentLine.shipment_id.label("sid"),
                func.count(func.distinct(InboundShipmentLine.product_id)).label("distinct_products"),
                func.sum(_remaining_expr()).label("total_remaining"),
            )
            .filter(_still_incoming_filter())
            .group_by(InboundShipmentLine.shipment_id)
            .subquery()
        )

        q = (
            self.db.query(
                InboundShipment.id,
                InboundShipment.shipment_number,
                InboundShipment.shipping_container_number,
                InboundShipment.estimated_arrival_date,
                incoming_lines.c.distinct_products,
                incoming_lines.c.total_remaining,
            )
            .join(incoming_lines, incoming_lines.c.sid == InboundShipment.id)
        )

        if shipment_ids:
            q = q.filter(InboundShipment.id.in_(shipment_ids))
        if supplier_ids:
            q = q.filter(InboundShipment.supplier_id.in_(supplier_ids))
        if query:
            term = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    InboundShipment.shipment_number.ilike(term),
                    InboundShipment.shipping_container_number.ilike(term),
                    InboundShipment.bill_of_lading_number.ilike(term),
                    InboundShipment.invoice_number.ilike(term),
                )
            )
        if eta_from is not None:
            q = q.filter(InboundShipment.estimated_arrival_date >= eta_from)
        if eta_to is not None:
            q = q.filter(InboundShipment.estimated_arrival_date <= eta_to)

        total = q.count()
        rows = (
            q.order_by(
                InboundShipment.estimated_arrival_date.asc().nulls_last(),
                InboundShipment.shipment_number.asc(),
            )
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        if not rows:
            return {"data": [], "empty": True, "pagination": {"total": 0, "page": page, "limit": limit}}

        attachment_map = self._attachments_for_shipments([str(r.id) for r in rows])

        data = [
            {
                "shipment_number": r.shipment_number,
                "shipping_container_number": r.shipping_container_number,
                "estimated_arrival_date": r.estimated_arrival_date,
                "total_remaining_incoming_quantity": int(r.total_remaining or 0),
                "distinct_products_incoming": int(r.distinct_products or 0),
                "attachment": attachment_map.get(str(r.id)),
            }
            for r in rows
        ]
        return {"data": data, "empty": False, "pagination": {"total": total, "page": page, "limit": limit}}

    # ------------------------------------------------------------------
    # Layer 1 + 2: products in a shipment (T3)
    # ------------------------------------------------------------------
    def shipment_incoming_products(self, shipment_id: str) -> dict[str, Any]:
        """Return only the still-incoming products on a given shipment, with warehouse allocation."""
        resolved = resolve_identifier(
            self.db,
            shipment_id,
            InboundShipment,
            code_fields=(
                "shipment_number",
                "shipping_container_number",
                "bill_of_lading_number",
                "invoice_number",
            ),
        )
        if resolved is None or not resolved:
            return {"data": None, "empty": True}
        # If multiple shipments match a business code we want the first (numbers are unique).
        shipment_uuid = resolved[0]

        shipment = (
            self.db.query(InboundShipment).filter(InboundShipment.id == shipment_uuid).first()
        )
        if not shipment:
            return {"data": None, "empty": True}

        remaining = _remaining_expr().label("remaining_incoming")
        line_rows = (
            self.db.query(
                InboundShipmentLine.product_id,
                remaining,
                Product.product_code,
                Product.product_name,
            )
            .join(Product, Product.id == InboundShipmentLine.product_id)
            .filter(
                InboundShipmentLine.shipment_id == shipment_uuid,
                _still_incoming_filter(),
            )
            .order_by(Product.product_code.asc())
            .all()
        )

        attachment = (
            self.db.query(Attachment)
            .filter(Attachment.id == shipment.attachment_id)
            .first()
            if shipment.attachment_id
            else None
        )

        if not line_rows:
            return {
                "data": {
                    "shipment_number": shipment.shipment_number,
                    "shipping_container_number": shipment.shipping_container_number,
                    "estimated_arrival_date": shipment.estimated_arrival_date,
                    "attachment": _attachment_payload(attachment),
                    "products": [],
                },
                "empty": True,
            }

        pairs = [(str(shipment_uuid), str(r.product_id)) for r in line_rows]
        warehouse_map = self._warehouse_allocations_for(pairs)

        products = [
            {
                "product_code": r.product_code,
                "product_name": r.product_name,
                "remaining_incoming_quantity": int(r.remaining_incoming or 0),
                "warehouse_allocations": warehouse_map.get((str(shipment_uuid), str(r.product_id)), []),
            }
            for r in line_rows
        ]

        return {
            "data": {
                "shipment_number": shipment.shipment_number,
                "shipping_container_number": shipment.shipping_container_number,
                "estimated_arrival_date": shipment.estimated_arrival_date,
                "attachment": _attachment_payload(attachment),
                "products": products,
            },
            "empty": False,
        }

    # ------------------------------------------------------------------
    # Layer 3: attachment
    # ------------------------------------------------------------------
    def shipment_attachment(self, shipment_id: str) -> Optional[dict[str, Any]]:
        resolved = resolve_identifier(
            self.db,
            shipment_id,
            InboundShipment,
            code_fields=(
                "shipment_number",
                "shipping_container_number",
                "bill_of_lading_number",
                "invoice_number",
            ),
        )
        if resolved is None or not resolved:
            return None
        row = (
            self.db.query(InboundShipment.shipment_number, Attachment)
            .outerjoin(Attachment, Attachment.id == InboundShipment.attachment_id)
            .filter(InboundShipment.id == resolved[0])
            .first()
        )
        if not row:
            return None
        shipment_number, attachment = row
        return {
            "shipment_number": shipment_number,
            "attachment": _attachment_payload(attachment),
        }

    # ------------------------------------------------------------------
    # Layer 4: GRN (only on explicit request)
    # ------------------------------------------------------------------
    def grn_records(
        self,
        *,
        shipment_id: Optional[str] = None,
        product_id: Optional[str] = None,
        shipment_uuids: Optional[list[str]] = None,
        product_uuids: Optional[list[str]] = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Minimal GRN records for explicit 'has a GRN been created?' enquiries.

        No quantities are surfaced. GRN matches via two paths (union):
          (1) SPO path: PickingHeader.spo_number → SPOAllocation (shipment + product)
          (2) Direct path: PickingLine.product_id (covers GRNs without SPO linkage)
        Either path satisfies the filter; both run when product is supplied.

        Callers may pass either single string ids (legacy: resolved via `resolve_identifier`)
        or pre-resolved UUID lists (`shipment_uuids` / `product_uuids` from entity buckets).
        UUID lists take precedence when both are supplied.
        """
        limit = max(1, min(limit, 50))

        if shipment_uuids is None and shipment_id:
            shipment_uuids = resolve_identifier(
                self.db,
                shipment_id,
                InboundShipment,
                code_fields=(
                    "shipment_number",
                    "shipping_container_number",
                    "bill_of_lading_number",
                    "invoice_number",
                ),
            )
            if shipment_uuids is not None and not shipment_uuids:
                return {"data": [], "empty": True}
        if product_uuids is None and product_id:
            product_uuids = resolve_identifier(
                self.db, product_id, Product, code_fields=("product_code",)
            )
            if product_uuids is not None and not product_uuids:
                return {"data": [], "empty": True}

        if not shipment_uuids and not product_uuids:
            return {"data": [], "empty": True}

        shipment_number_expr = InboundShipment.shipment_number

        # Path 1: via SPO allocations + PickingHeader.spo_number.
        spo_alloc_filter = [SPOAllocation.spo_number.isnot(None)]
        if shipment_uuids:
            spo_alloc_filter.append(SPOAllocation.inbound_shipment_id.in_(shipment_uuids))
        if product_uuids:
            spo_alloc_filter.append(SPOAllocation.product_id.in_(product_uuids))
        spo_numbers = [
            s[0]
            for s in self.db.query(func.distinct(SPOAllocation.spo_number))
            .filter(*spo_alloc_filter)
            .all()
            if s[0]
        ]

        spo_rows: list = []
        if spo_numbers:
            spo_rows = (
                self.db.query(
                    PickingHeader.picking_number,
                    PickingHeader.picking_date,
                    PickingHeader.picking_status,
                    shipment_number_expr.label("shipment_number"),
                )
                .join(PickingLine, PickingLine.picking_header_id == PickingHeader.id)
                .join(SPOAllocation, SPOAllocation.id == PickingLine.spo_allocation_id)
                .join(InboundShipment, InboundShipment.id == SPOAllocation.inbound_shipment_id)
                .filter(
                    PickingHeader.picking_type == "goods_received",
                    PickingHeader.spo_number.in_(spo_numbers),
                )
                .group_by(
                    PickingHeader.picking_number,
                    PickingHeader.picking_date,
                    PickingHeader.picking_status,
                    shipment_number_expr,
                )
                .all()
            )

        # Path 2: direct via PickingLine.product_id (no SPO required). Shipment_number
        # comes from SPOAllocation when picking_line links to one; otherwise NULL.
        direct_rows: list = []
        if product_uuids:
            direct_q = (
                self.db.query(
                    PickingHeader.picking_number,
                    PickingHeader.picking_date,
                    PickingHeader.picking_status,
                    func.max(shipment_number_expr).label("shipment_number"),
                )
                .join(PickingLine, PickingLine.picking_header_id == PickingHeader.id)
                .outerjoin(
                    SPOAllocation, SPOAllocation.id == PickingLine.spo_allocation_id
                )
                .outerjoin(
                    InboundShipment,
                    InboundShipment.id == SPOAllocation.inbound_shipment_id,
                )
                .filter(
                    PickingHeader.picking_type == "goods_received",
                    PickingLine.product_id.in_(product_uuids),
                )
                .group_by(
                    PickingHeader.picking_number,
                    PickingHeader.picking_date,
                    PickingHeader.picking_status,
                )
            )
            direct_rows = direct_q.all()

        # Merge + dedupe by picking_number. Sort by picking_date desc, NULL last.
        seen: dict[str, Any] = {}
        for r in list(spo_rows) + list(direct_rows):
            key = r.picking_number
            if key in seen:
                continue
            seen[key] = r
        merged = sorted(
            seen.values(),
            key=lambda r: (r.picking_date is None, r.picking_date),
            reverse=False,
        )
        merged.sort(key=lambda r: r.picking_date or date.min, reverse=True)
        merged = merged[:limit]

        data = [
            {
                "grn_number": r.picking_number,
                "grn_date": r.picking_date,
                "grn_status": r.picking_status,
                "shipment_number": r.shipment_number,
            }
            for r in merged
        ]
        return {"data": data, "empty": not data}
