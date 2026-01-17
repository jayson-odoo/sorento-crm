/**
 * Product Types and Interfaces
 * 
 * Defines TypeScript types for Product module matching database schema
 */

// Product Item Type Enum
export type ProductItemType = 'product' | 'bundle' | 'service' | 'other';

// Product Status
export type ProductStatus = 'active' | 'inactive';

// Product Interface (matches database schema)
export interface Product {
  id: string;
  product_code: string;
  product_name: string;
  description?: string | null;
  category_id: string;
  brand_id?: string | null;
  base_uom_id: string;
  list_price: number;
  cost_price?: number | null;
  invoice_price?: number | null;
  weight?: number | null;
  dimensions_length?: number | null;
  dimensions_width?: number | null;
  dimensions_height?: number | null;
  warranty_months?: number | null;
  has_serial_tracking: boolean;
  has_batch_tracking: boolean;
  reorder_level: number;
  reorder_quantity: number;
  item_type?: ProductItemType | null;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
  created_by?: string | null;
  updated_by?: string | null;
  
  // Relations (populated from API)
  category?: ProductCategory;
  brand?: Brand;
  base_uom?: UnitOfMeasure;
}

// Product Category Interface
export interface ProductCategory {
  id: string;
  category_code: string;
  category_name: string;
  description?: string | null;
  parent_category_id?: string | null;
  is_active: boolean;
  display_order: number;
  created_at: Date;
  updated_at: Date;
  created_by?: string | null;
  
  // Relations
  parent_category?: ProductCategory;
  children?: ProductCategory[];
  product_count?: number;
}

// Brand Interface
export interface Brand {
  id: string;
  brand_code: string;
  brand_name: string;
  manufacturer?: string | null;
  website?: string | null;
  description?: string | null;
  logo_url?: string | null;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
  created_by?: string | null;
  
  product_count?: number;
}

// Unit of Measure Interface
export interface UnitOfMeasure {
  id: string;
  uom_code: string;
  uom_name: string;
  description?: string | null;
  base_uom_id?: string | null;
  conversion_factor?: number | null;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
  created_by?: string | null;
  
  // Relations
  base_uom?: UnitOfMeasure;
  alternatives?: UnitOfMeasure[];
}

// Product Form Data (for create/edit operations)
export interface ProductFormData {
  product_code: string;
  product_name: string;
  description?: string;
  category_id: string;
  brand_id?: string;
  base_uom_id: string;
  list_price: number;
  cost_price?: number;
  invoice_price?: number;
  weight?: number;
  dimensions_length?: number;
  dimensions_width?: number;
  dimensions_height?: number;
  warranty_months?: number;
  has_serial_tracking: boolean;
  has_batch_tracking: boolean;
  reorder_level: number;
  reorder_quantity: number;
  item_type?: ProductItemType;
  is_active: boolean;
}

// Product Filters (for filtering state)
export interface ProductFilters {
  category_id?: string;
  brand_id?: string;
  is_active?: boolean;
  price_range?: {
    min?: number;
    max?: number;
  };
  search?: string;
  item_type?: ProductItemType;
}

// Product API Response
export interface ProductApiResponse {
  data: Product[];
  pagination: {
    total: number;
    page: number;
    limit: number;
  };
  empty: boolean;
}

// Product Detail Response (includes related data)
export interface ProductDetail extends Product {
  stock_by_warehouse?: StockByWarehouse[];
  product_suppliers?: ProductSupplier[];
  current_promotions?: Promotion[];
  recent_orders?: Order[];
  attachments?: Attachment[];
  audit_trail?: AuditLog[];
}

// Stock by Warehouse
export interface StockByWarehouse {
  warehouse_id: string;
  warehouse_name: string;
  available: number;
  reserved: number;
  total: number;
  reorder_level: number;
  status: 'low' | 'critical' | 'normal' | 'overstock';
}

// Product Supplier (from product_suppliers table)
export interface ProductSupplier {
  id: string;
  product_id: string;
  supplier_id: string;
  lead_time_days: number;
  min_order_quantity: number;
  is_primary: boolean;
  valid_from?: Date | null;
  valid_to?: Date | null;
  supplier?: Supplier;
}

// Supplier Interface
export interface Supplier {
  id: string;
  supplier_code: string;
  supplier_name: string;
  contact_name?: string | null;
  email?: string | null;
  phone_number?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  payment_terms_days: number;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
}

// Promotion Interface
export interface Promotion {
  id: string;
  promo_code: string;
  name: string;
  promo_type: 'price_override' | 'discount_percent' | 'discount_amount' | 'bundle' | 'other';
  start_date: Date;
  end_date: Date;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
}

// Order Interface (simplified)
export interface Order {
  id: string;
  order_number: string;
  order_date: Date;
  total_amount: number;
  status: string;
}

// Attachment Interface
export interface Attachment {
  id: string;
  attachment_type_id?: string | null;
  original_filename: string;
  stored_filename: string;
  file_path: string;
  file_size_bytes: number;
  mime_type: string;
  file_hash?: string | null;
  entity_type: string;
  entity_id: string;
  uploaded_by?: string | null;
  uploaded_at: Date;
  is_deleted: boolean;
  deleted_at?: Date | null;
  deleted_by?: string | null;
}

// Audit Log Interface
export interface AuditLog {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  user_id?: string | null;
  action_timestamp: Date;
  old_values?: Record<string, unknown>;
  new_values?: Record<string, unknown>;
  description?: string | null;
}

// Price History Entry
export interface PriceHistory {
  id: string;
  product_id: string;
  list_price: number;
  effective_date: Date;
  created_by?: string | null;
  created_at: Date;
}

// Product List Item (for grid display with joined data)
export interface ProductListItem {
  id: string;
  product_code: string;
  product_name: string;
  category_name?: string;
  brand_name?: string;
  list_price: number;
  is_active: boolean;
  created_at: Date;
  category?: ProductCategory;
  brand?: Brand;
}
