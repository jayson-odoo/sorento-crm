"""User-facing incoming-stock schemas.

These schemas enforce the business rules from next_agents/incoming_stock_enquiries.txt:
- NEVER expose internal IDs, UUIDs, foreign keys.
- NEVER expose `quantity_received`, `quantity_rejected`, receipt_status, or any received/rejected data.
- NEVER expose `spo_number`, `spo_allocation_id`, `picking_line_id`, or other internal refs.
- ONLY show human-readable identifiers: product_code, shipment_number, container_number, warehouse_code,
  ETA, filenames.
- ONLY show `remaining_incoming_quantity` (= quantity_shipped - quantity_received, clamped to >= 0).
- Allocation state is surfaced as `unallocated_quantity` (the GAP against quantity_shipped),
  never as the shipped base itself — the base plus the already-public remaining would let a
  consumer derive `quantity_received`.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class AttachmentInfo(BaseModel):
    """Packing list / shipment document attachment (user-facing fields only)."""

    filename: str
    file_path: Optional[str] = None
    mime_type: Optional[str] = None


class WarehouseAllocation(BaseModel):
    """Allocation amount for a single warehouse (for one shipment + product pair).

    `allocated_quantity` mirrors how much of the incoming stock is destined for this warehouse.
    No receipt / received / rejected data is ever surfaced.
    """

    warehouse_code: str
    warehouse_name: Optional[str] = None
    allocated_quantity: int


class IncomingShipmentForProduct(BaseModel):
    """One open inbound shipment carrying this product, with only user-facing data."""

    shipment_number: str
    shipping_container_number: Optional[str] = None
    estimated_arrival_date: Optional[date] = None
    batch_number: Optional[str] = None
    remaining_incoming_quantity: int
    unallocated_quantity: Optional[int] = None
    warehouse_allocations: List[WarehouseAllocation] = []
    attachment: Optional[AttachmentInfo] = None


class IncomingStockForProductResponse(BaseModel):
    """Aggregated answer for 'any incoming for product X?' queries."""

    product_code: str
    product_name: Optional[str] = None
    is_discontinued: bool = False
    nearest_estimated_arrival_date: Optional[date] = None
    shipments: List[IncomingShipmentForProduct] = []


class IncomingShipmentSummary(BaseModel):
    """Shipment-level summary for 'any incoming shipments?' queries."""

    shipment_number: str
    shipping_container_number: Optional[str] = None
    estimated_arrival_date: Optional[date] = None
    total_remaining_incoming_quantity: int
    distinct_products_incoming: int
    attachment: Optional[AttachmentInfo] = None


class IncomingProductInShipment(BaseModel):
    """Product still incoming on a given shipment."""

    product_code: str
    product_name: Optional[str] = None
    is_discontinued: bool = False
    batch_number: Optional[str] = None
    remaining_incoming_quantity: int
    unallocated_quantity: Optional[int] = None
    warehouse_allocations: List[WarehouseAllocation] = []


class IncomingShipmentDetail(BaseModel):
    """'What products are in this shipment?' response."""

    shipment_number: str
    shipping_container_number: Optional[str] = None
    estimated_arrival_date: Optional[date] = None
    attachment: Optional[AttachmentInfo] = None
    products: List[IncomingProductInShipment] = []


class IncomingStockGRNRecord(BaseModel):
    """Minimal GRN record, only when the user explicitly asks. No quantities.

    Per the incoming-stock business rules we only surface GRN identifiers and status,
    never received/rejected counts.
    """

    grn_number: str
    grn_date: Optional[date] = None
    grn_status: Optional[str] = None
    shipment_number: Optional[str] = None
