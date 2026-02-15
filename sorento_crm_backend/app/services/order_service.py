"""Order service for business logic."""
import logging
import uuid
import time
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from decimal import Decimal
from app.models.order import Order, OrderStatus, Customer
from app.schemas.order import (
    OrderCreate, OrderUpdate, CustomerCreate, CustomerUpdate,
    OrderStatusCreate, OrderStatusUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict
from app.services.import_log_service import ImportLogService
from app.services.calendar_service import CalendarService

logger = logging.getLogger(__name__)


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
    
    def _get_order_any(self, order_id: str):
        """Get order by ID including archived."""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise handle_not_found("Order", order_id)
        return order

    def archive_order(self, order_id: str):
        """Archive an order (soft delete). Data remains for retention."""
        from datetime import datetime, timezone
        order = self.get_order(order_id)
        order.deleted_at = datetime.now(timezone.utc)
        self.db.commit()
        return {"message": "Order archived successfully"}

    def restore_order(self, order_id: str):
        """Restore an archived order."""
        order = self._get_order_any(order_id)
        if order.deleted_at is None:
            raise handle_conflict("Order is not archived")
        order.deleted_at = None
        self.db.commit()
        return {"message": "Order restored successfully"}

    def delete_order(self, order_id: str):
        """Hard delete an order (permanent). Use archive for retention."""
        order = self._get_order_any(order_id)
        self.db.delete(order)
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
        warnings = []
        
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

    def import_excel_tracking(self, file_data: bytes, user_id: str):
        """Import orders from Excel file with Master and Daily Tracking sheets."""
        from io import BytesIO
        from datetime import datetime, date, time as dt_time, timedelta
        import openpyxl
        from decimal import Decimal

        created = 0
        updated = 0
        errors = []
        warnings = []
        kpi_warnings = []
        import_session_id = str(uuid.uuid4())
        start_time = time.monotonic()
        master_rows = 0
        tracking_rows = 0
        calendar_service = CalendarService(self.db)

        try:
            workbook = openpyxl.load_workbook(BytesIO(file_data), data_only=True)
        except Exception as exc:
            raise ValueError(f"Failed to read Excel file: {exc}") from exc

        logger.info("Order tracking import: opened workbook, sheets=%s", workbook.sheetnames)

        required_sheets = {"Master", "Daily Tracking"}
        if not required_sheets.issubset(set(workbook.sheetnames)):
            missing = required_sheets.difference(set(workbook.sheetnames))
            raise ValueError(f"Missing required sheet(s): {', '.join(sorted(missing))}")

        master_sheet = workbook["Master"]
        tracking_sheet = workbook["Daily Tracking"]

        master_mapping = {
            "Doc. No.": "order_number",
            "Date": "order_date",
            "Created Time": "created_time",
            "Debtor Code": "debtor_code",
            "Debtor Name": "debtor_name",
            "Agent": "agent",
            "Cancel": "is_cancelled",
            "Remarks CS": "remarks_cs",
            "Type": "order_type",
        }

        tracking_mapping = {
            "Doc Number": "order_number",
            "Doc No.": "order_number",
            "Date": "actual_delivery_date",
            "Delivery Date": "actual_delivery_date",
            "Time": "delivery_time",
            "Checker": "checker",
            "Transporter": "transporter",
            "Driver Name": "driver_name",
            "Lorry Plate": "lorry_plate",
            "Customer": "customer_ref",
            "Remarks CS": "delivery_remarks_cs",
            "Remarks": "delivery_remarks",
            "Salesman": "salesman",
            "Trips": "trips",
            "W/H": "warehouse",
            "Doc Date": "doc_date",
        }

        def normalize_header(value):
            return str(value).strip() if value is not None else ""

        def iter_sheet_rows(sheet, sheet_name_for_log=""):
            headers = [normalize_header(cell.value) for cell in sheet[1]]
            if sheet_name_for_log:
                logger.info("Order tracking import: sheet %r headers (row 1)=%s", sheet_name_for_log, headers)
            for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                if not any(cell is not None and str(cell).strip() for cell in row):
                    continue
                row_data = {}
                for idx, value in enumerate(row):
                    header = headers[idx] if idx < len(headers) else ""
                    if header:
                        row_data[header] = value
                yield row_idx, row_data

        def chunked(values, size):
            for i in range(0, len(values), size):
                yield values[i:i + size]

        def normalize_order_number(value):
            if value is None:
                return ""
            return str(value).strip()

        master_rows_list = list(iter_sheet_rows(master_sheet, "Master"))
        tracking_rows_list = list(iter_sheet_rows(tracking_sheet, "Daily Tracking"))
        master_rows = len(master_rows_list)
        tracking_rows = len(tracking_rows_list)

        master_order_numbers = {
            normalize_order_number(row_data.get("Doc. No.")).lower()
            for _, row_data in master_rows_list
            if normalize_order_number(row_data.get("Doc. No."))
        }
        tracking_order_numbers = {
            normalize_order_number(row_data.get("Doc Number") or row_data.get("Doc No.")).lower()
            for _, row_data in tracking_rows_list
            if normalize_order_number(row_data.get("Doc Number") or row_data.get("Doc No."))
        }
        all_order_numbers = master_order_numbers.union(tracking_order_numbers)

        existing_orders = {}
        if all_order_numbers:
            for number_chunk in chunked(sorted(all_order_numbers), 500):
                orders = self.db.query(Order).filter(
                    func.lower(Order.order_number).in_(number_chunk),
                    Order.deleted_at.is_(None)
                ).all()
                for order in orders:
                    if order.order_number:
                        existing_orders[order.order_number.lower()] = order

        def parse_date_value(value, doc_date_value=None):
            if value is None or value == "":
                return None
            if isinstance(value, datetime):
                return value
            if isinstance(value, date):
                return datetime.combine(value, dt_time.min)
            if isinstance(value, str):
                cleaned = value.strip()
                for fmt in ["%d/%m/%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        return datetime.strptime(cleaned, fmt)
                    except ValueError:
                        continue
                try:
                    parsed = datetime.strptime(cleaned, "%d-%b")
                    year = doc_date_value.year if isinstance(doc_date_value, (datetime, date)) else datetime.now().year
                    return parsed.replace(year=year)
                except ValueError:
                    return None
            return None

        def parse_time_value(value):
            if value is None or value == "":
                return None
            if isinstance(value, dt_time):
                return value
            if isinstance(value, datetime):
                return value.time()
            if isinstance(value, str):
                cleaned = value.strip()
                for fmt in ["%I:%M %p", "%I:%M%p", "%H:%M", "%H:%M:%S"]:
                    try:
                        return datetime.strptime(cleaned, fmt).time()
                    except ValueError:
                        continue
            return None

        def parse_bool(value):
            if value is None or value == "":
                return False
            if isinstance(value, bool):
                return value
            return str(value).strip().upper() not in {"F", "FALSE", "0", "NO", "N"}

        def json_safe(value):
            if isinstance(value, (datetime, date, dt_time)):
                return value.isoformat()
            if isinstance(value, Decimal):
                return float(value)
            if isinstance(value, dict):
                return {str(k): json_safe(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [json_safe(v) for v in value]
            return value

        working_weekdays = calendar_service.get_working_weekdays()

        mapped_master_rows = []
        min_master_date = None
        max_master_date = None

        # Process Master sheet
        for row_idx, row_data in master_rows_list:
            try:
                mapped = {}
                for header, value in row_data.items():
                    if header not in master_mapping:
                        continue
                    db_key = master_mapping[header]
                    if db_key in {"order_date", "created_time"}:
                        mapped[db_key] = parse_date_value(value)
                    elif db_key == "is_cancelled":
                        mapped[db_key] = parse_bool(value)
                    else:
                        mapped[db_key] = str(value).strip() if value is not None else None

                order_number = (mapped.get("order_number") or "").strip()
                if not order_number:
                    errors.append({"row": row_idx, "error": "Doc. No. is required", "data": row_data})
                    continue
                mapped["order_number"] = order_number
                order_date_value = mapped.get("order_date")
                if isinstance(order_date_value, (datetime, date)):
                    date_value = order_date_value.date() if isinstance(order_date_value, datetime) else order_date_value
                    min_master_date = date_value if min_master_date is None else min(min_master_date, date_value)
                    max_master_date = date_value if max_master_date is None else max(max_master_date, date_value)
                mapped_master_rows.append((row_idx, row_data, mapped))
            except Exception as exc:
                errors.append({"row": row_idx, "error": str(exc), "data": row_data})

        holidays_master = set()
        if min_master_date and max_master_date:
            holidays_master = calendar_service.get_public_holidays_between(
                min_master_date,
                max_master_date + timedelta(days=30),
            )

        for row_idx, row_data, mapped in mapped_master_rows:
            try:
                if mapped.get("order_date"):
                    mapped["promised_delivery_date"] = calendar_service.add_business_days(
                        mapped["order_date"],
                        2,
                        working_weekdays=working_weekdays,
                        holidays=holidays_master,
                    )

                order_number = mapped["order_number"]
                existing_order = existing_orders.get(order_number.lower())

                if existing_order:
                    for key, value in mapped.items():
                        if key != "order_number":
                            setattr(existing_order, key, value)
                    existing_order.updated_by = user_id
                    updated += 1
                else:
                    mapped["created_by"] = user_id
                    order = Order(**mapped)
                    self.db.add(order)
                    created += 1
                    existing_orders[order_number.lower()] = order
            except Exception as exc:
                errors.append({"row": row_idx, "error": str(exc), "data": row_data})

        tracking_updates = []
        min_tracking_date = None
        max_tracking_date = None

        # Process Daily Tracking sheet
        for row_idx, row_data in tracking_rows_list:
            try:
                mapped = {}
                doc_date_value = None
                for header, value in row_data.items():
                    if header not in tracking_mapping:
                        continue
                    db_key = tracking_mapping[header]
                    if db_key == "doc_date":
                        doc_date_value = parse_date_value(value)
                        continue
                    if db_key == "actual_delivery_date":
                        mapped[db_key] = parse_date_value(value, doc_date_value=doc_date_value)
                    elif db_key == "trips":
                        mapped[db_key] = int(value) if value not in (None, "") else None
                    else:
                        mapped[db_key] = str(value).strip() if value is not None else None

                order_number = (mapped.get("order_number") or "").strip()
                if not order_number:
                    errors.append({"row": row_idx, "error": "Doc Number is required", "data": row_data})
                    continue

                order = existing_orders.get(order_number.lower())
                if not order:
                    warnings.append({"row": row_idx, "warning": f"Order '{order_number}' not found in Master sheet", "data": row_data})
                    continue

                delivery_date = mapped.get("actual_delivery_date")
                delivery_time = parse_time_value(row_data.get("Time"))
                if delivery_date:
                    if delivery_time:
                        mapped["actual_delivery_date"] = datetime.combine(
                            delivery_date.date() if isinstance(delivery_date, datetime) else delivery_date,
                            delivery_time,
                        )
                    else:
                        # Date only: store as midnight for DateTime column
                        d = delivery_date.date() if isinstance(delivery_date, datetime) else delivery_date
                        mapped["actual_delivery_date"] = datetime.combine(d, dt_time.min)
                    delivery_date = mapped["actual_delivery_date"]

                for key, value in mapped.items():
                    if key != "order_number":
                        setattr(order, key, value)

                if order.order_date and delivery_date:
                    start_date_value = order.order_date.date() if isinstance(order.order_date, datetime) else order.order_date
                    end_date_value = delivery_date.date() if isinstance(delivery_date, datetime) else delivery_date
                    min_tracking_date = start_date_value if min_tracking_date is None else min(min_tracking_date, start_date_value)
                    max_tracking_date = end_date_value if max_tracking_date is None else max(max_tracking_date, end_date_value)
                    tracking_updates.append((order, delivery_date))
                else:
                    order.delivery_days = None
                    order.kpi_warning = False

                order.updated_by = user_id
                updated += 1
            except Exception as exc:
                errors.append({"row": row_idx, "error": str(exc), "data": row_data})

        holidays_tracking = set()
        if min_tracking_date and max_tracking_date:
            holidays_tracking = calendar_service.get_public_holidays_between(min_tracking_date, max_tracking_date)

        for order, delivery_date in tracking_updates:
            delivery_days = calendar_service.business_days_between(
                order.order_date,
                delivery_date,
                working_weekdays=working_weekdays,
                holidays=holidays_tracking,
            )
            order.delivery_days = delivery_days
            order.kpi_warning = delivery_days > 2
            if order.kpi_warning:
                kpi_warnings.append({"order_number": order.order_number, "days": delivery_days})

        logger.info(
            "Order tracking import: Master rows=%s, Tracking rows=%s, created=%s, updated=%s, errors=%s",
            master_rows, tracking_rows, created, updated, len(errors),
        )
        for i, err in enumerate(errors[:5]):
            if isinstance(err, dict):
                data = err.get("data")
                if isinstance(data, dict):
                    data_keys = list(data.keys())
                elif isinstance(data, list):
                    data_keys = f"list({len(data)})"
                else:
                    data_keys = type(data).__name__ if data is not None else None
                logger.warning(
                    "Order tracking import error [%s]: row=%s %s | data keys=%s",
                    i + 1,
                    err.get("row"),
                    err.get("error"),
                    data_keys,
                )
            else:
                logger.warning("Order tracking import error [%s]: %s", i + 1, err)
        for i, warn in enumerate(warnings[:5]):
            if isinstance(warn, dict):
                data = warn.get("data")
                if isinstance(data, dict):
                    data_keys = list(data.keys())
                elif isinstance(data, list):
                    data_keys = f"list({len(data)})"
                else:
                    data_keys = type(data).__name__ if data is not None else None
                logger.warning(
                    "Order tracking import warning [%s]: row=%s %s | data keys=%s",
                    i + 1,
                    warn.get("row"),
                    warn.get("warning"),
                    data_keys,
                )
            else:
                logger.warning("Order tracking import warning [%s]: %s", i + 1, warn)
        if len(errors) > 5:
            logger.warning("Order tracking import: ... and %s more errors", len(errors) - 5)

        try:
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            errors.append({"row": None, "error": f"Database error: {exc}", "data": None})
            logger.exception("Order tracking import: database commit failed")

        duration_ms = int((time.monotonic() - start_time) * 1000)
        try:
            import_log_service = ImportLogService(self.db)
            import_log_service.create_import_log(
                entity_type="order",
                entity_table="orders",
                import_session_id=import_session_id,
                filename=None,
                import_type="EXCEL_IMPORT",
                total_rows=master_rows + tracking_rows,
                successful_rows=created + updated,
                created_rows=created,
                updated_rows=updated,
                failed_rows=len(errors),
                skipped_rows=0,
                warnings=json_safe(warnings),
                errors=json_safe(errors),
                summary=json_safe({"kpi_warnings": kpi_warnings, "master_rows": master_rows, "tracking_rows": tracking_rows, "warnings": len(warnings)}),
                imported_by=user_id,
                duration_ms=duration_ms,
            )
        except Exception:
            pass

        return {
            "import_session_id": import_session_id,
            "created": created,
            "updated": updated,
            "errors": errors,
            "warnings": warnings,
            "kpi_warnings": kpi_warnings,
            "master_rows": master_rows,
            "tracking_rows": tracking_rows,
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
