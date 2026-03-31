"""Procurement service for business logic."""
import logging
import re
import secrets
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from sqlalchemy import inspect
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta, timezone
from app.models.procurement import (
    Supplier, ProductSupplier, InboundShipment, InboundShipmentLine, SPOAllocation,
    PickingHeader, PickingLine, StockInquiry, PurchaseRequestHeader, PurchaseRequestLine,
    ApprovalToken,
    ViewToken,
)
from app.models.product import Product
from app.models.resources import Attachment
from app.models.user import User
from app.schemas.procurement import (
    SupplierCreate, SupplierUpdate, ProductSupplierCreate, ProductSupplierUpdate,
    InboundShipmentCreate, InboundShipmentUpdate,
    SPOAllocationCreate, SPOAllocationUpdate, PickingHeaderCreate, PickingHeaderUpdate,
    StockInquiryCreate, StockInquiryUpdate,
    PurchaseRequestHeaderCreate, PurchaseRequestHeaderUpdate, PurchaseRequestUpdateAndReply,
)
from app.services.error_handler import handle_not_found, handle_conflict
from app.config import settings

logger = logging.getLogger(__name__)


def _normalize_spo_number(spo_number: Optional[str]) -> str:
    """Normalize SPO number for matching (e.g. SPO-2026/01-0178 vs SPO-2026.01-0178)."""
    if not spo_number or not str(spo_number).strip():
        return ""
    return str(spo_number).strip().replace("/", ".").replace("\\", ".")


def _spo_match_key(spo_number: Optional[str]) -> str:
    """Alphanumeric-only key so SPO-202602-0102 matches SPO-2026/02-0102 and SPO-2026.02-0102."""
    if not spo_number or not str(spo_number).strip():
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(spo_number).strip()).upper()


def compute_inbound_shipment_line_status(
    quantity_shipped: int,
    allocated_quantity: int,
    quantity_received: int,
) -> str:
    """Compute line-level status for packing list lines (stored in DB for n8n/API).
    Same logic as frontend: in_transit, allocated, partially_allocated, received, partially_received.
    """
    qty = quantity_shipped or 0
    alloc = allocated_quantity or 0
    recv = quantity_received or 0
    if alloc == 0:
        return "in_transit"
    if recv >= alloc:
        return "received"
    if qty > alloc:
        return "partially_allocated"
    if alloc >= qty and recv == 0:
        return "allocated"
    if alloc >= qty and recv > 0:
        return "partially_received"
    return "in_transit"


class SupplierService:
    """Service for supplier operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_suppliers(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "asc",
        advanced_filter_clause=None,
    ):
        """List suppliers."""
        q = self.db.query(Supplier)

        if query:
            q = q.filter(
                or_(
                    Supplier.supplier_code.ilike(f"%{query}%"),
                    Supplier.supplier_name.ilike(f"%{query}%"),
                )
            )

        if advanced_filter_clause is not None:
            q = q.filter(advanced_filter_clause)
        
        sort_map = {
            "created_at": Supplier.created_at,
            "supplier_code": Supplier.supplier_code,
            "supplier_name": Supplier.supplier_name,
        }
        sort_column = sort_map.get(sort_field, Supplier.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        suppliers = q.offset(offset).limit(limit).all()
        
        return {
            "data": suppliers,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_supplier(self, supplier_id: str):
        """Get a supplier by ID."""
        supplier = self.db.query(Supplier).filter(Supplier.id == supplier_id).first()
        if not supplier:
            raise handle_not_found("Supplier", supplier_id)
        return supplier
    
    def create_supplier(self, supplier_data: SupplierCreate):
        """Create a new supplier."""
        existing = self.db.query(Supplier).filter(
            Supplier.supplier_code == supplier_data.supplier_code
        ).first()
        if existing:
            raise handle_conflict("Supplier code already exists.")
        
        supplier = Supplier(**supplier_data.model_dump())
        self.db.add(supplier)
        self.db.commit()
        self.db.refresh(supplier)
        return supplier
    
    def update_supplier(self, supplier_id: str, supplier_data: SupplierUpdate):
        """Update a supplier."""
        supplier = self.get_supplier(supplier_id)
        
        update_data = supplier_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(supplier, key, value)
        
        self.db.commit()
        self.db.refresh(supplier)
        return supplier


class InboundShipmentService:
    """Service for inbound shipment (packing list) operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_shipments(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        supplier_id: Optional[str] = None,
        shipment_status: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "asc"
    ):
        """List inbound shipments."""
        q = self.db.query(InboundShipment)
        
        filters = []
        
        if supplier_id and supplier_id != "all":
            filters.append(InboundShipment.supplier_id == supplier_id)
        
        if shipment_status and shipment_status != "all":
            filters.append(InboundShipment.shipment_status == shipment_status)
        
        if query:
            filters.append(
                or_(
                    InboundShipment.shipment_number.ilike(f"%{query}%"),
                    InboundShipment.bill_of_lading_number.ilike(f"%{query}%"),
                    InboundShipment.shipping_container_number.ilike(f"%{query}%"),
                    InboundShipment.invoice_number.ilike(f"%{query}%"),
                    InboundShipment.supplier.has(Supplier.supplier_name.ilike(f"%{query}%")),
                    InboundShipment.supplier.has(Supplier.supplier_code.ilike(f"%{query}%"))
                )
            )
        
        if filters:
            q = q.filter(and_(*filters))
        
        sort_map = {
            "shipment_number": InboundShipment.shipment_number,
            "shipment_date": InboundShipment.shipment_date,
            "created_at": InboundShipment.created_at,
            "updated_at": InboundShipment.updated_at,
        }
        sort_column = sort_map.get(sort_field, InboundShipment.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        from sqlalchemy.orm import joinedload
        shipments = (
            q.options(joinedload(InboundShipment.shipment_lines))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "data": shipments,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_shipment(self, shipment_id: str):
        """Get a shipment by ID with lines and product details."""
        from sqlalchemy.orm import joinedload
        shipment = self.db.query(InboundShipment).options(
            joinedload(InboundShipment.attachment).joinedload(Attachment.attachment_type),
            joinedload(InboundShipment.shipment_lines).joinedload(InboundShipmentLine.product),
        ).filter(InboundShipment.id == shipment_id).first()
        if not shipment:
            raise handle_not_found("Inbound Shipment", shipment_id)
        return shipment

    def get_received_quantities_by_product(self, shipment_id: str) -> dict[str, int]:
        """Return received qty per product for a shipment, ignoring warehouse boundaries."""
        received_totals: dict[str, int] = {}

        linked_rows = (
            self.db.query(
                SPOAllocation.product_id,
                func.coalesce(func.sum(PickingLine.quantity_expected), 0).label("total"),
            )
            .join(PickingLine, PickingLine.spo_allocation_id == SPOAllocation.id)
            .join(PickingHeader, PickingLine.picking_header_id == PickingHeader.id)
            .filter(
                SPOAllocation.inbound_shipment_id == shipment_id,
                PickingHeader.picking_type == "goods_received",
                PickingHeader.picking_status == "approved",
            )
            .group_by(SPOAllocation.product_id)
            .all()
        )
        for product_id, total in linked_rows:
            received_totals[str(product_id)] = int(total or 0)

        allocation_rows = (
            self.db.query(SPOAllocation.product_id, SPOAllocation.spo_number)
            .filter(
                SPOAllocation.inbound_shipment_id == shipment_id,
                SPOAllocation.spo_number.isnot(None),
            )
            .all()
        )
        spo_numbers_by_product: dict[str, set[str]] = {}
        for product_id, spo_number in allocation_rows:
            normalized = _normalize_spo_number(spo_number)
            if not normalized:
                continue
            spo_numbers_by_product.setdefault(str(product_id), set()).add(normalized)

        if not spo_numbers_by_product:
            return received_totals

        product_ids = list(spo_numbers_by_product.keys())
        all_spo_numbers = {
            spo_number
            for spo_numbers in spo_numbers_by_product.values()
            for spo_number in spo_numbers
        }
        norm_expr = func.replace(
            func.replace(func.trim(PickingHeader.spo_number), "/", "."),
            "\\",
            ".",
        )
        orphan_rows = (
            self.db.query(
                PickingLine.product_id,
                norm_expr.label("normalized_spo_number"),
                func.coalesce(func.sum(PickingLine.quantity_expected), 0).label("total"),
            )
            .join(PickingHeader, PickingLine.picking_header_id == PickingHeader.id)
            .filter(
                PickingLine.spo_allocation_id.is_(None),
                PickingLine.product_id.in_(product_ids),
                PickingHeader.picking_type == "goods_received",
                PickingHeader.picking_status == "approved",
                PickingHeader.spo_number.isnot(None),
                norm_expr.in_(all_spo_numbers),
            )
            .group_by(PickingLine.product_id, norm_expr)
            .all()
        )
        for product_id, normalized_spo_number, total in orphan_rows:
            product_key = str(product_id)
            if normalized_spo_number not in spo_numbers_by_product.get(product_key, set()):
                continue
            received_totals[product_key] = received_totals.get(product_key, 0) + int(total or 0)

        return received_totals

    def refresh_shipment_line_statuses(self, shipment_id: str) -> None:
        """Recompute and persist line_status for all lines of this shipment (for n8n/API)."""
        lines = (
            self.db.query(InboundShipmentLine)
            .filter(InboundShipmentLine.shipment_id == shipment_id)
            .all()
        )
        if not lines:
            return
        totals_alloc = (
            self.db.query(SPOAllocation.product_id, func.sum(SPOAllocation.allocated_quantity).label("total"))
            .filter(SPOAllocation.inbound_shipment_id == shipment_id)
            .group_by(SPOAllocation.product_id)
            .all()
        )
        spo_by_product = {str(p): int(t) for p, t in totals_alloc}
        received_by_product = self.get_received_quantities_by_product(shipment_id)
        for line in lines:
            alloc = spo_by_product.get(str(line.product_id), 0)
            recv = received_by_product.get(str(line.product_id), 0)
            line.spo_allocated_quantity = alloc
            line.quantity_received = recv
            line.line_status = compute_inbound_shipment_line_status(
                line.quantity_shipped or 0, alloc, recv
            )
        self.db.commit()
    
    def create_shipment(self, shipment_data: InboundShipmentCreate, created_by: str | None = None):
        """Create a new inbound shipment with lines."""
        existing = self.db.query(InboundShipment).filter(
            InboundShipment.shipment_number == shipment_data.shipment_number
        ).first()
        if existing:
            raise handle_conflict("Shipment number already exists.")
        
        # Create shipment and lines in transaction
        shipment_dict = shipment_data.model_dump(exclude={"shipment_lines"})
        shipment_dict["created_by"] = created_by
        shipment = InboundShipment(**shipment_dict)
        self.db.add(shipment)
        self.db.flush()  # Get the ID
        
        # Create lines if provided (one row per product per shipment; merge duplicates by product_id)
        if shipment_data.shipment_lines:
            merged: dict[str, dict] = {}  # product_id -> merged line dict
            for line_data in shipment_data.shipment_lines:
                d = line_data.model_dump()
                pid = d["product_id"]
                if pid in merged:
                    merged[pid]["quantity_shipped"] += d.get("quantity_shipped", 0)
                    merged[pid]["cartons_count"] += d.get("cartons_count", 1)
                else:
                    merged[pid] = dict(d)
            for d in merged.values():
                line = InboundShipmentLine(**d, shipment_id=shipment.id)
                self.db.add(line)
        
        self.db.commit()
        self.db.refresh(shipment)
        self.refresh_shipment_line_statuses(shipment.id)
        return shipment
    
    def update_shipment(self, shipment_id: str, shipment_data: InboundShipmentUpdate, updated_by: str):
        """Update an inbound shipment. If shipment_lines provided, replace existing lines."""
        shipment = self.get_shipment(shipment_id)
        
        update_data = shipment_data.model_dump(exclude_unset=True, exclude={"shipment_lines"})
        for key, value in update_data.items():
            setattr(shipment, key, value)
        
        if "shipment_lines" in shipment_data.model_dump(exclude_unset=True):
            # Replace lines: delete existing, add new (grouped by product)
            for line in shipment.shipment_lines[:]:
                self.db.delete(line)
            self.db.flush()
            lines_data = shipment_data.shipment_lines or []
            if lines_data:
                merged: dict[str, dict] = {}
                for line_data in lines_data:
                    d = line_data.model_dump()
                    pid = d["product_id"]
                    if pid in merged:
                        merged[pid]["quantity_shipped"] += d.get("quantity_shipped", 0)
                        merged[pid]["cartons_count"] += d.get("cartons_count", 1)
                    else:
                        merged[pid] = dict(d)
                for d in merged.values():
                    line = InboundShipmentLine(**d, shipment_id=shipment.id)
                    self.db.add(line)
        
        self.db.commit()
        self.db.refresh(shipment)
        self.refresh_shipment_line_statuses(shipment_id)
        return shipment

    def delete_shipment(self, shipment_id: str) -> None:
        """Delete an inbound shipment. Lines and SPO allocations cascade via DB."""
        shipment = self.get_shipment(shipment_id)
        self.db.delete(shipment)
        self.db.commit()

    def bulk_delete_shipments(self, shipment_ids: list[str]) -> dict:
        """Delete multiple inbound shipments by ID. Returns message and deleted_count."""
        if not shipment_ids:
            return {"message": "No packing lists to delete", "deleted_count": 0}
        shipments = self.db.query(InboundShipment).filter(InboundShipment.id.in_(shipment_ids)).all()
        for shipment in shipments:
            self.db.delete(shipment)
        self.db.commit()
        deleted = len(shipments)
        return {"message": f"{deleted} packing list(s) deleted", "deleted_count": deleted}


class SPOAllocationService:
    """Service for SPO allocation operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_allocations(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        shipment_id: Optional[str] = None,
        warehouse_id: Optional[str] = None,
        receipt_status: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "asc"
    ):
        """List SPO allocations. quantity_received is computed on load from approved GRN lines."""
        from sqlalchemy.orm import joinedload
        from app.schemas.procurement import SPOAllocationResponse
        q = self.db.query(SPOAllocation).options(
            joinedload(SPOAllocation.product),
            joinedload(SPOAllocation.warehouse),
            joinedload(SPOAllocation.inbound_shipment),
        )
        
        filters = []
        
        if shipment_id and shipment_id != "all":
            filters.append(SPOAllocation.inbound_shipment_id == shipment_id)
        
        if warehouse_id and warehouse_id != "all":
            filters.append(SPOAllocation.warehouse_id == warehouse_id)
        
        if receipt_status and receipt_status != "all":
            filters.append(SPOAllocation.receipt_status == receipt_status)
        
        if query:
            filters.append(
                or_(
                    SPOAllocation.spo_number.ilike(f"%{query}%"),
                    SPOAllocation.inbound_shipment.has(InboundShipment.shipment_number.ilike(f"%{query}%")),
                    SPOAllocation.product.has(Product.product_code.ilike(f"%{query}%")),
                    SPOAllocation.product.has(Product.product_name.ilike(f"%{query}%"))
                )
            )
        
        if filters:
            q = q.filter(and_(*filters))
        
        sort_map = {
            "spo_number": SPOAllocation.spo_number,
            "created_at": SPOAllocation.created_at,
            "updated_at": SPOAllocation.updated_at,
        }
        sort_column = sort_map.get(sort_field, SPOAllocation.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        allocations = q.offset(offset).limit(limit).all()
        data = []
        try:
            alloc_ids = [str(a.id) for a in allocations]
            received_map = self.get_computed_received_map(alloc_ids)
            for a in allocations:
                resp = SPOAllocationResponse.model_validate(a)
                rec = received_map.get(str(a.id), 0)
                data.append(resp.model_copy(update={
                    "quantity_received": rec,
                    "receipt_status": "received" if rec >= (a.allocated_quantity or 0) else "pending",
                }))
        except Exception:
            data = [SPOAllocationResponse.model_validate(a) for a in allocations]
        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }

    def list_allocations_grouped_by_shipment(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        product_code: Optional[str] = None,
        warehouse_id: Optional[str] = None,
        receipt_status: Optional[str] = None,
        sort_field: str = "shipment_number",
        sort_dir: str = "asc",
    ):
        """List inbound shipments that have SPO allocations, each with its allocations (for grouped list view)."""
        from sqlalchemy.orm import joinedload
        from app.schemas.procurement import (
            InboundShipmentSimple,
            InboundShipmentLineResponse,
            SPOAllocationResponse,
            ShipmentWithAllocationsGroup,
        )

        # Subquery / join: shipments that have at least one allocation matching filters
        q_shipments = (
            self.db.query(InboundShipment)
            .join(SPOAllocation, SPOAllocation.inbound_shipment_id == InboundShipment.id)
            .distinct()
        )

        shipment_filters = []
        if warehouse_id and warehouse_id != "all":
            shipment_filters.append(SPOAllocation.warehouse_id == warehouse_id)
        if receipt_status and receipt_status != "all":
            shipment_filters.append(SPOAllocation.receipt_status == receipt_status)
        if product_code and product_code.strip():
            shipment_filters.append(
                SPOAllocation.product.has(Product.product_code.ilike(f"%{product_code.strip()}%"))
            )
        if query:
            q = query.strip()
            shipment_filters.append(
                or_(
                    SPOAllocation.spo_number.ilike(f"%{q}%"),
                    InboundShipment.shipment_number.ilike(f"%{q}%"),
                    InboundShipment.shipping_container_number.ilike(f"%{q}%"),
                    SPOAllocation.product.has(Product.product_code.ilike(f"%{q}%")),
                    SPOAllocation.product.has(Product.product_name.ilike(f"%{q}%")),
                )
            )
        if shipment_filters:
            q_shipments = q_shipments.filter(and_(*shipment_filters))

        allocation_filters = []
        if warehouse_id and warehouse_id != "all":
            allocation_filters.append(SPOAllocation.warehouse_id == warehouse_id)
        if receipt_status and receipt_status != "all":
            allocation_filters.append(SPOAllocation.receipt_status == receipt_status)
        if product_code and product_code.strip():
            allocation_filters.append(
                SPOAllocation.product.has(Product.product_code.ilike(f"%{product_code.strip()}%"))
            )

        sort_map = {
            "shipment_number": InboundShipment.shipment_number,
            "created_at": InboundShipment.created_at,
        }
        sort_column = sort_map.get(sort_field, InboundShipment.shipment_number)
        if sort_dir == "desc":
            q_shipments = q_shipments.order_by(sort_column.desc())
        else:
            q_shipments = q_shipments.order_by(sort_column.asc())

        total = q_shipments.count()
        offset = (page - 1) * limit
        shipments_page = q_shipments.offset(offset).limit(limit).all()
        shipment_ids = [s.id for s in shipments_page]

        if not shipment_ids:
            return {
                "data": [],
                "pagination": {"total": total, "page": page, "limit": limit},
                "empty": True,
            }

        # Load shipment lines (packing list quantities) in a separate query so they are always
        # populated regardless of the main query join/distinct
        lines_query = (
            self.db.query(InboundShipmentLine)
            .filter(InboundShipmentLine.shipment_id.in_(shipment_ids))
            .options(joinedload(InboundShipmentLine.product))
        )
        all_lines = lines_query.all()
        lines_by_shipment: dict[str, list] = {}
        for line in all_lines:
            lines_by_shipment.setdefault(line.shipment_id, []).append(line)

        # Load all allocations for these shipments (same filters) with relations
        q_alloc = (
            self.db.query(SPOAllocation)
            .filter(SPOAllocation.inbound_shipment_id.in_(shipment_ids))
            .options(
                joinedload(SPOAllocation.product),
                joinedload(SPOAllocation.warehouse),
                joinedload(SPOAllocation.inbound_shipment),
            )
        )
        if allocation_filters:
            q_alloc = q_alloc.filter(and_(*allocation_filters))
        q_alloc = q_alloc.order_by(SPOAllocation.spo_number, SPOAllocation.id)
        allocations = q_alloc.all()

        # Group by inbound_shipment_id preserving shipment order
        by_shipment: dict[str, list] = {}
        for a in allocations:
            by_shipment.setdefault(a.inbound_shipment_id, []).append(a)

        try:
            all_alloc_ids = [str(a.id) for a in allocations]
            received_map = self.get_computed_received_map(all_alloc_ids)
        except Exception:
            received_map = {}

        groups = []
        for ship in shipments_page:
            allocs = by_shipment.get(ship.id, [])
            raw_lines = lines_by_shipment.get(ship.id, [])
            shipment_lines = [
                InboundShipmentLineResponse.model_validate(line) for line in raw_lines
            ]
            alloc_responses = []
            for a in allocs:
                resp = SPOAllocationResponse.model_validate(a)
                try:
                    rec = received_map.get(str(a.id), 0)
                    alloc_responses.append(resp.model_copy(update={
                        "quantity_received": rec,
                        "receipt_status": "received" if rec >= (a.allocated_quantity or 0) else "pending",
                    }))
                except Exception:
                    alloc_responses.append(resp)
            groups.append(
                ShipmentWithAllocationsGroup(
                    inbound_shipment=InboundShipmentSimple.model_validate(ship),
                    spo_allocations=alloc_responses,
                    shipment_lines=shipment_lines if shipment_lines else None,
                )
            )

        return {
            "data": groups,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }

    def list_allocations_grouped_by_spo_number(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        product_code: Optional[str] = None,
        warehouse_id: Optional[str] = None,
        receipt_status: Optional[str] = None,
        sort_field: str = "spo_number",
        sort_dir: str = "asc",
    ):
        """List SPO allocations grouped by spo_number (for list view by SPO). Paginates at DB level."""
        from sqlalchemy.orm import joinedload
        from sqlalchemy import func
        from app.schemas.procurement import (
            SPOAllocationResponse,
            SPOAllocationWithShippedResponse,
            SPOWithAllocationsGroup,
        )

        # Base filter query (no eager load) – reuse for count and for page of spo_numbers
        q_base = self.db.query(SPOAllocation).filter(SPOAllocation.spo_number.isnot(None))
        filters = []
        if warehouse_id and warehouse_id != "all":
            filters.append(SPOAllocation.warehouse_id == warehouse_id)
        if receipt_status and receipt_status != "all":
            filters.append(SPOAllocation.receipt_status == receipt_status)
        if product_code and product_code.strip():
            filters.append(
                SPOAllocation.product.has(Product.product_code.ilike(f"%{product_code.strip()}%"))
            )
        if query:
            q_str = query.strip()
            q_base = q_base.outerjoin(InboundShipment, SPOAllocation.inbound_shipment_id == InboundShipment.id)
            filters.append(
                or_(
                    SPOAllocation.spo_number.ilike(f"%{q_str}%"),
                    InboundShipment.shipment_number.ilike(f"%{q_str}%"),
                    InboundShipment.shipping_container_number.ilike(f"%{q_str}%"),
                    SPOAllocation.product.has(Product.product_code.ilike(f"%{q_str}%")),
                    SPOAllocation.product.has(Product.product_name.ilike(f"%{q_str}%")),
                )
            )
        if filters:
            q_base = q_base.filter(and_(*filters))

        sort_map = {
            "spo_number": SPOAllocation.spo_number,
            "created_at": SPOAllocation.created_at,
        }
        sort_col = sort_map.get(sort_field, SPOAllocation.spo_number)
        order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()

        # Total count of distinct SPO numbers
        total = q_base.with_entities(func.count(func.distinct(SPOAllocation.spo_number))).scalar() or 0
        offset = (page - 1) * limit
        if total == 0:
            return {
                "data": [],
                "pagination": {"total": 0, "page": page, "limit": limit},
                "empty": True,
            }

        # Page of distinct spo_numbers at DB level (same filters and order)
        q_spo_page = (
            q_base.with_entities(SPOAllocation.spo_number)
            .distinct()
            .order_by(order)
            .offset(offset)
            .limit(limit)
        )
        spo_page = [r[0] for r in q_spo_page.all() if r[0]]

        if not spo_page:
            return {
                "data": [],
                "pagination": {"total": total, "page": page, "limit": limit},
                "empty": True,
            }

        # Load only allocations for this page of spo_numbers, with relations
        q_alloc = (
            self.db.query(SPOAllocation)
            .filter(SPOAllocation.spo_number.in_(spo_page))
            .options(
                joinedload(SPOAllocation.product),
                joinedload(SPOAllocation.warehouse),
                joinedload(SPOAllocation.inbound_shipment),
            )
            .order_by(SPOAllocation.spo_number, SPOAllocation.id)
        )
        if query:
            q_alloc = q_alloc.outerjoin(InboundShipment, SPOAllocation.inbound_shipment_id == InboundShipment.id)
        if filters:
            q_alloc = q_alloc.filter(and_(*filters))
        all_allocations = q_alloc.all()

        by_spo: dict[str, list] = {}
        for a in all_allocations:
            if a.spo_number and a.spo_number in spo_page:
                by_spo.setdefault(a.spo_number, []).append(a)

        shipment_ids = {
            a.inbound_shipment_id for allocs in by_spo.values() for a in allocs
            if a.inbound_shipment_id is not None
        }
        shipped_by_ship_product: dict[tuple[str, str], int] = {}
        if shipment_ids:
            lines_query = (
                self.db.query(InboundShipmentLine)
                .filter(InboundShipmentLine.shipment_id.in_(shipment_ids))
            )
            for line in lines_query.all():
                key = (line.shipment_id, line.product_id)
                shipped_by_ship_product[key] = shipped_by_ship_product.get(key, 0) + (line.quantity_shipped or 0)

        page_alloc_ids = [str(a.id) for spo_num in spo_page for a in by_spo.get(spo_num, [])]
        try:
            received_map = self.get_computed_received_map(page_alloc_ids)
        except Exception:
            received_map = {}

        groups = []
        for spo_num in spo_page:
            allocs = by_spo.get(spo_num, [])
            alloc_responses = []
            for a in allocs:
                try:
                    data = SPOAllocationResponse.model_validate(a).model_dump()
                    rec = received_map.get(str(a.id), 0)
                    data["quantity_received"] = rec
                    data["receipt_status"] = "received" if rec >= (a.allocated_quantity or 0) else "pending"
                    qty_shipped = shipped_by_ship_product.get((a.inbound_shipment_id, a.product_id))
                    data["quantity_shipped"] = qty_shipped
                    alloc_responses.append(SPOAllocationWithShippedResponse(**data))
                except Exception:
                    data = SPOAllocationResponse.model_validate(a).model_dump()
                    data["quantity_shipped"] = shipped_by_ship_product.get((a.inbound_shipment_id, a.product_id))
                    alloc_responses.append(SPOAllocationWithShippedResponse(**data))
            groups.append(SPOWithAllocationsGroup(spo_number=spo_num, spo_allocations=alloc_responses))

        return {
            "data": groups,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }

    def get_allocation(self, allocation_id: str):
        """Get an SPO allocation by ID."""
        from sqlalchemy.orm import joinedload
        allocation = self.db.query(SPOAllocation).options(
            joinedload(SPOAllocation.product),
            joinedload(SPOAllocation.warehouse),
            joinedload(SPOAllocation.inbound_shipment),
        ).filter(SPOAllocation.id == allocation_id).first()
        if not allocation:
            raise handle_not_found("SPO Allocation", allocation_id)
        return allocation
    
    def create_allocation(self, allocation_data: SPOAllocationCreate, created_by: str):
        """Create a new SPO allocation."""
        # Check unique constraint: (spo_number, product_id, warehouse_id)
        if allocation_data.spo_number and allocation_data.product_id and allocation_data.warehouse_id:
            existing = self.db.query(SPOAllocation).filter(
                SPOAllocation.spo_number == allocation_data.spo_number,
                SPOAllocation.product_id == allocation_data.product_id,
                SPOAllocation.warehouse_id == allocation_data.warehouse_id,
            ).first()
            if existing:
                raise handle_conflict("SPO number, product and warehouse combination already exists.")
        
        allocation_dict = allocation_data.model_dump()
        allocation_dict["created_by"] = created_by
        allocation = SPOAllocation(**allocation_dict)
        self.db.add(allocation)
        self.db.commit()
        self.db.refresh(allocation)
        InboundShipmentService(self.db).refresh_shipment_line_statuses(allocation.inbound_shipment_id)
        return allocation
    
    def update_allocation(self, allocation_id: str, allocation_data: SPOAllocationUpdate):
        """Update an SPO allocation."""
        allocation = self.get_allocation(allocation_id)
        previous_shipment_id = allocation.inbound_shipment_id
        update_data = allocation_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(allocation, key, value)
        
        self.db.commit()
        self.db.refresh(allocation)
        inbound_svc = InboundShipmentService(self.db)
        inbound_svc.refresh_shipment_line_statuses(allocation.inbound_shipment_id)
        if previous_shipment_id and allocation.inbound_shipment_id != previous_shipment_id:
            inbound_svc.refresh_shipment_line_statuses(previous_shipment_id)
        return allocation

    def delete_allocation(self, allocation_id: str):
        """Delete an SPO allocation by ID."""
        allocation = self.get_allocation(allocation_id)
        shipment_id = allocation.inbound_shipment_id
        self.db.delete(allocation)
        self.db.commit()
        InboundShipmentService(self.db).refresh_shipment_line_statuses(shipment_id)

    def bulk_delete_allocations(self, allocation_ids: list[str]):
        """Delete multiple SPO allocations by ID. Returns count of deleted."""
        if not allocation_ids:
            return {"message": "No allocations to delete", "deleted_count": 0}
        shipment_ids = {
            shipment_id
            for (shipment_id,) in self.db.query(SPOAllocation.inbound_shipment_id)
            .filter(SPOAllocation.id.in_(allocation_ids))
            .distinct()
            .all()
            if shipment_id is not None
        }
        deleted = self.db.query(SPOAllocation).filter(SPOAllocation.id.in_(allocation_ids)).delete(synchronize_session=False)
        self.db.commit()
        inbound_svc = InboundShipmentService(self.db)
        for shipment_id in shipment_ids:
            inbound_svc.refresh_shipment_line_statuses(shipment_id)
        return {"message": f"Deleted {deleted} SPO allocation(s)", "deleted_count": deleted}

    def compute_received_for_allocation(self, allocation_id: str) -> int:
        """Computed on read: sum quantity_expected from picking lines where spo_allocation_id = allocation_id
        and the picking line's header (GRN) is approved. Not stored in DB."""
        from sqlalchemy import func
        total = (
            self.db.query(func.coalesce(func.sum(PickingLine.quantity_expected), 0))
            .join(PickingHeader, PickingLine.picking_header_id == PickingHeader.id)
            .filter(
                PickingLine.spo_allocation_id == allocation_id,
                PickingHeader.picking_type == "goods_received",
                PickingHeader.picking_status == "approved",
            )
            .scalar()
        )
        return int(total)

    def get_computed_received_map(self, allocation_ids: list[str]) -> dict[str, int]:
        """Bulk: for each allocation id, return computed quantity_received (sum quantity_expected from approved GRN lines)."""
        if not allocation_ids:
            return {}
        from sqlalchemy import func
        rows = (
            self.db.query(PickingLine.spo_allocation_id, func.coalesce(func.sum(PickingLine.quantity_expected), 0))
            .join(PickingHeader, PickingLine.picking_header_id == PickingHeader.id)
            .filter(
                PickingLine.spo_allocation_id.in_(allocation_ids),
                PickingHeader.picking_type == "goods_received",
                PickingHeader.picking_status == "approved",
            )
            .group_by(PickingLine.spo_allocation_id)
            .all()
        )
        received_map = {str(r[0]): int(r[1]) for r in rows}
        return {aid: received_map.get(aid, 0) for aid in allocation_ids}

    def get_linked_grns_for_spo(self, spo_number: Optional[str]):
        """Return list of GRN headers (id, picking_number, picking_status, picking_date) for this SPO number.
        Matches by alphanumeric SPO key so variant formats (e.g. SPO-202602-0102 vs SPO-2026/02-0102) align."""
        if not spo_number or not spo_number.strip():
            return []
        target_key = _spo_match_key(spo_number)
        if not target_key:
            return []
        rows = (
            self.db.query(
                PickingHeader.id,
                PickingHeader.picking_number,
                PickingHeader.picking_status,
                PickingHeader.picking_date,
                PickingHeader.spo_number,
            )
            .filter(
                PickingHeader.picking_type == "goods_received",
                PickingHeader.spo_number.isnot(None),
            )
            .order_by(PickingHeader.picking_date.desc().nulls_last(), PickingHeader.picking_number)
            .all()
        )
        return [
            {"id": str(r[0]), "picking_number": r[1], "picking_status": r[2], "picking_date": r[3]}
            for r in rows
            if _spo_match_key(r[4]) == target_key
        ]


class PickingHeaderService:
    """Service for picking header (GRN) operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_grns(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        picking_status: Optional[str] = None,
        inspection_status: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "asc"
    ):
        """List GRNs (picking headers with type 'goods_received'). Does not load picking_lines; adds lines_count only."""
        from sqlalchemy.orm import noload
        q = self.db.query(PickingHeader).options(
            noload(PickingHeader.picking_lines)
        ).filter(PickingHeader.picking_type == "goods_received")
        
        filters = []
        
        if picking_status and picking_status != "all":
            filters.append(PickingHeader.picking_status == picking_status)
        
        if inspection_status and inspection_status != "all":
            filters.append(PickingHeader.inspection_status == inspection_status)
        
        if query:
            filters.append(PickingHeader.picking_number.ilike(f"%{query}%"))
        
        if filters:
            q = q.filter(and_(*filters))
        
        sort_map = {
            "picking_number": PickingHeader.picking_number,
            "picking_date": PickingHeader.picking_date,
            "created_at": PickingHeader.created_at,
            "updated_at": PickingHeader.updated_at,
        }
        use_lines_count_sort = sort_field == "lines_count"
        if use_lines_count_sort:
            line_count_subq = (
                self.db.query(
                    PickingLine.picking_header_id,
                    func.count(PickingLine.id).label("cnt"),
                )
                .group_by(PickingLine.picking_header_id)
            ).subquery()
            q = q.outerjoin(line_count_subq, PickingHeader.id == line_count_subq.c.picking_header_id)
            sort_column = line_count_subq.c.cnt
            if sort_dir == "desc":
                q = q.order_by(sort_column.desc().nulls_last())
            else:
                q = q.order_by(sort_column.asc().nulls_last())
            total = q.count()
            offset = (page - 1) * limit
            q = q.add_columns(line_count_subq.c.cnt)
            rows = q.offset(offset).limit(limit).all()
            grns = []
            for row in rows:
                header, cnt = row[0], row[1]
                setattr(header, "lines_count", int(cnt) if cnt is not None else 0)
                setattr(header, "picking_lines", [])
                grns.append(header)
        else:
            sort_column = sort_map.get(sort_field, PickingHeader.created_at)
            if sort_dir == "desc":
                q = q.order_by(sort_column.desc().nulls_last())
            else:
                q = q.order_by(sort_column.asc().nulls_last())
            total = q.count()
            offset = (page - 1) * limit
            grns = q.offset(offset).limit(limit).all()
            header_ids = [g.id for g in grns]
            if header_ids:
                count_rows = (
                    self.db.query(PickingLine.picking_header_id, func.count(PickingLine.id))
                    .filter(PickingLine.picking_header_id.in_(header_ids))
                    .group_by(PickingLine.picking_header_id)
                    .all()
                )
                counts_by_header = {str(r[0]): r[1] for r in count_rows}
                for g in grns:
                    setattr(g, "lines_count", counts_by_header.get(str(g.id), 0))
                    setattr(g, "picking_lines", [])
            else:
                for g in grns:
                    setattr(g, "lines_count", 0)
                    setattr(g, "picking_lines", [])
        
        return {
            "data": grns,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def list_picking_lines(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        sort_field: str = "spo_allocation",
        sort_dir: str = "asc",
    ):
        """List picking lines (GRN lines) with sort and search by SPO allocation or product."""
        from sqlalchemy.orm import joinedload
        from app.schemas.procurement import PickingLineResponse
        q = (
            self.db.query(PickingLine)
            .join(PickingHeader, PickingLine.picking_header_id == PickingHeader.id)
            .outerjoin(SPOAllocation, PickingLine.spo_allocation_id == SPOAllocation.id)
            .outerjoin(Product, PickingLine.product_id == Product.id)
            .filter(PickingHeader.picking_type == "goods_received")
            .options(
                joinedload(PickingLine.product),
                joinedload(PickingLine.spo_allocation),
                joinedload(PickingLine.source_warehouse),
                joinedload(PickingLine.destination_warehouse),
            )
        )
        if query and query.strip():
            q_str = f"%{query.strip()}%"
            q = q.filter(or_(
                SPOAllocation.spo_number.ilike(q_str),
                Product.product_code.ilike(q_str),
                Product.product_name.ilike(q_str),
            ))
        sort_map = {
            "spo_allocation": SPOAllocation.spo_number,
            "product": Product.product_code,
            "quantity_expected": PickingLine.quantity_expected,
            "quantity_picked": PickingLine.quantity_picked,
        }
        sort_col = sort_map.get(sort_field, SPOAllocation.spo_number)
        if sort_dir == "desc":
            q = q.order_by(sort_col.desc().nulls_last())
        else:
            q = q.order_by(sort_col.asc().nulls_last())
        total = q.count()
        offset = (page - 1) * limit
        lines = q.offset(offset).limit(limit).all()
        data = [PickingLineResponse.model_validate(line) for line in lines]
        return {"data": data, "pagination": {"total": total, "page": page, "limit": limit}, "empty": total == 0}

    def get_grn(self, grn_id: str):
        """Get a GRN by ID."""
        from sqlalchemy.orm import selectinload, joinedload
        grn = self.db.query(PickingHeader).options(
            selectinload(PickingHeader.picking_lines).joinedload(PickingLine.product),
            selectinload(PickingHeader.picking_lines).joinedload(PickingLine.spo_allocation),
            selectinload(PickingHeader.picking_lines).joinedload(PickingLine.source_warehouse),
            selectinload(PickingHeader.picking_lines).joinedload(PickingLine.destination_warehouse),
        ).filter(
            PickingHeader.id == grn_id,
            PickingHeader.picking_type == "goods_received"
        ).first()
        if not grn:
            raise handle_not_found("GRN", grn_id)
        return grn
    
    def create_grn(self, grn_data: PickingHeaderCreate, created_by: str | None = None):
        """Create a new GRN with lines."""
        existing = self.db.query(PickingHeader).filter(
            PickingHeader.picking_number == grn_data.picking_number
        ).first()
        if existing:
            raise handle_conflict("Picking number already exists.")
        
        # Create GRN header and lines in transaction
        grn_dict = grn_data.model_dump(exclude={"picking_lines"})
        grn_dict["picking_type"] = "goods_received"
        if not grn_dict.get("picked_by_user_id"):
            grn_dict["picked_by_user_id"] = str(created_by) if created_by else None
        
        grn = PickingHeader(**grn_dict)
        self.db.add(grn)
        self.db.flush()
        
        # Create lines if provided. Do not link to SPO on create (only link when status becomes approved).
        if grn_data.picking_lines:
            for line_data in grn_data.picking_lines:
                line_dict = line_data.model_dump(exclude={"quantity_discrepancy"}, exclude_none=False)
                line_dict.pop("spo_allocation_id", None)  # Never link on create
                line = PickingLine(**line_dict, picking_header_id=grn.id)
                self.db.add(line)
        
        self.db.commit()
        self.db.refresh(grn)
        return grn
    
    def update_grn(self, grn_id: str, grn_data: PickingHeaderUpdate):
        """Update a GRN. Link to SPO only when status changes to approved; unlink and release quantity when status changes to draft or rejected."""
        grn = self.get_grn(grn_id)
        prev_status = grn.picking_status
        prev_spo_number = grn.spo_number

        update_data = grn_data.model_dump(exclude_unset=True)
        picking_lines_payload = update_data.pop("picking_lines", None)

        for key, value in update_data.items():
            setattr(grn, key, value)
        self.db.flush()

        # When status changes from approved to draft/rejected: unlink and release SPO allocation quantity
        if prev_status == "approved" and grn.picking_status in ("draft", "rejected"):
            self._unlink_grn_from_spo(grn_id)
            self.db.flush()

        if picking_lines_payload is not None:
            self.db.query(PickingLine).filter(PickingLine.picking_header_id == grn_id).delete()
            # Only link to SPO when status is approved; otherwise create lines without spo_allocation_id
            if grn.picking_status == "approved" and grn.spo_number and str(grn.spo_number).strip():
                self._create_grn_lines_with_spo_fifo(grn_id, grn.spo_number, picking_lines_payload)
            else:
                for line_data in picking_lines_payload:
                    line_dict = {k: v for k, v in line_data.items() if k != "quantity_discrepancy"}
                    line_dict.pop("spo_allocation_id", None)  # Do not link when not approved
                    line = PickingLine(**line_dict, picking_header_id=grn_id)
                    self.db.add(line)
        elif grn.picking_status == "approved" and grn.spo_number and str(grn.spo_number).strip():
            status_became_approved = prev_status != "approved"
            spo_changed_while_approved = (
                prev_status == "approved"
                and _spo_match_key(prev_spo_number) != _spo_match_key(grn.spo_number)
            )
            if status_became_approved or spo_changed_while_approved:
                # No line payload: rebuild from existing DB rows and FIFO-link to current SPO
                existing_lines = (
                    self.db.query(PickingLine)
                    .filter(PickingLine.picking_header_id == grn_id)
                    .all()
                )
                if existing_lines:
                    lines_payload = [
                        {
                            "product_id": str(line.product_id),
                            "source_warehouse_id": str(line.source_warehouse_id) if line.source_warehouse_id else None,
                            "quantity_expected": line.quantity_expected or 0,
                            "quantity_picked": line.quantity_picked or 0,
                        }
                        for line in existing_lines
                    ]
                    self.db.query(PickingLine).filter(PickingLine.picking_header_id == grn_id).delete()
                    self._create_grn_lines_with_spo_fifo(grn_id, grn.spo_number, lines_payload)

        self.db.commit()
        self.db.refresh(grn)

        spo_key_changed = _spo_match_key(prev_spo_number) != _spo_match_key(grn.spo_number)
        if grn.picking_status == "approved" and (
            prev_status != "approved"
            or picking_lines_payload is not None
            or spo_key_changed
        ):
            self.sync_grn_received_to_spo(grn_id)
        if (
            grn.picking_status == "approved"
            and prev_status == "approved"
            and spo_key_changed
        ):
            if prev_spo_number and str(prev_spo_number).strip():
                self.sync_received_for_spo_number(prev_spo_number)
            if grn.spo_number and str(grn.spo_number).strip():
                self.sync_received_for_spo_number(grn.spo_number)

        return grn

    def _unlink_grn_from_spo(self, grn_id: str) -> None:
        """Clear spo_allocation_id from all picking lines of this GRN and re-sync SPO allocations to release quantity."""
        grn = self.db.query(PickingHeader).filter(
            PickingHeader.id == grn_id,
            PickingHeader.picking_type == "goods_received",
        ).first()
        if not grn or not grn.spo_number or not str(grn.spo_number).strip():
            return
        lines = self.db.query(PickingLine).filter(PickingLine.picking_header_id == grn_id).all()
        for line in lines:
            line.spo_allocation_id = None
        self.db.flush()
        self.sync_received_for_spo_number(grn.spo_number)
    
    def delete_grn(self, grn_id: str):
        """Delete a GRN and its lines."""
        grn = self.get_grn(grn_id)
        spo_number = grn.spo_number
        was_approved = grn.picking_status == "approved"
        
        # Explicitly delete picking lines first to avoid foreign key constraint issues
        self.db.query(PickingLine).filter(PickingLine.picking_header_id == grn_id).delete()
        
        # Then delete the header
        self.db.delete(grn)
        self.db.commit()
        if was_approved and spo_number and str(spo_number).strip():
            self.sync_received_for_spo_number(spo_number)
        return {"message": "GRN deleted successfully"}

    def bulk_delete_grns(self, grn_ids: list[str]) -> dict:
        """Delete multiple GRNs (and their lines) by ID. Only goods_received type."""
        if not grn_ids:
            return {"message": "No GRNs to delete", "deleted_count": 0}
        deleted = 0
        spo_numbers_to_sync = set()
        for gid in grn_ids:
            grn = (
                self.db.query(PickingHeader)
                .filter(
                    PickingHeader.id == gid,
                    PickingHeader.picking_type == "goods_received",
                )
                .first()
            )
            if grn:
                if grn.picking_status == "approved" and grn.spo_number and str(grn.spo_number).strip():
                    spo_numbers_to_sync.add(str(grn.spo_number))
                self.db.query(PickingLine).filter(PickingLine.picking_header_id == gid).delete()
                self.db.delete(grn)
                deleted += 1
        self.db.commit()
        for spo_number in spo_numbers_to_sync:
            self.sync_received_for_spo_number(spo_number)
        return {"message": f"{deleted} GRN(s) deleted", "deleted_count": deleted}

    def get_grn_by_picking_number(self, picking_number: str):
        """Get GRN (picking header) by picking_number. Returns None if not found."""
        return self.db.query(PickingHeader).filter(
            PickingHeader.picking_number == picking_number,
            PickingHeader.picking_type == "goods_received",
        ).first()

    def upsert_grn_header_for_import(self, picking_number: str, spo_number: Optional[str], picking_date: date):
        """Create or update GRN header by picking_number (idempotent). Returns the header."""
        existing = self.get_grn_by_picking_number(picking_number)
        if existing:
            existing.spo_number = spo_number
            existing.picking_date = picking_date
            existing.picking_status = "approved"
            self.db.commit()
            self.db.refresh(existing)
            return existing
        grn = PickingHeader(
            picking_number=picking_number,
            spo_number=spo_number,
            picking_type="goods_received",
            picking_date=picking_date,
            picking_status="approved",
            inspection_status="pending",
        )
        self.db.add(grn)
        self.db.commit()
        self.db.refresh(grn)
        return grn

    def upsert_grn_line_for_import(
        self,
        picking_header_id: str,
        product_id: str,
        source_warehouse_id: str,
        quantity: int,
        spo_allocation_id: Optional[str] = None,
    ):
        """Create or update one picking line by (header, product, source_warehouse, spo_allocation_id).
        Allows multiple lines with same (header, product, warehouse) when spo_allocation_id differs (for splitting).
        Idempotent."""
        # Match by (header, product, warehouse, spo_allocation_id) to allow splitting across multiple SPOs
        filters = [
            PickingLine.picking_header_id == picking_header_id,
            PickingLine.product_id == product_id,
            PickingLine.source_warehouse_id == source_warehouse_id,
        ]
        if spo_allocation_id is not None:
            filters.append(PickingLine.spo_allocation_id == spo_allocation_id)
        else:
            filters.append(PickingLine.spo_allocation_id.is_(None))
        
        line = self.db.query(PickingLine).filter(*filters).first()
        if line:
            line.quantity_expected = quantity
            line.quantity_picked = quantity
            self.db.flush()
            return line
        line = PickingLine(
            picking_header_id=picking_header_id,
            product_id=product_id,
            source_warehouse_id=source_warehouse_id,
            quantity_expected=quantity,
            quantity_picked=quantity,
            spo_allocation_id=spo_allocation_id,
        )
        self.db.add(line)
        self.db.flush()
        return line

    def _add_picking_line(
        self,
        picking_header_id: str,
        product_id: str,
        source_warehouse_id: Optional[str],
        quantity_expected: int,
        quantity_picked: int,
        spo_allocation_id: Optional[str] = None,
    ) -> PickingLine:
        """Create one picking line (used by FIFO when splitting)."""
        line = PickingLine(
            picking_header_id=picking_header_id,
            product_id=product_id,
            source_warehouse_id=source_warehouse_id,
            quantity_expected=quantity_expected,
            quantity_picked=quantity_picked,
            spo_allocation_id=spo_allocation_id,
            picked_condition="good",
        )
        self.db.add(line)
        self.db.flush()
        return line

    def _create_grn_lines_with_spo_fifo(
        self,
        grn_id: str,
        spo_number: str,
        lines_payload: List[Dict[str, Any]],
    ) -> None:
        """Create picking lines for a GRN, assigning spo_allocation_id via FIFO by SPO number + product.
        Matches import logic: same SPO number + product, consume from allocations (same warehouse first, then others)."""
        spo_key = _spo_match_key(spo_number)
        if not spo_key:
            for line_data in lines_payload:
                line_dict = {k: v for k, v in line_data.items() if k != "quantity_discrepancy"}
                line = PickingLine(**line_dict, picking_header_id=grn_id)
                self.db.add(line)
            return

        for line_data in lines_payload:
            product_id = line_data.get("product_id")
            if not product_id:
                continue
            source_warehouse_id = line_data.get("source_warehouse_id")
            quantity_expected = int(line_data.get("quantity_expected") or 0)
            quantity_picked = int(line_data.get("quantity_picked") or 0)
            if quantity_expected <= 0 and quantity_picked <= 0:
                continue

            # SPO allocations for this product, same SPO match key, FIFO by created_at
            allocations = (
                self.db.query(SPOAllocation)
                .filter(
                    SPOAllocation.product_id == product_id,
                    SPOAllocation.spo_number.isnot(None),
                )
                .order_by(SPOAllocation.created_at.asc())
                .all()
            )
            spo_allocations = [
                a for a in allocations
                if _spo_match_key(a.spo_number) == spo_key
            ]
            # Pool: [alloc_id, alloc_warehouse_id, available]
            spo_pool: List[List[Any]] = []
            for alloc in spo_allocations:
                received = self.compute_received_for_allocation(str(alloc.id))
                available = alloc.allocated_quantity - received
                if available > 0:
                    spo_pool.append([str(alloc.id), alloc.warehouse_id, available])

            # Consume from SPO pool by received qty when present; otherwise expected (draft line with only expected filled).
            remaining = quantity_picked if quantity_picked > 0 else quantity_expected
            first_chunk = True

            # First pass: same warehouse
            for entry in spo_pool:
                alloc_id, alloc_wh, avail = entry
                if alloc_wh != source_warehouse_id or avail <= 0 or remaining <= 0:
                    continue
                take = min(remaining, avail)
                qty_exp = quantity_expected if first_chunk else 0
                self._add_picking_line(
                    grn_id, product_id, source_warehouse_id,
                    qty_exp, take, alloc_id,
                )
                remaining -= take
                entry[2] = avail - take
                first_chunk = False

            # Second pass: other warehouses
            for entry in spo_pool:
                alloc_id, alloc_wh, avail = entry
                if alloc_wh == source_warehouse_id or avail <= 0 or remaining <= 0:
                    continue
                take = min(remaining, avail)
                qty_exp = quantity_expected if first_chunk else 0
                self._add_picking_line(
                    grn_id, product_id, source_warehouse_id,
                    qty_exp, take, alloc_id,
                )
                remaining -= take
                entry[2] = avail - take
                first_chunk = False

            if remaining > 0:
                qty_exp = quantity_expected if first_chunk else 0
                self._add_picking_line(
                    grn_id, product_id, source_warehouse_id,
                    qty_exp, remaining, None,
                )
            elif first_chunk and (quantity_expected > 0 or quantity_picked > 0):
                # No SPO consumption (e.g. quantity_picked is 0) but we still need one line
                self._add_picking_line(
                    grn_id, product_id, source_warehouse_id,
                    quantity_expected, quantity_picked, None,
                )

    def compute_received_for_allocation(self, allocation_id: str) -> int:
        """Computed on read: sum quantity_expected from picking lines where spo_allocation_id = allocation_id
        and the picking line's header (GRN) is approved. Not stored in DB."""
        from sqlalchemy import func
        total = (
            self.db.query(func.coalesce(func.sum(PickingLine.quantity_expected), 0))
            .join(PickingHeader, PickingLine.picking_header_id == PickingHeader.id)
            .filter(
                PickingLine.spo_allocation_id == allocation_id,
                PickingHeader.picking_type == "goods_received",
                PickingHeader.picking_status == "approved",
            )
            .scalar()
        )
        return int(total)

    def get_computed_received_map(self, allocation_ids: list[str]) -> dict[str, int]:
        """Bulk: for each allocation id, return computed quantity_received (sum quantity_expected from approved GRN lines)."""
        if not allocation_ids:
            return {}
        from sqlalchemy import func
        rows = (
            self.db.query(PickingLine.spo_allocation_id, func.coalesce(func.sum(PickingLine.quantity_expected), 0))
            .join(PickingHeader, PickingLine.picking_header_id == PickingHeader.id)
            .filter(
                PickingLine.spo_allocation_id.in_(allocation_ids),
                PickingHeader.picking_type == "goods_received",
                PickingHeader.picking_status == "approved",
            )
            .group_by(PickingLine.spo_allocation_id)
            .all()
        )
        received_map = {str(r[0]): int(r[1]) for r in rows}
        return {aid: received_map.get(aid, 0) for aid in allocation_ids}

    def sync_grn_received_to_spo(self, picking_header_id: str) -> None:
        """After GRN is approved: set quantity_received on each affected SPO allocation (DB field, for legacy/reports).
        From picking lines (spo_allocation_id = allocation, header approved). Idempotent.
        Also refreshes inbound_shipment_lines.line_status for affected shipments."""
        lines = self.db.query(PickingLine).filter(
            PickingLine.picking_header_id == picking_header_id,
            PickingLine.spo_allocation_id.isnot(None),
        ).all()
        allocation_ids = {str(line.spo_allocation_id) for line in lines if line.spo_allocation_id}
        shipment_ids = set()
        for alloc_id in allocation_ids:
            alloc = self.db.query(SPOAllocation).filter(SPOAllocation.id == alloc_id).first()
            if not alloc:
                continue
            shipment_ids.add(alloc.inbound_shipment_id)
            total = self.compute_received_for_allocation(alloc_id)
            alloc.quantity_received = total
            alloc.receipt_status = "received" if total >= alloc.allocated_quantity else "pending"
        self.db.commit()
        inbound_svc = InboundShipmentService(self.db)
        for sid in shipment_ids:
            inbound_svc.refresh_shipment_line_statuses(sid)

    def sync_received_for_spo_number(self, spo_number: Optional[str]) -> None:
        """Re-sync DB quantity_received for all allocations under this SPO (optional background use)."""
        if not spo_number or not spo_number.strip():
            return
        target_key = _spo_match_key(spo_number)
        if not target_key:
            return
        allocations = self.db.query(SPOAllocation).filter(SPOAllocation.spo_number.isnot(None)).all()
        shipment_ids = set()
        for alloc in allocations:
            if _spo_match_key(alloc.spo_number) != target_key:
                continue
            alloc_id = str(alloc.id)
            total = self.compute_received_for_allocation(alloc_id)
            alloc.quantity_received = total
            alloc.receipt_status = "received" if total >= alloc.allocated_quantity else "pending"
            if alloc.inbound_shipment_id:
                shipment_ids.add(alloc.inbound_shipment_id)
        self.db.commit()
        inbound_svc = InboundShipmentService(self.db)
        for sid in shipment_ids:
            inbound_svc.refresh_shipment_line_statuses(sid)

    def get_linked_grns_for_spo(self, spo_number: Optional[str]):
        """Return list of GRN headers (id, picking_number, picking_status, picking_date) for this SPO number.
        Matches by alphanumeric SPO key so variant formats (e.g. SPO-202602-0102 vs SPO-2026/02-0102) align."""
        if not spo_number or not spo_number.strip():
            return []
        target_key = _spo_match_key(spo_number)
        if not target_key:
            return []
        rows = (
            self.db.query(
                PickingHeader.id,
                PickingHeader.picking_number,
                PickingHeader.picking_status,
                PickingHeader.picking_date,
                PickingHeader.spo_number,
            )
            .filter(
                PickingHeader.picking_type == "goods_received",
                PickingHeader.spo_number.isnot(None),
            )
            .order_by(PickingHeader.picking_date.desc().nulls_last(), PickingHeader.picking_number)
            .all()
        )
        return [
            {"id": str(r[0]), "picking_number": r[1], "picking_status": r[2], "picking_date": r[3]}
            for r in rows
            if _spo_match_key(r[4]) == target_key
        ]


class StockInquiryService:
    """Service for stock inquiry operations."""
    
    def __init__(self, db: Session):
        self.db = db
        from app.services.entity_attachment_service import EntityAttachmentService
        self.entity_attachment_service = EntityAttachmentService(db)

    def _get_team_user_ids_for_agent_code(self, agent_code: str) -> List[str]:
        """Return user IDs of all teams assigned to the access agent with the given code."""
        from app.services.user_service import AccessAgentService
        from app.models.access import AgentTeam, TeamMember

        agent_id = AccessAgentService(self.db).get_agent_id_by_code(agent_code)
        if not agent_id:
            logger.debug("No access agent found for code=%s", agent_code)
            return []

        rows = (
            self.db.query(TeamMember.user_id)
            .join(AgentTeam, AgentTeam.team_id == TeamMember.team_id)
            .filter(AgentTeam.agent_id == agent_id)
            .distinct()
            .all()
        )
        return [str(r[0]) for r in rows if r and r[0]]

    def _get_team_user_ids_for_agent_team_assignment(
        self, agent_code: str, team_assignment_code: str
    ) -> List[str]:
        """Return user IDs of the team assigned to the agent with the given team assignment code (e.g. project_sales, purchasing)."""
        from app.services.user_service import AccessAgentService
        from app.models.access import TeamMember

        agent_svc = AccessAgentService(self.db)
        agent_id = agent_svc.get_agent_id_by_code(agent_code)
        if not agent_id:
            logger.debug("No access agent found for code=%s", agent_code)
            return []
        team_id = agent_svc.get_team_id_by_code(agent_id, team_assignment_code)
        if not team_id:
            logger.debug(
                "No team assignment found for agent %s with code=%s",
                agent_code,
                team_assignment_code,
            )
            return []
        rows = self.db.query(TeamMember.user_id).filter(TeamMember.team_id == team_id).all()
        return [str(r[0]) for r in rows if r and r[0]]

    def _get_team_user_ids_for_agent_tier(
        self, agent_code: str, tier: int
    ) -> List[str]:
        """Return user IDs of the team assigned to the agent with the given tier (1=initial, 2/3=escalation)."""
        from app.services.user_service import AccessAgentService
        from app.models.access import TeamMember

        agent_svc = AccessAgentService(self.db)
        agent_id = agent_svc.get_agent_id_by_code(agent_code)
        if not agent_id:
            logger.debug("No access agent found for code=%s", agent_code)
            return []
        team_id = agent_svc.get_team_id_by_tier(agent_id, tier)
        if not team_id:
            logger.debug(
                "No team assignment found for agent %s with tier=%s",
                agent_code,
                tier,
            )
            return []
        rows = self.db.query(TeamMember.user_id).filter(TeamMember.team_id == team_id).all()
        return [str(r[0]) for r in rows if r and r[0]]

    def _build_stock_inquiry_view_url(self, inquiry_id: str, base_url_override: Optional[str] = None) -> str:
        """Build a shareable (no-auth) frontend link for a stock inquiry using view token."""
        from app.models.user import SystemSetting

        view_token = self.get_or_create_view_token(inquiry_id)
        base_url = (base_url_override or "").strip().rstrip("/")
        if not base_url:
            base_url = (settings.frontend_base_url or "").strip().rstrip("/")
        if not base_url:
            sys_settings = self.db.query(SystemSetting).first()
            if sys_settings and getattr(sys_settings, "website_url", None):
                base_url = (sys_settings.website_url or "").strip().rstrip("/")
        return f"{base_url}/view/stock-inquiry?token={view_token}" if base_url else f"/view/stock-inquiry?token={view_token}"

    def _notify_team_stock_inquiry(
        self,
        *,
        inquiry_id: str,
        agent_code: str,
        team_assignment_code: Optional[str] = None,
        title: str,
        intro_plain: str,
        intro_html: str,
        event_type: str,
        base_url_override: Optional[str] = None,
        sync_email: bool = False,
    ) -> None:
        """Notify a team via in-app (each user) + one email to all. If team_assignment_code is set, use that assignment under the agent; else all teams for the agent. When sync_email=True, send email in the same request (e.g. for external API); otherwise enqueue to notifications queue."""
        from app.models.user import User
        from app.models.notification import Notification, NotificationDelivery
        from app.services.notification_service import NotificationService
        from datetime import datetime

        if team_assignment_code:
            if team_assignment_code == "project_sales":
                user_ids = (
                    self._get_team_user_ids_for_agent_tier(agent_code, 1)
                    or self._get_team_user_ids_for_agent_team_assignment(agent_code, "project_sales")
                )
            else:
                user_ids = self._get_team_user_ids_for_agent_team_assignment(agent_code, team_assignment_code)
        else:
            user_ids = self._get_team_user_ids_for_agent_code(agent_code)
        if not user_ids:
            logger.warning(
                "No team members found for agent code '%s'%s. Assign a team under Team Assignments (Tier 1 or code project_sales).",
                agent_code,
                f" with assignment code '{team_assignment_code}'" if team_assignment_code else "",
            )
            return

        users = self.db.query(User).filter(User.id.in_(user_ids)).all()
        emails = [u.email for u in users if getattr(u, "email", None) and str(u.email).strip()]
        if not emails:
            logger.warning("Team members for %s have no email addresses; skipping email.", agent_code)

        view_url = self._build_stock_inquiry_view_url(inquiry_id, base_url_override=base_url_override)
        # Requirement: include the link as a pure hyperlink (anchor text is the URL; no extra wording).
        body_plain = (
            f"{intro_plain}\n\n"
            f"{view_url}\n\n"
            "This is a system generated email. Please do not reply."
        )
        body_html = (
            f"<p>{intro_html}</p>\n"
            f'<p><a href="{view_url}">{view_url}</a></p>\n'
            "<p>This is a system generated email. Please do not reply.</p>"
        )

        notif_svc = NotificationService(self.db)
        first_uid = user_ids[0]

        if emails:
            notification = Notification(
                user_id=first_uid,
                type="stock_inquiry_notification",
                title=title,
                body=body_plain,
                data={"recipient_emails": emails, "single_email_to_all": True, "body_html": body_html},
                source_entity_type="stock_inquiry",
                source_entity_id=inquiry_id,
                event_type=event_type,
            )
            self.db.add(notification)
            self.db.flush()
            self.db.add(
                NotificationDelivery(
                    notification_id=notification.id,
                    channel="in_app",
                    status="sent",
                    sent_at=datetime.utcnow(),
                )
            )
            self.db.add(NotificationDelivery(notification_id=notification.id, channel="email", status="pending"))
            self.db.commit()
            self.db.refresh(notification)
            try:
                if sync_email:
                    from app.tasks import notification_tasks
                    notification_tasks.send_notification_deliveries(str(notification.id))
                else:
                    from app.services.queue_service import enqueue_job
                    from app.tasks import notification_tasks
                    enqueue_job(notification_tasks.send_notification_deliveries, str(notification.id), queue_name="notifications")
            except Exception as e:
                logger.warning("Failed to send/enqueue notification deliveries: %s", e)

        for uid in user_ids:
            if uid == first_uid and emails:
                continue
            try:
                notif_svc.create_in_app_only(
                    user_id=uid,
                    type="stock_inquiry_notification",
                    title=title,
                    body=body_plain,
                    source_entity_type="stock_inquiry",
                    source_entity_id=inquiry_id,
                    event_type=event_type,
                )
            except Exception as e:
                logger.warning("Failed to create in-app notification for user %s: %s", uid, e)
    
    def list_inquiries(self, page: int = 1, limit: int = 50, query: Optional[str] = None, sort_field: str = "created_at", sort_dir: str = "desc"):
        """List stock inquiries."""
        q = self.db.query(StockInquiry)
        
        if query:
            q = q.filter(
                or_(
                    StockInquiry.product_code.ilike(f"%{query}%"),
                    StockInquiry.item_description.ilike(f"%{query}%"),
                    StockInquiry.project_customer.ilike(f"%{query}%")
                )
            )
        
        # Normalize sort parameters - default to id since created_at may not exist in DB
        if sort_field and isinstance(sort_field, str):
            sort_field = sort_field.strip().lower() or "id"
        else:
            sort_field = "id"
        
        if sort_dir and isinstance(sort_dir, str):
            sort_dir = sort_dir.strip().lower() or "desc"
        else:
            sort_dir = "desc"
        
        sort_map = {
            "id": StockInquiry.id,
            "product_code": StockInquiry.product_code,
            "delivery_date": StockInquiry.delivery_date,
        }
        # Only use created_at/updated_at if explicitly requested and column exists
        # For now, default to id to avoid database errors
        sort_column = sort_map.get(sort_field, StockInquiry.id)
        
        # Ensure sort_dir is either "asc" or "desc"
        if sort_dir not in ["asc", "desc"]:
            sort_dir = "desc"
        
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        inquiries = q.offset(offset).limit(limit).all()
        
        from app.schemas.common import PaginationResponse
        
        return {
            "data": inquiries,
            "pagination": PaginationResponse(total=total, page=page, limit=limit),
            "empty": total == 0
        }
    
    def get_inquiry(self, inquiry_id: str):
        """Get a stock inquiry by ID."""
        inquiry = self.db.query(StockInquiry).filter(StockInquiry.id == inquiry_id).first()
        if not inquiry:
            raise handle_not_found("Stock Inquiry", inquiry_id)
        return inquiry

    def _resolve_user_display_name(self, user_id: Optional[str]) -> Optional[str]:
        """Resolve user id (CRM id or respond_user_id) to display name (name or email)."""
        if not user_id or not str(user_id).strip():
            return None
        from app.models.user import User
        user = (
            self.db.query(User)
            .filter(or_(User.id == user_id, User.respond_user_id == user_id))
            .first()
        )
        if not user:
            return None
        return user.name or user.email or None

    def get_inquiry_for_response(self, inquiry_id: str) -> dict:
        """Get stock inquiry as dict with last_responded_by_name resolved for API response."""
        inquiry = self.get_inquiry(inquiry_id)
        data = {attr.key: getattr(inquiry, attr.key) for attr in inspect(inquiry).mapper.column_attrs}
        data["last_responded_by_name"] = (
            self._resolve_user_display_name(inquiry.last_responded_by) if inquiry.last_responded_by else None
        )
        data["rejected_by_name"] = (
            self._resolve_user_display_name(inquiry.rejected_by) if inquiry.rejected_by else None
        )
        data["reopened_by_name"] = (
            self._resolve_user_display_name(inquiry.reopened_by) if inquiry.reopened_by else None
        )
        links = self.entity_attachment_service.list_links("stock_inquiry", str(inquiry.id))
        data["attachments"] = [
            self.entity_attachment_service.serialize_link(
                link,
                entity_key="inquiry_id",
                link_type="stock_inquiry_attachment",
            )
            for link in links
        ]
        return data

    def get_neighbour_ids(self, inquiry_id: str) -> dict:
        """Return prev_id and next_id for the given inquiry (order: id desc, same as default list)."""
        inquiry = self.db.query(StockInquiry).filter(StockInquiry.id == inquiry_id).first()
        if not inquiry:
            return {"prev_id": None, "next_id": None}
        q_desc = (
            self.db.query(StockInquiry.id)
            .order_by(StockInquiry.id.desc())
        )
        ids = [r[0] for r in q_desc.all()]
        try:
            idx = ids.index(inquiry_id)
        except ValueError:
            return {"prev_id": None, "next_id": None}
        prev_id = ids[idx - 1] if idx > 0 else None
        next_id = ids[idx + 1] if idx < len(ids) - 1 else None
        return {"prev_id": prev_id, "next_id": next_id}

    def get_or_create_view_token(self, inquiry_id: str) -> str:
        """Get or create a reusable view token for this stock inquiry. Returns the token string."""
        self.get_inquiry(inquiry_id)  # ensure exists
        row = (
            self.db.query(ViewToken)
            .filter(
                ViewToken.entity_type == "stock_inquiry",
                ViewToken.entity_id == inquiry_id,
            )
            .first()
        )
        if row:
            return row.token
        token_value = secrets.token_urlsafe(32)
        view_token = ViewToken(
            entity_type="stock_inquiry",
            entity_id=inquiry_id,
            token=token_value,
        )
        self.db.add(view_token)
        self.db.flush()
        return token_value

    def get_inquiry_summary_by_token(self, token_value: str) -> dict:
        """Return read-only stock inquiry summary for the given view token. No auth required."""
        view_token = (
            self.db.query(ViewToken)
            .filter(ViewToken.token == token_value, ViewToken.entity_type == "stock_inquiry")
            .first()
        )
        if not view_token or not view_token.entity_id:
            raise handle_not_found("View link", "(invalid token)")
        inquiry = self.get_inquiry(str(view_token.entity_id))
        links = self.entity_attachment_service.list_links("stock_inquiry", str(inquiry.id))
        return {
            "entity_type": "stock_inquiry",
            "entity_id": inquiry.id,
            "salesperson": getattr(inquiry, "salesperson", None),
            "product_code": getattr(inquiry, "product_code", None),
            "item_description": getattr(inquiry, "item_description", None),
            "project_customer": getattr(inquiry, "project_customer", None),
            "project_name": getattr(inquiry, "project_name", None),
            "quantity": getattr(inquiry, "quantity", None),
            "delivery_date": getattr(inquiry, "delivery_date", None),
            "remark": getattr(inquiry, "remark", None),
            "additional_remark": getattr(inquiry, "additional_remark", None),
            "purchasing_response": getattr(inquiry, "purchasing_response", None),
            "status": getattr(inquiry, "status", None),
            "last_responded_at": getattr(inquiry, "last_responded_at", None),
            "created_at": getattr(inquiry, "created_at", None),
            "updated_at": getattr(inquiry, "updated_at", None),
            "attachments": [
                self.entity_attachment_service.serialize_link(
                    link,
                    entity_key="inquiry_id",
                    link_type="stock_inquiry_attachment",
                )
                for link in links
            ],
        }

    def _build_respond_inbox_url(self, contact_id: Optional[str], space_id: Optional[str]) -> Optional[str]:
        """Build respond.io inbox URL: {base}/space/{space_id}/inbox/{contact_id}."""
        if not contact_id or not space_id:
            return None
        base = (settings.respond_app_base_url or "").rstrip("/")
        if not base:
            return None
        return f"{base}/space/{space_id.strip()}/inbox/{contact_id.strip()}"

    # Allowed initial statuses when creating via API (e.g. external flow can start in pending_project_sales).
    _CREATE_ALLOWED_STATUSES = ("new", "pending_project_sales", "pending_purchasing")

    def create_inquiry(self, inquiry_data: StockInquiryCreate):
        """Create a new stock inquiry. Status may be set via API to start in project sales or purchasing queue."""
        data = inquiry_data.model_dump()
        contact_id = data.get("contact_id")
        space_id = data.get("space_id")
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)
        if respond_inbox_url is not None:
            data["respond_inbox_url"] = respond_inbox_url
        status = data.get("status")
        if status is not None and status not in self._CREATE_ALLOWED_STATUSES:
            from app.services.error_handler import handle_validation_error
            raise handle_validation_error(
                f"status must be one of {self._CREATE_ALLOWED_STATUSES!r}, got {status!r}"
            )
        if status is None:
            data["status"] = "new"
        inquiry = StockInquiry(**data)
        self.db.add(inquiry)
        self.db.commit()
        self.db.refresh(inquiry)
        return inquiry

    def delete_inquiry(self, inquiry_id: str) -> dict:
        """Delete a stock inquiry by ID."""
        inquiry = self.get_inquiry(inquiry_id)
        self.entity_attachment_service.delete_links_for_entity("stock_inquiry", str(inquiry.id))
        self.db.delete(inquiry)
        self.db.commit()
        return {"message": "Stock inquiry deleted successfully"}

    def bulk_delete_inquiries(self, inquiry_ids: list[str]) -> dict:
        """Delete multiple stock inquiries by ID."""
        if not inquiry_ids:
            return {"message": "No inquiries to delete", "deleted_count": 0}
        deleted = 0
        for iid in inquiry_ids:
            inquiry = self.db.query(StockInquiry).filter(StockInquiry.id == iid).first()
            if inquiry:
                self.entity_attachment_service.delete_links_for_entity("stock_inquiry", str(inquiry.id))
                self.db.delete(inquiry)
                deleted += 1
        self.db.commit()
        return {"message": f"{deleted} stock inquiry(ies) deleted", "deleted_count": deleted}

    def link_attachment_to_inquiry(self, inquiry_id: str, attachment_id: str, created_by: Optional[str] = None):
        """Link an existing attachment to a stock inquiry (generic entity_attachment_links table)."""
        self.get_inquiry(inquiry_id)  # ensure inquiry exists
        link = self.entity_attachment_service.link_existing_attachment(
            entity_type="stock_inquiry",
            entity_id=str(inquiry_id),
            attachment_id=str(attachment_id),
            created_by=created_by,
        )
        self.db.commit()
        self.db.refresh(link)
        return link

    def delete_inquiry_attachment(self, link_id: str):
        """Delete a stock-inquiry attachment link from generic entity_attachment_links table."""
        link = self.entity_attachment_service.delete_link(link_id, entity_type="stock_inquiry")
        self.db.commit()
        return link

    def _identifier_from_respond_inbox_url(self, respond_inbox_url: Optional[str]) -> Optional[str]:
        """Extract contact identifier from respond_inbox_url (last path segment)."""
        if not respond_inbox_url or not respond_inbox_url.strip():
            return None
        parts = [p for p in respond_inbox_url.rstrip("/").split("/") if p]
        return parts[-1] if parts else None

    def update_inquiry(self, inquiry_id: str, inquiry_data: StockInquiryUpdate):
        """Update a stock inquiry. Status is only changed via workflow actions (submit/approve/reject/reopen)."""
        inquiry = self.get_inquiry(inquiry_id)

        update_data = inquiry_data.model_dump(exclude_unset=True)
        update_data.pop("status", None)  # Status only via workflow endpoints

        contact_id = update_data.get("contact_id") if "contact_id" in update_data else inquiry.contact_id
        space_id = update_data.get("space_id") if "space_id" in update_data else inquiry.space_id
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)
        if respond_inbox_url is not None:
            update_data["respond_inbox_url"] = respond_inbox_url
        elif contact_id is None and space_id is None:
            update_data["respond_inbox_url"] = None

        # Status is only changed via workflow actions (submit/approve/reject/reopen) and update_and_reply
        for key, value in update_data.items():
            setattr(inquiry, key, value)

        self.db.commit()
        self.db.refresh(inquiry)
        return inquiry

    def update_inquiry_and_reply(
        self,
        inquiry_id: str,
        inquiry_data: StockInquiryUpdate,
        respond_user_id: str,
        request_url: str = "",
    ):
        """
        Update inquiry, send message to Respond.io, update SLA tracking to responded, set status=responded.
        All integration calls are logged via IntegrationLogService.
        """
        import logging
        import time
        from datetime import datetime, timezone
        from app.services.integration_service import RespondClient, IntegrationLogService
        from app.schemas.integration import IntegrationLogCreate
        from app.services.sla_service import ConversationSLATrackingService
        from app.schemas.sla import ConversationSLATrackingUpdate

        logger = logging.getLogger(__name__)
        log_service = IntegrationLogService(self.db)

        inquiry = self.get_inquiry(inquiry_id)
        allowed_statuses = {"pending_purchasing", "responded"}
        if inquiry.status not in allowed_statuses:
            from app.services.error_handler import handle_validation_error
            raise handle_validation_error(
                "Update & Reply is only allowed when inquiry is pending purchasing review or responded. "
                "Current status: " + (inquiry.status or "unknown")
            )

        update_data = inquiry_data.model_dump(exclude_unset=True)
        contact_id = update_data.get("contact_id") if "contact_id" in update_data else inquiry.contact_id
        space_id = update_data.get("space_id") if "space_id" in update_data else inquiry.space_id
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)
        if respond_inbox_url is not None:
            update_data["respond_inbox_url"] = respond_inbox_url
        elif contact_id is None and space_id is None:
            update_data["respond_inbox_url"] = None

        # Message to send (may include view link); do not write back to purchasing_response
        message_text = update_data.get("purchasing_response") or inquiry.purchasing_response
        if not (message_text and str(message_text).strip()):
            from app.services.error_handler import handle_validation_error
            raise handle_validation_error("purchasing_response is required to reply.")
        # Do not persist the reply payload (often includes view link) into purchasing_response
        update_data.pop("purchasing_response", None)

        for key, value in update_data.items():
            setattr(inquiry, key, value)
        self.db.flush()

        identifier = self._identifier_from_respond_inbox_url(inquiry.respond_inbox_url)
        if not identifier:
            from app.services.error_handler import handle_validation_error
            raise handle_validation_error("respond_inbox_url is missing or invalid; cannot send message.")

        # Send the full composed message (e.g. with view link) to the contact; do not truncate
        message_to_send = str(message_text).strip()

        try:
            client = RespondClient()
            response = client.send_message(identifier, message_to_send)

            # Verify delivery status from Respond message endpoint and surface failed delivery to UI.
            message_id = response.get("messageId") if isinstance(response, dict) else None
            delivery_failed_message = None
            if message_id is not None:
                for attempt in range(3):
                    try:
                        sent_message = client.get_message(identifier, message_id)
                        log_service.create_integration_log(
                            IntegrationLogCreate(
                                integration_channel="respond_io",
                                business_table="stock_inquiries",
                                business_id=inquiry_id,
                                external_reference=f"{identifier}:{message_id}",
                                direction="outbound",
                                endpoint=f"https://api.respond.io/v2/contact/id:{identifier}/message/{message_id}",
                                http_method="GET",
                                status="success",
                                response_payload=str(sent_message)[:50000] if sent_message else None,
                            ),
                        )

                        statuses = sent_message.get("status") if isinstance(sent_message, dict) else None
                        if isinstance(statuses, list):
                            failed_status = next(
                                (
                                    s for s in statuses
                                    if isinstance(s, dict) and str(s.get("value", "")).lower() == "failed"
                                ),
                                None,
                            )
                            if failed_status:
                                delivery_failed_message = (failed_status.get("message") or "").strip()
                                break
                            # Status array exists and no failure -> no need to poll longer.
                            break
                    except Exception as status_check_err:
                        log_service.create_integration_log(
                            IntegrationLogCreate(
                                integration_channel="respond_io",
                                business_table="stock_inquiries",
                                business_id=inquiry_id,
                                external_reference=f"{identifier}:{message_id}",
                                direction="outbound",
                                endpoint=f"https://api.respond.io/v2/contact/id:{identifier}/message/{message_id}",
                                http_method="GET",
                                status="failed",
                                error_message=str(status_check_err),
                            ),
                        )
                        if attempt == 2:
                            logger.warning(
                                "Unable to verify Respond message status for stock_inquiry %s (message_id=%s): %s",
                                inquiry_id,
                                message_id,
                                status_check_err,
                            )
                    if attempt < 2:
                        time.sleep(0.6)

            if delivery_failed_message:
                from app.services.error_handler import handle_validation_error
                raise handle_validation_error(
                    delivery_failed_message or "Respond.io failed to deliver the message."
                )

            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="stock_inquiries",
                    business_id=inquiry_id,
                    external_reference=identifier,
                    direction="outbound",
                    endpoint=f"https://api.respond.io/v2/contact/id:{identifier}/message",
                    http_method="POST",
                    status="success",
                    response_payload=str(response)[:50000] if response else None,
                ),
                request_payload_dict={"message": {"type": "text", "text": message_to_send}},
            )
        except Exception as e:
            from app.services.error_handler import AppException
            if isinstance(e, AppException):
                raise
            logger.exception("Respond.io send_message failed for stock_inquiry %s", inquiry_id)
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="stock_inquiries",
                    business_id=inquiry_id,
                    external_reference=identifier or "",
                    direction="outbound",
                    endpoint=f"https://api.respond.io/v2/contact/id:{identifier or ''}/message",
                    http_method="POST",
                    status="failed",
                    error_message=str(e),
                ),
                request_payload_dict={"message": {"type": "text", "text": message_to_send}},
            )
            raise

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        sla_service = ConversationSLATrackingService(self.db)
        tracking = sla_service.get_tracking_by_source_entity("stock_inquiry", inquiry_id)
        if tracking:
            try:
                sla_service.update_tracking(
                    str(tracking.id),
                    ConversationSLATrackingUpdate(
                        is_responded=True,
                        responded_at=now_utc,
                        responded_by=respond_user_id,
                    ),
                )
                log_service.create_integration_log(
                    IntegrationLogCreate(
                        integration_channel="sla_management",
                        business_table="conversation_sla_tracking",
                        business_id=str(tracking.id),
                        external_reference=inquiry_id,
                        direction="inbound",
                        endpoint=request_url or "/api/v1/procurement/stock-inquiries/update-and-reply",
                        http_method="POST",
                        status="success",
                    ),
                    request_payload_dict={"is_responded": True, "responded_by": respond_user_id},
                )
            except Exception as sla_err:
                logger.warning("SLA tracking update failed for stock_inquiry %s: %s", inquiry_id, sla_err)
                log_service.create_integration_log(
                    IntegrationLogCreate(
                        integration_channel="sla_management",
                        business_table="conversation_sla_tracking",
                        business_id=str(tracking.id),
                        external_reference=inquiry_id,
                        direction="inbound",
                        endpoint=request_url or "/api/v1/procurement/stock-inquiries/update-and-reply",
                        http_method="POST",
                        status="failed",
                        error_message=str(sla_err),
                    ),
                    request_payload_dict={"is_responded": True, "responded_by": respond_user_id},
                )

        inquiry.status = "responded"
        inquiry.last_responded_by = respond_user_id
        inquiry.last_responded_at = now_utc
        self.db.commit()
        self.db.refresh(inquiry)
        return inquiry

    def submit_inquiry_for_project_sales(self, inquiry_id: str) -> StockInquiry:
        """Move inquiry from new to pending_project_sales."""
        inquiry = self.get_inquiry(inquiry_id)
        if inquiry.status != "new":
            from app.services.error_handler import handle_validation_error
            raise handle_validation_error(f"Cannot submit for project sales when status is {inquiry.status}. Expected: new.")
        inquiry.status = "pending_project_sales"
        self.db.commit()
        self.db.refresh(inquiry)
        return inquiry

    def project_sales_approve_inquiry(self, inquiry_id: str) -> StockInquiry:
        """Move inquiry from pending_project_sales to pending_purchasing."""
        inquiry = self.get_inquiry(inquiry_id)
        if inquiry.status != "pending_project_sales":
            from app.services.error_handler import handle_validation_error
            raise handle_validation_error(f"Cannot approve when status is {inquiry.status}. Expected: pending_project_sales.")
        inquiry.status = "pending_purchasing"
        inquiry.rejection_reason = None
        inquiry.rejected_at = None
        inquiry.rejected_by = None
        inquiry.rejected_from = None
        self.db.commit()
        self.db.refresh(inquiry)
        try:
            self._notify_team_stock_inquiry(
                inquiry_id=str(inquiry.id),
                agent_code="lead_time_enquiries",
                team_assignment_code="purchasing",
                title="Stock Inquiry pending purchasing review",
                intro_plain="Dear Purchasing Team,\n\nA stock inquiry has been approved and is now pending purchasing review.",
                intro_html="Dear Purchasing Team,<br /><br />A stock inquiry has been approved and is now pending purchasing review.",
                event_type="pending_purchasing",
            )
        except Exception as e:
            logger.warning("Failed to notify purchasing team for stock inquiry %s: %s", inquiry_id, e)
        return inquiry

    def project_sales_reject_inquiry(
        self, inquiry_id: str, reason: Optional[str] = None, user_id: Optional[str] = None
    ) -> StockInquiry:
        """Move inquiry from pending_project_sales to rejected."""
        from datetime import datetime, timezone
        inquiry = self.get_inquiry(inquiry_id)
        if inquiry.status != "pending_project_sales":
            from app.services.error_handler import handle_validation_error
            raise handle_validation_error(f"Cannot reject when status is {inquiry.status}. Expected: pending_project_sales.")
        inquiry.status = "rejected"
        inquiry.rejected_from = "pending_project_sales"
        inquiry.rejection_reason = reason
        inquiry.rejected_at = datetime.now(timezone.utc).replace(tzinfo=None)
        inquiry.rejected_by = user_id
        self.db.commit()
        self.db.refresh(inquiry)
        return inquiry

    def purchasing_reject_inquiry(
        self, inquiry_id: str, reason: Optional[str] = None, user_id: Optional[str] = None
    ) -> StockInquiry:
        """Move inquiry from pending_purchasing to rejected."""
        from datetime import datetime, timezone
        inquiry = self.get_inquiry(inquiry_id)
        if inquiry.status != "pending_purchasing":
            from app.services.error_handler import handle_validation_error
            raise handle_validation_error(f"Cannot reject when status is {inquiry.status}. Expected: pending_purchasing.")
        inquiry.status = "rejected"
        inquiry.rejected_from = "pending_purchasing"
        inquiry.rejection_reason = reason
        inquiry.rejected_at = datetime.now(timezone.utc).replace(tzinfo=None)
        inquiry.rejected_by = user_id
        self.db.commit()
        self.db.refresh(inquiry)
        return inquiry

    def reopen_inquiry(
        self, inquiry_id: str, reason: Optional[str] = None, user_id: Optional[str] = None
    ) -> StockInquiry:
        """Move inquiry from rejected back to the state it was rejected from (rejected_from)."""
        from datetime import datetime, timezone
        inquiry = self.get_inquiry(inquiry_id)
        if inquiry.status != "rejected":
            from app.services.error_handler import handle_validation_error
            raise handle_validation_error(f"Cannot reopen when status is {inquiry.status}. Expected: rejected.")
        # Restore to the state before rejection (pending_project_sales or pending_purchasing)
        inquiry.status = inquiry.rejected_from or "pending_project_sales"
        inquiry.reopen_reason = reason
        inquiry.reopened_at = datetime.now(timezone.utc).replace(tzinfo=None)
        inquiry.reopened_by = user_id
        inquiry.rejection_reason = None
        inquiry.rejected_at = None
        inquiry.rejected_by = None
        inquiry.rejected_from = None
        self.db.commit()
        self.db.refresh(inquiry)
        return inquiry


class ProductSupplierService:
    """Service for product supplier operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_product_suppliers(
        self,
        page: int = 1,
        limit: int = 50,
        sort_field: str = "created_at",
        sort_dir: str = "asc",
        product_id: Optional[str] = None,
        supplier_id: Optional[str] = None
    ):
        """List product suppliers with filtering and pagination."""
        from sqlalchemy.orm import joinedload
        
        q = self.db.query(ProductSupplier).options(
            joinedload(ProductSupplier.product),
            joinedload(ProductSupplier.supplier)
        )
        
        if product_id:
            q = q.filter(ProductSupplier.product_id == product_id)
        
        if supplier_id:
            q = q.filter(ProductSupplier.supplier_id == supplier_id)
        
        sort_map = {
            "created_at": ProductSupplier.created_at,
        }
        sort_column = sort_map.get(sort_field, ProductSupplier.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        product_suppliers = q.offset(offset).limit(limit).all()
        
        return {
            "data": product_suppliers,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_product_supplier(self, product_supplier_id: str):
        """Get a product supplier by ID."""
        from sqlalchemy.orm import joinedload
        product_supplier = self.db.query(ProductSupplier).options(
            joinedload(ProductSupplier.product),
            joinedload(ProductSupplier.supplier)
        ).filter(ProductSupplier.id == product_supplier_id).first()
        if not product_supplier:
            raise handle_not_found("Product Supplier", product_supplier_id)
        return product_supplier
    
    def create_product_supplier(self, product_supplier_data: ProductSupplierCreate):
        """Create a new product supplier relationship."""
        # Check if relationship already exists
        existing = self.db.query(ProductSupplier).filter(
            ProductSupplier.product_id == product_supplier_data.product_id,
            ProductSupplier.supplier_id == product_supplier_data.supplier_id
        ).first()
        if existing:
            raise handle_conflict("Product supplier relationship already exists.")
        
        product_supplier = ProductSupplier(**product_supplier_data.model_dump())
        self.db.add(product_supplier)
        self.db.commit()
        self.db.refresh(product_supplier)
        
        # Reload with relationships
        from sqlalchemy.orm import joinedload
        return self.db.query(ProductSupplier).options(
            joinedload(ProductSupplier.product),
            joinedload(ProductSupplier.supplier)
        ).filter(ProductSupplier.id == product_supplier.id).first()
    
    def update_product_supplier(self, product_supplier_id: str, product_supplier_data: ProductSupplierUpdate):
        """Update a product supplier relationship."""
        product_supplier = self.get_product_supplier(product_supplier_id)
        
        update_data = product_supplier_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(product_supplier, key, value)
        
        self.db.commit()
        self.db.refresh(product_supplier)
        
        # Reload with relationships
        from sqlalchemy.orm import joinedload
        return self.db.query(ProductSupplier).options(
            joinedload(ProductSupplier.product),
            joinedload(ProductSupplier.supplier)
        ).filter(ProductSupplier.id == product_supplier.id).first()
    
    def delete_product_supplier(self, product_supplier_id: str):
        """Delete a product supplier relationship."""
        product_supplier = self.get_product_supplier(product_supplier_id)
        self.db.delete(product_supplier)
        self.db.commit()


class PurchaseRequestService:
    """Service for purchase request / sponsorship form operations."""

    def __init__(self, db: Session):
        self.db = db
        from app.services.entity_attachment_service import EntityAttachmentService
        self.entity_attachment_service = EntityAttachmentService(db)

    def _build_respond_inbox_url(self, contact_id: Optional[str], space_id: Optional[str]) -> Optional[str]:
        """Build respond.io inbox URL: {base}/space/{space_id}/inbox/{contact_id}."""
        if not contact_id or not space_id:
            return None
        base = (settings.respond_app_base_url or "").rstrip("/")
        if not base:
            return None
        return f"{base}/space/{space_id.strip()}/inbox/{contact_id.strip()}"

    def _identifier_from_respond_inbox_url(self, respond_inbox_url: Optional[str]) -> Optional[str]:
        """Extract contact identifier from respond_inbox_url (last path segment)."""
        if not respond_inbox_url or not respond_inbox_url.strip():
            return None
        parts = [p for p in respond_inbox_url.rstrip("/").split("/") if p]
        return parts[-1] if parts else None

    def _parse_date(self, value: Optional[str | date | datetime]) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    return datetime.strptime(s, fmt).date()
                except ValueError:
                    continue
        return None

    def create_external_request(self, payload):
        """Create purchase request header + lines from external payload."""
        expected_po_date_text = None
        if isinstance(payload.expected_po_date, str):
            expected_po_date_text = payload.expected_po_date.strip() or None

        # Resolve expected_delivery_date: use date_of_delivery when expected_delivery_date is empty
        expected_delivery_date = self._parse_date(getattr(payload, "expected_delivery_date", None))
        if expected_delivery_date is None:
            expected_delivery_date = self._parse_date(getattr(payload, "date_of_delivery", None))

        # total_project_value: numeric -> column; descriptive text -> total_project_value_text
        raw_tpv = getattr(payload, "total_project_value", None)
        total_project_value = None
        total_project_value_text = None
        if raw_tpv is not None:
            if isinstance(raw_tpv, Decimal):
                total_project_value = raw_tpv
            elif isinstance(raw_tpv, str):
                s = raw_tpv.strip()
                if s:
                    try:
                        total_project_value = Decimal(s)
                    except (InvalidOperation, ValueError):
                        total_project_value_text = s

        contact_id = getattr(payload, "contact_id", None) or None
        space_id = getattr(payload, "space_id", None) or None
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)

        # Generate request_number if not provided
        request_number = getattr(payload, "request_number", None) or None
        if not request_number:
            from app.services.numbering_service import NumberingService
            ref_date = self._parse_date(getattr(payload, "date", None)) or date.today()
            request_number = NumberingService(self.db).get_next_number(payload.request_type, ref_date)

        header = PurchaseRequestHeader(
            request_type=payload.request_type,
            request_number=request_number,
            request_date=self._parse_date(payload.date),
            customer_name=payload.customer_name,
            project_title=payload.project_title,
            purpose=payload.purpose,
            delivery_address=getattr(payload, "delivery_address", None),
            total_project_value=total_project_value,
            total_project_value_text=total_project_value_text,
            sponsor_subject=getattr(payload, "sponsor_subject", None),
            expected_delivery_date=expected_delivery_date,
            expected_po_date=self._parse_date(payload.expected_po_date),
            expected_po_date_text=expected_po_date_text,
            requested_by=payload.requested_by,
            requested_at=self._parse_date(payload.requested_at),
            external_reference=payload.external_reference,
            contact_id=contact_id,
            space_id=space_id,
            respond_inbox_url=respond_inbox_url,
            status="draft",
            source="external",
        )
        self.db.add(header)
        self.db.flush()

        if payload.products:
            for index, line_data in enumerate(payload.products):
                line = PurchaseRequestLine(
                    purchase_request_id=header.id,
                    item_code=line_data.item_code,
                    quantity=line_data.quantity,
                    remark=line_data.remark,
                    unit_price=getattr(line_data, "unit_price", None),
                    total=getattr(line_data, "total", None),
                    sort_order=index,
                )
                self.db.add(line)

        self.db.commit()
        self.db.refresh(header)
        # Capture header fields before any further commits (session may expire objects)
        header_id = str(header.id)
        header_request_type = getattr(header, "request_type", None)
        header_request_number = getattr(header, "request_number", None) or "N/A"
        header_project_title = getattr(header, "project_title", None) or "N/A"
        try:
            self.get_or_create_view_token(header_id)
            self.db.commit()
        except Exception:
            pass
        try:
            base_url_override = getattr(payload, "base_url", None) if payload else None
            self._notify_team_on_external_pr_created(
                header_id=header_id,
                request_type=header_request_type,
                request_number=header_request_number,
                project_title=header_project_title,
                base_url_override=base_url_override,
            )
        except Exception as e:
            logger.warning("Failed to notify team for external purchase request %s: %s", header_id, e)
        return header

    def _get_team_user_ids_for_agent_code(self, agent_code: str) -> List[str]:
        """Return user IDs of all teams assigned to the access agent with the given code.

        Note: AgentTeam.code is an assignment code (e.g. customer_service), not necessarily the access agent code.
        So we resolve the access agent by code, then include all team assignments for that agent.
        """
        from app.services.user_service import AccessAgentService
        from app.models.access import AgentTeam, TeamMember

        agent_id = AccessAgentService(self.db).get_agent_id_by_code(agent_code)
        if not agent_id:
            logger.debug("No access agent found for code=%s", agent_code)
            return []

        rows = (
            self.db.query(TeamMember.user_id)
            .join(AgentTeam, AgentTeam.team_id == TeamMember.team_id)
            .filter(AgentTeam.agent_id == agent_id)
            .distinct()
            .all()
        )
        return [str(r[0]) for r in rows if r and r[0]]

    def _get_team_user_ids_for_agent_team_assignment_pr(
        self, agent_code: str, team_assignment_code: str
    ) -> List[str]:
        """Return user IDs of the team assigned to the agent with the given team assignment code (e.g. project_sales)."""
        from app.services.user_service import AccessAgentService
        from app.models.access import TeamMember

        agent_svc = AccessAgentService(self.db)
        agent_id = agent_svc.get_agent_id_by_code(agent_code)
        if not agent_id:
            logger.debug("No access agent found for code=%s", agent_code)
            return []
        team_id = agent_svc.get_team_id_by_code(agent_id, team_assignment_code)
        if not team_id:
            logger.debug(
                "No team assignment found for agent %s with code=%s",
                agent_code,
                team_assignment_code,
            )
            return []
        rows = self.db.query(TeamMember.user_id).filter(TeamMember.team_id == team_id).all()
        return [str(r[0]) for r in rows if r and r[0]]

    def _notify_team_on_external_pr_created(
        self,
        header_id: str,
        request_type: Optional[str] = None,
        request_number: str = "N/A",
        project_title: str = "N/A",
        base_url_override: Optional[str] = None,
        sync_email: bool = False,
    ) -> None:
        """Notify tier 1 team under agent purchase_request (fallback project_sales): one email to all, plus in-app for each. Email is enqueued by default so API returns quickly."""
        from app.models.user import User, SystemSetting
        from app.models.notification import Notification, NotificationDelivery
        from app.services.notification_service import NotificationService
        from datetime import datetime

        user_ids = (
            self._get_team_user_ids_for_agent_tier("purchase_request", 1)
            or self._get_team_user_ids_for_agent_team_assignment_pr("purchase_request", "project_sales")
        )
        if not user_ids:
            logger.warning(
                "No team members found for agent 'purchase_request' with Tier 1 or 'project_sales'. "
                "Create an Access Agent with code 'purchase_request' and a Team Assignment with Tier = 1 (or code 'project_sales')."
            )
            return
        users = self.db.query(User).filter(User.id.in_(user_ids)).all()
        emails = [u.email for u in users if getattr(u, "email", None) and str(u.email).strip()]
        if not emails:
            logger.warning("Team members for purchase_request (Tier 1 / project_sales) have no email addresses; skipping email.")
        type_label = "Purchase Request" if request_type == "purchase_request" else "Sponsorship Form"
        title = f"New {type_label} created"
        view_token = self.get_or_create_view_token(header_id)
        base_url = (base_url_override or "").strip().rstrip("/")
        if not base_url:
            base_url = (settings.frontend_base_url or "").strip().rstrip("/")
        if not base_url:
            sys_settings = self.db.query(SystemSetting).first()
            if sys_settings and getattr(sys_settings, "website_url", None):
                base_url = (sys_settings.website_url or "").strip().rstrip("/")
        if not base_url:
            logger.warning(
                "No app domain for notification email link. Set Website URL in User Management > Settings (General), "
                "or FRONTEND_BASE_URL in backend .env, or pass base_url in the external create payload."
            )
        view_url = f"{base_url}/view/request?token={view_token}" if base_url else f"/view/request?token={view_token}"
        intro_plain = (
            "Dear Project Sales Team,\n\n"
            f"A new {type_label.lower()} has been created via system integration and requires your review."
        )
        intro_html = (
            f"Dear Project Sales Team,<br /><br />"
            f"A new {type_label.lower()} has been created via system integration and requires your review."
        )
        body_plain = (
            f"{intro_plain}\n\n"
            f"{view_url}\n\n"
            "This is a system generated email. Please do not reply."
        )
        body_html = (
            f"<p>{intro_html}</p>\n"
            f'<p><a href="{view_url}">{view_url}</a></p>\n'
            "<p>This is a system generated email. Please do not reply.</p>"
        )
        notif_svc = NotificationService(self.db)
        first_uid = user_ids[0]
        if emails:
            notification = Notification(
                user_id=first_uid,
                type="purchase_request_created",
                title=title,
                body=body_plain,
                data={"recipient_emails": emails, "single_email_to_all": True, "body_html": body_html},
                source_entity_type="purchase_request",
                source_entity_id=header_id,
                event_type="external_created",
            )
            self.db.add(notification)
            self.db.flush()
            self.db.add(NotificationDelivery(notification_id=notification.id, channel="in_app", status="sent", sent_at=datetime.utcnow()))
            self.db.add(NotificationDelivery(notification_id=notification.id, channel="email", status="pending"))
            self.db.commit()
            self.db.refresh(notification)
            try:
                if sync_email:
                    from app.tasks import notification_tasks
                    notification_tasks.send_notification_deliveries(str(notification.id))
                else:
                    from app.services.queue_service import enqueue_job
                    from app.tasks import notification_tasks
                    enqueue_job(notification_tasks.send_notification_deliveries, str(notification.id), queue_name="notifications")
            except Exception as e:
                logger.warning("Failed to send/enqueue notification deliveries: %s", e)
        for uid in user_ids:
            if uid == first_uid and emails:
                continue
            try:
                notif_svc.create_in_app_only(
                    user_id=uid,
                    type="purchase_request_created",
                    title=title,
                    body=body_plain,
                    source_entity_type="purchase_request",
                    source_entity_id=header_id,
                    event_type="external_created",
                )
            except Exception as e:
                logger.warning("Failed to create in-app notification for user %s: %s", uid, e)
        logger.info("Notifying %s team member(s) for external PR/sponsorship created: %s (1 email to all)", len(user_ids), header_id)

    def _notify_requester_on_approved(self, header: PurchaseRequestHeader) -> None:
        """Notify the user who requested approval when the purchase request / sponsorship form is approved."""
        requested_by_uid = getattr(header, "requested_approval_by_user_id", None)
        if not requested_by_uid:
            return
        type_label = "Purchase Request" if getattr(header, "request_type", None) == "purchase_request" else "Sponsorship Form"
        form_number = getattr(header, "request_number", None) or "N/A"
        project = getattr(header, "project_title", None) or "N/A"
        title = f"{type_label} approved"
        body = f"{type_label} {form_number} (Project: {project}) has been approved."

        view_token = self.get_or_create_view_token(str(header.id))
        base_url = (settings.frontend_base_url or "").strip().rstrip("/")
        if not base_url:
            from app.models.user import SystemSetting
            sys_settings = self.db.query(SystemSetting).first()
            if sys_settings and getattr(sys_settings, "website_url", None):
                base_url = (sys_settings.website_url or "").strip().rstrip("/")
        view_url = f"{base_url}/view/request?token={view_token}" if base_url else f"/view/request?token={view_token}"
        body += f"\n\nView form: {view_url}"
        body_html = (
            f"<p>{type_label} {form_number} (Project: {project}) has been approved.</p>\n"
            f'<p><a href="{view_url}">View form</a><br />{view_url}</p>'
        )

        from app.services.notification_service import NotificationService
        NotificationService(self.db).create(
            user_id=str(requested_by_uid),
            type="purchase_request_approved",
            title=title,
            body=body,
            data={"body_html": body_html},
            source_entity_type="purchase_request",
            source_entity_id=str(header.id),
            event_type="approved",
        )

    def _notify_requester_on_rejected(self, header: PurchaseRequestHeader) -> None:
        """Notify the user who requested approval when the purchase request / sponsorship form is rejected."""
        requested_by_uid = getattr(header, "requested_approval_by_user_id", None)
        if not requested_by_uid:
            return
        type_label = "Purchase Request" if getattr(header, "request_type", None) == "purchase_request" else "Sponsorship Form"
        form_number = getattr(header, "request_number", None) or "N/A"
        project = getattr(header, "project_title", None) or "N/A"
        title = f"{type_label} rejected"
        body = f"{type_label} {form_number} (Project: {project}) has been rejected."

        view_token = self.get_or_create_view_token(str(header.id))
        base_url = (settings.frontend_base_url or "").strip().rstrip("/")
        if not base_url:
            from app.models.user import SystemSetting
            sys_settings = self.db.query(SystemSetting).first()
            if sys_settings and getattr(sys_settings, "website_url", None):
                base_url = (sys_settings.website_url or "").strip().rstrip("/")
        view_url = f"{base_url}/view/request?token={view_token}" if base_url else f"/view/request?token={view_token}"
        body += f"\n\nView form: {view_url}"
        body_html = (
            f"<p>{type_label} {form_number} (Project: {project}) has been rejected.</p>\n"
            f'<p><a href="{view_url}">View form</a><br />{view_url}</p>'
        )

        from app.services.notification_service import NotificationService
        NotificationService(self.db).create(
            user_id=str(requested_by_uid),
            type="purchase_request_rejected",
            title=title,
            body=body,
            data={"body_html": body_html},
            source_entity_type="purchase_request",
            source_entity_id=str(header.id),
            event_type="rejected",
        )

    def list_requests(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        request_type: Optional[str] = None,
        approval_status: Optional[str] = None,
        sort_field: str = "request_date",
        sort_dir: str = "desc",
    ):
        """List purchase requests / sponsorship forms with pagination."""
        from sqlalchemy.orm import joinedload

        q = self.db.query(PurchaseRequestHeader)
        if query:
            q = q.filter(
                or_(
                    PurchaseRequestHeader.customer_name.ilike(f"%{query}%"),
                    PurchaseRequestHeader.project_title.ilike(f"%{query}%"),
                    PurchaseRequestHeader.purpose.ilike(f"%{query}%"),
                    PurchaseRequestHeader.requested_by.ilike(f"%{query}%"),
                    PurchaseRequestHeader.request_number.ilike(f"%{query}%"),
                )
            )
        if request_type and request_type.strip() in ("purchase_request", "sponsorship_form"):
            q = q.filter(PurchaseRequestHeader.request_type == request_type.strip())
        if approval_status and approval_status.strip():
            status_val = approval_status.strip().lower()
            if status_val == "draft":
                q = q.filter(
                    or_(
                        PurchaseRequestHeader.approval_status.is_(None),
                        PurchaseRequestHeader.approval_status == "",
                    )
                )
            elif status_val in ("pending", "approved", "rejected"):
                q = q.filter(PurchaseRequestHeader.approval_status == status_val)

        sort_map = {
            "request_date": PurchaseRequestHeader.request_date,
            "created_at": PurchaseRequestHeader.created_at,
            "customer_name": PurchaseRequestHeader.customer_name,
            "project_title": PurchaseRequestHeader.project_title,
        }
        sort_col = sort_map.get(sort_field, PurchaseRequestHeader.request_date)
        if sort_dir == "desc":
            q = q.order_by(sort_col.desc().nullslast())
        else:
            q = q.order_by(sort_col.asc().nullsfirst())

        total = q.count()
        offset = (page - 1) * limit
        items = q.offset(offset).limit(limit).all()
        return {
            "data": items,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }

    def get_request(self, request_id: str):
        """Get a purchase request by ID with lines."""
        from sqlalchemy.orm import joinedload

        header = (
            self.db.query(PurchaseRequestHeader)
            .options(joinedload(PurchaseRequestHeader.lines))
            .filter(PurchaseRequestHeader.id == request_id)
            .first()
        )
        if not header:
            raise handle_not_found("Purchase request", request_id)
        return header

    def get_neighbour_ids(
        self, request_id: str, request_type: Optional[str] = None
    ) -> dict:
        """Return prev_id and next_id for the given request (order: request_date desc, same as list)."""
        header = self.get_request(request_id)
        q = self.db.query(PurchaseRequestHeader.id).order_by(
            PurchaseRequestHeader.request_date.desc().nullslast(),
            PurchaseRequestHeader.id.desc(),
        )
        if request_type and request_type.strip() in ("purchase_request", "sponsorship_form"):
            q = q.filter(PurchaseRequestHeader.request_type == request_type.strip())
        ids = [r[0] for r in q.all()]
        try:
            idx = ids.index(header.id)
        except ValueError:
            return {"prev_id": None, "next_id": None, "total_count": 0, "current_index": 0}
        prev_id = ids[idx - 1] if idx > 0 else None
        next_id = ids[idx + 1] if idx < len(ids) - 1 else None
        return {
            "prev_id": prev_id,
            "next_id": next_id,
            "total_count": len(ids),
            "current_index": idx + 1,
        }

    def create_request(self, data: PurchaseRequestHeaderCreate):
        """Create purchase request header + lines (internal API)."""
        dump = data.model_dump(exclude={"products"})
        dump["status"] = "draft"
        dump["source"] = "manual"
        if not dump.get("request_number"):
            from app.services.numbering_service import NumberingService
            ref_date = dump.get("request_date") or date.today()
            if isinstance(ref_date, datetime):
                ref_date = ref_date.date() if hasattr(ref_date, "date") else ref_date
            number = NumberingService(self.db).get_next_number(dump["request_type"], ref_date)
            if number:
                dump["request_number"] = number
        contact_id = dump.get("contact_id")
        space_id = dump.get("space_id")
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)
        if respond_inbox_url is not None:
            dump["respond_inbox_url"] = respond_inbox_url
        header = PurchaseRequestHeader(**{k: v for k, v in dump.items() if hasattr(PurchaseRequestHeader, k)})
        self.db.add(header)
        self.db.flush()

        for index, line_data in enumerate(data.products or []):
            line = PurchaseRequestLine(
                purchase_request_id=header.id,
                item_code=line_data.item_code,
                quantity=line_data.quantity,
                remark=line_data.remark,
                unit_price=getattr(line_data, "unit_price", None),
                total=getattr(line_data, "total", None),
                sort_order=index,
            )
            self.db.add(line)

        self.db.commit()
        self.db.refresh(header)
        try:
            self.get_or_create_view_token(str(header.id))
            self.db.commit()
        except Exception:
            pass
        return header

    def update_request(self, request_id: str, data: PurchaseRequestHeaderUpdate):
        """Update purchase request header and optionally replace lines."""
        header = self.get_request(request_id)
        payload = data.model_dump(exclude_unset=True, exclude={"products"})
        contact_id = payload.get("contact_id") if "contact_id" in payload else header.contact_id
        space_id = payload.get("space_id") if "space_id" in payload else header.space_id
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)
        if respond_inbox_url is not None:
            payload["respond_inbox_url"] = respond_inbox_url
        elif contact_id is None and space_id is None:
            payload["respond_inbox_url"] = None
        for key, value in payload.items():
            if hasattr(header, key):
                setattr(header, key, value)

        if data.products is not None:
            for line in list(header.lines or []):
                self.db.delete(line)
            self.db.flush()
            for index, line_data in enumerate(data.products):
                line = PurchaseRequestLine(
                    purchase_request_id=header.id,
                    item_code=line_data.item_code,
                    quantity=line_data.quantity,
                    remark=line_data.remark,
                    unit_price=getattr(line_data, "unit_price", None),
                    total=getattr(line_data, "total", None),
                    sort_order=index,
                )
                self.db.add(line)

        self.db.commit()
        self.db.refresh(header)
        return header

    def update_request_and_reply(
        self,
        request_id: str,
        data: PurchaseRequestUpdateAndReply,
        respond_user_id: str,
        request_url: str = "",
    ):
        """
        Update purchase request (e.g. request_number), then send a reply to the conversation via Respond.io.
        Message is reply_message if provided, otherwise built from request_number.
        """
        import logging
        from app.services.integration_service import RespondClient, IntegrationLogService
        from app.schemas.integration import IntegrationLogCreate
        from app.services.error_handler import handle_validation_error

        logger = logging.getLogger(__name__)
        log_service = IntegrationLogService(self.db)

        header = self.get_request(request_id)
        payload = data.model_dump(exclude_unset=True, exclude={"products", "reply_message"})
        contact_id = payload.get("contact_id") if "contact_id" in payload else header.contact_id
        space_id = payload.get("space_id") if "space_id" in payload else header.space_id
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)
        if respond_inbox_url is not None:
            payload["respond_inbox_url"] = respond_inbox_url
        elif contact_id is None and space_id is None:
            payload["respond_inbox_url"] = None

        for key, value in payload.items():
            if hasattr(header, key):
                setattr(header, key, value)

        if data.products is not None:
            for line in list(header.lines or []):
                self.db.delete(line)
            self.db.flush()
            for index, line_data in enumerate(data.products):
                line = PurchaseRequestLine(
                    purchase_request_id=header.id,
                    item_code=line_data.item_code,
                    quantity=line_data.quantity,
                    remark=line_data.remark,
                    unit_price=getattr(line_data, "unit_price", None),
                    total=getattr(line_data, "total", None),
                    sort_order=index,
                )
                self.db.add(line)

        self.db.flush()
        self.db.refresh(header)

        reply_message = (getattr(data, "reply_message", None) or "").strip()
        request_number = getattr(header, "request_number", None) or payload.get("request_number")
        if request_number is not None and isinstance(request_number, str):
            request_number = request_number.strip() or None
        if not reply_message and request_number:
            reply_message = f"Your request has been assigned form number: {request_number}."
        if not reply_message:
            raise handle_validation_error(
                "Provide reply_message or request_number so we can reply to the conversation."
            )

        identifier = self._identifier_from_respond_inbox_url(getattr(header, "respond_inbox_url", None))
        if not identifier:
            raise handle_validation_error(
                "respond_inbox_url is missing or invalid; cannot send message. Set contact_id and space_id."
            )

        display_message = reply_message
        try:
            client = RespondClient()
            response = client.send_message(identifier, display_message)
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="purchase_requests",
                    business_id=request_id,
                    external_reference=identifier,
                    direction="outbound",
                    endpoint="https://api.respond.io/v2/contact/id:{}/message".format(identifier),
                    http_method="POST",
                    status="success",
                    response_payload=str(response)[:50000] if response else None,
                ),
                request_payload_dict={"message": {"type": "text", "text": display_message}},
            )
        except Exception as e:
            logger.exception("Respond.io send_message failed for purchase_request %s", request_id)
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="purchase_requests",
                    business_id=request_id,
                    external_reference=identifier or "",
                    direction="outbound",
                    endpoint="https://api.respond.io/v2/contact/id:{}/message".format(identifier or ""),
                    http_method="POST",
                    status="failed",
                    error_message=str(e),
                ),
                request_payload_dict={"message": {"type": "text", "text": display_message}},
            )
            raise

        self.db.commit()
        self.db.refresh(header)
        return header

    def delete_request(self, request_id: str) -> None:
        """Delete a purchase request and its lines."""
        header = self.get_request(request_id)
        self.entity_attachment_service.delete_links_for_entity("purchase_request", str(header.id))
        self.db.delete(header)
        self.db.commit()

    def link_attachment_to_request(
        self, request_id: str, attachment_id: str, created_by: Optional[str] = None
    ):
        """Link an existing attachment to a purchase request (generic entity_attachment_links table)."""
        self.get_request(request_id)  # ensure request exists
        link = self.entity_attachment_service.link_existing_attachment(
            entity_type="purchase_request",
            entity_id=str(request_id),
            attachment_id=str(attachment_id),
            created_by=created_by,
        )
        self.db.commit()
        self.db.refresh(link)
        return link

    def delete_request_attachment(self, link_id: str) -> None:
        """Delete a purchase-request attachment link from generic entity_attachment_links table."""
        self.entity_attachment_service.delete_link(link_id, entity_type="purchase_request")
        self.db.commit()

    def bulk_delete_requests(self, request_ids: List[str]) -> dict:
        """Delete multiple purchase requests / sponsorship forms by ID. Returns deleted_count."""
        if not request_ids:
            return {"message": "No records to delete", "deleted_count": 0}
        headers = (
            self.db.query(PurchaseRequestHeader)
            .filter(PurchaseRequestHeader.id.in_(request_ids))
            .all()
        )
        for header in headers:
            self.entity_attachment_service.delete_links_for_entity("purchase_request", str(header.id))
            self.db.delete(header)
        self.db.commit()
        return {"message": f"Deleted {len(headers)} record(s)", "deleted_count": len(headers)}

    def set_pending_approval(self, request_id: str, requested_by_user_id: Optional[str] = None):
        """Set request to pending approval (clears approval fields if previously approved/rejected). Returns updated header."""
        header = self.get_request(request_id)
        header.approval_status = "pending"
        header.approved_at = None
        header.approved_by = None
        header.approval_signature_ref = None
        header.approval_comments = None
        if requested_by_user_id is not None:
            header.requested_approval_by_user_id = requested_by_user_id
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise
        # Re-query with relationships loaded to avoid expired instance issues
        return self.get_request(request_id)

    def create_approval_token(
        self,
        request_id: str,
        approver_email: Optional[str] = None,
        approver_user_id: Optional[str] = None,
        requested_by_user_id: Optional[str] = None,
        expires_hours: int = 24,
        base_url: str = "",
    ) -> tuple[ApprovalToken, str]:
        """Create one-time approval token for a purchase request. Returns (token row, approval_url)."""
        from app.models.user import User

        header = self.get_request(request_id)
        if approver_user_id:
            header.approver_user_id = approver_user_id
            user = self.db.query(User).filter(User.id == approver_user_id).first()
            if user:
                header.approver_email = approver_email or user.email or header.approver_email
            elif approver_email:
                header.approver_email = approver_email
        else:
            header.approver_user_id = None
            if approver_email:
                header.approver_email = approver_email
        if requested_by_user_id is not None:
            header.requested_approval_by_user_id = requested_by_user_id
        # When resending after approved/rejected, clear previous approval so request is back in "pending approval"
        if header.approval_status in ("approved", "rejected"):
            header.approved_at = None
            header.approved_by = None
            header.approval_signature_ref = None
            header.approval_comments = None
        header.approval_status = "pending"
        self.db.flush()

        token_value = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(hours=expires_hours)
        approval_token = ApprovalToken(
            entity_type="purchase_request",
            entity_id=request_id,
            token=token_value,
            expires=expires,
        )
        self.db.add(approval_token)
        self.db.commit()
        self.db.refresh(approval_token)

        approval_url = f"{base_url.rstrip('/')}/approval?token={token_value}" if base_url else f"/approval?token={token_value}"
        return approval_token, approval_url

    def get_approval_summary_by_token(self, token_value: str):
        """Validate token and return request summary for public approval page. Raises if invalid/expired/used."""
        approval_token = (
            self.db.query(ApprovalToken)
            .filter(ApprovalToken.token == token_value)
            .first()
        )
        if not approval_token:
            raise handle_not_found("Approval link", "(invalid token)")
        if approval_token.used_at is not None:
            raise handle_conflict("This approval link has already been used.")
        now = datetime.utcnow()
        if approval_token.expires <= now:
            raise handle_conflict("This approval link has expired.")
        header = self.get_request(approval_token.entity_id)
        lines = []
        grand_total = None
        if getattr(header, "lines", None):
            for line in sorted(header.lines, key=lambda l: (l.sort_order if l.sort_order is not None else 999, getattr(l, "id", 0))):
                qty = line.quantity
                if qty is not None and hasattr(qty, "__float__"):
                    try:
                        qty = float(qty)
                    except (TypeError, ValueError):
                        pass
                up = getattr(line, "unit_price", None)
                tot = getattr(line, "total", None)
                if up is not None and hasattr(up, "__float__"):
                    try:
                        up = float(up)
                    except (TypeError, ValueError):
                        up = None
                if tot is not None and hasattr(tot, "__float__"):
                    try:
                        tot = float(tot)
                    except (TypeError, ValueError):
                        tot = None
                lines.append({
                    "item_code": line.item_code,
                    "quantity": qty,
                    "remark": line.remark,
                    "unit_price": up,
                    "total": tot,
                    "sort_order": line.sort_order,
                })
            if getattr(header, "request_type", None) == "sponsorship_form" and lines:
                try:
                    total_sum = Decimal("0")
                    for l in lines:
                        t = l.get("total")
                        if t is not None:
                            total_sum += Decimal(str(t))
                        else:
                            q, u = l.get("quantity"), l.get("unit_price")
                            if q is not None and u is not None:
                                total_sum += Decimal(str(q)) * Decimal(str(u))
                    grand_total = total_sum
                except (InvalidOperation, ValueError, TypeError):
                    grand_total = None
        approver_display_name = None
        approver_email = getattr(header, "approver_email", None) or None
        approver_user_id = getattr(header, "approver_user_id", None)
        if approver_user_id:
            user = self.db.query(User).filter(User.id == approver_user_id).first()
            if user:
                approver_display_name = (user.name and user.name.strip()) or user.email or None
                if not approver_email and user.email:
                    approver_email = user.email

        return {
            "entity_type": approval_token.entity_type,
            "entity_id": approval_token.entity_id,
            "request_number": header.request_number,
            "request_type": header.request_type,
            "customer_name": header.customer_name,
            "project_title": header.project_title,
            "purpose": header.purpose,
            "delivery_address": getattr(header, "delivery_address", None),
            "total_project_value": getattr(header, "total_project_value", None),
            "total_project_value_text": getattr(header, "total_project_value_text", None),
            "sponsor_subject": getattr(header, "sponsor_subject", None),
            "requested_by": header.requested_by,
            "request_date": getattr(header, "request_date", None),
            "created_at": getattr(header, "created_at", None),
            "expected_delivery_date": getattr(header, "expected_delivery_date", None),
            "expected_po_date": getattr(header, "expected_po_date", None),
            "expected_po_date_text": getattr(header, "expected_po_date_text", None),
            "expires_at": approval_token.expires,
            "lines": lines,
            "grand_total": grand_total,
            "approval_status": getattr(header, "approval_status", None),
            "approver_display_name": approver_display_name,
            "approver_email": approver_email,
        }

    def get_or_create_view_token(self, entity_id: str) -> str:
        """Get or create a reusable view token for this purchase request. Returns the token string."""
        row = (
            self.db.query(ViewToken)
            .filter(
                ViewToken.entity_type == "purchase_request",
                ViewToken.entity_id == entity_id,
            )
            .first()
        )
        if row:
            return row.token
        token_value = secrets.token_urlsafe(32)
        view_token = ViewToken(
            entity_type="purchase_request",
            entity_id=entity_id,
            token=token_value,
        )
        self.db.add(view_token)
        self.db.flush()
        return token_value

    def get_view_summary_by_token(self, token_value: str) -> dict:
        """Return read-only request summary for the given view token. No auth required.
        If the token is not a view token, also try approval token so approval links can be used to view."""
        view_token = (
            self.db.query(ViewToken)
            .filter(ViewToken.token == token_value)
            .first()
        )
        entity_id = None
        if view_token:
            entity_id = str(view_token.entity_id) if view_token.entity_id else None
        if not entity_id:
            approval_token = (
                self.db.query(ApprovalToken)
                .filter(ApprovalToken.token == token_value)
                .first()
            )
            if approval_token:
                entity_id = str(approval_token.entity_id) if approval_token.entity_id else None
        if not entity_id:
            raise handle_not_found("View link", "(invalid token)")
        header = self.get_request(entity_id)
        lines = []
        grand_total = None
        if getattr(header, "lines", None):
            for line in sorted(header.lines, key=lambda l: (l.sort_order if l.sort_order is not None else 999, getattr(l, "id", 0))):
                qty = line.quantity
                if qty is not None and hasattr(qty, "__float__"):
                    try:
                        qty = float(qty)
                    except (TypeError, ValueError):
                        pass
                up = getattr(line, "unit_price", None)
                tot = getattr(line, "total", None)
                if up is not None and hasattr(up, "__float__"):
                    try:
                        up = float(up)
                    except (TypeError, ValueError):
                        up = None
                if tot is not None and hasattr(tot, "__float__"):
                    try:
                        tot = float(tot)
                    except (TypeError, ValueError):
                        tot = None
                lines.append({
                    "item_code": line.item_code,
                    "quantity": qty,
                    "remark": line.remark,
                    "unit_price": up,
                    "total": tot,
                    "sort_order": line.sort_order,
                })
            if getattr(header, "request_type", None) == "sponsorship_form" and lines:
                try:
                    total_sum = Decimal("0")
                    for l in lines:
                        t = l.get("total")
                        if t is not None:
                            total_sum += Decimal(str(t))
                        else:
                            q, u = l.get("quantity"), l.get("unit_price")
                            if q is not None and u is not None:
                                total_sum += Decimal(str(q)) * Decimal(str(u))
                    grand_total = total_sum
                except (InvalidOperation, ValueError, TypeError):
                    grand_total = None
        entity_type = view_token.entity_type if view_token else "purchase_request"
        return {
            "entity_type": entity_type,
            "entity_id": header.id,
            "request_number": header.request_number,
            "request_type": header.request_type,
            "customer_name": header.customer_name,
            "project_title": header.project_title,
            "purpose": header.purpose,
            "delivery_address": getattr(header, "delivery_address", None),
            "total_project_value": getattr(header, "total_project_value", None),
            "total_project_value_text": getattr(header, "total_project_value_text", None),
            "sponsor_subject": getattr(header, "sponsor_subject", None),
            "requested_by": header.requested_by,
            "request_date": getattr(header, "request_date", None),
            "created_at": getattr(header, "created_at", None),
            "expected_delivery_date": getattr(header, "expected_delivery_date", None),
            "expected_po_date": getattr(header, "expected_po_date", None),
            "expected_po_date_text": getattr(header, "expected_po_date_text", None),
            "expires_at": None,
            "lines": lines,
            "grand_total": grand_total,
            "approval_status": getattr(header, "approval_status", None),
        }

    def submit_approval(
        self,
        token_value: str,
        action: str,
        approved_by: Optional[str] = None,
        approval_signature_ref: Optional[str] = None,
        approval_comments: Optional[str] = None,
    ):
        """Consume token and update purchase request with approval/rejection. Returns updated header."""
        approval_token = (
            self.db.query(ApprovalToken)
            .filter(ApprovalToken.token == token_value)
            .first()
        )
        if not approval_token:
            raise handle_not_found("Approval link", "(invalid token)")
        if approval_token.used_at is not None:
            raise handle_conflict("This approval link has already been used.")
        now = datetime.now(timezone.utc)
        if approval_token.expires.tzinfo is None:
            now = datetime.now()
        if approval_token.expires <= now:
            raise handle_conflict("This approval link has expired.")
        if action not in ("approved", "rejected"):
            raise handle_conflict("action must be 'approved' or 'rejected'.")

        header = self.get_request(approval_token.entity_id)
        approval_token.used_at = datetime.utcnow()
        header.approval_status = action
        header.approved_at = now
        header.approved_by = approved_by or header.approver_email or ""
        header.approval_signature_ref = approval_signature_ref
        header.approval_comments = approval_comments
        self.db.commit()
        self.db.refresh(header)
        if action == "approved":
            requested_by_uid = getattr(header, "requested_approval_by_user_id", None)
            if requested_by_uid:
                try:
                    self._notify_requester_on_approved(header)
                except Exception as e:
                    logger.warning("Failed to notify requester for approved purchase request %s: %s", header.id, e)
        elif action == "rejected":
            requested_by_uid = getattr(header, "requested_approval_by_user_id", None)
            if requested_by_uid:
                try:
                    self._notify_requester_on_rejected(header)
                except Exception as e:
                    logger.warning("Failed to notify requester for rejected purchase request %s: %s", header.id, e)
        return header
