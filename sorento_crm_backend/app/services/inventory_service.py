"""Inventory service for business logic."""
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from typing import Optional
import uuid
from app.models.inventory import Warehouse, StorageZone, Stock, StockBatch, StockLedger
from app.models.product import Product
from app.schemas.inventory import (
    WarehouseCreate, WarehouseUpdate, StorageZoneCreate, StorageZoneUpdate,
    StockCreate, StockUpdate, StockBatchCreate, StockBatchUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict


class WarehouseService:
    """Service for warehouse operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_warehouses(self, page: int = 1, limit: int = 50, query: Optional[str] = None):
        """List warehouses."""
        q = self.db.query(Warehouse)
        
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
        warehouse_id: Optional[str] = None,
        product_id: Optional[str] = None,
        quantity_operator: Optional[str] = None,
        quantity_value: Optional[str] = None
    ):
        """List stock with product and warehouse info.
        
        Args:
            warehouse_id: Optional warehouse filter
            product_id: Optional product filter
            quantity_operator: One of 'gt', 'gte', 'lt', 'lte', 'eq' for available quantity filtering
            quantity_value: Numeric value to compare against available quantity
        """
        from sqlalchemy import case
        
        q = self.db.query(Stock)
        
        if warehouse_id:
            q = q.filter(Stock.warehouse_id == warehouse_id)
        
        if product_id:
            q = q.filter(Stock.product_id == product_id)
        
        # Filter by available quantity using the quantity_available column
        if quantity_operator and quantity_value:
            try:
                value = int(float(quantity_value))  # Convert to int for quantity comparison
                
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
        
        total = q.count()
        offset = (page - 1) * limit
        stock_items = q.offset(offset).limit(limit).all()
        
        return {
            "data": stock_items,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
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
        
        q = self.db.query(StockLedger)
        if product_id:
            q = q.filter(StockLedger.product_id == product_id)
        if warehouse_id:
            q = q.filter(StockLedger.warehouse_id == warehouse_id)
        if transaction_type:
            q = q.filter(StockLedger.transaction_type == transaction_type)

        total = q.count()
        offset = (page - 1) * limit
        entries = q.order_by(StockLedger.created_at.desc()).offset(offset).limit(limit).all()

        return ListResponse(
            data=[StockLedgerResponse.model_validate(entry) for entry in entries],
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
            dict with created, updated counts and errors
        """
        created = 0
        updated = 0
        errors = []
        
        # Column mapping from Excel headers to database fields
        column_mapping = {
            'id': 'id',
            'ID': 'id',
            'product_id': 'product_id',
            'Product ID': 'product_id',
            'product_code': 'product_code',  # For lookup
            'Product Code': 'product_code',
            'warehouse_id': 'warehouse_id',
            'Warehouse ID': 'warehouse_id',
            'warehouse': 'warehouse_name',  # For lookup
            'Warehouse': 'warehouse_name',
            'warehouse_name': 'warehouse_name',
            'Warehouse Name': 'warehouse_name',
            'zone_id': 'zone_id',
            'Zone ID': 'zone_id',
            'quantity_on_hand': 'quantity_on_hand',
            'Quantity On Hand': 'quantity_on_hand',
            'quantity': 'quantity_on_hand',  # Alias for quantity_on_hand (frontend uses 'quantity')
            'Quantity': 'quantity_on_hand',
            'Total': 'quantity_on_hand',
            'Total Quantity': 'quantity_on_hand',
            'reserved_quantity': 'quantity_reserved',
            'Reserved Quantity': 'quantity_reserved',
            'quantity_reserved': 'quantity_reserved',
            'Quantity Reserved': 'quantity_reserved',
            'Reserved': 'quantity_reserved',
            'quantity_available': 'quantity_available',
            'Available': 'quantity_available',
            'available': 'quantity_available',
            'quantity_damaged': 'quantity_damaged',
            'Quantity Damaged': 'quantity_damaged',
            'reorder_point': 'reorder_point',
            'Reorder Point': 'reorder_point',
        }
        
        def parse_int(value):
            """Parse integer value."""
            if value is None or value == '':
                return 0
            try:
                return int(float(str(value)))
            except (ValueError, TypeError):
                return 0
        
        # Step 1: Build lookup dictionaries for products and warehouses (bulk lookup)
        product_codes_to_lookup = set()
        warehouse_names_to_lookup = set()
        stock_ids_to_lookup = set()
        
        # First pass: collect all lookup values
        for row_data in stock_data:
            for excel_key, value in row_data.items():
                db_key = column_mapping.get(excel_key, excel_key.lower())
                if db_key == 'product_code' and value:
                    product_codes_to_lookup.add(str(value).strip())
                elif db_key == 'warehouse_name' and value:
                    warehouse_names_to_lookup.add(str(value).strip())
                elif db_key == 'id' and value:
                    stock_ids_to_lookup.add(str(value).strip())
        
        # Bulk lookup products by code
        product_code_map = {}
        if product_codes_to_lookup:
            products = self.db.query(Product).filter(Product.product_code.in_(product_codes_to_lookup)).all()
            product_code_map = {p.product_code: p.id for p in products}
        
        # Bulk lookup warehouses by name
        warehouse_name_map = {}
        if warehouse_names_to_lookup:
            warehouses = self.db.query(Warehouse).filter(Warehouse.warehouse_name.in_(warehouse_names_to_lookup)).all()
            warehouse_name_map = {w.warehouse_name: w.id for w in warehouses}
        
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
                stock_id = None
                
                for excel_key, value in row_data.items():
                    # Try exact match first, then case-insensitive match
                    db_key = column_mapping.get(excel_key)
                    if db_key is None:
                        # Try case-insensitive match
                        excel_key_lower = excel_key.lower().strip()
                        db_key = column_mapping.get(excel_key_lower)
                        if db_key is None:
                            # Try matching with common variations
                            for key, val in column_mapping.items():
                                if key.lower().strip() == excel_key_lower:
                                    db_key = val
                                    break
                        if db_key is None:
                            db_key = excel_key_lower
                    
                    if db_key in ['quantity_on_hand', 'quantity_reserved', 'quantity_available', 'quantity_damaged', 'reorder_point']:
                        mapped_data[db_key] = parse_int(value)
                    elif db_key == 'product_code':
                        product_code = str(value).strip() if value and str(value).strip() else None
                    elif db_key == 'warehouse_name':
                        warehouse_name = str(value).strip() if value and str(value).strip() else None
                    elif db_key in ['product_id', 'warehouse_id', 'zone_id']:
                        mapped_data[db_key] = str(value).strip() if value and str(value).strip() else None
                    elif db_key == 'id':
                        stock_id = str(value).strip() if value and str(value).strip() else None
                
                # Look up product_id from product_code
                if not mapped_data.get('product_id') and product_code:
                    if product_code in product_code_map:
                        mapped_data['product_id'] = product_code_map[product_code]
                    else:
                        errors.append(f"Row {idx}: Product with code '{product_code}' not found")
                        continue
                
                # Look up warehouse_id from warehouse_name
                if not mapped_data.get('warehouse_id') and warehouse_name:
                    if warehouse_name in warehouse_name_map:
                        mapped_data['warehouse_id'] = warehouse_name_map[warehouse_name]
                    else:
                        errors.append(f"Row {idx}: Warehouse with name '{warehouse_name}' not found")
                        continue
                
                # Validate required fields
                if not mapped_data.get('product_id'):
                    errors.append(f"Row {idx}: Product ID or Product Code is required")
                    continue
                
                if not mapped_data.get('warehouse_id'):
                    errors.append(f"Row {idx}: Warehouse ID or Warehouse Name is required")
                    continue
                
                # Handle quantity logic
                # Get values from mapped_data (already parsed as integers)
                quantity_available_raw = mapped_data.get('quantity_available', 0)
                quantity_on_hand_raw = mapped_data.get('quantity_on_hand', 0)
                quantity_reserved_raw = mapped_data.get('quantity_reserved', 0)
                
                # Ensure they are integers
                quantity_available = int(quantity_available_raw) if quantity_available_raw else 0
                quantity_on_hand = int(quantity_on_hand_raw) if quantity_on_hand_raw else 0
                quantity_reserved = int(quantity_reserved_raw) if quantity_reserved_raw else 0
                
                # Logic: If "Available" is provided but "Total Quantity" and "Reserved Quantity" are empty,
                # use Available as quantity_on_hand
                if quantity_available > 0 and quantity_on_hand == 0 and quantity_reserved == 0:
                    # Only Available is provided - use it as quantity_on_hand
                    mapped_data['quantity_on_hand'] = quantity_available
                    mapped_data['quantity_reserved'] = 0
                    mapped_data['quantity_available'] = quantity_available
                elif quantity_on_hand > 0:
                    # quantity_on_hand is provided - calculate available if not provided
                    if quantity_available == 0:
                        mapped_data['quantity_available'] = quantity_on_hand - quantity_reserved
                    else:
                        # Both provided - use the provided available value
                        mapped_data['quantity_available'] = quantity_available
                elif quantity_available > 0:
                    # Only Available provided (fallback case)
                    mapped_data['quantity_on_hand'] = quantity_available
                    mapped_data['quantity_reserved'] = 0
                    mapped_data['quantity_available'] = quantity_available
                else:
                    # Nothing provided - default to 0
                    mapped_data['quantity_on_hand'] = 0
                    mapped_data['quantity_reserved'] = 0
                    mapped_data['quantity_available'] = 0
                
                # Final safety check: ensure quantity_available is always set
                if 'quantity_available' not in mapped_data or mapped_data.get('quantity_available') is None:
                    qoh = mapped_data.get('quantity_on_hand', 0) or 0
                    qres = mapped_data.get('quantity_reserved', 0) or 0
                    mapped_data['quantity_available'] = qoh - qres
                
                # Prepare row data - ensure all quantity fields are explicitly set
                row_dict = {
                    'product_id': mapped_data['product_id'],
                    'warehouse_id': mapped_data['warehouse_id'],
                    'zone_id': mapped_data.get('zone_id'),
                    'quantity_on_hand': mapped_data.get('quantity_on_hand', 0) or 0,
                    'quantity_reserved': mapped_data.get('quantity_reserved', 0) or 0,
                    'quantity_available': mapped_data.get('quantity_available', 0) or 0,
                    'quantity_damaged': mapped_data.get('quantity_damaged', 0) or 0,
                    'reorder_point': mapped_data.get('reorder_point'),
                    '_row_idx': idx,
                    '_stock_id': stock_id,
                }
                
                # Final check: ensure quantity_available is set correctly
                if row_dict['quantity_available'] == 0 and row_dict['quantity_on_hand'] > 0:
                    row_dict['quantity_available'] = row_dict['quantity_on_hand'] - row_dict['quantity_reserved']
                
                # Check if exists by ID first
                if stock_id and stock_id in existing_stock_by_id:
                    row_dict['_existing_id'] = stock_id
                    rows_to_update.append(row_dict)
                else:
                    # Will check by product_id + warehouse_id later
                    product_warehouse_pairs.add((mapped_data['product_id'], mapped_data['warehouse_id']))
                    rows_to_create.append(row_dict)
                
            except Exception as e:
                errors.append(f"Row {idx}: {str(e)}")
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
            existing_stock_by_pair = {(s.product_id, s.warehouse_id): s for s in existing_stocks}
        
        # Step 4: Separate creates and updates
        final_creates = []
        final_updates = []
        ledger_entries = []
        
        for row_dict in rows_to_create:
            pair = (row_dict['product_id'], row_dict['warehouse_id'])
            if pair in existing_stock_by_pair:
                # Move to updates
                row_dict['_existing_id'] = existing_stock_by_pair[pair].id
                final_updates.append(row_dict)
            else:
                final_creates.append(row_dict)
        
        for row_dict in rows_to_update:
            final_updates.append(row_dict)
        
        # Build existing stock map for ledger calculations
        existing_by_id = {**existing_stock_by_id}
        for stock in existing_stock_by_pair.values():
            existing_by_id[stock.id] = stock
        
        # Step 5: Bulk insert new records
        if final_creates:
            try:
                insert_data = [
                    {
                        'id': str(uuid.uuid4()) if not row.get('_stock_id') else row['_stock_id'],
                        'product_id': row['product_id'],
                        'warehouse_id': row['warehouse_id'],
                        'zone_id': row.get('zone_id'),
                        'quantity_on_hand': row['quantity_on_hand'],
                        'quantity_reserved': row['quantity_reserved'],
                        'quantity_available': row['quantity_available'],
                        'quantity_damaged': row.get('quantity_damaged', 0),
                        'reorder_point': row.get('reorder_point'),
                    }
                    for row in final_creates
                ]
                self.db.bulk_insert_mappings(Stock, insert_data)
                created = len(final_creates)
                
                # Add ledger entries for newly created stock records
                for row in insert_data:
                    previous_qty = 0
                    new_qty = row['quantity_on_hand']
                    quantity_change = new_qty - previous_qty
                    if quantity_change != 0:
                        ledger_entries.append({
                            'id': str(uuid.uuid4()),
                            'product_id': row['product_id'],
                            'warehouse_id': row['warehouse_id'],
                            'transaction_type': 'BULK_IMPORT',
                            'quantity_change': quantity_change,
                            'previous_quantity': previous_qty,
                            'new_quantity': new_qty,
                            'reference_type': 'bulk_import',
                            'reference_id': None,
                            'notes': 'Bulk import create',
                            'created_by': user_id
                        })
            except Exception as e:
                errors.append(f"Bulk insert error: {str(e)}")
        
        # Step 6: Bulk update existing records
        if final_updates:
            try:
                # Group updates by ID (if same ID appears multiple times, use the last one)
                update_dict = {}
                for row_dict in final_updates:
                    stock_id = row_dict['_existing_id']
                    qoh = row_dict.get('quantity_on_hand', 0) or 0
                    qres = row_dict.get('quantity_reserved', 0) or 0
                    qavail = row_dict.get('quantity_available', 0) or 0
                    
                    # Ensure quantity_available is calculated if not explicitly set
                    if qavail == 0 and qoh > 0:
                        qavail = qoh - qres
                    
                    # Always update with the latest values - ensure all fields are explicitly set
                    update_dict[stock_id] = {
                        'id': stock_id,
                        'zone_id': row_dict.get('zone_id'),
                        'quantity_on_hand': qoh,
                        'quantity_reserved': qres,
                        'quantity_available': qavail,  # Explicitly set
                        'quantity_damaged': row_dict.get('quantity_damaged', 0) or 0,
                        'reorder_point': row_dict.get('reorder_point'),
                    }
                
                update_data = list(update_dict.values())
                # Use bulk_update_mappings - ensure all fields are included
                # Note: bulk_update_mappings updates all provided fields
                self.db.bulk_update_mappings(Stock, update_data)
                updated = len(update_data)
                
                # Add ledger entries for updated stock records
                for update_row in update_data:
                    existing = existing_by_id.get(update_row['id'])
                    previous_qty = existing.quantity_on_hand if existing else 0
                    new_qty = update_row['quantity_on_hand']
                    quantity_change = new_qty - previous_qty
                    if quantity_change != 0:
                        ledger_entries.append({
                            'id': str(uuid.uuid4()),
                            'product_id': existing.product_id if existing else update_row.get('product_id'),
                            'warehouse_id': existing.warehouse_id if existing else update_row.get('warehouse_id'),
                            'transaction_type': 'BULK_IMPORT',
                            'quantity_change': quantity_change,
                            'previous_quantity': previous_qty,
                            'new_quantity': new_qty,
                            'reference_type': 'bulk_import',
                            'reference_id': update_row['id'],
                            'notes': 'Bulk import update',
                            'created_by': user_id
                        })
            except Exception as e:
                errors.append(f"Bulk update error: {str(e)}")
        
        # Step 7: Commit all changes
        try:
            if ledger_entries:
                self.db.bulk_insert_mappings(StockLedger, ledger_entries)
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            errors.append(f"Database error: {str(e)}")
        
        return {
            "created": created,
            "updated": updated,
            "errors": errors
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
