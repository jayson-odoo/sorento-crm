"""Inventory service for business logic."""
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from typing import Optional
import time
import uuid
from app.models.inventory import Warehouse, StorageZone, Stock, StockBatch, StockLedger
from app.models.product import Product
from app.schemas.inventory import (
    WarehouseCreate, WarehouseUpdate, StorageZoneCreate, StorageZoneUpdate,
    StockCreate, StockUpdate, StockBatchCreate, StockBatchUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict
from app.services.import_log_service import ImportLogService


class WarehouseService:
    """Service for warehouse operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_warehouses(self, page: int = 1, limit: int = 50, query: Optional[str] = None, is_active: Optional[bool] = None):
        """List warehouses. When is_active=True, only return active warehouses."""
        q = self.db.query(Warehouse)

        if is_active is not None:
            q = q.filter(Warehouse.is_active == is_active)

        if query:
            q = q.filter(
                or_(
                    Warehouse.warehouse_code.ilike(f"%{query}%"),
                    Warehouse.warehouse_name.ilike(f"%{query}%")
                )
            )
        
        total = q.count()
        offset = (page - 1) * limit
        warehouses = q.offset(offset).limit(limit).all()
        
        # Add counts
        result = []
        for warehouse in warehouses:
            zones_count = self.db.query(func.count(StorageZone.id)).filter(
                StorageZone.warehouse_id == warehouse.id
            ).scalar() or 0
            
            stock_count = self.db.query(func.count(Stock.id)).filter(
                Stock.warehouse_id == warehouse.id
            ).scalar() or 0
            
            warehouse_dict = {
                **{c.name: getattr(warehouse, c.name) for c in warehouse.__table__.columns},
                "zones_count": zones_count,
                "stock_count": stock_count
            }
            result.append(warehouse_dict)
        
        return {
            "data": warehouses,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_warehouse(self, warehouse_id: str):
        """Get a warehouse by ID."""
        warehouse = self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
        if not warehouse:
            raise handle_not_found("Warehouse", warehouse_id)
        return warehouse
    
    def create_warehouse(self, warehouse_data: WarehouseCreate):
        """Create a new warehouse."""
        existing = self.db.query(Warehouse).filter(
            Warehouse.warehouse_code == warehouse_data.warehouse_code
        ).first()
        if existing:
            raise handle_conflict("Warehouse code already exists.")
        
        warehouse = Warehouse(**warehouse_data.model_dump())
        self.db.add(warehouse)
        self.db.commit()
        self.db.refresh(warehouse)
        return warehouse
    
    def update_warehouse(self, warehouse_id: str, warehouse_data: WarehouseUpdate):
        """Update a warehouse."""
        warehouse = self.get_warehouse(warehouse_id)
        
        update_data = warehouse_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(warehouse, key, value)
        
        self.db.commit()
        self.db.refresh(warehouse)
        return warehouse


class StorageZoneService:
    """Service for storage zone operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_zones(self, warehouse_id: Optional[str] = None, page: int = 1, limit: int = 50):
        """List storage zones."""
        q = self.db.query(StorageZone)
        
        if warehouse_id:
            q = q.filter(StorageZone.warehouse_id == warehouse_id)
        
        total = q.count()
        offset = (page - 1) * limit
        zones = q.offset(offset).limit(limit).all()
        
        return {
            "data": zones,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }

    def list_zones_tree(self, warehouse_id: Optional[str] = None):
        """List storage zones for tree view with warehouse info."""
        from sqlalchemy.orm import joinedload

        q = self.db.query(StorageZone).options(joinedload(StorageZone.warehouse))
        if warehouse_id:
            q = q.filter(StorageZone.warehouse_id == warehouse_id)
        return q.all()
    
    def get_zone(self, zone_id: str):
        """Get a storage zone by ID."""
        zone = self.db.query(StorageZone).filter(StorageZone.id == zone_id).first()
        if not zone:
            raise handle_not_found("Storage Zone", zone_id)
        return zone
    
    def create_zone(self, zone_data: StorageZoneCreate):
        """Create a new storage zone."""
        # Check unique constraint
        existing = self.db.query(StorageZone).filter(
            StorageZone.warehouse_id == zone_data.warehouse_id,
            StorageZone.zone_code == zone_data.zone_code
        ).first()
        if existing:
            raise handle_conflict("Zone code already exists for this warehouse.")
        
        zone = StorageZone(**zone_data.model_dump())
        self.db.add(zone)
        self.db.commit()
        self.db.refresh(zone)
        return zone
    
    def update_zone(self, zone_id: str, zone_data: StorageZoneUpdate):
        """Update a storage zone."""
        zone = self.get_zone(zone_id)
        
        update_data = zone_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(zone, key, value)
        
        self.db.commit()
        self.db.refresh(zone)
        return zone


class StockService:
    """Service for stock operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_stock(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        sort: Optional[str] = None,
        dir: Optional[str] = None,
        warehouse_id: Optional[str] = None,
        product_id: Optional[str] = None,
        quantity_operator: Optional[str] = None,
        quantity_value: Optional[str] = None,
        status: Optional[str] = None,
    ):
        """List stock with product and warehouse info.

        Args:
            sort: Column to sort by (e.g. product_code, product_name, available).
            dir: 'asc' or 'desc'.
            status: Filter by computed status: critical, low, normal, overstock.
        """
        from sqlalchemy import or_, func
        from sqlalchemy.orm import selectinload
        from app.models.product import Product, ProductCategory

        q = self.db.query(Stock).options(
            selectinload(Stock.product),
            selectinload(Stock.warehouse),
        )

        if warehouse_id:
            q = q.filter(Stock.warehouse_id == warehouse_id)

        if product_id:
            q = q.filter(Stock.product_id == product_id)

        # Join Product once when needed for search, status filter, or product-related sort
        sort_key = (sort or '').replace('product.category.category_name', 'category_name').replace('product.reorder_level', 'reorder_level').replace('warehouse.warehouse_name', 'warehouse_name').replace('product.product_code', 'product_code').replace('product.product_name', 'product_name')
        need_product_join = bool(query) or bool(status) or (sort and dir in ('asc', 'desc') and sort_key in ('product_code', 'product_name', 'category_name', 'reorder_level'))
        if need_product_join:
            q = q.join(Stock.product)

        if query:
            q = q.filter(
                or_(
                    Product.product_code.ilike(f"%{query}%"),
                    Product.product_name.ilike(f"%{query}%"),
                )
            )

        if quantity_operator and quantity_value:
            try:
                value = int(float(quantity_value))
                if quantity_operator == 'gt':
                    q = q.filter(Stock.quantity_available > value)
                elif quantity_operator == 'gte':
                    q = q.filter(Stock.quantity_available >= value)
                elif quantity_operator == 'lt':
                    q = q.filter(Stock.quantity_available < value)
                elif quantity_operator == 'lte':
                    q = q.filter(Stock.quantity_available <= value)
                elif quantity_operator == 'eq':
                    q = q.filter(Stock.quantity_available == value)
            except (ValueError, TypeError):
                pass

        if status and status in ('critical', 'low', 'normal', 'overstock'):
            reorder = func.coalesce(Product.reorder_level, 0)
            if status == 'critical':
                q = q.filter(Stock.quantity_available <= 0)
            elif status == 'low':
                q = q.filter(Stock.quantity_available > 0, Stock.quantity_available < reorder)
            elif status == 'normal':
                q = q.filter(Stock.quantity_available >= reorder)
            elif status == 'overstock':
                q = q.filter(Stock.quantity_available > reorder * 2)

        sort_col = None
        if sort and dir in ('asc', 'desc'):
            if sort_key in ('product_code', 'product_name', 'category_name', 'reorder_level'):
                if sort_key == 'category_name':
                    q = q.outerjoin(Product.category)
                    sort_col = ProductCategory.category_name
                elif sort_key == 'product_code':
                    sort_col = Product.product_code
                elif sort_key == 'product_name':
                    sort_col = Product.product_name
                elif sort_key == 'reorder_level':
                    sort_col = Product.reorder_level
            elif sort_key == 'warehouse_name':
                q = q.join(Stock.warehouse)
                sort_col = Warehouse.warehouse_name
            elif sort_key == 'available':
                sort_col = Stock.quantity_available
            elif sort_key == 'reserved_quantity':
                sort_col = Stock.quantity_reserved
            elif sort_key == 'quantity':
                sort_col = Stock.quantity_on_hand
            elif sort_key == 'status':
                sort_col = Stock.quantity_available
            if sort_col is not None:
                q = q.order_by(sort_col.desc() if dir == 'desc' else sort_col.asc())

        total = q.count()
        offset = (page - 1) * limit
        stock_items = q.offset(offset).limit(limit).all()

        return {
            "data": stock_items,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }

    def list_stock_ledger(
        self,
        page: int = 1,
        limit: int = 50,
        product_id: Optional[str] = None,
        warehouse_id: Optional[str] = None,
        transaction_type: Optional[str] = None
    ):
        """List stock ledger entries with pagination and filtering."""
        from app.schemas.common import ListResponse
        from app.schemas.inventory import StockLedgerResponse
        from app.models.user import User
        from sqlalchemy.orm import selectinload
        
        q = self.db.query(StockLedger).options(
            selectinload(StockLedger.product),
            selectinload(StockLedger.warehouse)
        )
        if product_id:
            q = q.filter(StockLedger.product_id == product_id)
        if warehouse_id:
            q = q.filter(StockLedger.warehouse_id == warehouse_id)
        if transaction_type:
            q = q.filter(StockLedger.transaction_type == transaction_type)

        total = q.count()
        offset = (page - 1) * limit
        entries = q.order_by(StockLedger.created_at.desc()).offset(offset).limit(limit).all()

        user_ids = {entry.created_by for entry in entries if entry.created_by}
        user_map = {}
        if user_ids:
            users = self.db.query(User).filter(User.id.in_(user_ids)).all()
            user_map = {user.id: user.name or user.email for user in users}

        response_entries = []
        for entry in entries:
            response = StockLedgerResponse.model_validate(entry)
            response.created_by_name = user_map.get(entry.created_by)
            response_entries.append(response)

        return ListResponse(
            data=response_entries,
            pagination={"total": total, "page": page, "limit": limit}
        )

    def get_stock_ledger_by_stock(self, product_id: str, warehouse_id: str, page: int = 1, limit: int = 50):
        """Get stock ledger entries for a specific product-warehouse combination."""
        from app.schemas.common import ListResponse
        from app.schemas.inventory import StockLedgerResponse
        from app.models.user import User
        from sqlalchemy.orm import selectinload

        q = self.db.query(StockLedger).options(
            selectinload(StockLedger.product),
            selectinload(StockLedger.warehouse)
        ).filter(
            StockLedger.product_id == product_id,
            StockLedger.warehouse_id == warehouse_id
        )

        total = q.count()
        offset = (page - 1) * limit
        entries = q.order_by(StockLedger.created_at.desc()).offset(offset).limit(limit).all()

        user_ids = {entry.created_by for entry in entries if entry.created_by}
        user_map = {}
        if user_ids:
            users = self.db.query(User).filter(User.id.in_(user_ids)).all()
            user_map = {user.id: user.name or user.email for user in users}

        response_entries = []
        for entry in entries:
            response = StockLedgerResponse.model_validate(entry)
            response.created_by_name = user_map.get(entry.created_by)
            response_entries.append(response)

        return ListResponse(
            data=response_entries,
            pagination={"total": total, "page": page, "limit": limit}
        )
    
    def get_all_stock_for_export(
        self,
        warehouse_id: Optional[str] = None,
        product_id: Optional[str] = None,
        quantity_operator: Optional[str] = None,
        quantity_value: Optional[str] = None
    ):
        """Get all stock for export (no pagination).
        
        Args:
            warehouse_id: Optional warehouse filter
            product_id: Optional product filter
            quantity_operator: One of 'gt', 'gte', 'lt', 'lte', 'eq' for available quantity filtering
            quantity_value: Numeric value to compare against available quantity
        """
        from sqlalchemy.orm import selectinload
        
        # Use selectinload to eagerly load relationships and avoid N+1 queries
        # selectinload is better for one-to-many/many-to-one and doesn't cause duplicate rows
        q = self.db.query(Stock).options(
            selectinload(Stock.product),
            selectinload(Stock.warehouse)
        )
        
        if warehouse_id:
            q = q.filter(Stock.warehouse_id == warehouse_id)
        
        if product_id:
            q = q.filter(Stock.product_id == product_id)
        
        # Filter by available quantity using the quantity_available column
        if quantity_operator and quantity_value:
            try:
                value = int(float(quantity_value))
                
                if quantity_operator == 'gt':
                    q = q.filter(Stock.quantity_available > value)
                elif quantity_operator == 'gte':
                    q = q.filter(Stock.quantity_available >= value)
                elif quantity_operator == 'lt':
                    q = q.filter(Stock.quantity_available < value)
                elif quantity_operator == 'lte':
                    q = q.filter(Stock.quantity_available <= value)
                elif quantity_operator == 'eq':
                    q = q.filter(Stock.quantity_available == value)
            except (ValueError, TypeError):
                # Invalid quantity value, ignore filter
                pass
        
        # Fetch all stock items without pagination
        stock_items = q.all()
        
        return stock_items
    
    def bulk_import_stock(self, stock_data: list[dict], user_id: str):
        """Bulk import stock from Excel data using bulk operations for performance.
        
        Args:
            stock_data: List of dictionaries containing stock data from Excel
            user_id: ID of the user performing the import
            
        Returns:
            dict with created, updated, skipped counts and errors
        """
        created = 0
        updated = 0
        errors = []
        error_records = []
        warnings = []
        skipped_rows = 0
        import_session_id = str(uuid.uuid4())
        start_time = time.monotonic()
        
        # Column mapping from Excel headers to database fields
        # Include all variations that might appear in exported Excel files
        column_mapping = {
            'id': 'id',
            'ID': 'id',
            'product_id': 'product_id',
            'Product ID': 'product_id',
            'product_code': 'product_code',  # For lookup
            'Product Code': 'product_code',
            'Item Code': 'product_code',
            'Item code': 'product_code',
            'item code': 'product_code',
            'ItemCode': 'product_code',
            'warehouse_id': 'warehouse_id',
            'Warehouse ID': 'warehouse_id',
            'warehouse': 'warehouse_name',  # For lookup
            'Warehouse': 'warehouse_name',
            'warehouse_name': 'warehouse_name',
            'Warehouse Name': 'warehouse_name',
            'warehouse_code': 'warehouse_code',
            'Warehouse Code': 'warehouse_code',
            'Location': 'warehouse_code',
            'location': 'warehouse_code',
            'zone_id': 'zone_id',
            'Zone ID': 'zone_id',
            'quantity_on_hand': 'quantity_on_hand',
            'Quantity On Hand': 'quantity_on_hand',
            'quantity': 'quantity_on_hand',  # Alias for quantity_on_hand (frontend uses 'quantity')
            'Quantity': 'quantity_on_hand',
            'Total': 'quantity_on_hand',
            'Total Quantity': 'quantity_on_hand',
            'total quantity': 'quantity_on_hand',  # Lowercase variant
            'total': 'quantity_on_hand',  # Lowercase variant
            'On Hand Qty': 'quantity_on_hand',
            'On hand qty': 'quantity_on_hand',
            'on hand qty': 'quantity_on_hand',
            'On Hand': 'quantity_on_hand',
            'reserved_quantity': 'quantity_reserved',
            'Reserved Quantity': 'quantity_reserved',
            'quantity_reserved': 'quantity_reserved',
            'Quantity Reserved': 'quantity_reserved',
            'reserved quantity': 'quantity_reserved',  # Lowercase variant
            'Reserved': 'quantity_reserved',
            'quantity_available': 'quantity_available',
            'Available': 'quantity_available',
            'available': 'quantity_available',
            'quantity_damaged': 'quantity_damaged',
            'Quantity Damaged': 'quantity_damaged',
            'quantity damaged': 'quantity_damaged',  # Lowercase variant
            'reorder_point': 'reorder_point',
            'Reorder Point': 'reorder_point',
            'reorder point': 'reorder_point',  # Lowercase variant
            'Item Description': 'item_description',
            'Item description': 'item_description',
            'item description': 'item_description',
        }
        
        def parse_int(value):
            """Parse integer value, handling Excel formatting."""
            if value is None or value == '':
                return 0
            # Handle string values that might be formatted numbers
            if isinstance(value, str):
                # Remove common formatting characters
                value = value.strip().replace(',', '').replace('$', '').replace('RM', '').replace(' ', '')
                if value == '' or value == '-':
                    return 0
            try:
                # Try to parse as float first (handles decimals), then convert to int
                return int(float(str(value)))
            except (ValueError, TypeError):
                return 0
        
        # Step 1: Build lookup dictionaries for products and warehouses (bulk lookup)
        product_codes_to_lookup = set()
        warehouse_names_to_lookup = set()
        warehouse_codes_to_lookup = set()
        stock_ids_to_lookup = set()
        
        # First pass: collect all lookup values
        for row_data in stock_data:
            for excel_key, value in row_data.items():
                db_key = column_mapping.get(excel_key, excel_key.lower())
                if db_key == 'product_code' and value:
                    product_codes_to_lookup.add(str(value).strip())
                elif db_key == 'warehouse_name' and value:
                    warehouse_names_to_lookup.add(str(value).strip())
                elif db_key == 'warehouse_code' and value:
                    warehouse_codes_to_lookup.add(str(value).strip())
                elif db_key == 'id' and value:
                    stock_ids_to_lookup.add(str(value).strip())
        
        # Bulk lookup products by code (case-insensitive)
        product_code_map = {}
        product_code_lower_map = {}
        if product_codes_to_lookup:
            # Use case-insensitive matching for product codes
            from sqlalchemy import func
            products = self.db.query(Product).filter(
                func.lower(Product.product_code).in_([code.lower() for code in product_codes_to_lookup])
            ).all()
            # Create maps: one with original case, one with lowercase
            for p in products:
                product_code_map[p.product_code] = p.id
                product_code_lower_map[p.product_code.lower()] = p.id
        
        # Bulk lookup warehouses by code (case-insensitive)
        warehouse_code_map = {}
        warehouse_code_lower_map = {}
        if warehouse_codes_to_lookup:
            warehouses = self.db.query(Warehouse).filter(
                func.lower(Warehouse.warehouse_code).in_([code.lower() for code in warehouse_codes_to_lookup])
            ).all()
            for w in warehouses:
                warehouse_code_map[w.warehouse_code] = w.id
                warehouse_code_lower_map[w.warehouse_code.lower()] = w.id

        # Bulk lookup warehouses by name (case-insensitive) - fallback
        warehouse_name_map = {}
        warehouse_name_lower_map = {}
        if warehouse_names_to_lookup:
            warehouses = self.db.query(Warehouse).filter(
                func.lower(Warehouse.warehouse_name).in_([name.lower() for name in warehouse_names_to_lookup])
            ).all()
            for w in warehouses:
                warehouse_name_map[w.warehouse_name] = w.id
                warehouse_name_lower_map[w.warehouse_name.lower()] = w.id
        
        # Bulk lookup existing stock by IDs
        existing_stock_by_id = {}
        if stock_ids_to_lookup:
            stocks_by_id = self.db.query(Stock).filter(Stock.id.in_(stock_ids_to_lookup)).all()
            existing_stock_by_id = {s.id: s for s in stocks_by_id}
        
        # Step 2: Process all rows and prepare data
        rows_to_create = []
        rows_to_update = []
        product_warehouse_pairs = set()  # Track (product_id, warehouse_id) pairs for bulk lookup
        
        for idx, row_data in enumerate(stock_data, start=1):
            try:
                # Map Excel columns to database fields
                mapped_data = {}
                product_code = None
                warehouse_name = None
                warehouse_code = None
                stock_id = None
                
                for excel_key, value in row_data.items():
                    # Normalize the Excel key
                    excel_key_normalized = str(excel_key).strip()
                    excel_key_lower = excel_key_normalized.lower()
                    
                    # Try exact match first
                    db_key = column_mapping.get(excel_key_normalized)
                    if db_key is None:
                        # Try case-insensitive match
                        db_key = column_mapping.get(excel_key_lower)
                    if db_key is None:
                        # Try matching with common variations (remove extra spaces, handle variations)
                        for key, val in column_mapping.items():
                            key_normalized = key.lower().strip().replace(' ', '')
                            excel_normalized = excel_key_lower.replace(' ', '')
                            if key_normalized == excel_normalized:
                                db_key = val
                                break
                    if db_key is None:
                        # Fallback: use lowercase key
                        db_key = excel_key_lower
                    
                    if db_key in ['quantity_on_hand', 'quantity_reserved', 'quantity_available', 'quantity_damaged', 'reorder_point']:
                        mapped_data[db_key] = parse_int(value)
                    elif db_key == 'product_code':
                        product_code = str(value).strip() if value and str(value).strip() else None
                    elif db_key == 'item_description':
                        # Not persisted; kept for future logging if needed
                        pass
                    elif db_key == 'warehouse_name':
                        warehouse_name = str(value).strip() if value and str(value).strip() else None
                    elif db_key == 'warehouse_code':
                        warehouse_code = str(value).strip() if value and str(value).strip() else None
                    elif db_key in ['product_id', 'warehouse_id', 'zone_id']:
                        mapped_data[db_key] = str(value).strip() if value and str(value).strip() else None
                    elif db_key == 'id':
                        stock_id = str(value).strip() if value and str(value).strip() else None
                
                # Look up product_id from product_code (case-insensitive)
                if not mapped_data.get('product_id') and product_code:
                    product_code_lower = product_code.lower()
                    if product_code in product_code_map:
                        mapped_data['product_id'] = product_code_map[product_code]
                    elif product_code_lower in product_code_lower_map:
                        mapped_data['product_id'] = product_code_lower_map[product_code_lower]
                    else:
                        message = f"Row {idx}: Product not found (code '{product_code}')"
                        errors.append(message)
                        error_records.append({"row": idx, "error": message, "data": row_data})
                        continue
                
                # Look up warehouse_id from warehouse_code (case-insensitive)
                if not mapped_data.get('warehouse_id') and warehouse_code:
                    warehouse_code_lower = warehouse_code.lower()
                    if warehouse_code in warehouse_code_map:
                        mapped_data['warehouse_id'] = warehouse_code_map[warehouse_code]
                    elif warehouse_code_lower in warehouse_code_lower_map:
                        mapped_data['warehouse_id'] = warehouse_code_lower_map[warehouse_code_lower]
                    else:
                        message = (
                            f"Row {idx}: Warehouse not found (code '{warehouse_code}', "
                            f"product '{product_code or '-'}')"
                        )
                        errors.append(message)
                        error_records.append({"row": idx, "error": message, "data": row_data})
                        continue

                # Look up warehouse_id from warehouse_name (case-insensitive) - fallback
                if not mapped_data.get('warehouse_id') and warehouse_name:
                    warehouse_name_lower = warehouse_name.lower()
                    if warehouse_name in warehouse_name_map:
                        mapped_data['warehouse_id'] = warehouse_name_map[warehouse_name]
                    elif warehouse_name_lower in warehouse_name_lower_map:
                        mapped_data['warehouse_id'] = warehouse_name_lower_map[warehouse_name_lower]
                    else:
                        message = (
                            f"Row {idx}: Warehouse not found (name '{warehouse_name}', "
                            f"product '{product_code or '-'}')"
                        )
                        errors.append(message)
                        error_records.append({"row": idx, "error": message, "data": row_data})
                        continue
                
                # Validate required fields
                if not mapped_data.get('product_id'):
                    message = f"Row {idx}: Product is required (code '{product_code or '-'}')"
                    errors.append(message)
                    error_records.append({"row": idx, "error": message, "data": row_data})
                    continue
                
                if not mapped_data.get('warehouse_id'):
                    message = (
                        f"Row {idx}: Warehouse is required "
                        f"(code '{warehouse_code or '-'}', name '{warehouse_name or '-'}', "
                        f"product '{product_code or '-'}')"
                    )
                    errors.append(message)
                    error_records.append({"row": idx, "error": message, "data": row_data})
                    continue
                
                # Handle quantity logic
                # quantity_available is a GENERATED column in the database, so we don't update it
                # We only update quantity_on_hand (from "Total Quantity") and quantity_reserved (from "Reserved Quantity")
                # The database will automatically calculate quantity_available = quantity_on_hand - quantity_reserved
                
                quantity_available_raw = mapped_data.get('quantity_available', 0)
                quantity_on_hand_raw = mapped_data.get('quantity_on_hand', 0)
                quantity_reserved_raw = mapped_data.get('quantity_reserved', 0)
                
                # Ensure they are integers
                quantity_available = int(quantity_available_raw) if quantity_available_raw else 0
                quantity_on_hand = int(quantity_on_hand_raw) if quantity_on_hand_raw else 0
                quantity_reserved = int(quantity_reserved_raw) if quantity_reserved_raw else 0
                
                # Logic: If "Available" is provided but "Total Quantity" and "Reserved Quantity" are empty,
                # use Available as quantity_on_hand (since Available = Total - Reserved, if Reserved=0, then Available = Total)
                if quantity_available > 0 and quantity_on_hand == 0 and quantity_reserved == 0:
                    # Only Available is provided - use it as quantity_on_hand
                    mapped_data['quantity_on_hand'] = quantity_available
                    mapped_data['quantity_reserved'] = 0
                elif quantity_on_hand > 0:
                    # quantity_on_hand is provided - use it as is
                    # quantity_reserved is already set from mapped_data
                    pass
                elif quantity_available > 0:
                    # Only Available provided (fallback case)
                    mapped_data['quantity_on_hand'] = quantity_available
                    mapped_data['quantity_reserved'] = 0
                else:
                    # Nothing provided - default to 0
                    mapped_data['quantity_on_hand'] = 0
                    mapped_data['quantity_reserved'] = 0
                
                # Prepare row data - only set fields we can update (NOT quantity_available - it's generated)
                row_dict = {
                    'product_id': mapped_data['product_id'],
                    'warehouse_id': mapped_data['warehouse_id'],
                    'zone_id': mapped_data.get('zone_id'),
                    'quantity_on_hand': mapped_data.get('quantity_on_hand', 0) or 0,
                    'quantity_reserved': mapped_data.get('quantity_reserved', 0) or 0,
                    # Note: quantity_available is NOT included - it's a generated column
                    'quantity_damaged': mapped_data.get('quantity_damaged', 0) or 0,
                    'reorder_point': mapped_data.get('reorder_point'),
                    '_row_idx': idx,
                    '_stock_id': stock_id,
                    '_product_code': product_code,
                    '_warehouse_name': warehouse_name,
                }
                
                # Check if exists by ID first
                if stock_id and stock_id in existing_stock_by_id:
                    row_dict['_existing_id'] = stock_id
                    rows_to_update.append(row_dict)
                else:
                    # Will check by product_id + warehouse_id later
                    # Ensure both IDs are strings for consistent tuple matching
                    product_warehouse_pairs.add((str(mapped_data['product_id']), str(mapped_data['warehouse_id'])))
                    rows_to_create.append(row_dict)
                
            except Exception as e:
                message = f"Row {idx}: {str(e)}"
                errors.append(message)
                error_records.append({"row": idx, "error": message, "data": row_data})
                continue
        
        # Step 3: Bulk lookup existing stock by product_id + warehouse_id
        existing_stock_by_pair = {}
        if product_warehouse_pairs:
            # Build query with OR conditions for all pairs
            conditions = [
                and_(Stock.product_id == pid, Stock.warehouse_id == wid)
                for pid, wid in product_warehouse_pairs
            ]
            existing_stocks = self.db.query(Stock).filter(or_(*conditions)).all()
            # Ensure tuple keys use string UUIDs for consistent matching
            existing_stock_by_pair = {(str(s.product_id), str(s.warehouse_id)): s for s in existing_stocks}
        
        # Step 4: Separate creates and updates (no new stock creation allowed)
        final_creates = []
        final_updates = []
        ledger_entries = []
        
        for row_dict in rows_to_create:
            # Ensure tuple uses string UUIDs for consistent matching
            pair = (str(row_dict['product_id']), str(row_dict['warehouse_id']))
            if pair in existing_stock_by_pair:
                # Move to updates
                row_dict['_existing_id'] = existing_stock_by_pair[pair].id
                final_updates.append(row_dict)
            else:
                skipped_rows += 1
                warnings.append({
                    "row": row_dict.get("_row_idx"),
                    "product_code": row_dict.get("_product_code"),
                    "warehouse": row_dict.get("_warehouse_name"),
                    "reason": "Stock record not found for product + warehouse"
                })
        
        for row_dict in rows_to_update:
            final_updates.append(row_dict)
        
        # Build existing stock map for ledger calculations
        existing_by_id = {**existing_stock_by_id}
        for stock in existing_stock_by_pair.values():
            existing_by_id[stock.id] = stock
        
        # Step 5: Skip bulk insert (no new stock creation allowed)
        if final_creates:
            created = 0
        
        # Step 6: Update existing records (use individual updates for reliability)
        if final_updates:
            try:
                # Group updates by ID (if same ID appears multiple times, use the last one)
                # Note: quantity_available is a GENERATED column, so we don't update it
                # The database will automatically calculate it as quantity_on_hand - quantity_reserved
                update_dict = {}
                for row_dict in final_updates:
                    stock_id = row_dict['_existing_id']
                    qoh = row_dict.get('quantity_on_hand', 0) or 0
                    qres = row_dict.get('quantity_reserved', 0) or 0
                    
                    # Store update data - only fields we can update (NOT quantity_available)
                    update_dict[stock_id] = {
                        'zone_id': row_dict.get('zone_id'),
                        'quantity_on_hand': qoh,
                        'quantity_reserved': qres,
                        # quantity_available is NOT included - it's a generated column
                        'quantity_damaged': row_dict.get('quantity_damaged', 0) or 0,
                        'reorder_point': row_dict.get('reorder_point'),
                    }
                
                # Perform individual updates for reliability
                for stock_id, update_data in update_dict.items():
                    stock = existing_by_id.get(stock_id)
                    if not stock:
                        # Try to fetch from database if not in cache
                        stock = self.db.query(Stock).filter(Stock.id == stock_id).first()
                        if not stock:
                            message = f"Stock record with ID '{stock_id}' not found for update"
                            errors.append(message)
                            error_records.append({"row": None, "error": message, "data": None})
                            continue
                        existing_by_id[stock_id] = stock
                    
                    previous_qty = stock.quantity_on_hand
                    # Update the stock record - only update fields that are not generated columns
                    # quantity_available will be automatically calculated by the database
                    for key, value in update_data.items():
                        # Skip quantity_available if it somehow got into update_data (shouldn't happen)
                        if key != 'quantity_available':
                            setattr(stock, key, value)
                    # Mark as modified to ensure SQLAlchemy tracks the change
                    self.db.add(stock)
                    new_qty = update_data['quantity_on_hand']
                    quantity_change = new_qty - previous_qty
                    # Add ledger entry if quantity changed
                    if quantity_change != 0:
                        # Get the calculated quantity_available after update (will be refreshed from DB)
                        # For ledger, we'll use the calculated value: new_qty - quantity_reserved
                        calculated_available = new_qty - update_data.get('quantity_reserved', 0)
                        ledger_entries.append({
                            'id': str(uuid.uuid4()),
                            'product_id': stock.product_id,
                            'warehouse_id': stock.warehouse_id,
                            'transaction_type': 'BULK_IMPORT',
                            'quantity_change': quantity_change,
                            'previous_quantity': previous_qty,
                            'new_quantity': new_qty,
                            'reference_type': 'bulk_import',
                            'reference_id': stock_id,
                            'notes': 'Bulk import update',
                            'created_by': user_id
                        })
                
                updated = len(update_dict)
            except Exception as e:
                message = f"Bulk update error: {str(e)}"
                errors.append(message)
                error_records.append({"row": None, "error": message, "data": None})
        
        # Step 7: Commit all changes
        commit_successful = False
        try:
            if ledger_entries:
                self.db.bulk_insert_mappings(StockLedger, ledger_entries)
            # Flush to ensure all changes are sent to database
            self.db.flush()
            # Commit the transaction
            self.db.commit()
            commit_successful = True
        except Exception as e:
            self.db.rollback()
            message = f"Database error: {str(e)}"
            errors.append(message)
            error_records.append({"row": None, "error": message, "data": None})

        # Step 8: Create import log entry (only if commit was successful)
        duration_ms = int((time.monotonic() - start_time) * 1000)
        if commit_successful:
            try:
                import_log_service = ImportLogService(self.db)
                import_log_service.create_import_log(
                    entity_type="stock",
                    entity_table="stock",
                    import_session_id=import_session_id,
                    filename=None,
                    import_type="BULK_IMPORT",
                    total_rows=len(stock_data),
                    successful_rows=created + updated,
                    created_rows=created,
                    updated_rows=updated,
                    failed_rows=len(error_records),
                    skipped_rows=skipped_rows,
                    warnings=warnings,
                    errors=error_records,
                    summary=None,
                    imported_by=user_id,
                    duration_ms=duration_ms,
                )
            except Exception:
                # Import logging should not break the main import flow
                pass

        return {
            "import_session_id": import_session_id,
            "created": created,
            "updated": updated,
            "skipped": skipped_rows,
            "errors": errors,
            "warnings": warnings
        }
    
    def get_stock(self, stock_id: str):
        """Get stock by ID."""
        stock = self.db.query(Stock).filter(Stock.id == stock_id).first()
        if not stock:
            raise handle_not_found("Stock", stock_id)
        return stock
    
    def get_stock_dashboard(self):
        """Get stock dashboard statistics."""
        # Count unique products
        total_skus = self.db.query(func.count(func.distinct(Stock.product_id))).scalar() or 0
        
        # Sum quantities from stock batches
        total_quantity_result = self.db.query(func.sum(StockBatch.quantity)).scalar()
        total_quantity = int(total_quantity_result) if total_quantity_result else 0
        
        return {
            "total_skus": total_skus,
            "total_quantity": total_quantity,
            "low_stock_alert_count": 0,
            "overstock_warning_count": 0,
            "stock_by_warehouse": [],
            "stock_by_category": [],
            "stock_movement_30_days": [],
            "low_stock_alerts": []
        }
    
    def get_stock_alerts(self):
        """Get low stock alerts."""
        # TODO: Implement based on reorder levels
        return []


class StockBatchService:
    """Service for stock batch operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_batches(
        self,
        page: int = 1,
        limit: int = 50,
        product_id: Optional[str] = None,
        warehouse_id: Optional[str] = None
    ):
        """List stock batches."""
        q = self.db.query(StockBatch)
        
        if product_id:
            q = q.filter(StockBatch.product_id == product_id)
        if warehouse_id:
            q = q.filter(StockBatch.warehouse_id == warehouse_id)
        
        total = q.count()
        offset = (page - 1) * limit
        batches = q.offset(offset).limit(limit).all()
        
        return {
            "data": batches,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_batch(self, batch_id: str):
        """Get a stock batch by ID."""
        batch = self.db.query(StockBatch).filter(StockBatch.id == batch_id).first()
        if not batch:
            raise handle_not_found("Stock Batch", batch_id)
        return batch
    
    def create_batch(self, batch_data: StockBatchCreate):
        """Create a new stock batch."""
        existing = self.db.query(StockBatch).filter(
            StockBatch.batch_code == batch_data.batch_code
        ).first()
        if existing:
            raise handle_conflict("Batch code already exists.")
        
        batch = StockBatch(**batch_data.model_dump())
        self.db.add(batch)
        self.db.commit()
        self.db.refresh(batch)
        return batch
    
    def update_batch(self, batch_id: str, batch_data: StockBatchUpdate):
        """Update a stock batch."""
        batch = self.get_batch(batch_id)
        
        update_data = batch_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(batch, key, value)
        
        self.db.commit()
        self.db.refresh(batch)
        return batch
