"""Order service for business logic."""
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import Optional
from decimal import Decimal
from app.models.order import Order, OrderStatus, Customer
from app.schemas.order import (
    OrderCreate, OrderUpdate, CustomerCreate, CustomerUpdate,
    OrderStatusCreate, OrderStatusUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict


class OrderService:
    """Service for order operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_orders(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        customer_id: Optional[str] = None,
        order_status_id: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "asc"
    ):
        """List orders with filtering and pagination."""
        q = self.db.query(Order).filter(Order.deleted_at.is_(None))
        
        filters = []
        
        if customer_id and customer_id != "all":
            filters.append(Order.customer_id == customer_id)
        
        if order_status_id and order_status_id != "all":
            filters.append(Order.order_status_id == order_status_id)
        
        if query:
            filters.append(
                or_(
                    Order.order_number.ilike(f"%{query}%"),
                    Order.customer.has(Customer.customer_name.ilike(f"%{query}%")),
                    Order.customer.has(Customer.customer_code.ilike(f"%{query}%"))
                )
            )
        
        if filters:
            q = q.filter(and_(*filters))
        
        total = q.count()
        
        sort_map = {
            "order_number": Order.order_number,
            "order_date": Order.order_date,
            "total_amount": Order.total_amount,
            "created_at": Order.created_at,
            "updated_at": Order.updated_at,
        }
        sort_column = sort_map.get(sort_field, Order.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        offset = (page - 1) * limit
        orders = q.offset(offset).limit(limit).all()
        
        return {
            "data": orders,
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit
            },
            "empty": total == 0
        }
    
    def get_order(self, order_id: str):
        """Get a single order by ID."""
        order = self.db.query(Order).filter(
            Order.id == order_id,
            Order.deleted_at.is_(None)
        ).first()
        if not order:
            raise handle_not_found("Order", order_id)
        return order
    
    def create_order(self, order_data: OrderCreate, created_by: str):
        """Create a new order."""
        # Check if order_number already exists
        existing = self.db.query(Order).filter(Order.order_number == order_data.order_number).first()
        if existing:
            raise handle_conflict("Order number already exists. Please use a different number.")
        
        # Calculate total if not provided
        subtotal = order_data.subtotal_amount or Decimal("0")
        discount = order_data.discount_amount or Decimal("0")
        tax = order_data.tax_amount or Decimal("0")
        total = subtotal - discount + tax
        
        order_dict = order_data.model_dump()
        order_dict["total_amount"] = total
        order_dict["created_by"] = created_by
        
        order = Order(**order_dict)
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order
    
    def update_order(self, order_id: str, order_data: OrderUpdate, updated_by: str):
        """Update an order."""
        order = self.get_order(order_id)
        
        update_data = order_data.model_dump(exclude_unset=True)
        if update_data:
            # Recalculate total if amounts changed
            if any(k in update_data for k in ["subtotal_amount", "discount_amount", "tax_amount"]):
                subtotal = update_data.get("subtotal_amount", order.subtotal_amount) or Decimal("0")
                discount = update_data.get("discount_amount", order.discount_amount) or Decimal("0")
                tax = update_data.get("tax_amount", order.tax_amount) or Decimal("0")
                update_data["total_amount"] = subtotal - discount + tax
            
            update_data["updated_by"] = updated_by
            for key, value in update_data.items():
                setattr(order, key, value)
            
            self.db.commit()
            self.db.refresh(order)
        
        return order
    
    def delete_order(self, order_id: str):
        """Soft delete an order."""
        from datetime import datetime, timezone
        order = self.get_order(order_id)
        order.deleted_at = datetime.now(timezone.utc)
        self.db.commit()
        return {"message": "Order deleted successfully"}
    
    def bulk_import_orders(self, orders_data: list[dict], user_id: str):
        """Bulk import orders from Excel data.
        
        Args:
            orders_data: List of dictionaries containing order data from Excel
            user_id: ID of the user performing the import
            
        Returns:
            dict with created, updated counts and errors
        """
        from datetime import datetime
        import re
        
        created = 0
        updated = 0
        errors = []
        
        # Column mapping from Excel headers to database fields
        column_mapping = {
            'id': 'id',
            'ID': 'id',
            'order_number': 'order_number',
            'Order Number': 'order_number',
            'order_date': 'order_date',
            'Order Date': 'order_date',
            'promised_delivery_date': 'promised_delivery_date',
            'Promised Delivery Date': 'promised_delivery_date',
            'actual_delivery_date': 'actual_delivery_date',
            'Actual Delivery Date': 'actual_delivery_date',
            'customer_id': 'customer_id',
            'Customer ID': 'customer_id',
            'order_status_id': 'order_status_id',
            'Order Status ID': 'order_status_id',
            'subtotal_amount': 'subtotal_amount',
            'Subtotal Amount': 'subtotal_amount',
            'discount_amount': 'discount_amount',
            'Discount Amount': 'discount_amount',
            'tax_amount': 'tax_amount',
            'Tax Amount': 'tax_amount',
            'total_amount': 'total_amount',
            'Total Amount': 'total_amount',
            'remarks': 'remarks',
            'Remarks': 'remarks',
            'billing_address_id': 'billing_address_id',
            'Billing Address ID': 'billing_address_id',
            'shipping_address_id': 'shipping_address_id',
            'Shipping Address ID': 'shipping_address_id',
        }
        
        def parse_date(value):
            """Parse date from various formats."""
            if not value or value == '':
                return None
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                # Try ISO format first
                try:
                    return datetime.fromisoformat(value.replace('Z', '+00:00'))
                except:
                    pass
                # Try other common formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                    try:
                        return datetime.strptime(value, fmt)
                    except:
                        continue
            return None
        
        def parse_decimal(value):
            """Parse decimal value."""
            if value is None or value == '':
                return Decimal("0")
            try:
                return Decimal(str(value))
            except:
                return Decimal("0")
        
        for idx, row_data in enumerate(orders_data, start=1):
            try:
                # Map Excel columns to database fields
                mapped_data = {}
                for excel_key, value in row_data.items():
                    db_key = column_mapping.get(excel_key, excel_key.lower())
                    if db_key in ['order_date', 'promised_delivery_date', 'actual_delivery_date']:
                        mapped_data[db_key] = parse_date(value)
                    elif db_key in ['subtotal_amount', 'discount_amount', 'tax_amount', 'total_amount']:
                        mapped_data[db_key] = parse_decimal(value)
                    elif db_key in ['customer_id', 'order_status_id', 'billing_address_id', 'shipping_address_id']:
                        # Convert to string, handle empty values
                        mapped_data[db_key] = str(value).strip() if value and str(value).strip() else None
                    elif db_key in ['order_number', 'remarks']:
                        mapped_data[db_key] = str(value).strip() if value else None
                    elif db_key == 'id':
                        # ID is optional - if provided, will update; if not, will create
                        mapped_data[db_key] = str(value).strip() if value and str(value).strip() else None
                
                order_id = mapped_data.pop('id', None)
                
                # Validate required fields
                if not mapped_data.get('order_number'):
                    errors.append(f"Row {idx}: Order Number is required")
                    continue
                
                # Check if order exists (by ID first, then by order_number)
                existing_order = None
                
                # First, try to find by ID if provided
                if order_id:
                    existing_order = self.db.query(Order).filter(
                        Order.id == order_id,
                        Order.deleted_at.is_(None)
                    ).first()
                
                # If not found by ID, try to find by order_number
                if not existing_order:
                    existing_order = self.db.query(Order).filter(
                        Order.order_number == mapped_data['order_number'],
                        Order.deleted_at.is_(None)
                    ).first()
                
                # If creating new order, check for duplicate order_number
                if not existing_order:
                    duplicate = self.db.query(Order).filter(
                        Order.order_number == mapped_data['order_number'],
                        Order.deleted_at.is_(None)
                    ).first()
                    if duplicate:
                        errors.append(f"Row {idx}: Order Number '{mapped_data['order_number']}' already exists")
                        continue
                
                # Calculate total if not provided
                if 'total_amount' not in mapped_data or not mapped_data['total_amount']:
                    subtotal = mapped_data.get('subtotal_amount', Decimal("0")) or Decimal("0")
                    discount = mapped_data.get('discount_amount', Decimal("0")) or Decimal("0")
                    tax = mapped_data.get('tax_amount', Decimal("0")) or Decimal("0")
                    mapped_data['total_amount'] = subtotal - discount + tax
                
                if existing_order:
                    # Update existing order
                    for key, value in mapped_data.items():
                        if key != 'order_number':  # Don't update order_number
                            setattr(existing_order, key, value)
                    existing_order.updated_by = user_id
                    updated += 1
                else:
                    # Create new order
                    mapped_data['created_by'] = user_id
                    order = Order(**mapped_data)
                    self.db.add(order)
                    created += 1
                
            except Exception as e:
                error_msg = f"Row {idx}: {str(e)}"
                errors.append(error_msg)
                continue
        
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            errors.append(f"Database error: {str(e)}")
        
        return {
            "created": created,
            "updated": updated,
            "errors": errors
        }


class CustomerService:
    """Service for customer operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_customers(self, page: int = 1, limit: int = 50, query: Optional[str] = None):
        """List customers."""
        q = self.db.query(Customer)
        
        if query:
            q = q.filter(
                or_(
                    Customer.customer_code.ilike(f"%{query}%"),
                    Customer.customer_name.ilike(f"%{query}%")
                )
            )
        
        total = q.count()
        offset = (page - 1) * limit
        customers = q.offset(offset).limit(limit).all()
        
        return {
            "data": customers,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_customer(self, customer_id: str):
        """Get a customer by ID."""
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise handle_not_found("Customer", customer_id)
        return customer
    
    def create_customer(self, customer_data: CustomerCreate):
        """Create a new customer."""
        existing = self.db.query(Customer).filter(
            Customer.customer_code == customer_data.customer_code
        ).first()
        if existing:
            raise handle_conflict("Customer code already exists.")
        
        customer = Customer(**customer_data.model_dump())
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer
    
    def update_customer(self, customer_id: str, customer_data: CustomerUpdate):
        """Update a customer."""
        customer = self.get_customer(customer_id)
        
        update_data = customer_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(customer, key, value)
        
        self.db.commit()
        self.db.refresh(customer)
        return customer


class OrderStatusService:
    """Service for order status operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_order_statuses(self, page: int = 1, limit: int = 50):
        """List order statuses."""
        q = self.db.query(OrderStatus).order_by(OrderStatus.sequence)
        
        total = q.count()
        offset = (page - 1) * limit
        statuses = q.offset(offset).limit(limit).all()
        
        return {
            "data": statuses,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_order_status(self, status_id: str):
        """Get an order status by ID."""
        status = self.db.query(OrderStatus).filter(OrderStatus.id == status_id).first()
        if not status:
            raise handle_not_found("Order Status", status_id)
        return status
    
    def create_order_status(self, status_data: OrderStatusCreate):
        """Create a new order status."""
        existing = self.db.query(OrderStatus).filter(
            OrderStatus.status_code == status_data.status_code
        ).first()
        if existing:
            raise handle_conflict("Status code already exists.")
        
        status = OrderStatus(**status_data.model_dump())
        self.db.add(status)
        self.db.commit()
        self.db.refresh(status)
        return status
    
    def update_order_status(self, status_id: str, status_data: OrderStatusUpdate):
        """Update an order status."""
        status = self.get_order_status(status_id)
        
        update_data = status_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(status, key, value)
        
        self.db.commit()
        self.db.refresh(status)
        return status
