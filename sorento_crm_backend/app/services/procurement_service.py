"""Procurement service for business logic."""
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import Optional
from datetime import date, datetime
from app.models.procurement import (
    Supplier, ProductSupplier, InboundShipment, InboundShipmentLine, SPOAllocation,
    PickingHeader, PickingLine, StockInquiry
)
from app.models.product import Product
from app.models.resources import Attachment
from app.schemas.procurement import (
    SupplierCreate, SupplierUpdate, ProductSupplierCreate, ProductSupplierUpdate,
    InboundShipmentCreate, InboundShipmentUpdate,
    SPOAllocationCreate, SPOAllocationUpdate, PickingHeaderCreate, PickingHeaderUpdate,
    StockInquiryCreate, StockInquiryUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict


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
        shipments = q.offset(offset).limit(limit).all()
        
        return {
            "data": shipments,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_shipment(self, shipment_id: str):
        """Get a shipment by ID."""
        from sqlalchemy.orm import joinedload
        shipment = self.db.query(InboundShipment).options(
            joinedload(InboundShipment.attachment).joinedload(Attachment.attachment_type)
        ).filter(InboundShipment.id == shipment_id).first()
        if not shipment:
            raise handle_not_found("Inbound Shipment", shipment_id)
        return shipment
    
    def create_shipment(self, shipment_data: InboundShipmentCreate, created_by: str):
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
        q = self.db.query(SPOAllocation)
        
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
    
    def get_allocation(self, allocation_id: str):
        """Get an SPO allocation by ID."""
        allocation = self.db.query(SPOAllocation).filter(SPOAllocation.id == allocation_id).first()
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
        q = self.db.query(PickingHeader).filter(PickingHeader.picking_type == "goods_received")
        
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
        grn = self.db.query(PickingHeader).filter(
            PickingHeader.id == grn_id,
            PickingHeader.picking_type == "goods_received"
        ).first()
        if not grn:
            raise handle_not_found("GRN", grn_id)
        return grn
    
    def create_grn(self, grn_data: PickingHeaderCreate, created_by: str):
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
        
        # Create lines if provided
        if grn_data.picking_lines:
            for line_data in grn_data.picking_lines:
                line = PickingLine(**line_data.model_dump(), picking_header_id=grn.id)
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
    
    def create_inquiry(self, inquiry_data: StockInquiryCreate):
        """Create a new stock inquiry."""
        inquiry = StockInquiry(**inquiry_data.model_dump())
        self.db.add(inquiry)
        self.db.commit()
        self.db.refresh(inquiry)
        return inquiry
    
    def update_inquiry(self, inquiry_id: str, inquiry_data: StockInquiryUpdate):
        """Update a stock inquiry."""
        inquiry = self.get_inquiry(inquiry_id)
        
        update_data = inquiry_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(inquiry, key, value)
        
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
