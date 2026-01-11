# SORENTO FRONTEND PROPOSAL - DATABASE SCHEMA MAPPING

## 📊 Database Schema Overview

Your PostgreSQL database has **44 tables** organized as follows:

### Core Tables by Category

**Authentication & Access Control (9 tables)**
- `users` - User accounts with groups and roles
- `groups` - Organizational units
- `roles` - Role definitions with permission scope
- `permissions` - Resource+Action combinations (CREATE, READ, UPDATE, DELETE, EXECUTE)
- `user_roles` - User to Role assignments with effective dates
- `role_permissions` - Role to Permission mappings
- `access_agents` - Contact agent codes for communication routing
- `contact_agent_access` - Agent access to specific contacts
- `audit_logs` - All user actions (CREATE, READ, UPDATE, DELETE)

**System Management (3 tables)**
- `system_activity_logs` - System-wide activity tracking
- `system_settings` - Configurable application settings
- `email_templates` - Email templates for notifications

**Master Data - Products (6 tables)**
- `products` - Product master records
- `product_categories` - Product categories (hierarchical)
- `brands` - Brand master
- `units_of_measure` - UOM definitions with conversion factors
- `attachments` - Files linked to entities
- `attachment_types` - File type configurations

**Master Data - Suppliers & Procurement (3 tables)**
- `suppliers` - Supplier master records
- `product_suppliers` - Product to Supplier mapping (link table)
- (Planned: Purchase Orders, Quotations)

**Master Data - Inventory & Warehousing (6 tables)**
- `warehouses` - Warehouse master records
- `storage_zones` - Warehouse storage zones
- `stock` - Stock levels (product × warehouse × UOM)
- `stock_batches` - Batch tracking with serial numbers
- `stock_transactions` - Stock movement history
- (Planned: Stock picks, transfers)

**Master Data - Marketing & Campaigns (4 tables)**
- `promotions` - Promotion master records
- `promotion_products` - Products in promotion (link table)
- `marketing_campaigns` - Campaign master records
- `campaign_types` - Campaign type configurations

**Master Data - Forms (2 tables)**
- `forms` - Form master records
- (Planned: form_sections, form_fields, form_submissions)

**Operational Data - Orders (4 tables)**
- `customers` - Customer master records
- `orders` - Order headers
- `order_items` - Order line items
- `order_statuses` - Order status definitions

**Operational Data - Complaints & Issues (4 tables)**
- `complaints` - Complaint master records (manual entry)
- `complaint_manual` - Detailed complaint information
- `complaint_categories` - Complaint categories with severity
- `complaint_statuses` - Complaint status workflow

**Operational Data - Shipments & Logistics (2 tables)**
- `inbound_shipments` - Supplier shipments
- `inbound_shipment_lines` - Details of items in shipment

**Operational Data - Warehouse Operations (2 tables)**
- `picking_headers` - Picking operation headers
- `picking_lines` - Picking operation line items

**Operational Data - Communications (3 tables)**
- `communications` - Multi-channel messages (WhatsApp, Email, SMS, Phone, Web)
- `conversation_sla_tracking` - SLA tracking per conversation
- `conversation_sla_escalation_log` - Escalation history

**Configuration & Reference (2 tables)**
- `sla_policies` - SLA policy definitions
- `sla_policy_tiers` - SLA response tiers per policy
- `complaint_statuses` - Complaint status workflow
- `order_statuses` - Order status workflow
- `campaign_types` - Campaign type reference
- `message_types` - Message type reference

---

## 🔗 FEATURE TO DATABASE MAPPING

### MODULE 1: MASTER DATA MANAGEMENT

#### Products Module

**ProductsList Component**
```
DATABASE TABLES USED:
┌─ products
│  ├─ id (UUID)
│  ├─ product_code (VARCHAR 100) ← DISPLAY IN GRID
│  ├─ product_name (VARCHAR 255) ← DISPLAY IN GRID
│  ├─ list_price (NUMERIC 12,2) ← DISPLAY IN GRID
│  ├─ is_active (BOOLEAN) ← FILTER & DISPLAY
│  ├─ created_at (TIMESTAMPTZ) ← SORT/FILTER
│  └─ created_by (UUID) → users table
├─ product_categories
│  ├─ id (UUID)
│  └─ category_name (VARCHAR 150) ← DISPLAY IN GRID
├─ brands
│  ├─ id (UUID)
│  └─ brand_name (VARCHAR 150) ← DISPLAY IN GRID
└─ audit_logs (filtered by entity_type='product')
   └─ Record product views and exports

GRID COLUMNS:
- product_code (FROM products.product_code)
- product_name (FROM products.product_name)
- category (FROM product_categories.category_name via products.category_id)
- brand (FROM brands.brand_name via products.brand_id)
- list_price (FROM products.list_price)
- status (FROM products.is_active)
- created_date (FROM products.created_at)

FILTERS:
- category_id: Filter by products.category_id
- brand_id: Filter by products.brand_id
- is_active: Filter by products.is_active
- price_range: Filter products.list_price BETWEEN min AND max
- search: WHERE product_code ILIKE ? OR product_name ILIKE ?

BULK ACTIONS:
- Update is_active: UPDATE products SET is_active = ?, updated_at = NOW()
- Delete (soft): UPDATE products SET is_deleted = true, deleted_at = NOW()

EXPORTS:
- CSV: SELECT product_code, product_name, category_name, brand_name, list_price, is_active FROM products JOIN product_categories ...
```

**ProductForm Component (Create/Edit)**
```
DATABASE TABLES AFFECTED:
┌─ products (INSERT/UPDATE)
│  ├─ product_code (required, unique)
│  ├─ product_name (required)
│  ├─ description (optional)
│  ├─ category_id (required) → product_categories.id
│  ├─ brand_id (optional) → brands.id
│  ├─ base_uom_id (required) → units_of_measure.id
│  ├─ list_price (required)
│  ├─ cost_price (optional, permission-based visibility)
│  ├─ invoice_price (optional, permission-based visibility)
│  ├─ weight, dimensions (optional)
│  ├─ warranty_months (optional)
│  ├─ has_serial_tracking (boolean)
│  ├─ has_batch_tracking (boolean)
│  ├─ reorder_level (default 10)
│  ├─ reorder_quantity (default 50)
│  ├─ is_active (boolean, default true)
│  ├─ created_by (UUID) → Set from current user
│  └─ updated_by (UUID) → Set from current user
├─ units_of_measure (JOIN for base UOM)
│  └─ Display conversion factors
├─ attachments (for product files)
│  ├─ entity_type = 'product'
│  ├─ entity_id = products.id
│  └─ Display uploaded files
└─ audit_logs (INSERT on create/update)
   └─ Log who created/updated what and when

FORM TABS MAPPING:

Tab 1: Basic Information
├─ product_code → products.product_code
├─ product_name → products.product_name
├─ description → products.description
├─ category_id → products.category_id (dropdown from product_categories)
├─ brand_id → products.brand_id (dropdown from brands)
├─ item_type → products.item_type
└─ is_active → products.is_active

Tab 2: Pricing
├─ list_price → products.list_price
├─ cost_price → products.cost_price (hidden for viewers)
├─ invoice_price → products.invoice_price (hidden for viewers)
└─ Price history: Query previous list_price values from audit_logs

Tab 3: Specifications
├─ weight → products.weight
├─ dimensions_length → products.dimensions_length
├─ dimensions_width → products.dimensions_width
├─ dimensions_height → products.dimensions_height
├─ warranty_months → products.warranty_months
├─ has_serial_tracking → products.has_serial_tracking
└─ has_batch_tracking → products.has_batch_tracking

Tab 4: Unit of Measure
├─ base_uom_id → products.base_uom_id (required)
├─ reorder_level → products.reorder_level
├─ reorder_quantity → products.reorder_quantity
└─ Alternative UOMs: Stored in units_of_measure with base_uom_id and conversion_factor

Tab 5: Attachments
├─ Upload files: INSERT INTO attachments
│  ├─ entity_type = 'product'
│  ├─ entity_id = products.id
│  ├─ attachment_type_id → attachment_types.id
│  ├─ original_filename (user's file name)
│  ├─ stored_filename (hashed name for storage)
│  ├─ file_size_bytes
│  ├─ mime_type
│  ├─ file_hash (SHA-256 for duplicate detection)
│  └─ uploaded_by → users.id
└─ Display: SELECT FROM attachments WHERE entity_type='product' AND entity_id=products.id
```

**ProductDetail Component**
```
DATABASE TABLES USED:
┌─ products (main record)
├─ product_categories (via products.category_id)
├─ brands (via products.brand_id)
├─ units_of_measure (via products.base_uom_id)
├─ stock (for stock information)
│  └─ WHERE product_id = ? GROUP BY warehouse_id
├─ stock_batches (for batch info)
│  └─ WHERE product_id = ?
├─ product_suppliers (related suppliers)
│  └─ WHERE product_id = ?
├─ promotions (current promotions)
│  └─ WHERE id IN (SELECT promotion_id FROM promotion_products WHERE product_id = ?)
├─ orders (recent orders)
│  └─ WHERE id IN (SELECT order_id FROM order_items WHERE product_id = ?)
├─ attachments (files)
│  └─ WHERE entity_type='product' AND entity_id = ?
└─ audit_logs (change history)
   └─ WHERE entity_type='product' AND entity_id = ? ORDER BY action_timestamp DESC

DETAIL PAGE TABS:

Tab: Overview
├─ Basic info: Display from products table
├─ Pricing summary: list_price, cost_price (if visible), margin %
├─ Specifications grid: weight, dimensions, warranty
└─ Flags: Serial tracking, Batch tracking

Tab: Stock
├─ Stock by warehouse: SELECT product_id, warehouse_id, SUM(quantity) FROM stock GROUP BY warehouse_id, product_id
├─ Low stock alerts: WHERE product_id = ? AND quantity < reorder_level
├─ Stock movement chart: SELECT DATE(transaction_date), SUM(quantity) FROM stock_transactions GROUP BY DATE ORDER BY DESC LIMIT 30
└─ Stock aging: Analyze oldest batches

Tab: Related Data
├─ Product Suppliers: SELECT FROM product_suppliers WHERE product_id = ? JOIN suppliers
├─ Promotions: SELECT FROM promotions WHERE id IN (...) ORDER BY start_date DESC
├─ Recent Orders: SELECT TOP 10 FROM orders WHERE id IN (...) ORDER BY created_at DESC
└─ Attachments: SELECT FROM attachments WHERE entity_type='product' AND entity_id = ?

Tab: Audit Trail
├─ Created: products.created_at, products.created_by (JOIN users for name)
├─ Modified: products.updated_at, products.updated_by (JOIN users)
├─ Version history: Query audit_logs for this product
└─ Change log: Display old_values and new_values from audit_logs
```

---

#### Product Categories Module

**CategoriesList (Tree View)**
```
DATABASE TABLES:
┌─ product_categories
│  ├─ id (UUID)
│  ├─ category_code (VARCHAR 50) ← DISPLAY
│  ├─ category_name (VARCHAR 150) ← DISPLAY
│  ├─ parent_category_id (UUID) ← FOREIGN KEY for hierarchy
│  ├─ is_active (BOOLEAN) ← FILTER
│  ├─ display_order (INT) ← SORT
│  └─ created_by (UUID)
└─ products (to count items)
   └─ COUNT(*) WHERE category_id = category_categories.id

TREE STRUCTURE:
- Root nodes: WHERE parent_category_id IS NULL ORDER BY display_order
- Child nodes: WHERE parent_category_id = ? ORDER BY display_order
- Show product count per category
- Drag-drop to reorder (UPDATE display_order)
- Drag-drop to move parent (UPDATE parent_category_id)

OPERATIONS:
- CREATE: INSERT INTO product_categories (category_code, category_name, parent_category_id, display_order, is_active, created_by)
- UPDATE: UPDATE product_categories SET category_name = ?, parent_category_id = ?, display_order = ? WHERE id = ?
- DELETE (soft): UPDATE product_categories SET is_active = false WHERE id = ?
- Move: UPDATE product_categories SET parent_category_id = ?, display_order = ? WHERE id = ?
```

**CategoryForm (Modal)**
```
DATABASE FIELDS:
- category_code → product_categories.category_code (required, unique)
- category_name → product_categories.category_name (required)
- description → product_categories.description (optional)
- parent_category_id → product_categories.parent_category_id (optional, dropdown from other categories)
- is_active → product_categories.is_active (toggle)
- display_order → product_categories.display_order (number for sort order)
```

---

#### Brands Module

**BrandsList**
```
DATABASE TABLES:
┌─ brands
│  ├─ id (UUID)
│  ├─ brand_code (VARCHAR 50) ← GRID
│  ├─ brand_name (VARCHAR 150) ← GRID
│  ├─ manufacturer (VARCHAR 150) ← GRID
│  ├─ logo_url (VARCHAR 255) ← DISPLAY THUMBNAIL
│  ├─ is_active (BOOLEAN) ← FILTER
│  └─ created_by (UUID)
└─ products (count)
   └─ COUNT(*) WHERE brand_id = brands.id

GRID COLUMNS:
- brand_code
- brand_name
- manufacturer
- logo (thumbnail from logo_url)
- status (is_active)

FILTERS:
- is_active: Toggle to show active/inactive

BULK ACTIONS:
- Status change: UPDATE brands SET is_active = ? WHERE id IN (?)
- Export: CSV with all columns
```

**BrandForm**
```
DATABASE FIELDS:
- brand_code → brands.brand_code (required, unique)
- brand_name → brands.brand_name (required)
- manufacturer → brands.manufacturer (optional)
- website → brands.website (optional)
- description → brands.description (optional)
- logo_url → brands.logo_url (file upload, stored in attachments or CDN)
- is_active → brands.is_active (toggle)

FILE UPLOAD HANDLING:
- Store logo in attachments table with entity_type='brand', entity_id=brands.id
- Or store URL directly in logo_url field
```

---

### MODULE 2: PROCUREMENT MANAGEMENT

#### Suppliers Module

**SuppliersList**
```
DATABASE TABLES:
┌─ suppliers
│  ├─ id (UUID)
│  ├─ supplier_code (VARCHAR 50) ← GRID
│  ├─ supplier_name (VARCHAR 255) ← GRID
│  ├─ contact_name (VARCHAR 150) ← GRID
│  ├─ email (VARCHAR 150) ← GRID
│  ├─ phone_number (VARCHAR 50) ← GRID
│  ├─ city (VARCHAR 100) ← FILTER
│  ├─ state (VARCHAR 100) ← FILTER
│  ├─ country (VARCHAR 100) ← FILTER
│  ├─ payment_terms_days (INT) ← FILTER
│  ├─ is_active (BOOLEAN) ← FILTER
│  └─ created_by (UUID)
└─ product_suppliers (for linked products count)
   └─ COUNT(*) WHERE supplier_id = suppliers.id

GRID DISPLAY:
- supplier_code, supplier_name, contact_name, phone_number, email, status

FILTERS:
- country, city, payment_terms_days, is_active

SEARCH:
- supplier_code ILIKE ? OR supplier_name ILIKE ?
```

**SupplierForm**
```
DATABASE FIELDS:
- supplier_code → suppliers.supplier_code (required, unique)
- supplier_name → suppliers.supplier_name (required)
- contact_name → suppliers.contact_name (optional)
- email → suppliers.email (optional, email validation)
- phone_number → suppliers.phone_number (optional)
- website → suppliers.website (optional)
- address_line1 → suppliers.address_line1 (required)
- address_line2 → suppliers.address_line2 (optional)
- city → suppliers.city (required)
- state → suppliers.state (required)
- postal_code → suppliers.postal_code (required)
- country → suppliers.country (required)
- payment_terms_days → suppliers.payment_terms_days (default 30)
- is_active → suppliers.is_active (toggle)
- attachments → entity_type='supplier', entity_id=suppliers.id
```

**SupplierDetail**
```
DATABASE TABLES USED:
┌─ suppliers (main)
├─ product_suppliers (linked products)
│  └─ JOIN products
├─ inbound_shipments (recent shipments)
│  └─ WHERE supplier_id = suppliers.id
├─ orders (recent orders)
│  └─ Via inbound_shipments or order items
└─ attachments (documents)
   └─ WHERE entity_type='supplier' AND entity_id=suppliers.id

DETAIL SECTIONS:
- Contact info card: From suppliers table
- Address: Full address display
- Linked products: SELECT FROM product_suppliers JOIN products WHERE supplier_id = ?
- Performance rating: Calculate from inbound_shipments delivery metrics
- Recent orders: TOP 10 from inbound_shipments ORDER BY shipment_date DESC
- Attachments: Certificates, agreements
```

---

#### Product-Suppliers Module

**ProductSuppliersGrid**
```
DATABASE TABLES:
┌─ product_suppliers (main mapping table)
│  ├─ id (UUID)
│  ├─ product_id (UUID) → products.id
│  ├─ supplier_id (UUID) → suppliers.id
│  ├─ lead_time_days (INT) ← DISPLAY
│  ├─ min_order_quantity (INT) ← DISPLAY
│  ├─ is_primary (BOOLEAN) ← DISPLAY (mark primary supplier)
│  ├─ valid_from (TIMESTAMPTZ) ← FILTER
│  ├─ valid_to (TIMESTAMPTZ) ← FILTER
│  └─ created_at (TIMESTAMPTZ)
├─ products (JOIN)
│  ├─ product_code
│  └─ product_name
└─ suppliers (JOIN)
   ├─ supplier_code
   └─ supplier_name

GRID COLUMNS:
- product_code (FROM products)
- product_name (FROM products)
- supplier_code (FROM suppliers)
- supplier_name (FROM suppliers)
- lead_time_days (FROM product_suppliers)
- min_order_quantity (FROM product_suppliers)
- is_primary (FROM product_suppliers)
- valid_from / valid_to (FROM product_suppliers)
- status

ACTIONS:
- Add supplier: Modal to INSERT product_suppliers
- Remove supplier: DELETE product_suppliers WHERE id = ?
- Edit: UPDATE product_suppliers SET lead_time_days = ?, min_order_quantity = ?, is_primary = ?
- Comparison chart: Compare lead_times for same product across suppliers
```

**SupplierAssignmentModal**
```
DATABASE OPERATIONS:
INSERT INTO product_suppliers (
  product_id,              ← From form selector
  supplier_id,             ← From form selector
  lead_time_days,          ← From input
  min_order_quantity,      ← From input
  is_primary,              ← From checkbox
  valid_from,              ← From date picker
  valid_to                 ← From date picker
) VALUES (...)

OR UPDATE product_suppliers SET ... WHERE id = ?

UNIQUENESS CONSTRAINT:
- Each product_supplier combination must be unique
- Do not allow duplicate product_id + supplier_id pairs
```

**Bulk Upload (CSV)**
```
CSV TEMPLATE COLUMNS:
- product_code (match against products.product_code)
- supplier_code (match against suppliers.supplier_code)
- lead_time_days
- min_order_quantity
- is_primary (true/false)

PROCESS:
1. Parse CSV
2. Validate: Match product_code and supplier_code to IDs
3. Check for duplicates in upload
4. Preview before insert
5. INSERT INTO product_suppliers (batch)
6. Log errors for invalid rows
```

---

### MODULE 3: INVENTORY MANAGEMENT

#### Warehouses Module

**WarehousesList**
```
DATABASE TABLES:
┌─ warehouses
│  ├─ id (UUID)
│  ├─ warehouse_code (VARCHAR 50) ← GRID
│  ├─ warehouse_name (VARCHAR 150) ← GRID
│  ├─ location (VARCHAR 255) ← GRID
│  ├─ manager_id (UUID) → users.id ← GRID
│  ├─ is_active (BOOLEAN) ← FILTER
│  └─ created_by (UUID)
├─ users (manager name)
│  └─ first_name, last_name, email
├─ storage_zones (count zones)
│  └─ COUNT(*) WHERE warehouse_id = warehouses.id
└─ stock (for totals)
   └─ SUM(quantity) WHERE warehouse_id = warehouses.id

GRID COLUMNS:
- warehouse_code
- warehouse_name
- location
- manager (FROM users)
- status
- zones_count (COUNT FROM storage_zones)

ACTIONS:
- Create: INSERT warehouses
- Edit: UPDATE warehouses
- Delete: DELETE warehouses (soft or hard, depends on requirements)
- View detail: Navigate to detail page
```

**WarehouseForm**
```
DATABASE FIELDS:
- warehouse_code → warehouses.warehouse_code (required, unique)
- warehouse_name → warehouses.warehouse_name (required)
- location → warehouses.location (required)
- manager_id → warehouses.manager_id (optional, autocomplete from users)
- address → warehouses.location (optional additional field)
- is_active → warehouses.is_active (toggle)
```

**WarehouseDetail**
```
DATABASE TABLES USED:
┌─ warehouses (main)
├─ users (manager info)
├─ storage_zones (zones tree)
│  └─ WHERE warehouse_id = ?
├─ stock (stock summary)
│  └─ WHERE warehouse_id = ? GROUP BY product_id
└─ stock_transactions (recent activity)
   └─ WHERE from_warehouse_id = ? OR to_warehouse_id = ? ORDER BY DESC LIMIT 20

DETAIL SECTIONS:
- Manager info: From warehouses.manager_id → users table
- Address/location: From warehouses.location
- Storage zones: Tree view of storage_zones WHERE warehouse_id = ?
- Stock summary: SUM(quantity) by product, count distinct products
- Capacity: SUM(capacity) from storage_zones, calculate utilization
- Recent activity: Latest stock_transactions
```

---

#### Storage Zones Module

**StorageZoneTree**
```
DATABASE TABLES:
┌─ warehouses (parent grouping)
└─ storage_zones (tree view per warehouse)
   ├─ id (UUID)
   ├─ warehouse_id (UUID) ← GROUP BY warehouse
   ├─ zone_code (VARCHAR 50) ← DISPLAY
   ├─ zone_name (VARCHAR 150) ← DISPLAY
   ├─ zone_type (VARCHAR 100: shelf, rack, bin, pallet) ← DISPLAY & FILTER
   ├─ capacity (INT) ← DISPLAY
   └─ created_at

TREE STRUCTURE:
- Level 1: Warehouses (expandable)
- Level 2: Storage zones (per warehouse)
- Show: zone_code | zone_name | type_icon | capacity | utilization %
- Drag-drop to reorder zones within warehouse
- Color-code by zone_type

OPERATIONS:
- Create zone: INSERT storage_zones (warehouse_id, zone_code, zone_name, zone_type, capacity)
- Edit zone: UPDATE storage_zones SET zone_name = ?, capacity = ? WHERE id = ?
- Delete zone: DELETE storage_zones WHERE id = ?
- Reorder: UPDATE storage_zones SET display_order = ? WHERE id = ?
```

**StorageZoneForm**
```
DATABASE FIELDS:
- warehouse_id → storage_zones.warehouse_id (required, dropdown)
- zone_code → storage_zones.zone_code (required, unique per warehouse)
- zone_name → storage_zones.zone_name (optional)
- zone_type → storage_zones.zone_type (required, dropdown: shelf, rack, bin, pallet)
- capacity → storage_zones.capacity (required, positive number)
```

---

#### Stock Module (Dashboard & Balance)

**StockDashboard**
```
DATABASE QUERIES:

KPI CARDS:
1. Total SKUs: SELECT COUNT(DISTINCT product_id) FROM stock
2. Total Quantity: SELECT SUM(quantity) FROM stock
3. Low Stock Alerts: SELECT COUNT(*) FROM stock JOIN products WHERE stock.quantity < products.reorder_level
4. Overstock: SELECT COUNT(*) FROM stock WHERE quantity > (capacity * 0.9)

CHARTS:
1. Stock by Warehouse:
   SELECT warehouse_id, SUM(quantity) FROM stock GROUP BY warehouse_id
   JOIN warehouses for warehouse_name
   
2. Stock by Category:
   SELECT product_categories.category_name, SUM(stock.quantity)
   FROM stock JOIN products JOIN product_categories
   GROUP BY category_name
   
3. Stock Movement (30 days):
   SELECT DATE(transaction_date), SUM(CASE WHEN transaction_type IN ('purchase', 'sale') THEN quantity ELSE 0 END)
   FROM stock_transactions
   WHERE transaction_date >= NOW() - INTERVAL 30 days
   GROUP BY DATE(transaction_date)
   ORDER BY DATE DESC

LOW STOCK ALERT LIST:
SELECT 
  products.product_code,
  products.product_name,
  stock.warehouse_id,
  warehouses.warehouse_name,
  stock.quantity,
  products.reorder_level
FROM stock
JOIN products ON stock.product_id = products.id
JOIN warehouses ON stock.warehouse_id = warehouses.id
WHERE stock.quantity < products.reorder_level
ORDER BY (products.reorder_level - stock.quantity) DESC
LIMIT 20
```

**StockBalanceGrid**
```
DATABASE TABLES:
┌─ stock
│  ├─ id (UUID)
│  ├─ product_id (UUID) ← GRID
│  ├─ warehouse_id (UUID) ← GRID
│  ├─ quantity (INT) ← GRID, SORT, FILTER
│  ├─ reserved_quantity (INT) ← GRID (available = quantity - reserved)
│  └─ uom_id (UUID)
├─ products
│  ├─ product_code ← GRID
│  ├─ product_name ← GRID
│  ├─ reorder_level ← CONTEXT
│  └─ category_id
├─ warehouses
│  ├─ warehouse_name ← GRID
└─ product_categories
   └─ category_name ← GRID

GRID COLUMNS:
- product_code (FROM products)
- product_name (FROM products)
- category (FROM product_categories)
- warehouse (FROM warehouses)
- available (stock.quantity - stock.reserved_quantity)
- reserved (stock.reserved_quantity)
- total (stock.quantity)
- reorder_level (FROM products)
- status (color-coded: RED if < reorder, YELLOW if < safety, GREEN if normal, ORANGE if over)

FILTERS:
- warehouse_id: Filter by stock.warehouse_id
- category_id: Filter by products.category_id
- status: WHERE quantity < reorder_level (low), etc.

SEARCH:
- product_code ILIKE ? OR product_name ILIKE ?

BULK ACTIONS:
- Trigger replenishment (admin): Create picking list or PO
- Adjust stock: UPDATE stock SET quantity = ? WHERE id = ?
```

---

#### Stock Batches Module

**BatchesList**
```
DATABASE TABLES:
┌─ stock_batches
│  ├─ id (UUID)
│  ├─ product_id (UUID) → products.id ← GRID
│  ├─ batch_code (VARCHAR 100) ← GRID
│  ├─ quantity (INT) ← GRID
│  ├─ manufactured_date (DATE) ← GRID, SORT
│  ├─ expiry_date (DATE) ← GRID, ALERT if < 30 days
│  ├─ warehouse_id (UUID) → warehouses.id ← GRID
│  ├─ status (VARCHAR 50: available, reserved, damaged, expired, returned) ← FILTER
│  └─ created_at
├─ products
│  ├─ product_code
│  └─ product_name
└─ warehouses
   └─ warehouse_name

GRID COLUMNS:
- product_code (FROM products)
- batch_code
- quantity
- manufactured_date
- expiry_date (color: RED if within 30 days)
- warehouse (FROM warehouses)
- status

FILTERS:
- warehouse_id, product_id, status (Available/Reserved/Damaged/Expired/Returned)

SEARCH:
- batch_code ILIKE ?

ALERTS:
- Color badge if expiry_date < NOW() + INTERVAL 30 days
```

**BatchDetail**
```
DATABASE TABLES USED:
┌─ stock_batches (main)
├─ products (product info)
├─ warehouses (warehouse info)
├─ storage_zones (zone location)
├─ stock_transactions (batch movements)
│  └─ WHERE reference_id = batch_id
└─ serial_numbers (if serial_tracking enabled)
   └─ Individual serial tracking per batch

DETAIL SECTIONS:
- Product info: From products table
- Batch code, manufactured date, expiry date
- Quantities: total, available, reserved
- Warehouse & zone: From warehouses and storage_zones
- Current status: From stock_batches.status
- Serial numbers: IF products.has_serial_tracking = true
  └─ List all serial numbers from serial_number table
  └─ Show individual serial status
  └─ QR code generation per serial
- Batch history: SELECT FROM stock_transactions WHERE reference_id = batch_id
- Attachments: Test certificates, quality reports
```

**BatchForm**
```
DATABASE FIELDS:
- product_id → stock_batches.product_id (required, autocomplete from products)
- batch_code → stock_batches.batch_code (required, unique)
- warehouse_id → stock_batches.warehouse_id (required)
- storage_zone_id → storage_zones.id (required)
- manufactured_date → stock_batches.manufactured_date (optional)
- expiry_date → stock_batches.expiry_date (optional, triggers warnings)
- received_date → stock_batches.received_date (required)
- quantity → stock_batches.quantity (required, positive)
- status → stock_batches.status (dropdown)
- serial_numbers → serial number entries (if applicable)
- attachments → entity_type='batch', entity_id=stock_batches.id

SERIAL NUMBER HANDLING:
IF products.has_serial_tracking = true:
  - Allow bulk entry: Paste comma-separated serial numbers
  - INSERT INTO serial_numbers (batch_id, serial_number, status) FOR EACH
  - Generate QR codes for scanning
```

---

### MODULE 4: MARKETING MANAGEMENT

#### Promotions Module

**PromotionsList**
```
DATABASE TABLES:
┌─ promotions
│  ├─ id (UUID)
│  ├─ promo_code (VARCHAR 50) ← GRID, SEARCH
│  ├─ name (VARCHAR 255) ← GRID
│  ├─ promo_type (VARCHAR 50: price_override, discount_percent, discount_amount, bundle, other) ← GRID, FILTER
│  ├─ start_date (DATE) ← GRID, SORT
│  ├─ end_date (DATE) ← GRID, SORT
│  ├─ is_active (BOOLEAN) ← FILTER
│  └─ created_by (UUID)
└─ promotion_products (count)
   └─ COUNT(*) WHERE promotion_id = promotions.id

GRID COLUMNS:
- promo_code
- name
- type (with icon for type)
- start_date
- end_date
- status (ACTIVE/INACTIVE, color-coded)
- products_count

FILTERS:
- promo_type
- is_active
- date_range: WHERE start_date BETWEEN ? AND ?

CALENDAR VIEW OPTION:
- Show promotions as events on calendar
- start_date to end_date

BULK ACTIONS:
- Activate/Deactivate: UPDATE promotions SET is_active = ? WHERE id IN (?)
- Delete: DELETE promotions WHERE id IN (?)
- Export: CSV
```

**PromotionForm**
```
DATABASE FIELDS:
- promo_code → promotions.promo_code (required, unique, auto-generate)
- name → promotions.name (required)
- promo_type → promotions.promo_type (required)
- description → promotions.description (optional)
- start_date → promotions.start_date (required)
- end_date → promotions.end_date (required, must be after start)
- is_active → promotions.is_active (toggle)

TYPE-SPECIFIC FIELDS (conditional):
- price_override: new_price (NUMERIC)
- discount_percent: discount_percentage (0-100)
- discount_amount: discount_amount (NUMERIC)
- bundle: promotion_products (grid of products + combined price)
```

**PromotionDetail**
```
DATABASE TABLES USED:
┌─ promotions (main)
├─ promotion_products (products in promo)
│  ├─ id (UUID)
│  ├─ promotion_id (UUID)
│  ├─ product_id (UUID)
│  ├─ promotion_price (NUMERIC) ← Show price override
│  └─ display_order (INT)
├─ products (product info)
├─ order_items (for metrics)
│  └─ WHERE product_id IN promotion_products AND order_created_at BETWEEN promo dates
└─ audit_logs

DETAIL SECTIONS:
- Promotion info: From promotions table
- Products in promo: Grid of promotion_products
  └─ product_code, product_name, list_price, promo_price, discount amount/%, category
- Promotion metrics:
  └─ Units sold during promo period
  └─ Revenue attributed
  └─ Total discount given
  └─ Unique customers
  └─ Repeat purchase rate
- Timeline: start_date, end_date
- Edit / Delete buttons
```

**PromotionProductsGrid**
```
DATABASE TABLES:
┌─ promotion_products
│  ├─ product_id (UUID)
│  ├─ promotion_price (NUMERIC)
│  └─ display_order (INT)
├─ products
│  ├─ product_code
│  ├─ product_name
│  ├─ list_price
│  └─ category_id
└─ product_categories
   └─ category_name

GRID COLUMNS:
- product_code
- product_name
- list_price
- promo_price (editable inline)
- discount_amount (calculated)
- discount_percent (calculated)
- category

ACTIONS:
- Add products: Modal with product search
  └─ INSERT INTO promotion_products (promotion_id, product_id, promotion_price)
- Remove product: DELETE FROM promotion_products WHERE id = ?
- Edit promo price: UPDATE promotion_products SET promotion_price = ? WHERE id = ?
- Bulk update: UPDATE multiple at once

CALCULATION:
discount_amount = list_price - promo_price
discount_percent = (discount_amount / list_price) * 100
```

---

#### Campaigns Module

**CampaignsList**
```
DATABASE TABLES:
┌─ marketing_campaigns
│  ├─ id (UUID)
│  ├─ campaign_code (VARCHAR 50) ← GRID
│  ├─ campaign_name (VARCHAR 255) ← GRID
│  ├─ campaign_type_id (UUID) → campaign_types.id ← GRID, FILTER
│  ├─ start_date (DATE) ← GRID, SORT
│  ├─ end_date (DATE) ← GRID, SORT
│  ├─ budget (NUMERIC 15,2) ← GRID
│  ├─ status (VARCHAR 50: planning, active, completed, cancelled) ← GRID, FILTER
│  └─ created_by (UUID)
├─ campaign_types
│  └─ type_name
└─ promotions (for campaign products)
   └─ WHERE campaign_type_id = campaigns.campaign_type_id (estimated link)

GRID COLUMNS:
- campaign_code
- campaign_name
- campaign_type (FROM campaign_types)
- start_date
- end_date
- budget
- status (color-coded)

FILTERS:
- campaign_type_id
- status (planning, active, completed, cancelled)
- date_range
- budget_range
```

**CampaignForm**
```
DATABASE FIELDS:
- campaign_code → marketing_campaigns.campaign_code (required, unique, auto-generate)
- campaign_name → marketing_campaigns.campaign_name (required)
- campaign_type_id → marketing_campaigns.campaign_type_id (required, dropdown from campaign_types)
- description → marketing_campaigns.description (optional)
- start_date → marketing_campaigns.start_date (required)
- end_date → marketing_campaigns.end_date (optional)
- budget → marketing_campaigns.budget (optional)
- target_audience → marketing_campaigns.target_audience (optional)
- status → marketing_campaigns.status (dropdown)
- attachments → entity_type='marketing', entity_id=marketing_campaigns.id
```

**CampaignDashboard**
```
DATABASE TABLES USED:
┌─ marketing_campaigns (main)
├─ campaign_types (type info)
├─ promotions (linked promotions)
│  └─ Estimate: promotions created during campaign period
├─ order_items (for revenue attribution)
│  └─ Estimate based on order_created_at between campaign dates
└─ audit_logs

DASHBOARD SECTIONS:

Campaign Info:
- campaign_code, campaign_name, type, dates, budget

Budget Tracking:
- Total budget allocated
- Spent to date (estimated from audit logs or separate spend table)
- Remaining budget
- Progress bar (% of budget spent)
- Burn rate ($/day)
- Warning if > 90% spent

Associated Products:
- Grid of promotions under this campaign

Campaign Activities:
- Events/roadshows/exhibitions linked to campaign
- Marketing activities table

Performance Metrics:
- Total impressions
- Click-through rate
- Conversion rate
- Revenue attributed to campaign
- Query order_items with order_created_at between campaign dates

Timeline:
- Start date
- End date
- Days remaining
- Status changes
```

---

### MODULE 5: FORMS MANAGEMENT

#### Forms Module

**FormsList**
```
DATABASE TABLES:
┌─ forms
│  ├─ id (UUID)
│  ├─ code (VARCHAR 100) ← GRID
│  ├─ name (VARCHAR 255) ← GRID
│  ├─ purpose (TEXT) ← FILTER
│  ├─ language (VARCHAR 10: en, MY) ← FILTER
│  ├─ version (INT) ← GRID
│  ├─ is_active (BOOLEAN) ← FILTER
│  ├─ created_at (TIMESTAMPTZ) ← GRID
│  ├─ updated_at (TIMESTAMPTZ) ← SORT
│  └─ attachment_id (UUID) → attachments.id (form template PDF)
└─ audit_logs

GRID COLUMNS:
- form_code
- form_name
- purpose
- language
- version
- status (active/inactive)
- last_updated

FILTERS:
- language, is_active, purpose

ACTIONS:
- Edit: Open FormBuilder
- View: Preview form
- Duplicate: Clone form with new code
- Delete: DELETE forms
- Publish: Update is_active = true
- View versions: Show version history
```

**FormBuilder (Main Interface)**
```
DATABASE TABLES:

PLANNED TABLES (need to be created):
┌─ form_sections
│  ├─ id (UUID)
│  ├─ form_id (UUID) → forms.id
│  ├─ section_name (VARCHAR 255)
│  ├─ section_order (INT)
│  └─ created_at
├─ form_fields
│  ├─ id (UUID)
│  ├─ section_id (UUID) → form_sections.id
│  ├─ field_name (VARCHAR 100) - Field identifier
│  ├─ field_label (VARCHAR 255) - Display label
│  ├─ field_type (VARCHAR 50: text, textarea, number, email, phone, date, dropdown, radio, checkbox, file, richtext, signature)
│  ├─ is_required (BOOLEAN)
│  ├─ help_text (TEXT)
│  ├─ placeholder (TEXT)
│  ├─ validation_rule (VARCHAR 500: regex pattern or rule)
│  ├─ min_length (INT)
│  ├─ max_length (INT)
│  ├─ default_value (TEXT)
│  ├─ conditional_logic (JSONB: {if: {field: "", value: ""}, then: "show"})
│  ├─ field_order (INT)
│  └─ created_at
└─ forms (updated)
   ├─ structure (JSONB: nested structure of sections/fields for export)
   └─ published_at (TIMESTAMPTZ)

FORM BUILDER OPERATIONS:

Create Section:
INSERT INTO form_sections (form_id, section_name, section_order)
VALUES (?, ?, ?)

Add Field:
INSERT INTO form_fields (
  section_id, field_name, field_label, field_type, is_required,
  help_text, placeholder, validation_rule, default_value, field_order
) VALUES (...)

Update Field:
UPDATE form_fields SET field_label = ?, field_type = ?, validation_rule = ? WHERE id = ?

Delete Field:
DELETE FROM form_fields WHERE id = ?

Reorder Sections/Fields:
UPDATE form_sections SET section_order = ? WHERE id = ?
UPDATE form_fields SET field_order = ? WHERE id = ?

Publish Form:
UPDATE forms SET is_active = true, published_at = NOW() WHERE id = ?
CREATE VERSION HISTORY RECORD
```

**FormPreview (Right Panel)**
```
DATABASE READS:
SELECT FROM form_sections, form_fields
WHERE form_sections.form_id = ?
ORDER BY form_sections.section_order, form_fields.field_order

RENDER:
- For each section, render section_name as heading
- For each field in section, render based on field_type:
  - text: <input type="text" />
  - textarea: <textarea></textarea>
  - number: <input type="number" />
  - email: <input type="email" />
  - phone: <input type="tel" />
  - date: <input type="date" />
  - dropdown: <select> with options
  - radio: <input type="radio" />
  - checkbox: <input type="checkbox" />
  - file: <input type="file" />
  - richtext: Rich text editor
  - signature: Signature pad

CONDITIONAL LOGIC:
- Show/hide fields based on conditional_logic JSONB
- Validate required fields on blur
- Show validation errors inline
```

**FormVersioning**
```
DATABASE TABLES (PLANNED):
┌─ form_versions
│  ├─ id (UUID)
│  ├─ form_id (UUID) → forms.id
│  ├─ version_number (INT)
│  ├─ structure (JSONB: snapshot of form_sections + form_fields)
│  ├─ created_at (TIMESTAMPTZ)
│  ├─ created_by (UUID) → users.id
│  ├─ change_summary (TEXT)
│  └─ is_active (BOOLEAN)

OPERATIONS:
- Create new version on publish: INSERT form_versions (form_id, version_number, structure)
- Rollback: Copy from form_versions back to forms/form_sections/form_fields
- Show diff: Compare structure JSONs
- List versions: SELECT FROM form_versions WHERE form_id = ? ORDER BY version_number DESC
```

---

### MODULE 6: RESOURCE MANAGEMENT

#### Attachments Module

**AttachmentBrowser**
```
DATABASE TABLES:
┌─ attachments
│  ├─ id (UUID)
│  ├─ attachment_type_id (UUID) → attachment_types.id
│  ├─ original_filename (VARCHAR 255) ← GRID
│  ├─ stored_filename (VARCHAR 255) ← Internal storage name
│  ├─ file_path (VARCHAR 500) ← Storage path
│  ├─ file_size_bytes (INT) ← GRID, display formatted
│  ├─ mime_type (VARCHAR 100) ← Determine icon/preview
│  ├─ file_hash (VARCHAR 64) ← Duplicate detection
│  ├─ entity_type (VARCHAR 100: order, complaint, product, marketing, invoice) ← FILTER
│  ├─ entity_id (UUID) ← FILTER
│  ├─ uploaded_by (UUID) → users.id ← GRID
│  ├─ uploaded_at (TIMESTAMPTZ) ← GRID, SORT
│  ├─ is_deleted (BOOLEAN) ← FILTER
│  ├─ deleted_at (TIMESTAMPTZ)
│  └─ deleted_by (UUID) → users.id
├─ attachment_types
│  ├─ id (UUID)
│  ├─ type_name (VARCHAR 100)
│  ├─ allowed_extensions (VARCHAR 255)
│  ├─ max_file_size_mb (INT)
│  └─ created_at
└─ users (for uploaded_by, deleted_by)

GRID COLUMNS:
- original_filename (with file type icon from mime_type)
- file_size (formatted from file_size_bytes)
- uploaded_by (first_name, last_name from users)
- uploaded_at (timestamp formatted)
- entity_type
- entity_name (JOIN to get order#, product_name, etc.)
- virus_status (separate field or API call)
- actions (download, preview, delete)

FILTERS:
- entity_type: WHERE attachments.entity_type IN (...)
- file_type: Derived from mime_type or file extension
- upload_date: WHERE uploaded_at BETWEEN ? AND ?
- is_deleted: WHERE is_deleted = false/true
- virus_status: WHERE virus_status = 'clean'

SEARCH:
- original_filename ILIKE ?

BULK ACTIONS:
- Delete: UPDATE is_deleted = true, deleted_at = NOW(), deleted_by = current_user
- Restore: UPDATE is_deleted = false, deleted_at = NULL, deleted_by = NULL
```

**FileUploadZone**
```
DATABASE OPERATIONS:

FILE VALIDATION:
1. Check file extension against attachment_types.allowed_extensions
2. Check file size against attachment_types.max_file_size_mb
3. Show validation error if invalid

FILE PROCESSING:
1. Calculate file_hash (SHA-256)
2. Check for duplicates: SELECT FROM attachments WHERE file_hash = ? AND is_deleted = false
3. If duplicate exists, show warning
4. Store file on disk/S3 with stored_filename
5. Trigger virus scan (external service)

DATABASE INSERT:
INSERT INTO attachments (
  attachment_type_id,       ← FROM attachment_types based on file extension
  original_filename,        ← User's file name
  stored_filename,          ← Hashed storage name
  file_path,                ← Storage location
  file_size_bytes,          ← SIZE OF FILE
  mime_type,                ← mime type detected
  file_hash,                ← SHA-256 hash
  entity_type,              ← 'order', 'complaint', 'product', etc.
  entity_id,                ← Related entity ID
  uploaded_by,              ← Current user ID
  uploaded_at               ← NOW()
)

TRIGGER n8n WEBHOOK (optional):
POST to n8n webhook: /webhook/file-uploaded
{
  attachment_id,
  entity_type,
  entity_id,
  filename,
  file_hash
}
```

**FilePreviewModal**
```
DATABASE READS:
SELECT FROM attachments WHERE id = ?

PREVIEW BY MIME_TYPE:

PDF (application/pdf):
- Use react-pdf-viewer library
- Load file from file_path (or download endpoint)
- Show toolbar: zoom, page nav, search, download, fullscreen
- Display: number of pages, page size

IMAGES (image/jpeg, image/png, image/gif, image/svg+xml):
- Use lightbox/gallery library
- Show multiple images if multiple selected
- Features: zoom, pan, rotate, fullscreen
- Download button

EXCEL (application/vnd.ms-excel, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet):
- Parse first sheet as data
- Display as TanStack table (read-only grid)
- Show column headers, first 50 rows
- Download full file button
- Sheet selector if multiple sheets

WORD (application/vnd.openxmlformats-officedocument.wordprocessingml.document):
- Show formatted preview or fallback
- Download button
- Message: "Open in Microsoft Office Online"

TEXT FILES (text/plain, text/csv, application/json):
- Show in code editor (read-only)
- Syntax highlighting
- Line numbers
- Copyable text

UNSUPPORTED:
- Show file icon, size, type
- Download button only
- Message: "This file type cannot be previewed"

METADATA DISPLAY:
- filename: FROM original_filename
- file_size: FORMAT file_size_bytes (1.5 MB)
- mime_type: FROM mime_type
- uploaded_by: JOIN users table
- uploaded_at: FORMAT timestamp
- entity: Display entity_type and entity_name
- virus_status: Icon/badge showing scan status
- file_hash: Display for reference
- download_count: COUNT FROM download_log table (if tracked)
```

**Virus Scan Integration**
```
SCAN STATUS DISPLAY:

STATUS VALUES:
- 'clean': File scanned, no threats
- 'scanning': File currently being scanned
- 'infected': Threats detected, block download
- 'unknown': Scan not completed

BADGE DISPLAY:
- Clean: ✓ Green checkmark "Clean"
- Scanning: ⏳ Yellow spinner "Scanning..."
- Infected: ✗ Red X "Infected - Download blocked"
- Unknown: ? Gray "Pending scan"

SCAN TRIGGER:
POST /api/attachments/:id/scan-virus

BLOCK DOWNLOAD:
IF attachments.virus_status = 'infected':
  Disable download button
  Show message: "This file contains malware and cannot be downloaded"
  
LOG INFECTION:
INSERT INTO audit_logs (
  entity_type = 'attachment',
  entity_id = attachment_id,
  action = 'SECURITY_ALERT',
  user_id = NULL (system),
  new_values = {virus_status: 'infected', threat_details: ...}
)

NOTIFY ADMIN:
Send email alert to admin
```

**Soft Delete & Restore**
```
DATABASE OPERATIONS:

SOFT DELETE:
UPDATE attachments SET 
  is_deleted = true,
  deleted_at = NOW(),
  deleted_by = current_user_id
WHERE id = ?

LOG ACTION:
INSERT INTO audit_logs (
  entity_type = 'attachment',
  entity_id = attachment_id,
  action = 'DELETE',
  user_id = current_user_id,
  old_values = {...attachment data...},
  new_values = {is_deleted: true}
)

RESTORE:
UPDATE attachments SET
  is_deleted = false,
  deleted_at = NULL,
  deleted_by = NULL
WHERE id = ? AND deleted_at IS NOT NULL

FILTER DELETED FILES:
By default: SELECT FROM attachments WHERE is_deleted = false
Show deleted only: WHERE is_deleted = true
Include both: All files
```

---

#### Attachment Types Module

**AttachmentTypesList**
```
DATABASE TABLES:
┌─ attachment_types
│  ├─ id (UUID)
│  ├─ type_name (VARCHAR 100) ← GRID
│  ├─ description (TEXT) ← GRID
│  ├─ allowed_extensions (VARCHAR 255) ← GRID (comma-separated)
│  ├─ max_file_size_mb (INT) ← GRID
│  ├─ created_at (TIMESTAMPTZ)
│  └─ (is_active not in schema, but could add)

GRID COLUMNS:
- type_name
- description
- allowed_extensions (e.g., "pdf,doc,xls")
- max_file_size_mb (e.g., "10 MB")

ACTIONS:
- Create: INSERT attachment_types
- Edit: UPDATE attachment_types
- Delete: DELETE attachment_types (hard delete, or soft if in use)

VALIDATION:
- Cannot delete type if attachments exist with that type
- Cannot delete if type is in use
```

**AttachmentTypeForm**
```
DATABASE FIELDS:
- type_name → attachment_types.type_name (required, unique)
- description → attachment_types.description (optional)
- allowed_extensions → attachment_types.allowed_extensions (required, comma-separated)
- max_file_size_mb → attachment_types.max_file_size_mb (required, default 10)

EXTENSION MANAGER:
- List of extensions for type
- Add extension: Append to allowed_extensions comma-separated
- Remove extension: Remove from list
- Validate: alphanumeric only, lowercase, single word (e.g., "pdf", "docx")
- Display MIME types as tooltips

EXAMPLE:
- Type: "Documents"
- Extensions: "pdf,doc,docx"
- Size: 25 MB
```

---

## 🔄 RELATIONSHIP DIAGRAM

```
┌─────────────────────────────────────────┐
│         USERS & AUTHENTICATION          │
│  users ←→ groups ←→ user_roles ←→ roles│
│           ↓                              │
│  All tables have created_by/updated_by  │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│         MASTER DATA CORE                │
│  products → product_categories          │
│  products → brands                      │
│  products → units_of_measure            │
│  products → attachments                 │
│  suppliers → attachments                │
│  warehouses → storage_zones             │
│  promotions → promotion_products → prod │
│  marketing_campaigns → campaign_types   │
│  forms → attachments                    │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│         OPERATIONAL DATA                │
│  orders ← customers                     │
│  order_items → products, orders         │
│  complaints → complaint_categories      │
│  complaint_manual → complaints          │
│  inbound_shipments → suppliers          │
│  inbound_shipment_lines → products      │
│  picking_headers, picking_lines         │
│  communications (multi-channel)         │
│  conversation_sla_tracking → sla_polici│
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│    STOCK & INVENTORY TRANSACTIONS       │
│  stock (product × warehouse)            │
│  stock_batches → products, warehouses   │
│  stock_transactions (movement history)  │
│  stock_transactions → users             │
│  stock_transactions → warehouses        │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│         AUDIT & COMPLIANCE              │
│  audit_logs (all CREATE/UPDATE/DELETE)  │
│  system_activity_logs (system events)   │
│  email_templates (notification templates│
└─────────────────────────────────────────┘
```

---

## ✅ IMPLEMENTATION CHECKLIST BY MODULE

### Module: Master Data Management

**Products**
- [ ] types/product.types.ts - Define interfaces
- [ ] services/productService.ts - API calls (GET, POST, PUT, DELETE)
- [ ] hooks/useProducts.ts - CRUD hook
- [ ] hooks/useProductFilters.ts - Filter state management
- [ ] components/ProductsList.tsx - Grid with DataGrid component
- [ ] components/ProductForm.tsx - 5-tab form
- [ ] components/ProductDetail.tsx - Detail page
- [ ] page.tsx - List page
- [ ] [id]/page.tsx - Detail page
- [ ] [id]/edit/page.tsx - Edit page (optional, can be modal)

**Product Categories**
- [ ] types/category.types.ts
- [ ] services/categoryService.ts
- [ ] hooks/useProductCategories.ts
- [ ] components/CategoriesList.tsx - Tree view with drag-drop
- [ ] components/CategoryForm.tsx - Modal form
- [ ] shared/ProductCategorySelect.tsx - Reusable selector
- [ ] page.tsx

**Brands**
- [ ] types/brand.types.ts
- [ ] services/brandService.ts
- [ ] hooks/useBrands.ts
- [ ] components/BrandsList.tsx
- [ ] components/BrandForm.tsx
- [ ] shared/BrandSelect.tsx - Reusable selector
- [ ] page.tsx

**Units of Measure**
- [ ] types/uom.types.ts
- [ ] services/uomService.ts
- [ ] hooks/useUOM.ts
- [ ] components/UOMList.tsx
- [ ] components/UOMForm.tsx
- [ ] components/UOMConverter.tsx
- [ ] page.tsx

---

**Status:** Database schema mapping added to proposal  
**Prepared by:** Solution Architecture Team  
**Date:** January 11, 2026
