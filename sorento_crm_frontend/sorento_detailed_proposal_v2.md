# SORENTO AI AUTOMATION - DETAILED FRONTEND PROPOSAL
## Enterprise Master Data Management System with Modular Architecture

**Project Scope:** Build an enterprise-grade admin dashboard using Metronics design system for comprehensive master data management (Products, Suppliers, Inventory, Marketing, Forms, Attachments) with operational data integration.

**Document Version:** 2.0 - Enhanced with Detailed Features & Architecture  
**Date:** January 11, 2026  
**Location:** Kajang, Selangor, MY

---

## PROJECT FOLDER STRUCTURE

### Directory Architecture (Following Metronics Convention)

```
/src
  /app
    /admin
      /protected
        
        # 1. MASTER DATA MANAGEMENT
        /master-data-management
          /products
            /components
              ProductsList.tsx          # Main grid/table with filters
              ProductForm.tsx           # Create/edit form
              ProductDetail.tsx         # Read-only detail view
              ProductCategorySelect.tsx # Category selector dropdown
              BrandSelect.tsx          # Brand selector dropdown
              PriceHistory.tsx         # Price trend chart
              ProductAttachments.tsx   # File upload/preview for products
            /hooks
              useProducts.ts           # Custom hook for products CRUD
              useProductFilters.ts     # Filter state management
            /services
              productService.ts        # API calls for products
            /types
              product.types.ts         # TypeScript interfaces
            /constants
              productConstants.ts      # Default values, enums
            page.tsx                   # Products list page
            [id]
              page.tsx                 # Product detail page
              edit
                page.tsx              # Product edit page

          /product-categories
            /components
              CategoriesList.tsx       # List view
              CategoryForm.tsx         # Create/edit modal
              CategoryTree.tsx         # Tree view with drag-drop
            /hooks
              useProductCategories.ts
            /services
              categoryService.ts
            /types
              category.types.ts
            page.tsx                  # Categories management page
            [id]
              page.tsx

          /brands
            /components
              BrandsList.tsx           # Brands data grid
              BrandForm.tsx            # Create/edit form
              BrandDetail.tsx          # Detail view with logo preview
            /hooks
              useBrands.ts
            /services
              brandService.ts
            /types
              brand.types.ts
            page.tsx
            [id]
              page.tsx

          /units-of-measure
            /components
              UOMList.tsx
              UOMForm.tsx
              UOMConverter.tsx         # Conversion factor calculator
            /hooks
              useUOM.ts
            /services
              uomService.ts
            /types
              uom.types.ts
            page.tsx

          # Shared components & utilities for master-data-management
          /shared
            /components
              MasterDataLayout.tsx     # Common layout
              MasterDataNavigation.tsx # Module navigation
              AttachmentUploader.tsx   # Reusable file upload
              PriceGrid.tsx           # Price list display
              StatusBadge.tsx         # Status indicator
            /hooks
              useMasterDataFilters.ts # Common filtering logic
              useBulkActions.ts       # Bulk operations
            /utils
              masterDataFormatters.ts # Formatting helpers
              masterDataValidators.ts # Validation rules

        # 2. PROCUREMENT MANAGEMENT
        /procurement-management
          /suppliers
            /components
              SuppliersList.tsx        # Suppliers grid with contacts
              SupplierForm.tsx         # Create/edit supplier
              SupplierDetail.tsx       # Supplier profile
              SupplierContactCard.tsx  # Contact information
              SupplierRating.tsx       # Performance ratings
              SupplierDocuments.tsx    # Attachments for suppliers
            /hooks
              useSuppliers.ts
              useSupplierFilters.ts
            /services
              supplierService.ts
            /types
              supplier.types.ts
            page.tsx
            [id]
              page.tsx
              edit
                page.tsx

          /product-suppliers
            /components
              ProductSuppliersGrid.tsx # Supplier mapping grid
              SupplierAssignmentModal.tsx # Add/edit supplier for product
              LeadTimeComparison.tsx   # Lead time analysis
              SupplierPerformance.tsx  # KPI dashboard
            /hooks
              useProductSuppliers.ts
            /services
              productSupplierService.ts
            /types
              productSupplier.types.ts
            page.tsx

          /shared
            /components
              SupplierSelector.tsx     # Autocomplete supplier picker
              ContactForm.tsx          # Reusable contact form
              AddressForm.tsx          # Address entry component
            /hooks
              useSupplierContacts.ts
            /utils
              supplierValidators.ts
              supplierFormatters.ts

        # 3. INVENTORY MANAGEMENT
        /inventory-management
          /warehouses
            /components
              WarehousesList.tsx       # Warehouses grid
              WarehouseForm.tsx        # Create/edit warehouse
              WarehouseDetail.tsx      # Warehouse profile with zones
              WarehouseMap.tsx         # Visual warehouse layout
              WarehouseManager.tsx     # Manager assignment
            /hooks
              useWarehouses.ts
            /services
              warehouseService.ts
            /types
              warehouse.types.ts
            page.tsx
            [id]
              page.tsx

          /storage-zones
            /components
              StorageZonesList.tsx     # Zones grid
              StorageZoneForm.tsx      # Create/edit zone
              StorageZoneTree.tsx      # Tree view by warehouse
              ZoneCapacityMetric.tsx   # Utilization display
              ZoneTypeIcon.tsx         # Visual zone type indicator
            /hooks
              useStorageZones.ts
            /services
              storageZoneService.ts
            /types
              storageZone.types.ts
            page.tsx

          /stock
            /components
              StockDashboard.tsx       # Main dashboard with KPIs
              StockBalanceGrid.tsx     # Product-warehouse stock grid
              StockAlert.tsx           # Low stock warnings
              ReorderAnalysis.tsx      # Reorder level visualization
              StockMovement.tsx        # Stock in/out chart
              StockAging.tsx           # Inventory age report
            /hooks
              useStock.ts
              useStockAlerts.ts
            /services
              stockService.ts
            /types
              stock.types.ts
            page.tsx

          /stock-batches
            /components
              BatchesList.tsx          # Batches by product
              BatchForm.tsx            # Create/edit batch
              BatchDetail.tsx          # Batch details with serials
              SerialNumberGrid.tsx     # Serial number listing
              BatchExpiryAlert.tsx     # Expiry warnings
            /hooks
              useStockBatches.ts
            /services
              batchService.ts
            /types
              batch.types.ts
            page.tsx

          /shared
            /components
              WarehouseSelector.tsx    # Warehouse autocomplete
              StorageZoneSelector.tsx
              StockLevelDisplay.tsx    # Visual stock indicator
              BatchSelector.tsx        # Batch picker
              InventoryMetrics.tsx     # KPI cards
            /hooks
              useInventoryFilters.ts
              useStockLevelAlerts.ts
            /utils
              inventoryValidators.ts
              inventoryFormatters.ts

        # 4. MARKETING MANAGEMENT
        /marketing-management
          /promotions
            /components
              PromotionsList.tsx       # Active/inactive promotions
              PromotionForm.tsx        # Create/edit promotion
              PromotionDetail.tsx      # Promotion details
              PromotionCalendar.tsx    # Timeline view
              PromotionMetrics.tsx     # Performance KPIs
              PromoTypeIcon.tsx        # Visual promo type
            /hooks
              usePromotions.ts
              usePromotionFilters.ts
            /services
              promotionService.ts
            /types
              promotion.types.ts
            page.tsx
            [id]
              page.tsx

          /promotion-products
            /components
              PromotionProductsGrid.tsx # Products in promotion
              ProductSelector.tsx       # Add products modal
              PricingOverrideForm.tsx   # Discount/override setup
              PromotionProductMetrics.tsx # Per-product performance
            /hooks
              usePromotionProducts.ts
            /services
              promotionProductService.ts
            /types
              promotionProduct.types.ts
            page.tsx

          /campaigns
            /components
              CampaignsList.tsx        # Campaigns grid
              CampaignForm.tsx         # Create/edit campaign
              CampaignDashboard.tsx    # Campaign KPIs & analytics
              BudgetTracker.tsx        # Budget vs actual spend
              CampaignTimeline.tsx     # Campaign schedule
              TargetAudienceForm.tsx   # Audience definition
            /hooks
              useCampaigns.ts
              useCampaignMetrics.ts
            /services
              campaignService.ts
            /types
              campaign.types.ts
            page.tsx
            [id]
              page.tsx

          /shared
            /components
              PromoCodeGenerator.tsx   # Auto-generate codes
              DateRangeSelector.tsx    # Campaign date picker
              BudgetInput.tsx          # Budget field with formatter
              PromotionTypeSelect.tsx  # Type selector dropdown
              CampaignTypeSelect.tsx
            /hooks
              useMarketingFilters.ts
              useCampaignTimeline.ts
            /utils
              marketingValidators.ts
              promoCodeValidator.ts
              marketingFormatters.ts

        # 5. FORMS MANAGEMENT
        /forms-management
          /forms
            /components
              FormsList.tsx            # Forms library grid
              FormBuilder.tsx          # Drag-drop form designer
              FormPreview.tsx          # Live form preview
              FormFieldEditor.tsx      # Field configuration modal
              FormVersionHistory.tsx   # Version management
              FormPublish.tsx          # Publish/activate form
              FieldTypeSelector.tsx    # Field type options
              ValidationRuleBuilder.tsx # Regex/validation setup
            /hooks
              useForms.ts
              useFormBuilder.ts
              useFormVersions.ts
            /services
              formService.ts
              formBuilderService.ts
            /types
              form.types.ts
              formField.types.ts
            page.tsx
            [id]
              page.tsx
              edit
                page.tsx
              builder
                page.tsx             # Form builder interface

          /form-templates
            /components
              TemplateLibrary.tsx      # Pre-built templates
              TemplateSelector.tsx     # Template picker modal
              TemplatePreview.tsx      # Template preview
              TemplateDuplicate.tsx    # Clone template
            /hooks
              useFormTemplates.ts
            /services
              templateService.ts
            /types
              template.types.ts
            page.tsx

          /shared
            /components
              FormFieldRenderer.tsx    # Display any field type
              FormPreviewModal.tsx     # Preview modal
              FieldValidationTest.tsx  # Test validation
              FormExporter.tsx         # Export as JSON/PDF
            /hooks
              useFormValidation.ts
              useFormSections.ts
            /utils
              formValidators.ts
              formFormatters.ts
              fieldRuleEngine.ts

        # 6. RESOURCE MANAGEMENT
        /resource-management
          /attachments
            /components
              AttachmentBrowser.tsx    # Grid of all attachments
              FileUploadZone.tsx       # Drag-drop upload area
              FilePreviewModal.tsx     # Embedded file viewer
              PDFViewer.tsx            # PDF reader with toolbar
              ImageGallery.tsx         # Image lightbox
              ExcelPreview.tsx         # Sheet preview
              DocumentPreview.tsx      # Word/Office fallback
              FileMetadata.tsx         # File info panel
              FileHistory.tsx          # Upload history
            /hooks
              useAttachments.ts
              useFileUpload.ts
              useFilePreview.ts
            /services
              attachmentService.ts
              fileService.ts
            /types
              attachment.types.ts
            page.tsx

          /attachment-types
            /components
              AttachmentTypesList.tsx  # Type configuration grid
              AttachmentTypeForm.tsx   # Create/edit type
              ExtensionManager.tsx     # Manage allowed extensions
            /hooks
              useAttachmentTypes.ts
            /services
              attachmentTypeService.ts
            /types
              attachmentType.types.ts
            page.tsx

          /shared
            /components
              FileTypeIcon.tsx         # Icon by file type
              FileSizeFormatter.tsx    # Size display (KB, MB)
              VirusScanStatus.tsx      # Scan result badge
              FileActionMenu.tsx       # Download/delete menu
              DuplicateDetector.tsx    # Hash-based duplicate warning
            /hooks
              useFileValidation.ts
              useFileSecurity.ts
            /utils
              fileValidators.ts
              fileFormatters.ts
              fileTypeDetector.ts
              hashCalculator.ts

        # GLOBAL PROTECTED LAYOUT & UTILITIES
        /layouts
          AdminLayout.tsx            # Common layout for all admin pages
          SidebarNavigation.tsx      # Module navigation menu
          TopNavigation.tsx          # Top bar with user menu

        /components
          DataGrid.tsx               # Reusable TanStack table grid
          FormBuilder.tsx            # Generic form builder (React Hook Form)
          Modal.tsx                  # Modal wrapper
          ActionButtons.tsx          # CRUD action buttons
          FilterBar.tsx              # Filter UI
          BulkActionsToolbar.tsx    # Bulk operation toolbar
          StatusBadge.tsx
          ConfirmDialog.tsx
          LoadingSpinner.tsx
          EmptyState.tsx
          ErrorBoundary.tsx

        /hooks
          useDataGridState.ts        # Grid pagination, sorting, filtering
          useBulkActions.ts          # Select, bulk update, delete
          useFormState.ts            # Form dirty tracking, validation
          useApiPagination.ts        # Pagination logic
          useSearch.ts               # Search debounce & fuzzy
          useExport.ts               # CSV/Excel export
          usePermissions.ts          # Permission checking in UI
          useAuditTrail.ts           # Track changes
          useNotification.ts         # Toast notifications

        /services
          api.ts                     # Axios instance & interceptors
          authService.ts             # Login, refresh token
          userService.ts             # User API calls
          auditService.ts            # Audit logging
          exportService.ts           # CSV/PDF generation
          notificationService.ts     # Toast handling

        /types
          index.ts                   # Global TypeScript types
          api.types.ts               # API response types
          entities.types.ts          # Database entity types
          permission.types.ts        # RBAC types
          audit.types.ts
          ui.types.ts

        /utils
          validators.ts              # Global validators
          formatters.ts              # Global formatters
          constants.ts               # Global constants
          helpers.ts                 # Utility functions
          errorHandler.ts            # Error handling
          apiConfig.ts               # API configuration
```

---

## DETAILED FEATURE SPECIFICATIONS BY MODULE

### 1. MASTER DATA MANAGEMENT - Products Module

#### 1.1 Products List Page Features

**Data Grid Display:**
- Columns: Product Code | Product Name | Category | Brand | List Price | Status | Created Date
- Sortable columns (click header)
- Filterable: Category, Brand, Status, Price Range
- Search box (live search in product code/name)
- Pagination: 50 rows per page, select 25/100/all
- Total record count displayed
- Sticky header during scroll
- Column width adjustable

**Toolbar Actions:**
- Create Product button → Opens ProductForm modal
- Export button → CSV with visible/selected rows
- Filter reset button
- Advanced filters slide-in panel

**Row Actions:**
- View icon → ProductDetail page
- Edit icon → ProductForm modal (edit mode)
- Delete icon → Soft delete with confirmation
- Duplicate icon → Clone product with new code prompt

**Bulk Actions (when rows selected):**
- Select all checkbox
- Individual checkboxes per row
- Bulk toolbar: Status change (Active/Inactive), Delete, Export
- Clear selection button

**Search & Filter:**
- Real-time search (debounced 300ms)
- Advanced filters: Category tree select, Brand multi-select, Price range slider, Status toggle
- Save filter preset for later use
- Clear all filters button

**Performance:**
- Virtual scrolling for 10K+ rows
- Server-side pagination
- Lazy load product images
- Loading skeleton on initial load
- Empty state with "Create first product" button

**Visual Design:**
- Green badge for Active, Gray for Inactive
- Row hover effect
- Responsive: Mobile → stacked table, Tablet → horizontal scroll
- Metronics color scheme

**API Endpoint:**
```
GET /api/products
  ?page=1&limit=50&category_id=uuid&brand_id=uuid
  &status=active&search=laptop&sort=product_name&order=asc
Response: { data: Product[], total: 1500, page: 1, limit: 50 }
```

---

#### 1.2 Product Create/Edit Form

**Tab 1: Basic Information**
- Product Code: Text input (required, auto-generate option, 50 char limit)
- Product Name: Text input (required, 255 char limit, counter)
- Description: Rich text editor (optional, 2000 char, preview)
- Category: Dropdown with tree search (required)
- Brand: Autocomplete dropdown (optional, shows logo)
- Item Type: Dropdown (product/bundle/service/other)
- Active Status: Toggle switch (default: true)

**Tab 2: Pricing**
- List Price: Number input (required, 2 decimals, currency symbol)
- Cost Price: Number input (optional, 2 decimals, hidden for viewers)
- Invoice Price: Number input (optional, 2 decimals, hidden for viewers)
- Price History Table: Read-only, shows all versions with dates
- Add New Price button → Set effective date and new price
- Price Trend Chart: Line chart of prices over 12 months

**Tab 3: Specifications**
- Weight: Number + UOM selector (kg, lb, g)
- Dimensions: Length, Width, Height (number + UOM selector)
- Warranty Months: Number input (optional)
- Has Serial Tracking: Checkbox
- Has Batch Tracking: Checkbox
- Reorder Level: Number (default 10)
- Reorder Quantity: Number (default 50)

**Tab 4: Unit of Measure**
- Base UOM: Dropdown (required)
- Alternative UOMs: Table with conversion factors
- Add UOM button → Modal to select and set conversion
- Remove UOM button with confirmation

**Tab 5: Attachments**
- FileUploadZone (drag-drop area)
- Allowed: PDF, DOC, XLS, JPG, PNG
- Max size: 10MB
- Show uploaded files as cards:
  - Thumbnail (images)
  - Filename, size, upload date
  - Uploaded by username
  - Delete button
- Click card to preview

**Form Validation:**
- Product Code: Required, unique, alphanumeric with dash/underscore
- Product Name: Required, 3-255 chars
- List Price: Required, > 0
- Category: Required
- All prices: Valid decimals
- Weight/dimensions: Positive numbers

**Form Behavior:**
- Auto-save draft every 30 seconds to localStorage
- Show "Unsaved changes" warning on navigate away
- Success toast on save
- Error toast on validation failure
- Loading spinner on submit
- Disable submit button during API call
- Lock form if being edited by another user (display message)
- Tab navigation (keyboard support)

**API:**
```
POST /api/products
PUT /api/products/:id
GET /api/products/:id
```

---

#### 1.3 Product Detail Page

**Header Section:**
- Breadcrumb: Admin > Master Data > Products > [Product Name]
- Product Code and Name (large heading)
- Status badge (Active/Inactive)
- Action buttons: Edit, Delete, Print, More menu

**Left Sidebar (Quick Info Card):**
- Category badge
- Brand with logo
- List Price (highlighted)
- Status
- Created: Date + user
- Updated: Date + user
- Version history link

**Main Content Tabs:**

**Tab 1: Overview**
- Basic info (read-only fields)
- Pricing summary
- Specifications grid
- Warranty info
- Serial/Batch tracking flags

**Tab 2: Stock**
- Stock by warehouse grid (warehouse | available | reserved | total)
- Low stock alerts if below reorder level
- Stock movement chart (30 days)
- Stock aging report

**Tab 3: Related Data**
- Product Suppliers table (supplier | lead time | min qty | status)
- Current Promotions table
- Recent Orders table (order # | qty | date)
- Attachments section

**Tab 4: Audit Trail**
- Created by, created date
- Last modified by, last modified date
- Version history (expandable)
- Change log (field-by-field changes)

---

#### 1.4 Product Categories (Tree Management)

**Tree View Display:**
- Hierarchical structure (parent-child)
- Expandable/collapsible nodes
- Category Code | Category Name (per node)
- Active/Inactive visual (green/gray)
- Product count per category
- Drag-drop to reorder or move to parent
- Right-click context menu: Edit, Delete, Create sub-category

**Toolbar:**
- Create Category button
- Expand all / Collapse all buttons
- Search categories box
- Refresh button

**Category Form (Modal):**
- Category Code: Text (required, unique, auto-generate)
- Category Name: Text (required, 150 char)
- Description: Textarea (optional)
- Parent Category: Dropdown (optional, for hierarchies)
- Active: Toggle
- Display Order: Number (for custom sort)

**API:**
```
GET /api/product-categories (tree structure)
POST /api/product-categories
PUT /api/product-categories/:id
DELETE /api/product-categories/:id
```

---

#### 1.5 Brands Management

**Brands List:**
- Grid: Brand Code | Brand Name | Manufacturer | Logo | Status | Actions
- Logo column shows thumbnail (50x50px)
- Create, Edit, Delete actions
- Search by brand code/name
- Filter by status (active/inactive)
- Bulk status change
- Export to Excel

**Brand Form:**
- Brand Code: Text (required, unique)
- Brand Name: Text (required, 150 char)
- Manufacturer: Text (optional)
- Website URL: Text (optional, URL validation)
- Description: Rich text (optional)
- Logo: File upload (image, shows preview)
- Active: Toggle

**API:**
```
GET /api/brands
POST /api/brands
PUT /api/brands/:id
DELETE /api/brands/:id
POST /api/brands/:id/logo (image upload)
```

---

### 2. PROCUREMENT MANAGEMENT - Suppliers & Product-Suppliers

#### 2.1 Suppliers List & Detail

**Suppliers Grid:**
- Columns: Supplier Code | Supplier Name | Contact Person | Phone | Email | Status
- Advanced filters: Country, City, Payment Terms, Status
- Search by code/name
- Create, Edit, Delete actions
- View detail page

**Supplier Detail Page:**
- Contact info card (name, email, phone, website)
- Full address display
- Payment terms: XXX days
- Linked products: Grid showing all products from this supplier
- Performance rating: Stars (5) with breakdown:
  - On-time delivery %
  - Quality (defect %)
  - Price competitiveness
- Recent orders from supplier
- Attachments: Certificates, agreements

**Supplier Form:**
- Supplier Code: Text (required, unique)
- Supplier Name: Text (required, 255 char)
- Contact Name: Text (optional)
- Email: Email field (optional)
- Phone: Text (optional)
- Website: Text (optional)
- Address section:
  - Line 1: Text (required)
  - Line 2: Text (optional)
  - City: Text (required)
  - State: Text (required)
  - Postal Code: Text (required)
  - Country: Dropdown (required)
- Payment Terms Days: Number (default 30)
- Active: Toggle
- Attachments: Upload area

**API:**
```
GET /api/suppliers
POST /api/suppliers
PUT /api/suppliers/:id
DELETE /api/suppliers/:id
GET /api/suppliers/:id/linked-products
GET /api/suppliers/:id/performance-metrics
```

---

#### 2.2 Product-Suppliers Mapping

**Product-Suppliers Grid:**
- Columns: Product Code | Product Name | Supplier Code | Supplier Name | Lead Time Days | Min Order Qty | Status
- Add supplier for product: Button → Modal
- Remove supplier: Action button with confirmation
- Edit lead time/min qty: Inline or modal
- Filter by product, supplier, status
- Lead time comparison chart (compare suppliers for same product)

**Assignment Form (Modal):**
- Product: Autocomplete selector (required)
- Supplier: Autocomplete selector (required)
- Lead Time Days: Number (required, positive)
- Min Order Quantity: Number (required, positive)
- Is Primary: Checkbox (mark as primary supplier for product)
- Valid From Date: Date picker (optional)
- Valid To Date: Date picker (optional)
- Notes: Textarea (optional)

**Bulk Upload:**
- CSV template download button
- Upload CSV area
- Expected columns: Product Code, Supplier Code, Lead Time Days, Min Qty
- Show validation errors before confirming
- Preview before upload
- Confirmation and success message

**API:**
```
GET /api/product-suppliers
POST /api/product-suppliers
PUT /api/product-suppliers/:id
DELETE /api/product-suppliers/:id
GET /api/products/:id/suppliers
POST /api/product-suppliers/bulk-upload
```

---

### 3. INVENTORY MANAGEMENT - Warehouses, Zones, Stock, Batches

#### 3.1 Warehouses Management

**Warehouses List:**
- Grid: Warehouse Code | Warehouse Name | Location | Manager | Status | Zones Count
- Create, Edit, Delete actions
- View detail page

**Warehouse Detail:**
- Manager info (name, contact)
- Address/location
- Storage zones: Tree view or grid
- Stock summary: Total products, Total quantity
- Capacity utilization: Visual gauge (%)
- Recent activity: Receiving/picking logs
- Zones table: Code | Name | Type | Capacity | Utilization

**Warehouse Form:**
- Warehouse Code: Text (required, unique)
- Warehouse Name: Text (required, 150 char)
- Location: Text (required)
- Manager: Autocomplete user selector (optional)
- Address: Text (optional)
- Active: Toggle

---

#### 3.2 Storage Zones (Tree Management)

**Zones Tree View:**
- By warehouse (expandable)
- Zone properties: Code, Name, Type (icon), Capacity, Utilization %
- Drag-drop to reorder or move zones
- Create zone button (per warehouse)
- Edit/Delete actions per zone

**Zone Form:**
- Warehouse: Dropdown (required)
- Zone Code: Text (required, unique per warehouse)
- Zone Name: Text (optional)
- Zone Type: Dropdown (required: shelf, rack, bin, pallet)
- Capacity: Number (items max, required)
- Active: Toggle

**Zone Visualization:**
- Color-coded by type (shelf=blue, rack=green, etc.)
- Utilization bar (visual fill percentage)
- Hover shows capacity and current items

**API:**
```
GET /api/warehouses/:id/zones (tree structure)
POST /api/storage-zones
PUT /api/storage-zones/:id
DELETE /api/storage-zones/:id
```

---

#### 3.3 Stock Dashboard & Balance

**Stock Dashboard:**
- KPI Cards:
  - Total SKUs in stock
  - Total quantity across warehouses
  - Low stock alert count (clickable)
  - Overstock warning count (clickable)
- Charts:
  - Stock by Warehouse (donut chart)
  - Stock by Category (bar chart)
  - Stock movement last 30 days (line chart)
- Low Stock Alert List: Table with product code, warehouse, qty, reorder level

**Stock Balance Grid:**
- Columns: Product Code | Product Name | Category | Warehouse | Available | Reserved | Total | Reorder Level | Status
- Status color-coded:
  - Red: Below reorder level
  - Yellow: Critical (between reorder and safety)
  - Green: Normal
  - Orange: Overstock
- Filter by warehouse, category, status
- Search by product code/name
- Show reorder level for context
- Sorting by any column
- Bulk actions: Trigger replenishment, adjust stock (admin only)

**Alert System:**
- Real-time notification badge on dashboard icon
- Alert list in sidebar
- Color-coded by severity
- Can dismiss or action on alerts
- Alert history in notifications panel
- Integration with n8n: Trigger workflows on alerts

**API:**
```
GET /api/stock/dashboard
GET /api/stock/balance-grid
  ?warehouse_id=&category_id=&status=low&sort=product_name
GET /api/stock/alerts
```

---

#### 3.4 Stock Batches & Serial Tracking

**Batches List:**
- Grid: Product Code | Batch Code | Qty | Manufactured Date | Expiry Date | Warehouse | Status
- Filter by warehouse, product, status (Available/Reserved/Damaged/Expired)
- Search by batch code
- View detail, Edit, Delete actions
- Expiry alert badge (red if within 30 days)
- Color status badge

**Batch Detail:**
- Product info
- Batch code (unique identifier)
- Manufactured date
- Expiry date (with alert if soon)
- Received date
- Quantities: Total, Available, Reserved
- Warehouse location (warehouse | zone)
- Current status
- Serial numbers table (if applicable):
  - Serial number
  - Individual status
  - QR code (generate)
  - Transaction history per serial
- Batch history/transactions: All in/out movements
- Attachments: Test certificates, quality reports

**Batch Form:**
- Product: Autocomplete selector (required)
- Batch Code: Text (required, unique)
- Warehouse: Dropdown (required)
- Storage Zone: Dropdown (required)
- Manufactured Date: Date picker (optional)
- Expiry Date: Date picker (optional, triggers warnings)
- Received Date: Date picker (required)
- Quantity: Number (required, positive)
- Status: Dropdown (Available/Reserved/Damaged/Expired/Returned)
- Serial Numbers: Text area (comma-separated, optional)
- Attachments: File upload

**Serial Number Management:**
- Bulk add: Paste comma-separated list
- Individual entry: Add one at a time
- Generate QR codes for tracking
- Per-serial status tracking
- QR code scanner (mobile) integration (future)

**API:**
```
GET /api/stock-batches
POST /api/stock-batches
PUT /api/stock-batches/:id
GET /api/stock-batches/:id/serials
POST /api/stock-batches/:id/serials/bulk
GET /api/stock-batches/:id/transactions
DELETE /api/stock-batches/:id/serials/:serialId
```

---

### 4. MARKETING MANAGEMENT - Promotions & Campaigns

#### 4.1 Promotions Management

**Promotions List:**
- Grid: Promo Code | Name | Type | Start Date | End Date | Status | Actions
- Filter by type, status, date range
- Calendar view option (events showing promos)
- Search by code/name
- Create, Edit, Delete actions
- Bulk actions: Activate/Deactivate, Export, Delete

**Promotion Types:**
- Price Override: Fixed price (replaces list price)
- Discount Percent: % off list price (0-100)
- Discount Amount: Fixed $ amount off
- Bundle: Multiple products at combined price
- Other: Custom promotions

**Promotion Form:**
- Promo Code: Text (required, unique, auto-generate with button)
- Name: Text (required, 255 char)
- Type: Dropdown (required)
- Description: Rich text (optional)
- Start Date: Date picker (required)
- End Date: Date picker (required, must be after start)
- Active: Toggle
- Type-specific fields (conditional show):
  - Price Override: New price field
  - Discount %: Percentage input (0-100)
  - Discount Amount: Amount input ($)
  - Bundle: Product grid (add products)

**Promotion Detail Page:**
- Promotion info display
- Products in promotion: Grid (code | name | list price | promo price | discount)
  - Add products button → Search and select
  - Remove product button
  - Edit promo price per product
- Promotion Metrics:
  - Units sold during promo
  - Revenue during promo
  - Total discount given
  - Unique customers
  - Repeat purchase rate
- Promo Timeline
- Edit / Delete buttons

**Promotion Products Grid:**
- Show all products currently in this promotion
- Product Code | Product Name | List Price | Promo Price | Discount | Discount % | Category
- Bulk edit promo prices
- Add products button (modal with product search)
- Remove product confirmation
- Re-sort products

**API:**
```
GET /api/promotions
POST /api/promotions
PUT /api/promotions/:id
DELETE /api/promotions/:id
GET /api/promotions/:id/products
POST /api/promotions/:id/products (add)
PUT /api/promotions/:id/products/:productId
DELETE /api/promotions/:id/products/:productId
GET /api/promotions/:id/metrics
```

---

#### 4.2 Campaigns Management

**Campaigns List:**
- Grid: Campaign Code | Campaign Name | Type | Start Date | End Date | Budget | Spent | Status
- Filter by type, status, date range, budget range
- Search by code/name
- Create, Edit, Delete actions
- View detail page with dashboard

**Campaign Form:**
- Campaign Code: Text (required, unique, auto-generate)
- Campaign Name: Text (required, 255 char)
- Campaign Type: Dropdown (required, from campaign_types)
- Description: Rich text (optional)
- Start Date: Date picker (required)
- End Date: Date picker (optional)
- Budget: Currency input (optional)
- Target Audience: Text area (description, optional)
- Status: Dropdown (planning/active/completed/cancelled)
- Attachments: File upload (campaign materials)

**Campaign Dashboard:**
- Header info: Code, name, type, dates, budget
- Budget tracking:
  - Total budget (display)
  - Spent to date (display)
  - Remaining budget (display)
  - Progress bar (% spent)
  - Budget burn rate ($/day)
  - Warning if >90% spent or overspending pace
- Associated products/promotions: Grid
- Campaign activities: Event list
- Performance metrics:
  - Total impressions
  - Click-through rate
  - Conversion rate
  - Revenue attributed
- Timeline view showing activities and milestones
- Related orders: Orders from this campaign

**Budget Tracker Component:**
- Monthly budget vs actual spend chart (line + bar combo)
- Variance analysis (over/under)
- Budget allocation by activity/product
- Forecast spending to campaign end

**API:**
```
GET /api/marketing-campaigns
POST /api/marketing-campaigns
PUT /api/marketing-campaigns/:id
DELETE /api/marketing-campaigns/:id
GET /api/marketing-campaigns/:id/metrics
GET /api/marketing-campaigns/:id/budget-tracker
GET /api/marketing-campaigns/:id/activities
GET /api/campaign-types
```

---

### 5. FORMS MANAGEMENT - Dynamic Form Builder

#### 5.1 Forms List & Builder

**Forms List:**
- Grid: Form Code | Form Name | Purpose | Language | Version | Status | Last Updated | Actions
- Filter by language, status, purpose, version
- Search by code/name
- Create form button
- Actions per form: Edit, View, Duplicate, Delete, Publish, View versions

**Form Builder Interface:**
- Split screen:
  - Left (30%): Form tree (sections + fields)
  - Center (40%): Field editor (properties)
  - Right (30%): Live preview (mobile responsive)

**Form Structure:**
- Form has Sections (logical groupings)
- Section has Fields (individual input elements)
- Field types: Text, Textarea, Number, Email, Phone, Date, Date Range, Dropdown, Radio, Checkbox, Multi-select, File Upload, Rich Text, Signature

**Left Panel (Form Tree):**
- Form name (editable)
- Add Section button
- Drag-drop sections to reorder
- Per section:
  - Section name (editable)
  - Add Field button
  - Drag-drop fields
  - Delete section button
- Visual field type icons

**Center Panel (Field Properties):**
- Field label (text input)
- Field name/identifier (auto-generated, editable, alphanumeric)
- Field type (dropdown to change)
- Field group: Basic | Validation | Conditional | Advanced
  - Basic: Label, help text, placeholder
  - Validation: Required, regex pattern, min/max length, email format
  - Conditional: Show if field X = value Y
  - Advanced: Default value, field width (full/half), CSS class
- Delete field button
- Preview of field (real-time)

**Right Panel (Live Preview):**
- Responsive preview toggle (desktop/tablet/mobile)
- Show form as users will see
- Test form interaction (no validation)
- Show error states when required field empty
- Show conditional field logic working
- Test file upload (no actual upload)

**Validation Rule Builder:**
- Required: Checkbox
- Min Length: Number input
- Max Length: Number input
- Email Format: Checkbox
- Phone Format: Checkbox
- Regex Pattern: Text input with tester
- Custom Validation: JavaScript expression (future)

**Field Conditional Logic:**
- Show/hide field based on another field value
- If [field] equals [value] then show this field
- Multiple conditions (AND/OR logic)
- Visual rule builder

**Form Versioning:**
- Each form can have multiple published versions
- Version list with dates and change summary
- Set effective date for versions
- Rollback to previous version button
- Version diff view (what changed)
- Auto-save as draft (not published)
- Publish button to activate version
- Unpublish old versions

**Multi-Language Support:**
- Language selector dropdown (en, MY, etc.)
- Translate form, section, field labels
- Translate help texts and placeholders
- Per-language content storage

**Form Export/Import:**
- Export form as JSON (for backup or sharing)
- Export form as PDF (printable)
- Import form from JSON
- Template library access

**API:**
```
GET /api/forms (list)
POST /api/forms (create)
GET /api/forms/:id (full structure)
PUT /api/forms/:id (update)
DELETE /api/forms/:id
GET /api/forms/:id/versions
POST /api/forms/:id/publish
PUT /api/forms/:id/unpublish
GET /api/forms/:id/preview (render HTML)
POST /api/forms/:id/validate (validate submission)
```

---

### 6. RESOURCE MANAGEMENT - Attachments & Files

#### 6.1 File Upload & Management

**Attachment Browser:**
- Grid: Filename | Type | Size | Uploaded By | Upload Date | Entity | Entity Name | Status | Actions
- Filter by entity type, file type, upload date, status (deleted/active)
- Search by filename
- Pagination (20, 50, 100)
- Bulk actions: Delete, Restore
- Row actions: Download, Preview, View metadata, Delete

**File Upload Zone (Drag-Drop Component):**
- Large rectangular drop area
- "Click to browse" link inside
- Show selected file(s) before upload
- File validation:
  - Type checking (allowed extensions)
  - Size checking (max file size)
  - Show validation error if invalid
- Upload progress bar per file
- Show upload speed and estimated time remaining
- Cancel upload button
- Success toast with file link
- Error handling with retry button (auto-retry 3 times)
- Show file size in human-readable format

**File Preview System:**

**PDF Files:**
- Embedded PDF viewer with controls
- Zoom buttons (in/out, fit-to-page, fit-to-width)
- Pan (click and drag)
- Page navigation (previous, next, go to page)
- Page counter (page X of Y)
- Search within PDF
- Print button
- Download button
- Full screen option

**Images (JPG, PNG, GIF, SVG):**
- Lightbox gallery view
- Thumbnail grid for multiple images
- Zoom in/out buttons
- Pan and drag
- Full screen button
- Rotate 90° / Flip buttons
- Download button
- Previous/Next buttons for gallery

**Excel Files (.xls, .xlsx):**
- Show first sheet as grid preview
- Display column headers
- Show first 50 rows
- Scrollable (horizontal and vertical)
- No editing, read-only
- Download full file button
- Sheet selector if multiple sheets

**Word/Office Documents (.docx, .xlsx, .pptx):**
- Show formatted preview if possible
- Fallback: Document icon + metadata
- Download button (browser opens in Office Online if available)
- Info: "Preview not available for this format"

**Text Files (.txt, .csv, .json):**
- Show content in code editor (read-only)
- Line numbers
- Syntax highlighting for code files
- Copyable text

**Unsupported Formats:**
- Show file icon + filename
- File size and type
- Message: "This file type cannot be previewed"
- Download button to open externally

**File Metadata Display:**
- Filename (original, editable description optional)
- File size (formatted: 1.5 MB, 350 KB)
- MIME type (display to user)
- Upload date and time (formatted)
- Uploaded by (username with link to user profile)
- Entity linked to (e.g., "Order #ORD-001" as link)
- Virus scan status: ✓ Clean, ⏳ Scanning, ✗ Infected
- File hash (SHA-256 for duplicate detection)
- Download count
- Last downloaded date

**Virus Scan Status:**
- Badge display: Green checkmark (Clean), Yellow spinning (Scanning), Red X (Infected)
- "Scanning..." message during scan
- Cannot download if status is Infected
- Notify user if virus detected
- Log infection in audit trail

**Soft Delete & Restore:**
- Delete button → Soft delete (set is_deleted=true, deleted_at, deleted_by)
- Deleted files shown in filtered view with "Deleted" badge
- Restore button to recover deleted file
- Show deleted date and who deleted
- Hard delete only by admin after retention period (configurable)

**Duplicate Detection:**
- File hash (SHA-256) calculated on upload
- Compare hash against existing files
- Show warning: "File with same content already exists (uploaded X days ago)"
- Allow user to proceed or choose existing file
- Prevent duplicate uploads (optional setting)

**API:**
```
GET /api/attachments
  ?entity_type=order&entity_id=uuid&page=1&limit=20
POST /api/attachments (multipart/form-data)
  - file: binary
  - entity_type: string
  - entity_id: uuid
  - description: optional
GET /api/attachments/:id/metadata
GET /api/attachments/:id/download
GET /api/attachments/:id/preview (return file content or preview HTML)
DELETE /api/attachments/:id (soft delete)
PUT /api/attachments/:id/restore
POST /api/attachments/:id/virus-scan (trigger scan)
GET /api/attachments/hash/:hash (check duplicate by hash)
```

---

#### 6.2 Attachment Types Configuration

**Attachment Types List:**
- Grid: Type Name | Allowed Extensions | Max File Size (MB) | Description | Status
- Create, Edit, Delete actions

**Attachment Type Form:**
- Type Name: Text (required, unique)
- Description: Text (optional)
- Allowed Extensions: Text area (comma-separated: pdf,doc,xls,jpg,png)
- Max File Size (MB): Number (default 10)
- Active: Toggle

**Extension Manager:**
- List of extensions for this type
- Add extension button → Input and add
- Remove extension with confirmation
- Validate extensions (must be single word, alphanumeric, lowercase)
- Tooltips showing MIME types

**API:**
```
GET /api/attachment-types
POST /api/attachment-types
PUT /api/attachment-types/:id
DELETE /api/attachment-types/:id
```

---

## REUSABLE COMPONENTS & HOOKS STRATEGY

### Global Reusable Components

These components appear across multiple modules:

```tsx
// DataGrid.tsx - TanStack React Table wrapper
// Features: Column def management, sorting, filtering, pagination, 
//           bulk row selection, export, responsive mobile
<DataGrid
  columns={columnDefs}
  data={tableData}
  loading={isLoading}
  pagination={{ page, limit, total }}
  onPageChange={setPage}
  onSort={handleSort}
  onFilter={handleFilter}
  actions={[
    { label: 'View', onClick: (row) => viewItem(row.id) },
    { label: 'Edit', onClick: (row) => editItem(row.id) },
    { label: 'Delete', onClick: (row) => deleteItem(row.id) }
  ]}
  bulkActions={[
    { label: 'Activate', onClick: (rows) => bulkActivate(rows) },
    { label: 'Delete', onClick: (rows) => bulkDelete(rows) }
  ]}
/>

// FormBuilder.tsx - React Hook Form + Zod validation wrapper
// Features: Field registration, validation, error display, dirty state, auto-save
<FormBuilder
  schema={validationSchema}
  defaultValues={initialData}
  onSubmit={handleFormSubmit}
  fields={[
    { name: 'productCode', label: 'Product Code', type: 'text', required: true },
    { name: 'productName', label: 'Product Name', type: 'text', required: true },
    { name: 'categoryId', label: 'Category', type: 'select', required: true }
  ]}
  onDirtyChange={setIsDirty}
  autoSaveDraft={true}
/>

// Modal.tsx - Reusable modal dialog wrapper
<Modal
  isOpen={showModal}
  title="Create Product"
  size="lg" // sm, md, lg, xl
  onClose={closeModal}
  footer={
    <>
      <Button variant="secondary" onClick={closeModal}>Cancel</Button>
      <Button variant="primary" onClick={handleSave}>Save</Button>
    </>
  }
>
  <ProductForm />
</Modal>

// StatusBadge.tsx - Visual status indicator
<StatusBadge status="active" label="Active" variant="success" />
<StatusBadge status="inactive" label="Inactive" variant="secondary" />

// FileUploadZone.tsx - Drag-drop file upload
<FileUploadZone
  onFileSelected={handleFiles}
  acceptedTypes=".pdf,.doc,.jpg,.png"
  maxFileSize={10} // MB
  onUploadProgress={setProgress}
  onUploadError={handleError}
/>

// ConfirmDialog.tsx - Delete/action confirmation
<ConfirmDialog
  isOpen={showConfirm}
  title="Delete Product?"
  message="This action cannot be undone."
  confirmLabel="Delete"
  cancelLabel="Cancel"
  onConfirm={handleDelete}
  onCancel={closeConfirm}
  variant="danger"
/>

// FilterBar.tsx - Advanced filtering UI
<FilterBar
  filters={[
    { name: 'category', label: 'Category', type: 'select', options: categories },
    { name: 'status', label: 'Status', type: 'checkbox', options: statuses },
    { name: 'priceRange', label: 'Price Range', type: 'range' }
  ]}
  onApplyFilters={handleFilter}
  onClearFilters={handleClearFilters}
/>

// BulkActionsToolbar.tsx - Shows when rows selected
<BulkActionsToolbar
  selectedCount={selectedRows.length}
  actions={[
    { label: 'Activate', onClick: () => bulkActivate(selectedRows) },
    { label: 'Deactivate', onClick: () => bulkDeactivate(selectedRows) },
    { label: 'Delete', onClick: () => bulkDelete(selectedRows) }
  ]}
  onClearSelection={clearSelection}
/>
```

---

### Custom Hooks (Shared Across Modules)

```typescript
// useDataGridState.ts
// Manages: pagination state, sorting, filters, column preferences
const [gridState, dispatch] = useDataGridState({
  initialPage: 1,
  initialLimit: 50,
  initialSort: { column: 'created_at', order: 'desc' }
});

// useBulkActions.ts
// Manages: row selection, bulk operation loading, error handling
const { 
  selectedRows, 
  selectRow, 
  selectAll, 
  deselectAll,
  handleBulkUpdate,
  handleBulkDelete,
  isLoading,
  error
} = useBulkActions();

// useFormState.ts
// Manages: form dirty state, auto-save draft, restore draft, track changes
const { 
  isDirty, 
  save, 
  hasDraft, 
  restoreDraft,
  getChangeLog,
  isSubmitting,
  error
} = useFormState(formData);

// useSearch.ts
// Debounced search with caching and fuzzy matching
const { 
  searchTerm, 
  setSearchTerm, 
  results, 
  isSearching,
  clearSearch
} = useSearch(
  async (query) => fetchSearchResults(query),
  300 // debounce ms
);

// useApiPagination.ts
// Server-side pagination with caching and prefetch
const { 
  data, 
  loading, 
  page, 
  setPage, 
  total,
  limit,
  setLimit,
  hasNextPage,
  hasPreviousPage
} = useApiPagination('/api/products', { limit: 50 });

// useExport.ts
// Export data to CSV or Excel with formatting
const { 
  exportToCSV,
  exportToExcel,
  isExporting,
  error
} = useExport();

// usePermissions.ts
// Check user permissions for conditional UI rendering
const { 
  can,
  canCreate,
  canEdit,
  canDelete,
  canExecute,
  hasPermission
} = usePermissions('products');

// useAuditTrail.ts
// Track field changes and generate change log
const { 
  trackChange,
  getChangeLog,
  hasChanges,
  changes
} = useAuditTrail();

// useNotification.ts
// Toast/notification management (success, error, warning, info)
const { 
  showSuccess,
  showError,
  showWarning,
  showInfo,
  dismiss
} = useNotification();
```

---

## IMPLEMENTATION ROADMAP FOR CURSOR AI

### Sprint 1: Foundation (Week 1-2)
- [x] Create React project with Metronics integration
- [x] Setup folder structure per specification
- [x] Configure TypeScript, ESLint, Prettier
- [x] Setup Axios with auth interceptors
- [x] Implement authentication module (login, logout, token refresh)
- [x] Create global AdminLayout and SidebarNavigation
- [x] Implement error boundary and error handling
- [x] Setup notification/toast system
- [x] Create global types and constants

### Sprint 2-3: Master Data Core (Week 3-6)
- [ ] Build DataGrid reusable component (TanStack table wrapper)
- [ ] Build FormBuilder component (React Hook Form + Zod)
- [ ] Implement Products module:
  - [ ] Products list page
  - [ ] Product create/edit form
  - [ ] Product detail page
  - [ ] API integration
- [ ] Implement Product Categories (tree view)
- [ ] Implement Brands (CRUD)
- [ ] Implement Units of Measure (CRUD)
- [ ] Build reusable selectors (CategorySelect, BrandSelect, UOMSelect)

### Sprint 4: Procurement (Week 7-8)
- [ ] Implement Suppliers module (list, create, edit, detail)
- [ ] Implement Supplier rating/performance display
- [ ] Implement Product-Suppliers mapping (grid)
- [ ] Build supplier assignment modal
- [ ] CSV bulk upload for suppliers
- [ ] Build SupplierSelector component (reusable)
- [ ] API integration

### Sprint 5-6: Inventory (Week 9-12)
- [ ] Implement Warehouses module (CRUD)
- [ ] Implement Storage Zones (tree view with drag-drop)
- [ ] Implement Stock Dashboard (KPI cards, charts)
- [ ] Implement Stock Balance Grid (product-warehouse matrix)
- [ ] Implement Stock Batches (list, detail, serial tracking)
- [ ] Build stock level alerts
- [ ] Build warehouse/zone selectors
- [ ] API integration

### Sprint 7-8: Marketing (Week 13-16)
- [ ] Implement Promotions module (CRUD, promo types)
- [ ] Implement Promotion Products grid
- [ ] Implement Campaigns module (CRUD)
- [ ] Build budget tracker components
- [ ] Implement campaign metrics/dashboard
- [ ] Build promotion type selector
- [ ] API integration

### Sprint 9: Forms Management (Week 17-18)
- [ ] Implement Forms list page
- [ ] Build Form Builder interface (split-screen UI)
- [ ] Implement form sections and fields
- [ ] Build field property editor
- [ ] Implement form versioning
- [ ] Build form preview (right panel)
- [ ] Implement validation rule builder
- [ ] Implement conditional logic builder
- [ ] Add form publishing/versioning
- [ ] API integration

### Sprint 10: Resource Management (Week 19-20)
- [ ] Build FileUploadZone component
- [ ] Build AttachmentBrowser (grid view)
- [ ] Implement PDF viewer (react-pdf-viewer)
- [ ] Implement image gallery/lightbox
- [ ] Implement Excel preview (data grid)
- [ ] Implement soft delete and restore
- [ ] Build file metadata display
- [ ] Implement virus scan status
- [ ] Implement duplicate detection (hash-based)
- [ ] Implement Attachment Types (CRUD)
- [ ] API integration

### Sprint 11: Access Control & Testing (Week 21-22)
- [ ] Implement permission checking in UI (usePermissions hook)
- [ ] Implement role-based field visibility
- [ ] Build permission matrix view (optional)
- [ ] Add comprehensive unit tests (utilities, hooks)
- [ ] Add component tests (forms, tables, modals)
- [ ] Add integration tests (CRUD flows)
- [ ] Performance testing and optimization
- [ ] Load testing (10K+ records)

### Sprint 12: Polish & n8n Integration (Week 23-24)
- [ ] Integrate n8n webhooks (product, order, complaint events)
- [ ] Build analytics dashboard (optional)
- [ ] Performance optimization (code splitting, lazy loading)
- [ ] Security audit (input validation, sanitization)
- [ ] Documentation (API, components, setup guide)
- [ ] User guide creation
- [ ] Deployment setup (Docker, CI/CD)
- [ ] UAT and final fixes

---

## CURSOR AI FINAL PROMPT

```
PROJECT CONTEXT:
You are building the Sorento Admin Dashboard using this detailed proposal.
This is a production enterprise system, not a prototype.

CODE QUALITY STANDARDS:
- TypeScript strict mode ALWAYS
- ESLint + Prettier (100 char lines)
- JSDoc comments for all public functions and components
- Self-documenting code with clear variable/function names
- WCAG 2.1 AA accessibility standards

DEVELOPMENT APPROACH:
1. Read this entire proposal first
2. Implement types/interfaces BEFORE component logic
3. Build API service layer with proper error handling
4. Build reusable components FIRST (DataGrid, Modal, FormBuilder)
5. Build shared hooks (useDataGridState, useBulkActions, useFormState)
6. Then build domain-specific modules (products, suppliers, etc.)
7. Write tests as you build (unit, component, integration)
8. Optimize for performance (lazy loading, code splitting, virtual scrolling)

FOLDER STRUCTURE:
Follow the exact folder structure in this proposal.
Each module has: components/, hooks/, services/, types/, page.tsx
Shared utilities in: /shared/components, /shared/hooks, /utils

COMPONENT PATTERNS:
- Use React Hook Form + Zod for all forms
- Use TanStack React Table for all grids
- Use Metronics components where available
- Create wrapper components for common patterns
- Export all types from types/ files

API INTEGRATION:
- Axios instance in /services/api.ts
- Interceptors for auth (JWT), error handling
- Service methods return Promise<Data | null>
- Error handling: User-friendly messages, log to Sentry
- Pagination: page, limit, total (server-side default)
- Filtering: Pass filter params to API
- Loading states: Show skeleton or spinner
- Caching: Use React Query or TanStack Query

AUTHENTICATION:
- JWT token from login endpoint
- Store in HttpOnly cookie (preferred) + localStorage fallback
- Refresh token rotation (15 min access, 7 day refresh)
- Auto-logout on token expiry
- Redirect to login on 401 Unauthorized
- Show "Session Expired" message

PERMISSION CHECKING:
- usePermissions hook checks user permissions
- Hide/disable UI elements based on permissions
- API validates permissions (always, don't trust frontend)
- Field-level access: Hide pricing fields from viewers
- Data-level access: Users see only their group's data
- Log permission checks in audit trail

FILE UPLOADS:
- Client-side validation (type, size) before upload
- Server-side validation (ALWAYS)
- Show upload progress bar
- Auto-retry failed uploads (3 attempts)
- Virus scan status display
- Hash-based duplicate detection
- Soft delete capability
- Store files outside web root

PERFORMANCE:
- Virtual scrolling for lists 10K+ rows
- Lazy load images and code-split routes
- Debounce search (300ms)
- Pagination with server-side limits
- Memoize expensive components
- Cache API responses (stale-while-revalidate)
- Monitor bundle size (target < 500KB gzipped)

TESTING:
- Unit tests: Utils, hooks, services (80% coverage)
- Component tests: Forms, grids, modals (critical paths)
- Integration tests: CRUD workflows, auth flow
- E2E tests: Key user journeys (Cypress/Playwright)
- Run tests on every commit (pre-commit hook)

DEPLOYMENT:
- Docker image for containerization
- GitHub Actions for CI/CD
- Automated testing before deploy
- Staging environment for UAT
- Blue-green deployment for zero downtime

WHEN YOU GET STUCK:
1. Check TypeScript errors (compile-time)
2. Check API response format (runtime)
3. Check permissions required (auth error)
4. Check database relationships (data error)
5. Ask for clarification on requirements

NEXT IMMEDIATE STEPS:
1. Initialize React project with Metronics
2. Create folder structure
3. Setup authentication
4. Build DataGrid and FormBuilder components
5. Start with Products module

LET'S BUILD!
```

---

**Status:** Ready for Cursor AI Implementation  
**Document Prepared by:** Solution Architecture Team  
**Date:** January 11, 2026  
**For:** Sorento AI Automation Project
