"""Inventory service for business logic."""
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, tuple_
from typing import Optional
import time
import uuid
from datetime import datetime
from app.models.inventory import Warehouse, StorageZone, Stock, StockBatch, StockLedger
from app.models.product import Product
from app.schemas.inventory import (
    WarehouseCreate, WarehouseUpdate, StorageZoneCreate, StorageZoneUpdate,
    StockCreate, StockUpdate, StockBatchCreate, StockBatchUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict, handle_validation_error
from app.services.import_log_service import ImportLogService
from app.services.identifier_resolver import resolve_identifier


def _resolve_stock_product_id(db: Session, product_id: Optional[str]) -> Optional[str]:
    """Map API product filter to ``Stock.product_id`` (UUID string).

    Accepts a UUID string or ``Product.product_code`` (case-insensitive exact match).
    Returns ``None`` if *product_id* is blank, or if a non-UUID value does not match any product.
    """
    if product_id is None:
        return None
    s = product_id.strip()
    if not s:
        return None
    try:
        return str(uuid.UUID(s))
    except ValueError:
        row = (
            db.query(Product.id)
            .filter(func.lower(Product.product_code) == s.lower())
            .first()
        )
        return str(row.id) if row else None


class WarehouseService:
    """Service for warehouse operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_warehouses(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        is_active: Optional[bool] = None,
        sort_field: Optional[str] = None,
        sort_dir: Optional[str] = None,
    ):
        """List warehouses. Supports sort by warehouse_code, warehouse_name, location, is_active, created_at, updated_at, zones_count, stock_count."""
        from sqlalchemy import select

        # Correlated count subqueries for derived columns (zones_count, stock_count).
        zones_count_sq = (
            select(func.count(StorageZone.id))
            .where(StorageZone.warehouse_id == Warehouse.id)
            .correlate(Warehouse)
            .scalar_subquery()
        )
        stock_count_sq = (
            select(func.count(Stock.id))
            .where(Stock.warehouse_id == Warehouse.id)
            .correlate(Warehouse)
            .scalar_subquery()
        )

        q = self.db.query(
            Warehouse,
            zones_count_sq.label("zones_count"),
            stock_count_sq.label("stock_count"),
        )

        if is_active is not None:
            q = q.filter(Warehouse.is_active == is_active)

        if query:
            q = q.filter(
                or_(
                    Warehouse.warehouse_code.ilike(f"%{query}%"),
                    Warehouse.warehouse_name.ilike(f"%{query}%"),
                )
            )

        sort_map = {
            "warehouse_code": Warehouse.warehouse_code,
            "warehouse_name": Warehouse.warehouse_name,
            "location": Warehouse.location,
            "is_active": Warehouse.is_active,
            "created_at": Warehouse.created_at,
            "updated_at": Warehouse.updated_at,
            "zones_count": zones_count_sq,
            "stock_count": stock_count_sq,
        }
        key = (sort_field or "created_at").strip()
        col = sort_map.get(key, Warehouse.created_at)
        direction = (sort_dir or "asc").lower()
        q = q.order_by(col.desc() if direction == "desc" else col.asc())

        total = q.with_entities(func.count(Warehouse.id)).order_by(None).scalar() or 0
        offset = (page - 1) * limit
        rows = q.offset(offset).limit(limit).all()

        warehouses = []
        for warehouse, zc, sc in rows:
            setattr(warehouse, "zones_count", zc or 0)
            setattr(warehouse, "stock_count", sc or 0)
            warehouses.append(warehouse)

        return {
            "data": warehouses,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    
    def get_warehouse(self, warehouse_id: str):
        """Get a warehouse by UUID or warehouse_code/name."""
        resolved_ids = resolve_identifier(
            self.db,
            warehouse_id,
            Warehouse,
            code_fields=("warehouse_code", "warehouse_name"),
        )
        if not resolved_ids:
            raise handle_not_found("Warehouse", warehouse_id)
        warehouse = self.db.query(Warehouse).filter(Warehouse.id.in_(resolved_ids)).first()
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
        new_code = update_data.get("warehouse_code")
        if new_code is not None:
            new_code = (new_code or "").strip()
            if not new_code:
                raise handle_validation_error("Warehouse code cannot be empty.")
            if new_code != (warehouse.warehouse_code or "").strip():
                taken = (
                    self.db.query(Warehouse)
                    .filter(
                        Warehouse.warehouse_code == new_code,
                        Warehouse.id != warehouse_id,
                    )
                    .first()
                )
                if taken:
                    raise handle_conflict("Warehouse code already exists.")
            update_data["warehouse_code"] = new_code

        for key, value in update_data.items():
            setattr(warehouse, key, value)

        self.db.commit()
        self.db.refresh(warehouse)
        return warehouse

    def delete_warehouse(self, warehouse_id: str) -> dict:
        """Hard delete one warehouse by id (UUID or code/name). 409 if referenced by stock/zones/etc."""
        from sqlalchemy.exc import IntegrityError
        warehouse = self.get_warehouse(warehouse_id)
        wid = warehouse.id
        try:
            self.db.delete(warehouse)
            self.db.commit()
        except IntegrityError as ex:
            self.db.rollback()
            raise handle_conflict(
                "Warehouse has linked stock, zones, allocations, or picking lines. "
                "Remove or reassign them before deleting."
            ) from ex
        return {"id": wid, "message": "Warehouse deleted."}

    def bulk_delete_warehouses(self, warehouse_ids: list[str]) -> dict:
        """Delete multiple warehouses by id. Returns deleted_count, failed[], message."""
        from sqlalchemy.exc import IntegrityError
        if not warehouse_ids:
            return {"deleted_count": 0, "failed": [], "message": "No warehouses to delete."}

        # Resolve mixed UUIDs/codes/names → UUIDs.
        resolved: list[str] = []
        unresolved: list[str] = []
        for raw in warehouse_ids:
            ids = resolve_identifier(
                self.db,
                raw,
                Warehouse,
                code_fields=("warehouse_code", "warehouse_name"),
            )
            if ids:
                resolved.extend(ids)
            else:
                unresolved.append(raw)
        resolved = list(dict.fromkeys(resolved))

        failed: list[dict] = [{"id": raw, "reason": "not found"} for raw in unresolved]
        deleted_count = 0
        # Delete one-by-one so FK conflicts surface per-row instead of aborting whole batch.
        for wid in resolved:
            row = self.db.query(Warehouse).filter(Warehouse.id == wid).first()
            if not row:
                failed.append({"id": wid, "reason": "not found"})
                continue
            try:
                self.db.delete(row)
                self.db.flush()
                deleted_count += 1
            except IntegrityError as ex:
                self.db.rollback()
                failed.append({"id": wid, "reason": "referenced by stock / zones / allocations"})
            except Exception as ex:
                self.db.rollback()
                failed.append({"id": wid, "reason": str(ex)})
        self.db.commit()
        return {
            "deleted_count": deleted_count,
            "failed": failed,
            "message": f"Deleted {deleted_count} warehouse(s); {len(failed)} failed."
            if failed
            else f"Deleted {deleted_count} warehouse(s).",
        }

    def bulk_import_warehouses(
        self,
        rows: list[dict],
        user_id: str,
        validate_only: bool = False,
    ):
        """Upsert warehouses from Excel data, keyed by warehouse_code (case-insensitive).

        Column mapping (Excel header → DB field):
          - "Sytem Location" / "System Location" / "warehouse_code" → warehouse_code
          - "System Location Descriptions" / "System Location Description" / "warehouse_name" → warehouse_name
          - "Warehouse Location" / "location" → location
          - "Status" / "is_active" → is_active (Active|true → True; Inactive|false → False)

        Returns dict with created/updated/skipped counts + errors/warnings; if
        validate_only=True returns valid/errors/warnings/summary without writes.
        """
        column_mapping = {
            "Sytem Location": "warehouse_code",
            "System Location": "warehouse_code",
            "system location": "warehouse_code",
            "warehouse_code": "warehouse_code",
            "Warehouse Code": "warehouse_code",
            "Code": "warehouse_code",
            "code": "warehouse_code",
            "System Location Descriptions": "warehouse_name",
            "System Location Description": "warehouse_name",
            "system location description": "warehouse_name",
            "Description": "warehouse_name",
            "description": "warehouse_name",
            "warehouse_name": "warehouse_name",
            "Warehouse Name": "warehouse_name",
            "Warehouse Location": "location",
            "warehouse location": "location",
            "Location": "location",
            "location": "location",
            "Status": "is_active",
            "status": "is_active",
            "Active": "is_active",
            "is_active": "is_active",
        }

        def _norm_status(value) -> Optional[bool]:
            if value is None:
                return None
            if isinstance(value, bool):
                return value
            s = str(value).strip().lower()
            if not s:
                return None
            if s in {"active", "true", "1", "yes", "y", "enabled"}:
                return True
            if s in {"inactive", "false", "0", "no", "n", "disabled"}:
                return False
            return None

        def _map_row(raw: dict) -> dict:
            mapped: dict = {}
            for raw_key, value in raw.items():
                key = str(raw_key).strip()
                db_key = column_mapping.get(key) or column_mapping.get(key.lower())
                if db_key is None:
                    norm = key.lower().replace(" ", "")
                    for ck, cv in column_mapping.items():
                        if ck.lower().replace(" ", "") == norm:
                            db_key = cv
                            break
                if db_key is None:
                    continue
                if isinstance(value, str):
                    value = value.strip()
                if value == "":
                    value = None
                if db_key == "is_active":
                    value = _norm_status(value)
                mapped[db_key] = value
            return mapped

        errors: list[str] = []
        warnings: list[dict] = []
        created = 0
        updated = 0
        skipped = 0
        import_session_id = str(uuid.uuid4())

        # Pass 1: parse + validate; collect codes for bulk lookup.
        parsed: list[tuple[int, dict]] = []
        codes_seen: dict[str, int] = {}
        for idx, raw in enumerate(rows, start=1):
            row = _map_row(raw)
            code = row.get("warehouse_code")
            if not code:
                errors.append(f"Row {idx}: missing warehouse_code / Sytem Location.")
                continue
            code = str(code).strip()
            row["warehouse_code"] = code
            key = code.lower()
            if key in codes_seen:
                warnings.append({
                    "row": idx,
                    "message": f"Duplicate warehouse_code '{code}' (first at row {codes_seen[key]}); later row wins.",
                })
            codes_seen[key] = idx
            parsed.append((idx, row))

        if not parsed:
            result = {
                "valid": len(errors) == 0,
                "created": 0,
                "updated": 0,
                "skipped": skipped,
                "errors": errors,
                "warnings": warnings,
                "import_session_id": import_session_id,
                "summary": {"rows": len(rows), "parsed": 0},
            }
            return result

        # Bulk lookup existing by code (case-insensitive).
        all_codes = [r["warehouse_code"] for _, r in parsed]
        existing = self.db.query(Warehouse).filter(
            func.lower(Warehouse.warehouse_code).in_([c.lower() for c in all_codes])
        ).all()
        existing_by_code = {w.warehouse_code.lower(): w for w in existing}

        if validate_only:
            for idx, row in parsed:
                if row["warehouse_code"].lower() in existing_by_code:
                    warnings.append({"row": idx, "message": f"Will update existing warehouse '{row['warehouse_code']}'."})
                else:
                    warnings.append({"row": idx, "message": f"Will create new warehouse '{row['warehouse_code']}'."})
            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "summary": {
                    "rows": len(rows),
                    "parsed": len(parsed),
                    "to_update": sum(1 for _, r in parsed if r["warehouse_code"].lower() in existing_by_code),
                    "to_create": sum(1 for _, r in parsed if r["warehouse_code"].lower() not in existing_by_code),
                },
                "import_session_id": import_session_id,
            }

        # Pass 2: apply upsert. Later duplicate wins (overwrite earlier).
        seen_keys: set[str] = set()
        for idx, row in parsed:
            key = row["warehouse_code"].lower()
            target = existing_by_code.get(key)
            try:
                if target is not None:
                    for col in ("warehouse_code", "warehouse_name", "location", "is_active"):
                        if col in row and row[col] is not None:
                            setattr(target, col, row[col])
                    if key not in seen_keys:
                        updated += 1
                else:
                    new = Warehouse(
                        warehouse_code=row["warehouse_code"],
                        warehouse_name=row.get("warehouse_name"),
                        location=row.get("location"),
                        is_active=row["is_active"] if row.get("is_active") is not None else True,
                    )
                    self.db.add(new)
                    existing_by_code[key] = new
                    if key not in seen_keys:
                        created += 1
                seen_keys.add(key)
            except Exception as ex:
                errors.append(f"Row {idx}: {ex}")
                skipped += 1

        try:
            self.db.commit()
        except Exception as ex:
            self.db.rollback()
            errors.append(f"Commit failed: {ex}")
            return {
                "valid": False,
                "created": 0,
                "updated": 0,
                "skipped": len(parsed),
                "errors": errors,
                "warnings": warnings,
                "import_session_id": import_session_id,
            }

        return {
            "valid": len(errors) == 0,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "warnings": warnings,
            "import_session_id": import_session_id,
        }


class StorageZoneService:
    """Service for storage zone operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_zones(self, warehouse_id: Optional[str] = None, page: int = 1, limit: int = 50):
        """List storage zones."""
        q = self.db.query(StorageZone)

        warehouse_ids = resolve_identifier(
            self.db,
            warehouse_id,
            Warehouse,
            code_fields=("warehouse_code", "warehouse_name"),
        )
        if warehouse_ids is not None:
            if not warehouse_ids:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            q = q.filter(StorageZone.warehouse_id.in_(warehouse_ids))

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
        warehouse_ids = resolve_identifier(
            self.db,
            warehouse_id,
            Warehouse,
            code_fields=("warehouse_code", "warehouse_name"),
        )
        if warehouse_ids is not None:
            if not warehouse_ids:
                return []
            q = q.filter(StorageZone.warehouse_id.in_(warehouse_ids))
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
        ).filter(Stock.warehouse.has(Warehouse.is_active.is_(True)))

        warehouse_ids = resolve_identifier(
            self.db,
            warehouse_id,
            Warehouse,
            code_fields=("warehouse_code", "warehouse_name"),
        )
        if warehouse_ids is not None:
            if not warehouse_ids:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            q = q.filter(Stock.warehouse_id.in_(warehouse_ids))

        if product_id:
            resolved_pid = _resolve_stock_product_id(self.db, product_id)
            if resolved_pid is None:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            q = q.filter(Stock.product_id == resolved_pid)

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

    def bulk_delete_stock(self, stock_ids: list[str]) -> dict:
        """Delete multiple stock records by id. Returns deleted_count and message."""
        if not stock_ids:
            return {"deleted_count": 0, "message": "No stock records to delete."}
        deleted = self.db.query(Stock).filter(Stock.id.in_(stock_ids)).delete(synchronize_session=False)
        self.db.commit()
        return {"deleted_count": deleted, "message": f"Deleted {deleted} stock record(s)."}

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
        ).filter(StockLedger.warehouse.has(Warehouse.is_active.is_(True)))
        if product_id:
            resolved_pid = _resolve_stock_product_id(self.db, product_id)
            if resolved_pid is None:
                return ListResponse(
                    data=[],
                    pagination={"total": 0, "page": page, "limit": limit},
                )
            q = q.filter(StockLedger.product_id == resolved_pid)
        warehouse_ids = resolve_identifier(
            self.db,
            warehouse_id,
            Warehouse,
            code_fields=("warehouse_code", "warehouse_name"),
        )
        if warehouse_ids is not None:
            if not warehouse_ids:
                return ListResponse(
                    data=[],
                    pagination={"total": 0, "page": page, "limit": limit},
                )
            q = q.filter(StockLedger.warehouse_id.in_(warehouse_ids))
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

        resolved_pid = _resolve_stock_product_id(self.db, product_id)
        if resolved_pid is None:
            return ListResponse(
                data=[],
                pagination={"total": 0, "page": page, "limit": limit},
            )

        warehouse_ids = resolve_identifier(
            self.db,
            warehouse_id,
            Warehouse,
            code_fields=("warehouse_code", "warehouse_name"),
        )
        if warehouse_ids is None or not warehouse_ids:
            return ListResponse(
                data=[],
                pagination={"total": 0, "page": page, "limit": limit},
            )

        q = self.db.query(StockLedger).options(
            selectinload(StockLedger.product),
            selectinload(StockLedger.warehouse)
        ).filter(
            StockLedger.product_id == resolved_pid,
            StockLedger.warehouse_id.in_(warehouse_ids),
            StockLedger.warehouse.has(Warehouse.is_active.is_(True)),
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
        ).filter(Stock.warehouse.has(Warehouse.is_active.is_(True)))
        
        warehouse_ids = resolve_identifier(
            self.db,
            warehouse_id,
            Warehouse,
            code_fields=("warehouse_code", "warehouse_name"),
        )
        if warehouse_ids is not None:
            if not warehouse_ids:
                return []
            q = q.filter(Stock.warehouse_id.in_(warehouse_ids))
        
        if product_id:
            resolved_pid = _resolve_stock_product_id(self.db, product_id)
            if resolved_pid is None:
                return []
            q = q.filter(Stock.product_id == resolved_pid)
        
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

    def bulk_import_stock(self, stock_data: list[dict], user_id: str, validate_only: bool = False):
        """Bulk import stock from Excel data using bulk operations for performance.

        Args:
            stock_data: List of dictionaries containing stock data from Excel
            user_id: ID of the user performing the import
            validate_only: If True, run validation only (no DB writes); return errors/warnings.

        Returns:
            dict with created, updated, skipped counts and errors; if validate_only, valid/errors/warnings/summary.
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
            pair_list = list(product_warehouse_pairs)
            existing_stocks: list[Stock] = []
            # Chunk to keep IN list manageable for very large imports
            for chunk_start in range(0, len(pair_list), 1000):
                chunk = pair_list[chunk_start:chunk_start + 1000]
                stocks_chunk = self.db.query(Stock).filter(
                    tuple_(Stock.product_id, Stock.warehouse_id).in_(chunk)
                ).all()
                existing_stocks.extend(stocks_chunk)
            existing_stock_by_pair = {(str(s.product_id), str(s.warehouse_id)): s for s in existing_stocks}
        
        # Step 4: Separate creates and updates (new stock records are created automatically)
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
                # Create new stock record for this product + warehouse
                final_creates.append(row_dict)

        for row_dict in rows_to_update:
            final_updates.append(row_dict)

        create_dict = {}
        for row_dict in final_creates:
            pair = (str(row_dict['product_id']), str(row_dict['warehouse_id']))
            create_dict[pair] = row_dict

        seen_stock_pairs = {
            (str(r['product_id']), str(r['warehouse_id']))
            for r in [*create_dict.values(), *final_updates]
        }

        # Find stocks "missing from import" (will be system-adjusted to 0).
        # Pulling seen_stock_pairs into SQL as a tuple-NOT-IN explodes parameter
        # count (>20k params on a full snapshot) and produces a pathological plan;
        # SELECT all candidates and set-diff in Python instead.
        zero_q = self.db.query(Stock).filter(
            Stock.warehouse.has(Warehouse.is_active.is_(True)),
            Stock.quantity_on_hand != 0,
        )
        all_zero_candidates: list[Stock] = zero_q.all()
        seen_set = seen_stock_pairs  # already string-tuple keys
        stocks_to_zero_cached: list[Stock] = [
            s for s in all_zero_candidates
            if (str(s.product_id), str(s.warehouse_id)) not in seen_set
        ]
        snapshot_zero_count = len(stocks_to_zero_cached)
        if validate_only:
            # Don't need the instance refs further in validate-only path.
            stocks_to_zero_cached = []

        if validate_only:
            warnings_str = [
                f"Row {w.get('row', '?')}: {w.get('product_code', '-')} / {w.get('warehouse', '-')}: {w.get('reason', '')}"
                for w in warnings
            ]
            # Dedupe creates by (product_id, warehouse_id) for count
            create_keys = {(str(r['product_id']), str(r['warehouse_id'])) for r in final_creates}
            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings_str,
                "summary": {
                    "total_rows": len(stock_data),
                    "would_create": len(create_keys),
                    "would_update": len(final_updates),
                    "would_system_adjust_to_zero": snapshot_zero_count,
                    "would_skip": skipped_rows,
                    "error_count": len(errors),
                },
            }

        # Build existing stock map for ledger calculations
        existing_by_id = {**existing_stock_by_id}
        for stock in existing_stock_by_pair.values():
            existing_by_id[stock.id] = stock
        
        now = datetime.utcnow()

        # Step 5: Create new stock records (dedupe by product_id + warehouse_id, last wins).
        # Stock.id has a python-side UUID default, so ids are assigned at construction
        # time — no per-row flush needed. Build all instances, add together, single flush.
        if create_dict:
            try:
                new_stocks: list[tuple[Stock, int]] = []
                for (_pid, _wid), row_dict in create_dict.items():
                    qoh = row_dict.get('quantity_on_hand', 0) or 0
                    qres = row_dict.get('quantity_reserved', 0) or 0
                    new_stock = Stock(
                        product_id=row_dict['product_id'],
                        warehouse_id=row_dict['warehouse_id'],
                        zone_id=row_dict.get('zone_id'),
                        quantity_on_hand=qoh,
                        quantity_reserved=qres,
                        quantity_damaged=row_dict.get('quantity_damaged', 0) or 0,
                        reorder_point=row_dict.get('reorder_point'),
                        updated_at=now,
                    )
                    new_stocks.append((new_stock, qoh))

                self.db.add_all(s for s, _ in new_stocks)
                self.db.flush()

                for new_stock, qoh in new_stocks:
                    if qoh != 0:
                        ledger_entries.append({
                            'id': str(uuid.uuid4()),
                            'product_id': new_stock.product_id,
                            'warehouse_id': new_stock.warehouse_id,
                            'transaction_type': 'BULK_IMPORT',
                            'quantity_change': qoh,
                            'previous_quantity': 0,
                            'new_quantity': qoh,
                            'reference_type': 'bulk_import',
                            'reference_id': new_stock.id,
                            'notes': 'Bulk import (new stock record)',
                            'created_by': user_id,
                        })
                created = len(create_dict)
            except Exception as e:
                message = f"Bulk create error: {str(e)}"
                errors.append(message)
                error_records.append({"row": None, "error": message, "data": None})
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
                    stock.updated_at = now
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

        system_adjusted_to_zero = 0
        try:
            stocks_to_zero = stocks_to_zero_cached
            for stock in stocks_to_zero:
                previous_qty = stock.quantity_on_hand or 0
                if previous_qty == 0:
                    continue
                stock.quantity_on_hand = 0
                stock.quantity_reserved = 0
                stock.quantity_damaged = 0
                stock.updated_at = now
                self.db.add(stock)
                ledger_entries.append({
                    'id': str(uuid.uuid4()),
                    'product_id': stock.product_id,
                    'warehouse_id': stock.warehouse_id,
                    'transaction_type': 'SYSTEM_ADJUSTMENT',
                    'quantity_change': -previous_qty,
                    'previous_quantity': previous_qty,
                    'new_quantity': 0,
                    'reference_type': 'stock_snapshot_import',
                    'reference_id': import_session_id,
                    'notes': 'System adjustment: missing from full stock import; set on-hand quantity to 0',
                    'created_by': user_id
                })
                system_adjusted_to_zero += 1
        except Exception as e:
            message = f"Snapshot zero-adjustment error: {str(e)}"
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
                    skipped_rows=skipped_rows + system_adjusted_to_zero,
                    warnings=warnings,
                    errors=error_records,
                    summary={"system_adjusted_to_zero": system_adjusted_to_zero},
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
            "warnings": warnings,
            "system_adjusted_to_zero": system_adjusted_to_zero,
        }
    
    def get_stock(self, stock_id: str):
        """Get stock by ID."""
        stock = self.db.query(Stock).filter(
            Stock.id == stock_id,
            Stock.warehouse.has(Warehouse.is_active.is_(True)),
        ).first()
        if not stock:
            raise handle_not_found("Stock", stock_id)
        return stock
    
    def get_stock_dashboard(self, limit: int = 10):
        """Stock dashboard sourced from the `stock` table (same source as the Stock listing UI).

        `limit` caps the size of every list returned (top warehouses, top low-stock rows).
        Hard-bounded to [1, 50] inside the call. Counts/totals are NOT affected by `limit`.

        StockBatch is only populated when batch-tracking is in use; the previous implementation
        summed StockBatch.quantity which produced zeros for every account that doesn't track
        batches. Source-of-truth for on-hand quantity is `Stock.quantity_on_hand`.
        """
        from datetime import datetime, timedelta

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))

        active_wh = Stock.warehouse.has(Warehouse.is_active.is_(True))

        total_skus = (
            self.db.query(func.count(func.distinct(Stock.product_id)))
            .filter(active_wh)
            .scalar()
            or 0
        )

        total_quantity = (
            self.db.query(func.coalesce(func.sum(Stock.quantity_on_hand), 0))
            .filter(active_wh)
            .scalar()
            or 0
        )

        # Per-warehouse aggregation (top N by on-hand)
        wh_rows = (
            self.db.query(
                Warehouse.id.label("warehouse_id"),
                Warehouse.warehouse_code.label("warehouse_code"),
                Warehouse.warehouse_name.label("warehouse_name"),
                func.coalesce(func.sum(Stock.quantity_on_hand), 0).label("on_hand"),
                func.coalesce(func.sum(Stock.quantity_reserved), 0).label("reserved"),
                func.coalesce(func.sum(Stock.quantity_available), 0).label("available"),
                func.count(func.distinct(Stock.product_id)).label("sku_count"),
            )
            .join(Stock, Stock.warehouse_id == Warehouse.id)
            .filter(Warehouse.is_active.is_(True))
            .group_by(Warehouse.id, Warehouse.warehouse_code, Warehouse.warehouse_name)
            .order_by(func.sum(Stock.quantity_on_hand).desc())
            .limit(limit)
            .all()
        )
        stock_by_warehouse = [
            {
                "warehouse_id": str(r.warehouse_id),
                "warehouse_code": r.warehouse_code,
                "warehouse_name": r.warehouse_name,
                "quantity_on_hand": int(r.on_hand or 0),
                "quantity_reserved": int(r.reserved or 0),
                "quantity_available": int(r.available or 0),
                "sku_count": int(r.sku_count or 0),
            }
            for r in wh_rows
        ]

        # 30-day movement from stock_ledger (net change per day)
        since = datetime.utcnow() - timedelta(days=30)
        movement_rows = (
            self.db.query(
                func.date(StockLedger.created_at).label("day"),
                func.coalesce(func.sum(StockLedger.quantity_change), 0).label("net_change"),
                func.count(StockLedger.id).label("txn_count"),
            )
            .filter(StockLedger.created_at >= since)
            .group_by(func.date(StockLedger.created_at))
            .order_by(func.date(StockLedger.created_at).asc())
            .all()
        )
        stock_movement_30_days = [
            {
                "date": r.day.isoformat() if hasattr(r.day, "isoformat") else str(r.day),
                "net_change": int(r.net_change or 0),
                "transaction_count": int(r.txn_count or 0),
            }
            for r in movement_rows
        ]

        # Current Stock List attachment (singleton; matches /resources/attachments/current-stock-list).
        # Stock imports upload a single "Stock List" file; previous versions are soft-deleted, so
        # this returns only the newest non-archived row. Provides a signed download URL.
        from app.models.resources import Attachment, AttachmentType
        from app.services.storage_router import resolve_signed_url

        latest_stock_list_attachment = None
        stock_list_type = (
            self.db.query(AttachmentType)
            .filter(AttachmentType.type_name.in_(("Stock List", "Stock_List")))
            .first()
        )
        if stock_list_type is not None:
            attachment = (
                self.db.query(Attachment)
                .filter(
                    Attachment.attachment_type_id == str(stock_list_type.id),
                    Attachment.is_deleted.is_(False),
                )
                .order_by(Attachment.uploaded_at.desc())
                .first()
            )
            if attachment is not None:
                try:
                    signed_url = resolve_signed_url(
                        attachment.file_path,
                        provider=getattr(attachment, "storage_provider", None),
                    )
                except Exception:
                    signed_url = attachment.file_path
                latest_stock_list_attachment = {
                    "id": str(attachment.id),
                    "original_filename": attachment.original_filename,
                    "stored_filename": attachment.stored_filename,
                    "file_size_bytes": attachment.file_size_bytes,
                    "mime_type": attachment.mime_type,
                    "uploaded_at": attachment.uploaded_at.isoformat() if attachment.uploaded_at else None,
                    "uploaded_by": attachment.uploaded_by,
                    "description": attachment.description,
                    "file_path": signed_url,
                    "storage_provider": getattr(attachment, "storage_provider", None),
                }

        return {
            "total_skus": int(total_skus),
            "total_quantity": int(total_quantity),
            "stock_by_warehouse": stock_by_warehouse,
            "stock_movement_30_days": stock_movement_30_days,
            "latest_stock_list_attachment": latest_stock_list_attachment,
            "limit": limit,
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
        q = self.db.query(StockBatch).filter(
            StockBatch.warehouse.has(Warehouse.is_active.is_(True))
        )
        
        if product_id:
            resolved_pid = _resolve_stock_product_id(self.db, product_id)
            if resolved_pid is None:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            q = q.filter(StockBatch.product_id == resolved_pid)
        warehouse_ids = resolve_identifier(
            self.db,
            warehouse_id,
            Warehouse,
            code_fields=("warehouse_code", "warehouse_name"),
        )
        if warehouse_ids is not None:
            if not warehouse_ids:
                return {
                    "data": [],
                    "pagination": {"total": 0, "page": page, "limit": limit},
                    "empty": True,
                }
            q = q.filter(StockBatch.warehouse_id.in_(warehouse_ids))
        
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
        batch = self.db.query(StockBatch).filter(
            StockBatch.id == batch_id,
            StockBatch.warehouse.has(Warehouse.is_active.is_(True)),
        ).first()
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
