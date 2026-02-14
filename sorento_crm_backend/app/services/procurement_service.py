"""Procurement service for business logic."""
import secrets
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import Optional
from datetime import date, datetime, timedelta, timezone
from app.models.procurement import (
    Supplier, ProductSupplier, InboundShipment, InboundShipmentLine, SPOAllocation,
    PickingHeader, PickingLine, StockInquiry, PurchaseRequestHeader, PurchaseRequestLine,
    ApprovalToken,
)
from app.models.product import Product
from app.models.resources import Attachment
from app.schemas.procurement import (
    SupplierCreate, SupplierUpdate, ProductSupplierCreate, ProductSupplierUpdate,
    InboundShipmentCreate, InboundShipmentUpdate,
    SPOAllocationCreate, SPOAllocationUpdate, PickingHeaderCreate, PickingHeaderUpdate,
    StockInquiryCreate, StockInquiryUpdate,
    PurchaseRequestHeaderCreate, PurchaseRequestHeaderUpdate,
)
from app.services.error_handler import handle_not_found, handle_conflict
from app.config import settings


class SupplierService:
    """Service for supplier operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_suppliers(self, page: int = 1, limit: int = 50, query: Optional[str] = None, sort_field: str = "created_at", sort_dir: str = "asc"):
        """List suppliers."""
        q = self.db.query(Supplier)
        
        if query:
            q = q.filter(
                or_(
                    Supplier.supplier_code.ilike(f"%{query}%"),
                    Supplier.supplier_name.ilike(f"%{query}%")
                )
            )
        
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
        
        # Create lines if provided
        if shipment_data.shipment_lines:
            for line_data in shipment_data.shipment_lines:
                line = InboundShipmentLine(**line_data.model_dump(), shipment_id=shipment.id)
                self.db.add(line)
        
        self.db.commit()
        self.db.refresh(shipment)
        return shipment
    
    def update_shipment(self, shipment_id: str, shipment_data: InboundShipmentUpdate, updated_by: str):
        """Update an inbound shipment."""
        shipment = self.get_shipment(shipment_id)
        
        update_data = shipment_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(shipment, key, value)
        
        self.db.commit()
        self.db.refresh(shipment)
        return shipment

    def delete_shipment(self, shipment_id: str) -> None:
        """Delete an inbound shipment. Lines and SPO allocations cascade via DB."""
        shipment = self.get_shipment(shipment_id)
        self.db.delete(shipment)
        self.db.commit()


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
        """List SPO allocations."""
        from sqlalchemy.orm import joinedload
        q = self.db.query(SPOAllocation).options(
            joinedload(SPOAllocation.product)
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
        
        return {
            "data": allocations,
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
            shipment_filters.append(
                or_(
                    SPOAllocation.spo_number.ilike(f"%{query}%"),
                    InboundShipment.shipment_number.ilike(f"%{query}%"),
                    SPOAllocation.product.has(Product.product_code.ilike(f"%{query}%")),
                    SPOAllocation.product.has(Product.product_name.ilike(f"%{query}%")),
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

        groups = []
        for ship in shipments_page:
            allocs = by_shipment.get(ship.id, [])
            raw_lines = lines_by_shipment.get(ship.id, [])
            shipment_lines = [
                InboundShipmentLineResponse.model_validate(line) for line in raw_lines
            ]
            groups.append(
                ShipmentWithAllocationsGroup(
                    inbound_shipment=InboundShipmentSimple.model_validate(ship),
                    spo_allocations=[SPOAllocationResponse.model_validate(a) for a in allocs],
                    shipment_lines=shipment_lines if shipment_lines else None,
                )
            )

        return {
            "data": groups,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }

    def get_allocation(self, allocation_id: str):
        """Get an SPO allocation by ID."""
        from sqlalchemy.orm import joinedload
        allocation = self.db.query(SPOAllocation).options(
            joinedload(SPOAllocation.product)
        ).filter(SPOAllocation.id == allocation_id).first()
        if not allocation:
            raise handle_not_found("SPO Allocation", allocation_id)
        return allocation
    
    def create_allocation(self, allocation_data: SPOAllocationCreate, created_by: str):
        """Create a new SPO allocation."""
        # Check unique constraint if both spo_number and spo_line_number are provided
        if allocation_data.spo_number and allocation_data.spo_line_number is not None:
            existing = self.db.query(SPOAllocation).filter(
                SPOAllocation.spo_number == allocation_data.spo_number,
                SPOAllocation.spo_line_number == allocation_data.spo_line_number
            ).first()
            if existing:
                raise handle_conflict("SPO number and line number combination already exists.")
        
        allocation_dict = allocation_data.model_dump()
        allocation_dict["created_by"] = created_by
        allocation = SPOAllocation(**allocation_dict)
        self.db.add(allocation)
        self.db.commit()
        self.db.refresh(allocation)
        return allocation
    
    def update_allocation(self, allocation_id: str, allocation_data: SPOAllocationUpdate):
        """Update an SPO allocation."""
        allocation = self.get_allocation(allocation_id)
        
        update_data = allocation_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(allocation, key, value)
        
        self.db.commit()
        self.db.refresh(allocation)
        return allocation


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
        """List GRNs (picking headers with type 'goods_received')."""
        from sqlalchemy.orm import selectinload
        q = self.db.query(PickingHeader).options(
            selectinload(PickingHeader.picking_lines).joinedload(PickingLine.product)
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
        sort_column = sort_map.get(sort_field, PickingHeader.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        grns = q.offset(offset).limit(limit).all()
        
        return {
            "data": grns,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_grn(self, grn_id: str):
        """Get a GRN by ID."""
        from sqlalchemy.orm import selectinload, joinedload
        grn = self.db.query(PickingHeader).options(
            selectinload(PickingHeader.picking_lines).joinedload(PickingLine.product),
            selectinload(PickingHeader.picking_lines).joinedload(PickingLine.spo_allocation),
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
            grn_dict["picked_by_user_id"] = created_by
        
        grn = PickingHeader(**grn_dict)
        self.db.add(grn)
        self.db.flush()
        
        # Create lines if provided (exclude quantity_discrepancy - DB generated column)
        if grn_data.picking_lines:
            for line_data in grn_data.picking_lines:
                line_dict = line_data.model_dump(exclude={"quantity_discrepancy"}, exclude_none=False)
                line = PickingLine(**line_dict, picking_header_id=grn.id)
                self.db.add(line)
        
        self.db.commit()
        self.db.refresh(grn)
        return grn
    
    def update_grn(self, grn_id: str, grn_data: PickingHeaderUpdate):
        """Update a GRN."""
        grn = self.get_grn(grn_id)
        
        update_data = grn_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(grn, key, value)
        
        self.db.commit()
        self.db.refresh(grn)
        return grn
    
    def delete_grn(self, grn_id: str):
        """Delete a GRN and its lines."""
        grn = self.get_grn(grn_id)
        
        # Explicitly delete picking lines first to avoid foreign key constraint issues
        self.db.query(PickingLine).filter(PickingLine.picking_header_id == grn_id).delete()
        
        # Then delete the header
        self.db.delete(grn)
        self.db.commit()
        return {"message": "GRN deleted successfully"}


class StockInquiryService:
    """Service for stock inquiry operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
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
    
    def _build_respond_inbox_url(self, contact_id: Optional[str], space_id: Optional[str]) -> Optional[str]:
        """Build respond.io inbox URL: {base}/space/{space_id}/inbox/{contact_id}."""
        if not contact_id or not space_id:
            return None
        base = (settings.respond_app_base_url or "").rstrip("/")
        if not base:
            return None
        return f"{base}/space/{space_id.strip()}/inbox/{contact_id.strip()}"

    def create_inquiry(self, inquiry_data: StockInquiryCreate):
        """Create a new stock inquiry."""
        data = inquiry_data.model_dump()
        contact_id = data.get("contact_id")
        space_id = data.get("space_id")
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)
        if respond_inbox_url is not None:
            data["respond_inbox_url"] = respond_inbox_url
        inquiry = StockInquiry(**data)
        self.db.add(inquiry)
        self.db.commit()
        self.db.refresh(inquiry)
        return inquiry

    def _identifier_from_respond_inbox_url(self, respond_inbox_url: Optional[str]) -> Optional[str]:
        """Extract contact identifier from respond_inbox_url (last path segment)."""
        if not respond_inbox_url or not respond_inbox_url.strip():
            return None
        parts = [p for p in respond_inbox_url.rstrip("/").split("/") if p]
        return parts[-1] if parts else None

    def update_inquiry(self, inquiry_id: str, inquiry_data: StockInquiryUpdate):
        """Update a stock inquiry. Sets status to 'updated' when purchasing_response is changed."""
        inquiry = self.get_inquiry(inquiry_id)

        update_data = inquiry_data.model_dump(exclude_unset=True)
        contact_id = update_data.get("contact_id") if "contact_id" in update_data else inquiry.contact_id
        space_id = update_data.get("space_id") if "space_id" in update_data else inquiry.space_id
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)
        if respond_inbox_url is not None:
            update_data["respond_inbox_url"] = respond_inbox_url
        elif contact_id is None and space_id is None:
            update_data["respond_inbox_url"] = None

        if "purchasing_response" in update_data and inquiry.status != "responded":
            update_data["status"] = "updated"

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
        from datetime import datetime, timezone
        from app.services.integration_service import RespondClient, IntegrationLogService
        from app.schemas.integration import IntegrationLogCreate
        from app.services.sla_service import ConversationSLATrackingService
        from app.schemas.sla import ConversationSLATrackingUpdate

        logger = logging.getLogger(__name__)
        log_service = IntegrationLogService(self.db)

        inquiry = self.get_inquiry(inquiry_id)
        update_data = inquiry_data.model_dump(exclude_unset=True)
        contact_id = update_data.get("contact_id") if "contact_id" in update_data else inquiry.contact_id
        space_id = update_data.get("space_id") if "space_id" in update_data else inquiry.space_id
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)
        if respond_inbox_url is not None:
            update_data["respond_inbox_url"] = respond_inbox_url
        elif contact_id is None and space_id is None:
            update_data["respond_inbox_url"] = None

        message_text = update_data.get("purchasing_response") or inquiry.purchasing_response
        if not (message_text and str(message_text).strip()):
            from app.services.error_handler import handle_validation_error
            raise handle_validation_error("purchasing_response is required to reply.")

        for key, value in update_data.items():
            setattr(inquiry, key, value)
        self.db.flush()

        identifier = self._identifier_from_respond_inbox_url(inquiry.respond_inbox_url)
        if not identifier:
            from app.services.error_handler import handle_validation_error
            raise handle_validation_error("respond_inbox_url is missing or invalid; cannot send message.")

        product_code = (inquiry.product_code or "this inquiry").strip()
        response_snippet = str(message_text).strip()[:200]
        display_message = f"Please find your response on stock inquiry on {product_code}. {response_snippet}"
        if len(str(message_text).strip()) > 200:
            display_message += "..."

        try:
            client = RespondClient()
            response = client.send_message(identifier, display_message)
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
                request_payload_dict={"message": {"type": "text", "text": display_message}},
            )
        except Exception as e:
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
                request_payload_dict={"message": {"type": "text", "text": display_message}},
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

    def _build_respond_inbox_url(self, contact_id: Optional[str], space_id: Optional[str]) -> Optional[str]:
        """Build respond.io inbox URL: {base}/space/{space_id}/inbox/{contact_id}."""
        if not contact_id or not space_id:
            return None
        base = (settings.respond_app_base_url or "").rstrip("/")
        if not base:
            return None
        return f"{base}/space/{space_id.strip()}/inbox/{contact_id.strip()}"

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

        contact_id = getattr(payload, "contact_id", None) or None
        space_id = getattr(payload, "space_id", None) or None
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)

        header = PurchaseRequestHeader(
            request_type=payload.request_type,
            request_date=self._parse_date(payload.date),
            customer_name=payload.customer_name,
            project_title=payload.project_title,
            purpose=payload.purpose,
            expected_delivery_date=self._parse_date(payload.expected_delivery_date),
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
                    sort_order=index,
                )
                self.db.add(line)

        self.db.commit()
        self.db.refresh(header)
        return header

    def list_requests(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        request_type: Optional[str] = None,
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
            return {"prev_id": None, "next_id": None}
        prev_id = ids[idx - 1] if idx > 0 else None
        next_id = ids[idx + 1] if idx < len(ids) - 1 else None
        return {"prev_id": prev_id, "next_id": next_id}

    def create_request(self, data: PurchaseRequestHeaderCreate):
        """Create purchase request header + lines (internal API)."""
        dump = data.model_dump(exclude={"products"})
        dump["status"] = "draft"
        dump["source"] = "manual"
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
                sort_order=index,
            )
            self.db.add(line)

        self.db.commit()
        self.db.refresh(header)
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
                    sort_order=index,
                )
                self.db.add(line)

        self.db.commit()
        self.db.refresh(header)
        return header

    def delete_request(self, request_id: str) -> None:
        """Delete a purchase request and its lines."""
        header = self.get_request(request_id)
        self.db.delete(header)
        self.db.commit()

    def set_pending_approval(self, request_id: str):
        """Set request to pending approval (clears approval fields if previously approved/rejected). Returns updated header."""
        header = self.get_request(request_id)
        header.approval_status = "pending"
        header.approved_at = None
        header.approved_by = None
        header.approval_signature_ref = None
        header.approval_comments = None
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
        return {
            "entity_type": approval_token.entity_type,
            "entity_id": approval_token.entity_id,
            "request_number": header.request_number,
            "request_type": header.request_type,
            "customer_name": header.customer_name,
            "project_title": header.project_title,
            "purpose": header.purpose,
            "requested_by": header.requested_by,
            "expires_at": approval_token.expires,
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
        return header
